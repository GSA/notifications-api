import json
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from app import redis_store
from app.config import QueueNames
from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.dao_utils import transaction
from app.dao.fact_billing_dao import fetch_usage_year_for_organization
from app.dao.notifications_dao import (
    dao_get_notification_counts_per_service,
    dao_get_recent_sms_template_per_service,
)
from app.dao.organization_dao import (
    dao_add_service_to_organization,
    dao_add_user_to_organization,
    dao_create_organization,
    dao_get_organization_by_email_address,
    dao_get_organization_by_id,
    dao_get_organization_services,
    dao_get_organizations,
    dao_get_users_for_organization,
    dao_remove_user_from_organization,
    dao_update_organization,
)
from app.dao.services_dao import (
    dao_fetch_service_by_id,
    dao_get_service_primary_contacts,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.users_dao import get_user_by_id
from app.enums import KeyType
from app.errors import InvalidRequest, register_errors
from app.models import Organization
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.organization.organization_schema import (
    post_create_organization_schema,
    post_link_service_to_organization_schema,
    post_update_organization_schema,
)
from app.schema_validation import validate
from app.utils import check_suspicious_id

organization_blueprint = Blueprint("organization", __name__)
register_errors(organization_blueprint)


@organization_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint on ix_organization_name
    """
    current_app.logger.exception("Handling integrity error")
    if "ix_organization_name" in str(exc):
        return jsonify(result="error", message="Organization name already exists"), 400
    if 'duplicate key value violates unique constraint "domain_pkey"' in str(exc):
        return jsonify(result="error", message="Domain already exists"), 400

    return jsonify(result="error", message="Internal server error"), 500


@organization_blueprint.route("", methods=["GET"])
def get_organizations():
    organizations = [org.serialize_for_list() for org in dao_get_organizations()]

    return jsonify(organizations)


@organization_blueprint.route("/<uuid:organization_id>", methods=["GET"])
def get_organization_by_id(organization_id):
    check_suspicious_id(organization_id)
    organization = dao_get_organization_by_id(organization_id)
    return jsonify(organization.serialize())


@organization_blueprint.route("/by-domain", methods=["GET"])
def get_organization_by_domain():
    domain = request.args.get("domain")

    if not domain or "@" in domain:
        abort(400)

    organization = dao_get_organization_by_email_address(
        "example@{}".format(request.args.get("domain"))
    )

    if not organization:
        abort(404)

    return jsonify(organization.serialize())


@organization_blueprint.route("", methods=["POST"])
def create_organization():
    data = request.get_json()
    validate(data, post_create_organization_schema)
    organization = Organization(**data)
    dao_create_organization(organization)

    return jsonify(organization.serialize()), 201


@organization_blueprint.route("/<uuid:organization_id>", methods=["POST"])
def update_organization(organization_id):
    check_suspicious_id(organization_id)
    data = request.get_json()
    validate(data, post_update_organization_schema)

    result = dao_update_organization(organization_id, **data)

    if data.get("agreement_signed") is True:
        # if a platform admin has manually adjusted the organization, don't tell people
        if data.get("agreement_signed_by_id"):
            send_notifications_on_mou_signed(organization_id)

    if result:
        return "", 204
    else:
        raise InvalidRequest("Organization not found", 404)


@organization_blueprint.route("/<uuid:organization_id>/service", methods=["POST"])
def link_service_to_organization(organization_id):
    check_suspicious_id(organization_id)
    data = request.get_json()
    validate(data, post_link_service_to_organization_schema)
    service = dao_fetch_service_by_id(data["service_id"])
    service.organization = None

    with transaction():
        dao_add_service_to_organization(service, organization_id)
        set_default_free_allowance_for_service(service, year_start=None)

    return "", 204


@organization_blueprint.route("/<uuid:organization_id>/services", methods=["GET"])
def get_organization_services(organization_id):
    check_suspicious_id(organization_id)
    services = dao_get_organization_services(organization_id)
    sorted_services = sorted(services, key=lambda s: (-s.active, s.name))
    return jsonify([s.serialize_for_org_dashboard() for s in sorted_services])


@organization_blueprint.route(
    "/<uuid:organization_id>/services-with-usage", methods=["GET"]
)
def get_organization_services_usage(organization_id):
    check_suspicious_id(organization_id)
    try:
        year = int(request.args.get("year", "none"))
    except ValueError:
        return jsonify(result="error", message="No valid year provided"), 400

    services = fetch_usage_year_for_organization(organization_id, year)
    list_services = services.values()
    sorted_services = sorted(
        list_services, key=lambda s: (-s["active"], s["service_name"].lower())
    )
    return jsonify(services=sorted_services)


@organization_blueprint.route("/<uuid:organization_id>/dashboard", methods=["GET"])
def get_organization_dashboard(organization_id):

    check_suspicious_id(organization_id)

    try:
        year = int(request.args.get("year", "none"))
    except ValueError:
        return jsonify(result="error", message="No valid year provided"), 400

    services_with_usage = fetch_usage_year_for_organization(
        organization_id, year, include_all_services=True
    )

    service_ids = [service_data["service_id"] for service_data in services_with_usage.values()]

    if not service_ids:
        return jsonify(services=[]), 200

    recent_templates = dao_get_recent_sms_template_per_service(service_ids)
    primary_contacts = dao_get_service_primary_contacts(service_ids)

    for service_data in services_with_usage.values():
        service_uuid = service_data["service_id"]
        service_data["recent_sms_template_name"] = recent_templates.get(service_uuid)
        service_data["primary_contact"] = primary_contacts.get(service_uuid)

    services_list = list(services_with_usage.values())
    sorted_services = sorted(
        services_list,
        key=lambda s: (
            0 if (s["active"] and not s["restricted"]) else
            1 if (s["active"] and s["restricted"]) else
            2,
            s["service_name"].lower()
        )
    )

    return jsonify(services=sorted_services)


@organization_blueprint.route(
    "/<uuid:organization_id>/users/<uuid:user_id>", methods=["POST"]
)
def add_user_to_organization(organization_id, user_id):
    check_suspicious_id(organization_id, user_id)
    new_org_user = dao_add_user_to_organization(organization_id, user_id)
    return jsonify(data=new_org_user.serialize())


@organization_blueprint.route(
    "/<uuid:organization_id>/users/<uuid:user_id>", methods=["DELETE"]
)
def remove_user_from_organization(organization_id, user_id):
    check_suspicious_id(organization_id, user_id)
    organization = dao_get_organization_by_id(organization_id)
    user = get_user_by_id(user_id=user_id)

    if user not in organization.users:
        error = "User not found"
        raise InvalidRequest(error, status_code=404)

    dao_remove_user_from_organization(organization, user)

    return {}, 204


@organization_blueprint.route("/<uuid:organization_id>/users", methods=["GET"])
def get_organization_users(organization_id):
    check_suspicious_id(organization_id)
    org_users = dao_get_users_for_organization(organization_id)
    return jsonify(data=[x.serialize() for x in org_users])


def check_request_args(request):
    org_id = request.args.get("org_id")
    name = request.args.get("name", None)
    errors = []
    if not org_id:
        errors.append({"org_id": ["Can't be empty"]})
    if not name:
        errors.append({"name": ["Can't be empty"]})
    if errors:
        raise InvalidRequest(errors, status_code=400)
    return org_id, name


def send_notifications_on_mou_signed(organization_id):
    organization = dao_get_organization_by_id(organization_id)
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    def _send_notification(template_id, recipient, personalisation):
        template = dao_get_template_by_id(template_id)

        saved_notification = persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient=recipient,
            service=notify_service,
            personalisation={},
            notification_type=template.template_type,
            api_key_id=None,
            key_type=KeyType.NORMAL,
            reply_to_text=notify_service.get_default_reply_to_email_address(),
        )
        saved_notification.personalisation = personalisation

        redis_store.set(
            f"email-personalisation-{saved_notification.id}",
            json.dumps(personalisation),
            ex=60 * 60,
        )
        send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    personalisation = {
        "mou_link": "{}/agreement/agreement.pdf".format(
            current_app.config["ADMIN_BASE_URL"]
        ),
        "org_name": organization.name,
        "org_dashboard_link": "{}/organizations/{}".format(
            current_app.config["ADMIN_BASE_URL"], organization.id
        ),
        "signed_by_name": organization.agreement_signed_by.name,
        "on_behalf_of_name": organization.agreement_signed_on_behalf_of_name,
    }

    if not organization.agreement_signed_on_behalf_of_email_address:
        signer_template_id = "MOU_SIGNER_RECEIPT_TEMPLATE_ID"
    else:
        signer_template_id = "MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID"

        # let the person who has been signed on behalf of know.
        _send_notification(
            current_app.config["MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID"],
            organization.agreement_signed_on_behalf_of_email_address,
            personalisation,
        )

    # let the person who signed know - the template is different depending on if they signed on behalf of someone
    _send_notification(
        current_app.config[signer_template_id],
        organization.agreement_signed_by.email_address,
        personalisation,
    )


@organization_blueprint.route(
    "/<uuid:organization_id>/message-allowance", methods=["GET"]
)
def get_organization_message_allowance(organization_id):

    check_suspicious_id(organization_id)

    dao_get_organization_by_id(organization_id)

    services = dao_get_organization_services(organization_id)

    if not services:
        return (
            jsonify(
                {
                    "messages_sent": 0,
                    "messages_remaining": 0,
                    "total_message_limit": 0,
                }
            ),
            200,
        )

    current_year = datetime.now(tz=ZoneInfo("UTC")).year
    service_ids = [service.id for service in services]

    messages_by_service = dao_get_notification_counts_per_service(
        service_ids, current_year
    )

    total_messages_sent = sum(messages_by_service.get(s.id, 0) for s in services)
    total_message_limit = sum(s.total_message_limit for s in services)
    total_messages_remaining = total_message_limit - total_messages_sent

    return (
        jsonify(
            {
                "messages_sent": total_messages_sent,
                "messages_remaining": total_messages_remaining,
                "total_message_limit": total_message_limit,
            }
        ),
        200,
    )
