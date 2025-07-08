import json
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

import pytest
from sqlalchemy import func, select

from app import db
from app.commands import (
    _clear_templates_from_cache,
    _update_template,
    associate_services_to_organizations,
    bulk_invite_user_to_service,
    clear_redis_list,
    create_new_service,
    create_test_user,
    create_user_jwt,
    download_csv_file_by_name,
    dump_sms_senders,
    dump_user_info,
    fix_billable_units,
    generate_salt,
    get_service_sender_phones,
    insert_inbound_numbers_from_file,
    populate_annual_billing_with_defaults,
    populate_annual_billing_with_the_previous_years_allowance,
    populate_go_live,
    populate_organization_agreement_details_from_file,
    populate_organizations_from_file,
    process_row_from_job,
    promote_user_to_platform_admin,
    purge_csv_bucket,
    purge_functional_test_data,
    update_jobs_archived_flag,
    update_templates,
)
from app.dao.inbound_numbers_dao import dao_get_available_inbound_numbers
from app.dao.users_dao import get_user_by_email
from app.enums import (
    AuthType,
    KeyType,
    NotificationStatus,
    NotificationType,
    OrganizationType,
    TemplateType,
)
from app.models import (
    AnnualBilling,
    Job,
    Notification,
    Organization,
    Service,
    Template,
    User,
)
from app.utils import utc_now
from tests.app.db import (
    create_annual_billing,
    create_job,
    create_notification,
    create_organization,
    create_service,
    create_template,
)


def _get_user_query_count():
    stmt = select(func.count()).select_from(User)
    return db.session.execute(stmt).scalar() or 0


def test_purge_functional_test_data(notify_db_session, notify_api):
    orig_user_count = _get_user_query_count()

    notify_api.test_cli_runner().invoke(
        create_test_user,
        [
            "--email",
            "somebody+7af2cdb0-7cbc-44dc-a5d0-f817fc6ee94e@fake.gov",
            "--mobile_number",
            "202-555-5555",
            "--password",
            "correct horse battery staple",
            "--name",
            "Fake Humanson",
        ],
    )

    user_count = _get_user_query_count()
    assert user_count == orig_user_count + 1
    notify_api.test_cli_runner().invoke(purge_functional_test_data, ["-u", "somebody"])
    # if the email address has a uuid, it is test data so it should be purged and there should be
    # zero users.  Otherwise, it is real data so there should be one user.
    assert _get_user_query_count() == orig_user_count


def test_purge_functional_test_data_bad_mobile(notify_db_session, notify_api):
    user_count = _get_user_query_count()
    assert user_count == 0
    # run the command
    command_response = notify_api.test_cli_runner().invoke(
        create_test_user,
        [
            "--email",
            "somebody+7af2cdb0-7cbc-44dc-a5d0-f817fc6ee94e@fake.gov",
            "--mobile_number",
            "555-555-55554444",
            "--password",
            "correct horse battery staple",
            "--name",
            "Fake Personson",
        ],
    )
    # The bad mobile phone number results in a bad parameter error,
    # leading to a system exit 2 and no entry made in db
    assert "SystemExit(2)" in str(command_response)
    user_count = _get_user_query_count()
    assert user_count == 0


def test_update_jobs_archived_flag(notify_db_session, notify_api):
    service = create_service()

    sms_template = create_template(service=service, template_type=TemplateType.SMS)
    create_job(sms_template)

    right_now = utc_now()
    tomorrow = right_now + timedelta(days=1)

    right_now = right_now.strftime("%Y-%m-%d")
    tomorrow = tomorrow.strftime("%Y-%m-%d")

    stmt = select(Job).where(Job.archived is True)
    archived_jobs = db.session.execute(stmt).scalar() or 0
    assert archived_jobs == 0

    notify_api.test_cli_runner().invoke(
        update_jobs_archived_flag,
        [
            "-e",
            tomorrow,
            "-s",
            right_now,
        ],
    )
    jobs = db.session.execute(select(Job)).scalars().all()
    assert len(jobs) == 1
    for job in jobs:
        assert job.archived is True


def _get_organization_query_count():
    stmt = select(func.count()).select_from(Organization)
    return db.session.execute(stmt).scalar() or 0


def test_populate_organizations_from_file(notify_db_session, notify_api):
    org_count = _get_organization_query_count()
    assert org_count == 0

    file_name = "./tests/app/orgs1.csv"
    text = "name|blah|blah|blah|||\n" "foo|Federal|True|'foo.gov'|'foo.gov'||\n"
    f = open(file_name, "a")
    f.write(text)
    f.close()
    command_response = notify_api.test_cli_runner().invoke(
        populate_organizations_from_file, ["-f", file_name]
    )

    os.remove(file_name)
    print(f"command_response = {command_response}")

    org_count = _get_organization_query_count()
    assert org_count == 1


def test_populate_organization_agreement_details_from_file(
    notify_db_session, notify_api
):
    file_name = "./tests/app/orgs.csv"

    org_count = _get_organization_query_count()
    assert org_count == 0
    create_organization()
    org_count = _get_organization_query_count()
    assert org_count == 1

    org = db.session.execute(select(Organization)).scalars().one()
    org.agreement_signed = True
    notify_db_session.commit()

    text = (
        "id,agreement_signed_version,agreement_signed_on_behalf_of_name,agreement_signed_at\n"
        f"{org.id},1,bob,'2023-01-01 00:00:00'\n"
    )
    f = open(file_name, "a")
    f.write(text)
    f.close()
    command_response = notify_api.test_cli_runner().invoke(
        populate_organization_agreement_details_from_file, ["-f", file_name]
    )
    print(f"command_response = {command_response}")

    org_count = _get_organization_query_count()
    assert org_count == 1
    org = db.session.execute(select(Organization)).scalars().one()
    assert org.agreement_signed_on_behalf_of_name == "bob"
    os.remove(file_name)


def _get_organization_query_one():
    stmt = select(Organization)
    return db.session.execute(stmt).scalars().one()


def test_bulk_invite_user_to_service(
    notify_db_session, notify_api, sample_service, sample_user
):
    file_name = "./tests/app/users.csv"

    text = (
        "service,email_address,from_user,permissions,auth_type,invite_link_host\n"
        f"{sample_service.id},someone@fake.gov,{sample_user.id},sms,platform_admin,https://somewhere.fake.gov'\n"
    )
    f = open(file_name, "a")
    f.write(text)
    f.close()
    command_response = notify_api.test_cli_runner().invoke(
        bulk_invite_user_to_service,
        [
            "-f",
            file_name,
            "-s",
            sample_service.id,
            "-u",
            sample_user.id,
            "-p",
            "send_texts",
        ],
    )
    print(f"command_response = {command_response}")

    assert "okay" in str(command_response)

    os.remove(file_name)


def test_create_test_user_command(notify_db_session, notify_api):
    # number of users before adding ours
    user_count = _get_user_query_count()

    # run the command
    notify_api.test_cli_runner().invoke(
        create_test_user,
        [
            "--email",
            "somebody@fake.gov",
            "--mobile_number",
            "202-555-5555",
            "--password",
            "correct horse battery staple",
            "--name",
            "Fake Personson",
        ],
    )

    # there should be one more user
    assert _get_user_query_count() == user_count + 1

    # that user should be the one we added
    stmt = select(User).where(User.name == "Fake Personson")
    user = db.session.execute(stmt).scalars().first()
    assert user.email_address == "somebody@fake.gov"
    assert user.auth_type == AuthType.SMS
    assert user.state == "active"


def test_insert_inbound_numbers_from_file(notify_db_session, notify_api, tmpdir):
    numbers_file = tmpdir.join("numbers.txt")
    numbers_file.write("07700900373\n07700900473\n07700900375\n\n\n\n")

    notify_api.test_cli_runner().invoke(
        insert_inbound_numbers_from_file, ["-f", numbers_file]
    )

    inbound_numbers = dao_get_available_inbound_numbers()
    assert len(inbound_numbers) == 3
    assert set(x.number for x in inbound_numbers) == {
        "07700900373",
        "07700900473",
        "07700900375",
    }


@pytest.mark.parametrize(
    "organization_type, expected_allowance",
    [(OrganizationType.FEDERAL, 40000), (OrganizationType.STATE, 40000)],
)
def test_populate_annual_billing_with_defaults(
    notify_db_session, notify_api, organization_type, expected_allowance
):
    service = create_service(
        service_name=organization_type,
        organization_type=organization_type,
    )

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ["-y", 2022]
    )

    stmt = select(AnnualBilling).where(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id,
    )
    results = db.session.execute(stmt).scalars().all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance


@pytest.mark.parametrize(
    "organization_type, expected_allowance",
    [(OrganizationType.FEDERAL, 40000), (OrganizationType.STATE, 40000)],
)
def test_populate_annual_billing_with_the_previous_years_allowance(
    notify_db_session, notify_api, organization_type, expected_allowance
):
    service = create_service(
        service_name=organization_type,
        organization_type=organization_type,
    )

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ["-y", 2022]
    )

    stmt = select(AnnualBilling).where(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id,
    )
    results = db.session.execute(stmt).scalars().all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_the_previous_years_allowance, ["-y", 2023]
    )

    stmt = select(AnnualBilling).where(
        AnnualBilling.financial_year_start == 2023,
        AnnualBilling.service_id == service.id,
    )
    results = db.session.execute(stmt).scalars().all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance


def _get_notification_query_one():
    stmt = select(Notification)
    return db.session.execute(stmt).scalars().one()


def test_fix_billable_units(notify_db_session, notify_api, sample_template):
    create_notification(template=sample_template)
    notification = _get_notification_query_one()
    notification.billable_units = 0
    notification.notification_type = NotificationType.SMS
    notification.status = NotificationStatus.DELIVERED
    notification.sent_at = None
    notification.key_type = KeyType.NORMAL

    notify_db_session.commit()

    notify_api.test_cli_runner().invoke(fix_billable_units, [])

    notification = _get_notification_query_one()
    assert notification.billable_units == 1


def test_populate_annual_billing_with_defaults_sets_free_allowance_to_zero_if_previous_year_is_zero(
    notify_db_session, notify_api
):
    service = create_service(organization_type=OrganizationType.FEDERAL)
    create_annual_billing(
        service_id=service.id, free_sms_fragment_limit=0, financial_year_start=2021
    )
    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ["-y", 2022]
    )

    results = (
        db.session.execute(
            select(AnnualBilling).where(
                AnnualBilling.financial_year_start == 2022,
                AnnualBilling.service_id == service.id,
            )
        )
        .scalars()
        .all()
    )

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == 0


def test_update_template(notify_db_session, email_2fa_code_template):
    _update_template(
        "299726d2-dba6-42b8-8209-30e1d66ea164",
        "Example text message template!",
        TemplateType.SMS,
        [
            "Hi, I’m trying out Notify.gov! Today is ((day of week)) and my favorite color is ((color))."
        ],
        "",
    )

    t = db.session.execute(select(Template)).scalars().all()

    assert t[0].name == "Example text message template!"


def test_create_service_command(notify_db_session, notify_api):
    notify_api.test_cli_runner().invoke(
        create_test_user,
        [
            "--email",
            "somebody@fake.gov",
            "--mobile_number",
            "202-555-5555",
            "--password",
            "correct horse battery staple",
            "--name",
            "Fake Personson",
        ],
    )

    user = db.session.execute(select(User)).scalars().first()

    stmt = select(func.count()).select_from(Service)
    service_count = db.session.execute(stmt).scalar() or 0

    # run the command
    notify_api.test_cli_runner().invoke(
        create_new_service,
        ["-e", "somebody@fake.gov", "-n", "Fake Service", "-c", user.id],
    )

    # there should be one more service

    stmt = select(func.count()).select_from(Service)
    count = db.session.execute(stmt).scalar() or 0
    assert count == service_count + 1

    # that service should be the one we added
    stmt = select(Service).where(Service.name == "Fake Service")
    service = db.session.execute(stmt).scalars().first()
    assert service.email_from == "somebody@fake.gov"
    assert service.restricted is False
    assert service.message_limit == 40000


def test_promote_user_to_platform_admin(
    notify_db_session, notify_api, sample_user, sample_platform_admin
):
    assert sample_user.platform_admin is False
    assert sample_platform_admin.platform_admin is True

    notify_api.test_cli_runner().invoke(
        promote_user_to_platform_admin,
        [
            "-u",
            "notify@digital.fake.gov",
        ],
    )

    user = get_user_by_email("notify@digital.fake.gov")
    assert user.platform_admin is True


def test_download_csv_file_by_name(notify_api, mocker):
    mock_download = mocker.patch("app.commands.s3.download_from_s3")
    notify_api.test_cli_runner().invoke(
        download_csv_file_by_name,
        [
            "-f",
            "NonExistentName",
        ],
    )
    mock_download.assert_called_once()


def test_promote_user_to_platform_admin_no_result_found(
    notify_db_session,
    notify_api,
    sample_user,
):
    assert sample_user.platform_admin is False

    result = notify_api.test_cli_runner().invoke(
        promote_user_to_platform_admin,
        [
            "-u",
            "notify@digital.fake.asefasefasefasef",
        ],
    )
    assert "NoResultFound" in str(result)
    assert sample_user.platform_admin is False


def test_populate_go_live_success(notify_api, mocker):
    mock_csv_reader = mocker.patch("app.commands.csv.reader")
    mocker.patch(
        "app.commands.open",
        new_callable=mock_open,
        read_data="""count,Link,Service ID,DEPT,Service Name,Main contact,Contact detail,MOU,LIVE date,SMS,Email,Letters,CRM,Blue badge\n1,link,123,Dept A,Service A,Contact A,email@example.com,MOU,15/10/2024,Yes,Yes,Yes,Yes,No""",  # noqa
    )
    mock_current_app = mocker.patch("app.commands.current_app")
    mock_logger = mock_current_app.logger
    mock_dao_update_service = mocker.patch("app.commands.dao_update_service")
    mock_dao_fetch_service_by_id = mocker.patch("app.commands.dao_fetch_service_by_id")
    mock_get_user_by_email = mocker.patch("app.commands.get_user_by_email")
    mock_csv_reader.return_value = iter(
        [
            [
                "count",
                "Link",
                "Service ID",
                "DEPT",
                "Service Name",
                "Main contract",
                "Contact detail",
                "MOU",
                "LIVE date",
                "SMS",
                "Email",
                "Letters",
                "CRM",
                "Blue badge",
            ],
            [
                "1",
                "link",
                "123",
                "Dept A",
                "Service A",
                "Contact A",
                "email@example.com",
                "MOU",
                "15/10/2024",
                "Yes",
                "Yes",
                "Yes",
                "Yes",
                "No",
            ],
        ]
    )
    mock_user = MagicMock()
    mock_get_user_by_email.return_value = mock_user
    mock_service = MagicMock()
    mock_dao_fetch_service_by_id.return_value = mock_service

    notify_api.test_cli_runner().invoke(
        populate_go_live,
        [
            "-f",
            "dummy_file.csv",
        ],
    )

    mock_get_user_by_email.assert_called_once_with("email@example.com")
    mock_dao_fetch_service_by_id.assert_called_once_with("123")
    mock_service.go_live_user = mock_user
    mock_service.go_live_at = datetime.strptime("15/10/2024", "%d/%m/%Y") + timedelta(
        hours=12
    )
    mock_dao_update_service.assert_called_once_with(mock_service)

    mock_logger.info.assert_any_call("Populate go live user and date")


def test_process_row_from_job_success(notify_api, mocker):
    mock_current_app = mocker.patch("app.commands.current_app")
    mock_logger = mock_current_app.logger
    mock_dao_get_job_by_id = mocker.patch("app.commands.dao_get_job_by_id")
    mock_dao_get_template_by_id = mocker.patch("app.commands.dao_get_template_by_id")
    mock_get_job_from_s3 = mocker.patch("app.commands.s3.get_job_from_s3")
    mock_recipient_csv = mocker.patch("app.commands.RecipientCSV")
    mock_process_row = mocker.patch("app.commands.process_row")

    mock_job = MagicMock()
    mock_job.service_id = "service_123"
    mock_job.id = "job_456"
    mock_job.template_id = "template_789"
    mock_job.template_version = 1
    mock_template = MagicMock()
    mock_template._as_utils_template.return_value = MagicMock(
        template_type="sms", placeholders=["name", "date"]
    )
    mock_row = MagicMock()
    mock_row.index = 2
    mock_recipient_csv.return_value.get_rows.return_value = [mock_row]
    mock_dao_get_job_by_id.return_value = mock_job
    mock_dao_get_template_by_id.return_value = mock_template
    mock_get_job_from_s3.return_value = "some_csv_content"
    mock_process_row.return_value = "notification_123"

    notify_api.test_cli_runner().invoke(
        process_row_from_job,
        ["-j", "job_456", "-n", "2"],
    )
    mock_dao_get_job_by_id.assert_called_once_with("job_456")
    mock_dao_get_template_by_id.assert_called_once_with(
        mock_job.template_id, mock_job.template_version
    )
    mock_get_job_from_s3.assert_called_once_with(
        str(mock_job.service_id), str(mock_job.id)
    )
    mock_recipient_csv.assert_called_once_with(
        "some_csv_content", template_type="sms", placeholders=["name", "date"]
    )
    mock_process_row.assert_called_once_with(
        mock_row, mock_template._as_utils_template(), mock_job, mock_job.service
    )
    mock_logger.infoassert_called_once_with(
        "Process row 2 for job job_456 created notification_id: notification_123"
    )


def test_dump_sms_senders_single_service(notify_api, mocker):
    mock_get_services_by_partial_name = mocker.patch(
        "app.commands.get_services_by_partial_name"
    )
    mock_dao_get_sms_senders_by_service_id = mocker.patch(
        "app.commands.dao_get_sms_senders_by_service_id"
    )

    mock_service = MagicMock()
    mock_service.id = "service_123"
    mock_get_services_by_partial_name.return_value = [mock_service]
    mock_sender_1 = MagicMock()
    mock_sender_1.serialize.return_value = {"name": "Sender 1", "id": "sender_1"}
    mock_sender_2 = MagicMock()
    mock_sender_2.serialize.return_value = {"name": "Sender 2", "id": "sender_2"}
    mock_dao_get_sms_senders_by_service_id.return_value = [mock_sender_1, mock_sender_2]

    notify_api.test_cli_runner().invoke(
        dump_sms_senders,
        ["service_name"],
    )

    mock_get_services_by_partial_name.assert_called_once_with("service_name")
    mock_dao_get_sms_senders_by_service_id.assert_called_once_with("service_123")


def test_dump_user_info(notify_api, mocker):
    mock_open_file = mocker.patch("app.commands.open", new_callable=mock_open)
    mock_get_user_by_email = mocker.patch("app.commands.get_user_by_email")
    mock_user = MagicMock()
    mock_user.serialize.return_value = {"name": "John Doe", "email": "john@example.com"}
    mock_get_user_by_email.return_value = mock_user

    notify_api.test_cli_runner().invoke(
        dump_user_info,
        ["john@example.com"],
    )

    mock_get_user_by_email.assert_called_once_with("john@example.com")
    mock_open_file.assert_called_once_with("user_download.json", "wb")


def test_generate_salt(notify_api):
    runner = notify_api.test_cli_runner()
    result = runner.invoke(generate_salt)
    assert result.exit_code == 0
    assert len(result.output.strip()) == 32


def test_associate_services_to_organizations(notify_api, mocker):
    mock_service_history = MagicMock()
    mock_service_history.id = "service-id-123"
    mock_service_history.version = 1
    mock_service_history.created_by_id = "user-id-456"

    mock_user = MagicMock()
    mock_user.email_address = "test@example.com"

    mock_organization = MagicMock()
    mock_organization.id = "org-id-789"

    mock_service = MagicMock()

    mock_stmt_result = MagicMock()
    mock_stmt_result.scalars.return_value.all.return_value = [mock_service_history]
    mocker.patch("app.commands.db.session.execute", return_value=mock_stmt_result)

    mock_add_to_org = mocker.patch("app.commands.dao_add_service_to_organization")

    mocker.patch(
        "app.commands.dao_get_organization_by_email_address",
        return_value=mock_organization,
    )

    mocker.patch("app.commands.dao_fetch_service_by_id", return_value=mock_service)

    mock_logger = mocker.patch("app.commands.current_app.logger")

    notify_api.test_cli_runner().invoke(associate_services_to_organizations)

    mock_add_to_org.assert_called_once_with(
        service=mock_service, organization_id=mock_organization.id
    )

    mock_logger.info.assert_called_once_with(
        "finished associating services to organizations"
    )


def test_clear_templates_from_cache(mocker):
    mock_delete = mocker.patch(
        "app.commands.redis_store.delete_by_pattern", return_value=3
    )
    mock_logger = mocker.patch("app.commands.current_app.logger")

    _clear_templates_from_cache()

    expected_patterns = [
        "service-????????-????-????-????-????????????-templates",
        "service-????????-????-????-????-????????????-template-????????-????-????-????-????????????-version-*",
        "service-????????-????-????-????-????????????-template-????????-????-????-????-????????????-versions",
    ]

    assert mock_delete.call_count == len(expected_patterns)
    mock_delete.assert_has_calls(
        [mocker.call(p) for p in expected_patterns], any_order=True
    )
    mock_logger.info.assert_called_once_with("Number of templates deleted from cache 9")


@patch("app.commands.s3.purge_bucket")
@patch("app.commands.current_app")
def test_purge_csv_bucket(mock_current_app, mock_purge_bucket, notify_api):
    mock_current_app.config = {
        "CSV_UPLOAD_BUCKET": {
            "bucket": "test-bucket",
            "access_key_id": "FAKE_ACCESS_KEY",
            "secret_access_key": "FAKE_SECRET_KEY",  # pragma: allowlist secret
            "region": "us-north-1",
        }
    }
    runner = notify_api.test_cli_runner()
    runner.invoke(purge_csv_bucket)

    mock_purge_bucket.assert_called_once_with(
        "test-bucket", "FAKE_ACCESS_KEY", "FAKE_SECRET_KEY", "us-north-1"
    )


@patch("app.commands.db.session.execute")
def test_get_service_sender_phones(mock_execute, notify_api):
    runner = notify_api.test_cli_runner()
    result = runner.invoke(get_service_sender_phones, ["-s", "service-id"])
    assert result.exit_code == 0
    mock_execute.assert_called_once()


@patch("app.commands.current_app.logger.info")
def test_create_user_jwt(mock_logger, notify_api, sample_api_key, sample_service):
    token = f"{sample_service.id}{sample_api_key}"
    runner = notify_api.test_cli_runner()
    result = runner.invoke(create_user_jwt, ["-t", token])
    assert result.exit_code == 0
    mock_logger.assert_called_once()


def test_update_templates_calls_update_and_clear(monkeypatch, notify_api):
    templates_data = [
        {
            "id": 1,
            "name": "Template1",
            "type": "email",
            "content": "Hello",
            "subject": "Subject1",
        },
        {
            "id": 2,
            "name": "Template2",
            "type": "sms",
            "content": "Hi",
            "subject": "Subject2",
        },
    ]
    m = mock_open(read_data=json.dumps(templates_data))
    monkeypatch.setattr(
        "app.commands.current_app",
        type("obj", (), {"config": {"CONFIG_FILES": "/fake/path"}}),
    )
    with patch("app.commands.open", m):
        with patch("app.commands._update_template") as mock_update_template, patch(
            "app.commands._clear_templates_from_cache"
        ) as mock_clear_cache:

            runner = notify_api.test_cli_runner()
            result = runner.invoke(update_templates)
            assert result.exit_code == 0

            expected_calls = [
                (1, "Template1", "email", "Hello", "Subject1"),
                (2, "Template2", "sms", "Hi", "Subject2"),
            ]
            actual_calls = [call.args for call in mock_update_template.call_args_list]
            assert actual_calls == expected_calls
            mock_clear_cache.assert_called_once()


def test_clear_redis_list(monkeypatch, notify_api):
    mock_redis_store = type("RedisStoreMock", (), {})()
    monkeypatch.setattr("app.commands.redis_store", mock_redis_store)
    mock_redis_store.llen = lambda list_name: {"before_list": 5, "after_list": 0}[
        list_name
    ]
    ltrim_calls = []

    def fake_ltrim(name, start, end):
        ltrim_calls.append((name, start, end))

    mock_redis_store.ltrim = fake_ltrim
    logger_info_calls = []
    mock_logger = type(
        "LoggerMock", (), {"info": lambda self, msg: logger_info_calls.append(msg)}
    )()
    mock_app = type("FlaskAppMock", (), {"logger": mock_logger})
    monkeypatch.setattr("app.commands.current_app", mock_app)
    call_count = {"count": 0}

    def llen_side_effect(name):
        if call_count["count"] == 0:
            call_count["count"] += 1
            return 5
        return 0

    mock_redis_store.llen = llen_side_effect
    runner = notify_api.test_cli_runner
    result = runner.invoke(clear_redis_list, ["-n", "foo"])
    assert result.exit_code == 0
    assert ltrim_calls == [("test_list", 1, 0)]
    assert logger_info_calls == ["Cleared redis list test_list.  Before: 5 after 0"]
