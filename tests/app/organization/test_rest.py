import uuid
from unittest.mock import Mock

import pytest
from freezegun import freeze_time
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.dao.organization_dao import (
    dao_add_service_to_organization,
    dao_add_user_to_organization,
)
from app.dao.services_dao import dao_archive_service
from app.enums import OrganizationType
from app.models import AnnualBilling, Organization
from app.organization.rest import check_request_args
from app.utils import utc_now
from tests.app.db import (
    create_annual_billing,
    create_domain,
    create_email_branding,
    create_ft_billing,
    create_organization,
    create_service,
    create_template,
    create_user,
)


def test_get_all_organizations(admin_request, notify_db_session):
    create_organization(
        name="inactive org", active=False, organization_type=OrganizationType.FEDERAL
    )
    create_organization(name="active org", domains=["example.com"])

    response = admin_request.get("organization.get_organizations", _expected_status=200)

    assert len(response) == 2
    assert (
        set(response[0].keys())
        == set(response[1].keys())
        == {
            "name",
            "id",
            "active",
            "count_of_live_services",
            "domains",
            "organization_type",
        }
    )
    assert response[0]["name"] == "active org"
    assert response[0]["active"] is True
    assert response[0]["count_of_live_services"] == 0
    assert response[0]["domains"] == ["example.com"]
    assert response[0]["organization_type"] is None
    assert response[1]["name"] == "inactive org"
    assert response[1]["active"] is False
    assert response[1]["count_of_live_services"] == 0
    assert response[1]["domains"] == []
    assert response[1]["organization_type"] == OrganizationType.FEDERAL


def test_get_organization_by_id(admin_request, notify_db_session):
    org = create_organization()

    response = admin_request.get(
        "organization.get_organization_by_id",
        _expected_status=200,
        organization_id=org.id,
    )

    assert set(response.keys()) == {
        "id",
        "name",
        "active",
        "organization_type",
        "agreement_signed",
        "agreement_signed_at",
        "agreement_signed_by_id",
        "agreement_signed_version",
        "agreement_signed_on_behalf_of_name",
        "agreement_signed_on_behalf_of_email_address",
        "email_branding_id",
        "domains",
        "request_to_go_live_notes",
        "count_of_live_services",
        "notes",
        "billing_contact_names",
        "billing_contact_email_addresses",
        "billing_reference",
        "purchase_order_number",
    }
    assert response["id"] == str(org.id)
    assert response["name"] == "test_org_1"
    assert response["active"] is True
    assert response["organization_type"] is None
    assert response["agreement_signed"] is None
    assert response["agreement_signed_by_id"] is None
    assert response["agreement_signed_version"] is None
    assert response["email_branding_id"] is None
    assert response["domains"] == []
    assert response["request_to_go_live_notes"] is None
    assert response["count_of_live_services"] == 0
    assert response["agreement_signed_on_behalf_of_name"] is None
    assert response["agreement_signed_on_behalf_of_email_address"] is None
    assert response["notes"] is None
    assert response["billing_contact_names"] is None
    assert response["billing_contact_email_addresses"] is None
    assert response["billing_reference"] is None
    assert response["purchase_order_number"] is None


def test_get_organization_by_id_returns_domains(admin_request, notify_db_session):
    org = create_organization(
        domains=[
            "foo.gov.uk",
            "bar.gov.uk",
        ]
    )

    response = admin_request.get(
        "organization.get_organization_by_id",
        _expected_status=200,
        organization_id=org.id,
    )

    assert set(response["domains"]) == {
        "foo.gov.uk",
        "bar.gov.uk",
    }


@pytest.mark.parametrize(
    "domain, expected_status",
    (
        ("foo.gov.uk", 200),
        ("bar.gov.uk", 200),
        ("oof.gov.uk", 404),
        ("rab.gov.uk", 200),
        (None, 400),
        ("personally.identifying.information@example.com", 400),
    ),
)
def test_get_organization_by_domain(
    admin_request, notify_db_session, domain, expected_status
):
    org = create_organization()
    other_org = create_organization("Other organization")
    create_domain("foo.gov.uk", org.id)
    create_domain("bar.gov.uk", org.id)
    create_domain("rab.gov.uk", other_org.id)

    response = admin_request.get(
        "organization.get_organization_by_domain",
        _expected_status=expected_status,
        domain=domain,
    )

    if domain == "rab.gov.uk" and expected_status == 200:
        assert response["id"] == str(other_org.id)
    elif expected_status == 200:
        assert response["id"] == str(org.id)
    else:
        assert response["result"] == "error"


def test_post_create_organization(admin_request, notify_db_session):
    data = {
        "name": "test organization",
        "active": True,
        "organization_type": OrganizationType.STATE,
    }

    response = admin_request.post(
        "organization.create_organization", _data=data, _expected_status=201
    )

    organizations = _get_organizations()

    assert data["name"] == response["name"]
    assert data["active"] == response["active"]
    assert data["organization_type"] == response["organization_type"]

    assert len(organizations) == 1
    # check that for non-nhs orgs, default branding is not set
    assert organizations[0].email_branding_id is None


def _get_organizations():
    stmt = select(Organization)
    return db.session.execute(stmt).scalars().all()


def test_post_create_organization_existing_name_raises_400(
    admin_request, sample_organization
):
    organization = _get_organizations()
    assert len(organization) == 1

    data = {
        "name": sample_organization.name,
        "active": True,
        "organization_type": OrganizationType.FEDERAL,
    }

    response = admin_request.post(
        "organization.create_organization", _data=data, _expected_status=400
    )

    organization = _get_organizations()

    assert len(organization) == 1
    assert response["message"] == "Organization name already exists"


def test_post_create_organization_works(admin_request, sample_organization):
    organization = _get_organizations()
    assert len(organization) == 1

    data = {
        "name": "org 2",
        "active": True,
        "organization_type": OrganizationType.FEDERAL,
    }

    admin_request.post(
        "organization.create_organization", _data=data, _expected_status=201
    )

    organization = _get_organizations()

    assert len(organization) == 2


@pytest.mark.parametrize(
    "data, expected_error",
    (
        (
            {
                "active": False,
                "organization_type": OrganizationType.FEDERAL,
            },
            "name is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
            },
            "organization_type is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "organization_type": "foo",
            },
            ("organization_type foo is not one of " "[federal, state, other]"),
        ),
    ),
)
def test_post_create_organization_with_missing_data_gives_validation_error(
    admin_request,
    notify_db_session,
    data,
    expected_error,
):
    response = admin_request.post(
        "organization.create_organization", _data=data, _expected_status=400
    )

    assert len(response["errors"]) == 1
    assert response["errors"][0]["error"] == "ValidationError"
    assert response["errors"][0]["message"] == expected_error


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    fuzzed_name=st.one_of(st.none(), st.text(min_size=1, max_size=2000)),
    fuzzed_active=st.one_of(st.none(), st.booleans()),
    fuzzed_organization_type=st.one_of(st.none(), st.text(min_size=1, max_size=2000)),
)
def test_fuzz_post_create_organization_with_missing_data_gives_validation_error(
    admin_request, fuzzed_name, fuzzed_active, fuzzed_organization_type
):
    data = {
        "name": fuzzed_name,
        "active": fuzzed_active,
        "organization_type": fuzzed_organization_type,
    }
    response = admin_request.post(
        "organization.create_organization", _data=data, _expected_status=400
    )

    assert len(response["errors"]) > 0
    assert response["errors"][0]["error"] == "ValidationError"


def test_post_update_organization_updates_fields(
    admin_request,
    notify_db_session,
):
    org = create_organization()
    data = {
        "name": "new organization name",
        "active": False,
        "organization_type": OrganizationType.FEDERAL,
    }

    admin_request.post(
        "organization.update_organization",
        _data=data,
        organization_id=org.id,
        _expected_status=204,
    )

    organization = _get_organizations()

    assert len(organization) == 1
    assert organization[0].id == org.id
    assert organization[0].name == data["name"]
    assert organization[0].active == data["active"]
    assert organization[0].domains == []
    assert organization[0].organization_type == OrganizationType.FEDERAL


@pytest.mark.parametrize(
    "domain_list",
    (
        ["example.com"],
        ["example.com", "example.org", "example.net"],
        [],
    ),
)
def test_post_update_organization_updates_domains(
    admin_request,
    notify_db_session,
    domain_list,
):
    org = create_organization(name="test_org_2")
    data = {"domains": domain_list}

    admin_request.post(
        "organization.update_organization",
        _data=data,
        organization_id=org.id,
        _expected_status=204,
    )

    organization = _get_organizations()

    assert len(organization) == 1
    assert [domain.domain for domain in organization[0].domains] == domain_list


def test_update_other_organization_attributes_doesnt_clear_domains(
    admin_request,
    notify_db_session,
):
    org = create_organization(name="test_org_2")
    create_domain("example.gov.uk", org.id)

    admin_request.post(
        "organization.update_organization",
        _data={"domains": ["example.gov.uk"]},
        organization_id=org.id,
        _expected_status=204,
    )

    assert [domain.domain for domain in org.domains] == ["example.gov.uk"]


def test_update_organization_default_branding(
    admin_request,
    notify_db_session,
):
    org = create_organization(name="Test Organization")

    email_branding = create_email_branding()

    assert org.email_branding is None

    admin_request.post(
        "organization.update_organization",
        _data={
            "email_branding_id": str(email_branding.id),
        },
        organization_id=org.id,
        _expected_status=204,
    )

    assert org.email_branding == email_branding


def test_post_update_organization_raises_400_on_existing_org_name(
    admin_request, sample_organization
):
    org = create_organization()
    data = {"name": sample_organization.name, "active": False}

    response = admin_request.post(
        "organization.update_organization",
        _data=data,
        organization_id=org.id,
        _expected_status=400,
    )

    assert response["message"] == "Organization name already exists"


def test_post_update_organization_gives_404_status_if_org_does_not_exist(
    admin_request, notify_db_session
):
    data = {"name": "new organization name"}

    admin_request.post(
        "organization.update_organization",
        _data=data,
        organization_id="31d42ce6-3dac-45a7-95cb-94423d5ca03c",
        _expected_status=404,
    )

    organization = _get_organizations()

    assert not organization


def test_post_update_organization_returns_400_if_domain_is_duplicate(
    admin_request, notify_db_session
):
    org = create_organization()
    org2 = create_organization(name="Second org")
    create_domain("same.com", org.id)

    data = {"domains": ["new.com", "same.com"]}

    response = admin_request.post(
        "organization.update_organization",
        _data=data,
        organization_id=org2.id,
        _expected_status=400,
    )

    assert response["message"] == "Domain already exists"


def test_post_update_organization_set_mou_doesnt_email_if_no_signed_by(
    sample_organization, admin_request, mocker
):
    queue_mock = mocker.patch("app.organization.rest.send_notification_to_queue")

    data = {"agreement_signed": True}

    admin_request.post(
        "organization.update_organization",
        _data=data,
        organization_id=sample_organization.id,
        _expected_status=204,
    )

    assert queue_mock.called is False


@pytest.mark.parametrize(
    "on_behalf_of_name, on_behalf_of_email_address, templates_and_recipients",
    [
        (
            None,
            None,
            {
                "MOU_SIGNER_RECEIPT_TEMPLATE_ID": "notify@digital.fake.gov",
            },
        ),
        (
            "Important Person",
            "important@person.com",
            {
                "MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID": "important@person.com",
                "MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID": "notify@digital.fake.gov",
            },
        ),
    ],
)
def test_post_update_organization_set_mou_emails_signed_by(
    sample_organization,
    admin_request,
    mou_signed_templates,
    mocker,
    sample_user,
    on_behalf_of_name,
    on_behalf_of_email_address,
    templates_and_recipients,
):
    queue_mock = mocker.patch("app.organization.rest.send_notification_to_queue")
    sample_organization.agreement_signed_on_behalf_of_name = on_behalf_of_name
    sample_organization.agreement_signed_on_behalf_of_email_address = (
        on_behalf_of_email_address
    )

    admin_request.post(
        "organization.update_organization",
        _data={"agreement_signed": True, "agreement_signed_by_id": str(sample_user.id)},
        organization_id=sample_organization.id,
        _expected_status=204,
    )

    notifications = [x[0][0] for x in queue_mock.call_args_list]
    # assert {n.template.name: n.to for n in notifications} == templates_and_recipients

    for n in notifications:
        # we pass in the same personalisation for all templates (though some templates don't use all fields)
        assert n.personalisation == {
            "mou_link": "http://localhost:6012/agreement/agreement.pdf",
            "org_name": "sample organization",
            "org_dashboard_link": "http://localhost:6012/organizations/{}".format(
                sample_organization.id
            ),
            "signed_by_name": "Test User",
            "on_behalf_of_name": on_behalf_of_name,
        }


def test_post_link_service_to_organization(admin_request, sample_service):
    data = {"service_id": str(sample_service.id)}
    organization = create_organization(organization_type=OrganizationType.FEDERAL)

    admin_request.post(
        "organization.link_service_to_organization",
        _data=data,
        organization_id=organization.id,
        _expected_status=204,
    )
    assert len(organization.services) == 1
    assert sample_service.organization_type == OrganizationType.FEDERAL


@freeze_time("2021-09-24 13:30")
def test_post_link_service_to_organization_inserts_annual_billing(
    admin_request, sample_service
):
    data = {"service_id": str(sample_service.id)}
    organization = create_organization(organization_type=OrganizationType.FEDERAL)
    assert len(organization.services) == 0
    assert len(db.session.execute(select(AnnualBilling)).scalars().all()) == 0
    admin_request.post(
        "organization.link_service_to_organization",
        _data=data,
        organization_id=organization.id,
        _expected_status=204,
    )

    annual_billing = db.session.execute(select(AnnualBilling)).scalars().all()
    assert len(annual_billing) == 1
    assert annual_billing[0].free_sms_fragment_limit == 150000


def test_post_link_service_to_organization_rollback_service_if_annual_billing_update_fails(
    admin_request, sample_service, mocker
):
    mocker.patch(
        "app.dao.annual_billing_dao.dao_create_or_update_annual_billing_for_year",
        side_effect=SQLAlchemyError,
    )
    data = {"service_id": str(sample_service.id)}
    assert not sample_service.organization_type

    organization = create_organization(organization_type=OrganizationType.FEDERAL)
    assert len(organization.services) == 0
    assert len(db.session.execute(select(AnnualBilling)).scalars().all()) == 0
    with pytest.raises(expected_exception=SQLAlchemyError):
        admin_request.post(
            "organization.link_service_to_organization",
            _data=data,
            organization_id=organization.id,
        )
    assert not sample_service.organization_type
    assert len(organization.services) == 0
    assert len(db.session.execute(select(AnnualBilling)).scalars().all()) == 0


@freeze_time("2021-09-24 13:30")
def test_post_link_service_to_another_org(
    admin_request, sample_service, sample_organization
):
    data = {"service_id": str(sample_service.id)}
    assert len(sample_organization.services) == 0
    assert not sample_service.organization_type
    admin_request.post(
        "organization.link_service_to_organization",
        _data=data,
        organization_id=sample_organization.id,
        _expected_status=204,
    )

    assert len(sample_organization.services) == 1
    assert not sample_service.organization_type

    new_org = create_organization(organization_type=OrganizationType.FEDERAL)
    admin_request.post(
        "organization.link_service_to_organization",
        _data=data,
        organization_id=new_org.id,
        _expected_status=204,
    )
    assert not sample_organization.services
    assert len(new_org.services) == 1
    assert sample_service.organization_type == OrganizationType.FEDERAL
    annual_billing = db.session.execute(select(AnnualBilling)).scalars().all()
    assert len(annual_billing) == 1
    assert annual_billing[0].free_sms_fragment_limit == 150000


def test_post_link_service_to_organization_nonexistent_organization(
    admin_request, sample_service, fake_uuid
):
    data = {"service_id": str(sample_service.id)}

    admin_request.post(
        "organization.link_service_to_organization",
        _data=data,
        organization_id=fake_uuid,
        _expected_status=404,
    )


def test_post_link_service_to_organization_nonexistent_service(
    admin_request, sample_organization, fake_uuid
):
    data = {"service_id": fake_uuid}

    admin_request.post(
        "organization.link_service_to_organization",
        _data=data,
        organization_id=str(sample_organization.id),
        _expected_status=404,
    )


def test_post_link_service_to_organization_missing_payload(
    admin_request, sample_organization, fake_uuid
):
    admin_request.post(
        "organization.link_service_to_organization",
        organization_id=str(sample_organization.id),
        _expected_status=400,
    )


def test_rest_get_organization_services(
    admin_request, sample_organization, sample_service
):
    dao_add_service_to_organization(sample_service, sample_organization.id)
    response = admin_request.get(
        "organization.get_organization_services",
        organization_id=str(sample_organization.id),
        _expected_status=200,
    )

    assert response == [sample_service.serialize_for_org_dashboard()]


def test_rest_get_organization_services_is_ordered_by_name(
    admin_request, sample_organization, sample_service
):
    service_2 = create_service(service_name="service 2")
    service_1 = create_service(service_name="service 1")
    dao_add_service_to_organization(service_1, sample_organization.id)
    dao_add_service_to_organization(service_2, sample_organization.id)
    dao_add_service_to_organization(sample_service, sample_organization.id)

    response = admin_request.get(
        "organization.get_organization_services",
        organization_id=str(sample_organization.id),
        _expected_status=200,
    )

    assert response[0]["name"] == sample_service.name
    assert response[1]["name"] == service_1.name
    assert response[2]["name"] == service_2.name


def test_rest_get_organization_services_inactive_services_at_end(
    admin_request, sample_organization
):
    inactive_service = create_service(service_name="inactive service", active=False)
    service = create_service()
    inactive_service_1 = create_service(service_name="inactive service 1", active=False)

    dao_add_service_to_organization(inactive_service, sample_organization.id)
    dao_add_service_to_organization(service, sample_organization.id)
    dao_add_service_to_organization(inactive_service_1, sample_organization.id)

    response = admin_request.get(
        "organization.get_organization_services",
        organization_id=str(sample_organization.id),
        _expected_status=200,
    )

    assert response[0]["name"] == service.name
    assert response[1]["name"] == inactive_service.name
    assert response[2]["name"] == inactive_service_1.name


def test_add_user_to_organization_returns_added_user(
    admin_request, sample_organization, sample_user
):
    response = admin_request.post(
        "organization.add_user_to_organization",
        organization_id=str(sample_organization.id),
        user_id=str(sample_user.id),
        _expected_status=200,
    )

    assert response["data"]["id"] == str(sample_user.id)
    assert len(response["data"]["organizations"]) == 1
    assert response["data"]["organizations"][0] == str(sample_organization.id)


def test_add_user_to_organization_returns_404_if_user_does_not_exist(
    admin_request, sample_organization
):
    admin_request.post(
        "organization.add_user_to_organization",
        organization_id=str(sample_organization.id),
        user_id=str(uuid.uuid4()),
        _expected_status=404,
    )


def test_remove_user_from_organization(admin_request, sample_organization, sample_user):
    dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=sample_user.id
    )

    admin_request.delete(
        "organization.remove_user_from_organization",
        organization_id=sample_organization.id,
        user_id=sample_user.id,
    )

    assert sample_organization.users == []


def test_remove_user_from_organization_when_user_is_not_an_org_member(
    admin_request, sample_organization, sample_user
):
    resp = admin_request.delete(
        "organization.remove_user_from_organization",
        organization_id=sample_organization.id,
        user_id=sample_user.id,
        _expected_status=404,
    )

    assert resp == {"result": "error", "message": "User not found"}


def test_get_organization_users_returns_users_for_organization(
    admin_request, sample_organization
):
    first = create_user(email="first@invited.com")
    second = create_user(email="another@invited.com")
    dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=first.id
    )
    dao_add_user_to_organization(
        organization_id=sample_organization.id, user_id=second.id
    )

    response = admin_request.get(
        "organization.get_organization_users",
        organization_id=sample_organization.id,
        _expected_status=200,
    )

    assert len(response["data"]) == 2
    response_ids = [response["data"][0]["id"], response["data"][1]["id"]]
    assert str(first.id) in response_ids
    assert str(second.id) in response_ids


@freeze_time("2019-12-24 13:30")
def test_get_organization_services_usage(admin_request, notify_db_session):
    org = create_organization(name="Organization without live services")
    service = create_service()
    template = create_template(service=service)
    dao_add_service_to_organization(service=service, organization_id=org.id)
    create_annual_billing(
        service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2019
    )
    create_ft_billing(
        local_date=utc_now().date(),
        template=template,
        billable_unit=19,
        rate=0.060,
        notifications_sent=19,
    )
    response = admin_request.get(
        "organization.get_organization_services_usage",
        organization_id=org.id,
        **{"year": 2019},
    )
    assert len(response) == 1
    assert len(response["services"]) == 1
    service_usage = response["services"][0]
    assert service_usage["service_id"] == str(service.id)
    assert service_usage["service_name"] == service.name
    assert service_usage["chargeable_billable_sms"] == 9.0
    assert service_usage["emails_sent"] == 0
    assert service_usage["free_sms_limit"] == 10
    assert service_usage["sms_billable_units"] == 19
    assert service_usage["sms_remainder"] == 0
    assert service_usage["sms_cost"] == 0.54


@freeze_time("2020-02-24 13:30")
def test_get_organization_services_usage_sort_active_first(
    admin_request, notify_db_session
):
    org = create_organization(name="Organization without live services")
    service = create_service(service_name="live service")
    archived_service = create_service(service_name="archived_service")
    template = create_template(service=service)
    dao_add_service_to_organization(service=service, organization_id=org.id)
    dao_add_service_to_organization(service=archived_service, organization_id=org.id)
    create_annual_billing(
        service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2019
    )
    create_ft_billing(
        local_date=utc_now().date(),
        template=template,
        billable_unit=19,
        rate=0.060,
        notifications_sent=19,
    )
    response = admin_request.get(
        "organization.get_organization_services_usage",
        organization_id=org.id,
        **{"year": 2019},
    )
    assert len(response) == 1
    assert len(response["services"]) == 2
    first_service = response["services"][0]
    assert first_service["service_id"] == str(archived_service.id)
    assert first_service["service_name"] == archived_service.name
    assert first_service["active"] is True
    last_service = response["services"][1]
    assert last_service["service_id"] == str(service.id)
    assert last_service["service_name"] == service.name
    assert last_service["active"] is True

    dao_archive_service(service_id=archived_service.id)
    response_after_archive = admin_request.get(
        "organization.get_organization_services_usage",
        organization_id=org.id,
        **{"year": 2019},
    )
    first_service = response_after_archive["services"][0]
    assert first_service["service_id"] == str(service.id)
    assert first_service["service_name"] == service.name
    assert first_service["active"] is True
    last_service = response_after_archive["services"][1]
    assert last_service["service_id"] == str(archived_service.id)
    assert last_service["service_name"] == archived_service.name
    assert last_service["active"] is False


def test_get_organization_services_usage_returns_400_if_year_is_invalid(admin_request):
    response = admin_request.get(
        "organization.get_organization_services_usage",
        organization_id=uuid.uuid4(),
        **{"year": "not-a-valid-year"},
        _expected_status=400,
    )
    assert response["message"] == "No valid year provided"


def test_get_organization_services_usage_returns_400_if_year_is_empty(admin_request):
    response = admin_request.get(
        "organization.get_organization_services_usage",
        organization_id=uuid.uuid4(),
        _expected_status=400,
    )
    assert response["message"] == "No valid year provided"


def test_valid_request_args():
    request = Mock()
    request.args = {"org_id": "123", "name": "Test Org"}
    org_id, name = check_request_args(request)
    assert org_id == "123"
    assert name == "Test Org"


def test_missing_org_id():
    request = Mock()
    request.args = {"name": "Test Org"}
    try:
        check_request_args(request)
        assert 1 == 0
    except Exception as e:
        assert e.status_code == 400
        assert e.message == [{"org_id": ["Can't be empty"]}]


def test_missing_name():
    request = Mock()
    request.args = {"org_id": "123"}
    try:
        check_request_args(request)
        assert 1 == 0
    except Exception as e:
        assert e.status_code == 400
        assert e.message == [{"name": ["Can't be empty"]}]


def test_missing_both():
    request = Mock()
    request.args = {}
    try:
        check_request_args(request)
        assert 1 == 0
    except Exception as e:
        assert e.status_code == 400
        assert e.message == [
            {"org_id": ["Can't be empty"]},
            {"name": ["Can't be empty"]},
        ]


@freeze_time("2025-01-15 10:00:00")
def test_get_organization_message_allowance(admin_request, sample_organization, mocker):
    service_1 = create_service(service_name="Service 1")
    service_2 = create_service(service_name="Service 2")

    service_1.total_message_limit = 100000
    service_2.total_message_limit = 50000

    dao_add_service_to_organization(service_1, sample_organization.id)
    dao_add_service_to_organization(service_2, sample_organization.id)

    mock_get_counts = mocker.patch(
        "app.organization.rest.dao_get_notification_counts_per_service"
    )
    mock_get_counts.return_value = {
        service_1.id: 30000,
        service_2.id: 20000,
    }

    response = admin_request.get(
        "organization.get_organization_message_allowance",
        organization_id=sample_organization.id,
        _expected_status=200,
    )

    assert response["messages_sent"] == 50000
    assert response["messages_remaining"] == 100000
    assert response["total_message_limit"] == 150000

    assert mock_get_counts.call_count == 1
    mock_get_counts.assert_called_once()
    args, _ = mock_get_counts.call_args
    assert set(args[0]) == {service_1.id, service_2.id}
    assert args[1] == 2025


def test_get_organization_message_allowance_no_services(
    admin_request, sample_organization
):
    response = admin_request.get(
        "organization.get_organization_message_allowance",
        organization_id=sample_organization.id,
        _expected_status=200,
    )

    assert response["messages_sent"] == 0
    assert response["messages_remaining"] == 0
    assert response["total_message_limit"] == 0


def test_get_organization_message_allowance_invalid_org_id(admin_request):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    admin_request.get(
        "organization.get_organization_message_allowance",
        organization_id=fake_uuid,
        _expected_status=404,
    )


def test_get_organization_dashboard(admin_request, mocker):
    org_id = uuid.uuid4()
    service_id = uuid.uuid4()

    mock_usage = mocker.patch("app.organization.rest.fetch_usage_year_for_organization")
    mock_usage.return_value = {
        service_id: {
            "service_id": service_id,
            "service_name": "Test Service",
            "active": True,
            "restricted": False,
            "emails_sent": 100,
            "sms_billable_units": 5,
            "sms_remainder": 245,
            "sms_cost": 1.50,
            "free_sms_limit": 250,
            "chargeable_billable_sms": 0,
        }
    }

    mock_templates = mocker.patch("app.organization.rest.dao_get_recent_sms_template_per_service")
    mock_templates.return_value = {service_id: "Welcome SMS"}

    mock_contacts = mocker.patch("app.organization.rest.dao_get_service_primary_contacts")
    mock_contacts.return_value = {service_id: "billing@example.com"}

    response = admin_request.get(
        "organization.get_organization_dashboard",
        organization_id=org_id,
        **{"year": 2025},
    )

    assert len(response["services"]) == 1
    service_data = response["services"][0]

    assert service_data["service_id"] == str(service_id)
    assert service_data["service_name"] == "Test Service"
    assert service_data["active"] is True
    assert service_data["restricted"] is False
    assert service_data["sms_billable_units"] == 5
    assert service_data["free_sms_limit"] == 250
    assert service_data["sms_remainder"] == 245
    assert service_data["recent_sms_template_name"] == "Welcome SMS"
    assert service_data["primary_contact"] == "billing@example.com"

    mock_usage.assert_called_once_with(org_id, 2025, include_all_services=True)
    mock_templates.assert_called_once_with([service_id])
    mock_contacts.assert_called_once_with([service_id])
