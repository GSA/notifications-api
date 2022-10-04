import enum
from datetime import timedelta

from flask import Blueprint, current_app, json, jsonify, request

from app.celery.process_ses_receipts_tasks import process_ses_results
from app.celery.service_callback_tasks import (
    create_complaint_callback_data,
    create_delivery_status_callback_data,
    send_complaint_to_service,
    send_delivery_status_to_service,
)
from app.config import QueueNames
from app.dao.complaint_dao import save_complaint
from app.dao.notifications_dao import dao_get_notification_history_by_reference
from app.dao.service_callback_api_dao import (
    get_service_complaint_callback_api_for_service,
    get_service_delivery_status_callback_api_for_service,
)
from app.errors import InvalidRequest
from app.models import Complaint
from app.notifications.callbacks import create_complaint_callback_data
from app.notifications.sns_handlers import sns_notification_handler

ses_callback_blueprint = Blueprint('notifications_ses_callback', __name__)
DEFAULT_MAX_AGE = timedelta(days=10000)

# 400 counts as a permanent failure so SNS will not retry.
# 500 counts as a failed delivery attempt so SNS will retry.
# See https://docs.aws.amazon.com/sns/latest/dg/DeliveryPolicies.html#DeliveryPolicies
@ses_callback_blueprint.route('/notifications/email/ses', methods=['POST'])
def email_ses_callback_handler():
    try:
        data = sns_notification_handler(request.data, request.headers)
    except Exception as e:
        raise InvalidRequest("SES-SNS callback failed: invalid message type", 400)
    
    message = data.get("Message")
    if "mail" in message:
        process_ses_results.apply_async([{"Message": message}], queue=QueueNames.NOTIFY)

    return jsonify(
        result="success", message="SES-SNS callback succeeded"
    ), 200
