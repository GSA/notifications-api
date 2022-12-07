from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from hashlib import sha512

from botocore.exceptions import ClientError as BotoClientError
from flask import current_app
from notifications_utils.letter_timings import LETTER_PROCESSING_DEADLINE
from notifications_utils.postal_address import PostalAddress
from notifications_utils.timezones import convert_utc_to_local_timezone

from app import encryption, notify_celery
from app.aws import s3
from app.config import QueueNames, TaskNames
from app.cronitor import cronitor
from app.dao.notifications_dao import (
    dao_get_letters_and_sheets_volume_by_postage,
    dao_get_letters_to_be_printed,
    dao_get_notification_by_reference,
    dao_update_notification,
    dao_update_notifications_by_reference,
    get_notification_by_id,
    update_notification_status_by_id,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.errors import VirusScanError
from app.exceptions import NotificationTechnicalFailureException
from app.letters.utils import (
    LetterPDFNotFound,
    ScanErrorType,
    find_letter_pdf_in_s3,
    generate_letter_pdf_filename,
    get_billable_units_for_letter_page_count,
    get_file_names_from_error_bucket,
    get_folder_name,
    get_reference_from_filename,
    move_error_pdf_to_scan_bucket,
    move_failed_pdf,
    move_sanitised_letter_to_test_or_live_pdf_bucket,
    move_scan_to_invalid_pdf_bucket,
)
from app.models import (
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_POSTAGE_TYPES,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_VALIDATION_FAILED,
    NOTIFICATION_VIRUS_SCAN_FAILED,
    POSTAGE_TYPES,
    RESOLVE_POSTAGE_FOR_FILE_NAME,
    Service,
)


@notify_celery.task(bind=True, name='sanitise-letter', max_retries=15, default_retry_delay=300)
def sanitise_letter(self, filename):
    try:
        reference = get_reference_from_filename(filename)
        notification = dao_get_notification_by_reference(reference)

        current_app.logger.info('Notification ID {} Virus scan passed: {}'.format(notification.id, filename))

        if notification.status != NOTIFICATION_PENDING_VIRUS_CHECK:
            current_app.logger.info('Sanitise letter called for notification {} which is in {} state'.format(
                notification.id, notification.status))
            return

        notify_celery.send_task(
            name=TaskNames.SANITISE_LETTER,
            kwargs={
                'notification_id': str(notification.id),
                'filename': filename,
                'allow_international_letters': notification.service.has_permission(
                    INTERNATIONAL_LETTERS
                ),
            },
            queue=QueueNames.SANITISE_LETTERS,
        )
    except Exception:
        try:
            current_app.logger.exception(
                "RETRY: calling sanitise_letter task for notification {} failed".format(notification.id)
            )
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            message = "RETRY FAILED: Max retries reached. " \
                      "The task sanitise_letter failed for notification {}. " \
                      "Notification has been updated to technical-failure".format(notification.id)
            update_notification_status_by_id(notification.id, NOTIFICATION_TECHNICAL_FAILURE)
            raise NotificationTechnicalFailureException(message)
