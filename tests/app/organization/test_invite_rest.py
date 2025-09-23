import os
import uuid

import pytest
from flask import current_app, json
from freezegun import freeze_time
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select

from app import db
from app.enums import InvitedUserStatus
from app.models import Notification
from notifications_utils.url_safe_token import generate_token
from tests import create_admin_authorization_header
from tests.app.db import create_invited_org_user


@pytest.mark.parametrize(
    "platform_admin, expected_invited_by",
    ((True, "The Notify.gov team"), (False, "Test User")),
)
@pytest.mark.parametrize(
    "extra_args, expected_start_of_invite_url",
    [
        ({}, "http://localhost:6012/organization-invitation/"),
        (
            {"invite_link_host": "https://www.example.com"},
            "https://www.example.com/organization-invitation/",
        ),
    ],
)
def test_create_invited_org_user(
    admin_request,
    sample_organization,
    sample_user,
    mocker,
    org_invite_email_template,
    extra_args,
    expected_start_of_invite_url,
    platform_admin,
    expected_invited_by,
):
    os.environ["LOGIN_DOT_GOV_REGISTRATION_URL"] = "http://foo.fake.gov"
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    email_address = "invited_user@example.com"
    sample_user.platform_admin = platform_admin

    data = dict(
        organization=str(sample_organization.id),
        email_address=email_address,
        invited_by=str(sample_user.id),
        nonce="dummy-nonce",
        state="dummy-state",
        **extra_args
    )

    json_resp = admin_request.post(
        "organization_invite.invite_user_to_org",
        organization_id=sample_organization.id,
        _data=data,
        _expected_status=201,
    )

    assert json_resp["data"]["organization"] == str(sample_organization.id)
    assert json_resp["data"]["email_address"] == email_address
    assert json_resp["data"]["invited_by"] == str(sample_user.id)
    assert json_resp["data"]["status"] == InvitedUserStatus.PENDING
    assert json_resp["data"]["id"]

    notification = db.session.execute(select(Notification)).scalars().first()

    assert notification.reply_to_text == sample_user.email_address

    assert len(notification.personalisation.keys()) == 3
    assert notification.personalisation["organization_name"] == "sample organization"
    assert notification.personalisation["user_name"] == expected_invited_by
    # assert notification.personalisation["url"].startswith(expected_start_of_invite_url)
    # assert len(notification.personalisation["url"]) > len(expected_start_of_invite_url)

    mocked.assert_called_once_with(
        [str(notification.id)], queue="notify-internal-tasks", countdown=60
    )


def test_create_invited_user_invalid_email(
    admin_request, sample_organization, sample_user, mocker
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    email_address = "notanemail"

    data = {
        "service": str(sample_organization.id),
        "email_address": email_address,
        "invited_by": str(sample_user.id),
    }

    json_resp = admin_request.post(
        "organization_invite.invite_user_to_org",
        organization_id=sample_organization.id,
        _data=data,
        _expected_status=400,
    )

    assert (
        json_resp["errors"][0]["message"] == "email_address Not a valid email address"
    )
    assert mocked.call_count == 0


def test_get_all_invited_users_by_service(
    admin_request, sample_organization, sample_user
):
    for i in range(5):
        create_invited_org_user(
            sample_organization,
            sample_user,
            email_address="invited_user_{}@service.gov.uk".format(i),
        )

    json_resp = admin_request.get(
        "organization_invite.get_invited_org_users_by_organization",
        organization_id=sample_organization.id,
    )

    assert len(json_resp["data"]) == 5
    for invite in json_resp["data"]:
        assert invite["organization"] == str(sample_organization.id)
        assert invite["invited_by"] == str(sample_user.id)
        assert invite["id"]


def test_get_invited_users_by_service_with_no_invites(
    admin_request, sample_organization
):
    json_resp = admin_request.get(
        "organization_invite.get_invited_org_users_by_organization",
        organization_id=sample_organization.id,
    )
    assert len(json_resp["data"]) == 0


def test_get_invited_user_by_organization(admin_request, sample_invited_org_user):
    json_resp = admin_request.get(
        "organization_invite.get_invited_org_user_by_organization",
        organization_id=sample_invited_org_user.organization.id,
        invited_org_user_id=sample_invited_org_user.id,
    )
    assert json_resp["data"]["email_address"] == sample_invited_org_user.email_address


def test_get_invited_user_by_organization_when_user_does_not_belong_to_the_org(
    admin_request,
    sample_invited_org_user,
    fake_uuid,
):
    json_resp = admin_request.get(
        "organization_invite.get_invited_org_user_by_organization",
        organization_id=fake_uuid,
        invited_org_user_id=sample_invited_org_user.id,
        _expected_status=404,
    )
    assert json_resp["result"] == "error"


def test_update_org_invited_user_set_status_to_cancelled(
    admin_request, sample_invited_org_user
):
    data = {"status": InvitedUserStatus.CANCELLED}

    json_resp = admin_request.post(
        "organization_invite.update_org_invite_status",
        organization_id=sample_invited_org_user.organization_id,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data,
    )
    assert json_resp["data"]["status"] == InvitedUserStatus.CANCELLED


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(random_user_id=st.uuids(), random_org_id=st.uuids())
def test_fuzz_update_org_invited_user_for_wrong_service_returns_404(
    admin_request, random_user_id, random_org_id
):
    data = {"status": InvitedUserStatus.CANCELLED}

    json_resp = admin_request.post(
        "organization_invite.update_org_invite_status",
        organization_id=random_org_id,
        invited_org_user_id=random_user_id,
        _data=data,
        _expected_status=404,
    )
    assert json_resp["message"] == "No result found"


def test_update_org_invited_user_for_invalid_data_returns_400(
    admin_request, sample_invited_org_user
):
    data = {"status": "garbage"}

    json_resp = admin_request.post(
        "organization_invite.update_org_invite_status",
        organization_id=sample_invited_org_user.organization_id,
        invited_org_user_id=sample_invited_org_user.id,
        _data=data,
        _expected_status=400,
    )
    assert len(json_resp["errors"]) == 1
    assert (
        json_resp["errors"][0]["message"]
        == "status garbage is not one of [pending, accepted, cancelled, expired]"
    )


@pytest.mark.parametrize(
    "endpoint_format_str",
    [
        "/invite/organization/{}",
        "/invite/organization/check/{}",
    ],
)
def test_validate_invitation_token_returns_200_when_token_valid(
    client, sample_invited_org_user, endpoint_format_str
):
    token = generate_token(
        str(sample_invited_org_user.id),
        current_app.config["SECRET_KEY"],
        current_app.config["DANGEROUS_SALT"],
    )

    url = endpoint_format_str.format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(
        url, headers=[("Content-Type", "application/json"), auth_header]
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"] == sample_invited_org_user.serialize()


def test_validate_invitation_token_for_expired_token_returns_400(client):
    with freeze_time("2016-01-01T12:00:00"):
        token = generate_token(
            str(uuid.uuid4()),
            current_app.config["SECRET_KEY"],
            current_app.config["DANGEROUS_SALT"],
        )
    url = "/invite/organization/{}".format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(
        url, headers=[("Content-Type", "application/json"), auth_header]
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == {
        "invitation": "Your invitation to Notify.gov has expired. "
        "Please ask the person that invited you to send you another one"
    }


def test_validate_invitation_token_returns_400_when_invited_user_does_not_exist(client):
    token = generate_token(
        str(uuid.uuid4()),
        current_app.config["SECRET_KEY"],
        current_app.config["DANGEROUS_SALT"],
    )
    url = "/invite/organization/{}".format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(
        url, headers=[("Content-Type", "application/json"), auth_header]
    )

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_validate_invitation_token_returns_400_when_token_is_malformed(client):
    token = generate_token(
        str(uuid.uuid4()),
        current_app.config["SECRET_KEY"],
        current_app.config["DANGEROUS_SALT"],
    )[:-2]

    url = "/invite/organization/{}".format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(
        url, headers=[("Content-Type", "application/json"), auth_header]
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == {
        "invitation": "Something’s wrong with this link. Make sure you’ve copied the whole thing."
    }


def test_get_invited_org_user(admin_request, sample_invited_org_user):
    json_resp = admin_request.get(
        "organization_invite.get_invited_org_user",
        invited_org_user_id=sample_invited_org_user.id,
    )
    assert json_resp["data"]["id"] == str(sample_invited_org_user.id)
    assert json_resp["data"]["email_address"] == sample_invited_org_user.email_address
    assert json_resp["data"]["organization"] == str(
        sample_invited_org_user.organization_id
    )


def test_get_invited_org_user_404s_if_invite_doesnt_exist(
    admin_request, sample_invited_org_user, fake_uuid
):
    json_resp = admin_request.get(
        "organization_invite.get_invited_org_user",
        invited_org_user_id=fake_uuid,
        _expected_status=404,
    )
    assert json_resp["result"] == "error"
