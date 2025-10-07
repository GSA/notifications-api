import csv
import io
import json
import os
import time

import gevent
from celery.signals import task_postrun
from flask import current_app
from requests import HTTPError, RequestException, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_uuid, get_encryption, notify_celery
from app.aws import s3
from app.celery import provider_tasks
from app.config import Config, QueueNames
from app.dao import notifications_dao
from app.dao.inbound_sms_dao import dao_get_inbound_sms_by_id
from app.dao.jobs_dao import dao_get_job_by_id, dao_update_job
from app.dao.notifications_dao import (
    dao_get_last_notification_added_for_job_id,
    get_notification_by_id,
)
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_inbound_api_dao import get_service_inbound_api_for_service
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.dao.services_dao import dao_fetch_all_services, dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.enums import JobStatus, KeyType, NotificationType
from app.errors import TotalRequestsError
from app.notifications.process_notifications import (
    get_notification,
    persist_notification,
)
from app.notifications.validators import check_service_over_total_message_limit
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import DATETIME_FORMAT, hilite, utc_now
from notifications_utils.recipients import RecipientCSV

encryption = get_encryption()


@notify_celery.task(name="process-job")
def process_job(job_id, sender_id=None):
    """Update job status, get csv data from s3, and begin processing csv rows."""
    start = utc_now()
    job = dao_get_job_by_id(job_id)
    current_app.logger.info(
        f"Starting process-job task for job id {job_id} with status: {job.job_status}"
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
            f"Job {job_id} has been cancelled, service {service.id} is inactive".format(
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
        f"Starting job {job_id} processing {job.notification_count} notifications"
    )

    # notify-api-1495 we are going to sleep periodically to give other
    # jobs running at the same time a chance to get some of their messages
    # sent.  Sleep for 1 second after every 3 sends, which gives us throughput
    # of about 3600*3 per hour and would keep the queue clear assuming only one sender.
    # It will also hopefully eliminate throttling when we send messages which we are
    # currently seeing.
    count = 0
    for row in recipient_csv.get_rows():
        process_row(row, template, job, service, sender_id=sender_id)
        count = count + 1
        if count % 3 == 0:
            gevent.sleep(1)

    # End point/Exit point for message send flow.
    job_complete(job, start=start)


def job_complete(job, resumed=False, start=None):
    job.job_status = JobStatus.FINISHED

    finished = utc_now()
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
        expires=Config.DEFAULT_REDIS_EXPIRE_TIME,
    )
    return notification_id


# TODO
# Originally this was checking a daily limit
# It is now checking an overall limit (annual?) for the free tier
# Is there any limit for the paid tier?
# Assuming the limit is annual, is it calendar year, fiscal year, MOU year?
# Do we need a command to run to clear the redis value, or should it happen automatically?
def __total_sending_limits_for_job_exceeded(service, job, job_id):

    try:
        total_sent = check_service_over_total_message_limit(KeyType.NORMAL, service)
        if total_sent + job.notification_count > service.total_message_limit:
            raise TotalRequestsError(service.total_message_limit)
        else:
            return False
    except TotalRequestsError:
        job.job_status = "sending limits exceeded"
        job.processing_finished = utc_now()
        dao_update_job(job)
        current_app.logger.exception(
            "Job {} size {} error. Total sending limits {} exceeded".format(
                job_id, job.notification_count, service.total_message_limit
            ),
        )
        return True


@task_postrun.connect
def log_task_ejection(sender=None, task_id=None, **kwargs):
    current_app.logger.info(
        f"Task {task_id} ({sender.name if sender else 'unknown_task'}) has been completed and removed"
    )


@notify_celery.task(bind=True, name="save-sms", max_retries=2, default_retry_delay=600)
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
        current_app.logger.info(
            hilite(
                f"service not allowed to send for job_id {notification.get('job', None)}, aborting"
            )
        )
        current_app.logger.debug(f"SMS {notification_id} failed as restricted service")
        return

    try:
        job_id = notification.get("job", None)
        created_by_id = None
        if job_id:
            job = dao_get_job_by_id(job_id)
            created_by_id = job.created_by_id

        try:
            saved_notification = persist_notification(
                template_id=notification["template"],
                template_version=notification["template_version"],
                recipient=notification["to"],
                service=service,
                personalisation=notification.get("personalisation"),
                notification_type=NotificationType.SMS,
                api_key_id=None,
                key_type=KeyType.NORMAL,
                created_at=utc_now(),
                created_by_id=created_by_id,
                job_id=notification.get("job", None),
                job_row_number=notification.get("row_number", None),
                notification_id=notification_id,
                reply_to_text=reply_to_text,
            )
        except IntegrityError:
            current_app.logger.warning(
                f"{NotificationType.SMS}: {notification_id} already exists."
            )
            # If we don't have the return statement here, we will fall through and end
            # up retrying because IntegrityError is a subclass of SQLAlchemyError
            return

        # Kick off sns process in provider_tasks.py
        sn = saved_notification
        current_app.logger.info(
            hilite(
                f"Deliver sms for job_id: {sn.job_id} row_number: {sn.job_row_number}"
            )
        )
        provider_tasks.deliver_sms.apply_async(
            [str(saved_notification.id)], queue=QueueNames.SEND_SMS, countdown=60
        )

        current_app.logger.debug(
            f"SMS {saved_notification.id} created at {saved_notification.created_at} "
            f"for job {notification.get('job', None)}"
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
    original_notification = get_notification(notification_id)
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
            created_at=utc_now(),
            job_id=notification.get("job", None),
            job_row_number=notification.get("row_number", None),
            notification_id=notification_id,
            reply_to_text=reply_to_text,
        )
        # we only want to send once
        if original_notification is None:
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
    bind=True, name="save-api-sms", max_retries=2, default_retry_delay=600
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

    original_notification = get_notification(notification["id"])
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
        # Only get here if save to the db was successful (i.e. first time)
        if original_notification is None:
            provider_task.apply_async([notification["id"]], queue=q)
            current_app.logger.debug(
                f"{notification['id']} has been persisted and sent to delivery queue."
            )

    except IntegrityError:
        current_app.logger.warning(
            f"{notification['notification_type']} {notification['id']} already exists."
        )
        # If we don't have the return statement here, we will fall through and end
        # up retrying because IntegrityError is a subclass of SQLAlchemyError
        return

    except SQLAlchemyError:
        try:
            self.retry(queue=QueueNames.RETRY, expires=Config.DEFAULT_REDIS_EXPIRE_TIME)
        except self.MaxRetriesExceededError:
            current_app.logger.exception(
                f"Max retry failed Failed to persist notification {notification['id']}",
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
            task.retry(
                queue=QueueNames.RETRY,
                exc=exc,
                expires=Config.DEFAULT_REDIS_EXPIRE_TIME,
            )
        except task.MaxRetriesExceededError:
            current_app.logger.exception("Max retry failed" + retry_msg)


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
                self.retry(
                    queue=QueueNames.RETRY, expires=Config.DEFAULT_REDIS_EXPIRE_TIME
                )
            except self.MaxRetriesExceededError:
                current_app.logger.exception(
                    "Retry: send_inbound_sms_to_service has retried the max number of"
                    + f"times for service: {service_id} and inbound_sms {inbound_sms_id}"
                )
        else:
            current_app.logger.warning(
                f"send_inbound_sms_to_service is not being retried for service_id: {service_id} for "
                + f"inbound_sms id: {inbound_sms_id} and url: {inbound_api.url}. exception: {e}"
            )


@notify_celery.task(name="regenerate-job-cache")
def regenerate_job_cache():
    s3.get_s3_files()


@notify_celery.task(name="clean-job-cache")
def clean_job_cache():
    s3.clean_cache()


@notify_celery.task(name="delete-old-s3-objects")
def delete_old_s3_objects():

    existing_service_ids = s3.cleanup_old_s3_objects()
    service_names = []
    for service_id in existing_service_ids:
        service = dao_fetch_service_by_id(service_id)
        service_names.append(service.name)
    current_app.logger.info(
        f"#delete-old-s3-objects Services with retained csvs: {service_names}"
    )


@notify_celery.task(name="process-incomplete-jobs")
def process_incomplete_jobs(job_ids):
    jobs = [dao_get_job_by_id(job_id) for job_id in job_ids]

    # reset the processing start time so that the check_job_status scheduled task doesn't pick this job up again
    for job in jobs:
        job.job_status = JobStatus.IN_PROGRESS
        job.processing_started = utc_now()
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


def _generate_notifications_report(service_id, report_id, limit_days):

    # Hard code these values for now
    page = 1
    page_size = 20000
    include_jobs = True
    include_from_test_key = False
    include_one_off = True

    data = {
        "limit_days": limit_days,
        "include_jobs": True,
        "include_from_test_key": False,
        "include_one_off": True,
    }
    pagination = notifications_dao.get_notifications_for_service(
        service_id,
        filter_dict=data,
        page=page,
        page_size=page_size,
        count_pages=False,
        limit_days=limit_days,
        include_jobs=include_jobs,
        include_from_test_key=include_from_test_key,
        include_one_off=include_one_off,
    )
    count = 0
    if len(pagination.items) == 0:
        current_app.logger.info(f"SKIP {service_id}")

        # Delete stale report when there's no new data
        _, file_location, _, _, _ = get_csv_location(service_id, report_id)
        s3.delete_s3_object(file_location)
        current_app.logger.info(f"Deleted stale report {file_location} - no new data")

        return
    start_time = time.time()
    for notification in pagination.items:
        count = count + 1
        if notification.job_id is not None:

            notification.personalisation = s3.get_personalisation_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )

            recipient = s3.get_phone_number_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )

            notification.to = recipient
            notification.normalised_to = recipient

        else:
            notification.to = ""
            notification.normalised_to = ""

        current_app.logger.debug(
            hilite(
                f"Processing  row {count} for service {service_id} and days {limit_days}"
            )
        )

    notifications = [
        notification.serialize_for_csv() for notification in pagination.items
    ]

    current_app.logger.debug(hilite(f"RAW: {notifications}"))

    # We try and get the next page of results to work out if we need provide a pagination link to the next page
    # in our response if it exists. Note, this could be done instead by changing `count_pages` in the previous
    # call to be True which will enable us to use Flask-Sqlalchemy to tell if there is a next page of results but
    # this way is much more performant for services with many results (unlike Flask SqlAlchemy, this approach
    # doesn't do an additional query to count all the results of which there could be millions but instead only
    # asks for a single extra page of results).

    # These columns are in the raw data but we don't show them in the report
    columns_to_remove = {
        "created_by_email_address",
        "row_number",
        "client_reference",
        "template_type",
    }

    # cleanup for report presentation
    header_renames = {
        "recipient": "Phone Number",
        "template_name": "Template",
        "created_by_name": "Sent By",
        "carrier": "Carrier",
        "status": "Status",
        "created_at": "Time",
        "job_name": "Batch File",
        "provider_response": "Carrier Response",
    }

    processed_notifications = []
    for notification in notifications:
        new_notification = {}
        for old_key, new_key in header_renames.items():
            if old_key not in columns_to_remove and old_key in notification:
                new_notification[new_key] = notification[old_key]
        processed_notifications.append(new_notification)

    csv_bytes = io.BytesIO()
    text_stream = io.TextIOWrapper(csv_bytes, encoding="utf-8", newline="")
    writer = csv.DictWriter(text_stream, fieldnames=header_renames.values())
    writer.writeheader()
    writer.writerows(processed_notifications)
    text_stream.flush()
    csv_bytes.seek(0)

    bucket_name, file_location, access_key, secret_key, region = get_csv_location(
        service_id, report_id
    )

    current_app.logger.debug(
        hilite(f"REPORT {file_location} {csv_bytes.getvalue().decode('utf-8')}")
    )
    if bucket_name == "":
        exp_bucket = current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]
        exp_region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]
        tier = os.getenv("NOTIFY_ENVIRONMENT")
        raise Exception(
            f"No bucket name should be: {exp_bucket} with region {exp_region} and tier {tier}"
        )

    # Delete yesterday's version of this report
    s3.delete_s3_object(file_location)

    s3.s3upload(
        filedata=csv_bytes,
        region=region,
        bucket_name=bucket_name,
        file_location=file_location,
    )
    elapsed_time = str(time.time() - start_time)
    elapsed_time = elapsed_time.split(".")
    current_app.logger.info(
        hilite(
            f"generate-notifications-report uploaded {file_location} elapsed_time = {elapsed_time[0]} seconds"
        )
    )


@notify_celery.task(name="generate-notifications-reports")
def generate_notification_reports_task():
    services = dao_fetch_all_services(only_active=True)
    for service in services:

        limit_days = [1, 3, 5, 7]
        for limit_day in limit_days:

            report_id = f"{limit_day}-day-report"
            _generate_notifications_report(service.id, report_id, limit_day)
    current_app.logger.info("Notifications report generation complete")


NEW_FILE_LOCATION_STRUCTURE = "{}-service-notify/{}.csv"


def get_csv_location(service_id, upload_id):
    return (
        current_app.config["CSV_UPLOAD_BUCKET"]["bucket"],
        NEW_FILE_LOCATION_STRUCTURE.format(service_id, upload_id),
        current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"],
        current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"],
        current_app.config["CSV_UPLOAD_BUCKET"]["region"],
    )
