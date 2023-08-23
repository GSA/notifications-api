import pytest
from flask import json
from freezegun import freeze_time

from app.models import ProviderDetails, ProviderDetailsHistory
from tests import create_admin_authorization_header
from tests.app.db import create_ft_billing


def test_get_provider_details_returns_all_providers(admin_request, notify_db_session):
    json_resp = admin_request.get("provider_details.get_providers")["provider_details"]

    assert len(json_resp) > 0
    assert {"ses", "sns"} == {x["identifier"] for x in json_resp}


def test_get_provider_details_by_id(client, notify_db_session):
    response = client.get(
        "/provider-details", headers=[create_admin_authorization_header()]
    )
    json_resp = json.loads(response.get_data(as_text=True))["provider_details"]

    provider_resp = client.get(
        "/provider-details/{}".format(json_resp[0]["id"]),
        headers=[create_admin_authorization_header()],
    )

    provider = json.loads(provider_resp.get_data(as_text=True))["provider_details"]
    assert provider["identifier"] == json_resp[0]["identifier"]


@freeze_time("2018-06-28 12:00")
def test_get_provider_contains_correct_fields(client, sample_template):
    create_ft_billing("2018-06-01", sample_template, provider="sns", billable_unit=1)

    response = client.get(
        "/provider-details", headers=[create_admin_authorization_header()]
    )
    json_resp = json.loads(response.get_data(as_text=True))["provider_details"]
    allowed_keys = {
        "id",
        "created_by_name",
        "display_name",
        "identifier",
        "priority",
        "notification_type",
        "active",
        "updated_at",
        "supports_international",
        "current_month_billable_sms",
    }
    assert len(json_resp) > 0
    assert allowed_keys == set(json_resp[0].keys())


def test_should_be_able_to_update_priority(client, restore_provider_details):
    provider = ProviderDetails.query.first()

    update_resp = client.post(
        "/provider-details/{}".format(provider.id),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps({"priority": 5}),
    )
    assert update_resp.status_code == 200
    update_json = json.loads(update_resp.get_data(as_text=True))["provider_details"]
    assert update_json["identifier"] == provider.identifier
    assert update_json["priority"] == 5
    assert provider.priority == 5


def test_should_be_able_to_update_status(client, restore_provider_details):
    provider = ProviderDetails.query.first()

    update_resp_1 = client.post(
        "/provider-details/{}".format(provider.id),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps({"active": False}),
    )
    assert update_resp_1.status_code == 200
    update_resp_1 = json.loads(update_resp_1.get_data(as_text=True))["provider_details"]
    assert update_resp_1["identifier"] == provider.identifier
    assert not update_resp_1["active"]
    assert not provider.active


@pytest.mark.parametrize(
    "field,value", [("identifier", "new"), ("version", 7), ("updated_at", None)]
)
def test_should_not_be_able_to_update_disallowed_fields(
    client, restore_provider_details, field, value
):
    provider = ProviderDetails.query.first()

    resp = client.post(
        "/provider-details/{}".format(provider.id),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps({field: value}),
    )
    resp_json = json.loads(resp.get_data(as_text=True))

    assert resp_json["message"][field][0] == "Not permitted to be updated"
    assert resp_json["result"] == "error"
    assert resp.status_code == 400


def test_get_provider_versions_contains_correct_fields(client, notify_db_session):
    provider = ProviderDetailsHistory.query.first()
    response = client.get(
        "/provider-details/{}/versions".format(provider.id),
        headers=[create_admin_authorization_header()],
    )
    json_resp = json.loads(response.get_data(as_text=True))["data"]
    allowed_keys = {
        "id",
        "created_by",
        "display_name",
        "identifier",
        "priority",
        "notification_type",
        "active",
        "version",
        "updated_at",
        "supports_international",
    }
    assert allowed_keys == set(json_resp[0].keys())


def test_update_provider_should_store_user_id(
    client, restore_provider_details, sample_user
):
    provider = ProviderDetails.query.first()

    update_resp_1 = client.post(
        "/provider-details/{}".format(provider.id),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
        data=json.dumps({"created_by": sample_user.id, "active": False}),
    )
    assert update_resp_1.status_code == 200
    update_resp_1 = json.loads(update_resp_1.get_data(as_text=True))["provider_details"]
    assert update_resp_1["identifier"] == provider.identifier
    assert not update_resp_1["active"]
    assert not provider.active
