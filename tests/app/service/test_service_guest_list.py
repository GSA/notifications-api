import json
import uuid

from sqlalchemy import select

from app import db
from app.dao.service_guest_list_dao import dao_add_and_commit_guest_list_contacts
from app.enums import RecipientType
from app.models import ServiceGuestList
from tests import create_admin_authorization_header


def test_get_guest_list_returns_data(client, sample_service_guest_list):
    service_id = sample_service_guest_list.service_id

    response = client.get(
        f"service/{service_id}/guest-list",
        headers=[create_admin_authorization_header()],
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {
        "email_addresses": [sample_service_guest_list.recipient],
        "phone_numbers": [],
    }


def test_get_guest_list_separates_emails_and_phones(client, sample_service):
    dao_add_and_commit_guest_list_contacts(
        [
            ServiceGuestList.from_string(
                sample_service.id,
                RecipientType.EMAIL,
                "service@example.com",
            ),
            ServiceGuestList.from_string(
                sample_service.id, RecipientType.MOBILE, "2028675309"
            ),
            ServiceGuestList.from_string(
                sample_service.id,
                RecipientType.MOBILE,
                "+1800-555-5555",
            ),
        ]
    )

    response = client.get(
        "service/{}/guest-list".format(sample_service.id),
        headers=[create_admin_authorization_header()],
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["email_addresses"] == ["service@example.com"]
    assert sorted(json_resp["phone_numbers"]) == sorted(
        ["+18005555555", "+12028675309"]
    )


def test_get_guest_list_404s_with_unknown_service_id(client):
    path = "service/{}/guest-list".format(uuid.uuid4())

    response = client.get(path, headers=[create_admin_authorization_header()])
    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_get_guest_list_returns_no_data(client, sample_service):
    path = "service/{}/guest-list".format(sample_service.id)

    response = client.get(path, headers=[create_admin_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {
        "email_addresses": [],
        "phone_numbers": [],
    }


def test_update_guest_list_replaces_old_guest_list(client, sample_service_guest_list):
    data = {"email_addresses": ["foo@bar.com"], "phone_numbers": ["2028765309"]}

    response = client.put(
        f"service/{sample_service_guest_list.service_id}/guest-list",
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )

    assert response.status_code == 204
    guest_list = (
        db.session.execute(select(ServiceGuestList))
        .order_by(ServiceGuestList.recipient)
        .scalars()
        .all()
    )
    assert len(guest_list) == 2
    assert guest_list[0].recipient == "+12028765309"
    assert guest_list[1].recipient == "foo@bar.com"


def test_update_guest_list_doesnt_remove_old_guest_list_if_error(
    client, sample_service_guest_list
):
    data = {"email_addresses": [""], "phone_numbers": ["2028675309"]}

    response = client.put(
        "service/{}/guest-list".format(sample_service_guest_list.service_id),
        data=json.dumps(data),
        headers=[
            ("Content-Type", "application/json"),
            create_admin_authorization_header(),
        ],
    )

    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True)) == {
        "result": "error",
        "message": 'Invalid guest list: "" is not a valid email address or phone number',
    }
    guest_list = db.session.execute(select(ServiceGuestList)).scalars().one()
    assert guest_list.id == sample_service_guest_list.id
