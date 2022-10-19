import uuid
from datetime import datetime

from flask import current_app
from notifications_utils.template import SMSMessageTemplate

from app import notify_celery, statsd_client
from app.celery.process_ses_receipts_tasks import check_and_queue_callback_task
from app.clients import ClientException
from app.dao import notifications_dao
from app.dao.templates_dao import dao_get_template_by_id
from app.models import NOTIFICATION_PENDING

sms_response_mapper = {
    # 'MMG': get_mmg_responses,
    # 'Firetext': get_firetext_responses,
}


# gUpdate with new providers")
@notify_celery.task(bind=True, name="process-sms-client-response", max_retries=5, default_retry_delay=300)
def process_sms_client_response(self, status, provider_reference, client_name, detailed_status_code=None):
    # validate reference
    try:
        uuid.UUID(provider_reference, version=4)
    except ValueError as e:
        current_app.logger.exception(f'{client_name} callback with invalid reference {provider_reference}')
        raise e

    response_parser = sms_response_mapper[client_name]

    # validate status
    try:
        notification_status, detailed_status = response_parser(status, detailed_status_code)
        current_app.logger.info(
            f'{client_name} callback returned status of {notification_status}'
            f'({status}): {detailed_status}({detailed_status_code}) for reference: {provider_reference}'
        )
    except KeyError:
        _process_for_status(
            notification_status='technical-failure',
            client_name=client_name,
            provider_reference=provider_reference
        )
        raise ClientException(f'{client_name} callback failed: status {status} not found.')

    _process_for_status(
        notification_status=notification_status,
        client_name=client_name,
        provider_reference=provider_reference,
        detailed_status_code=detailed_status_code
    )


def _process_for_status(notification_status, client_name, provider_reference, detailed_status_code=None):
    # record stats
    notification = notifications_dao.update_notification_status_by_id(
        notification_id=provider_reference,
        status=notification_status,
        sent_by=client_name.lower(),
        detailed_status_code=detailed_status_code
    )
    if not notification:
        return

    statsd_client.incr('callback.{}.{}'.format(client_name.lower(), notification_status))

    if notification.sent_at:
        statsd_client.timing_with_dates(
            f'callback.{client_name.lower()}.{notification_status}.elapsed-time',
            datetime.utcnow(),
            notification.sent_at
        )

    if notification.billable_units == 0:
        service = notification.service
        template_model = dao_get_template_by_id(notification.template_id, notification.template_version)

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=service.name,
            show_prefix=service.prefix_sms,
        )
        notification.billable_units = template.fragment_count
        notifications_dao.dao_update_notification(notification)

    if notification_status != NOTIFICATION_PENDING:
        check_and_queue_callback_task(notification)
