import base64
import json
import os
from urllib.parse import unquote

from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadData, SignatureExpired

from app import db, redis_store
from app.config import QueueNames
from app.dao.invited_user_dao import (
    get_expired_invite_by_service_and_id,
    get_expired_invited_users_for_service,
    get_invited_user_by_id,
    get_invited_user_by_service_and_id,
    get_invited_users_for_service,
    save_invited_user,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.enums import InvitedUserStatus, KeyType, NotificationType
from app.errors import InvalidRequest, register_errors
from app.models import Service
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.schemas import invited_user_schema
from app.utils import utc_now
from notifications_utils.url_safe_token import check_token, generate_token

service_invite = Blueprint("service_invite", __name__)

register_errors(service_invite)


def _create_service_invite(invited_user, nonce, state):

    template_id = current_app.config["INVITATION_EMAIL_TEMPLATE_ID"]

    template = dao_get_template_by_id(template_id)

    service = db.session.get(Service, current_app.config["NOTIFY_SERVICE_ID"])

    # The raw permissions are in the form "a,b,c,d"
    # but need to be in the form ["a", "b", "c", "d"]
    data = {}
    permissions = invited_user.permissions
    permissions = permissions.split(",")
    data["from_user_id"] = str(invited_user.from_user.id)
    data["service_id"] = str(invited_user.service.id)
    data["permissions"] = permissions
    data["folder_permissions"] = invited_user.folder_permissions
    data["invited_user_id"] = str(invited_user.id)
    data["invited_user_email"] = invited_user.email_address

    invite_redis_key = f"invite-data-{unquote(state)}"
    redis_store.set(invite_redis_key, get_user_data_url_safe(data), ex=2 * 24 * 60 * 60)

    url = os.environ["LOGIN_DOT_GOV_REGISTRATION_URL"]

    url = url.replace("NONCE", nonce)  # handed from data sent from admin.

    url = url.replace("STATE", state)

    personalisation = {
        "user_name": invited_user.from_user.name,
        "service_name": invited_user.service.name,
        "url": url,
    }

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=invited_user.email_address,
        service=service,
        personalisation={},
        notification_type=NotificationType.EMAIL,
        api_key_id=None,
        key_type=KeyType.NORMAL,
        reply_to_text=invited_user.from_user.email_address,
    )
    saved_notification.personalisation = personalisation
    redis_store.set(
        f"email-personalisation-{saved_notification.id}",
        json.dumps(personalisation),
        ex=2 * 24 * 60 * 60,
    )
    send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    return data


@service_invite.route("/service/<service_id>/invite", methods=["POST"])
def create_invited_user(service_id):
    request_json = request.get_json()
    try:
        nonce = request_json.pop("nonce")
    except KeyError:
        current_app.logger.exception("nonce not found in submitted data.")
        raise
    try:
        state = request_json.pop("state")
    except KeyError:
        current_app.logger.exception("state not found in submitted data.")
        raise

    invited_user = invited_user_schema.load(request_json)
    save_invited_user(invited_user)

    invite_data = _create_service_invite(invited_user, nonce, state)

    return jsonify(data=invited_user_schema.dump(invited_user), invite=invite_data), 201


@service_invite.route("/service/<service_id>/invite/expired", methods=["GET"])
def get_expired_invited_users_by_service(service_id):
    expired_invited_users = get_expired_invited_users_for_service(service_id)
    return jsonify(data=invited_user_schema.dump(expired_invited_users, many=True)), 200


@service_invite.route("/service/<service_id>/invite", methods=["GET"])
def get_invited_users_by_service(service_id):
    invited_users = get_invited_users_for_service(service_id)
    return jsonify(data=invited_user_schema.dump(invited_users, many=True)), 200


@service_invite.route("/service/<service_id>/invite/<invited_user_id>", methods=["GET"])
def get_invited_user_by_service(service_id, invited_user_id):
    invited_user = get_invited_user_by_service_and_id(service_id, invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


@service_invite.route(
    "/service/<service_id>/invite/<invited_user_id>", methods=["POST"]
)
def update_invited_user(service_id, invited_user_id):
    fetched = get_invited_user_by_service_and_id(
        service_id=service_id, invited_user_id=invited_user_id
    )

    current_data = dict(invited_user_schema.dump(fetched).items())
    current_data.update(request.get_json())
    update_dict = invited_user_schema.load(current_data)
    save_invited_user(update_dict)
    return jsonify(data=invited_user_schema.dump(fetched)), 200


@service_invite.route(
    "/service/<service_id>/invite/<invited_user_id>/resend", methods=["POST"]
)
def resend_service_invite(service_id, invited_user_id):
    """Resend an expired invite.

    This resets the invited user's created date and status to make it a new invite, and
    sends the new invite out to the user.

    Note:
        This ignores the POST data entirely.
    """
    request_json = request.get_json()
    try:
        nonce = request_json.pop("nonce")
    except KeyError:
        current_app.logger.exception("nonce not found in submitted data.")
        raise
    try:
        state = request_json.pop("state")
    except KeyError:
        current_app.logger.exception("state not found in submitted data.")
        raise

    fetched = get_expired_invite_by_service_and_id(
        service_id=service_id,
        invited_user_id=invited_user_id,
    )

    fetched.created_at = utc_now()
    fetched.status = InvitedUserStatus.PENDING

    current_data = {k: v for k, v in invited_user_schema.dump(fetched).items()}
    update_dict = invited_user_schema.load(current_data)

    save_invited_user(update_dict)

    invite_data = _create_service_invite(fetched, nonce, state)

    return jsonify(data=invited_user_schema.dump(fetched), invite=invite_data), 200


def invited_user_url(invited_user_id, invite_link_host=None):
    token = generate_token(
        str(invited_user_id),
        current_app.config["SECRET_KEY"],
        current_app.config["DANGEROUS_SALT"],
    )

    if invite_link_host is None:
        invite_link_host = current_app.config["ADMIN_BASE_URL"]

    return "{0}/invitation/{1}".format(invite_link_host, token)


@service_invite.route("/invite/service/<uuid:invited_user_id>", methods=["GET"])
def get_invited_user(invited_user_id):
    invited_user = get_invited_user_by_id(invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


@service_invite.route("/invite/service/<token>", methods=["GET"])
@service_invite.route("/invite/service/check/<token>", methods=["GET"])
def validate_service_invitation_token(token):
    max_age_seconds = 60 * 60 * 24 * current_app.config["INVITATION_EXPIRATION_DAYS"]

    try:
        invited_user_id = check_token(
            token,
            current_app.config["SECRET_KEY"],
            current_app.config["DANGEROUS_SALT"],
            max_age_seconds,
        )
    except SignatureExpired:
        errors = {
            "invitation": "Your invitation to Notify.gov has expired. "
            "Please ask the person that invited you to send you another one"
        }
        raise InvalidRequest(errors, status_code=400)
    except BadData:
        errors = {
            "invitation": "Something’s wrong with this link. Make sure you’ve copied the whole thing."
        }
        raise InvalidRequest(errors, status_code=400)

    invited_user = get_invited_user_by_id(invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


def get_user_data_url_safe(data):
    data = json.dumps(data)
    data = base64.b64encode(data.encode("utf8"))
    return data.decode("utf8")
