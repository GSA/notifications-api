import pytest

from app.commands import (
    create_test_user,
    insert_inbound_numbers_from_file,
    populate_annual_billing_with_defaults,
    update_template,
)
from app.dao.inbound_numbers_dao import dao_get_available_inbound_numbers
from app.models import AnnualBilling, Template, User
from tests.app.db import create_annual_billing, create_service


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


@pytest.mark.parametrize("organisation_type, expected_allowance",
                         [('federal', 40000),
                          ('state', 40000)])
def test_populate_annual_billing_with_defaults(
        notify_db_session, notify_api, organisation_type, expected_allowance
):
    service = create_service(service_name=organisation_type, organisation_type=organisation_type)

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ['-y', 2022]
    )

    results = AnnualBilling.query.filter(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id
    ).all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance


def test_populate_annual_billing_with_defaults_sets_free_allowance_to_zero_if_previous_year_is_zero(
        notify_db_session, notify_api
):
    service = create_service(organisation_type='federal')
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

    update_template(
        "299726d2-dba6-42b8-8209-30e1d66ea164",
        "Example text message template!",
        "sms",
        ["Hi, I’m trying out US Notify! Today is ((day of week)) and my favourite colour is ((colour))."],
        ""
    )

    t = Template.query.all()

    assert t[0].name == "Example text message template!"
