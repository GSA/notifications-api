import json
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import ANY
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.exc import SQLAlchemyError

import app.celery.tasks
from app import db
from app.dao.templates_dao import dao_update_template
from app.enums import (
    JobStatus,
    KeyType,
    NotificationStatus,
    NotificationType,
    TemplateType,
)
from app.utils import utc_now
from tests import create_admin_authorization_header
from tests.app.db import (
    create_ft_notification_status,
    create_job,
    create_notification,
    create_service,
    create_template,
)
from tests.conftest import set_config


def test_get_job_with_invalid_service_id_returns404(client, sample_service):
    path = f"/service/{sample_service.id}/job"
    auth_header = create_admin_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json["data"]) == 0


def test_get_job_with_invalid_job_id_returns404(client, sample_template):
    service_id = sample_template.service.id
    path = f"/service/{service_id}/job/{'bad-id'}"
    auth_header = create_admin_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 404
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["result"] == "error"
    assert resp_json["message"] == "No result found"


def test_get_job_with_unknown_id_returns404(client, sample_template, fake_uuid):
    service_id = sample_template.service.id
    path = f"/service/{service_id}/job/{fake_uuid}"
    auth_header = create_admin_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 404
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json == {"message": "No result found", "result": "error"}


def test_cancel_job(client, sample_scheduled_job):
    job_id = str(sample_scheduled_job.id)
    service_id = sample_scheduled_job.service.id
    path = f"/service/{service_id}/job/{job_id}/cancel"
    auth_header = create_admin_authorization_header()
    response = client.post(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["data"]["id"] == job_id
    assert resp_json["data"]["job_status"] == JobStatus.CANCELLED


uuid_str_strategy = st.one_of(
    st.just(str(uuid.uuid4())), st.text(min_size=1, max_size=36)
)


@pytest.mark.usefixtures("client", "sample_scheduled_job")
@settings(max_examples=10)
@given(fuzzed_job_id=uuid_str_strategy, fuzzed_service_id=uuid_str_strategy)
def test_fuzz_cancel_job(fuzzed_job_id, fuzzed_service_id, request):
    client = request.getfixturevalue("client")
    sample_scheduled_job = request.getfixturevalue("sample_scheduled_job")
    valid_job_id = str(sample_scheduled_job.id)
    valid_service_id = str(sample_scheduled_job.service.id)
    job_id = fuzzed_job_id
    service_id = fuzzed_service_id

    path = f"/service/{service_id}/job/{job_id}/cancel"
    auth_header = create_admin_authorization_header()
    try:
        response = client.post(path, headers=[auth_header])
    except SQLAlchemyError:
        db.session.rollback()
        raise

    status = response.status_code
    # 400 Bad Request, 403 Forbidden, 404 Not Found
    # 405 Method Not Allowed (if ids are not ascii)
    assert status in (
        200,
        400,
        403,
        404,
        405,
    ), f"Unexpected status: {status} for path: {path}"
    # This will only happen once every trillion years
    if status == 200:
        assert job_id == valid_job_id
        assert service_id == valid_service_id
        resp_json = json.loads(response.get_data(as_text=True))
        assert resp_json["data"]["id"] == valid_job_id
        assert resp_json["data"]["job_status"] == JobStatus.CANCELLED


def test_cant_cancel_normal_job(client, sample_job, mocker):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    mock_update = mocker.patch("app.dao.jobs_dao.dao_update_job")
    path = f"/service/{service_id}/job/{job_id}/cancel"
    auth_header = create_admin_authorization_header()
    response = client.post(path, headers=[auth_header])
    assert response.status_code == 404
    assert mock_update.call_count == 0


def test_create_unscheduled_job(client, sample_template, mocker, fake_uuid):
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
            "original_file_name": "thisisatest.csv",
            "notification_count": "1",
            "valid": "True",
        },
    )
    data = {
        "id": fake_uuid,
        "created_by": str(sample_template.created_by.id),
    }
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_called_once_with(
        ([str(fake_uuid)]), {"sender_id": None}, queue="job-tasks"
    )

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json["data"]["id"] == fake_uuid
    assert resp_json["data"]["statistics"] == []
    assert resp_json["data"]["job_status"] == JobStatus.PENDING
    assert not resp_json["data"]["scheduled_for"]
    assert resp_json["data"]["job_status"] == JobStatus.PENDING
    assert resp_json["data"]["template"] == str(sample_template.id)
    assert resp_json["data"]["original_file_name"] == "thisisatest.csv"
    assert resp_json["data"]["notification_count"] == 1


def test_create_unscheduled_job_with_sender_id_in_metadata(
    client, sample_template, mocker, fake_uuid
):
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
            "original_file_name": "thisisatest.csv",
            "notification_count": "1",
            "valid": "True",
            "sender_id": fake_uuid,
        },
    )
    data = {
        "id": fake_uuid,
        "created_by": str(sample_template.created_by.id),
    }
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_called_once_with(
        ([str(fake_uuid)]),
        {"sender_id": fake_uuid},
        queue="job-tasks",
    )


@freeze_time("2016-01-01 12:00:00.000000")
def test_create_scheduled_job(client, sample_template, mocker, fake_uuid):
    scheduled_date = (utc_now() + timedelta(hours=95, minutes=59)).isoformat()
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
            "original_file_name": "thisisatest.csv",
            "notification_count": "1",
            "valid": "True",
        },
    )
    data = {
        "id": fake_uuid,
        "created_by": str(sample_template.created_by.id),
        "scheduled_for": scheduled_date,
    }
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_not_called()

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json["data"]["id"] == fake_uuid
    assert (
        resp_json["data"]["scheduled_for"]
        == datetime(2016, 1, 5, 11, 59, 0, tzinfo=ZoneInfo("UTC")).isoformat()
    )
    assert resp_json["data"]["job_status"] == JobStatus.SCHEDULED
    assert resp_json["data"]["template"] == str(sample_template.id)
    assert resp_json["data"]["original_file_name"] == "thisisatest.csv"
    assert resp_json["data"]["notification_count"] == 1


def test_create_job_returns_403_if_service_is_not_active(
    client, fake_uuid, sample_service, mocker
):
    sample_service.active = False
    mock_job_dao = mocker.patch("app.dao.jobs_dao.dao_create_job")
    auth_header = create_admin_authorization_header()
    response = client.post(
        f"/service/{sample_service.id}/job",
        data="",
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 403
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["result"] == "error"
    assert resp_json["message"] == "Create job is not allowed: service is inactive "
    mock_job_dao.assert_not_called()


@pytest.mark.parametrize(
    "extra_metadata",
    (
        {},
        {"valid": "anything not the string True"},
    ),
)
def test_create_job_returns_400_if_file_is_invalid(
    client,
    fake_uuid,
    sample_template,
    mocker,
    extra_metadata,
):
    mock_job_dao = mocker.patch("app.dao.jobs_dao.dao_create_job")
    auth_header = create_admin_authorization_header()
    metadata = dict(
        template_id=str(sample_template.id),
        original_file_name="thisisatest.csv",
        notification_count=1,
        **extra_metadata,
    )
    mocker.patch("app.job.rest.get_job_metadata_from_s3", return_value=metadata)
    data = {"id": fake_uuid}
    response = client.post(
        f"/service/{sample_template.service.id}/job",
        data=json.dumps(data),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["result"] == "error"
    assert resp_json["message"] == "File is not valid, can't create job"
    mock_job_dao.assert_not_called()


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_create_scheduled_job_more_then_96_hours_in_the_future(
    client, sample_template, mocker, fake_uuid
):
    scheduled_date = (utc_now() + timedelta(hours=96, minutes=1)).isoformat()
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
            "original_file_name": "thisisatest.csv",
            "notification_count": "1",
            "valid": "True",
        },
    )
    data = {
        "id": fake_uuid,
        "created_by": str(sample_template.created_by.id),
        "scheduled_for": scheduled_date,
    }
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()

    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["result"] == "error"
    assert "scheduled_for" in resp_json["message"]
    assert resp_json["message"]["scheduled_for"] == [
        "Date cannot be more than 96hrs in the future"
    ]


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_create_scheduled_job_in_the_past(
    client, sample_template, mocker, fake_uuid
):
    scheduled_date = (utc_now() - timedelta(minutes=1)).isoformat()
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
            "original_file_name": "thisisatest.csv",
            "notification_count": "1",
            "valid": "True",
        },
    )
    data = {
        "id": fake_uuid,
        "created_by": str(sample_template.created_by.id),
        "scheduled_for": scheduled_date,
    }
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]

    response = client.post(path, data=json.dumps(data), headers=headers)
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()

    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["result"] == "error"
    assert "scheduled_for" in resp_json["message"]
    assert resp_json["message"]["scheduled_for"] == ["Date cannot be in the past"]


def test_create_job_returns_400_if_missing_id(client, sample_template, mocker):
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
        },
    )
    data = {}
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]
    response = client.post(path, data=json.dumps(data), headers=headers)

    resp_json = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()
    assert resp_json["result"] == "error"
    assert "Missing data for required field." in resp_json["message"]["id"]


def test_create_job_returns_400_if_missing_data(
    client, sample_template, mocker, fake_uuid
):
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
        },
    )
    data = {
        "id": fake_uuid,
        "valid": "True",
    }
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]
    response = client.post(path, data=json.dumps(data), headers=headers)

    resp_json = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()
    assert resp_json["result"] == "error"
    assert (
        "Missing data for required field." in resp_json["message"]["original_file_name"]
    )
    assert (
        "Missing data for required field." in resp_json["message"]["notification_count"]
    )


def test_create_job_returns_404_if_template_does_not_exist(
    client, sample_service, mocker, fake_uuid
):
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_service.id),
        },
    )
    data = {
        "id": fake_uuid,
    }
    path = f"/service/{sample_service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]
    response = client.post(path, data=json.dumps(data), headers=headers)

    resp_json = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404

    app.celery.tasks.process_job.apply_async.assert_not_called()
    assert resp_json["result"] == "error"
    assert resp_json["message"] == "No result found"


def test_create_job_returns_404_if_missing_service(client, sample_template, mocker):
    mocker.patch("app.celery.tasks.process_job.apply_async")
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
        },
    )
    random_id = str(uuid.uuid4())
    data = {}
    path = f"/service/{random_id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]
    response = client.post(path, data=json.dumps(data), headers=headers)

    resp_json = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404

    app.celery.tasks.process_job.apply_async.assert_not_called()
    assert resp_json["result"] == "error"
    assert resp_json["message"] == "No result found"


def test_create_job_returns_400_if_archived_template(
    client, sample_template, mocker, fake_uuid
):
    mocker.patch("app.celery.tasks.process_job.apply_async")
    sample_template.archived = True
    dao_update_template(sample_template)
    mocker.patch(
        "app.job.rest.get_job_metadata_from_s3",
        return_value={
            "template_id": str(sample_template.id),
        },
    )
    data = {
        "id": fake_uuid,
        "valid": "True",
    }
    path = f"/service/{sample_template.service.id}/job"
    auth_header = create_admin_authorization_header()
    headers = [("Content-Type", "application/json"), auth_header]
    response = client.post(path, data=json.dumps(data), headers=headers)

    resp_json = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()
    assert resp_json["result"] == "error"
    assert "Template has been deleted" in resp_json["message"]["template"]


def _setup_jobs(template, number_of_jobs=5):
    for _ in range(number_of_jobs):
        create_job(template=template)


def test_get_all_notifications_for_job_in_order_of_job_number(
    admin_request, sample_template, mocker
):

    mock_job = mocker.patch("app.job.rest.get_job_from_s3")
    mock_job.return_value = None
    mock_s3 = mocker.patch("app.job.rest.extract_phones")
    mock_s3.return_value = {
        0: "15555555555",
        1: "15555555555",
        2: "15555555555",
        3: "15555555555",
    }
    mock_s3_personalisation = mocker.patch("app.job.rest.extract_personalisation")
    mock_s3_personalisation.return_value = {0: "", 1: "", 2: "", 3: ""}

    main_job = create_job(sample_template)
    another_job = create_job(sample_template)

    notification_1 = create_notification(job=main_job, to_field="1", job_row_number=1)
    notification_2 = create_notification(job=main_job, to_field="2", job_row_number=2)
    notification_3 = create_notification(job=main_job, to_field="3", job_row_number=3)
    create_notification(job=another_job)

    resp = admin_request.get(
        "job.get_all_notifications_for_service_job",
        service_id=main_job.service_id,
        job_id=main_job.id,
    )

    assert len(resp["notifications"]) == 3
    assert resp["notifications"][0]["to"] == notification_1.to
    assert resp["notifications"][0]["job_row_number"] == notification_1.job_row_number
    assert resp["notifications"][1]["to"] == notification_2.to
    assert resp["notifications"][1]["job_row_number"] == notification_2.job_row_number
    assert resp["notifications"][2]["to"] == notification_3.to
    assert resp["notifications"][2]["job_row_number"] == notification_3.job_row_number


def test_get_recent_notifications_for_job_in_reverse_order_of_job_number(
    admin_request, sample_template, mocker
):
    mock_s3 = mocker.patch("app.job.rest.get_phone_number_from_s3")
    mock_s3.return_value = "15555555555"

    mock_s3_personalisation = mocker.patch("app.job.rest.get_personalisation_from_s3")
    mock_s3_personalisation.return_value = {}

    main_job = create_job(sample_template)
    another_job = create_job(sample_template)

    count = 1
    for status in NotificationStatus:
        create_notification(job=main_job, job_row_number=str(count), status=status)
        count = count + 1
    create_notification(job=another_job)

    resp = admin_request.get(
        "job.get_recent_notifications_for_service_job",
        service_id=main_job.service_id,
        job_id=main_job.id,
    )

    assert len(resp["notifications"]) == 13
    assert resp["notifications"][0]["status"] == "virus-scan-failed"
    assert resp["notifications"][0]["job_row_number"] == 13

    query_string = {"status": "delivered"}
    resp = admin_request.get(
        "job.get_recent_notifications_for_service_job",
        service_id=main_job.service_id,
        job_id=main_job.id,
        **query_string,
    )

    assert len(resp["notifications"]) == 1

    assert resp["notifications"][0]["status"] == "delivered"
    assert resp["notifications"][0]["job_row_number"] == 5


@pytest.mark.parametrize(
    "expected_notification_count, status_args, expected_phones, expected_personalisation",
    [
        (1, [NotificationStatus.CREATED], {0: "15555555555"}, {0: ""}),
        (0, [NotificationStatus.SENDING], {}, {}),
        (
            1,
            [NotificationStatus.CREATED, NotificationStatus.SENDING],
            {0: "15555555555"},
            {0: ""},
        ),
        (0, [NotificationStatus.SENDING, NotificationStatus.DELIVERED], {}, {}),
    ],
)
def test_get_all_notifications_for_job_filtered_by_status(
    admin_request,
    sample_job,
    expected_notification_count,
    status_args,
    expected_phones,
    expected_personalisation,
    mocker,
):

    mock_job = mocker.patch("app.job.rest.get_job_from_s3")
    mock_job.return_value = None
    mock_s3 = mocker.patch("app.job.rest.extract_phones")
    mock_s3.return_value = expected_phones
    mock_s3_personalisation = mocker.patch("app.job.rest.extract_personalisation")
    mock_s3_personalisation.return_value = expected_personalisation

    create_notification(
        job=sample_job,
        job_row_number=0,
        to_field="1",
        status=NotificationStatus.CREATED,
    )

    resp = admin_request.get(
        "job.get_all_notifications_for_service_job",
        service_id=sample_job.service_id,
        job_id=sample_job.id,
        status=status_args,
    )
    assert len(resp["notifications"]) == expected_notification_count


def test_get_all_notifications_for_job_returns_correct_format(
    admin_request, sample_notification_with_job, mocker
):

    mock_job = mocker.patch("app.job.rest.get_job_from_s3")
    mock_job.return_value = None
    mock_s3 = mocker.patch("app.job.rest.extract_phones")
    mock_s3.return_value = {0: "15555555555"}
    mock_s3_personalisation = mocker.patch("app.job.rest.extract_personalisation")
    mock_s3_personalisation.return_value = {0: ""}
    sample_notification_with_job.job_row_number = 0

    service_id = sample_notification_with_job.service_id
    job_id = sample_notification_with_job.job_id

    resp = admin_request.get(
        "job.get_all_notifications_for_service_job",
        service_id=service_id,
        job_id=job_id,
    )

    assert len(resp["notifications"]) == 1
    assert resp["notifications"][0]["id"] == str(sample_notification_with_job.id)
    assert resp["notifications"][0]["status"] == sample_notification_with_job.status


def test_get_notification_count_for_job_id(admin_request, mocker, sample_job):
    mock_dao = mocker.patch(
        "app.job.rest.dao_get_notification_count_for_job_id", return_value=3
    )
    response = admin_request.get(
        "job.get_notification_count_for_job_id",
        service_id=sample_job.service_id,
        job_id=sample_job.id,
    )
    mock_dao.assert_called_once_with(job_id=str(sample_job.id))
    assert response["count"] == 3


def test_get_notification_count_for_job_id_for_wrong_service_id(
    admin_request, sample_job
):
    service_id = uuid.uuid4()
    response = admin_request.get(
        "job.get_notification_count_for_job_id",
        service_id=service_id,
        job_id=sample_job.id,
        _expected_status=404,
    )
    assert response["message"] == "No result found"


def test_get_notification_count_for_job_id_for_wrong_job_id(
    admin_request, sample_service
):
    job_id = uuid.uuid4()
    response = admin_request.get(
        "job.get_notification_count_for_job_id",
        service_id=sample_service.id,
        job_id=job_id,
        _expected_status=404,
    )
    assert response["message"] == "No result found"


def test_get_job_by_id(admin_request, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    resp_json = admin_request.get(
        "job.get_job_by_service_and_job_id", service_id=service_id, job_id=job_id
    )

    assert resp_json["data"]["id"] == job_id
    assert resp_json["data"]["statistics"] == []
    assert resp_json["data"]["created_by"]["name"] == "Test User"


def test_get_job_by_id_should_return_summed_statistics(admin_request, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    create_notification(job=sample_job, status=NotificationStatus.CREATED)
    create_notification(job=sample_job, status=NotificationStatus.CREATED)
    create_notification(job=sample_job, status=NotificationStatus.CREATED)
    create_notification(job=sample_job, status=NotificationStatus.SENDING)
    create_notification(job=sample_job, status=NotificationStatus.FAILED)
    create_notification(job=sample_job, status=NotificationStatus.FAILED)
    create_notification(job=sample_job, status=NotificationStatus.FAILED)
    create_notification(job=sample_job, status=NotificationStatus.TECHNICAL_FAILURE)
    create_notification(job=sample_job, status=NotificationStatus.TEMPORARY_FAILURE)
    create_notification(job=sample_job, status=NotificationStatus.TEMPORARY_FAILURE)

    resp_json = admin_request.get(
        "job.get_job_by_service_and_job_id",
        service_id=service_id,
        job_id=job_id,
    )

    assert resp_json["data"]["id"] == job_id
    assert {
        "status": NotificationStatus.CREATED,
        "count": 3,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.SENDING,
        "count": 1,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.FAILED,
        "count": 3,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.TECHNICAL_FAILURE,
        "count": 1,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.TEMPORARY_FAILURE,
        "count": 2,
    } in resp_json[
        "data"
    ]["statistics"]
    assert resp_json["data"]["created_by"]["name"] == "Test User"


def test_get_job_by_id_with_stats_for_old_job_where_notifications_have_been_purged(
    admin_request, sample_template
):
    old_job = create_job(
        sample_template,
        notification_count=10,
        created_at=utc_now() - timedelta(days=9),
        job_status=JobStatus.FINISHED,
    )

    def __create_ft_status(job, status, count):
        create_ft_notification_status(
            local_date=job.created_at.date(),
            notification_type=NotificationType.SMS,
            service=job.service,
            job=job,
            template=job.template,
            key_type=KeyType.NORMAL,
            notification_status=status,
            count=count,
        )

    __create_ft_status(old_job, NotificationStatus.CREATED, 3)
    __create_ft_status(old_job, NotificationStatus.SENDING, 1)
    __create_ft_status(old_job, NotificationStatus.FAILED, 3)
    __create_ft_status(old_job, NotificationStatus.TECHNICAL_FAILURE, 1)
    __create_ft_status(old_job, NotificationStatus.TEMPORARY_FAILURE, 2)

    resp_json = admin_request.get(
        "job.get_job_by_service_and_job_id",
        service_id=old_job.service_id,
        job_id=old_job.id,
    )

    assert resp_json["data"]["id"] == str(old_job.id)
    assert {
        "status": NotificationStatus.CREATED,
        "count": 3,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.SENDING,
        "count": 1,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.FAILED,
        "count": 3,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.TECHNICAL_FAILURE,
        "count": 1,
    } in resp_json[
        "data"
    ]["statistics"]
    assert {
        "status": NotificationStatus.TEMPORARY_FAILURE,
        "count": 2,
    } in resp_json[
        "data"
    ]["statistics"]
    assert resp_json["data"]["created_by"]["name"] == "Test User"


@freeze_time("2017-07-17 07:17")
def test_get_jobs(admin_request, sample_template):
    _setup_jobs(sample_template)

    service_id = sample_template.service.id

    resp_json = admin_request.get("job.get_jobs_by_service", service_id=service_id)
    assert len(resp_json["data"]) == 5
    assert resp_json["data"][0] == {
        "archived": False,
        "created_at": "2017-07-17T07:17:00+00:00",
        "created_by": {
            "id": ANY,
            "name": "Test User",
        },
        "id": ANY,
        "job_status": JobStatus.PENDING,
        "notification_count": 1,
        "original_file_name": "some.csv",
        "processing_finished": None,
        "processing_started": None,
        "scheduled_for": None,
        "service": str(sample_template.service.id),
        "service_name": {"name": sample_template.service.name},
        "statistics": [],
        "template": str(sample_template.id),
        "template_name": sample_template.name,
        "template_type": TemplateType.SMS,
        "template_version": 1,
        "updated_at": None,
    }


def test_get_jobs_with_limit_days(admin_request, sample_template):
    for time in [
        "Sunday 1st July 2018 22:59",
        "Sunday 2nd July 2018 23:00",  # beginning of monday morning
        "Monday 3rd July 2018 12:00",
    ]:
        with freeze_time(time):
            create_job(template=sample_template)

    with freeze_time("Monday 9th July 2018 12:00"):
        resp_json = admin_request.get(
            "job.get_jobs_by_service",
            service_id=sample_template.service_id,
            limit_days=7,
        )

    assert len(resp_json["data"]) == 2


def test_get_jobs_should_return_statistics(admin_request, sample_template):
    now = utc_now()
    earlier = utc_now() - timedelta(days=1)
    job_1 = create_job(sample_template, processing_started=earlier)
    job_2 = create_job(sample_template, processing_started=now)
    create_notification(job=job_1, status=NotificationStatus.CREATED)
    create_notification(job=job_1, status=NotificationStatus.CREATED)
    create_notification(job=job_1, status=NotificationStatus.CREATED)
    create_notification(job=job_2, status=NotificationStatus.SENDING)
    create_notification(job=job_2, status=NotificationStatus.SENDING)
    create_notification(job=job_2, status=NotificationStatus.SENDING)

    resp_json = admin_request.get(
        "job.get_jobs_by_service", service_id=sample_template.service_id
    )

    assert len(resp_json["data"]) == 2
    assert resp_json["data"][0]["id"] == str(job_2.id)
    assert {
        "status": NotificationStatus.SENDING,
        "count": 3,
    } in resp_json["data"][
        0
    ]["statistics"]
    assert resp_json["data"][1]["id"] == str(job_1.id)
    assert {
        "status": NotificationStatus.CREATED,
        "count": 3,
    } in resp_json["data"][
        1
    ]["statistics"]


def test_get_jobs_should_return_no_stats_if_no_rows_in_notifications(
    admin_request,
    sample_template,
):
    now = utc_now()
    earlier = utc_now() - timedelta(days=1)
    job_1 = create_job(sample_template, created_at=earlier)
    job_2 = create_job(sample_template, created_at=now)

    resp_json = admin_request.get(
        "job.get_jobs_by_service", service_id=sample_template.service_id
    )

    assert len(resp_json["data"]) == 2
    assert resp_json["data"][0]["id"] == str(job_2.id)
    assert resp_json["data"][0]["statistics"] == []
    assert resp_json["data"][1]["id"] == str(job_1.id)
    assert resp_json["data"][1]["statistics"] == []


def test_get_jobs_should_paginate(admin_request, sample_template):
    create_10_jobs(sample_template)

    with set_config(admin_request.app, "PAGE_SIZE", 2):
        resp_json = admin_request.get(
            "job.get_jobs_by_service", service_id=sample_template.service_id
        )

    assert resp_json["data"][0]["created_at"] == "2015-01-01T10:00:00+00:00"
    assert resp_json["data"][1]["created_at"] == "2015-01-01T09:00:00+00:00"
    assert resp_json["page_size"] == 2
    assert resp_json["total"] == 10
    assert "links" in resp_json
    assert set(resp_json["links"].keys()) == {"next", "last", "prev"}


def test_get_jobs_accepts_page_parameter(admin_request, sample_template):
    create_10_jobs(sample_template)

    with set_config(admin_request.app, "PAGE_SIZE", 2):
        resp_json = admin_request.get(
            "job.get_jobs_by_service", service_id=sample_template.service_id, page=2
        )

    assert resp_json["data"][0]["created_at"] == "2015-01-01T08:00:00+00:00"
    assert resp_json["data"][1]["created_at"] == "2015-01-01T07:00:00+00:00"
    assert resp_json["page_size"] == 2
    assert resp_json["total"] == 10
    assert "links" in resp_json
    assert set(resp_json["links"].keys()) == {"prev", "next", "last"}


@pytest.mark.parametrize(
    "statuses_filter, expected_statuses",
    [
        ("", list(JobStatus)),
        ("pending", [JobStatus.PENDING]),
        (
            "pending, in progress, finished, sending limits exceeded, scheduled, cancelled, ready to send, sent to dvla, error",  # noqa
            list(JobStatus),
        ),
        # bad statuses are accepted, just return no data
        ("foo", []),
    ],
)
def test_get_jobs_can_filter_on_statuses(
    admin_request, sample_template, statuses_filter, expected_statuses
):
    create_job(sample_template, job_status=JobStatus.PENDING)
    create_job(sample_template, job_status=JobStatus.IN_PROGRESS)
    create_job(sample_template, job_status=JobStatus.FINISHED)
    create_job(sample_template, job_status=JobStatus.SENDING_LIMITS_EXCEEDED)
    create_job(sample_template, job_status=JobStatus.SCHEDULED)
    create_job(sample_template, job_status=JobStatus.CANCELLED)
    create_job(sample_template, job_status=JobStatus.READY_TO_SEND)
    create_job(sample_template, job_status=JobStatus.SENT_TO_DVLA)
    create_job(sample_template, job_status=JobStatus.ERROR)

    resp_json = admin_request.get(
        "job.get_jobs_by_service",
        service_id=sample_template.service_id,
        statuses=statuses_filter,
    )

    assert {x["job_status"] for x in resp_json["data"]} == set(expected_statuses)


def create_10_jobs(template):
    with freeze_time("2015-01-01T00:00:00") as the_time:
        for _ in range(10):
            the_time.tick(timedelta(hours=1))
            create_job(template)


def test_get_all_notifications_for_job_returns_csv_format(
    admin_request, sample_notification_with_job, mocker
):
    mock_job = mocker.patch("app.job.rest.get_job_from_s3")
    mock_job.return_value = None
    mock_s3 = mocker.patch("app.job.rest.extract_phones")
    mock_s3.return_value = {0: "15555555555"}
    mock_s3_personalisation = mocker.patch("app.job.rest.extract_personalisation")
    mock_s3_personalisation.return_value = {0: ""}
    sample_notification_with_job.job_row_number = 0

    resp = admin_request.get(
        "job.get_all_notifications_for_service_job",
        service_id=sample_notification_with_job.service_id,
        job_id=sample_notification_with_job.job_id,
        format_for_csv=True,
    )
    assert len(resp["notifications"]) == 1
    assert set(resp["notifications"][0].keys()) == {
        "created_at",
        "created_by_name",
        "created_by_email_address",
        "template_type",
        "template_name",
        "job_name",
        "carrier",
        "provider_response",
        "status",
        "row_number",
        "recipient",
        "client_reference",
    }


@freeze_time("2017-06-10 00:00")
def test_get_jobs_should_retrieve_from_ft_notification_status_for_old_jobs(
    admin_request, sample_template
):
    # it's the 10th today, so 3 days should include all of 7th, 8th, 9th, and some of 10th.
    just_three_days_ago = datetime(2017, 6, 6, 23, 59, 59)
    not_quite_three_days_ago = just_three_days_ago + timedelta(seconds=1)

    job_1 = create_job(
        sample_template,
        created_at=just_three_days_ago,
        processing_started=just_three_days_ago,
    )
    job_2 = create_job(
        sample_template,
        created_at=just_three_days_ago,
        processing_started=not_quite_three_days_ago,
    )
    # is old but hasn't started yet (probably a scheduled job). We don't have any stats for this job yet.
    job_3 = create_job(
        sample_template, created_at=just_three_days_ago, processing_started=None
    )

    # some notifications created more than three days ago, some created after the midnight cutoff
    create_ft_notification_status(
        date(2017, 6, 6),
        job=job_1,
        notification_status=NotificationStatus.DELIVERED,
        count=2,
    )
    create_ft_notification_status(
        date(2017, 6, 7),
        job=job_1,
        notification_status=NotificationStatus.DELIVERED,
        count=4,
    )
    # job2's new enough
    create_notification(
        job=job_2,
        status=NotificationStatus.CREATED,
        created_at=not_quite_three_days_ago,
    )

    # this isn't picked up because the job is too new
    create_ft_notification_status(
        date(2017, 6, 7),
        job=job_2,
        notification_status=NotificationStatus.DELIVERED,
        count=8,
    )
    # this isn't picked up - while the job is old, it started in last 3 days so we look at notification table instead
    create_ft_notification_status(
        date(2017, 6, 7),
        job=job_3,
        notification_status=NotificationStatus.DELIVERED,
        count=16,
    )

    # this isn't picked up because we're using the ft status table for job_1 as it's old
    create_notification(
        job=job_1,
        status=NotificationStatus.CREATED,
        created_at=not_quite_three_days_ago,
    )

    resp_json = admin_request.get(
        "job.get_jobs_by_service",
        service_id=sample_template.service_id,
    )

    returned_jobs = resp_json["data"]

    expected_jobs = [job_3, job_2, job_1]
    expected_order = sorted(
        expected_jobs,
        key=lambda job: ((job.processing_started or job.created_at), str(job.id)),
        reverse=True,
    )
    expected_ids = [str(job.id) for job in expected_order]
    returned_ids = [job["id"] for job in returned_jobs if job["id"] in expected_ids]
    assert returned_ids == expected_ids

    for job in expected_jobs:
        idx = returned_ids.index(str(job.id))
        if job is job_3:
            assert returned_jobs[idx]["statistics"] == []
        elif job is job_2:
            assert returned_jobs[idx]["statistics"] == [
                {"status": NotificationStatus.CREATED, "count": 1},
            ]
        elif job is job_1:
            assert returned_jobs[idx]["statistics"] == [
                {"status": NotificationStatus.DELIVERED, "count": 6},
            ]


@freeze_time("2017-07-17 07:17")
def test_get_scheduled_job_stats_when_no_scheduled_jobs(admin_request, sample_template):
    # This sets up a bunch of regular, non-scheduled jobs
    _setup_jobs(sample_template)

    service_id = sample_template.service.id

    resp_json = admin_request.get("job.get_scheduled_job_stats", service_id=service_id)
    assert resp_json == {
        "count": 0,
        "soonest_scheduled_for": None,
    }


@freeze_time("2017-07-17 07:17")
def test_get_scheduled_job_stats(admin_request):
    service_1 = create_service(service_name="service 1")
    service_1_template = create_template(service=service_1)
    service_2 = create_service(service_name="service 2")
    service_2_template = create_template(service=service_2)

    # Shouldn’t be counted – wrong status
    create_job(
        service_1_template,
        job_status=JobStatus.FINISHED,
        scheduled_for="2017-07-17 07:00",
    )
    create_job(
        service_1_template,
        job_status=JobStatus.IN_PROGRESS,
        scheduled_for="2017-07-17 08:00",
    )

    # Should be counted – service 1
    create_job(
        service_1_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for="2017-07-17 09:00",
    )
    create_job(
        service_1_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for="2017-07-17 10:00",
    )
    create_job(
        service_1_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for="2017-07-17 11:00",
    )

    # Should be counted – service 2
    create_job(
        service_2_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for="2017-07-17 11:00",
    )

    assert admin_request.get(
        "job.get_scheduled_job_stats",
        service_id=service_1.id,
    ) == {
        "count": 3,
        "soonest_scheduled_for": "2017-07-17T09:00:00+00:00",
    }

    assert admin_request.get(
        "job.get_scheduled_job_stats",
        service_id=service_2.id,
    ) == {
        "count": 1,
        "soonest_scheduled_for": "2017-07-17T11:00:00+00:00",
    }


def test_get_job_status_returns_light_response(admin_request, sample_job):
    """Test that the status endpoint returns only required fields."""
    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    sample_job.notification_count = 5

    create_notification(job=sample_job, status=NotificationStatus.SENT)
    create_notification(job=sample_job, status=NotificationStatus.DELIVERED)
    create_notification(job=sample_job, status=NotificationStatus.FAILED)

    resp_json = admin_request.get(
        "job.get_job_status",
        service_id=service_id,
        job_id=job_id,
    )

    assert set(resp_json.keys()) == {
        "total",
        "delivered",
        "failed",
        "pending",
        "finished",
    }

    assert resp_json["total"] == 5
    assert resp_json["delivered"] == 2  # sent + delivered
    assert resp_json["failed"] == 1
    assert resp_json["pending"] == 2  # total - delivered - failed
    assert resp_json["finished"] is False


def test_get_job_status_counts_all_delivered_statuses(admin_request, sample_job):
    """Test that delivered count includes both 'delivered' and 'sent' statuses."""
    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    sample_job.notification_count = 4

    create_notification(job=sample_job, status=NotificationStatus.SENT)
    create_notification(job=sample_job, status=NotificationStatus.SENT)
    create_notification(job=sample_job, status=NotificationStatus.DELIVERED)
    create_notification(job=sample_job, status=NotificationStatus.DELIVERED)

    resp_json = admin_request.get(
        "job.get_job_status",
        service_id=service_id,
        job_id=job_id,
    )

    assert resp_json["delivered"] == 4
    assert resp_json["failed"] == 0
    assert resp_json["pending"] == 0


def test_get_job_status_counts_all_failed_statuses(admin_request, sample_job):
    """Test that failed count includes all failure status types."""
    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    sample_job.notification_count = 6

    create_notification(job=sample_job, status=NotificationStatus.FAILED)
    create_notification(job=sample_job, status=NotificationStatus.TECHNICAL_FAILURE)
    create_notification(job=sample_job, status=NotificationStatus.TEMPORARY_FAILURE)
    create_notification(job=sample_job, status=NotificationStatus.PERMANENT_FAILURE)
    create_notification(job=sample_job, status=NotificationStatus.VALIDATION_FAILED)
    create_notification(job=sample_job, status=NotificationStatus.VIRUS_SCAN_FAILED)

    resp_json = admin_request.get(
        "job.get_job_status",
        service_id=service_id,
        job_id=job_id,
    )

    assert resp_json["delivered"] == 0
    assert resp_json["failed"] == 6
    assert resp_json["pending"] == 0


def test_get_job_status_finished_when_processing_complete_and_no_pending(
    admin_request, sample_job
):
    """Test that finished is True only when processing_finished is set and pending is 0."""
    from app.utils import utc_now

    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    sample_job.notification_count = 2
    sample_job.processing_finished = utc_now()

    create_notification(job=sample_job, status=NotificationStatus.DELIVERED)
    create_notification(job=sample_job, status=NotificationStatus.DELIVERED)

    resp_json = admin_request.get(
        "job.get_job_status",
        service_id=service_id,
        job_id=job_id,
    )

    assert resp_json["pending"] == 0
    assert resp_json["finished"] is True


def test_get_job_status_not_finished_when_pending_exists(admin_request, sample_job):
    """Test that finished is False when there are still pending notifications."""
    from app.utils import utc_now

    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    sample_job.notification_count = 5
    sample_job.processing_finished = utc_now()

    create_notification(job=sample_job, status=NotificationStatus.DELIVERED)

    resp_json = admin_request.get(
        "job.get_job_status",
        service_id=service_id,
        job_id=job_id,
    )

    assert resp_json["pending"] == 4
    assert (
        resp_json["finished"] is False
    )  # Still has pending even though processing_finished is set
