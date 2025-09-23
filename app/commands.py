import csv
import functools
import itertools
import secrets
import uuid
from datetime import datetime, timedelta
from os import getenv

import click
import flask
from click_datetime import Datetime as click_dt
from faker import Faker
from flask import current_app, json
from sqlalchemy import and_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app import db, redis_store
from app.aws import s3
from app.celery.nightly_tasks import cleanup_unfinished_jobs
from app.celery.tasks import (
    generate_notification_reports_task,
    process_row,
)
from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    set_default_free_allowance_for_service,
)
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.organization_dao import (
    dao_add_service_to_organization,
    dao_get_organization_by_email_address,
    dao_get_organization_by_id,
)
from app.dao.service_sms_sender_dao import dao_get_sms_senders_by_service_id
from app.dao.services_dao import (
    dao_fetch_all_services_by_user,
    dao_fetch_all_services_created_by_user,
    dao_fetch_service_by_id,
    dao_update_service,
    delete_service_and_all_associated_db_objects,
    get_services_by_partial_name,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.users_dao import (
    delete_model_user,
    delete_user_verify_codes,
    get_user_by_email,
)
from app.enums import AuthType, KeyType, NotificationStatus, NotificationType
from app.models import (
    AnnualBilling,
    Domain,
    EmailBranding,
    Notification,
    Organization,
    Service,
    Template,
    TemplateHistory,
    User,
)
from app.utils import utc_now
from notifications_python_client.authentication import create_jwt_token
from notifications_utils.recipients import RecipientCSV
from notifications_utils.template import SMSMessageTemplate
from tests.app.db import (
    create_job,
    create_notification,
    create_organization,
    create_service,
    create_template,
    create_user,
)

# used in add-test-* commands
fake = Faker(["en_US"])


@click.group(name="command", help="Additional commands")
def command_group():
    pass


class notify_command:
    def __init__(self, name=None):
        self.name = name

    def __call__(self, func):
        decorators = [
            functools.wraps(func),  # carry through function name, docstrings, etc.
            click.command(name=self.name),  # turn it into a click.Command
        ]

        # in the test environment the app context is already provided and having
        # another will lead to the test db connection being closed prematurely
        if getenv("NOTIFY_ENVIRONMENT", "") != "test":
            # with_appcontext ensures the config is loaded, db connected, etc.
            decorators.insert(0, flask.cli.with_appcontext)

        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        for decorator in decorators:
            # this syntax is equivalent to e.g. "@flask.cli.with_appcontext"
            wrapper = decorator(wrapper)

        command_group.add_command(wrapper)
        return wrapper


@notify_command()
@click.option(
    "-u",
    "--user_email_prefix",
    required=True,
    help="""
    Functional test user email prefix. eg "notify-test-preview"
""",
)  # noqa
def purge_functional_test_data(user_email_prefix):
    """
    Remove non-seeded functional test data

    users, services, etc. Give an email prefix. Probably "notify-tests-preview".
    """
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return
    stmt = select(User).where(User.email_address.like(f"{user_email_prefix}%"))
    users = db.session.execute(stmt).scalars().all()
    for usr in users:
        # Make sure the full email includes a uuid in it
        # Just in case someone decides to use a similar email address.
        try:
            uuid.UUID(usr.email_address.split("@")[0].split("+")[1])
        except ValueError:
            current_app.logger.warning(
                f"Skipping {usr.email_address} as the user email doesn't contain a UUID."
            )
        else:
            services = dao_fetch_all_services_by_user(usr.id)
            if services:
                current_app.logger.info(
                    f"Deleting user {usr.id} which is part of services"
                )
                for service in services:
                    delete_service_and_all_associated_db_objects(service)
            else:
                services_created_by_this_user = dao_fetch_all_services_created_by_user(
                    usr.id
                )
                if services_created_by_this_user:
                    # user is not part of any services but may still have been the one to create the service
                    # sometimes things get in this state if the tests fail half way through
                    # Remove the service they created (but are not a part of) so we can then remove the user
                    current_app.logger.info(f"Deleting services created by {usr.id}")
                    for service in services_created_by_this_user:
                        delete_service_and_all_associated_db_objects(service)

                current_app.logger.info(
                    f"Deleting user {usr.id} which is not part of any services"
                )
                delete_user_verify_codes(usr)
                delete_model_user(usr)


# TODO maintainability what is the purpose of this command?  Who would use it and why?
@notify_command(name="insert-inbound-numbers")
@click.option(
    "-f",
    "--file_name",
    required=True,
    help="""Full path of the file to upload, file is a contains inbound numbers, one number per line.""",
)
def insert_inbound_numbers_from_file(file_name):

    current_app.logger.info(f"Inserting inbound numbers from {file_name}")
    with open(file_name) as file:
        sql = text(
            "insert into inbound_numbers values(:uuid, :line, 'sns', null, True, now(), null);"
        )

        for line in file:
            line = line.strip()
            if line:
                current_app.logger.debug(line)
                db.session.execute(sql, {"uuid": str(uuid.uuid4()), "line": line})
                db.session.commit()


def setup_commands(application):
    application.cli.add_command(command_group)


@notify_command(name="bulk-invite-user-to-service")
@click.option(
    "-f",
    "--file_name",
    required=True,
    help="Full path of the file containing a list of email address for people to invite to a service",
)
@click.option(
    "-s",
    "--service_id",
    required=True,
    help="The id of the service that the invite is for",
)
@click.option(
    "-u", "--user_id", required=True, help="The id of the user that the invite is from"
)
@click.option(
    "-a",
    "--auth_type",
    required=False,
    help="The authentication type for the user, AuthType.SMS or AuthType.EMAIL. "
    "Defaults to AuthType.SMS if not provided",
)
@click.option(
    "-p", "--permissions", required=True, help="Comma separated list of permissions."
)
def bulk_invite_user_to_service(file_name, service_id, user_id, auth_type, permissions):
    #  permissions
    #  manage_users | manage_templates | manage_settings
    #  send messages ==> send_texts | send_emails
    #  Access API keys manage_api_keys
    #  platform_admin
    #  view_activity
    # "send_texts,send_emails,view_activity"
    from app.service_invite.rest import create_invited_user

    file = open(file_name)
    for email_address in file:
        data = {
            "service": service_id,
            "email_address": email_address.strip(),
            "from_user": user_id,
            "permissions": permissions,
            "auth_type": auth_type,
            "invite_link_host": current_app.config["ADMIN_BASE_URL"],
        }
        with current_app.test_request_context(
            path=f"/service/{service_id}/invite/",
            method="POST",
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
        ):
            try:
                response = create_invited_user(service_id)
                current_app.logger.debug(f"RESPONSE {response[1]}")
                if response[1] != 201:
                    current_app.logger.warning(
                        f"*** ERROR occurred for email address: {email_address.strip()}"
                    )
                current_app.logger.debug(response[0].get_data(as_text=True))
            except Exception:
                current_app.logger.exception(
                    f"*** ERROR occurred for email address: {email_address.strip()}.",
                )

    file.close()


@notify_command(name="archive-jobs-created-between-dates")
@click.option(
    "-s",
    "--start_date",
    required=True,
    help="start date inclusive",
    type=click_dt(format="%Y-%m-%d"),
)
@click.option(
    "-e",
    "--end_date",
    required=True,
    help="end date inclusive",
    type=click_dt(format="%Y-%m-%d"),
)
def update_jobs_archived_flag(start_date, end_date):
    current_app.logger.info(
        f"Archiving jobs created between {start_date} to {end_date}"
    )

    process_date = start_date
    total_updated = 0

    while process_date < end_date:
        start_time = utc_now()
        sql = """update
                    jobs set archived = true
                where
                    created_at >= (date :start + time '00:00:00')
                    and created_at < (date :end + time '00:00:00')
        """
        result = db.session.execute(
            text(sql), {"start": process_date, "end": process_date + timedelta(days=1)}
        )
        db.session.commit()
        current_app.logger.info(
            f"jobs: --- Completed took {datetime.now() - start_time}ms. Archived "
            f"{result.rowcount} jobs for {process_date}"
        )

        process_date += timedelta(days=1)

        total_updated += result.rowcount
    current_app.logger.info(f"Total archived jobs = {total_updated}")


@notify_command(name="populate-organizations-from-file")
@click.option(
    "-f",
    "--file_name",
    required=True,
    help="Pipe delimited file containing organization name, sector, agreement_signed, domains",
)
def populate_organizations_from_file(file_name):
    # [0] organization name:: name of the organization insert if organization is missing.
    # [1] sector:: Federal | State only
    # [2] agreement_signed:: TRUE | FALSE
    # [3] domains:: comma separated list of domains related to the organization
    # [4] email branding name: name of the default email branding for the org

    # The expectation is that the organization, organization_to_service
    # and user_to_organization will be cleared before running this command.
    # Ignoring duplicates allows us to run the command again with the same file or same file with new rows.
    with open(file_name, "r") as f:

        def boolean_or_none(field):
            if field == "1":
                return True
            elif field == "0":
                return False
            elif field == "":
                return None

        for line in itertools.islice(f, 1, None):
            columns = line.split("|")
            email_branding = None
            email_branding_column = columns[5].strip()
            if len(email_branding_column) > 0:
                stmt = select(EmailBranding).where(
                    EmailBranding.name == email_branding_column
                )
                email_branding = db.session.execute(stmt).scalars().one()
            data = {
                "name": columns[0],
                "active": True,
                "agreement_signed": boolean_or_none(columns[3]),
                "organization_type": columns[1].lower(),
                "email_branding_id": email_branding.id if email_branding else None,
            }
            org = Organization(**data)
            try:
                db.session.add(org)
                db.session.commit()
            except IntegrityError:
                current_app.logger.exception(f"Error duplicate org {org.name}")
                db.session.rollback()
            domains = columns[4].split(",")
            for d in domains:
                if len(d.strip()) > 0:
                    domain = Domain(domain=d.strip(), organization_id=org.id)
                    try:
                        db.session.add(domain)
                        db.session.commit()
                    except IntegrityError:
                        current_app.logger.exception(
                            f"Integrity error duplicate domain {d.strip()}",
                        )
                        db.session.rollback()


@notify_command(name="populate-organization-agreement-details-from-file")
@click.option(
    "-f",
    "--file_name",
    required=True,
    help="CSV file containing id, agreement_signed_version, "
    "agreement_signed_on_behalf_of_name, agreement_signed_at",
)
def populate_organization_agreement_details_from_file(file_name):
    """
    The input file should be a comma separated CSV file with a header row and 4 columns
    id: the organization ID
    agreement_signed_version
    agreement_signed_on_behalf_of_name
    agreement_signed_at: The date the agreement was signed in the format of 'dd/mm/yyyy'
    """
    with open(file_name) as f:
        csv_reader = csv.reader(f)
        # ignore the header row
        next(csv_reader)

        for row in csv_reader:
            org = dao_get_organization_by_id(row[0])
            current_app.logger.info(f"Updating {org.name}")
            if not org.agreement_signed:
                raise RuntimeError("Agreement was not signed")

            org.agreement_signed_version = float(row[1])
            org.agreement_signed_on_behalf_of_name = row[2].strip()
            org.agreement_signed_at = datetime.strptime(row[3], "%d/%m/%Y")

            db.session.add(org)
            db.session.commit()


@notify_command(name="associate-services-to-organizations")
def associate_services_to_organizations():
    stmt = select(Service.get_history_model()).where(
        Service.get_history_model().version == 1
    )
    services = db.session.execute(stmt).scalars().all()

    for s in services:
        stmt = select(User).where(User.id == s.created_by_id)
        created_by_user = db.session.execute(stmt).scalars().first()
        organization = dao_get_organization_by_email_address(
            created_by_user.email_address
        )
        service = dao_fetch_service_by_id(service_id=s.id)
        if organization:
            dao_add_service_to_organization(
                service=service, organization_id=organization.id
            )

    current_app.logger.info("finished associating services to organizations")


@notify_command(name="populate-go-live")
@click.option(
    "-f", "--file_name", required=True, help="CSV file containing live service data"
)
def populate_go_live(file_name):
    # 0 - count, 1- Link, 2- Service ID, 3- DEPT, 4- Service Name, 5- Main contact,
    # 6- Contact detail, 7-MOU, 8- LIVE date, 9- SMS, 10 - Email, 11 - Letters, 12 -CRM, 13 - Blue badge
    import csv

    with open(file_name, "r") as f:
        rows = csv.reader(
            f,
            quoting=csv.QUOTE_MINIMAL,
            skipinitialspace=True,
        )
        current_app.logger.debug(next(rows))  # ignore header row
        for index, row in enumerate(rows):
            current_app.logger.debug(index, row)
            service_id = row[2]
            go_live_email = row[6]
            go_live_date = datetime.strptime(row[8], "%d/%m/%Y") + timedelta(hours=12)
            current_app.logger.debug(service_id, go_live_email, go_live_date)
            try:
                if go_live_email:
                    go_live_user = get_user_by_email(go_live_email)
                else:
                    go_live_user = None
            except NoResultFound:
                current_app.logger.exception("No user found for email address")
                continue
            try:
                service = dao_fetch_service_by_id(service_id)
            except NoResultFound:
                current_app.logger.exception(
                    f"No service found for service: {service_id}"
                )
                continue
            service.go_live_user = go_live_user
            service.go_live_at = go_live_date
            dao_update_service(service)


@notify_command(name="fix-billable-units")
def fix_billable_units():
    stmt = select(Notification).where(
        Notification.notification_type == NotificationType.SMS,
        Notification.status != NotificationStatus.CREATED,
        Notification.sent_at == None,  # noqa
        Notification.billable_units == 0,
        Notification.key_type != KeyType.TEST,
    )
    all = db.session.execute(stmt).scalars().all()

    for notification in all:
        template_model = dao_get_template_by_id(
            notification.template_id, notification.template_version
        )

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=notification.service.name,
            show_prefix=notification.service.prefix_sms,
        )
        current_app.logger.info(
            f"Updating notification: {notification.id} with {template.fragment_count} billable_units"
        )

        stmt = (
            update(Notification)
            .where(Notification.id == notification.id)
            .values({"billable_units": template.fragment_count})
        )
        db.session.execute(stmt)
    db.session.commit()


@notify_command(name="delete-unfinished-jobs")
def delete_unfinished_jobs():
    cleanup_unfinished_jobs()


@notify_command(name="process-row-from-job")
@click.option("-j", "--job_id", required=True, help="Job id")
@click.option("-n", "--job_row_number", type=int, required=True, help="Job id")
def process_row_from_job(job_id, job_row_number):
    job = dao_get_job_by_id(job_id)
    db_template = dao_get_template_by_id(job.template_id, job.template_version)

    template = db_template._as_utils_template()

    for row in RecipientCSV(
        s3.get_job_from_s3(str(job.service_id), str(job.id)),
        template_type=template.template_type,
        placeholders=template.placeholders,
    ).get_rows():
        if row.index == job_row_number:
            notification_id = process_row(row, template, job, job.service)
            current_app.logger.info(
                f"Process row {job_row_number} for job {job_id} created notification_id: {notification_id}"
            )


@notify_command(name="download-csv-file-by-name")
@click.option("-f", "--csv_filename", required=True, help="S3 file location")
def download_csv_file_by_name(csv_filename):
    # poetry run flask command download-csv-file-by-name -f <s3 file location>
    # cf run-task notify-api-production --command "flask command download-csv-file-by-name -f <s3 location>"
    bucket_name = current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]
    access_key = current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"]
    secret = current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"]
    region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]

    s3.download_from_s3(
        bucket_name, csv_filename, "download.csv", access_key, secret, region
    )


@notify_command(name="dump-sms-senders")
@click.argument("service_name")
def dump_sms_senders(service_name):

    # poetry run flask command dump-sms-senders MyServiceName
    # cf run-task notify-api-production --command "flask command dump-sms-senders <MyServiceName>"
    services = get_services_by_partial_name(service_name)
    if len(services) > 1:
        raise ValueError(
            f"Please use a unique and complete service name instead of {service_name}"
        )

    senders = dao_get_sms_senders_by_service_id(services[0].id)
    for sender in senders:
        # Not PII, okay to put in logs
        click.echo(sender.serialize())


@notify_command(name="populate-annual-billing-with-the-previous-years-allowance")
@click.option(
    "-y",
    "--year",
    required=True,
    type=int,
    help="""The year to populate the annual billing data for, i.e. 2019""",
)
def populate_annual_billing_with_the_previous_years_allowance(year):
    """
    add annual_billing for given year.
    """
    sql = """
        Select id from services where active = true
        except
        select service_id
        from annual_billing
        where financial_year_start = :year
    """
    services_without_annual_billing = db.session.execute(text(sql), {"year": year})
    for row in services_without_annual_billing:
        latest_annual_billing = """
            Select free_sms_fragment_limit
            from annual_billing
            where service_id = :service_id
            order by financial_year_start desc limit 1
        """
        free_allowance_rows = db.session.execute(
            text(latest_annual_billing), {"service_id": row.id}
        )
        free_allowance = [x[0] for x in free_allowance_rows]
        current_app.logger.info(
            f"create free limit of {free_allowance[0]} for service: {row.id}"
        )
        dao_create_or_update_annual_billing_for_year(
            service_id=row.id,
            free_sms_fragment_limit=free_allowance[0],
            financial_year_start=int(year),
        )


@notify_command(name="dump-user-info")
@click.argument("user_email_address")
def dump_user_info(user_email_address):
    user = get_user_by_email(user_email_address)
    content = user.serialize()
    with open("user_download.json", "wb") as f:
        f.write(json.dumps(content).encode("utf8"))
    f.close()
    current_app.logger.debug("Successfully downloaded user info to user_download.json")


@notify_command(name="populate-annual-billing-with-defaults")
@click.option(
    "-y",
    "--year",
    required=True,
    type=int,
    help="""The year to populate the annual billing data for, i.e. 2021""",
)
@click.option(
    "-m",
    "--missing-services-only",
    default=True,
    type=bool,
    help="""If true then only populate services missing from annual billing for the year.
                      If false populate the default values for all active services.""",
)
def populate_annual_billing_with_defaults(year, missing_services_only):
    """
    Add or update annual billing with free allowance defaults for all active services.
    The default free allowance limits are in: app/dao/annual_billing_dao.py:57.

    If missing_services_only is true then only add rows for services that do not have annual billing for that year yet.
    This is useful to prevent overriding any services that have a free allowance that is not the default.

    If missing_services_only is false then add or update annual billing for all active services.
    This is useful to ensure all services start the new year with the correct annual billing.
    """
    if missing_services_only:
        stmt = (
            select(Service)
            .where(Service.active)
            .outerjoin(
                AnnualBilling,
                and_(
                    Service.id == AnnualBilling.service_id,
                    AnnualBilling.financial_year_start == year,
                ),
            )
            .where(AnnualBilling.id == None)  # noqa
        )
        active_services = db.session.execute(stmt).scalars().all()
    else:
        stmt = select(Service).where(Service.active)
        active_services = db.session.execute(stmt).scalars().all()
    previous_year = year - 1
    services_with_zero_free_allowance = (
        db.session.query(AnnualBilling.service_id)
        .where(
            AnnualBilling.financial_year_start == previous_year,
            AnnualBilling.free_sms_fragment_limit == 0,
        )
        .all()
    )

    for service in active_services:
        # If a service has free_sms_fragment_limit for the previous year
        # set the free allowance for this year to 0 as well.
        # Else use the default free allowance for the service.
        if service.id in [x.service_id for x in services_with_zero_free_allowance]:
            current_app.logger.info(f"update service {service.id} to 0")
            dao_create_or_update_annual_billing_for_year(
                service_id=service.id,
                free_sms_fragment_limit=0,
                financial_year_start=year,
            )
        else:
            current_app.logger.info(f"update service {service.id} with default")
            set_default_free_allowance_for_service(service, year)


# We use noqa to protect this method from the vulture dead code check.  Otherwise, the params ctx and param
# will trigger vulture and cause a build failure.
def validate_mobile(ctx, param, value):  # noqa
    if len("".join(i for i in value if i.isdigit())) != 10:
        raise click.BadParameter("mobile number must have 10 digits")
    else:
        return value


@notify_command(name="create-test-user")
@click.option("-n", "--name", required=True, prompt=True)
@click.option("-e", "--email", required=True, prompt=True)  # TODO: require valid email
@click.option(
    "-m", "--mobile_number", required=True, prompt=True, callback=validate_mobile
)
@click.option(
    "-p",
    "--password",
    required=True,
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
)
@click.option("-a", "--auth_type", default=AuthType.SMS)
@click.option("-s", "--state", default="active")
@click.option("-d", "--admin", default=False, type=bool)
def create_test_user(name, email, mobile_number, password, auth_type, state, admin):
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test", "staging"]:
        current_app.logger.error("Can only be run in development, test, staging")
        return

    data = {
        "name": name,
        "email_address": email,
        "mobile_number": mobile_number,
        "password": password,
        "auth_type": auth_type,
        "state": state,  # skip the email verification for our test user
        "platform_admin": admin,
    }
    user = User(**data)
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        current_app.logger.exception("Integrity error duplicate user")
        db.session.rollback()


@notify_command(name="create-admin-jwt")
def create_admin_jwt():
    if getenv("NOTIFY_ENVIRONMENT", "") != "development":
        current_app.logger.error("Can only be run in development")
        return
    current_app.logger.info(
        create_jwt_token(
            current_app.config["SECRET_KEY"], current_app.config["ADMIN_CLIENT_ID"]
        )
    )


@notify_command(name="create-user-jwt")
@click.option("-t", "--token", required=True, prompt=False)
def create_user_jwt(token):
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return
    service_id = token[-73:-37]
    api_key = token[-36:]
    token = create_jwt_token(api_key, service_id)
    current_app.logger.info(token)


def _update_template(id, name, template_type, content, subject):
    stmt = select(Template).where(Template.id == id)
    template = db.session.execute(stmt).scalars().first()
    if not template:
        template = Template(id=id)
        template.service_id = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"
        template.created_by_id = "6af522d0-2915-4e52-83a3-3690455a5fe6"
        db.session.add(template)
    template.name = name
    template.template_type = template_type
    template.content = "\n".join(content)
    template.subject = subject

    stmt = select(TemplateHistory).where(TemplateHistory.id == id)
    history = db.session.execute(stmt).scalars().first()
    if not history:
        history = TemplateHistory(id=id)
        history.service_id = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"
        history.created_by_id = "6af522d0-2915-4e52-83a3-3690455a5fe6"
        history.version = 1
        db.session.add(history)
    history.name = name
    history.template_type = template_type
    history.content = "\n".join(content)
    history.subject = subject

    db.session.commit()


@notify_command(name="clear-redis-list")
@click.option("-n", "--name_of_list", required=True)
def clear_redis_list(name_of_list):
    my_len_before = redis_store.llen(name_of_list)
    redis_store.ltrim(name_of_list, 1, 0)
    my_len_after = redis_store.llen(name_of_list)
    current_app.logger.info(
        f"Cleared redis list {name_of_list}. Before: {my_len_before} after {my_len_after}"
    )


@notify_command(name="update-templates")
def update_templates():
    with open(current_app.config["CONFIG_FILES"] + "/templates.json") as f:
        data = json.load(f)
        for d in data:
            _update_template(d["id"], d["name"], d["type"], d["content"], d["subject"])
    _clear_templates_from_cache()


@notify_command(name="generate-notification-reports")
def generate_notification_reports():
    generate_notification_reports_task()


def _clear_templates_from_cache():
    # When we update-templates in the db, we need to make sure to delete them
    # from redis, otherwise the old versions will stick around forever.
    CACHE_KEYS = [
        "service-????????-????-????-????-????????????-templates",
        "service-????????-????-????-????-????????????-template-????????-????-????-????-????????????-version-*",  # noqa
        "service-????????-????-????-????-????????????-template-????????-????-????-????-????????????-versions",  # noqa
    ]

    num_deleted = sum(redis_store.delete_by_pattern(pattern) for pattern in CACHE_KEYS)
    current_app.logger.info(f"Number of templates deleted from cache {num_deleted}")


@notify_command(name="create-new-service")
@click.option("-n", "--name", required=True, prompt=True)
@click.option("-l", "--message_limit", required=False, default=40000)
@click.option("-r", "--restricted", required=False, default=False)
@click.option("-e", "--email_from", required=True)
@click.option("-c", "--created_by_id", required=True)
def create_new_service(name, message_limit, restricted, email_from, created_by_id):
    data = {
        "name": name,
        "message_limit": message_limit,
        "restricted": restricted,
        "email_from": email_from,
        "created_by_id": created_by_id,
    }

    service = Service(**data)
    try:
        db.session.add(service)
        db.session.commit()
    except IntegrityError:
        current_app.logger.info("duplicate service", service.name)
        db.session.rollback()


@notify_command(name="get-service-sender-phones")
@click.option("-s", "--service_id", required=True, prompt=True)
def get_service_sender_phones(service_id):
    sender_phone_numbers = """
            select sms_sender, is_default
            from service_sms_senders
            where service_id = :service_id
        """
    rows = db.session.execute(text(sender_phone_numbers), {"service_id": service_id})
    for row in rows:
        print(row)


@notify_command(name="promote-user-to-platform-admin")
@click.option("-u", "--user-email-address", required=True, prompt=True)
def promote_user_to_platform_admin(user_email_address):
    # If the email address is wrong, sqlalchemy will automatically raise a NoResultFound error which is what we want.
    # See tests.
    user = get_user_by_email(user_email_address)
    user.platform_admin = True
    db.session.add(user)
    db.session.commit()


@notify_command(name="purge-csv-bucket")
def purge_csv_bucket():
    bucket_name = current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]
    access_key = current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"]
    secret = current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"]
    region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]

    s3.purge_bucket(bucket_name, access_key, secret, region)


"""
Commands to load test data into the database for
Orgs, Services, Users, Jobs, Notifications

faker is used to generate some random fields. All
database commands were used from tests/app/db.py
where possible to enable better maintainability.
"""


# generate n number of test orgs into the dev DB
@notify_command(name="add-test-organizations-to-db")
@click.option("-g", "--generate", required=True, prompt=True, default=1)
def add_test_organizations_to_db(generate):  # pragma: no cover
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return

    def generate_gov_agency():
        agency_names = [
            "Bureau",
            "Department",
            "Administration",
            "Authority",
            "Commission",
            "Division",
            "Office",
            "Institute",
            "Agency",
            "Council",
            "Board",
            "Committee",
            "Corporation",
            "Service",
            "Center",
            "Registry",
            "Foundation",
            "Task Force",
            "Unit",
        ]

        government_sectors = [
            "Healthcare",
            "Education",
            "Transportation",
            "Defense",
            "Law Enforcement",
            "Environmental Protection",
            "Housing and Urban Development",
            "Finance and Economy",
            "Social Services",
            "Energy",
            "Agriculture",
            "Labor and Employment",
            "Foreign Affairs",
            "Trade and Commerce",
            "Science and Technology",
        ]

        agency = secrets.choice(agency_names)
        speciality = secrets.choice(government_sectors)

        return f"{fake.word().capitalize()} {speciality} {agency}"

    for num in range(1, int(generate) + 1):
        org = create_organization(
            name=generate_gov_agency(),
            organization_type=secrets.choice(["federal", "state", "other"]),
        )
        current_app.logger.info(f"{num} {org.name} created")


# generate n number of test services into the dev DB
@notify_command(name="add-test-services-to-db")
@click.option("-g", "--generate", required=True, prompt=True, default=1)
def add_test_services_to_db(generate):  # pragma: no cover
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return

    for num in range(1, int(generate) + 1):
        service_name = f"{fake.company()} sample service"
        service = create_service(service_name=service_name)
        current_app.logger.info(f"{num} {service.name} created")


# generate n number of test jobs into the dev DB
@notify_command(name="add-test-jobs-to-db")
@click.option("-g", "--generate", required=True, prompt=True, default=1)
def add_test_jobs_to_db(generate):  # pragma: no cover
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return

    for num in range(1, int(generate) + 1):
        service = create_service(check_if_service_exists=True)
        template = create_template(service=service)
        job = create_job(template)
        current_app.logger.info(f"{num} {job.id} created")


# generate n number of notifications into the dev DB
@notify_command(name="add-test-notifications-to-db")
@click.option("-g", "--generate", required=True, prompt=True, default=1)
def add_test_notifications_to_db(generate):  # pragma: no cover
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return

    for num in range(1, int(generate) + 1):
        service = create_service(check_if_service_exists=True)
        template = create_template(service=service)
        job = create_job(template=template)
        notification = create_notification(
            template=template,
            job=job,
        )
        current_app.logger.info(f"{num} {notification.id} created")


# generate n number of test users into the dev DB
@notify_command(name="add-test-users-to-db")
@click.option("-g", "--generate", required=True, prompt=True, default="1")
@click.option("-s", "--state", default="active")
@click.option("-d", "--admin", default=False, type=bool)
def add_test_users_to_db(generate, state, admin):  # pragma: no cover
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return

    for num in range(1, int(generate) + 1):  # noqa

        def fake_email(name):
            first_name, last_name = name.split(maxsplit=1)
            username = f"{first_name.lower()}.{last_name.lower()}"
            return f"{username}@test.gsa.gov"

        name = fake.name()
        create_user(
            name=name,
            email=fake_email(name),
            state=state,
            platform_admin=admin,
        )
        current_app.logger.info("User created")


# generate a new salt value
@notify_command(name="generate-salt")
def generate_salt():
    if getenv("NOTIFY_ENVIRONMENT", "") not in ["development", "test"]:
        current_app.logger.error("Can only be run in development")
        return
    salt = secrets.token_hex(16)
    print(salt)  # noqa
