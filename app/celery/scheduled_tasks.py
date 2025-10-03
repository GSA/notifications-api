import json
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import between, select, union
from sqlalchemy.exc import SQLAlchemyError

from app import db, get_zendesk_client, notify_celery, redis_store
from app.celery.tasks import (
    get_recipient_csv_and_template_and_sender_id,
    process_incomplete_jobs,
    process_job,
    process_row,
)
from app.clients.cloudwatch.aws_cloudwatch import AwsCloudwatchClient
from app.config import QueueNames
from app.dao.invited_org_user_dao import (
    delete_org_invitations_created_more_than_two_days_ago,
)
from app.dao.invited_user_dao import expire_invitations_created_more_than_two_days_ago
from app.dao.jobs_dao import (
    dao_set_scheduled_jobs_to_pending,
    dao_update_job_status_to_error,
    find_jobs_with_missing_rows,
    find_missing_row_for_job,
)
from app.dao.notifications_dao import (
    dao_batch_insert_notifications,
    dao_close_out_delivery_receipts,
    dao_update_delivery_receipts,
    notifications_not_yet_sent,
)
from app.dao.services_dao import (
    dao_find_services_sending_to_tv_numbers,
    dao_find_services_with_high_failure_rates,
)
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.enums import JobStatus, NotificationType
from app.models import Job, Notification
from app.notifications.process_notifications import send_notification_to_queue
from app.utils import utc_now
from notifications_utils import aware_utcnow
from notifications_utils.clients.zendesk.zendesk_client import NotifySupportTicket

MAX_NOTIFICATION_FAILS = 10000

zendesk_client = get_zendesk_client()


@notify_celery.task(name="run-scheduled-jobs")
def run_scheduled_jobs():
    try:
        for job in dao_set_scheduled_jobs_to_pending():
            process_job.apply_async([str(job.id)], queue=QueueNames.JOBS)
            current_app.logger.info(
                "Job ID {} added to process job queue".format(job.id)
            )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to run scheduled jobs")
        raise


@notify_celery.task(name="delete-verify-codes")
def delete_verify_codes():
    try:
        start = utc_now()
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} verify codes".format(
                start, utc_now(), deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete verify codes")
        raise


@notify_celery.task(name="expire-or-delete-invitations")
def expire_or_delete_invitations():
    try:
        start = utc_now()
        expired_invites = expire_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            f"Expire job started {start} finished {utc_now()} expired {expired_invites} invitations"
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to expire invitations")
        raise

    try:
        start = utc_now()
        deleted_invites = delete_org_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            f"Delete job started {start} finished {utc_now()} deleted {deleted_invites} invitations"
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete invitations")
        raise


@notify_celery.task(name="check-job-status")
def check_job_status():
    """
    every x minutes do this check
    select
    from jobs
    where job_status == 'in progress'
    and processing started some time ago
    OR where the job_status == 'pending'
    and the job scheduled_for timestamp is some time ago.
    if any results then
        update the job_status to 'error'
        process the rows in the csv that are missing (in another task) just do the check here.
    """
    START_MINUTES = 245
    END_MINUTES = 240
    end_minutes_ago = utc_now() - timedelta(minutes=END_MINUTES)
    start_minutes_ago = utc_now() - timedelta(minutes=START_MINUTES)

    incomplete_in_progress_jobs = select(Job).where(
        Job.job_status == JobStatus.IN_PROGRESS,
        between(Job.processing_started, start_minutes_ago, end_minutes_ago),
    )
    incomplete_pending_jobs = select(Job).where(
        Job.job_status == JobStatus.PENDING,
        Job.scheduled_for.isnot(None),
        between(Job.scheduled_for, start_minutes_ago, end_minutes_ago),
    )
    jobs_not_completed_after_allotted_time = union(
        incomplete_in_progress_jobs, incomplete_pending_jobs
    )
    jobs_not_completed_after_allotted_time = (
        jobs_not_completed_after_allotted_time.order_by(
            Job.processing_started, Job.scheduled_for
        )
    )

    jobs_not_complete_after_allotted_time = db.session.execute(
        jobs_not_completed_after_allotted_time
    ).all()

    # temporarily mark them as ERROR so that they don't get picked up by future check_job_status tasks
    # if they haven't been re-processed in time.
    job_ids = []
    for job in jobs_not_complete_after_allotted_time:
        dao_update_job_status_to_error(job)
        job_ids.append(str(job.id))
    if job_ids:
        current_app.logger.info("Job(s) {} have not completed.".format(job_ids))
        process_incomplete_jobs.apply_async([job_ids], queue=QueueNames.JOBS)


@notify_celery.task(name="replay-created-notifications")
def replay_created_notifications():
    # if the notification has not be send after 1 hour, then try to resend.
    resend_created_notifications_older_than = 60 * 60
    for notification_type in (NotificationType.EMAIL, NotificationType.SMS):
        notifications_to_resend = notifications_not_yet_sent(
            resend_created_notifications_older_than, notification_type
        )

        if len(notifications_to_resend) > 0:
            current_app.logger.info(
                "Sending {} {} notifications "
                "to the delivery queue because the notification "
                "status was created.".format(
                    len(notifications_to_resend), notification_type
                )
            )

        for n in notifications_to_resend:
            send_notification_to_queue(notification=n)


@notify_celery.task(name="check-for-missing-rows-in-completed-jobs")
def check_for_missing_rows_in_completed_jobs():

    jobs = find_jobs_with_missing_rows()
    for job in jobs:
        (
            recipient_csv,
            template,
            sender_id,
        ) = get_recipient_csv_and_template_and_sender_id(job)
        missing_rows = find_missing_row_for_job(job.id, job.notification_count)
        for row_to_process in missing_rows:
            row = recipient_csv[row_to_process.missing_row]
            current_app.logger.info(
                f"Processing missing row: {row_to_process.missing_row} for job: {job.id}"
            )
            process_row(row, template, job, job.service, sender_id=sender_id)


@notify_celery.task(
    name="check-for-services-with-high-failure-rates-or-sending-to-tv-numbers"
)
def check_for_services_with_high_failure_rates_or_sending_to_tv_numbers():
    start_date = utc_now() - timedelta(days=1)
    end_date = utc_now()
    message = ""

    services_with_failures = dao_find_services_with_high_failure_rates(
        start_date=start_date, end_date=end_date
    )
    services_sending_to_tv_numbers = dao_find_services_sending_to_tv_numbers(
        start_date=start_date, end_date=end_date
    )

    if services_with_failures:
        message += "{} service(s) have had high permanent-failure rates for sms messages in last 24 hours:\n".format(
            len(services_with_failures)
        )
        for service in services_with_failures:
            service_dashboard = "{}/services/{}".format(
                current_app.config["ADMIN_BASE_URL"],
                str(service.service_id),
            )
            message += "service: {} failure rate: {},\n".format(
                service_dashboard, service.permanent_failure_rate
            )
    elif services_sending_to_tv_numbers:
        message += "{} service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n".format(
            len(services_sending_to_tv_numbers)
        )
        for service in services_sending_to_tv_numbers:
            service_dashboard = "{}/services/{}".format(
                current_app.config["ADMIN_BASE_URL"],
                str(service.service_id),
            )
            message += "service: {} count of sms to tv numbers: {},\n".format(
                service_dashboard, service.notification_count
            )

    if services_with_failures or services_sending_to_tv_numbers:
        current_app.logger.warning(message)

        if current_app.config["NOTIFY_ENVIRONMENT"] in ["live", "production", "test"]:
            message += (
                "\nYou can find instructions for this ticket in our manual:\n"
                "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"  # noqa
            )
            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] High failure rates for sms spotted for services",
                message=message,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                technical_ticket=True,
            )
            zendesk_client.send_ticket_to_zendesk(ticket)


@notify_celery.task(
    bind=True, max_retries=7, default_retry_delay=3600, name="process-delivery-receipts"
)
def process_delivery_receipts(self):
    # If we need to check db settings do it here for convenience
    # current_app.logger.info(f"POOL SIZE {app.db.engine.pool.size()}")
    """
    Every eight minutes or so (see config.py) we run this task, which searches the last ten
    minutes of logs for delivery receipts and batch updates the db with the results.  The overlap
    is intentional.  We don't mind re-updating things, it is better than losing data.

    We also set this to retry with exponential backoff in the case of failure.  The only way this would
    fail is if, for example the db went down, or redis filled causing the app to stop processing.  But if
    it does fail, we need to go back over at some point when things are running again and process those results.
    """
    try:
        batch_size = 1000  # in theory with postgresql this could be 10k to 20k?

        cloudwatch = AwsCloudwatchClient()
        cloudwatch.init_app(current_app)
        start_time = aware_utcnow() - timedelta(minutes=3)
        end_time = aware_utcnow()
        delivered_receipts, failed_receipts = cloudwatch.check_delivery_receipts(
            start_time, end_time
        )
        delivered_receipts = list(delivered_receipts)
        for i in range(0, len(delivered_receipts), batch_size):
            batch = delivered_receipts[i : i + batch_size]
            dao_update_delivery_receipts(batch, True)
        failed_receipts = list(failed_receipts)
        for i in range(0, len(failed_receipts), batch_size):
            batch = failed_receipts[i : i + batch_size]
            dao_update_delivery_receipts(batch, False)
    except Exception as ex:
        retry_count = self.request.retries
        wait_time = 3600 * 2**retry_count

        current_app.logger.exception(str(ex))

        try:
            raise self.retry(ex=ex, countdown=wait_time)
        except self.MaxRetriesExceededError:
            current_app.logger.error(
                "Failed process delivery receipts after max retries"
            )


@notify_celery.task(
    bind=True, max_retries=2, default_retry_delay=3600, name="cleanup-delivery-receipts"
)
def cleanup_delivery_receipts(self):
    dao_close_out_delivery_receipts()


@notify_celery.task(bind=True, name="batch-insert-notifications")
def batch_insert_notifications(self):
    batch = []

    current_len = redis_store.llen("message_queue")
    with redis_store.pipeline():
        # since this list is being fed by other processes, just grab what is available when
        # this call is made and process that.

        count = 0
        while count < current_len:
            count = count + 1
            notification_bytes = redis_store.lpop("message_queue")
            notification_dict = json.loads(notification_bytes.decode("utf-8"))
            notification_dict["status"] = notification_dict.pop("notification_status")
            if not notification_dict.get("created_at"):
                notification_dict["created_at"] = utc_now()
            elif isinstance(notification_dict["created_at"], list):
                notification_dict["created_at"] = notification_dict["created_at"][0]
            notification = Notification(**notification_dict)
            # notify-api-749 do not write to db
            # if we have a verify_code we know this is the authentication notification at login time
            # and not csv (containing PII) provided by the user, so allow verify_code to continue to exist
            if notification is None:
                continue
            if "verify_code" in str(notification.personalisation):
                pass
            else:
                batch.append(notification)
    try:
        dao_batch_insert_notifications(batch)
    except Exception:
        current_app.logger.exception("Notification batch insert failed")
        for n in batch:
            # Use 'created_at' as a TTL so we don't retry infinitely
            notification_time = n.created_at
            if isinstance(notification_time, str):
                notification_time = datetime.fromisoformat(n.created_at)
            if notification_time < utc_now() - timedelta(seconds=50):
                current_app.logger.warning(
                    f"Abandoning stale data, could not write to db: {n.serialize_for_redis(n)}"
                )
                continue
            else:
                redis_store.rpush("message_queue", json.dumps(n.serialize_for_redis(n)))
