import os

import pytest

from app.commands import (
    _update_template,
    create_test_user,
    fix_billable_units,
    insert_inbound_numbers_from_file,
    populate_annual_billing_with_defaults,
    populate_annual_billing_with_the_previous_years_allowance,
    populate_organization_agreement_details_from_file,
    populate_organizations_from_file,
)
from app.dao.inbound_numbers_dao import dao_get_available_inbound_numbers
from app.models import AnnualBilling, Notification, Organization, Template, User
from tests.app.db import (
    create_annual_billing,
    create_notification,
    create_organization,
    create_service,
)

# @pytest.mark.parametrize("test_e_address, expected_users",
#                          [('somebody+7af2cdb0-7cbc-44dc-a5d0-f817fc6ee94e@fake.gov', 0),
#                           ('somebody@fake.gov', 1)])
# def test_purge_functional_test_data(notify_db_session, notify_api, test_e_address, expected_users):
#
#     user_count = User.query.count()
#     if user_count > 0:
#         users = User.query.all()
#         for user in users:
#             notify_db_session.delete(user)
#         notify_db_session.commit()
#     user_count = User.query.count()
#     assert user_count == 0
#     notify_api.test_cli_runner().invoke(
#         create_test_user, [
#             '--email', test_e_address,
#             '--mobile_number', '202-555-5555',
#             '--password', 'correct horse battery staple',
#             '--name', 'Fake Humanson',
#             # '--auth_type', 'sms_auth',  # this is the default
#             # '--state', 'active',  # this is the default
#             # '--admin', 'False',  # this is the default
#         ]
#     )
#
#     user_count = User.query.count()
#     assert user_count == 1
#     # notify_api.test_cli_runner().invoke(purge_functional_test_data, ['-u', 'somebody'])
#     # if the email address has a uuid, it is test data so it should be purged and there should be
#     # zero users.  Otherwise, it is real data so there should be one user.
#     # assert User.query.count() == expected_users


# def test_purge_functional_test_data_bad_mobile(notify_db_session, notify_api):
#
#     user_count = User.query.count()
#     assert user_count == 0
#     # run the command
#     x = notify_api.test_cli_runner().invoke(
#         create_test_user, [
#             '--email', 'somebody+7af2cdb0-7cbc-44dc-a5d0-f817fc6ee94e@fake.gov',
#             '--mobile_number', '555-555-55554444',
#             '--password', 'correct horse battery staple',
#             '--name', 'Fake Personson',
#             # '--auth_type', 'sms_auth',  # this is the default
#             # '--state', 'active',  # this is the default
#             # '--admin', 'False',  # this is the default
#         ]
#     )
#     print(f"X = {x}")
#     # The bad mobile phone number results in a bad parameter error, leading to a system exit 2 and no entry made in db
#     assert "SystemExit(2)" in str(x)
#     user_count = User.query.count()
#     assert user_count == 0


# def test_update_jobs_archived_flag(notify_db_session, notify_api):
#
#     service_count = Service.query.count()
#     assert service_count == 0
#
#     service = create_service()
#     service_count = Service.query.count()
#     assert service_count == 1
#
#     sms_template = create_template(service=service, template_type='sms')
#     create_job(sms_template)
#
#     # run the command
#     one_hour_past = datetime.datetime.utcnow()
#     one_hour_future = datetime.datetime.utcnow() + datetime.timedelta(days=1)
#
#     one_hour_past = one_hour_past.strftime("%Y-%m-%d")
#     one_hour_future = one_hour_future.strftime("%Y-%m-%d")
#
#     archived_jobs = Job.query.filter(Job.archived is True).count()
#     assert archived_jobs == 0
#
#     notify_api.test_cli_runner().invoke(
#         update_jobs_archived_flag, [
#             '-e', one_hour_future,
#             '-s', one_hour_past,
#         ]
#     )
#     jobs = Job.query.all()
#     assert len(jobs) == 1
#     for job in jobs:
#         assert job.archived is True


def test_populate_organizations_from_file(notify_db_session, notify_api):

    org_count = Organization.query.count()
    assert org_count == 0

    file_name = "./tests/app/orgs1.csv"
    text = "name|blah|blah|blah|||\n" \
           "foo|Federal|True|'foo.gov'|||\n"
    f = open(file_name, "a")
    f.write(text)
    f.close()
    x = notify_api.test_cli_runner().invoke(
        populate_organizations_from_file, [
            '-f', file_name
        ]
    )

    os.remove(file_name)
    print(f"X = {x}")

    org_count = Organization.query.count()
    assert org_count == 1


def test_populate_organization_agreement_details_from_file(notify_db_session, notify_api):
    file_name = "./tests/app/orgs.csv"

    org_count = Organization.query.count()
    assert org_count == 0
    create_organization()
    org_count = Organization.query.count()
    assert org_count == 1

    org = Organization.query.one()
    org.agreement_signed = True
    notify_db_session.commit()

    text = "id,agreement_signed_version,agreement_signed_on_behalf_of_name,agreement_signed_at\n" \
           f"{org.id},1,bob,'2023-01-01 00:00:00'\n"
    f = open(file_name, "a")
    f.write(text)
    f.close()
    x = notify_api.test_cli_runner().invoke(
        populate_organization_agreement_details_from_file, [
            '-f', file_name
        ]
    )
    print(f"X = {x}")

    org_count = Organization.query.count()
    assert org_count == 1
    org = Organization.query.one()
    assert org.agreement_signed_on_behalf_of_name == 'bob'
    os.remove(file_name)


def test_create_test_user_command(notify_db_session, notify_api):

    # number of users before adding ours
    user_count = User.query.count()

    # run the command
    notify_api.test_cli_runner().invoke(
        create_test_user, [
            '--email', 'somebody@fake.gov',
            '--mobile_number', '202-555-5555',
            '--password', 'correct horse battery staple',
            '--name', 'Fake Personson',
            # '--auth_type', 'sms_auth',  # this is the default
            # '--state', 'active',  # this is the default
            # '--admin', 'False',  # this is the default
        ]
    )

    # there should be one more user
    assert User.query.count() == user_count + 1

    # that user should be the one we added
    user = User.query.filter_by(
        name='Fake Personson'
    ).first()
    assert user.email_address == 'somebody@fake.gov'
    assert user.auth_type == 'sms_auth'
    assert user.state == 'active'


def test_insert_inbound_numbers_from_file(notify_db_session, notify_api, tmpdir):
    numbers_file = tmpdir.join("numbers.txt")
    numbers_file.write("07700900373\n07700900473\n07700900375\n\n\n\n")

    notify_api.test_cli_runner().invoke(insert_inbound_numbers_from_file, ['-f', numbers_file])

    inbound_numbers = dao_get_available_inbound_numbers()
    assert len(inbound_numbers) == 3
    assert set(x.number for x in inbound_numbers) == {'07700900373', '07700900473', '07700900375'}


@pytest.mark.parametrize("organization_type, expected_allowance",
                         [('federal', 40000),
                          ('state', 40000)])
def test_populate_annual_billing_with_defaults(
        notify_db_session, notify_api, organization_type, expected_allowance
):
    service = create_service(service_name=organization_type, organization_type=organization_type)

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ['-y', 2022]
    )

    results = AnnualBilling.query.filter(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id
    ).all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance


@pytest.mark.parametrize("organization_type, expected_allowance",
                         [('federal', 40000),
                          ('state', 40000)])
def test_populate_annual_billing_with_the_previous_years_allowance(
        notify_db_session, notify_api, organization_type, expected_allowance
):
    service = create_service(service_name=organization_type, organization_type=organization_type)

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ['-y', 2022]
    )

    results = AnnualBilling.query.filter(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id
    ).all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_the_previous_years_allowance, ['-y', 2023]
    )

    results = AnnualBilling.query.filter(
        AnnualBilling.financial_year_start == 2023,
        AnnualBilling.service_id == service.id
    ).all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance


def test_fix_billable_units(notify_db_session, notify_api, sample_template):

    create_notification(template=sample_template)
    notification = Notification.query.one()
    assert notification.billable_units == 1

    notify_api.test_cli_runner().invoke(
        fix_billable_units, []
    )

    notification = Notification.query.one()
    assert notification.billable_units == 1


def test_populate_annual_billing_with_defaults_sets_free_allowance_to_zero_if_previous_year_is_zero(
        notify_db_session, notify_api
):
    service = create_service(organization_type='federal')
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=0, financial_year_start=2021)
    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ['-y', 2022]
    )

    results = AnnualBilling.query.filter(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id
    ).all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == 0


def test_update_template(
    notify_db_session, email_2fa_code_template
):

    _update_template(
        "299726d2-dba6-42b8-8209-30e1d66ea164",
        "Example text message template!",
        "sms",
        ["Hi, I’m trying out U.S. Notify! Today is ((day of week)) and my favorite color is ((color))."],
        ""
    )

    t = Template.query.all()

    assert t[0].name == "Example text message template!"
