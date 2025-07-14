from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery
from app.aws import s3
from app.aws.s3 import remove_csv_object
from app.celery.process_ses_receipts_tasks import check_and_queue_callback_task
from app.config import QueueNames
from app.dao.fact_processing_time_dao import insert_update_processing_time
from app.dao.inbound_sms_dao import delete_inbound_sms_older_than_retention
from app.dao.jobs_dao import (
    dao_archive_job,
    dao_get_jobs_older_than_data_retention,
    dao_get_unfinished_jobs,
)
from app.dao.notifications_dao import (
    dao_get_notifications_processing_time_stats,
    dao_timeout_notifications,
    get_service_ids_with_notifications_before,
    move_notifications_to_notification_history,
)
from app.dao.service_data_retention_dao import (
    fetch_service_data_retention_for_all_services_by_notification_type,
)
from app.enums import NotificationType
from app.models import FactProcessingTime
from app.utils import get_midnight_in_utc, utc_now


@notify_celery.task(name="remove-sms-email-jobs")
def remove_sms_email_csv_files():
    _remove_csv_files([NotificationType.EMAIL, NotificationType.SMS])


def _remove_csv_files(job_types):
    jobs = dao_get_jobs_older_than_data_retention(notification_types=job_types)
    for job in jobs:
        s3.remove_job_from_s3(job.service_id, job.id)
        dao_archive_job(job)
        current_app.logger.info("Job ID {} has been removed from s3.".format(job.id))


@notify_celery.task(name="cleanup-unfinished-jobs")
def cleanup_unfinished_jobs():
    now = utc_now()
    jobs = dao_get_unfinished_jobs()
    for job in jobs:
        # The query already checks that the processing_finished time is null, so here we are saying
        # if it started more than 4 hours ago, that's too long
        acceptable_finish_time = None
        try:
            if job.processing_started is not None:
                acceptable_finish_time = job.processing_started + timedelta(minutes=5)
        except TypeError:
            current_app.logger.exception(
                f"Job ID {job.id} processing_started is {job.processing_started}.",
            )
            raise
        if acceptable_finish_time and now > acceptable_finish_time:
            remove_csv_object(job.original_file_name)
            dao_archive_job(job)


@notify_celery.task(name="delete-notifications-older-than-retention")
def delete_notifications_older_than_retention():
    delete_email_notifications_older_than_retention.apply_async(
        queue=QueueNames.REPORTING
    )
    delete_sms_notifications_older_than_retention.apply_async(
        queue=QueueNames.REPORTING
    )


@notify_celery.task(name="delete-sms-notifications-older-than-retention")
def delete_sms_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type(NotificationType.SMS)


@notify_celery.task(name="delete-email-notifications-older-than-retention")
def delete_email_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type(NotificationType.EMAIL)


def _delete_notifications_older_than_retention_by_type(notification_type):
    flexible_data_retention = (
        fetch_service_data_retention_for_all_services_by_notification_type(
            notification_type
        )
    )

    for f in flexible_data_retention:
        day_to_delete_backwards_from = get_midnight_in_utc(
            utc_now()
        ).date() - timedelta(days=f.days_of_retention)

        delete_notifications_for_service_and_type.apply_async(
            queue=QueueNames.REPORTING,
            kwargs={
                "service_id": f.service_id,
                "notification_type": notification_type,
                "datetime_to_delete_before": day_to_delete_backwards_from,
            },
        )

    seven_days_ago = get_midnight_in_utc(utc_now()).date() - timedelta(days=7)

    service_ids_with_data_retention = {x.service_id for x in flexible_data_retention}

    # get a list of all service ids that we'll need to delete for. Typically that might only be 5% of services.
    # This query takes a couple of mins to run.
    service_ids_that_have_sent_notifications_recently = (
        get_service_ids_with_notifications_before(notification_type, seven_days_ago)
    )

    service_ids_to_purge = (
        service_ids_that_have_sent_notifications_recently
        - service_ids_with_data_retention
    )

    for service_id in service_ids_to_purge:
        delete_notifications_for_service_and_type.apply_async(
            queue=QueueNames.REPORTING,
            kwargs={
                "service_id": service_id,
                "notification_type": notification_type,
                "datetime_to_delete_before": seven_days_ago,
            },
        )

    current_app.logger.info(
        f"delete-notifications-older-than-retention: triggered subtasks for notification_type {notification_type}: "
        f"{len(service_ids_with_data_retention)} services with flexible data retention, "
        f"{len(service_ids_to_purge)} services without flexible data retention"
    )


@notify_celery.task(name="delete-notifications-for-service-and-type")
def delete_notifications_for_service_and_type(
    service_id, notification_type, datetime_to_delete_before
):
    start = utc_now()
    num_deleted = move_notifications_to_notification_history(
        notification_type,
        service_id,
        datetime_to_delete_before,
    )
    if num_deleted:
        end = utc_now()
        current_app.logger.info(
            f"delete-notifications-for-service-and-type: "
            f"service: {service_id}, "
            f"notification_type: {notification_type}, "
            f"count deleted: {num_deleted}, "
            f"duration: {(end - start).seconds} seconds"
        )


@notify_celery.task(name="timeout-sending-notifications")
def timeout_notifications():
    notifications = ["dummy value so len() > 0"]

    cutoff_time = utc_now() - timedelta(
        seconds=current_app.config.get("SENDING_NOTIFICATIONS_TIMEOUT_PERIOD")
    )

    while len(notifications) > 0:
        notifications = dao_timeout_notifications(cutoff_time)

        for notification in notifications:
            check_and_queue_callback_task(notification)

        current_app.logger.info(
            "Timeout period reached for {} notifications, status has been updated.".format(
                len(notifications)
            )
        )


@notify_celery.task(name="delete-inbound-sms")
def delete_inbound_sms():
    try:
        start = utc_now()
        deleted = delete_inbound_sms_older_than_retention()
        current_app.logger.info(
            "Delete inbound sms job started {} finished {} deleted {} inbound sms notifications".format(
                start, utc_now(), deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete inbound sms notifications")
        raise


@notify_celery.task(name="save-daily-notification-processing-time")
def save_daily_notification_processing_time(local_date=None):
    # local_date is a string in the format of "YYYY-MM-DD"
    if local_date is None:
        # if a date is not provided, we run against yesterdays data
        local_date = (utc_now() - timedelta(days=1)).date()
    else:
        local_date = datetime.strptime(local_date, "%Y-%m-%d").date()

    start_time = get_midnight_in_utc(local_date)
    end_time = get_midnight_in_utc(local_date + timedelta(days=1))
    result = dao_get_notifications_processing_time_stats(start_time, end_time)
    insert_update_processing_time(
        FactProcessingTime(
            local_date=local_date,
            messages_total=result.messages_total,
            messages_within_10_secs=result.messages_within_10_secs,
        )
    )
