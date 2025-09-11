import json
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import ANY, MagicMock, patch

import pytest
from flask import current_app, url_for
from freezegun import freeze_time
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.dao.organization_dao import dao_add_service_to_organization
from app.dao.service_sms_sender_dao import dao_get_sms_senders_by_service_id
from app.dao.service_user_dao import dao_get_service_user
from app.dao.services_dao import dao_add_user_to_service, dao_remove_user_from_service
from app.dao.templates_dao import dao_redact_template
from app.dao.users_dao import save_model_user
from app.enums import (
    KeyType,
    NotificationStatus,
    NotificationType,
    OrganizationType,
    PermissionType,
    ServicePermissionType,
    StatisticsType,
    TemplateType,
)
from app.errors import InvalidRequest
from app.models import (
    AnnualBilling,
    EmailBranding,
    InboundNumber,
    Notification,
    Permission,
    Service,
    ServiceEmailReplyTo,
    ServicePermission,
    ServiceSmsSender,
    User,
)
from app.service.rest import (
    check_request_args,
    get_service_statistics_for_specific_days,
    get_service_statistics_for_specific_days_by_user,
)
from app.utils import utc_now
from tests import create_admin_authorization_header
from tests.app.db import (
    create_annual_billing,
    create_domain,
    create_email_branding,
    create_ft_billing,
    create_ft_notification_status,
    create_inbound_number,
    create_notification,
    create_organization,
    create_reply_to_email,
    create_service,
    create_service_sms_sender,
    create_service_with_defined_sms_sender,
    create_service_with_inbound_number,
    create_template,
    create_template_folder,
    create_user,
)


def test_get_service_list(client, service_factory):
    service_factory.get("one")
    service_factory.get("two")
    service_factory.get("three")
    auth_header = create_admin_authorization_header()
    response = client.get("/service", headers=[auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))

    found_service_one = False
    found_service_two = False
    found_service_three = False
    for item in json_resp["data"]:
        if item["name"] == "one":
            found_service_one = True
        elif item["name"] == "two":
            found_service_two = True
        elif item["name"] == "three":
            found_service_three = True
    assert found_service_one is True
    assert found_service_two is True
    assert found_service_three is True


def test_get_service_list_with_only_active_flag(client, service_factory):
    inactive = service_factory.get("one")
    active = service_factory.get("two")

    inactive.active = False

    auth_header = create_admin_authorization_header()
    response = client.get("/service?only_active=True", headers=[auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp["data"]) == 1
    assert json_resp["data"][0]["id"] == str(active.id)


def test_get_service_list_with_user_id_and_only_active_flag(
    admin_request, sample_user, service_factory
):
    other_user = create_user(email="foo@bar.gov.uk")

    inactive = service_factory.get("one", user=sample_user)
    active = service_factory.get("two", user=sample_user)
    # from other user
    service_factory.get("three", user=other_user)

    inactive.active = False

    json_resp = admin_request.get(
        "service.get_services", user_id=sample_user.id, only_active=True
    )
    assert len(json_resp["data"]) == 1
    assert json_resp["data"][0]["id"] == str(active.id)


def test_get_service_list_by_user(admin_request, sample_user, service_factory):
    other_user = create_user(email="foo@bar.gov.uk")
    service_factory.get("one", sample_user)
    service_factory.get("two", sample_user)
    service_factory.get("three", other_user)

    json_resp = admin_request.get("service.get_services", user_id=sample_user.id)
    assert len(json_resp["data"]) == 2
    assert json_resp["data"][0]["name"] == "one"
    assert json_resp["data"][1]["name"] == "two"


def test_get_service_list_by_user_should_return_empty_list_if_no_services(
    admin_request, sample_service
):
    # service is already created by sample user
    new_user = create_user(email="foo@bar.gov.uk")

    json_resp = admin_request.get("service.get_services", user_id=new_user.id)
    assert json_resp["data"] == []


def test_get_service_list_should_return_empty_list_if_no_services(admin_request):
    json_resp = admin_request.get("service.get_services")
    assert len(json_resp["data"]) == 0


def test_find_services_by_name_finds_services(notify_db_session, admin_request, mocker):
    service_1 = create_service(service_name="ABCDEF")
    service_2 = create_service(service_name="ABCGHT")
    mock_get_services_by_partial_name = mocker.patch(
        "app.service.rest.get_services_by_partial_name",
        return_value=[service_1, service_2],
    )
    response = admin_request.get(
        "service.find_services_by_name",
        service_name="ABC",
    )["data"]
    mock_get_services_by_partial_name.assert_called_once_with("ABC")
    assert len(response) == 2


def test_find_services_by_name_handles_no_results(
    notify_db_session, admin_request, mocker
):
    mock_get_services_by_partial_name = mocker.patch(
        "app.service.rest.get_services_by_partial_name", return_value=[]
    )
    response = admin_request.get(
        "service.find_services_by_name",
        service_name="ABC",
    )["data"]
    mock_get_services_by_partial_name.assert_called_once_with("ABC")
    assert len(response) == 0


def test_find_services_by_name_handles_no_service_name(
    notify_db_session, admin_request, mocker
):
    mock_get_services_by_partial_name = mocker.patch(
        "app.service.rest.get_services_by_partial_name"
    )
    admin_request.get("service.find_services_by_name", _expected_status=400)
    mock_get_services_by_partial_name.assert_not_called()


@freeze_time("2019-05-02")
def test_get_live_services_data(sample_user, admin_request):
    org = create_organization()

    service = create_service(go_live_user=sample_user, go_live_at=datetime(2018, 1, 1))
    service_2 = create_service(
        service_name="second",
        go_live_at=datetime(2019, 1, 1),
        go_live_user=sample_user,
    )

    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type=TemplateType.EMAIL)
    dao_add_service_to_organization(service=service, organization_id=org.id)
    create_ft_billing(local_date="2019-04-20", template=sms_template)
    create_ft_billing(local_date="2019-04-20", template=email_template)

    create_annual_billing(service.id, 1, 2019)
    create_annual_billing(service_2.id, 2, 2018)

    response = admin_request.get("service.get_live_services_data")["data"]

    assert len(response) == 2
    assert response == [
        {
            "consent_to_research": None,
            "contact_email": "notify@digital.fake.gov",
            "contact_mobile": "+12028675309",
            "contact_name": "Test User",
            "email_totals": 1,
            "email_volume_intent": None,
            "live_date": "Mon, 01 Jan 2018 00:00:00 GMT",
            "organization_name": "test_org_1",
            "service_id": ANY,
            "service_name": "Sample service",
            "sms_totals": 1,
            "sms_volume_intent": None,
            "organization_type": None,
            "free_sms_fragment_limit": 1,
        },
        {
            "consent_to_research": None,
            "contact_email": "notify@digital.fake.gov",
            "contact_mobile": "+12028675309",
            "contact_name": "Test User",
            "email_totals": 0,
            "email_volume_intent": None,
            "live_date": "Tue, 01 Jan 2019 00:00:00 GMT",
            "organization_name": None,
            "service_id": ANY,
            "service_name": "second",
            "sms_totals": 0,
            "sms_volume_intent": None,
            "organization_type": None,
            "free_sms_fragment_limit": 2,
        },
    ]


def test_get_service_by_id(admin_request, sample_service):
    json_resp = admin_request.get(
        "service.get_service_by_id", service_id=sample_service.id
    )
    assert json_resp["data"]["name"] == sample_service.name
    assert json_resp["data"]["id"] == str(sample_service.id)
    assert json_resp["data"]["email_branding"] is None
    assert json_resp["data"]["prefix_sms"] is True

    assert set(json_resp["data"].keys()) == {
        "active",
        "billing_contact_email_addresses",
        "billing_contact_names",
        "billing_reference",
        "consent_to_research",
        "contact_link",
        "count_as_live",
        "created_by",
        "email_branding",
        "email_from",
        "go_live_at",
        "go_live_user",
        "id",
        "inbound_api",
        "message_limit",
        "total_message_limit",
        "name",
        "notes",
        "organization",
        "organization_type",
        "permissions",
        "prefix_sms",
        "purchase_order_number",
        "rate_limit",
        "restricted",
        "service_callback_api",
        "volume_email",
        "volume_sms",
    }


@pytest.mark.parametrize("detailed", [True, False])
def test_get_service_by_id_returns_organization_type(
    admin_request, sample_service, detailed
):
    json_resp = admin_request.get(
        "service.get_service_by_id",
        service_id=sample_service.id,
        detailed=detailed,
    )
    assert json_resp["data"]["organization_type"] is None


def test_get_service_list_has_default_permissions(admin_request, service_factory):
    service_factory.get("one")
    service_factory.get("one")
    service_factory.get("two")
    service_factory.get("three")

    json_resp = admin_request.get("service.get_services")
    assert len(json_resp["data"]) == 3
    assert all(
        set(json["permissions"])
        == {
            ServicePermissionType.EMAIL,
            ServicePermissionType.SMS,
            ServicePermissionType.INTERNATIONAL_SMS,
        }
        for json in json_resp["data"]
    )


def test_get_service_by_id_has_default_service_permissions(
    admin_request, sample_service
):
    json_resp = admin_request.get(
        "service.get_service_by_id",
        service_id=sample_service.id,
    )

    assert set(json_resp["data"]["permissions"]) == {
        ServicePermissionType.EMAIL,
        ServicePermissionType.SMS,
        ServicePermissionType.INTERNATIONAL_SMS,
    }


def test_get_service_by_id_should_404_if_no_service(admin_request, notify_db_session):
    json_resp = admin_request.get(
        "service.get_service_by_id",
        service_id=uuid.uuid4(),
        _expected_status=404,
    )

    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_get_service_by_id_and_user(client, sample_service, sample_user):
    sample_service.reply_to_email = "something@service.com"
    create_reply_to_email(service=sample_service, email_address="new@service.com")
    auth_header = create_admin_authorization_header()
    resp = client.get(
        f"/service/{sample_service.id}?user_id={sample_user.id}",
        headers=[auth_header],
    )
    assert resp.status_code == 200
    json_resp = resp.json
    assert json_resp["data"]["name"] == sample_service.name
    assert json_resp["data"]["id"] == str(sample_service.id)


def test_get_service_by_id_should_404_if_no_service_for_user(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_admin_authorization_header()
            resp = client.get(
                f"/service/{service_id}?user_id={sample_user.id}",
                headers=[auth_header],
            )
            assert resp.status_code == 404
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert json_resp["message"] == "No result found"


def test_get_service_by_id_returns_go_live_user_and_go_live_at(
    admin_request, sample_user
):
    now = utc_now()
    service = create_service(user=sample_user, go_live_user=sample_user, go_live_at=now)
    json_resp = admin_request.get("service.get_service_by_id", service_id=service.id)
    assert json_resp["data"]["go_live_user"] == str(sample_user.id)
    assert json_resp["data"]["go_live_at"] == str(now)


@pytest.mark.parametrize(
    "platform_admin, expected_count_as_live",
    (
        (True, False),
        (False, True),
    ),
)
def test_create_service(
    admin_request,
    sample_user,
    platform_admin,
    expected_count_as_live,
):
    sample_user.platform_admin = platform_admin
    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "total_message_limit": 100000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
    }

    json_resp = admin_request.post(
        "service.create_service",
        _data=data,
        _expected_status=201,
    )

    assert json_resp["data"]["id"]
    assert json_resp["data"]["name"] == "created service"
    assert json_resp["data"]["email_from"] == "created.service"
    assert json_resp["data"]["count_as_live"] is expected_count_as_live

    service_db = db.session.get(Service, json_resp["data"]["id"])
    assert service_db.name == "created service"

    json_resp = admin_request.get(
        "service.get_service_by_id",
        service_id=json_resp["data"]["id"],
        user_id=sample_user.id,
    )

    assert json_resp["data"]["name"] == "created service"

    stmt = select(ServiceSmsSender).where(ServiceSmsSender.service_id == service_db.id)
    service_sms_senders = db.session.execute(stmt).scalars().all()
    assert len(service_sms_senders) == 1
    assert service_sms_senders[0].sms_sender == current_app.config["FROM_NUMBER"]


@pytest.mark.parametrize(
    "domain, expected_org",
    (
        (None, False),
        ("", False),
        ("unknown.gov.uk", False),
        ("unknown-example.gov.uk", False),
        ("example.gov.uk", True),
        ("test.gov.uk", True),
        ("test.example.gov.uk", True),
    ),
)
def test_create_service_with_domain_sets_organization(
    admin_request,
    sample_user,
    domain,
    expected_org,
):
    red_herring_org = create_organization(name="Sub example")
    create_domain("specific.example.gov.uk", red_herring_org.id)
    create_domain("aaaaaaaa.example.gov.uk", red_herring_org.id)

    org = create_organization()
    create_domain("example.gov.uk", org.id)
    create_domain("test.gov.uk", org.id)

    another_org = create_organization(name="Another")
    create_domain("fake.gov", another_org.id)
    create_domain("cabinetoffice.gov.uk", another_org.id)

    sample_user.email_address = f"test@{domain}"

    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "total_message_limit": 100000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
        "service_domain": domain,
    }

    json_resp = admin_request.post(
        "service.create_service",
        _data=data,
        _expected_status=201,
    )

    if expected_org:
        assert json_resp["data"]["organization"] == str(org.id)
    else:
        assert json_resp["data"]["organization"] is None


def test_create_service_should_create_annual_billing_for_service(
    admin_request, sample_user
):
    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "total_message_limit": 100000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
    }

    assert len(db.session.execute(select(AnnualBilling)).scalars().all()) == 0
    admin_request.post("service.create_service", _data=data, _expected_status=201)

    annual_billing = db.session.execute(select(AnnualBilling)).scalars().all()
    assert len(annual_billing) == 1


def test_create_service_should_raise_exception_and_not_create_service_if_annual_billing_query_fails(
    admin_request, sample_user, mocker
):
    mocker.patch(
        "app.service.rest.set_default_free_allowance_for_service",
        side_effect=SQLAlchemyError,
    )
    data = {
        "name": "created service",
        "user_id": str(sample_user.id),
        "message_limit": 1000,
        "total_message_limit": 100000,
        "restricted": False,
        "active": False,
        "email_from": "created.service",
        "created_by": str(sample_user.id),
    }
    assert len(db.session.execute(select(AnnualBilling)).scalars().all()) == 0
    with pytest.raises(expected_exception=SQLAlchemyError):
        admin_request.post("service.create_service", _data=data)

    annual_billing = db.session.execute(select(AnnualBilling)).scalars().all()
    assert len(annual_billing) == 0
    stmt = (
        select(func.count())
        .select_from(Service)
        .where(Service.name == "created service")
    )
    count = db.session.execute(stmt).scalar() or 0
    assert count == 0


def test_create_service_inherits_branding_from_organization(
    admin_request,
    sample_user,
):
    org = create_organization()
    email_branding = create_email_branding()
    org.email_branding = email_branding
    create_domain("example.gov.uk", org.id)
    sample_user.email_address = "test@example.gov.uk"

    json_resp = admin_request.post(
        "service.create_service",
        _data={
            "name": "created service",
            "user_id": str(sample_user.id),
            "message_limit": 1000,
            "total_message_limit": 100000,
            "restricted": False,
            "active": False,
            "email_from": "created.service",
            "created_by": str(sample_user.id),
        },
        _expected_status=201,
    )

    assert json_resp["data"]["email_branding"] == str(email_branding.id)


def test_should_not_create_service_with_missing_user_id_field(notify_api, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "email_from": "service",
                "name": "created service",
                "message_limit": 1000,
                "total_message_limit": 100000,
                "restricted": False,
                "active": False,
                "created_by": str(fake_uuid),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 400
            assert json_resp["result"] == "error"
            assert "Missing data for required field." in json_resp["message"]["user_id"]


def test_should_error_if_created_by_missing(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "email_from": "service",
                "name": "created service",
                "message_limit": 1000,
                "total_message_limit": 100000,
                "restricted": False,
                "active": False,
                "user_id": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 400
            assert json_resp["result"] == "error"
            assert (
                "Missing data for required field." in json_resp["message"]["created_by"]
            )


def test_should_not_create_service_with_missing_if_user_id_is_not_in_database(
    notify_api, notify_db_session, fake_uuid
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "email_from": "service",
                "user_id": fake_uuid,
                "name": "created service",
                "message_limit": 1000,
                "total_message_limit": 100000,
                "restricted": False,
                "active": False,
                "created_by": str(fake_uuid),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 404
            assert json_resp["result"] == "error"
            assert json_resp["message"] == "No result found"


def test_should_not_create_service_if_missing_data(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {"user_id": str(sample_user.id)}
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 400
            assert json_resp["result"] == "error"
            assert "Missing data for required field." in json_resp["message"]["name"]
            assert (
                "Missing data for required field."
                in json_resp["message"]["message_limit"]
            )
            assert (
                "Missing data for required field." in json_resp["message"]["restricted"]
            )


def test_should_not_create_service_with_duplicate_name(
    notify_api, sample_user, sample_service
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "name": sample_service.name,
                "user_id": str(sample_service.users[0].id),
                "message_limit": 1000,
                "total_message_limit": 100000,
                "restricted": False,
                "active": False,
                "email_from": "sample.service2",
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert (
                f"Duplicate service name '{sample_service.name}'"
                in json_resp["message"]["name"]
            )


def test_create_service_should_throw_duplicate_key_constraint_for_existing_email_from(
    notify_api, service_factory, sample_user
):
    first_service = service_factory.get("First service", email_from="first.service")
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = "First SERVICE"
            data = {
                "name": service_name,
                "user_id": str(first_service.users[0].id),
                "message_limit": 1000,
                "total_message_limit": 100000,
                "restricted": False,
                "active": False,
                "email_from": "first.service",
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert (
                f"Duplicate service name '{service_name}'"
                in json_resp["message"]["name"]
            )


def test_update_service(client, notify_db_session, sample_service):
    brand = EmailBranding(
        colour="#000000",
        logo="justice-league.png",
        name="Justice League",
    )
    notify_db_session.add(brand)
    notify_db_session.commit()

    assert sample_service.email_branding is None

    data = {
        "name": "updated service name",
        "email_from": "updated.service.name",
        "created_by": str(sample_service.created_by.id),
        "email_branding": str(brand.id),
        "organization_type": OrganizationType.FEDERAL,
    }

    auth_header = create_admin_authorization_header()

    resp = client.post(
        f"/service/{sample_service.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert result["data"]["name"] == "updated service name"
    assert result["data"]["email_from"] == "updated.service.name"
    assert result["data"]["email_branding"] == str(brand.id)
    assert result["data"]["organization_type"] == OrganizationType.FEDERAL


def test_cant_update_service_org_type_to_random_value(client, sample_service):
    data = {
        "name": "updated service name",
        "email_from": "updated.service.name",
        "created_by": str(sample_service.created_by.id),
        "organization_type": "foo",
    }

    auth_header = create_admin_authorization_header()

    resp = client.post(
        f"/service/{sample_service.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert resp.status_code == 400


def test_update_service_remove_email_branding(
    admin_request, notify_db_session, sample_service
):
    brand = EmailBranding(
        colour="#000000",
        logo="justice-league.png",
        name="Justice League",
    )
    sample_service.email_branding = brand
    notify_db_session.commit()

    resp = admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={"email_branding": None},
    )
    assert resp["data"]["email_branding"] is None


def test_update_service_change_email_branding(
    admin_request, notify_db_session, sample_service
):
    brand1 = EmailBranding(
        colour="#000000",
        logo="justice-league.png",
        name="Justice League",
    )
    brand2 = EmailBranding(colour="#111111", logo="avengers.png", name="Avengers")
    notify_db_session.add_all([brand1, brand2])
    sample_service.email_branding = brand1
    notify_db_session.commit()

    resp = admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={"email_branding": str(brand2.id)},
    )
    assert resp["data"]["email_branding"] == str(brand2.id)


def test_update_service_flags(client, sample_service):
    auth_header = create_admin_authorization_header()
    resp = client.get(f"/service/{sample_service.id}", headers=[auth_header])
    json_resp = resp.json
    assert resp.status_code == 200
    assert json_resp["data"]["name"] == sample_service.name
    data = {"permissions": [ServicePermissionType.INTERNATIONAL_SMS]}

    auth_header = create_admin_authorization_header()

    resp = client.post(
        f"/service/{sample_service.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json
    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == {
        ServicePermissionType.INTERNATIONAL_SMS
    }


@pytest.mark.parametrize(
    "field",
    (
        "volume_email",
        "volume_sms",
    ),
)
@pytest.mark.parametrize(
    "value, expected_status, expected_persisted",
    (
        (1234, 200, 1234),
        (None, 200, None),
        ("Aa", 400, None),
    ),
)
def test_update_service_sets_volumes(
    admin_request,
    sample_service,
    field,
    value,
    expected_status,
    expected_persisted,
):
    admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={
            field: value,
        },
        _expected_status=expected_status,
    )
    assert getattr(sample_service, field) == expected_persisted


@pytest.mark.parametrize(
    "value, expected_status, expected_persisted",
    (
        (True, 200, True),
        (False, 200, False),
        ("unknown", 400, None),
    ),
)
def test_update_service_sets_research_consent(
    admin_request,
    sample_service,
    value,
    expected_status,
    expected_persisted,
):
    assert sample_service.consent_to_research is None
    admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={
            "consent_to_research": value,
        },
        _expected_status=expected_status,
    )
    assert sample_service.consent_to_research is expected_persisted


@pytest.fixture(scope="function")
def service_with_no_permissions(notify_db_session):
    return create_service(service_permissions=[])


def test_update_service_flags_with_service_without_default_service_permissions(
    client, service_with_no_permissions
):
    auth_header = create_admin_authorization_header()
    data = {
        "permissions": [ServicePermissionType.INTERNATIONAL_SMS],
    }

    resp = client.post(
        f"/service/{service_with_no_permissions.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == {
        ServicePermissionType.INTERNATIONAL_SMS,
    }


def test_update_service_flags_will_remove_service_permissions(
    client, notify_db_session
):
    auth_header = create_admin_authorization_header()

    service = create_service(
        service_permissions={
            ServicePermissionType.SMS,
            ServicePermissionType.EMAIL,
            ServicePermissionType.INTERNATIONAL_SMS,
        }
    )

    assert ServicePermissionType.INTERNATIONAL_SMS in {
        p.permission for p in service.permissions
    }

    data = {"permissions": [ServicePermissionType.SMS, ServicePermissionType.EMAIL]}

    resp = client.post(
        f"/service/{service.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert ServicePermissionType.INTERNATIONAL_SMS not in result["data"]["permissions"]

    stmt = select(ServicePermission).where(ServicePermission.service_id == service.id)
    permissions = db.session.execute(stmt).scalars().all()
    assert {p.permission for p in permissions} == {
        ServicePermissionType.SMS,
        ServicePermissionType.EMAIL,
    }


def test_update_permissions_will_override_permission_flags(
    client, service_with_no_permissions
):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [ServicePermissionType.INTERNATIONAL_SMS]}

    resp = client.post(
        f"/service/{service_with_no_permissions.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == {
        ServicePermissionType.INTERNATIONAL_SMS
    }


def test_update_service_permissions_will_add_service_permissions(
    client, sample_service
):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [ServicePermissionType.EMAIL, ServicePermissionType.SMS]}

    resp = client.post(
        f"/service/{sample_service.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 200
    assert set(result["data"]["permissions"]) == {
        ServicePermissionType.SMS,
        ServicePermissionType.EMAIL,
    }


@pytest.mark.parametrize(
    "permission_to_add",
    [
        ServicePermissionType.EMAIL,
        ServicePermissionType.SMS,
        ServicePermissionType.INTERNATIONAL_SMS,
        ServicePermissionType.INBOUND_SMS,
        ServicePermissionType.EMAIL_AUTH,
    ],
)
def test_add_service_permission_will_add_permission(
    client, service_with_no_permissions, permission_to_add
):
    auth_header = create_admin_authorization_header()

    data = {"permissions": [permission_to_add]}

    resp = client.post(
        f"/service/{service_with_no_permissions.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    stmt = select(ServicePermission).where(
        ServicePermission.service_id == service_with_no_permissions.id
    )
    permissions = db.session.execute(stmt).scalars().all()

    assert resp.status_code == 200
    assert [p.permission for p in permissions] == [permission_to_add]


def test_update_permissions_with_an_invalid_permission_will_raise_error(
    client, sample_service
):
    auth_header = create_admin_authorization_header()
    invalid_permission = "invalid_permission"

    data = {
        "permissions": [
            ServicePermissionType.EMAIL,
            ServicePermissionType.SMS,
            invalid_permission,
        ]
    }

    resp = client.post(
        f"/service/{sample_service.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 400
    assert result["result"] == "error"
    assert (
        f"Invalid Service Permission: '{invalid_permission}'"
        in result["message"]["permissions"]
    )


def test_update_permissions_with_duplicate_permissions_will_raise_error(
    client, sample_service
):
    auth_header = create_admin_authorization_header()

    data = {
        "permissions": [
            ServicePermissionType.EMAIL,
            ServicePermissionType.SMS,
            ServicePermissionType.SMS,
        ]
    }

    resp = client.post(
        f"/service/{sample_service.id}",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    result = resp.json

    assert resp.status_code == 400
    assert result["result"] == "error"
    assert (
        f"Duplicate Service Permission: ['{ServicePermissionType.SMS}']"
        in result["message"]["permissions"]
    )


def test_should_not_update_service_with_duplicate_name(
    notify_api, notify_db_session, sample_user, sample_service
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = "another name"
            service = create_service(
                service_name=service_name, user=sample_user, email_from="another.name"
            )
            data = {"name": service_name, "created_by": str(service.created_by.id)}

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 400
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert (
                f"Duplicate service name '{service_name}'"
                in json_resp["message"]["name"]
            )


def test_should_not_update_service_with_duplicate_email_from(
    notify_api, notify_db_session, sample_user, sample_service
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            email_from = "duplicate.name"
            service_name = "duplicate name"
            service = create_service(
                service_name=service_name, user=sample_user, email_from=email_from
            )
            data = {
                "name": service_name,
                "email_from": email_from,
                "created_by": str(service.created_by.id),
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 400
            json_resp = resp.json
            assert json_resp["result"] == "error"
            assert (
                f"Duplicate service name '{service_name}'"
                in json_resp["message"]["name"]
                or f"Duplicate service name '{email_from}'"
                in json_resp["message"]["name"]
            )


def test_update_service_should_404_if_id_is_invalid(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {"name": "updated service name"}

            missing_service_id = uuid.uuid4()

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{missing_service_id}",
                data=json.dumps(data),
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 404


def test_get_users_by_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_on_service = sample_service.users[0]
            auth_header = create_admin_authorization_header()

            resp = client.get(
                f"/service/{sample_service.id}/users",
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            result = resp.json
            assert len(result["data"]) == 1
            assert result["data"][0]["name"] == user_on_service.name
            assert result["data"][0]["email_address"] == user_on_service.email_address
            assert result["data"][0]["mobile_number"] == user_on_service.mobile_number


def test_get_users_for_service_returns_empty_list_if_no_users_associated_with_service(
    notify_api, sample_service
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            dao_remove_user_from_service(sample_service, sample_service.users[0])
            auth_header = create_admin_authorization_header()

            response = client.get(
                f"/service/{sample_service.id}/users",
                headers=[("Content-Type", "application/json"), auth_header],
            )
            result = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert result["data"] == []


def test_get_users_for_service_returns_404_when_service_does_not_exist(
    notify_api, notify_db_session
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = uuid.uuid4()
            auth_header = create_admin_authorization_header()

            response = client.get(
                f"/service/{service_id}/users",
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert response.status_code == 404
            result = json.loads(response.get_data(as_text=True))
            assert result["result"] == "error"
            assert result["message"] == "No result found"


def test_default_permissions_are_added_for_user_service(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "name": "created service",
                "user_id": str(sample_user.id),
                "message_limit": 1000,
                "total_message_limit": 100000,
                "restricted": False,
                "active": False,
                "email_from": "created.service",
                "created_by": str(sample_user.id),
            }
            auth_header = create_admin_authorization_header()
            headers = [("Content-Type", "application/json"), auth_header]
            resp = client.post("/service", data=json.dumps(data), headers=headers)
            json_resp = resp.json
            assert resp.status_code == 201
            assert json_resp["data"]["id"]
            assert json_resp["data"]["name"] == "created service"
            assert json_resp["data"]["email_from"] == "created.service"

            auth_header_fetch = create_admin_authorization_header()

            resp = client.get(
                f"/service/{json_resp['data']['id']}?user_id={sample_user.id}",
                headers=[auth_header_fetch],
            )
            assert resp.status_code == 200
            header = create_admin_authorization_header()
            response = client.get(
                url_for("user.get_user", user_id=sample_user.id),
                headers=[header],
            )
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            service_permissions = json_resp["data"]["permissions"][
                str(sample_service.id)
            ]

            assert sorted(PermissionType.defaults()) == sorted(service_permissions)


def test_add_existing_user_to_another_service_with_all_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # check which users part of service
            user_already_in_service = sample_service.users[0]
            auth_header = create_admin_authorization_header()

            resp = client.get(
                f"/service/{sample_service.id}/users",
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            result = resp.json
            assert len(result["data"]) == 1
            assert (
                result["data"][0]["email_address"]
                == user_already_in_service.email_address
            )

            fake_password = "password"
            # add new user to service
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.fake.gov",
                password=fake_password,
                mobile_number="+14254147755",
            )
            # they must exist in db first
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
                    {"permission": PermissionType.SEND_EMAILS},
                    {"permission": PermissionType.SEND_TEXTS},
                    {"permission": PermissionType.MANAGE_USERS},
                    {"permission": PermissionType.MANAGE_SETTINGS},
                    {"permission": PermissionType.MANAGE_API_KEYS},
                    {"permission": PermissionType.MANAGE_TEMPLATES},
                    {"permission": PermissionType.VIEW_ACTIVITY},
                ],
                "folder_permissions": [],
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}/users/{user_to_add.id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check new user added to service
            auth_header = create_admin_authorization_header()

            resp = client.get(
                f"/service/{sample_service.id}",
                headers=[("Content-Type", "application/json"), auth_header],
            )
            assert resp.status_code == 200
            json_resp = resp.json

            # check user has all permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json
            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = [
                PermissionType.SEND_TEXTS,
                PermissionType.SEND_EMAILS,
                PermissionType.MANAGE_USERS,
                PermissionType.MANAGE_SETTINGS,
                PermissionType.MANAGE_TEMPLATES,
                PermissionType.MANAGE_API_KEYS,
                PermissionType.VIEW_ACTIVITY,
            ]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_send_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.fake.gov",
                password="password",
                mobile_number="+14254147755",
            )
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
                    {"permission": PermissionType.SEND_EMAILS},
                    {"permission": PermissionType.SEND_TEXTS},
                ],
                "folder_permissions": [],
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}/users/{user_to_add.id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json

            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = [
                PermissionType.SEND_TEXTS,
                PermissionType.SEND_EMAILS,
            ]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_manage_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.fake.gov",
                password="password",
                mobile_number="+14254147755",
            )
            save_model_user(user_to_add, validated_email_access=True)

            data = {
                "permissions": [
                    {"permission": PermissionType.MANAGE_USERS},
                    {"permission": PermissionType.MANAGE_SETTINGS},
                    {"permission": PermissionType.MANAGE_TEMPLATES},
                ]
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}/users/{user_to_add.id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json

            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = [
                PermissionType.MANAGE_USERS,
                PermissionType.MANAGE_SETTINGS,
                PermissionType.MANAGE_TEMPLATES,
            ]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_folder_permissions(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.fake.gov",
                password="password",
                mobile_number="+14254147755",
            )
            save_model_user(user_to_add, validated_email_access=True)

            folder_1 = create_template_folder(sample_service)
            folder_2 = create_template_folder(sample_service)

            data = {
                "permissions": [{"permission": PermissionType.MANAGE_API_KEYS}],
                "folder_permissions": [str(folder_1.id), str(folder_2.id)],
            }

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}/users/{user_to_add.id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            new_user = dao_get_service_user(
                user_id=user_to_add.id, service_id=sample_service.id
            )

            assert len(new_user.folders) == 2
            assert folder_1 in new_user.folders
            assert folder_2 in new_user.folders


def test_add_existing_user_to_another_service_with_manage_api_keys(
    notify_api, notify_db_session, sample_service, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.fake.gov",
                password="password",
                mobile_number="+14254147755",
            )
            save_model_user(user_to_add, validated_email_access=True)

            data = {"permissions": [{"permission": PermissionType.MANAGE_API_KEYS}]}

            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}/users/{user_to_add.id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_admin_authorization_header()
            resp = client.get(
                url_for("user.get_user", user_id=user_to_add.id),
                headers=[("Content-Type", "application/json"), auth_header],
            )

            assert resp.status_code == 200
            json_resp = resp.json

            permissions = json_resp["data"]["permissions"][str(sample_service.id)]
            expected_permissions = [PermissionType.MANAGE_API_KEYS]
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_non_existing_service_returns404(
    notify_api, notify_db_session, sample_user
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_to_add = User(
                name="Invited User",
                email_address="invited@digital.fake.gov",
                password="password",
                mobile_number="+14254147755",
            )
            save_model_user(user_to_add, validated_email_access=True)

            incorrect_id = uuid.uuid4()

            data = {
                "permissions": [
                    PermissionType.SEND_EMAILS,
                    PermissionType.SEND_TEXTS,
                    PermissionType.MANAGE_USERS,
                    PermissionType.MANAGE_SETTINGS,
                    PermissionType.MANAGE_TEMPLATES,
                    PermissionType.MANAGE_API_KEYS,
                ]
            }
            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{incorrect_id}/users/{user_to_add.id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            result = resp.json
            expected_message = "No result found"

            assert resp.status_code == 404
            assert result["result"] == "error"
            assert result["message"] == expected_message


def test_add_existing_user_of_service_to_service_returns400(
    notify_api, notify_db_session, sample_service
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            existing_user_id = sample_service.users[0].id

            data = {
                "permissions": [
                    PermissionType.SEND_EMAILS,
                    PermissionType.SEND_TEXTS,
                    PermissionType.MANAGE_USERS,
                    PermissionType.MANAGE_SETTINGS,
                    PermissionType.MANAGE_TEMPLATES,
                    PermissionType.MANAGE_API_KEYS,
                ]
            }
            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}/users/{existing_user_id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            result = resp.json
            expected_message = (
                f"User id: {existing_user_id} already part of service "
                f"id: {sample_service.id}"
            )

            assert resp.status_code == 400
            assert result["result"] == "error"
            assert result["message"] == expected_message


def test_add_unknown_user_to_service_returns404(
    notify_api, notify_db_session, sample_service
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            incorrect_id = 9876

            data = {
                "permissions": [
                    PermissionType.SEND_EMAILS,
                    PermissionType.SEND_TEXTS,
                    PermissionType.MANAGE_USERS,
                    PermissionType.MANAGE_SETTINGS,
                    PermissionType.MANAGE_TEMPLATES,
                    PermissionType.MANAGE_API_KEYS,
                ]
            }
            auth_header = create_admin_authorization_header()

            resp = client.post(
                f"/service/{sample_service.id}/users/{incorrect_id}",
                headers=[("Content-Type", "application/json"), auth_header],
                data=json.dumps(data),
            )

            result = resp.json
            expected_message = "No result found"

            assert resp.status_code == 404
            assert result["result"] == "error"
            assert result["message"] == expected_message


def test_remove_user_from_service(client, sample_user_service_permission):
    second_user = create_user(email="new@digital.fake.gov")
    service = sample_user_service_permission.service

    # Simulates successfully adding a user to the service
    dao_add_user_to_service(
        service,
        second_user,
        permissions=[
            Permission(
                service_id=service.id,
                user_id=second_user.id,
                permission=PermissionType.MANAGE_SETTINGS,
            )
        ],
    )

    endpoint = url_for(
        "service.remove_user_from_service",
        service_id=str(service.id),
        user_id=str(second_user.id),
    )
    auth_header = create_admin_authorization_header()
    resp = client.delete(
        endpoint, headers=[("Content-Type", "application/json"), auth_header]
    )
    assert resp.status_code == 204


def test_get_service_message_ratio(mocker, client, sample_user_service_permission):
    service = sample_user_service_permission.service

    mock_redis = mocker.patch(
        "app.service.rest.dao_get_notification_count_for_service_message_ratio"
    )
    mock_redis.return_value = 1

    endpoint = url_for(
        "service.get_service_message_ratio",
        service_id=str(service.id),
    )
    auth_header = create_admin_authorization_header()

    resp = client.get(
        endpoint, headers=[("Content-Type", "application/json"), auth_header]
    )
    assert resp.status_code == 200
    result = resp.json
    assert result["total_message_limit"] == 100000
    assert result["messages_sent"] == 1


def test_remove_non_existant_user_from_service(client, sample_user_service_permission):
    second_user = create_user(email="new@digital.fake.gov")
    endpoint = url_for(
        "service.remove_user_from_service",
        service_id=str(sample_user_service_permission.service.id),
        user_id=str(second_user.id),
    )
    auth_header = create_admin_authorization_header()
    resp = client.delete(
        endpoint, headers=[("Content-Type", "application/json"), auth_header]
    )
    assert resp.status_code == 404


def test_cannot_remove_only_user_from_service(
    notify_api, notify_db_session, sample_user_service_permission
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            endpoint = url_for(
                "service.remove_user_from_service",
                service_id=str(sample_user_service_permission.service.id),
                user_id=str(sample_user_service_permission.user.id),
            )
            auth_header = create_admin_authorization_header()
            resp = client.delete(
                endpoint, headers=[("Content-Type", "application/json"), auth_header]
            )
            assert resp.status_code == 400
            result = resp.json
            assert result["message"] == "You cannot remove the only user for a service"


# This test is just here verify get_service_and_api_key_history that is a temp solution
# until proper ui is sorted out on admin app
def test_get_service_and_api_key_history(notify_api, sample_service, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_admin_authorization_header()
            response = client.get(
                path=f"/service/{sample_service.id}/history",
                headers=[auth_header],
            )
            assert response.status_code == 200

            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp["data"]["service_history"][0]["id"] == str(
                sample_service.id
            )
            assert json_resp["data"]["api_key_history"][0]["id"] == str(
                sample_api_key.id
            )


def test_get_all_notifications_for_service_in_order(client, notify_db_session):
    service_1 = create_service(service_name="1", email_from="1")
    service_2 = create_service(service_name="2", email_from="2")

    service_1_template = create_template(service_1)
    service_2_template = create_template(service_2)

    # create notification for service_2
    create_notification(service_2_template)

    notification_1 = create_notification(service_1_template)
    notification_2 = create_notification(service_1_template)
    notification_3 = create_notification(service_1_template)

    auth_header = create_admin_authorization_header()

    response = client.get(
        path=f"/service/{service_1.id}/notifications", headers=[auth_header]
    )

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp["notifications"]) == 3
    assert resp["notifications"][0]["to"] == notification_3.to
    assert resp["notifications"][1]["to"] == notification_2.to
    assert resp["notifications"][2]["to"] == notification_1.to
    assert response.status_code == 200


def test_get_all_notifications_for_service_in_order_with_post_request(
    client, notify_db_session
):
    service_1 = create_service(service_name="1")
    service_2 = create_service(service_name="2")

    service_1_template = create_template(service_1)
    service_2_template = create_template(service_2)

    # create notification for service_2
    create_notification(service_2_template)

    notification_1 = create_notification(service_1_template)
    notification_2 = create_notification(service_1_template)
    notification_3 = create_notification(service_1_template)

    response = client.post(
        path=f"/service/{service_1.id}/notifications",
        data=json.dumps({}),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp["notifications"]) == 3
    assert resp["notifications"][0]["to"] == notification_3.to
    assert resp["notifications"][1]["to"] == notification_2.to
    assert resp["notifications"][2]["to"] == notification_1.to
    assert response.status_code == 200


def test_get_all_notifications_for_service_filters_notifications_when_using_post_request(
    client, notify_db_session
):
    service_1 = create_service(service_name="1")
    service_2 = create_service(service_name="2")

    service_1_sms_template = create_template(service_1)
    service_1_email_template = create_template(
        service_1, template_type=TemplateType.EMAIL
    )
    service_2_sms_template = create_template(service_2)

    returned_notification = create_notification(
        service_1_sms_template, normalised_to="447700900855"
    )

    create_notification(
        service_1_sms_template,
        to_field="+447700900000",
        normalised_to="447700900000",
    )
    create_notification(
        service_1_sms_template,
        status=NotificationStatus.DELIVERED,
        normalised_to="447700900855",
    )
    create_notification(service_1_email_template, normalised_to="447700900855")
    # create notification for service_2
    create_notification(service_2_sms_template)

    auth_header = create_admin_authorization_header()
    data = {
        "page": 1,
        "template_type": [TemplateType.SMS],
        "status": [NotificationStatus.CREATED, NotificationStatus.SENDING],
    }

    response = client.post(
        path=f"/service/{service_1.id}/notifications",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp["notifications"]) == 2
    assert resp["notifications"][0]["to"] == ""
    assert resp["notifications"][0]["status"] == returned_notification.status
    assert response.status_code == 200


def test_get_all_notifications_for_service_formatted_for_csv(client, sample_template):
    notification = create_notification(template=sample_template)
    auth_header = create_admin_authorization_header()

    response = client.get(
        path=f"/service/{sample_template.service_id}/notifications?format_for_csv=True",
        headers=[auth_header],
    )

    resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert len(resp["notifications"]) == 1
    assert resp["notifications"][0]["recipient"] == notification.to
    assert not resp["notifications"][0]["row_number"]
    assert resp["notifications"][0]["template_name"] == sample_template.name
    assert resp["notifications"][0]["template_type"] == notification.notification_type
    assert resp["notifications"][0]["status"] == "Sending"


def test_get_notification_for_service_without_uuid(client, notify_db_session):
    service_1 = create_service(service_name="1", email_from="1")
    response = client.get(
        path=f"/service/{service_1.id}/notifications/{'foo'}",
        headers=[create_admin_authorization_header()],
    )
    assert response.status_code == 404


def test_get_notification_for_service(client, notify_db_session):
    service_1 = create_service(service_name="1", email_from="1")
    service_2 = create_service(service_name="2", email_from="2")

    service_1_template = create_template(service_1)
    service_2_template = create_template(service_2)

    service_1_notifications = [
        create_notification(service_1_template),
        create_notification(service_1_template),
        create_notification(service_1_template),
    ]

    create_notification(service_2_template)

    for notification in service_1_notifications:
        response = client.get(
            path=f"/service/{service_1.id}/notifications/{notification.id}",
            headers=[create_admin_authorization_header()],
        )
        resp = json.loads(response.get_data(as_text=True))
        assert str(resp["id"]) == str(notification.id)
        assert response.status_code == 200

        service_2_response = client.get(
            path=f"/service/{service_2.id}/notifications/{notification.id}",
            headers=[create_admin_authorization_header()],
        )
        assert service_2_response.status_code == 404
        service_2_response = json.loads(service_2_response.get_data(as_text=True))
        assert service_2_response == {"message": "No result found", "result": "error"}


def test_get_notification_for_service_includes_created_by(
    admin_request, sample_notification
):
    user = sample_notification.created_by = sample_notification.service.created_by

    resp = admin_request.get(
        "service.get_notification_for_service",
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id,
    )

    assert resp["id"] == str(sample_notification.id)
    assert resp["created_by"] == {
        "id": str(user.id),
        "name": user.name,
        "email_address": user.email_address,
    }


def test_get_notification_for_service_returns_old_template_version(
    admin_request, sample_template
):
    sample_notification = create_notification(sample_template)
    sample_notification.reference = "modified-inplace"
    sample_template.version = 2
    sample_template.content = "New template content"

    resp = admin_request.get(
        "service.get_notification_for_service",
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id,
    )

    assert resp["reference"] == "modified-inplace"
    assert resp["template"]["version"] == 1
    assert resp["template"]["content"] == sample_notification.template.content
    assert resp["template"]["content"] != sample_template.content


@pytest.mark.parametrize(
    "include_from_test_key, expected_count_of_notifications", [(False, 2), (True, 3)]
)
def test_get_all_notifications_for_service_including_ones_made_by_jobs(
    client,
    sample_service,
    include_from_test_key,
    expected_count_of_notifications,
    sample_notification,
    sample_notification_with_job,
    sample_template,
    mocker,
):
    mock_s3 = mocker.patch("app.service.rest.get_phone_number_from_s3")
    mock_s3.return_value = ""

    mock_s3 = mocker.patch("app.service.rest.get_personalisation_from_s3")
    mock_s3.return_value = {}

    # notification from_test_api_key
    create_notification(sample_template, key_type=KeyType.TEST)

    auth_header = create_admin_authorization_header()

    response = client.get(
        path=(
            f"/service/{sample_service.id}/notifications?include_from_test_key="
            f"{include_from_test_key}"
        ),
        headers=[auth_header],
    )

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp["notifications"]) == expected_count_of_notifications
    assert resp["notifications"][0]["to"] == sample_notification_with_job.to
    assert resp["notifications"][1]["to"] == sample_notification.to
    assert response.status_code == 200


def test_get_monthly_notification_stats_by_user(
    client,
    sample_service,
    sample_user,
    mocker,
):
    mock_s3 = mocker.patch("app.service.rest.get_phone_number_from_s3")
    mock_s3.return_value = ""

    mock_s3 = mocker.patch("app.service.rest.get_personalisation_from_s3")
    mock_s3.return_value = {}

    auth_header = create_admin_authorization_header()

    response = client.get(
        path=(
            f"/service/{sample_service.id}/notifications/{sample_user.id}/monthly?year=2024"
        ),
        headers=[auth_header],
    )

    assert response.status_code == 200


def test_get_single_month_notification_stats_by_user(
    client,
    sample_service,
    sample_user,
    mocker,
):
    mock_s3 = mocker.patch("app.service.rest.get_phone_number_from_s3")
    mock_s3.return_value = ""

    mock_s3 = mocker.patch("app.service.rest.get_personalisation_from_s3")
    mock_s3.return_value = {}

    auth_header = create_admin_authorization_header()

    response = client.get(
        path=(
            f"/service/{sample_service.id}/notifications/{sample_user.id}/month?year=2024&month=07"
        ),
        headers=[auth_header],
    )

    # TODO This test could be a little more complete
    assert response.status_code == 200


def test_get_single_month_notification_stats_for_service(
    client,
    sample_service,
    mocker,
):
    mock_s3 = mocker.patch("app.service.rest.get_phone_number_from_s3")
    mock_s3.return_value = ""

    mock_s3 = mocker.patch("app.service.rest.get_personalisation_from_s3")
    mock_s3.return_value = {}

    auth_header = create_admin_authorization_header()

    response = client.get(
        path=(f"/service/{sample_service.id}/notifications/month?year=2024&month=07"),
        headers=[auth_header],
    )

    assert response.status_code == 200


def test_get_only_api_created_notifications_for_service(
    admin_request,
    sample_job,
    sample_template,
    sample_user,
):
    # notification sent as a job
    create_notification(sample_template, job=sample_job)
    # notification sent as a one-off
    create_notification(sample_template, one_off=True, created_by_id=sample_user.id)
    # notification sent via API
    without_job = create_notification(sample_template)

    resp = admin_request.get(
        "service.get_all_notifications_for_service",
        service_id=sample_template.service_id,
        include_jobs=False,
        include_one_off=False,
    )
    assert len(resp["notifications"]) == 1
    assert resp["notifications"][0]["id"] == str(without_job.id)


def test_get_notifications_for_service_without_page_count(
    admin_request,
    sample_job,
    sample_template,
    sample_user,
):
    create_notification(sample_template)
    without_job = create_notification(sample_template)

    resp = admin_request.get(
        "service.get_all_notifications_for_service",
        service_id=sample_template.service_id,
        page_size=1,
        include_jobs=False,
        include_one_off=False,
        count_pages=False,
    )
    assert len(resp["notifications"]) == 1
    assert resp["notifications"][0]["id"] == str(without_job.id)
    assert "prev" not in resp["links"]
    assert "next" not in resp["links"]


def test_get_notifications_for_service_pagination_links(
    admin_request,
    sample_job,
    sample_template,
    sample_user,
):
    for _ in range(101):
        create_notification(
            sample_template, to_field="+447700900855", normalised_to="447700900855"
        )

    resp = admin_request.get(
        "service.get_all_notifications_for_service",
        service_id=sample_template.service_id,
    )

    assert "prev" not in resp["links"]
    assert "?page=2" in resp["links"]["next"]

    resp = admin_request.get(
        "service.get_all_notifications_for_service",
        service_id=sample_template.service_id,
        page=2,
    )

    assert "?page=1" in resp["links"]["prev"]
    assert "?page=3" in resp["links"]["next"]

    resp = admin_request.get(
        "service.get_all_notifications_for_service",
        service_id=sample_template.service_id,
        page=6,
    )

    assert "?page=5" in resp["links"]["prev"]
    assert "next" not in resp["links"]


@pytest.mark.parametrize(
    "should_prefix",
    [
        True,
        False,
    ],
)
def test_prefixing_messages_based_on_prefix_sms(
    client,
    notify_db_session,
    should_prefix,
):
    service = create_service(prefix_sms=should_prefix)

    result = client.get(
        url_for("service.get_service_by_id", service_id=service.id),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    service = json.loads(result.get_data(as_text=True))["data"]
    assert service["prefix_sms"] == should_prefix


@pytest.mark.parametrize(
    "posted_value, stored_value, returned_value",
    [
        (True, True, True),
        (False, False, False),
    ],
)
def test_set_sms_prefixing_for_service(
    admin_request,
    client,
    sample_service,
    posted_value,
    stored_value,
    returned_value,
):
    result = admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={"prefix_sms": posted_value},
    )
    assert result["data"]["prefix_sms"] == stored_value


def test_set_sms_prefixing_for_service_cant_be_none(
    admin_request,
    sample_service,
):
    resp = admin_request.post(
        "service.update_service",
        service_id=sample_service.id,
        _data={"prefix_sms": None},
        _expected_status=400,
    )
    assert resp["message"] == {"prefix_sms": ["Field may not be null."]}


@pytest.mark.parametrize(
    "today_only,stats",
    [
        (
            "False",
            {
                StatisticsType.REQUESTED: 2,
                StatisticsType.DELIVERED: 1,
                StatisticsType.FAILURE: 0,
                StatisticsType.PENDING: 0,
            },
        ),
        (
            "True",
            {
                StatisticsType.REQUESTED: 1,
                StatisticsType.DELIVERED: 0,
                StatisticsType.FAILURE: 0,
                StatisticsType.PENDING: 0,
            },
        ),
    ],
    ids=["seven_days", "today"],
)
def test_get_detailed_service(
    sample_template, client, sample_service, today_only, stats
):
    create_ft_notification_status(
        date(2000, 1, 1), NotificationType.SMS, sample_service, count=1
    )
    with freeze_time("2000-01-02T12:00:00"):
        create_notification(template=sample_template, status=NotificationStatus.CREATED)
        resp = client.get(
            f"/service/{sample_service.id}?detailed=True&today_only={today_only}",
            headers=[create_admin_authorization_header()],
        )

    assert resp.status_code == 200
    service = resp.json["data"]
    assert service["id"] == str(sample_service.id)
    assert "statistics" in service.keys()
    assert set(service["statistics"].keys()) == {
        NotificationType.SMS,
        NotificationType.EMAIL,
    }
    assert service["statistics"][NotificationType.SMS] == stats


def test_get_services_with_detailed_flag(client, sample_template):
    notifications = [
        create_notification(sample_template),
        create_notification(sample_template),
        create_notification(sample_template, key_type=KeyType.TEST),
    ]
    resp = client.get(
        "/service?detailed=True", headers=[create_admin_authorization_header()]
    )

    assert resp.status_code == 200
    data = resp.json["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Sample service"
    assert data[0]["id"] == str(notifications[0].service_id)
    assert data[0]["statistics"] == {
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
        NotificationType.SMS: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 3,
        },
    }


def test_get_services_with_detailed_flag_excluding_from_test_key(
    client, sample_template
):
    create_notification(sample_template, key_type=KeyType.NORMAL)
    create_notification(sample_template, key_type=KeyType.TEAM)
    create_notification(sample_template, key_type=KeyType.TEST)
    create_notification(sample_template, key_type=KeyType.TEST)
    create_notification(sample_template, key_type=KeyType.TEST)

    resp = client.get(
        "/service?detailed=True&include_from_test_key=False",
        headers=[create_admin_authorization_header()],
    )

    assert resp.status_code == 200
    data = resp.json["data"]
    assert len(data) == 1
    assert data[0]["statistics"] == {
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
        NotificationType.SMS: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 2,
        },
    }


def test_get_services_with_detailed_flag_accepts_date_range(client, mocker):
    mock_get_detailed_services = mocker.patch(
        "app.service.rest.get_detailed_services", return_value={}
    )
    resp = client.get(
        url_for(
            "service.get_services",
            detailed=True,
            start_date="2001-01-01",
            end_date="2002-02-02",
        ),
        headers=[create_admin_authorization_header()],
    )

    mock_get_detailed_services.assert_called_once_with(
        start_date=date(2001, 1, 1),
        end_date=date(2002, 2, 2),
        only_active=ANY,
        include_from_test_key=ANY,
    )
    assert resp.status_code == 200


@freeze_time("2002-02-02")
def test_get_services_with_detailed_flag_defaults_to_today(client, mocker):
    mock_get_detailed_services = mocker.patch(
        "app.service.rest.get_detailed_services", return_value={}
    )
    resp = client.get(
        url_for("service.get_services", detailed=True),
        headers=[create_admin_authorization_header()],
    )

    mock_get_detailed_services.assert_called_once_with(
        end_date=date(2002, 2, 2),
        include_from_test_key=ANY,
        only_active=ANY,
        start_date=date(2002, 2, 2),
    )

    assert resp.status_code == 200


def test_get_detailed_services_groups_by_service(notify_db_session):
    from app.service.rest import get_detailed_services

    service_1 = create_service(service_name="1", email_from="1")
    service_2 = create_service(service_name="2", email_from="2")

    service_1_template = create_template(service_1)
    service_2_template = create_template(service_2)

    create_notification(service_1_template, status=NotificationStatus.CREATED)
    create_notification(service_2_template, status=NotificationStatus.CREATED)
    create_notification(service_1_template, status=NotificationStatus.DELIVERED)
    create_notification(service_1_template, status=NotificationStatus.CREATED)

    data = get_detailed_services(start_date=utc_now().date(), end_date=utc_now().date())
    data = sorted(data, key=lambda x: x["name"])

    assert len(data) == 2
    assert data[0]["id"] == str(service_1.id)
    assert data[0]["statistics"] == {
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
        NotificationType.SMS: {
            StatisticsType.DELIVERED: 1,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 3,
        },
    }
    assert data[1]["id"] == str(service_2.id)
    assert data[1]["statistics"] == {
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
        NotificationType.SMS: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 1,
        },
    }


def test_get_detailed_services_includes_services_with_no_notifications(
    notify_db_session,
):
    from app.service.rest import get_detailed_services

    service_1 = create_service(service_name="1", email_from="1")
    service_2 = create_service(service_name="2", email_from="2")

    service_1_template = create_template(service_1)
    create_notification(service_1_template)

    data = get_detailed_services(start_date=utc_now().date(), end_date=utc_now().date())
    data = sorted(data, key=lambda x: x["name"])

    assert len(data) == 2
    assert data[0]["id"] == str(service_1.id)
    assert data[0]["statistics"] == {
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
        NotificationType.SMS: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 1,
        },
    }
    assert data[1]["id"] == str(service_2.id)
    assert data[1]["statistics"] == {
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
        NotificationType.SMS: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
    }


def test_get_detailed_services_only_includes_todays_notifications(sample_template):
    from app.service.rest import get_detailed_services

    create_notification(sample_template, created_at=datetime(2015, 10, 10, 3, 59))
    create_notification(sample_template, created_at=datetime(2015, 10, 10, 4, 0))
    create_notification(sample_template, created_at=datetime(2015, 10, 10, 12, 0))
    create_notification(sample_template, created_at=datetime(2015, 10, 11, 3, 0))

    with freeze_time("2015-10-10T12:00:00"):
        data = get_detailed_services(
            start_date=utc_now().date(), end_date=utc_now().date()
        )
        data = sorted(data, key=lambda x: x["id"])

    assert len(data) == 1
    assert data[0]["statistics"] == {
        NotificationType.EMAIL: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 0,
        },
        NotificationType.SMS: {
            StatisticsType.DELIVERED: 0,
            StatisticsType.FAILURE: 0,
            StatisticsType.PENDING: 0,
            StatisticsType.REQUESTED: 3,
        },
    }


@pytest.mark.parametrize("start_date_delta, end_date_delta", [(2, 1), (3, 2), (1, 0)])
@freeze_time("2017-03-28T12:00:00")
def test_get_detailed_services_for_date_range(
    sample_template, start_date_delta, end_date_delta
):
    from app.service.rest import get_detailed_services

    create_ft_notification_status(
        local_date=(utc_now() - timedelta(days=3)).date(),
        service=sample_template.service,
        notification_type=NotificationType.SMS,
    )
    create_ft_notification_status(
        local_date=(utc_now() - timedelta(days=2)).date(),
        service=sample_template.service,
        notification_type=NotificationType.SMS,
    )
    create_ft_notification_status(
        local_date=(utc_now() - timedelta(days=1)).date(),
        service=sample_template.service,
        notification_type=NotificationType.SMS,
    )

    create_notification(
        template=sample_template,
        created_at=utc_now(),
        status=NotificationStatus.DELIVERED,
    )

    start_date = (utc_now() - timedelta(days=start_date_delta)).date()
    end_date = (utc_now() - timedelta(days=end_date_delta)).date()

    data = get_detailed_services(
        only_active=False,
        include_from_test_key=True,
        start_date=start_date,
        end_date=end_date,
    )

    assert len(data) == 1
    assert data[0]["statistics"][NotificationType.EMAIL] == {
        StatisticsType.DELIVERED: 0,
        StatisticsType.FAILURE: 0,
        StatisticsType.PENDING: 0,
        StatisticsType.REQUESTED: 0,
    }
    assert data[0]["statistics"][NotificationType.SMS] == {
        StatisticsType.DELIVERED: 2,
        StatisticsType.FAILURE: 0,
        StatisticsType.PENDING: 0,
        StatisticsType.REQUESTED: 2,
    }


def test_update_service_calls_send_notification_as_service_becomes_live(
    notify_db_session, client, mocker
):
    send_notification_mock = mocker.patch(
        "app.service.rest.send_notification_to_service_users"
    )

    restricted_service = create_service(restricted=True)

    data = {"restricted": False}

    auth_header = create_admin_authorization_header()
    resp = client.post(
        f"service/{restricted_service.id}",
        data=json.dumps(data),
        headers=[auth_header],
        content_type="application/json",
    )

    assert resp.status_code == 200
    send_notification_mock.assert_called_once_with(
        service_id=restricted_service.id,
        template_id="618185c6-3636-49cd-b7d2-6f6f5eb3bdde",
        personalisation={"service_name": restricted_service.name},
        include_user_fields=["name"],
    )


def test_update_service_does_not_call_send_notification_for_live_service(
    sample_service, client, mocker
):
    send_notification_mock = mocker.patch(
        "app.service.rest.send_notification_to_service_users"
    )

    data = {"restricted": True}

    auth_header = create_admin_authorization_header()
    resp = client.post(
        f"service/{sample_service.id}",
        data=json.dumps(data),
        headers=[auth_header],
        content_type="application/json",
    )

    assert resp.status_code == 200
    assert not send_notification_mock.called


def test_update_service_does_not_call_send_notification_when_restricted_not_changed(
    sample_service, client, mocker
):
    send_notification_mock = mocker.patch(
        "app.service.rest.send_notification_to_service_users"
    )

    data = {"name": "Name of service"}

    auth_header = create_admin_authorization_header()
    resp = client.post(
        f"service/{sample_service.id}",
        data=json.dumps(data),
        headers=[auth_header],
        content_type="application/json",
    )

    assert resp.status_code == 200
    assert not send_notification_mock.called


def test_send_one_off_notification(sample_service, admin_request, mocker):
    template = create_template(service=sample_service)
    mocker.patch("app.service.send_notification.send_notification_to_queue")

    response = admin_request.post(
        "service.create_one_off_notification",
        service_id=sample_service.id,
        _data={
            "template_id": str(template.id),
            "to": "2028675309",
            "created_by": str(sample_service.created_by_id),
        },
        _expected_status=201,
    )

    noti = db.session.execute(select(Notification)).scalars().one()
    assert response["id"] == str(noti.id)


def test_get_notification_for_service_includes_template_redacted(
    admin_request, sample_notification
):
    resp = admin_request.get(
        "service.get_notification_for_service",
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id,
    )

    assert resp["id"] == str(sample_notification.id)
    assert resp["template"]["redact_personalisation"] is False


def test_get_all_notifications_for_service_includes_template_redacted(
    admin_request, sample_service
):
    normal_template = create_template(sample_service)

    redacted_template = create_template(sample_service)
    dao_redact_template(redacted_template, sample_service.created_by_id)

    with freeze_time("2000-01-01"):
        redacted_noti = create_notification(redacted_template)
    with freeze_time("2000-01-02"):
        normal_noti = create_notification(normal_template)

    resp = admin_request.get(
        "service.get_all_notifications_for_service", service_id=sample_service.id
    )

    assert resp["notifications"][0]["id"] == str(normal_noti.id)
    assert resp["notifications"][0]["template"]["redact_personalisation"] is False

    assert resp["notifications"][1]["id"] == str(redacted_noti.id)
    assert resp["notifications"][1]["template"]["redact_personalisation"] is True


def test_get_email_reply_to_addresses_when_there_are_no_reply_to_email_addresses(
    client, sample_service
):
    response = client.get(
        f"/service/{sample_service.id}/email-reply-to",
        headers=[create_admin_authorization_header()],
    )

    assert json.loads(response.get_data(as_text=True)) == []
    assert response.status_code == 200


def test_get_email_reply_to_addresses_with_one_email_address(client, notify_db_session):
    service = create_service()
    create_reply_to_email(service, "test@mail.com")

    response = client.get(
        f"/service/{service.id}/email-reply-to",
        headers=[create_admin_authorization_header()],
    )
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 1
    assert json_response[0]["email_address"] == "test@mail.com"
    assert json_response[0]["is_default"]
    assert json_response[0]["created_at"]
    assert not json_response[0]["updated_at"]
    assert response.status_code == 200


def test_get_email_reply_to_addresses_with_multiple_email_addresses(
    client, notify_db_session
):
    service = create_service()
    reply_to_a = create_reply_to_email(service, "test_a@mail.com")
    reply_to_b = create_reply_to_email(service, "test_b@mail.com", False)

    response = client.get(
        f"/service/{service.id}/email-reply-to",
        headers=[create_admin_authorization_header()],
    )
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 2
    assert response.status_code == 200

    assert json_response[0]["id"] == str(reply_to_a.id)
    assert json_response[0]["service_id"] == str(reply_to_a.service_id)
    assert json_response[0]["email_address"] == "test_a@mail.com"
    assert json_response[0]["is_default"]
    assert json_response[0]["created_at"]
    assert not json_response[0]["updated_at"]

    assert json_response[1]["id"] == str(reply_to_b.id)
    assert json_response[1]["service_id"] == str(reply_to_b.service_id)
    assert json_response[1]["email_address"] == "test_b@mail.com"
    assert not json_response[1]["is_default"]
    assert json_response[1]["created_at"]
    assert not json_response[1]["updated_at"]


def test_verify_reply_to_email_address_should_send_verification_email(
    admin_request, notify_db_session, mocker, verify_reply_to_address_email_template
):
    service = create_service()
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    data = {"email": "reply-here@example.gov.uk"}
    notify_service = verify_reply_to_address_email_template.service
    response = admin_request.post(
        "service.verify_reply_to_email_address",
        service_id=service.id,
        _data=data,
        _expected_status=201,
    )

    notification = db.session.execute(select(Notification)).scalars().first()
    assert notification.template_id == verify_reply_to_address_email_template.id
    assert response["data"] == {"id": str(notification.id)}
    mocked.assert_called_once_with(
        [str(notification.id)], queue="notify-internal-tasks", countdown=60
    )
    assert (
        notification.reply_to_text
        == notify_service.get_default_reply_to_email_address()
    )


def test_verify_reply_to_email_address_doesnt_allow_duplicates(
    admin_request, notify_db_session, mocker
):
    data = {"email": "reply-here@example.gov.uk"}
    service = create_service()
    create_reply_to_email(service, "reply-here@example.gov.uk")
    response = admin_request.post(
        "service.verify_reply_to_email_address",
        service_id=service.id,
        _data=data,
        _expected_status=409,
    )
    assert (
        response["message"]
        == "Your service already uses ‘reply-here@example.gov.uk’ as an email reply-to address."
    )


def test_add_service_reply_to_email_address(admin_request, sample_service):
    data = {"email_address": "new@reply.com", "is_default": True}
    response = admin_request.post(
        "service.add_service_reply_to_email_address",
        service_id=sample_service.id,
        _data=data,
        _expected_status=201,
    )

    results = db.session.execute(select(ServiceEmailReplyTo)).scalars().all()
    assert len(results) == 1
    assert response["data"] == results[0].serialize()


def test_add_service_reply_to_email_address_doesnt_allow_duplicates(
    admin_request, notify_db_session, mocker
):
    data = {"email_address": "reply-here@example.gov.uk", "is_default": True}
    service = create_service()
    create_reply_to_email(service, "reply-here@example.gov.uk")
    response = admin_request.post(
        "service.add_service_reply_to_email_address",
        service_id=service.id,
        _data=data,
        _expected_status=409,
    )
    assert (
        response["message"]
        == "Your service already uses ‘reply-here@example.gov.uk’ as an email reply-to address."
    )


def test_add_service_reply_to_email_address_can_add_multiple_addresses(
    admin_request, sample_service
):
    data = {"email_address": "first@reply.com", "is_default": True}
    admin_request.post(
        "service.add_service_reply_to_email_address",
        service_id=sample_service.id,
        _data=data,
        _expected_status=201,
    )
    second = {"email_address": "second@reply.com", "is_default": True}
    response = admin_request.post(
        "service.add_service_reply_to_email_address",
        service_id=sample_service.id,
        _data=second,
        _expected_status=201,
    )
    results = db.session.execute(select(ServiceEmailReplyTo)).scalars().all()
    assert len(results) == 2
    default = [x for x in results if x.is_default]
    assert response["data"] == default[0].serialize()
    first_reply_to_not_default = [x for x in results if not x.is_default]
    assert first_reply_to_not_default[0].email_address == "first@reply.com"


def test_add_service_reply_to_email_address_raise_exception_if_no_default(
    admin_request, sample_service
):
    data = {"email_address": "first@reply.com", "is_default": False}
    response = admin_request.post(
        "service.add_service_reply_to_email_address",
        service_id=sample_service.id,
        _data=data,
        _expected_status=400,
    )
    assert (
        response["message"]
        == "You must have at least one reply to email address as the default."
    )


def test_add_service_reply_to_email_address_404s_when_invalid_service_id(
    admin_request, notify_db_session
):
    response = admin_request.post(
        "service.add_service_reply_to_email_address",
        service_id=uuid.uuid4(),
        _data={},
        _expected_status=404,
    )

    assert response["result"] == "error"
    assert response["message"] == "No result found"


def test_update_service_reply_to_email_address(admin_request, sample_service):
    original_reply_to = create_reply_to_email(
        service=sample_service, email_address="some@email.com"
    )
    data = {"email_address": "changed@reply.com", "is_default": True}
    response = admin_request.post(
        "service.update_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=original_reply_to.id,
        _data=data,
        _expected_status=200,
    )

    results = db.session.execute(select(ServiceEmailReplyTo)).scalars().all()
    assert len(results) == 1
    assert response["data"] == results[0].serialize()


def test_update_service_reply_to_email_address_returns_400_when_no_default(
    admin_request, sample_service
):
    original_reply_to = create_reply_to_email(
        service=sample_service, email_address="some@email.com"
    )
    data = {"email_address": "changed@reply.com", "is_default": False}
    response = admin_request.post(
        "service.update_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=original_reply_to.id,
        _data=data,
        _expected_status=400,
    )

    assert (
        response["message"]
        == "You must have at least one reply to email address as the default."
    )


def test_update_service_reply_to_email_address_404s_when_invalid_service_id(
    admin_request, notify_db_session
):
    response = admin_request.post(
        "service.update_service_reply_to_email_address",
        service_id=uuid.uuid4(),
        reply_to_email_id=uuid.uuid4(),
        _data={},
        _expected_status=404,
    )

    assert response["result"] == "error"
    assert response["message"] == "No result found"


def test_delete_service_reply_to_email_address_archives_an_email_reply_to(
    sample_service, admin_request, notify_db_session
):
    create_reply_to_email(service=sample_service, email_address="some@email.com")
    reply_to = create_reply_to_email(
        service=sample_service, email_address="some@email.com", is_default=False
    )

    admin_request.post(
        "service.delete_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=reply_to.id,
    )
    assert reply_to.archived is True


def test_delete_service_reply_to_email_address_returns_400_if_archiving_default_reply_to(
    admin_request, notify_db_session, sample_service
):
    reply_to = create_reply_to_email(
        service=sample_service, email_address="some@email.com"
    )

    response = admin_request.post(
        "service.delete_service_reply_to_email_address",
        service_id=sample_service.id,
        reply_to_email_id=reply_to.id,
        _expected_status=400,
    )

    assert response == {
        "message": "You cannot delete a default email reply to address",
        "result": "error",
    }
    assert reply_to.archived is False


def test_get_email_reply_to_address(client, notify_db_session):
    service = create_service()
    reply_to = create_reply_to_email(service, "test_a@mail.com")

    response = client.get(
        f"/service/{service.id}/email-reply-to/{reply_to.id}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == reply_to.serialize()


def test_add_service_sms_sender_can_add_multiple_senders(client, notify_db_session):
    service = create_service()
    data = {
        "sms_sender": "second",
        "is_default": False,
    }
    response = client.post(
        f"/service/{service.id}/sms-sender",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["sms_sender"] == "second"
    assert not resp_json["is_default"]
    senders = db.session.execute(select(ServiceSmsSender)).scalars().all()
    assert len(senders) == 2


def test_add_service_sms_sender_when_it_is_an_inbound_number_updates_the_only_existing_non_archived_sms_sender(
    client, notify_db_session
):
    service = create_service_with_defined_sms_sender(sms_sender_value="GOVUK")
    create_service_sms_sender(
        service=service, sms_sender="archived", is_default=False, archived=True
    )
    inbound_number = create_inbound_number(number="12345")
    data = {
        "sms_sender": str(inbound_number.id),
        "is_default": True,
        "inbound_number_id": str(inbound_number.id),
    }
    response = client.post(
        f"/service/{service.id}/sms-sender",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 201
    updated_number = db.session.get(InboundNumber, inbound_number.id)
    assert updated_number.service_id == service.id
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["sms_sender"] == inbound_number.number
    assert resp_json["inbound_number_id"] == str(inbound_number.id)
    assert resp_json["is_default"]

    senders = dao_get_sms_senders_by_service_id(service.id)
    assert len(senders) == 1


def test_add_service_sms_sender_when_it_is_an_inbound_number_inserts_new_sms_sender_when_more_than_one(
    client, notify_db_session
):
    service = create_service_with_defined_sms_sender(sms_sender_value="GOVUK")
    create_service_sms_sender(service=service, sms_sender="second", is_default=False)
    inbound_number = create_inbound_number(number="12345")
    data = {
        "sms_sender": str(inbound_number.id),
        "is_default": True,
        "inbound_number_id": str(inbound_number.id),
    }
    response = client.post(
        f"/service/{service.id}/sms-sender",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 201
    updated_number = db.session.get(InboundNumber, inbound_number.id)
    assert updated_number.service_id == service.id
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["sms_sender"] == inbound_number.number
    assert resp_json["inbound_number_id"] == str(inbound_number.id)
    assert resp_json["is_default"]

    stmt = (
        select(func.count())
        .select_from(ServiceSmsSender)
        .where(ServiceSmsSender.service_id == service.id)
    )
    senders = db.session.execute(stmt).scalar() or 0
    assert senders == 3


def test_add_service_sms_sender_switches_default(client, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value="first")
    data = {
        "sms_sender": "second",
        "is_default": True,
    }
    response = client.post(
        f"/service/{service.id}/sms-sender",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["sms_sender"] == "second"
    assert not resp_json["inbound_number_id"]
    assert resp_json["is_default"]
    stmt = select(ServiceSmsSender).where(ServiceSmsSender.sms_sender == "first")
    sms_senders = db.session.execute(stmt).scalars().first()
    assert not sms_senders.is_default


def test_add_service_sms_sender_return_404_when_service_does_not_exist(client):
    data = {"sms_sender": "12345", "is_default": False}
    response = client.post(
        f"/service/{uuid.uuid4()}/sms-sender",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result["result"] == "error"
    assert result["message"] == "No result found"


def test_update_service_sms_sender(client, notify_db_session):
    service = create_service()
    service_sms_sender = create_service_sms_sender(
        service=service, sms_sender="1235", is_default=False
    )
    data = {
        "sms_sender": "second",
        "is_default": False,
    }
    response = client.post(
        f"/service/{service.id}/sms-sender/{service_sms_sender.id}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["sms_sender"] == "second"
    assert not resp_json["inbound_number_id"]
    assert not resp_json["is_default"]


@settings(max_examples=10)
@given(
    fuzzed_sms_sender=st.text(min_size=1, max_size=50), fuzzed_is_default=st.booleans()
)
def test_fuzz_update_service_sms_sender(client, fuzzed_sms_sender, fuzzed_is_default):
    service = create_service(service_name=f"service-{uuid.uuid4()}")
    service_sms_sender = create_service_sms_sender(
        service=service, sms_sender="1235", is_default=False
    )
    data = {
        "sms_sender": fuzzed_sms_sender,
        "is_default": fuzzed_is_default,
    }
    response = client.post(
        f"/service/{service.id}/sms-sender/{service_sms_sender.id}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code in [
        200,
        400,
    ], f"Unexpected status: {response.status_code}, body: {response.get_data(as_text=True)}"

    if response.status_code == 200:
        resp_json = json.loads(response.get_data(as_text=True))
        assert resp_json["sms_sender"] == fuzzed_sms_sender
        assert resp_json["is_default"] == fuzzed_is_default


def test_update_service_sms_sender_switches_default(client, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value="first")
    service_sms_sender = create_service_sms_sender(
        service=service, sms_sender="1235", is_default=False
    )
    data = {
        "sms_sender": "second",
        "is_default": True,
    }
    response = client.post(
        f"/service/{service.id}/sms-sender/{service_sms_sender.id}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["sms_sender"] == "second"
    assert not resp_json["inbound_number_id"]
    assert resp_json["is_default"]
    stmt = select(ServiceSmsSender).where(ServiceSmsSender.sms_sender == "first")
    sms_senders = db.session.execute(stmt).scalars().first()
    assert not sms_senders.is_default


def test_update_service_sms_sender_does_not_allow_sender_update_for_inbound_number(
    client, notify_db_session
):
    service = create_service()
    inbound_number = create_inbound_number("12345", service_id=service.id)
    service_sms_sender = create_service_sms_sender(
        service=service,
        sms_sender="1235",
        is_default=False,
        inbound_number_id=inbound_number.id,
    )
    data = {
        "sms_sender": "second",
        "is_default": True,
        "inbound_number_id": str(inbound_number.id),
    }
    response = client.post(
        f"/service/{service.id}/sms-sender/{service_sms_sender.id}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 400


def test_update_service_sms_sender_return_404_when_service_does_not_exist(client):
    data = {"sms_sender": "12345", "is_default": False}
    response = client.post(
        f"/service/{uuid.uuid4()}/sms-sender/{uuid.uuid4()}",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result["result"] == "error"
    assert result["message"] == "No result found"


def test_delete_service_sms_sender_can_archive_sms_sender(
    admin_request, notify_db_session
):
    service = create_service()
    service_sms_sender = create_service_sms_sender(
        service=service, sms_sender="5678", is_default=False
    )

    admin_request.post(
        "service.delete_service_sms_sender",
        service_id=service.id,
        sms_sender_id=service_sms_sender.id,
    )

    assert service_sms_sender.archived is True


def test_delete_service_sms_sender_returns_400_if_archiving_inbound_number(
    admin_request, notify_db_session
):
    service = create_service_with_inbound_number(inbound_number="7654321")
    inbound_number = service.service_sms_senders[0]

    response = admin_request.post(
        "service.delete_service_sms_sender",
        service_id=service.id,
        sms_sender_id=service.service_sms_senders[0].id,
        _expected_status=400,
    )
    assert response == {
        "message": "You cannot delete an inbound number",
        "result": "error",
    }
    assert inbound_number.archived is False


def test_get_service_sms_sender_by_id(client, notify_db_session):
    service_sms_sender = create_service_sms_sender(
        service=create_service(), sms_sender="1235", is_default=False
    )
    response = client.get(
        f"/service/{service_sms_sender.service_id}/sms-sender/{service_sms_sender.id}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == service_sms_sender.serialize()


def test_get_service_sms_sender_by_id_returns_404_when_service_does_not_exist(
    client, notify_db_session
):
    service_sms_sender = create_service_sms_sender(
        service=create_service(), sms_sender="1235", is_default=False
    )
    response = client.get(
        f"/service/{uuid.uuid4()}/sms-sender/{service_sms_sender.id}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 404


def test_get_service_sms_sender_by_id_returns_404_when_sms_sender_does_not_exist(
    client, notify_db_session
):
    service = create_service()
    response = client.get(
        f"/service/{service.id}/sms-sender/{uuid.uuid4()}",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 404


def test_get_service_sms_senders_for_service(client, notify_db_session):
    service_sms_sender = create_service_sms_sender(
        service=create_service(), sms_sender="second", is_default=False
    )
    response = client.get(
        f"/service/{service_sms_sender.service_id}/sms-sender",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp) == 2
    assert json_resp[0]["is_default"]
    assert json_resp[0]["sms_sender"] == current_app.config["FROM_NUMBER"]
    assert not json_resp[1]["is_default"]
    assert json_resp[1]["sms_sender"] == "second"


def test_get_service_sms_senders_for_service_returns_empty_list_when_service_does_not_exist(
    client,
):
    response = client.get(
        f"/service/{uuid.uuid4()}/sms-sender",
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == []


def test_get_organization_for_service_id(
    admin_request, sample_service, sample_organization
):
    dao_add_service_to_organization(sample_service, sample_organization.id)
    response = admin_request.get(
        "service.get_organization_for_service", service_id=sample_service.id
    )
    assert response == sample_organization.serialize()


def test_get_organization_for_service_id_return_empty_dict_if_service_not_in_organization(
    admin_request, fake_uuid
):
    response = admin_request.get(
        "service.get_organization_for_service", service_id=fake_uuid
    )
    assert response == {}


def test_get_monthly_notification_data_by_service(sample_service, admin_request):
    create_ft_notification_status(
        date(2019, 4, 17),
        notification_type=NotificationType.SMS,
        service=sample_service,
        notification_status=NotificationStatus.DELIVERED,
    )
    create_ft_notification_status(
        date(2019, 3, 5),
        notification_type=NotificationType.EMAIL,
        service=sample_service,
        notification_status=NotificationStatus.SENDING,
        count=4,
    )
    response = admin_request.get(
        "service.get_monthly_notification_data_by_service",
        start_date="2019-01-01",
        end_date="2019-06-17",
    )

    assert response == [
        [
            "2019-03-01",
            str(sample_service.id),
            "Sample service",
            NotificationType.EMAIL,
            4,
            0,
            0,
            0,
            0,
            0,
        ],
        [
            "2019-04-01",
            str(sample_service.id),
            "Sample service",
            NotificationType.SMS,
            0,
            1,
            0,
            0,
            0,
            0,
        ],
    ]


def test_get_service_notification_statistics_by_day(
    admin_request, mocker, sample_service
):
    mock_data = [
        {
            "notification_type": "email",
            "status": "sent",
            "day": "2024-11-01",
            "count": 10,
        },
        {
            "notification_type": "sms",
            "status": "failed",
            "day": "2024-11-02",
            "count": 5,
        },
        {
            "notification_type": "sms",
            "status": "delivered",
            "day": "2024-11-03",
            "count": 11,
        },
    ]

    mock_get_service_statistics_for_specific_days = mocker.patch(
        "app.service.rest.get_service_statistics_for_specific_days",
        return_value=mock_data,
    )

    response = admin_request.get(
        "service.get_service_notification_statistics_by_day",
        service_id=sample_service.id,
        start="2024-11-03",
        days="1",
    )["data"]

    assert mock_get_service_statistics_for_specific_days.assert_called_once
    assert response == mock_data


@patch("app.service.rest.check_suspicious_id")
@patch("app.service.rest.dao_fetch_stats_for_service_from_hours")
@patch("app.service.rest.get_specific_hours_stats")
def test_get_service_statistics_for_specific_days(
    mock_get_stats, mock_fetch_stats, mock_check_id
):
    service_id = "test-service"
    start_date_str = "2025-07-01"
    days = 2

    fake_total_notifications = {
        datetime(2025, 6, 30, 12): 100,
        datetime(2025, 6, 30, 13): 200,
    }
    fake_results = [
        MagicMock(
            notification_type="email",
            status="delivered",
            hour=datetime(2025, 6, 30, 12),
            count=50,
        ),
        MagicMock(
            notification_type="sms",
            status="failed",
            hour=datetime(2025, 6, 30, 13),
            count=150,
        ),
    ]
    mock_fetch_stats.return_value = (fake_total_notifications, fake_results)
    expected_output = {"emails_sent": 50, "sms_failed": 150}
    mock_get_stats.return_value = expected_output
    result = get_service_statistics_for_specific_days(service_id, start_date_str, days)
    assert result == expected_output
    mock_check_id.assert_called_once_with(service_id)
    expected_start = datetime(2025, 6, 30)
    expected_end = datetime(2025, 7, 1)
    mock_fetch_stats.assert_called_once_with(service_id, expected_start, expected_end)
    mock_get_stats.assert_called_once_with(
        fake_results,
        expected_start,
        hours=48,
        total_notifications=fake_total_notifications,
    )


@patch("app.service.rest.dao_fetch_stats_for_service_from_days_for_user")
@patch("app.service.rest.get_specific_hours_stats")
def test_get_service_statistics_for_specific_days_by_user(
    mock_get_stats, mock_fetch_stats
):
    service_id = "service-abc"
    user_id = "user-123"
    start_date_str = "2025-07-01"
    days = 3
    expected_end = datetime(2025, 7, 1)
    expected_start = expected_end - timedelta(days=days - 1)

    mock_total_notifications = {
        datetime(2025, 6, 29, 10): 5,
        datetime(2025, 6, 30, 12): 8,
    }
    mock_results = [
        MagicMock(
            notification_type="email",
            status="delivered",
            hour=datetime(2025, 6, 29, 10),
            count=5,
        ),
        MagicMock(
            notification_type="sms",
            status="sent",
            hour=datetime(2025, 6, 30, 12),
            count=8,
        ),
    ]

    mock_fetch_stats.return_value = (mock_total_notifications, mock_results)
    expected_stats = {"emails_delivered": 5, "sms_sent": 8}
    mock_get_stats.return_value = expected_stats
    result = get_service_statistics_for_specific_days_by_user(
        service_id, user_id, start_date_str, days
    )
    assert result == expected_stats
    mock_fetch_stats.assert_called_once_with(
        service_id, expected_start, expected_end, user_id
    )
    mock_get_stats.assert_called_once_with(
        mock_results,
        expected_start,
        hours=days * 24,
        total_notifications=mock_total_notifications,
    )


def test_check_request_args_success():
    mock_request = MagicMock()
    mock_request.args.get.side_effect = lambda key, default=None: {
        "service_id": "abc123",
        "name": "test service",
        "email_from": "test@example.com",
    }.get(key, default)

    result = check_request_args(mock_request)
    assert result == ("abc123", "test service", "test@example.com")


@pytest.mark.parametrize(
    "args_dict,expected_errors",
    [
        (
            {},
            [
                {"service_id": ["Can't be empty"]},
                {"name": ["Can't be empty"]},
                {"email_from": ["Can't be empty"]},
            ],
        ),
        (
            {"service_id": "abc123"},
            [{"name": ["Can't be empty"]}, {"email_from": ["Can't be empty"]}],
        ),
        (
            {"service_id": "abc123", "name": "Test"},
            [{"email_from": ["Can't be empty"]}],
        ),
    ],
)
def test_check_request_args_missing_fields(args_dict, expected_errors):
    mock_request = MagicMock()
    mock_request.args.get.side_effect = lambda key, default=None: args_dict.get(
        key, default
    )
    with pytest.raises(InvalidRequest) as exc:
        check_request_args(mock_request)

    assert exc.value.status_code == 400
    assert exc.value.message == expected_errors
