import json
from datetime import datetime

from flask import current_app
from requests import HTTPError, RequestException, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_uuid, encryption, notify_celery
from app.aws import s3
from app.celery import provider_tasks
from app.config import QueueNames
from app.dao.inbound_sms_dao import dao_get_inbound_sms_by_id
from app.dao.jobs_dao import dao_get_job_by_id, dao_update_job
from app.dao.notifications_dao import (
    dao_get_last_notification_added_for_job_id,
    get_notification_by_id,
)
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_inbound_api_dao import get_service_inbound_api_for_service
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.enums import JobStatus, KeyType, NotificationType
from app.notifications.process_notifications import persist_notification
from app.notifications.validators import check_service_over_total_message_limit
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import DATETIME_FORMAT
from app.v2.errors import TotalRequestsError
from notifications_utils.recipients import RecipientCSV


@notify_celery.task(name="process-job")
def process_job(job_id, sender_id=None):
    """Update job status, get csv data from s3, and begin processing csv rows."""
    start = datetime.utcnow()
    job = dao_get_job_by_id(job_id)
    current_app.logger.info(
        "Starting process-job task for job id {} with status: {}".format(
            job_id, job.job_status
        )
    )

    if job.job_status != JobStatus.PENDING:
        return

    service = job.service

    job.job_status = JobStatus.IN_PROGRESS
    job.processing_started = start
    dao_update_job(job)

    if not service.active:
        job.job_status = JobStatus.CANCELLED
        dao_update_job(job)
        current_app.logger.warning(
            "Job {} has been cancelled, service {} is inactive".format(
                job_id, service.id
            )
        )
        return

    if __total_sending_limits_for_job_exceeded(service, job, job_id):
        return

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(
        job
    )

    current_app.logger.info(
        "Starting job {} processing {} notifications".format(
            job_id, job.notification_count
        )
    )

    for row in recipient_csv.get_rows():
        process_row(row, template, job, service, sender_id=sender_id)

    # End point/Exit point for message send flow.
    job_complete(job, start=start)


def job_complete(job, resumed=False, start=None):
    job.job_status = JobStatus.FINISHED

    finished = datetime.utcnow()
    job.processing_finished = finished
    dao_update_job(job)

    if resumed:
        current_app.logger.info(
            "Resumed Job {} completed at {}".format(job.id, job.created_at)
        )
    else:
        current_app.logger.info(
            "Job {} created at {} started at {} finished at {}".format(
                job.id, job.created_at, start, finished
            )
        )


def get_recipient_csv_and_template_and_sender_id(job):
    db_template = dao_get_template_by_id(job.template_id, job.template_version)
    template = db_template._as_utils_template()

    contents, meta_data = s3.get_job_and_metadata_from_s3(
        service_id=str(job.service_id), job_id=str(job.id)
    )
    recipient_csv = RecipientCSV(contents, template=template)

    return recipient_csv, template, meta_data.get("sender_id")


def process_row(row, template, job, service, sender_id=None):
    """Branch off based on notification type, sms or email."""
    template_type = template.template_type
    encrypted = encryption.encrypt(
        {
            "template": str(template.id),
            "template_version": job.template_version,
            "job": str(job.id),
            "to": row.recipient,
            "row_number": row.index,
            "personalisation": dict(row.personalisation),
        }
    )

    # Both save_sms and save_email have the same general
    # persist logic.
    send_fns = {NotificationType.SMS: save_sms, NotificationType.EMAIL: save_email}

    send_fn = send_fns[template_type]

    task_kwargs = {}
    if sender_id:
        task_kwargs["sender_id"] = sender_id

    notification_id = create_uuid()
    # Kick-off persisting notification in save_sms/save_email.
    send_fn.apply_async(
        (
            str(service.id),
            notification_id,
            encrypted,
        ),
        task_kwargs,
        queue=QueueNames.DATABASE,
    )
    return notification_id


def __total_sending_limits_for_job_exceeded(service, job, job_id):
    try:
        total_sent = check_service_over_total_message_limit(KeyType.NORMAL, service)
        if total_sent + job.notification_count > service.total_message_limit:
            raise TotalRequestsError(service.total_message_limit)
        else:
            return False
    except TotalRequestsError:
        job.job_status = "sending limits exceeded"
        job.processing_finished = datetime.utcnow()
        dao_update_job(job)
        current_app.logger.error(
            "Job {} size {} error. Total sending limits {} exceeded".format(
                job_id, job.notification_count, service.message_limit
            )
        )
        return True


@notify_celery.task(bind=True, name="save-sms", max_retries=5, default_retry_delay=300)
def save_sms(self, service_id, notification_id, encrypted_notification, sender_id=None):
    """Persist notification to db and place notification in queue to send to sns."""
    notification = encryption.decrypt(encrypted_notification)
    # SerialisedService and SerialisedTemplate classes are
    # used here to grab the same service and template from the cache
    # to improve performance.
    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_and_service_id(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    if sender_id:
        reply_to_text = dao_get_service_sms_senders_by_id(
            service_id, sender_id
        ).sms_sender
    else:
        reply_to_text = template.reply_to_text
    # Return False when trial mode services try sending notifications
    # to non-team and non-simulated recipients.
    if not service_allowed_to_send_to(notification["to"], service, KeyType.NORMAL):
        current_app.logger.debug(
            "SMS {} failed as restricted service".format(notification_id)
        )
        return

    try:
        job_id = notification.get("job", None)
        created_by_id = None
        if job_id:
            job = dao_get_job_by_id(job_id)
            created_by_id = job.created_by_id

        saved_notification = persist_notification(
            template_id=notification["template"],
            template_version=notification["template_version"],
            recipient=notification["to"],
            service=service,
            personalisation=notification.get("personalisation"),
            notification_type=NotificationType.SMS,
            api_key_id=None,
            key_type=KeyType.NORMAL,
            created_at=datetime.utcnow(),
            created_by_id=created_by_id,
            job_id=notification.get("job", None),
            job_row_number=notification.get("row_number", None),
            notification_id=notification_id,
            reply_to_text=reply_to_text,
        )

        # Kick off sns process in provider_tasks.py
        provider_tasks.deliver_sms.apply_async(
            [str(saved_notification.id)], queue=QueueNames.SEND_SMS
        )

        current_app.logger.debug(
            "SMS {} created at {} for job {}".format(
                saved_notification.id,
                saved_notification.created_at,
                notification.get("job", None),
            )
        )

    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(
    bind=True, name="save-email", max_retries=5, default_retry_delay=300
)
def save_email(
    self, service_id, notification_id, encrypted_notification, sender_id=None
):
    notification = encryption.decrypt(encrypted_notification)

    service = SerialisedService.from_id(service_id)
    template = SerialisedTemplate.from_id_and_service_id(
        notification["template"],
        service_id=service.id,
        version=notification["template_version"],
    )

    if sender_id:
        reply_to_text = dao_get_reply_to_by_id(service_id, sender_id).email_address
    else:
        reply_to_text = template.reply_to_text

    if not service_allowed_to_send_to(notification["to"], service, KeyType.NORMAL):
        current_app.logger.info(
            "Email {} failed as restricted service".format(notification_id)
        )
        return

    try:
        saved_notification = persist_notification(
            template_id=notification["template"],
            template_version=notification["template_version"],
            recipient=notification["to"],
            service=service,
            personalisation=notification.get("personalisation"),
            notification_type=NotificationType.EMAIL,
            api_key_id=None,
            key_type=KeyType.NORMAL,
            created_at=datetime.utcnow(),
            job_id=notification.get("job", None),
            job_row_number=notification.get("row_number", None),
            notification_id=notification_id,
            reply_to_text=reply_to_text,
        )

        provider_tasks.deliver_email.apply_async(
            [str(saved_notification.id)], queue=QueueNames.SEND_EMAIL
        )

        current_app.logger.debug(
            "Email {} created at {}".format(
                saved_notification.id, saved_notification.created_at
            )
        )
    except SQLAlchemyError as e:
        handle_exception(self, notification, notification_id, e)


@notify_celery.task(
    bind=True, name="save-api-email", max_retries=5, default_retry_delay=300
)
def save_api_email(self, encrypted_notification):
    save_api_email_or_sms(self, encrypted_notification)


@notify_celery.task(
    bind=True, name="save-api-sms", max_retries=5, default_retry_delay=300
)
def save_api_sms(self, encrypted_notification):
    save_api_email_or_sms(self, encrypted_notification)


def save_api_email_or_sms(self, encrypted_notification):
    notification = encryption.decrypt(encrypted_notification)
    service = SerialisedService.from_id(notification["service_id"])
    q = (
        QueueNames.SEND_EMAIL
        if notification["notification_type"] == NotificationType.EMAIL
        else QueueNames.SEND_SMS
    )
    provider_task = (
        provider_tasks.deliver_email
        if notification["notification_type"] == NotificationType.EMAIL
        else provider_tasks.deliver_sms
    )
    try:
        persist_notification(
            notification_id=notification["id"],
            template_id=notification["template_id"],
            template_version=notification["template_version"],
            recipient=notification["to"],
            service=service,
            personalisation=notification.get("personalisation"),
            notification_type=notification["notification_type"],
            client_reference=notification["client_reference"],
            api_key_id=notification.get("api_key_id"),
            key_type=KeyType.NORMAL,
            created_at=notification["created_at"],
            reply_to_text=notification["reply_to_text"],
            status=notification["status"],
            document_download_count=notification["document_download_count"],
        )

        provider_task.apply_async([notification["id"]], queue=q)
        current_app.logger.debug(
            f"{notification['notification_type']} {notification['id']} has been persisted and sent to delivery queue."
        )
    except IntegrityError:
        current_app.logger.info(
            f"{notification['notification_type']} {notification['id']} already exists."
        )

    except SQLAlchemyError:
        try:
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            current_app.logger.error(
                f"Max retry failed Failed to persist notification {notification['id']}"
            )


def handle_exception(task, notification, notification_id, exc):
    if not get_notification_by_id(notification_id):
        retry_msg = "{task} notification for job {job} row number {row} and notification id {noti}".format(
            task=task.__name__,
            job=notification.get("job", None),
            row=notification.get("row_number", None),
            noti=notification_id,
        )
        # Sometimes, SQS plays the same message twice. We should be able to catch an IntegrityError, but it seems
        # SQLAlchemy is throwing a FlushError. So we check if the notification id already exists then do not
        # send to the retry queue.
        # This probably (hopefully) is not an issue with Redis as the celery backing store
        current_app.logger.exception("Retry" + retry_msg)
        try:
            task.retry(queue=QueueNames.RETRY, exc=exc)
        except task.MaxRetriesExceededError:
            current_app.logger.error("Max retry failed" + retry_msg)


@notify_celery.task(
    bind=True, name="send-inbound-sms", max_retries=5, default_retry_delay=300
)
def send_inbound_sms_to_service(self, inbound_sms_id, service_id):
    inbound_api = get_service_inbound_api_for_service(service_id=service_id)
    if not inbound_api:
        # No API data has been set for this service
        return

    inbound_sms = dao_get_inbound_sms_by_id(
        service_id=service_id, inbound_id=inbound_sms_id
    )
    data = {
        "id": str(inbound_sms.id),
        # TODO: should we be validating and formatting the phone number here?
        "source_number": inbound_sms.user_number,
        "destination_number": inbound_sms.notify_number,
        "message": inbound_sms.content,
        "date_received": inbound_sms.provider_date.strftime(DATETIME_FORMAT),
    }

    try:
        response = request(
            method="POST",
            url=inbound_api.url,
            data=json.dumps(data),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(inbound_api.bearer_token),
            },
            timeout=60,
        )
        current_app.logger.debug(
            f"send_inbound_sms_to_service sending {inbound_sms_id} to {inbound_api.url}, "
            + f"response {response.status_code}"
        )
        response.raise_for_status()
    except RequestException as e:
        current_app.logger.warning(
            f"send_inbound_sms_to_service failed for service_id: {service_id} for inbound_sms_id: {inbound_sms_id} "
            + f"and url: {inbound_api.url}. exception: {e}"
        )
        if not isinstance(e, HTTPError) or e.response.status_code >= 500:
            try:
                self.retry(queue=QueueNames.RETRY)
            except self.MaxRetriesExceededError:
                current_app.logger.error(
                    "Retry: send_inbound_sms_to_service has retried the max number of"
                    + f"times for service: {service_id} and inbound_sms {inbound_sms_id}"
                )
        else:
            current_app.logger.warning(
                f"send_inbound_sms_to_service is not being retried for service_id: {service_id} for "
                + f"inbound_sms id: {inbound_sms_id} and url: {inbound_api.url}. exception: {e}"
            )


@notify_celery.task(name="process-incomplete-jobs")
def process_incomplete_jobs(job_ids):
    jobs = [dao_get_job_by_id(job_id) for job_id in job_ids]

    # reset the processing start time so that the check_job_status scheduled task doesn't pick this job up again
    for job in jobs:
        job.job_status = JobStatus.IN_PROGRESS
        job.processing_started = datetime.utcnow()
        dao_update_job(job)

    current_app.logger.info("Resuming Job(s) {}".format(job_ids))
    for job_id in job_ids:
        process_incomplete_job(job_id)


def process_incomplete_job(job_id):
    job = dao_get_job_by_id(job_id)

    last_notification_added = dao_get_last_notification_added_for_job_id(job_id)

    if last_notification_added:
        resume_from_row = last_notification_added.job_row_number
    else:
        resume_from_row = -1  # The first row in the csv with a number is row 0

    current_app.logger.info(
        "Resuming job {} from row {}".format(job_id, resume_from_row)
    )

    recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(
        job
    )

    for row in recipient_csv.get_rows():
        if row.index > resume_from_row:
            process_row(row, template, job, job.service, sender_id=sender_id)

    job_complete(job, resumed=True)
