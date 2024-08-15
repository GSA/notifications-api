from flask import Blueprint, current_app, json, jsonify, request

from app.celery import tasks
from app.config import QueueNames
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.dao.services_dao import dao_fetch_service_by_inbound_number
from app.enums import ServicePermissionType
from app.errors import InvalidRequest, register_errors
from app.models import InboundSms
from app.notifications.sns_handlers import sns_notification_handler
from notifications_utils.recipients import try_validate_and_format_phone_number

receive_notifications_blueprint = Blueprint("receive_notifications", __name__)
register_errors(receive_notifications_blueprint)


@receive_notifications_blueprint.route(
    "/notifications/sms/receive/sns", methods=["POST"]
)
def receive_sns_sms():
    """
    Expected value of the 'Message' key in the incoming payload from SNS
    {
        "originationNumber":"+14255550182",
        "destinationNumber":"+12125550101",
        "messageKeyword":"JOIN", # unique to our sending number
        "messageBody":"EXAMPLE",
        "inboundMessageId":"cae173d2-66b9-564c-8309-21f858e9fb84",
        "previousPublishedMessageId":"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    }
    """

    # Whether or not to ignore inbound SMS replies
    if not current_app.config["RECEIVE_INBOUND_SMS"]:
        return jsonify(result="success", message="SMS-SNS callback succeeded"), 200

    try:
        post_data = sns_notification_handler(request.data, request.headers)
    except Exception as e:
        raise InvalidRequest(f"SMS-SNS callback failed with error: {e}", 400)

    message = json.loads(post_data.get("Message"))
    # TODO wrap this up
    if "inboundMessageId" in message:
        # TODO use standard formatting we use for all US numbers
        inbound_number = message["destinationNumber"].replace("+", "")

        service = fetch_potential_service(inbound_number, "sns")
        if not service:
            # since this is an issue with our service <-> number mapping, or no inbound_sms service permission
            # we should still tell SNS that we received it successfully
            current_app.logger.warning(
                f"Mapping between service and inbound number: {inbound_number} is broken, "
                f"or service does not have permission to receive inbound sms"
            )
            return jsonify(result="success", message="SMS-SNS callback succeeded"), 200

        inbound = create_inbound_sms_object(
            service,
            content=message.get("messageBody"),
            from_number=message.get("originationNumber"),
            provider_ref=message.get("inboundMessageId"),
            date_received=post_data.get("Timestamp"),
            provider_name="sns",
        )

        tasks.send_inbound_sms_to_service.apply_async(
            [str(inbound.id), str(service.id)], queue=QueueNames.NOTIFY
        )

        current_app.logger.debug(
            "{} received inbound SMS with reference {} from SNS".format(
                service.id, inbound.provider_reference
            )
        )

    return jsonify(result="success", message="SMS-SNS callback succeeded"), 200


def unescape_string(string):
    return string.encode("raw_unicode_escape").decode("unicode_escape")


def create_inbound_sms_object(
    service, content, from_number, provider_ref, date_received, provider_name
):
    user_number = try_validate_and_format_phone_number(
        from_number,
        international=True,
        log_msg=f'Invalid from_number received for service "{service.id}"',
    )

    provider_date = date_received
    inbound = InboundSms(
        service=service,
        notify_number=service.get_inbound_number(),
        user_number=user_number,
        provider_date=provider_date,
        provider_reference=provider_ref,
        content=content,
        provider=provider_name,
    )
    dao_create_inbound_sms(inbound)
    return inbound


def fetch_potential_service(inbound_number, provider_name):
    service = dao_fetch_service_by_inbound_number(inbound_number)

    if not service:
        current_app.logger.warning(
            'Inbound number "{}" from {} not associated with a service'.format(
                inbound_number, provider_name
            )
        )
        return False

    if not has_inbound_sms_permissions(service.permissions):
        current_app.logger.error(
            'Service "{}" does not allow inbound SMS'.format(service.id), exc_info=True
        )
        return False

    return service


def has_inbound_sms_permissions(permissions):
    str_permissions = [p.permission for p in permissions]
    return {ServicePermissionType.INBOUND_SMS, ServicePermissionType.SMS}.issubset(
        set(str_permissions)
    )
