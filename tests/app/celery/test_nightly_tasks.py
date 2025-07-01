from datetime import date, datetime, timedelta
from unittest.mock import ANY, call, patch

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.celery import nightly_tasks
from app.celery.nightly_tasks import (
    _delete_notifications_older_than_retention_by_type,
    cleanup_unfinished_jobs,
    delete_email_notifications_older_than_retention,
    delete_inbound_sms,
    delete_notifications_for_service_and_type,
    delete_sms_notifications_older_than_retention,
    remove_sms_email_csv_files,
    s3,
    save_daily_notification_processing_time,
    timeout_notifications,
)
from app.enums import NotificationType, TemplateType
from app.models import FactProcessingTime, Job
from app.utils import utc_now
from tests.app.db import (
    create_job,
    create_notification,
    create_service,
    create_service_data_retention,
    create_template,
)


def mock_s3_get_list_match(bucket_name, subfolder="", suffix="", last_modified=None):
    if subfolder == "2018-01-11/zips_sent":
        return ["NOTIFY.2018-01-11175007.ZIP.TXT", "NOTIFY.2018-01-11175008.ZIP.TXT"]
    if subfolder == "root/dispatch":
        return [
            "root/dispatch/NOTIFY.2018-01-11175007.ACK.txt",
            "root/dispatch/NOTIFY.2018-01-11175008.ACK.txt",
        ]


def mock_s3_get_list_diff(bucket_name, subfolder="", suffix="", last_modified=None):
    if subfolder == "2018-01-11/zips_sent":
        return [
            "NOTIFY.2018-01-11175007p.ZIP.TXT",
            "NOTIFY.2018-01-11175008.ZIP.TXT",
            "NOTIFY.2018-01-11175009.ZIP.TXT",
            "NOTIFY.2018-01-11175010.ZIP.TXT",
        ]
    if subfolder == "root/dispatch":
        return [
            "root/disoatch/NOTIFY.2018-01-11175007p.ACK.TXT",
            "root/disoatch/NOTIFY.2018-01-11175008.ACK.TXT",
        ]


@freeze_time("2016-10-18T10:00:00")
def test_will_remove_csv_files_for_jobs_older_than_seven_days(
    notify_db_session, mocker, sample_template
):
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    mocker.patch("app.celery.nightly_tasks.s3.remove_job_from_s3")

    seven_days_ago = utc_now() - timedelta(days=7)
    just_under_seven_days = seven_days_ago + timedelta(seconds=1)
    eight_days_ago = seven_days_ago - timedelta(days=1)
    nine_days_ago = eight_days_ago - timedelta(days=1)
    just_under_nine_days = nine_days_ago + timedelta(seconds=1)
    nine_days_one_second_ago = nine_days_ago - timedelta(seconds=1)

    create_job(sample_template, created_at=nine_days_one_second_ago, archived=True)
    job1_to_delete = create_job(sample_template, created_at=eight_days_ago)
    job2_to_delete = create_job(sample_template, created_at=just_under_nine_days)
    dont_delete_me_1 = create_job(sample_template, created_at=seven_days_ago)
    create_job(sample_template, created_at=just_under_seven_days)

    remove_sms_email_csv_files()

    assert s3.remove_job_from_s3.call_args_list == [
        call(job1_to_delete.service_id, job1_to_delete.id),
        call(job2_to_delete.service_id, job2_to_delete.id),
    ]
    assert job1_to_delete.archived is True
    assert dont_delete_me_1.archived is False


@freeze_time("2016-10-18T10:00:00")
def test_will_remove_csv_files_for_jobs_older_than_retention_period(
    notify_db_session, mocker
):
    """
    Jobs older than retention period are deleted, but only two day's worth (two-day window)
    """
    mocker.patch("app.celery.nightly_tasks.s3.remove_job_from_s3")
    service_1 = create_service(service_name="service 1")
    service_2 = create_service(service_name="service 2")
    create_service_data_retention(
        service=service_1, notification_type=NotificationType.SMS, days_of_retention=3
    )
    create_service_data_retention(
        service=service_2,
        notification_type=NotificationType.EMAIL,
        days_of_retention=30,
    )
    sms_template_service_1 = create_template(service=service_1)
    email_template_service_1 = create_template(
        service=service_1,
        template_type=TemplateType.EMAIL,
    )

    sms_template_service_2 = create_template(service=service_2)
    email_template_service_2 = create_template(
        service=service_2,
        template_type=TemplateType.EMAIL,
    )

    four_days_ago = utc_now() - timedelta(days=4)
    eight_days_ago = utc_now() - timedelta(days=8)
    thirty_one_days_ago = utc_now() - timedelta(days=31)

    job1_to_delete = create_job(sms_template_service_1, created_at=four_days_ago)
    job2_to_delete = create_job(email_template_service_1, created_at=eight_days_ago)
    create_job(email_template_service_1, created_at=four_days_ago)

    create_job(email_template_service_2, created_at=eight_days_ago)
    job3_to_delete = create_job(
        email_template_service_2, created_at=thirty_one_days_ago
    )
    job4_to_delete = create_job(sms_template_service_2, created_at=eight_days_ago)

    remove_sms_email_csv_files()

    s3.remove_job_from_s3.assert_has_calls(
        [
            call(job1_to_delete.service_id, job1_to_delete.id),
            call(job2_to_delete.service_id, job2_to_delete.id),
            call(job3_to_delete.service_id, job3_to_delete.id),
            call(job4_to_delete.service_id, job4_to_delete.id),
        ],
        any_order=True,
    )


def test_delete_sms_notifications_older_than_retention_calls_child_task(
    notify_api, mocker
):
    mocked = mocker.patch(
        "app.celery.nightly_tasks._delete_notifications_older_than_retention_by_type"
    )
    delete_sms_notifications_older_than_retention()
    mocked.assert_called_once_with(NotificationType.SMS)


def test_delete_email_notifications_older_than_retentions_calls_child_task(
    notify_api, mocker
):
    mocked_notifications = mocker.patch(
        "app.celery.nightly_tasks._delete_notifications_older_than_retention_by_type"
    )
    delete_email_notifications_older_than_retention()
    mocked_notifications.assert_called_once_with(NotificationType.EMAIL)


@freeze_time("2021-12-13T10:00")
def test_timeout_notifications(mocker, sample_notification):
    mock_update = mocker.patch("app.celery.nightly_tasks.check_and_queue_callback_task")
    mock_dao = mocker.patch("app.celery.nightly_tasks.dao_timeout_notifications")

    mock_dao.side_effect = [
        [sample_notification],  # first batch to time out
        [sample_notification],  # second batch
        [],  # nothing left to time out
    ]

    timeout_notifications()
    mock_dao.assert_called_with(datetime.fromisoformat("2021-12-10T10:00"))
    assert mock_update.mock_calls == [
        call(sample_notification),
        call(sample_notification),
    ]


def test_delete_inbound_sms_calls_child_task(notify_api, mocker):
    mocker.patch("app.celery.nightly_tasks.delete_inbound_sms_older_than_retention")
    delete_inbound_sms()
    assert nightly_tasks.delete_inbound_sms_older_than_retention.call_count == 1


def test_delete_inbound_sms_calls_child_task_db_error(notify_api, mocker):
    mock_delete = mocker.patch(
        "app.celery.nightly_tasks.delete_inbound_sms_older_than_retention"
    )
    mock_delete.side_effect = SQLAlchemyError

    with pytest.raises(expected_exception=SQLAlchemyError):
        delete_inbound_sms()


@freeze_time("2021-01-18T02:00")
@pytest.mark.parametrize("date_provided", [None, "2021-1-17"])
def test_save_daily_notification_processing_time(
    mocker, sample_template, date_provided
):
    # notification created too early to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 16, 23, 59),
        sent_at=datetime(2021, 1, 16, 23, 59) + timedelta(seconds=5),
    )
    # notification counted and sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 17, 00, 00),
        sent_at=datetime(2021, 1, 17, 00, 00) + timedelta(seconds=5),
    )
    # notification counted but not sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 17, 23, 59),
        sent_at=datetime(2021, 1, 17, 23, 59) + timedelta(seconds=15),
    )
    # notification created too late to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 18, 00, 00),
        sent_at=datetime(2021, 1, 18, 00, 00) + timedelta(seconds=5),
    )

    save_daily_notification_processing_time(date_provided)

    persisted_to_db = db.session.execute(select(FactProcessingTime)).scalars().all()
    assert len(persisted_to_db) == 1
    assert persisted_to_db[0].local_date == date(2021, 1, 17)
    assert persisted_to_db[0].messages_total == 2
    assert persisted_to_db[0].messages_within_10_secs == 1


@freeze_time("2021-04-18T02:00")
@pytest.mark.parametrize("date_provided", [None, "2021-4-17"])
def test_save_daily_notification_processing_time_when_in_est(
    mocker, sample_template, date_provided
):
    # notification created too early to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 16, 22, 59),
        sent_at=datetime(2021, 4, 16, 22, 59) + timedelta(seconds=15),
    )
    # notification counted and sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 17, 4, 00),
        sent_at=datetime(2021, 4, 17, 4, 00) + timedelta(seconds=5),
    )
    # notification counted and sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 17, 22, 59),
        sent_at=datetime(2021, 4, 17, 22, 59) + timedelta(seconds=5),
    )
    # notification created too late to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 18, 23, 00),
        sent_at=datetime(2021, 4, 18, 23, 00) + timedelta(seconds=15),
    )

    save_daily_notification_processing_time(date_provided)

    persisted_to_db = db.session.execute(select(FactProcessingTime)).scalars().all()
    assert len(persisted_to_db) == 1
    assert persisted_to_db[0].local_date == date(2021, 4, 17)
    assert persisted_to_db[0].messages_total == 2
    assert persisted_to_db[0].messages_within_10_secs == 2


@freeze_time("2021-06-05 08:00")
def test_delete_notifications_task_calls_task_for_services_with_data_retention_of_same_type(
    notify_db_session, mocker
):
    sms_service = create_service(service_name="a")
    email_service = create_service(service_name="b")
    letter_service = create_service(service_name="c")

    create_service_data_retention(sms_service, notification_type=NotificationType.SMS)
    create_service_data_retention(
        email_service, notification_type=NotificationType.EMAIL
    )
    create_service_data_retention(
        letter_service, notification_type=NotificationType.LETTER
    )

    mock_subtask = mocker.patch(
        "app.celery.nightly_tasks.delete_notifications_for_service_and_type"
    )

    _delete_notifications_older_than_retention_by_type(NotificationType.SMS)

    mock_subtask.apply_async.assert_called_once_with(
        queue="reporting-tasks",
        kwargs={
            "service_id": sms_service.id,
            "notification_type": NotificationType.SMS,
            # three days of retention, its morn of 5th, so we want to keep all messages from 4th, 3rd and 2nd.
            "datetime_to_delete_before": date(2021, 6, 2),
        },
    )


@freeze_time("2021-04-04 23:00")
def test_delete_notifications_task_calls_task_for_services_with_data_retention_by_looking_at_retention(
    notify_db_session, mocker
):
    service_14_days = create_service(service_name="a")
    service_3_days = create_service(service_name="b")
    create_service_data_retention(service_14_days, days_of_retention=14)
    create_service_data_retention(service_3_days, days_of_retention=3)

    mock_subtask = mocker.patch(
        "app.celery.nightly_tasks.delete_notifications_for_service_and_type"
    )

    _delete_notifications_older_than_retention_by_type(NotificationType.SMS)

    assert mock_subtask.apply_async.call_count == 2
    mock_subtask.apply_async.assert_has_calls(
        any_order=True,
        calls=[
            call(
                queue=ANY,
                kwargs={
                    "service_id": service_14_days.id,
                    "notification_type": NotificationType.SMS,
                    "datetime_to_delete_before": date(2021, 3, 21),
                },
            ),
            call(
                queue=ANY,
                kwargs={
                    "service_id": service_3_days.id,
                    "notification_type": NotificationType.SMS,
                    "datetime_to_delete_before": date(2021, 4, 1),
                },
            ),
        ],
    )


@freeze_time("2021-04-02 23:00")
def test_delete_notifications_task_calls_task_for_services_that_have_sent_notifications_recently(
    notify_db_session, mocker
):
    service_will_delete_1 = create_service(service_name="a")
    service_will_delete_2 = create_service(service_name="b")
    service_nothing_to_delete = create_service(service_name="c")

    create_template(service_will_delete_1)
    create_template(service_will_delete_2)
    nothing_to_delete_sms_template = create_template(
        service_nothing_to_delete,
        template_type=TemplateType.SMS,
    )
    nothing_to_delete_email_template = create_template(
        service_nothing_to_delete,
        template_type=TemplateType.EMAIL,
    )

    # will be deleted as service has no custom retention, but past our default 7 days
    create_notification(
        service_will_delete_1.templates[0],
        created_at=utc_now() - timedelta(days=8),
    )
    create_notification(
        service_will_delete_2.templates[0],
        created_at=utc_now() - timedelta(days=8),
    )

    # will be kept as it's recent, and we won't run delete_notifications_for_service_and_type
    create_notification(
        nothing_to_delete_sms_template, created_at=utc_now() - timedelta(days=2)
    )
    # this is an old notification, but for email not sms, so we won't run delete_notifications_for_service_and_type
    create_notification(
        nothing_to_delete_email_template,
        created_at=utc_now() - timedelta(days=8),
    )

    mock_subtask = mocker.patch(
        "app.celery.nightly_tasks.delete_notifications_for_service_and_type"
    )

    _delete_notifications_older_than_retention_by_type(NotificationType.SMS)

    assert mock_subtask.apply_async.call_count == 2
    mock_subtask.apply_async.assert_has_calls(
        any_order=True,
        calls=[
            call(
                queue=ANY,
                kwargs={
                    "service_id": service_will_delete_1.id,
                    "notification_type": NotificationType.SMS,
                    "datetime_to_delete_before": date(2021, 3, 26),
                },
            ),
            call(
                queue=ANY,
                kwargs={
                    "service_id": service_will_delete_2.id,
                    "notification_type": NotificationType.SMS,
                    "datetime_to_delete_before": date(2021, 3, 26),
                },
            ),
        ],
    )


def test_cleanup_unfinished_jobs(mocker):
    mock_s3 = mocker.patch("app.celery.nightly_tasks.remove_csv_object")
    mock_dao_archive = mocker.patch("app.celery.nightly_tasks.dao_archive_job")
    mock_dao = mocker.patch("app.celery.nightly_tasks.dao_get_unfinished_jobs")
    mock_job_unfinished = Job()
    mock_job_unfinished.processing_started = datetime(2023, 1, 1, 0, 0, 0)
    mock_job_unfinished.original_file_name = "blah"

    mock_dao.return_value = [mock_job_unfinished]
    cleanup_unfinished_jobs()
    mock_s3.assert_called_once_with("blah")
    mock_dao_archive.assert_called_once_with(mock_job_unfinished)


def test_delete_notifications_logs_when_deletion_occurs():
    fake_start_time = datetime(2025, 1, 1, 12, 0, 0)
    fake_end_time = fake_start_time + timedelta(seconds=10)
    with patch(
        "app.utils.utc_now", side_effect=[fake_start_time, fake_end_time]
    ), patch(
        "app.celery.nightly_tasks.move_notifications_to_notification_history",
        return_value=5,
    ) as mock_move, patch(
        "app.celery.nightly_tasks.current_app.logger.info"
    ) as mock_logger:

        delete_notifications_for_service_and_type(
            service_id="abc123",
            notification_type="sms",
            datetime_to_delete_before=datetime(2025, 1, 1, 0, 0, 0),
        )
        mock_move.assert_called_once_with(
            "sms", "abc123", datetime(2025, 1, 1, 0, 0, 0)
        )
        mock_logger.assert_called_once()
        log_message = mock_logger.call_args[0][0]
        assert "service: abc123" in log_message
        assert "notification_type: sms" in log_message
        assert "count deleted: 5" in log_message
