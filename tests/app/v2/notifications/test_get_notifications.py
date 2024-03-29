import pytest
from flask import json, url_for

from app.enums import NotificationStatus, NotificationType, TemplateType
from app.utils import DATETIME_FORMAT
from tests import create_service_authorization_header
from tests.app.db import create_notification, create_template


@pytest.mark.parametrize(
    "billable_units, provider", [(1, "sns"), (0, "sns"), (1, None)]
)
def test_get_notification_by_id_returns_200(
    client, billable_units, provider, sample_template, mocker
):
    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {}

    sample_notification = create_notification(
        template=sample_template,
        billable_units=billable_units,
        sent_by=provider,
    )

    # another
    create_notification(
        template=sample_template,
        billable_units=billable_units,
        sent_by=provider,
    )

    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )
    response = client.get(
        path="/v2/notifications/{}".format(sample_notification.id),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))

    expected_template_response = {
        "id": "{}".format(sample_notification.serialize()["template"]["id"]),
        "version": sample_notification.serialize()["template"]["version"],
        "uri": sample_notification.serialize()["template"]["uri"],
    }

    expected_response = {
        "id": "{}".format(sample_notification.id),
        "reference": None,
        "email_address": None,
        "phone_number": "{}".format(sample_notification.to),
        "line_1": None,
        "line_2": None,
        "line_3": None,
        "line_4": None,
        "line_5": None,
        "line_6": None,
        "postcode": None,
        "type": "{}".format(sample_notification.notification_type),
        "status": "{}".format(sample_notification.status),
        "template": expected_template_response,
        "created_at": sample_notification.created_at.strftime(DATETIME_FORMAT),
        "created_by_name": None,
        "body": sample_notification.template.content,
        "subject": None,
        "sent_at": sample_notification.sent_at,
        "completed_at": sample_notification.completed_at(),
        "scheduled_for": None,
        "provider_response": None,
        "carrier": None,
    }

    assert json_response == expected_response


def test_get_notification_by_id_with_placeholders_returns_200(
    client, sample_email_template_with_placeholders, mocker
):
    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {"name": "Bob"}

    sample_notification = create_notification(
        template=sample_email_template_with_placeholders,
        personalisation={"name": "Bob"},
    )

    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )
    response = client.get(
        path="/v2/notifications/{}".format(sample_notification.id),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))

    expected_template_response = {
        "id": "{}".format(sample_notification.serialize()["template"]["id"]),
        "version": sample_notification.serialize()["template"]["version"],
        "uri": sample_notification.serialize()["template"]["uri"],
    }

    expected_response = {
        "id": "{}".format(sample_notification.id),
        "reference": None,
        "email_address": "{}".format(sample_notification.to),
        "phone_number": None,
        "line_1": None,
        "line_2": None,
        "line_3": None,
        "line_4": None,
        "line_5": None,
        "line_6": None,
        "postcode": None,
        "type": "{}".format(sample_notification.notification_type),
        "status": "{}".format(sample_notification.status),
        "template": expected_template_response,
        "created_at": sample_notification.created_at.strftime(DATETIME_FORMAT),
        "created_by_name": None,
        "body": "Hello Bob\nThis is an email from GOV.UK",
        "subject": "Bob",
        "sent_at": sample_notification.sent_at,
        "completed_at": sample_notification.completed_at(),
        "scheduled_for": None,
        "provider_response": None,
        "carrier": None,
    }

    assert json_response == expected_response


def test_get_notification_by_reference_returns_200(client, sample_template, mocker):
    sample_notification_with_reference = create_notification(
        template=sample_template, client_reference="some-client-reference"
    )

    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {}

    auth_header = create_service_authorization_header(
        service_id=sample_notification_with_reference.service_id
    )
    response = client.get(
        path="/v2/notifications?reference={}".format(
            sample_notification_with_reference.client_reference
        ),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(
        sample_notification_with_reference.id
    )
    assert json_response["notifications"][0]["reference"] == "some-client-reference"


def test_get_notification_by_id_returns_created_by_name_if_notification_created_by_id(
    client, sample_user, sample_template, mocker
):
    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {"name": "Bob"}

    sms_notification = create_notification(template=sample_template)
    sms_notification.created_by_id = sample_user.id

    auth_header = create_service_authorization_header(
        service_id=sms_notification.service_id
    )
    response = client.get(
        path=url_for(
            "v2_notifications.get_notification_by_id",
            notification_id=sms_notification.id,
        ),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = response.get_json()
    assert json_response["created_by_name"] == "Test User"


def test_get_notification_by_reference_nonexistent_reference_returns_no_notifications(
    client, sample_service
):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    response = client.get(
        path="/v2/notifications?reference={}".format("nonexistent-reference"),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert len(json_response["notifications"]) == 0


def test_get_notification_by_id_nonexistent_id(client, sample_notification):
    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )
    response = client.get(
        path="/v2/notifications/dd4b8b9d-d414-4a83-9256-580046bf18f9",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 404
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))
    assert json_response == {
        "errors": [{"error": "NoResultFound", "message": "No result found"}],
        "status_code": 404,
    }


@pytest.mark.parametrize("id", ["1234-badly-formatted-id-7890", "0"])
def test_get_notification_by_id_invalid_id(client, sample_notification, id):
    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )
    response = client.get(
        path="/v2/notifications/{}".format(id),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 400
    assert response.headers["Content-type"] == "application/json"

    json_response = json.loads(response.get_data(as_text=True))
    assert json_response == {
        "errors": [
            {
                "error": "ValidationError",
                "message": "notification_id is not a valid UUID",
            }
        ],
        "status_code": 400,
    }


@pytest.mark.parametrize("template_type", [TemplateType.SMS, TemplateType.EMAIL])
def test_get_notification_doesnt_have_delivery_estimate_for_non_letters(
    client, sample_service, template_type, mocker
):
    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {"name": "Bob"}

    template = create_template(service=sample_service, template_type=template_type)
    mocked_notification = create_notification(template=template)

    auth_header = create_service_authorization_header(
        service_id=mocked_notification.service_id
    )
    response = client.get(
        path="/v2/notifications/{}".format(mocked_notification.id),
        headers=[("Content-Type", "application/json"), auth_header],
    )
    assert response.status_code == 200
    assert "estimated_delivery" not in json.loads(response.get_data(as_text=True))


def test_get_all_notifications_except_job_notifications_returns_200(
    client, sample_template, sample_job
):
    create_notification(
        template=sample_template, job=sample_job
    )  # should not return this job notification
    notifications = [create_notification(template=sample_template) for _ in range(2)]
    notification = notifications[-1]

    auth_header = create_service_authorization_header(
        service_id=notification.service_id
    )
    response = client.get(
        path="/v2/notifications",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith("/v2/notifications")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 2

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == NotificationStatus.CREATED
    assert json_response["notifications"][0]["template"] == {
        "id": str(notification.template.id),
        "uri": notification.template.get_link(),
        "version": 1,
    }
    assert json_response["notifications"][0]["phone_number"] == "1"
    assert json_response["notifications"][0]["type"] == NotificationType.SMS
    assert not json_response["notifications"][0]["scheduled_for"]


def test_get_all_notifications_with_include_jobs_arg_returns_200(
    client, sample_template, sample_job, mocker
):
    mock_s3_personalisation = mocker.patch(
        "app.v2.notifications.get_notifications.get_personalisation_from_s3"
    )
    mock_s3_personalisation.return_value = {}

    notifications = [
        create_notification(template=sample_template, job=sample_job),
        create_notification(template=sample_template),
    ]
    notification = notifications[-1]

    auth_header = create_service_authorization_header(
        service_id=notification.service_id
    )
    response = client.get(
        path="/v2/notifications?include_jobs=true",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert json_response["links"]["current"].endswith(
        "/v2/notifications?include_jobs=true"
    )
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 2

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == notification.status
    assert "1" == notification.to
    assert (
        json_response["notifications"][0]["type"] == notification.template.template_type
    )
    assert not json_response["notifications"][0]["scheduled_for"]


def test_get_all_notifications_no_notifications_if_no_notifications(
    client, sample_service
):
    auth_header = create_service_authorization_header(service_id=sample_service.id)
    response = client.get(
        path="/v2/notifications",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith("/v2/notifications")
    assert "next" not in json_response["links"].keys()
    assert len(json_response["notifications"]) == 0


def test_get_all_notifications_filter_by_template_type(client, sample_service):
    email_template = create_template(
        service=sample_service, template_type=TemplateType.EMAIL
    )
    sms_template = create_template(
        service=sample_service, template_type=TemplateType.SMS
    )

    notification = create_notification(
        template=email_template, to_field="don.draper@scdp.biz"
    )
    create_notification(template=sms_template)

    auth_header = create_service_authorization_header(
        service_id=notification.service_id
    )
    response = client.get(
        path="/v2/notifications?template_type=email",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith(
        "/v2/notifications?template_type=email"
    )
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == NotificationStatus.CREATED
    assert json_response["notifications"][0]["template"] == {
        "id": str(email_template.id),
        "uri": notification.template.get_link(),
        "version": 1,
    }
    assert json_response["notifications"][0]["email_address"] == "1"
    assert json_response["notifications"][0]["type"] == NotificationType.EMAIL


def test_get_all_notifications_filter_by_template_type_invalid_template_type(
    client, sample_notification
):
    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )
    response = client.get(
        path="/v2/notifications?template_type=orange",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 400
    assert response.headers["Content-type"] == "application/json"

    assert json_response["status_code"] == 400
    assert len(json_response["errors"]) == 1
    type_str = ", ".join(
        [f"<{type(e).__name__}.{e.name}: {e.value}>" for e in TemplateType]
    )
    assert (
        json_response["errors"][0]["message"]
        == f"template_type orange is not one of [{type_str}]"
    )


def test_get_all_notifications_filter_by_single_status(client, sample_template):
    notification = create_notification(
        template=sample_template,
        status=NotificationStatus.PENDING,
    )
    create_notification(template=sample_template)

    auth_header = create_service_authorization_header(
        service_id=notification.service_id
    )
    response = client.get(
        path="/v2/notifications?status=pending",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith(
        "/v2/notifications?status=pending"
    )
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == NotificationStatus.PENDING


def test_get_all_notifications_filter_by_status_invalid_status(
    client, sample_notification
):
    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )
    response = client.get(
        path="/v2/notifications?status=elephant",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 400
    assert response.headers["Content-type"] == "application/json"

    assert json_response["status_code"] == 400
    assert len(json_response["errors"]) == 1
    type_str = ", ".join(
        [f"<{type(e).__name__}.{e.name}: {e.value}>" for e in NotificationStatus]
    )
    assert (
        json_response["errors"][0]["message"]
        == f"status elephant is not one of [{type_str}]"
    )


def test_get_all_notifications_filter_by_multiple_statuses(client, sample_template):
    notifications = [
        create_notification(template=sample_template, status=_status)
        for _status in [
            NotificationStatus.CREATED,
            NotificationStatus.PENDING,
            NotificationStatus.SENDING,
        ]
    ]
    failed_notification = create_notification(
        template=sample_template,
        status=NotificationStatus.PERMANENT_FAILURE,
    )

    auth_header = create_service_authorization_header(
        service_id=notifications[0].service_id
    )
    response = client.get(
        path="/v2/notifications?status=created&status=pending&status=sending",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith(
        "/v2/notifications?status=created&status=pending&status=sending"
    )
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 3

    returned_notification_ids = [_n["id"] for _n in json_response["notifications"]]
    for _id in [_notification.id for _notification in notifications]:
        assert str(_id) in returned_notification_ids

    assert failed_notification.id not in returned_notification_ids


def test_get_all_notifications_filter_by_failed_status(client, sample_template):
    created_notification = create_notification(
        template=sample_template,
        status=NotificationStatus.CREATED,
    )
    failed_notifications = [
        create_notification(template=sample_template, status=NotificationStatus.FAILED)
    ]
    auth_header = create_service_authorization_header(
        service_id=created_notification.service_id
    )
    response = client.get(
        path="/v2/notifications?status=failed",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith("/v2/notifications?status=failed")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    returned_notification_ids = [n["id"] for n in json_response["notifications"]]
    for _id in [_notification.id for _notification in failed_notifications]:
        assert str(_id) in returned_notification_ids

    assert created_notification.id not in returned_notification_ids


def test_get_all_notifications_filter_by_id(client, sample_template):
    older_notification = create_notification(template=sample_template)
    newer_notification = create_notification(template=sample_template)

    auth_header = create_service_authorization_header(
        service_id=newer_notification.service_id
    )
    response = client.get(
        path="/v2/notifications?older_than={}".format(newer_notification.id),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith(
        "/v2/notifications?older_than={}".format(newer_notification.id)
    )
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(older_notification.id)


def test_get_all_notifications_filter_by_id_invalid_id(client, sample_notification):
    auth_header = create_service_authorization_header(
        service_id=sample_notification.service_id
    )
    response = client.get(
        path="/v2/notifications?older_than=1234-badly-formatted-id-7890",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response["status_code"] == 400
    assert len(json_response["errors"]) == 1
    assert json_response["errors"][0]["message"] == "older_than is not a valid UUID"


def test_get_all_notifications_filter_by_id_no_notifications_if_nonexistent_id(
    client, sample_template
):
    notification = create_notification(template=sample_template)

    auth_header = create_service_authorization_header(
        service_id=notification.service_id
    )
    response = client.get(
        path="/v2/notifications?older_than=dd4b8b9d-d414-4a83-9256-580046bf18f9",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith(
        "/v2/notifications?older_than=dd4b8b9d-d414-4a83-9256-580046bf18f9"
    )
    assert "next" not in json_response["links"].keys()
    assert len(json_response["notifications"]) == 0


def test_get_all_notifications_filter_by_id_no_notifications_if_last_notification(
    client, sample_template
):
    notification = create_notification(template=sample_template)

    auth_header = create_service_authorization_header(
        service_id=notification.service_id
    )
    response = client.get(
        path="/v2/notifications?older_than={}".format(notification.id),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    assert json_response["links"]["current"].endswith(
        "/v2/notifications?older_than={}".format(notification.id)
    )
    assert "next" not in json_response["links"].keys()
    assert len(json_response["notifications"]) == 0


def test_get_all_notifications_filter_multiple_query_parameters(
    client, sample_email_template
):
    # TODO had to change pending to sending.  Is that correct?
    # this is the notification we are looking for
    older_notification = create_notification(
        template=sample_email_template,
        status=NotificationStatus.SENDING,
    )

    # wrong status
    create_notification(template=sample_email_template)
    wrong_template = create_template(
        sample_email_template.service, template_type=TemplateType.SMS
    )
    # wrong template
    create_notification(template=wrong_template, status=NotificationStatus.SENDING)

    # we only want notifications created before this one
    newer_notification = create_notification(template=sample_email_template)

    # this notification was created too recently
    create_notification(
        template=sample_email_template,
        status=NotificationStatus.SENDING,
    )

    auth_header = create_service_authorization_header(
        service_id=newer_notification.service_id
    )
    response = client.get(
        path="/v2/notifications?status=sending&template_type=email&older_than={}".format(
            newer_notification.id
        ),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers["Content-type"] == "application/json"
    # query parameters aren't returned in order
    for url_part in [
        "/v2/notifications?",
        "template_type=email",
        "status=sending",
        "older_than={}".format(newer_notification.id),
    ]:
        assert url_part in json_response["links"]["current"]

    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(older_notification.id)


def test_get_all_notifications_renames_letter_statuses(
    client,
    sample_notification,
    sample_email_notification,
):
    auth_header = create_service_authorization_header(
        service_id=sample_email_notification.service_id
    )
    response = client.get(
        path=url_for("v2_notifications.get_notifications"),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    json_response = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200

    for noti in json_response["notifications"]:
        if (
            noti["type"] == NotificationType.SMS
            or noti["type"] == NotificationType.EMAIL
        ):
            assert noti["status"] == NotificationStatus.CREATED
        else:
            pytest.fail()
