import json
import os

from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadData, SignatureExpired

from app import redis_store
from app.config import QueueNames
from app.dao.invited_org_user_dao import (
    get_invited_org_user as dao_get_invited_org_user,
)
from app.dao.invited_org_user_dao import (
    get_invited_org_user_by_id,
    get_invited_org_users_for_organization,
    save_invited_org_user,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.enums import KeyType, NotificationType
from app.errors import InvalidRequest, register_errors
from app.models import InvitedOrganizationUser
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.organization.organization_schema import (
    post_create_invited_org_user_status_schema,
    post_update_invited_org_user_status_schema,
)
from app.schema_validation import validate
from app.utils import check_suspicious_id
from notifications_utils.url_safe_token import check_token, generate_token

organization_invite_blueprint = Blueprint("organization_invite", __name__)

register_errors(organization_invite_blueprint)


@organization_invite_blueprint.route(
    "/organization/<uuid:organization_id>/invite", methods=["POST"]
)
def invite_user_to_org(organization_id):
    check_suspicious_id(organization_id)
    data = request.get_json()
    validate(data, post_create_invited_org_user_status_schema)

    invited_org_user = InvitedOrganizationUser(
        email_address=data["email_address"],
        invited_by_id=data["invited_by"],
        organization_id=organization_id,
    )
    save_invited_org_user(invited_org_user)

    template = dao_get_template_by_id(
        current_app.config["ORGANIZATION_INVITATION_EMAIL_TEMPLATE_ID"]
    )

    token = generate_token(
        str(invited_org_user.email_address),
        current_app.config["SECRET_KEY"],
        current_app.config["DANGEROUS_SALT"],
    )
    url = os.environ["LOGIN_DOT_GOV_REGISTRATION_URL"]
    url = url.replace("NONCE", token)
    url = url.replace("STATE", token)

    personalisation = {
        "user_name": (
            "The Notify.gov team"
            if invited_org_user.invited_by.platform_admin
            else invited_org_user.invited_by.name
        ),
        "organization_name": invited_org_user.organization.name,
        "url": url,
    }
    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=invited_org_user.email_address,
        service=template.service,
        personalisation={},
        notification_type=NotificationType.EMAIL,
        api_key_id=None,
        key_type=KeyType.NORMAL,
        reply_to_text=invited_org_user.invited_by.email_address,
    )

    saved_notification.personalisation = personalisation
    redis_store.set(
        f"email-personalisation-{saved_notification.id}",
        json.dumps(personalisation),
        ex=1800,
    )

    send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    return jsonify(data=invited_org_user.serialize()), 201


@organization_invite_blueprint.route(
    "/organization/<uuid:organization_id>/invite", methods=["GET"]
)
def get_invited_org_users_by_organization(organization_id):

    check_suspicious_id(organization_id)
    invited_org_users = get_invited_org_users_for_organization(organization_id)
    return jsonify(data=[x.serialize() for x in invited_org_users]), 200


@organization_invite_blueprint.route(
    "/organization/<uuid:organization_id>/invite/<invited_org_user_id>", methods=["GET"]
)
def get_invited_org_user_by_organization(organization_id, invited_org_user_id):
    check_suspicious_id(organization_id, invited_org_user_id)
    invited_org_user = dao_get_invited_org_user(organization_id, invited_org_user_id)
    return jsonify(data=invited_org_user.serialize()), 200


@organization_invite_blueprint.route(
    "/organization/<uuid:organization_id>/invite/<invited_org_user_id>",
    methods=["POST"],
)
def update_org_invite_status(organization_id, invited_org_user_id):
    check_suspicious_id(organization_id, invited_org_user_id)
    fetched = dao_get_invited_org_user(
        organization_id=organization_id, invited_org_user_id=invited_org_user_id
    )

    data = request.get_json()
    validate(data, post_update_invited_org_user_status_schema)

    fetched.status = data["status"]
    save_invited_org_user(fetched)

    return jsonify(data=fetched.serialize()), 200


def invited_org_user_url(invited_org_user_id, invite_link_host=None):

    token = generate_token(
        str(invited_org_user_id),
        current_app.config["SECRET_KEY"],
        current_app.config["DANGEROUS_SALT"],
    )

    if invite_link_host is None:
        invite_link_host = current_app.config["ADMIN_BASE_URL"]

    return "{0}/organization-invitation/{1}".format(invite_link_host, token)


@organization_invite_blueprint.route(
    "/invite/organization/<uuid:invited_org_user_id>", methods=["GET"]
)
def get_invited_org_user(invited_org_user_id):
    check_suspicious_id(invited_org_user_id)
    invited_user = get_invited_org_user_by_id(invited_org_user_id)
    return jsonify(data=invited_user.serialize()), 200


@organization_invite_blueprint.route("/invite/organization/<token>", methods=["GET"])
@organization_invite_blueprint.route(
    "/invite/organization/check/<token>", methods=["GET"]
)
def validate_invitation_token(token):
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

    invited_user = get_invited_org_user_by_id(invited_user_id)
    return jsonify(data=invited_user.serialize()), 200
