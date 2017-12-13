from datetime import datetime
from flask import current_app
import math
from requests import (
    post as requests_post,
    RequestException
)

from botocore.exceptions import ClientError as BotoClientError

from app import notify_celery
from app.aws import s3
from app.config import QueueNames
from app.dao.notifications_dao import (
    get_notification_by_id,
    update_notification_status_by_id,
    dao_update_notifications_by_reference
)
from app.statsd_decorators import statsd


@notify_celery.task(bind=True, name="create-letters-pdf", max_retries=15, default_retry_delay=300)
@statsd(namespace="tasks")
def create_letters_pdf(self, notification_id):
    try:
        notification = get_notification_by_id(notification_id, _raise=True)

        pdf_data, billable_units = get_letters_pdf(
            notification.template,
            contact_block=notification.reply_to_text,
            org_id=notification.service.dvla_organisation.id,
            values=notification.personalisation
        )
        current_app.logger.info("PDF Letter {} reference {} created at {}, {} bytes".format(
            notification.id, notification.reference, notification.created_at, len(pdf_data)))
        s3.upload_letters_pdf(reference=notification.reference, crown=notification.service.crown, filedata=pdf_data)

        updated_count = dao_update_notifications_by_reference(
            references=[notification.reference],
            update_dict={
                "billable_units": billable_units,
                "updated_at": datetime.utcnow()
            }
        )

        if not updated_count:
            msg = "Update letter notification billing units failed: notification not found with reference {}".format(
                notification.reference)
            current_app.logger.error(msg)
        else:
            current_app.logger.info(
                'Letter notification reference {reference}: billable units set to {billable_units}'.format(
                    reference=str(notification.reference), billable_units=billable_units))

    except (RequestException, BotoClientError):
        try:
            current_app.logger.exception(
                "Letters PDF notification creation for id: {} failed".format(notification_id)
            )
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            current_app.logger.exception(
                "RETRY FAILED: task create_letters_pdf failed for notification {}".format(notification_id),
            )
            update_notification_status_by_id(notification_id, 'technical-failure')


def get_letters_pdf(template, contact_block, org_id, values):
    template_for_letter_print = {
        "subject": template.subject,
        "content": template.content
    }

    data = {
        'letter_contact_block': contact_block,
        'template': template_for_letter_print,
        'values': values,
        'dvla_org_id': org_id,
    }
    resp = requests_post(
        '{}/print.pdf'.format(
            current_app.config['TEMPLATE_PREVIEW_API_HOST']
        ),
        json=data,
        headers={'Authorization': 'Token {}'.format(current_app.config['TEMPLATE_PREVIEW_API_KEY'])}
    )
    resp.raise_for_status()

    pages_per_sheet = 2
    billable_units = math.ceil(int(resp.headers.get("X-pdf-page-count", 0)) / pages_per_sheet)

    return resp.content, billable_units
