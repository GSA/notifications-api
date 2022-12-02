import csv
import functools
import itertools
import uuid
from datetime import datetime, timedelta
from os import getenv

import click
import flask
from click_datetime import Datetime as click_dt
from flask import current_app, json
from notifications_python_client.authentication import create_jwt_token
from notifications_utils.recipients import RecipientCSV
from notifications_utils.statsd_decorators import statsd
from notifications_utils.template import SMSMessageTemplate
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.aws import s3
from app.celery.letters_pdf_tasks import (
    get_pdf_for_templated_letter,
    resanitise_pdf,
)
from app.celery.tasks import process_row, record_daily_sorted_counts
from app.config import QueueNames
from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    set_default_free_allowance_for_service,
)
from app.dao.fact_billing_dao import (
    delete_billing_data_for_service_for_day,
    fetch_billing_data_for_day,
    get_service_ids_that_need_billing_populated,
    update_fact_billing,
)
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.organisation_dao import (
    dao_add_service_to_organisation,
    dao_get_organisation_by_email_address,
    dao_get_organisation_by_id,
)
from app.dao.services_dao import (
    dao_fetch_all_services_by_user,
    dao_fetch_all_services_created_by_user,
    dao_fetch_service_by_id,
    dao_update_service,
    delete_service_and_all_associated_db_objects,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.users_dao import (
    delete_model_user,
    delete_user_verify_codes,
    get_user_by_email,
)
from app.models import (
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    SMS_TYPE,
    AnnualBilling,
    Domain,
    EmailBranding,
    LetterBranding,
    Notification,
    Organisation,
    Service,
    User,
)
from app.utils import get_local_midnight_in_utc


@click.group(name='command', help='Additional commands')
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
        if getenv('NOTIFY_ENVIRONMENT', '') != 'test':
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
@click.option('-u', '--user_email_prefix', required=True, help="""
    Functional test user email prefix. eg "notify-test-preview"
""")  # noqa
def purge_functional_test_data(user_email_prefix):
    """
    Remove non-seeded functional test data

    users, services, etc. Give an email prefix. Probably "notify-tests-preview".
    """
    if getenv('NOTIFY_ENVIRONMENT', '') not in ['development', 'test']:
        current_app.logger.error('Can only be run in development')
        return

    users = User.query.filter(User.email_address.like("{}%".format(user_email_prefix))).all()
    for usr in users:
        # Make sure the full email includes a uuid in it
        # Just in case someone decides to use a similar email address.
        try:
            uuid.UUID(usr.email_address.split("@")[0].split('+')[1])
        except ValueError:
            print("Skipping {} as the user email doesn't contain a UUID.".format(usr.email_address))
        else:
            services = dao_fetch_all_services_by_user(usr.id)
            if services:
                print(f"Deleting user {usr.id} which is part of services")
                for service in services:
                    delete_service_and_all_associated_db_objects(service)
            else:
                services_created_by_this_user = dao_fetch_all_services_created_by_user(usr.id)
                if services_created_by_this_user:
                    # user is not part of any services but may still have been the one to create the service
                    # sometimes things get in this state if the tests fail half way through
                    # Remove the service they created (but are not a part of) so we can then remove the user
                    print(f"Deleting services created by {usr.id}")
                    for service in services_created_by_this_user:
                        delete_service_and_all_associated_db_objects(service)

                print(f"Deleting user {usr.id} which is not part of any services")
                delete_user_verify_codes(usr)
                delete_model_user(usr)


@notify_command(name='insert-inbound-numbers')
@click.option('-f', '--file_name', required=True,
              help="""Full path of the file to upload, file is a contains inbound numbers,
              one number per line. The number must have the format of 07... not 447....""")
def insert_inbound_numbers_from_file(file_name):
    print("Inserting inbound numbers from {}".format(file_name))
    with open(file_name) as file:
        sql = "insert into inbound_numbers values('{}', '{}', 'mmg', null, True, now(), null);"

        for line in file:
            line = line.strip()
            if line:
                print(line)
                db.session.execute(sql.format(uuid.uuid4(), line))
                db.session.commit()


@notify_command(name='replay-create-pdf-for-templated-letter')
@click.option('-n', '--notification_id', type=click.UUID, required=True,
              help="Notification id of the letter that needs the get_pdf_for_templated_letter task replayed")
def replay_create_pdf_for_templated_letter(notification_id):
    print("Create task to get_pdf_for_templated_letter for notification: {}".format(notification_id))
    get_pdf_for_templated_letter.apply_async([str(notification_id)], queue=QueueNames.CREATE_LETTERS_PDF)


@notify_command(name='recreate-pdf-for-precompiled-or-uploaded-letter')
@click.option('-n', '--notification_id', type=click.UUID, required=True,
              help="Notification ID of the precompiled or uploaded letter")
def recreate_pdf_for_precompiled_or_uploaded_letter(notification_id):
    print(f"Call resanitise_pdf task for notification: {notification_id}")
    resanitise_pdf.apply_async([str(notification_id)], queue=QueueNames.LETTERS)


def setup_commands(application):
    application.cli.add_command(command_group)


@notify_command(name='rebuild-ft-billing-for-day')
@click.option('-s', '--service_id', required=False, type=click.UUID)
@click.option('-d', '--day', help="The date to recalculate, as YYYY-MM-DD", required=True,
              type=click_dt(format='%Y-%m-%d'))
def rebuild_ft_billing_for_day(service_id, day):
    """
    Rebuild the data in ft_billing for the given service_id and date
    """
    def rebuild_ft_data(process_day, service):
        deleted_rows = delete_billing_data_for_service_for_day(process_day, service)
        current_app.logger.info('deleted {} existing billing rows for {} on {}'.format(
            deleted_rows,
            service,
            process_day
        ))
        transit_data = fetch_billing_data_for_day(process_day=process_day, service_id=service)
        # transit_data = every row that should exist
        for data in transit_data:
            # upsert existing rows
            update_fact_billing(data, process_day)
        current_app.logger.info('added/updated {} billing rows for {} on {}'.format(
            len(transit_data),
            service,
            process_day
        ))

    if service_id:
        # confirm the service exists
        dao_fetch_service_by_id(service_id)
        rebuild_ft_data(day, service_id)
    else:
        services = get_service_ids_that_need_billing_populated(
            get_local_midnight_in_utc(day),
            get_local_midnight_in_utc(day + timedelta(days=1))
        )
        for row in services:
            rebuild_ft_data(day, row.service_id)


@notify_command(name='bulk-invite-user-to-service')
@click.option('-f', '--file_name', required=True,
              help="Full path of the file containing a list of email address for people to invite to a service")
@click.option('-s', '--service_id', required=True, help='The id of the service that the invite is for')
@click.option('-u', '--user_id', required=True, help='The id of the user that the invite is from')
@click.option('-a', '--auth_type', required=False,
              help='The authentication type for the user, sms_auth or email_auth. Defaults to sms_auth if not provided')
@click.option('-p', '--permissions', required=True, help='Comma separated list of permissions.')
def bulk_invite_user_to_service(file_name, service_id, user_id, auth_type, permissions):
    #  permissions
    #  manage_users | manage_templates | manage_settings
    #  send messages ==> send_texts | send_emails | send_letters
    #  Access API keys manage_api_keys
    #  platform_admin
    #  view_activity
    # "send_texts,send_emails,send_letters,view_activity"
    from app.service_invite.rest import create_invited_user
    file = open(file_name)
    for email_address in file:
        data = {
            'service': service_id,
            'email_address': email_address.strip(),
            'from_user': user_id,
            'permissions': permissions,
            'auth_type': auth_type,
            'invite_link_host': current_app.config['ADMIN_BASE_URL']
        }
        with current_app.test_request_context(
            path='/service/{}/invite/'.format(service_id),
            method='POST',
            data=json.dumps(data),
            headers={"Content-Type": "application/json"}
        ):
            try:
                response = create_invited_user(service_id)
                if response[1] != 201:
                    print("*** ERROR occurred for email address: {}".format(email_address.strip()))
                print(response[0].get_data(as_text=True))
            except Exception as e:
                print("*** ERROR occurred for email address: {}. \n{}".format(email_address.strip(), e))

    file.close()


@notify_command(name='populate-notification-postage')
@click.option(
    '-s',
    '--start_date',
    default=datetime(2017, 2, 1),
    help="start date inclusive",
    type=click_dt(format='%Y-%m-%d')
)
@statsd(namespace="tasks")
def populate_notification_postage(start_date):
    current_app.logger.info('populating historical notification postage')

    total_updated = 0

    while start_date < datetime.utcnow():
        # process in ten day chunks
        end_date = start_date + timedelta(days=10)

        sql = \
            """
            UPDATE {}
            SET postage = 'second'
            WHERE notification_type = 'letter' AND
            postage IS NULL AND
            created_at BETWEEN :start AND :end
            """

        execution_start = datetime.utcnow()

        if end_date > datetime.utcnow() - timedelta(days=8):
            print('Updating notifications table as well')
            db.session.execute(sql.format('notifications'), {'start': start_date, 'end': end_date})

        result = db.session.execute(sql.format('notification_history'), {'start': start_date, 'end': end_date})
        db.session.commit()

        current_app.logger.info('notification postage took {}ms. Migrated {} rows for {} to {}'.format(
            datetime.utcnow() - execution_start, result.rowcount, start_date, end_date))

        start_date += timedelta(days=10)

        total_updated += result.rowcount

    current_app.logger.info('Total inserted/updated records = {}'.format(total_updated))


@notify_command(name='archive-jobs-created-between-dates')
@click.option('-s', '--start_date', required=True, help="start date inclusive", type=click_dt(format='%Y-%m-%d'))
@click.option('-e', '--end_date', required=True, help="end date inclusive", type=click_dt(format='%Y-%m-%d'))
@statsd(namespace="tasks")
def update_jobs_archived_flag(start_date, end_date):
    current_app.logger.info('Archiving jobs created between {} to {}'.format(start_date, end_date))

    process_date = start_date
    total_updated = 0

    while process_date < end_date:
        start_time = datetime.utcnow()
        sql = """update
                    jobs set archived = true
                where
                    created_at >= (date :start + time '00:00:00') at time zone 'America/New_York'
                    at time zone 'UTC'
                    and created_at < (date :end + time '00:00:00') at time zone 'America/New_York' at time zone 'UTC'"""

        result = db.session.execute(sql, {"start": process_date, "end": process_date + timedelta(days=1)})
        db.session.commit()
        current_app.logger.info('jobs: --- Completed took {}ms. Archived {} jobs for {}'.format(
            datetime.now() - start_time, result.rowcount, process_date))

        process_date += timedelta(days=1)

        total_updated += result.rowcount
    current_app.logger.info('Total archived jobs = {}'.format(total_updated))


@notify_command(name='replay-daily-sorted-count-files')
@click.option('-f', '--file_extension', required=False, help="File extension to search for, defaults to rs.txt")
@statsd(namespace="tasks")
def replay_daily_sorted_count_files(file_extension):
    bucket_location = '{}-ftp'.format(current_app.config['NOTIFY_EMAIL_DOMAIN'])
    for filename in s3.get_list_of_files_by_suffix(bucket_name=bucket_location,
                                                   subfolder='root/dispatch',
                                                   suffix=file_extension or '.rs.txt'):
        print("Create task to record daily sorted counts for file: ", filename)
        record_daily_sorted_counts.apply_async([filename], queue=QueueNames.NOTIFY)


@notify_command(name='populate-organisations-from-file')
@click.option('-f', '--file_name', required=True,
              help="Pipe delimited file containing organisation name, sector, crown, argeement_signed, domains")
def populate_organisations_from_file(file_name):
    # [0] organisation name:: name of the organisation insert if organisation is missing.
    # [1] sector:: Federal | State only
    # [2] crown:: TRUE | FALSE only
    # [3] argeement_signed:: TRUE | FALSE
    # [4] domains:: comma separated list of domains related to the organisation
    # [5] email branding name: name of the default email branding for the org
    # [6] letter branding name: name of the default letter branding for the org

    # The expectation is that the organisation, organisation_to_service
    # and user_to_organisation will be cleared before running this command.
    # Ignoring duplicates allows us to run the command again with the same file or same file with new rows.
    with open(file_name, 'r') as f:
        def boolean_or_none(field):
            if field == '1':
                return True
            elif field == '0':
                return False
            elif field == '':
                return None

        for line in itertools.islice(f, 1, None):
            columns = line.split('|')
            print(columns)
            email_branding = None
            email_branding_column = columns[5].strip()
            if len(email_branding_column) > 0:
                email_branding = EmailBranding.query.filter(EmailBranding.name == email_branding_column).one()
            letter_branding = None
            letter_branding_column = columns[6].strip()
            if len(letter_branding_column) > 0:
                letter_branding = LetterBranding.query.filter(LetterBranding.name == letter_branding_column).one()
            data = {
                'name': columns[0],
                'active': True,
                'agreement_signed': boolean_or_none(columns[3]),
                'crown': boolean_or_none(columns[2]),
                'organisation_type': columns[1].lower(),
                'email_branding_id': email_branding.id if email_branding else None,
                'letter_branding_id': letter_branding.id if letter_branding else None

            }
            org = Organisation(**data)
            try:
                db.session.add(org)
                db.session.commit()
            except IntegrityError:
                print("duplicate org", org.name)
                db.session.rollback()
            domains = columns[4].split(',')
            for d in domains:
                if len(d.strip()) > 0:
                    domain = Domain(domain=d.strip(), organisation_id=org.id)
                    try:
                        db.session.add(domain)
                        db.session.commit()
                    except IntegrityError:
                        print("duplicate domain", d.strip())
                        db.session.rollback()


@notify_command(name='populate-organisation-agreement-details-from-file')
@click.option('-f', '--file_name', required=True,
              help="CSV file containing id, agreement_signed_version, "
              "agreement_signed_on_behalf_of_name, agreement_signed_at")
def populate_organisation_agreement_details_from_file(file_name):
    """
    The input file should be a comma separated CSV file with a header row and 4 columns
    id: the organisation ID
    agreement_signed_version
    agreement_signed_on_behalf_of_name
    agreement_signed_at: The date the agreement was signed in the format of 'dd/mm/yyyy'
    """
    with open(file_name) as f:
        csv_reader = csv.reader(f)

        # ignore the header row
        next(csv_reader)

        for row in csv_reader:
            org = dao_get_organisation_by_id(row[0])

            current_app.logger.info(f"Updating {org.name}")

            if not org.agreement_signed:
                raise RuntimeError('Agreement was not signed')

            org.agreement_signed_version = float(row[1])
            org.agreement_signed_on_behalf_of_name = row[2].strip()
            org.agreement_signed_at = datetime.strptime(row[3], "%d/%m/%Y")

            db.session.add(org)
            db.session.commit()


@notify_command(name='get-letter-details-from-zips-sent-file')
@click.argument('file_paths', required=True, nargs=-1)
@statsd(namespace="tasks")
def get_letter_details_from_zips_sent_file(file_paths):
    """Get notification details from letters listed in zips_sent file(s)

    This takes one or more file paths for the zips_sent files in S3 as its parameters, for example:
    get-letter-details-from-zips-sent-file '2019-04-01/zips_sent/filename_1' '2019-04-01/zips_sent/filename_2'
    """

    rows_from_file = []

    for path in file_paths:
        file_contents = s3.get_s3_file(
            bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
            file_location=path
        )
        rows_from_file.extend(json.loads(file_contents))

    notification_references = tuple(row[18:34] for row in rows_from_file)
    get_letters_data_from_references(notification_references)


@notify_command(name='get-notification-and-service-ids-for-letters-that-failed-to-print')
@click.option('-f', '--file_name', required=True,
              help="""Full path of the file to upload, file should contain letter filenames, one per line""")
def get_notification_and_service_ids_for_letters_that_failed_to_print(file_name):
    print("Getting service and notification ids for letter filenames list {}".format(file_name))
    file = open(file_name)
    references = tuple([row[7:23] for row in file])

    get_letters_data_from_references(tuple(references))
    file.close()


def get_letters_data_from_references(notification_references):
    sql = """
        SELECT id, service_id, template_id, reference, job_id, created_at
        FROM notifications
        WHERE reference IN :notification_references
        ORDER BY service_id, job_id"""
    result = db.session.execute(sql, {'notification_references': notification_references}).fetchall()

    with open('zips_sent_details.csv', 'w') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['notification_id', 'service_id', 'template_id', 'reference', 'job_id', 'created_at'])

        for row in result:
            csv_writer.writerow(row)


@notify_command(name='associate-services-to-organisations')
def associate_services_to_organisations():
    services = Service.get_history_model().query.filter_by(
        version=1
    ).all()

    for s in services:
        created_by_user = User.query.filter_by(id=s.created_by_id).first()
        organisation = dao_get_organisation_by_email_address(created_by_user.email_address)
        service = dao_fetch_service_by_id(service_id=s.id)
        if organisation:
            dao_add_service_to_organisation(service=service, organisation_id=organisation.id)

    print("finished associating services to organisations")


@notify_command(name='populate-service-volume-intentions')
@click.option('-f', '--file_name', required=True,
              help="Pipe delimited file containing service_id, SMS, email, letters")
def populate_service_volume_intentions(file_name):
    # [0] service_id
    # [1] SMS:: volume intentions for service
    # [2] Email:: volume intentions for service
    # [3] Letters:: volume intentions for service

    with open(file_name, 'r') as f:
        for line in itertools.islice(f, 1, None):
            columns = line.split(',')
            print(columns)
            service = dao_fetch_service_by_id(columns[0])
            service.volume_sms = columns[1]
            service.volume_email = columns[2]
            service.volume_letter = columns[3]
            dao_update_service(service)
    print("populate-service-volume-intentions complete")


@notify_command(name='populate-go-live')
@click.option('-f', '--file_name', required=True, help='CSV file containing live service data')
def populate_go_live(file_name):
    # 0 - count, 1- Link, 2- Service ID, 3- DEPT, 4- Service Name, 5- Main contact,
    # 6- Contact detail, 7-MOU, 8- LIVE date, 9- SMS, 10 - Email, 11 - Letters, 12 -CRM, 13 - Blue badge
    import csv
    print("Populate go live user and date")
    with open(file_name, 'r') as f:
        rows = csv.reader(
            f,
            quoting=csv.QUOTE_MINIMAL,
            skipinitialspace=True,
        )
        print(next(rows))  # ignore header row
        for index, row in enumerate(rows):
            print(index, row)
            service_id = row[2]
            go_live_email = row[6]
            go_live_date = datetime.strptime(row[8], '%d/%m/%Y') + timedelta(hours=12)
            print(service_id, go_live_email, go_live_date)
            try:
                if go_live_email:
                    go_live_user = get_user_by_email(go_live_email)
                else:
                    go_live_user = None
            except NoResultFound:
                print("No user found for email address: ", go_live_email)
                continue
            try:
                service = dao_fetch_service_by_id(service_id)
            except NoResultFound:
                print("No service found for: ", service_id)
                continue
            service.go_live_user = go_live_user
            service.go_live_at = go_live_date
            dao_update_service(service)


@notify_command(name='fix-billable-units')
def fix_billable_units():
    query = Notification.query.filter(
        Notification.notification_type == SMS_TYPE,
        Notification.status != NOTIFICATION_CREATED,
        Notification.sent_at == None,  # noqa
        Notification.billable_units == 0,
        Notification.key_type != KEY_TYPE_TEST,
    )

    for notification in query.all():
        template_model = dao_get_template_by_id(notification.template_id, notification.template_version)

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=notification.service.name,
            show_prefix=notification.service.prefix_sms,
        )
        print("Updating notification: {} with {} billable_units".format(notification.id, template.fragment_count))

        Notification.query.filter(
            Notification.id == notification.id
        ).update(
            {"billable_units": template.fragment_count}
        )
    db.session.commit()
    print("End fix_billable_units")


@notify_command(name='process-row-from-job')
@click.option('-j', '--job_id', required=True, help='Job id')
@click.option('-n', '--job_row_number', type=int, required=True, help='Job id')
def process_row_from_job(job_id, job_row_number):
    job = dao_get_job_by_id(job_id)
    db_template = dao_get_template_by_id(job.template_id, job.template_version)

    template = db_template._as_utils_template()

    for row in RecipientCSV(
            s3.get_job_from_s3(str(job.service_id), str(job.id)),
            template_type=template.template_type,
            placeholders=template.placeholders
    ).get_rows():
        if row.index == job_row_number:
            notification_id = process_row(row, template, job, job.service)
            current_app.logger.info("Process row {} for job {} created notification_id: {}".format(
                job_row_number, job_id, notification_id))


@notify_command(name='populate-annual-billing-with-the-previous-years-allowance')
@click.option('-y', '--year', required=True, type=int,
              help="""The year to populate the annual billing data for, i.e. 2019""")
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
    services_without_annual_billing = db.session.execute(sql, {"year": year})
    for row in services_without_annual_billing:
        latest_annual_billing = """
            Select free_sms_fragment_limit
            from annual_billing
            where service_id = :service_id
            order by financial_year_start desc limit 1
        """
        free_allowance_rows = db.session.execute(latest_annual_billing, {"service_id": row.id})
        free_allowance = [x[0]for x in free_allowance_rows]
        print("create free limit of {} for service: {}".format(free_allowance[0], row.id))
        dao_create_or_update_annual_billing_for_year(service_id=row.id,
                                                     free_sms_fragment_limit=free_allowance[0],
                                                     financial_year_start=int(year))


@notify_command(name='populate-annual-billing-with-defaults')
@click.option('-y', '--year', required=True, type=int,
              help="""The year to populate the annual billing data for, i.e. 2021""")
@click.option('-m', '--missing-services-only', default=True, type=bool,
              help="""If true then only populate services missing from annual billing for the year.
                      If false populate the default values for all active services.""")
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
        active_services = Service.query.filter(
            Service.active
        ).outerjoin(
            AnnualBilling, and_(Service.id == AnnualBilling.service_id, AnnualBilling.financial_year_start == year)
        ).filter(
            AnnualBilling.id == None  # noqa
        ).all()
    else:
        active_services = Service.query.filter(
            Service.active
        ).all()
    previous_year = year - 1
    services_with_zero_free_allowance = db.session.query(AnnualBilling.service_id).filter(
        AnnualBilling.financial_year_start == previous_year,
        AnnualBilling.free_sms_fragment_limit == 0
    ).all()

    for service in active_services:

        # If a service has free_sms_fragment_limit for the previous year
        # set the free allowance for this year to 0 as well.
        # Else use the default free allowance for the service.
        if service.id in [x.service_id for x in services_with_zero_free_allowance]:
            print(f'update service {service.id} to 0')
            dao_create_or_update_annual_billing_for_year(
                service_id=service.id,
                free_sms_fragment_limit=0,
                financial_year_start=year
            )
        else:
            print(f'update service {service.id} with default')
            set_default_free_allowance_for_service(service, year)


def validate_mobile(ctx, param, value):
    if (len(''.join(i for i in value if i.isdigit())) != 10):
        raise click.BadParameter("mobile number must have 10 digits")
    else:
        return value


@notify_command(name='create-test-user')
@click.option('-n', '--name', required=True, prompt=True)
@click.option('-e', '--email', required=True, prompt=True)  # TODO: require valid email
@click.option('-m', '--mobile_number',
              required=True, prompt=True, callback=validate_mobile)
@click.option('-p', '--password',
              required=True, prompt=True, hide_input=True, confirmation_prompt=True)
@click.option('-a', '--auth_type', default="sms_auth")
@click.option('-s', '--state', default="active")
@click.option('-d', '--admin', default=False, type=bool)
def create_test_user(name, email, mobile_number, password, auth_type, state, admin):
    if getenv('NOTIFY_ENVIRONMENT', '') not in ['development', 'test']:
        current_app.logger.error('Can only be run in development')
        return

    data = {
        'name': name,
        'email_address': email,
        'mobile_number': mobile_number,
        'password': password,
        'auth_type': auth_type,
        'state': state,  # skip the email verification for our test user
        'platform_admin': admin,
    }
    user = User(**data)
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        print("duplicate user", user.name)
        db.session.rollback()


@notify_command(name='create-admin-jwt')
def create_admin_jwt():
    if getenv('NOTIFY_ENVIRONMENT', '') != 'development':
        current_app.logger.error('Can only be run in development')
        return
    print(create_jwt_token(current_app.config['SECRET_KEY'], current_app.config['ADMIN_CLIENT_ID']))


@notify_command(name='create-user-jwt')
@click.option('-t', '--token', required=True, prompt=False)
def create_user_jwt(token):
    if getenv('NOTIFY_ENVIRONMENT', '') != 'development':
        current_app.logger.error('Can only be run in development')
        return
    service_id = token[-73:-37]
    api_key = token[-36:]
    print(create_jwt_token(api_key, service_id))
