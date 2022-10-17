import pytest
from freezegun import freeze_time

from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    dao_get_free_sms_fragment_limit_for_year,
    dao_update_annual_billing_for_future_years,
    set_default_free_allowance_for_service,
)
from app.dao.date_util import get_current_financial_year_start_year
from app.models import AnnualBilling
from tests.app.db import create_annual_billing, create_service


def test_dao_update_free_sms_fragment_limit(notify_db_session, sample_service):
    new_limit = 9999
    year = get_current_financial_year_start_year()
    dao_create_or_update_annual_billing_for_year(sample_service.id, new_limit, year)
    new_free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, year)

    assert new_free_limit.free_sms_fragment_limit == new_limit


def test_create_annual_billing(sample_service):

    dao_create_or_update_annual_billing_for_year(sample_service.id, 9999, 2016)

    free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, 2016)

    assert free_limit.free_sms_fragment_limit == 9999


def test_dao_update_annual_billing_for_future_years(notify_db_session, sample_service):
    current_year = get_current_financial_year_start_year()
    limits = [1, 2, 3, 4]
    create_annual_billing(sample_service.id, limits[0], current_year - 1)
    create_annual_billing(sample_service.id, limits[2], current_year + 1)
    create_annual_billing(sample_service.id, limits[3], current_year + 2)

    dao_update_annual_billing_for_future_years(sample_service.id, 9999, current_year)

    assert dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year - 1).free_sms_fragment_limit == 1
    # current year is not created
    assert dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year) is None
    assert dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year + 1).free_sms_fragment_limit == 9999
    assert dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year + 2).free_sms_fragment_limit == 9999


@pytest.mark.parametrize('org_type, year, expected_default',
                         [('federal', 2021, 150000),
                          ('state', 2021, 150000),
                          (None, 2021, 150000),
                          ('federal', 2020, 250000),
                          ('state', 2020, 250000),
                          ('other', 2020, 250000),
                          (None, 2020, 250000),
                          ('federal', 2019, 250000),
                          ('federal', 2022, 40000),
                          ('state', 2022, 40000),
                          ('federal', 2023, 40000),
                          ])
def test_set_default_free_allowance_for_service(notify_db_session, org_type, year, expected_default):

    service = create_service(organisation_type=org_type)

    set_default_free_allowance_for_service(service=service, year_start=year)

    annual_billing = AnnualBilling.query.all()

    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == service.id
    assert annual_billing[0].free_sms_fragment_limit == expected_default


@freeze_time('2021-03-29 14:02:00')
def test_set_default_free_allowance_for_service_using_correct_year(sample_service, mocker):
    mock_dao = mocker.patch('app.dao.annual_billing_dao.dao_create_or_update_annual_billing_for_year')
    set_default_free_allowance_for_service(service=sample_service, year_start=None)

    mock_dao.assert_called_once_with(
        sample_service.id,
        250000,
        2020
    )


@freeze_time('2021-04-01 14:02:00')
def test_set_default_free_allowance_for_service_updates_existing_year(sample_service):
    set_default_free_allowance_for_service(service=sample_service, year_start=None)
    annual_billing = AnnualBilling.query.all()
    assert not sample_service.organisation_type
    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == sample_service.id
    assert annual_billing[0].free_sms_fragment_limit == 150000

    sample_service.organisation_type = 'federal'

    set_default_free_allowance_for_service(service=sample_service, year_start=None)
    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == sample_service.id
    assert annual_billing[0].free_sms_fragment_limit == 150000
