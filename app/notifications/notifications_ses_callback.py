from datetime import timedelta

from flask import Blueprint, jsonify, request

from app.celery.process_ses_receipts_tasks import process_ses_results
from app.config import QueueNames
from app.errors import InvalidRequest
from app.notifications.sns_handlers import sns_notification_handler

ses_callback_blueprint = Blueprint('notifications_ses_callback', __name__)
DEFAULT_MAX_AGE = timedelta(days=10000)

# 400 counts as a permanent failure so SNS will not retry.
# 500 counts as a failed delivery attempt so SNS will retry.
# See https://docs.aws.amazon.com/sns/latest/dg/DeliveryPolicies.html#DeliveryPolicies
@ses_callback_blueprint.route('/notifications/email/ses', methods=['POST'])
def email_ses_callback_handler():
    try:
        data, _ = sns_notification_handler(request.data, request.headers)
    except InvalidRequest as e:
        return jsonify(
            result="error", message=str(e.message)
        ), e.status_code
    
    message = data.get("Message")
    if "mail" in message:
        process_ses_results.apply_async([{"Message": message}], queue=QueueNames.NOTIFY)

    return jsonify(
        result="success", message="SES-SNS callback succeeded"
    ), 200
