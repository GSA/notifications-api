import enum
from datetime import datetime, timedelta
from json import decoder

import iso8601
import requests
import validatesns
from celery.exceptions import Retry
from flask import Blueprint, current_app, json, jsonify, request
from notifications_utils.statsd_decorators import statsd
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery, redis_store, statsd_client
from app.config import QueueNames
from app.dao import notifications_dao
from app.errors import InvalidRequest, register_errors
from app.models import NOTIFICATION_PENDING, NOTIFICATION_SENDING
from app.notifications.notifications_ses_callback import (
    _check_and_queue_complaint_callback_task,
    _determine_notification_bounce_type,
    check_and_queue_callback_task,
    get_aws_responses,
    handle_complaint,
)

ses_callback_blueprint = Blueprint('notifications_ses_callback', __name__)

register_errors(ses_callback_blueprint)

class SNSMessageType(enum.Enum):
    SubscriptionConfirmation = 'SubscriptionConfirmation'
    Notification = 'Notification'
    UnsubscribeConfirmation = 'UnsubscribeConfirmation'


class InvalidMessageTypeException(Exception):
    pass


def verify_message_type(message_type: str):
    try:
        SNSMessageType(message_type)
    except ValueError:
        raise InvalidMessageTypeException(f'{message_type} is not a valid message type.')


def get_certificate(url):
    res = redis_store.get(url)
    if res is not None:
        return res
    res = requests.get(url).content
    redis_store.set(url, res, ex=60 * 60)  # 60 minutes
    return res

# 400 counts as a permanent failure so SNS will not retry.
# 500 counts as a failed delivery attempt so SNS will retry.
# See https://docs.aws.amazon.com/sns/latest/dg/DeliveryPolicies.html#DeliveryPolicies
# This should not be here, it used to be in notifications/notifications_ses_callback. It then
# got refactored into a task, which is fine, but it created a circular dependency. Will need
# to investigate why GDS extracted this into a lambda
@ses_callback_blueprint.route('/notifications/email/ses', methods=['POST'])
def sns_callback_handler():
    message_type = request.headers.get('x-amz-sns-message-type')
    try:
        verify_message_type(message_type)
    except InvalidMessageTypeException:
        raise InvalidRequest("SES-SNS callback failed: invalid message type", 400)

    try:
        message = json.loads(request.data)
    except decoder.JSONDecodeError:
        raise InvalidRequest("SES-SNS callback failed: invalid JSON given", 400)

    try:
        validatesns.validate(message, get_certificate=get_certificate)
    except validatesns.ValidationError:
        raise InvalidRequest("SES-SNS callback failed: validation failed", 400)

    if message.get('Type') == 'SubscriptionConfirmation':
        url = message.get('SubscribeURL')
        response = requests.get(url)
        try:
            response.raise_for_status()
        except Exception as e:
            current_app.logger.warning("Response: {}".format(response.text))
            raise e

        return jsonify(
            result="success", message="SES-SNS auto-confirm callback succeeded"
        ), 200

    process_ses_results.apply_async([{"Message": message.get("Message")}], queue=QueueNames.NOTIFY)

    return jsonify(
        result="success", message="SES-SNS callback succeeded"
    ), 200


@notify_celery.task(bind=True, name="process-ses-result", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def process_ses_results(self, response):
    try:
        ses_message = json.loads(response["Message"])
        notification_type = ses_message["notificationType"]
        print(f"ses_message is: {ses_message}")
        if notification_type == "Complaint":
            _check_and_queue_complaint_callback_task(*handle_complaint(ses_message))
            return True

        aws_response_dict = get_aws_responses(ses_message)

        notification_status = aws_response_dict["notification_status"]
        reference = ses_message["mail"]["messageId"]
        
        print(f"notification_status is: {notification_status}")

        try:
            notification = notifications_dao.dao_get_notification_by_reference(reference)
        except NoResultFound:
            message_time = iso8601.parse_date(ses_message["mail"]["timestamp"]).replace(tzinfo=None)
            if datetime.utcnow() - message_time < timedelta(minutes=5):
                self.retry(queue=QueueNames.RETRY)
            else:
                current_app.logger.warning(
                    "notification not found for reference: {} (update to {})".format(reference, notification_status)
                )
            return

        if notification.status not in {NOTIFICATION_SENDING, NOTIFICATION_PENDING}:
            notifications_dao._duplicate_update_warning(
                notification, 
                notification_status
            )
            return

        notifications_dao._update_notification_status(
            notification=notification,
            status=notification_status,
            provider_response=aws_response_dict["provider_response"],
        )

        if not aws_response_dict["success"]:
            current_app.logger.info(
                "SES delivery failed: notification id {} and reference {} has error found. Status {}".format(
                    notification.id, reference, aws_response_dict["message"]
                )
            )
        else:
            current_app.logger.info(
                "SES callback return status of {} for notification: {}".format(notification_status, notification.id)
            )

        statsd_client.incr("callback.ses.{}".format(notification_status))

        if notification.sent_at:
            statsd_client.timing_with_dates("callback.ses.elapsed-time", datetime.utcnow(), notification.sent_at)

        check_and_queue_callback_task(notification)

        return True

    except Retry:
        raise

    except Exception as e:
        current_app.logger.exception("Error processing SES results: {}".format(type(e)))
        self.retry(queue=QueueNames.RETRY)

# def process_ses_results(self, response):
#     try:
#         ses_message = json.loads(response['Message'])
#         print(f"ses_message is {ses_message}")
#         notification_type = ses_message['notificationType']
#         print(f"notification_type is {notification_type}")
#         if notification_type == 'Bounce':
#             notification_type = _determine_notification_bounce_type(ses_message)
#         elif notification_type == 'Complaint':
#             _check_and_queue_complaint_callback_task(*handle_complaint(ses_message))
#             return True
#         aws_response_dict = get_aws_responses(notification_type)
#         print(f"aws_response_dict is {aws_response_dict}")
#         notification_status = aws_response_dict['notification_status']
#         print(f"notification_status is {notification_status}")
#         reference = ses_message['mail']['messageId']
#         try:
#             notification = notifications_dao.dao_get_notification_by_reference(reference)
#             print(f"notification is {notification}")
#         except NoResultFound:
#             print(f"notification not found")
#             message_time = iso8601.parse_date(ses_message['mail']['timestamp']).replace(tzinfo=None)
#             if datetime.utcnow() - message_time < timedelta(minutes=5):
#                 self.retry(queue=QueueNames.RETRY)
#             else:
#                 current_app.logger.warning(
#                     "notification not found for reference: {} (update to {})".format(reference, notification_status)
#                 )
#             return
#         print(f"notification.status is {notification.status}")
#         if notification.status not in {NOTIFICATION_SENDING, NOTIFICATION_PENDING}:
#             print(f"notification.status is not in [{NOTIFICATION_SENDING}, {NOTIFICATION_PENDING}]")
#             notifications_dao._duplicate_update_warning(notification, notification_status)
#             return
#         notifications_dao._update_notification_status(
#             notification=notification, 
#             status=notification_status, 
#             provider_response=None
#         )
#         if not aws_response_dict['success']:
#             current_app.logger.info(
#                 "SES delivery failed: notification id {} and reference {} has error found. Status {}".format(
#                     notification.id, reference, aws_response_dict['message']
#                 )
#             )
#             print(
#                 "SES delivery failed: notification id {} and reference {} has error found. Status {}".format(
#                     notification.id, reference, aws_response_dict['message']
#                 )
#             )
#         else:
#             current_app.logger.info('SES callback return status of {} for notification: {}'.format(
#                 notification_status, notification.id
#             ))
#             print('SES callback return status of {} for notification: {}'.format(
#                 notification_status, notification.id
#             ))
#         statsd_client.incr('callback.ses.{}'.format(notification_status))
#         if notification.sent_at:
#             statsd_client.timing_with_dates('callback.ses.elapsed-time', datetime.utcnow(), notification.sent_at)
#         check_and_queue_callback_task(notification)
#         return True
#     except Retry:
#         raise
#     except Exception as e:
#         current_app.logger.exception('Error processing SES results: {}'.format(type(e)))
#         self.retry(queue=QueueNames.RETRY)
        