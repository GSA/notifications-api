import json
from collections import namedtuple
from datetime import timedelta
from unittest import mock
from unittest.mock import ANY, MagicMock, call

import pytest

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    batch_insert_notifications,
    check_for_missing_rows_in_completed_jobs,
    check_for_services_with_high_failure_rates_or_sending_to_tv_numbers,
    check_job_status,
    delete_verify_codes,
    expire_or_delete_invitations,
    process_delivery_receipts,
    replay_created_notifications,
    run_scheduled_jobs,
)
from app.config import QueueNames, Test
from app.dao.jobs_dao import dao_get_job_by_id
from app.enums import JobStatus, NotificationStatus, TemplateType
from app.utils import utc_now
from notifications_utils.clients.zendesk.zendesk_client import NotifySupportTicket
from tests.app import load_example_csv
from tests.app.db import create_job, create_notification, create_template

CHECK_JOB_STATUS_TOO_OLD_MINUTES = 241


def test_should_call_delete_codes_on_delete_verify_codes_task(
    notify_db_session, mocker
):
    mocker.patch(
        "app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago"
    )
    delete_verify_codes()
    assert (
        scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1
    )


def test_should_call_expire_or_delete_invotations_on_expire_or_delete_invitations_task(
    notify_db_session, mocker
):
    mocker.patch(
        "app.celery.scheduled_tasks.expire_invitations_created_more_than_two_days_ago"
    )
    expire_or_delete_invitations()
    assert (
        scheduled_tasks.expire_invitations_created_more_than_two_days_ago.call_count
        == 1
    )


def test_should_update_scheduled_jobs_and_put_on_queue(mocker, sample_template):
    mocked = mocker.patch("app.celery.tasks.process_job.apply_async")

    one_minute_in_the_past = utc_now() - timedelta(minutes=1)
    job = create_job(
        sample_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for=one_minute_in_the_past,
    )

    run_scheduled_jobs()

    updated_job = dao_get_job_by_id(job.id)
    assert updated_job.job_status == JobStatus.PENDING
    mocked.assert_called_with([str(job.id)], queue="job-tasks")


def test_should_update_all_scheduled_jobs_and_put_on_queue(sample_template, mocker):
    mocked = mocker.patch("app.celery.tasks.process_job.apply_async")

    one_minute_in_the_past = utc_now() - timedelta(minutes=1)
    ten_minutes_in_the_past = utc_now() - timedelta(minutes=10)
    twenty_minutes_in_the_past = utc_now() - timedelta(minutes=20)
    job_1 = create_job(
        sample_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for=one_minute_in_the_past,
    )
    job_2 = create_job(
        sample_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for=ten_minutes_in_the_past,
    )
    job_3 = create_job(
        sample_template,
        job_status=JobStatus.SCHEDULED,
        scheduled_for=twenty_minutes_in_the_past,
    )

    run_scheduled_jobs()

    assert dao_get_job_by_id(job_1.id).job_status == JobStatus.PENDING
    assert dao_get_job_by_id(job_2.id).job_status == JobStatus.PENDING
    assert dao_get_job_by_id(job_2.id).job_status == JobStatus.PENDING

    mocked.assert_has_calls(
        [
            call([str(job_3.id)], queue="job-tasks"),
            call([str(job_2.id)], queue="job-tasks"),
            call([str(job_1.id)], queue="job-tasks"),
        ]
    )


def test_check_job_status_task_calls_process_incomplete_jobs(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.IN_PROGRESS,
    )
    create_notification(template=sample_template, job=job)
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_calls_process_incomplete_jobs_when_scheduled_job_is_not_complete(
    mocker, sample_template
):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=5),
        scheduled_for=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.IN_PROGRESS,
    )
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_calls_process_incomplete_jobs_for_pending_scheduled_jobs(
    mocker, sample_template
):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=5),
        scheduled_for=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.PENDING,
    )

    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_does_not_call_process_incomplete_jobs_for_non_scheduled_pending_jobs(
    mocker,
    sample_template,
):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=2),
        job_status=JobStatus.PENDING,
    )
    check_job_status()

    assert not mock_celery.called


def test_check_job_status_task_calls_process_incomplete_jobs_for_multiple_jobs(
    mocker, sample_template
):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=5),
        scheduled_for=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.IN_PROGRESS,
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=5),
        scheduled_for=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.IN_PROGRESS,
    )
    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id), str(job_2.id)]], queue=QueueNames.JOBS
    )


def test_check_job_status_task_only_sends_old_tasks(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=5),
        scheduled_for=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.IN_PROGRESS,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(minutes=300),
        processing_started=utc_now() - timedelta(minutes=239),
        job_status=JobStatus.IN_PROGRESS,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(minutes=300),
        scheduled_for=utc_now() - timedelta(minutes=239),
        job_status=JobStatus.PENDING,
    )
    check_job_status()

    # jobs 2 and 3 were created less than 30 minutes ago, so are not sent to Celery task
    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_sets_jobs_to_error(mocker, sample_template):
    mock_celery = mocker.patch("app.celery.tasks.process_incomplete_jobs.apply_async")
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=5),
        scheduled_for=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.IN_PROGRESS,
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(minutes=300),
        processing_started=utc_now() - timedelta(minutes=239),
        job_status=JobStatus.IN_PROGRESS,
    )
    check_job_status()

    # job 2 not in celery task
    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)
    assert job.job_status == JobStatus.ERROR
    assert job_2.job_status == JobStatus.IN_PROGRESS


def test_replay_created_notifications(notify_db_session, sample_service, mocker):
    email_delivery_queue = mocker.patch(
        "app.celery.provider_tasks.deliver_email.apply_async"
    )
    sms_delivery_queue = mocker.patch(
        "app.celery.provider_tasks.deliver_sms.apply_async"
    )

    sms_template = create_template(
        service=sample_service, template_type=TemplateType.SMS
    )
    email_template = create_template(
        service=sample_service, template_type=TemplateType.EMAIL
    )
    older_than = (60 * 60) + (60 * 15)  # 1 hour 15 minutes
    # notifications expected to be resent
    old_sms = create_notification(
        template=sms_template,
        created_at=utc_now() - timedelta(seconds=older_than),
        status=NotificationStatus.CREATED,
    )
    old_email = create_notification(
        template=email_template,
        created_at=utc_now() - timedelta(seconds=older_than),
        status=NotificationStatus.CREATED,
    )
    # notifications that are not to be resent
    create_notification(
        template=sms_template,
        created_at=utc_now() - timedelta(seconds=older_than),
        status=NotificationStatus.SENDING,
    )
    create_notification(
        template=email_template,
        created_at=utc_now() - timedelta(seconds=older_than),
        status=NotificationStatus.DELIVERED,
    )
    create_notification(
        template=sms_template,
        created_at=utc_now(),
        status=NotificationStatus.CREATED,
    )
    create_notification(
        template=email_template,
        created_at=utc_now(),
        status=NotificationStatus.CREATED,
    )

    replay_created_notifications()
    email_delivery_queue.assert_called_once_with(
        [str(old_email.id)], queue="send-email-tasks", countdown=60
    )
    sms_delivery_queue.assert_called_once_with(
        [str(old_sms.id)], queue="send-sms-tasks", countdown=60
    )


def test_check_job_status_task_does_not_raise_error(sample_template):
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(hours=5),
        scheduled_for=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.FINISHED,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=utc_now() - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        processing_started=utc_now()
        - timedelta(minutes=CHECK_JOB_STATUS_TOO_OLD_MINUTES),
        job_status=JobStatus.FINISHED,
    )

    check_job_status()


@pytest.mark.parametrize(
    "offset",
    (
        timedelta(days=1),
        pytest.param(timedelta(hours=23, minutes=59), marks=pytest.mark.xfail),
        pytest.param(timedelta(minutes=20), marks=pytest.mark.xfail),
        timedelta(minutes=19),
    ),
)
def test_check_for_missing_rows_in_completed_jobs_ignores_old_and_new_jobs(
    mocker,
    sample_email_template,
    offset,
):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mocker.patch("app.encryption.encrypt", return_value="something_encrypted")
    process_row = mocker.patch("app.celery.scheduled_tasks.process_row")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - offset,
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    assert process_row.called is False


def test_check_for_missing_rows_in_completed_jobs(mocker, sample_email_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mocker.patch("app.encryption.encrypt", return_value="something_encrypted")
    process_row = mocker.patch("app.celery.scheduled_tasks.process_row")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=20),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    process_row.assert_called_once_with(
        mock.ANY, mock.ANY, job, job.service, sender_id=None
    )


def test_check_for_missing_rows_in_completed_jobs_calls_save_email(
    mocker, sample_email_template
):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    save_email_task = mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=20),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    save_email_task.assert_called_once_with(
        (
            str(job.service_id),
            "uuid",
            ANY,
        ),
        {},
        queue="database-tasks",
        expires=ANY,
    )


def test_check_for_missing_rows_in_completed_jobs_uses_sender_id(
    mocker, sample_email_template, fake_uuid
):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": fake_uuid}),
    )
    mock_process_row = mocker.patch("app.celery.scheduled_tasks.process_row")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JobStatus.FINISHED,
        processing_finished=utc_now() - timedelta(minutes=20),
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    mock_process_row.assert_called_once_with(
        mock.ANY, mock.ANY, job, job.service, sender_id=fake_uuid
    )


MockServicesSendingToTVNumbers = namedtuple(
    "ServicesSendingToTVNumbers",
    [
        "service_id",
        "notification_count",
    ],
)
MockServicesWithHighFailureRate = namedtuple(
    "ServicesWithHighFailureRate",
    [
        "service_id",
        "permanent_failure_rate",
    ],
)


@pytest.mark.parametrize(
    "failure_rates, sms_to_tv_numbers, expected_message",
    [
        [
            [MockServicesWithHighFailureRate("123", 0.3)],
            [],
            "1 service(s) have had high permanent-failure rates for sms messages in last "
            "24 hours:\nservice: {}/services/{} failure rate: 0.3,\n".format(
                Test.ADMIN_BASE_URL, "123"
            ),
        ],
        [
            [],
            [MockServicesSendingToTVNumbers("123", 300)],
            "1 service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n"
            "service: {}/services/{} count of sms to tv numbers: 300,\n".format(
                Test.ADMIN_BASE_URL, "123"
            ),
        ],
    ],
)
def test_check_for_services_with_high_failure_rates_or_sending_to_tv_numbers(
    mocker, notify_db_session, failure_rates, sms_to_tv_numbers, expected_message
):
    mock_logger = mocker.patch("app.celery.tasks.current_app.logger.warning")
    mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
    mock_zendesk_client = MagicMock()
    mocker.patch("app.celery.scheduled_tasks.zendesk_client", mock_zendesk_client)
    mock_send_ticket_to_zendesk = mock_zendesk_client.send_ticket_to_zendesk
    mock_failure_rates = mocker.patch(
        "app.celery.scheduled_tasks.dao_find_services_with_high_failure_rates",
        return_value=failure_rates,
    )
    mock_sms_to_tv_numbers = mocker.patch(
        "app.celery.scheduled_tasks.dao_find_services_sending_to_tv_numbers",
        return_value=sms_to_tv_numbers,
    )

    zendesk_actions = "\nYou can find instructions for this ticket in our manual:\nhttps://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"  # noqa

    check_for_services_with_high_failure_rates_or_sending_to_tv_numbers()

    assert mock_failure_rates.called
    assert mock_sms_to_tv_numbers.called
    mock_logger.assert_called_once_with(expected_message)
    mock_create_ticket.assert_called_with(
        ANY,
        message=expected_message + zendesk_actions,
        subject="[test] High failure rates for sms spotted for services",
        ticket_type="incident",
        technical_ticket=True,
    )
    mock_send_ticket_to_zendesk.assert_called_once()


def test_batch_insert_with_valid_notifications(mocker):
    mocker.patch("app.celery.scheduled_tasks.dao_batch_insert_notifications")
    rs = MagicMock()
    mocker.patch("app.celery.scheduled_tasks.redis_store", rs)
    notifications = [
        {"id": 1, "notification_status": "pending"},
        {"id": 2, "notification_status": "pending"},
    ]
    serialized_notifications = [json.dumps(n).encode("utf-8") for n in notifications]

    pipeline_mock = MagicMock()

    rs.pipeline.return_value.__enter__.return_value = pipeline_mock
    rs.llen.return_value = len(notifications)
    rs.lpop.side_effect = serialized_notifications

    batch_insert_notifications()

    rs.llen.assert_called_once_with("message_queue")
    rs.lpop.assert_called_with("message_queue")


def test_batch_insert_with_expired_notifications(mocker):
    expired_time = utc_now() - timedelta(minutes=2)
    mocker.patch(
        "app.celery.scheduled_tasks.dao_batch_insert_notifications",
        side_effect=Exception("DB Error"),
    )
    rs = MagicMock()
    mocker.patch("app.celery.scheduled_tasks.redis_store", rs)
    notifications = [
        {
            "id": 1,
            "notification_status": "pending",
            "created_at": utc_now().isoformat(),
        },
        {
            "id": 2,
            "notification_status": "pending",
            "created_at": expired_time.isoformat(),
        },
    ]
    serialized_notifications = [json.dumps(n).encode("utf-8") for n in notifications]

    pipeline_mock = MagicMock()

    rs.pipeline.return_value.__enter__.return_value = pipeline_mock
    rs.llen.return_value = len(notifications)
    rs.lpop.side_effect = serialized_notifications

    batch_insert_notifications()

    rs.llen.assert_called_once_with("message_queue")
    rs.rpush.assert_called_once()
    requeued_notification = json.loads(rs.rpush.call_args[0][1])
    assert requeued_notification["id"] == "1"


def test_batch_insert_with_malformed_notifications(mocker):
    rs = MagicMock()
    mocker.patch("app.celery.scheduled_tasks.redis_store", rs)
    malformed_data = b"not_a_valid_json"
    pipeline_mock = MagicMock()

    rs.pipeline.return_value.__enter__.return_value = pipeline_mock
    rs.llen.return_value = 1
    rs.lpop.side_effect = [malformed_data]

    with pytest.raises(json.JSONDecodeError):
        batch_insert_notifications()

    rs.llen.assert_called_once_with("message_queue")
    rs.rpush.assert_not_called()


def test_process_delivery_receipts_success(mocker):
    dao_update_mock = mocker.patch(
        "app.celery.scheduled_tasks.dao_update_delivery_receipts"
    )
    cloudwatch_mock = mocker.patch("app.celery.scheduled_tasks.AwsCloudwatchClient")
    cloudwatch_mock.return_value.check_delivery_receipts.return_value = (
        range(2000),
        range(500),
    )
    current_app_mock = mocker.patch("app.celery.scheduled_tasks.current_app")
    current_app_mock.return_value = MagicMock()
    processor = MagicMock()
    processor.process_delivery_receipts = process_delivery_receipts
    processor.retry = MagicMock()

    processor.process_delivery_receipts()
    assert dao_update_mock.call_count == 3
    dao_update_mock.assert_any_call(list(range(1000)), True)
    dao_update_mock.assert_any_call(list(range(1000, 2000)), True)
    dao_update_mock.assert_any_call(list(range(500)), False)
    processor.retry.assert_not_called()
