from base64 import b64decode

import pytest

from notifications_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
    ZendeskClient,
    ZendeskError,
)


@pytest.fixture(scope="function")
def zendesk_client(app):
    client = ZendeskClient()

    app.config["ZENDESK_API_KEY"] = "testkey"

    client.init_app(app)

    return client


def test_zendesk_client_send_ticket_to_zendesk(zendesk_client, app, mocker, rmock):
    rmock.request(
        "POST",
        ZendeskClient.ZENDESK_TICKET_URL,
        status_code=201,
        json={
            "ticket": {
                "id": 12345,
                "subject": "Something is wrong",
            }
        },
    )
    mock_logger = mocker.patch.object(app.logger, "info")

    ticket = NotifySupportTicket("subject", "message", "incident")
    zendesk_client.send_ticket_to_zendesk(ticket)

    assert rmock.last_request.headers["Authorization"][:6] == "Basic "
    b64_auth = rmock.last_request.headers["Authorization"][6:]
    assert (
        b64decode(b64_auth.encode()).decode()
        == "zd-api-notify@digital.cabinet-office.gov.uk/token:testkey"
    )
    assert rmock.last_request.json() == ticket.request_data
    mock_logger.assert_called_once_with("Zendesk create ticket 12345 succeeded")


def test_zendesk_client_send_ticket_to_zendesk_error(
    zendesk_client, app, mocker, rmock
):
    rmock.request(
        "POST", ZendeskClient.ZENDESK_TICKET_URL, status_code=401, json={"foo": "bar"}
    )

    mock_logger = mocker.patch.object(app.logger, "error")

    ticket = NotifySupportTicket("subject", "message", "incident")

    with pytest.raises(ZendeskError):
        zendesk_client.send_ticket_to_zendesk(ticket)

    mock_logger.assert_called_with(
        "Zendesk create ticket request failed with 401 '{'foo': 'bar'}'"
    )


@pytest.mark.parametrize(
    "p1_arg, expected_tags, expected_priority",
    (
        (
            {},
            ["govuk_notify_support"],
            "normal",
        ),
        (
            {
                "p1": False,
            },
            ["govuk_notify_support"],
            "normal",
        ),
        (
            {
                "p1": True,
            },
            ["govuk_notify_emergency"],
            "urgent",
        ),
    ),
)
def test_notify_support_ticket_request_data(p1_arg, expected_tags, expected_priority):
    notify_ticket_form = NotifySupportTicket("subject", "message", "question", **p1_arg)

    assert notify_ticket_form.request_data == {
        "ticket": {
            "subject": "subject",
            "comment": {
                "body": "message",
                "public": True,
            },
            "group_id": NotifySupportTicket.NOTIFY_GROUP_ID,
            "organization_id": NotifySupportTicket.NOTIFY_ORG_ID,
            "ticket_form_id": NotifySupportTicket.NOTIFY_TICKET_FORM_ID,
            "priority": expected_priority,
            "tags": expected_tags,
            "type": "question",
            "custom_fields": [
                {"id": "1900000744994", "value": "notify_ticket_type_non_technical"},
                {"id": "360022836500", "value": []},
                {"id": "360022943959", "value": None},
                {"id": "360022943979", "value": None},
                {"id": "1900000745014", "value": None},
            ],
        }
    }


def test_notify_support_ticket_request_data_with_message_hidden_from_requester():
    notify_ticket_form = NotifySupportTicket(
        "subject", "message", "problem", requester_sees_message_content=False
    )

    assert notify_ticket_form.request_data["ticket"]["comment"]["public"] is False


@pytest.mark.parametrize(
    "name, zendesk_name", [("Name", "Name"), (None, "(no name supplied)")]
)
def test_notify_support_ticket_request_data_with_user_name_and_email(
    name, zendesk_name
):
    notify_ticket_form = NotifySupportTicket(
        "subject", "message", "question", user_name=name, user_email="user@example.com"
    )

    assert (
        notify_ticket_form.request_data["ticket"]["requester"]["email"]
        == "user@example.com"
    )
    assert (
        notify_ticket_form.request_data["ticket"]["requester"]["name"] == zendesk_name
    )


@pytest.mark.parametrize(
    "custom_fields, tech_ticket_tag, categories, org_id, org_type, service_id",
    [
        (
            {"technical_ticket": True},
            "notify_ticket_type_technical",
            [],
            None,
            None,
            None,
        ),
        (
            {"technical_ticket": False},
            "notify_ticket_type_non_technical",
            [],
            None,
            None,
            None,
        ),
        (
            {"ticket_categories": ["notify_billing", "notify_bug"]},
            "notify_ticket_type_non_technical",
            ["notify_billing", "notify_bug"],
            None,
            None,
            None,
        ),
        (
            {"org_id": "1234", "org_type": "local"},
            "notify_ticket_type_non_technical",
            [],
            "1234",
            "notify_org_type_local",
            None,
        ),
        (
            {"service_id": "abcd", "org_type": "nhs"},
            "notify_ticket_type_non_technical",
            [],
            None,
            "notify_org_type_nhs",
            "abcd",
        ),
    ],
)
def test_notify_support_ticket_request_data_custom_fields(
    custom_fields,
    tech_ticket_tag,
    categories,
    org_id,
    org_type,
    service_id,
):
    notify_ticket_form = NotifySupportTicket(
        "subject", "message", "question", **custom_fields
    )

    assert notify_ticket_form.request_data["ticket"]["custom_fields"] == [
        {"id": "1900000744994", "value": tech_ticket_tag},
        {"id": "360022836500", "value": categories},
        {"id": "360022943959", "value": org_id},
        {"id": "360022943979", "value": org_type},
        {"id": "1900000745014", "value": service_id},
    ]


def test_notify_support_ticket_request_data_email_ccs():
    notify_ticket_form = NotifySupportTicket(
        "subject", "message", "question", email_ccs=["someone@example.com"]
    )

    assert notify_ticket_form.request_data["ticket"]["email_ccs"] == [
        {"user_email": "someone@example.com", "action": "put"},
    ]
