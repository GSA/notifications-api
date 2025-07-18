from flask import Blueprint, jsonify, request
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.template_folder_dao import dao_get_template_folder_by_id_and_service_id
from app.dao.templates_dao import (
    dao_create_template,
    dao_get_all_templates_for_service,
    dao_get_template_by_id_and_service_id,
    dao_get_template_versions,
    dao_redact_template,
    dao_update_template,
)
from app.enums import TemplateType
from app.errors import InvalidRequest, register_errors
from app.models import Template
from app.notifications.validators import check_reply_to, service_has_permission
from app.schema_validation import validate
from app.schemas import (
    template_history_schema,
    template_schema,
    template_schema_no_detail,
)
from app.template.template_schemas import (
    post_create_template_schema,
    post_update_template_schema,
)
from app.utils import check_suspicious_id, get_public_notify_type_text
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.template import SMSMessageTemplate

template_blueprint = Blueprint(
    "template", __name__, url_prefix="/service/<uuid:service_id>/template"
)

register_errors(template_blueprint)


def _content_count_greater_than_limit(content, template_type):
    if template_type == TemplateType.SMS:
        template = SMSMessageTemplate(
            {"content": content, "template_type": template_type}
        )
        return template.is_message_too_long()
    return False


def validate_parent_folder(template_json):
    if template_json.get("parent_folder_id"):
        try:
            return dao_get_template_folder_by_id_and_service_id(
                template_folder_id=template_json.pop("parent_folder_id"),
                service_id=template_json["service"],
            )
        except NoResultFound:
            raise InvalidRequest("parent_folder_id not found", status_code=400)
    else:
        return None


@template_blueprint.route("", methods=["POST"])
def create_template(service_id):
    check_suspicious_id(service_id)
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    # permissions needs to be placed here otherwise marshmallow will interfere with versioning
    permissions = [p.permission for p in fetched_service.permissions]
    template_json = validate(request.get_json(), post_create_template_schema)
    folder = validate_parent_folder(template_json=template_json)
    new_template = Template.from_json(template_json, folder)

    if not service_has_permission(new_template.template_type, permissions):
        message = "Creating {} templates is not allowed".format(
            get_public_notify_type_text(new_template.template_type)
        )
        errors = {"template_type": [message]}
        raise InvalidRequest(errors, 403)

    new_template.service = fetched_service

    over_limit = _content_count_greater_than_limit(
        new_template.content, new_template.template_type
    )
    if over_limit:
        message = "Content has a character count greater than the limit of {}".format(
            SMS_CHAR_COUNT_LIMIT
        )
        errors = {"content": [message]}
        raise InvalidRequest(errors, status_code=400)

    check_reply_to(service_id, new_template.reply_to, new_template.template_type)

    dao_create_template(new_template)

    return jsonify(data=template_schema.dump(new_template)), 201


@template_blueprint.route("/<uuid:template_id>", methods=["POST"])
def update_template(service_id, template_id):
    check_suspicious_id(service_id, template_id)
    fetched_template = dao_get_template_by_id_and_service_id(
        template_id=template_id, service_id=service_id
    )

    if not service_has_permission(
        fetched_template.template_type,
        [p.permission for p in fetched_template.service.permissions],
    ):
        message = "Updating {} templates is not allowed".format(
            get_public_notify_type_text(fetched_template.template_type)
        )
        errors = {"template_type": [message]}

        raise InvalidRequest(errors, 403)

    data = request.get_json()
    validate(data, post_update_template_schema)

    # if redacting, don't update anything else
    if data.get("redact_personalisation") is True:
        return redact_template(fetched_template, data)

    current_data = dict(template_schema.dump(fetched_template).items())
    updated_template = dict(template_schema.dump(fetched_template).items())
    updated_template.update(data)

    # Check if there is a change to make.
    if _template_has_not_changed(current_data, updated_template):
        return jsonify(data=updated_template), 200

    over_limit = _content_count_greater_than_limit(
        updated_template["content"], fetched_template.template_type
    )
    if over_limit:
        message = "Content has a character count greater than the limit of {}".format(
            SMS_CHAR_COUNT_LIMIT
        )
        errors = {"content": [message]}
        raise InvalidRequest(errors, status_code=400)

    update_dict = template_schema.load(updated_template, session=db.session)

    if update_dict.archived:
        update_dict.folder = None
    dao_update_template(update_dict)
    return jsonify(data=template_schema.dump(update_dict)), 200


@template_blueprint.route("", methods=["GET"])
def get_all_templates_for_service(service_id):
    check_suspicious_id(service_id)
    templates = dao_get_all_templates_for_service(service_id=service_id)
    if str(request.args.get("detailed", True)) == "True":
        data = template_schema.dump(templates, many=True)
    else:
        data = template_schema_no_detail.dump(templates, many=True)
    return jsonify(data=data)


@template_blueprint.route("/<uuid:template_id>", methods=["GET"])
def get_template_by_id_and_service_id(service_id, template_id):
    check_suspicious_id(service_id, template_id)
    fetched_template = dao_get_template_by_id_and_service_id(
        template_id=template_id, service_id=service_id
    )
    data = template_schema.dump(fetched_template)
    return jsonify(data=data)


@template_blueprint.route("/<uuid:template_id>/preview", methods=["GET"])
def preview_template_by_id_and_service_id(service_id, template_id):
    check_suspicious_id(service_id, template_id)
    fetched_template = dao_get_template_by_id_and_service_id(
        template_id=template_id, service_id=service_id
    )
    data = template_schema.dump(fetched_template)
    template_object = fetched_template._as_utils_template_with_personalisation(
        request.args.to_dict()
    )

    if template_object.missing_data:
        raise InvalidRequest(
            {
                "template": [
                    "Missing personalisation: {}".format(
                        ", ".join(template_object.missing_data)
                    )
                ]
            },
            status_code=400,
        )
    # Only emails have subjects, SMS do not
    if hasattr(template_object, "subject"):
        data["subject"] = template_object.subject
    data["content"] = template_object.content_with_placeholders_filled_in

    return jsonify(data)


@template_blueprint.route("/<uuid:template_id>/version/<int:version>")
def get_template_version(service_id, template_id, version):
    check_suspicious_id(service_id, template_id)
    data = template_history_schema.dump(
        dao_get_template_by_id_and_service_id(
            template_id=template_id, service_id=service_id, version=version
        )
    )
    return jsonify(data=data)


@template_blueprint.route("/<uuid:template_id>/versions")
def get_template_versions(service_id, template_id):
    check_suspicious_id(service_id, template_id)
    data = template_history_schema.dump(
        dao_get_template_versions(service_id=service_id, template_id=template_id),
        many=True,
    )
    return jsonify(data=data)


def _template_has_not_changed(current_data, updated_template):
    return all(
        current_data[key] == updated_template[key]
        for key in ("name", "content", "subject", "archived", "process_type")
    )


def redact_template(template, data):
    # we also don't need to check what was passed in redact_personalisation - its presence in the dict is enough.
    if "created_by" not in data:
        message = "Field is required"
        errors = {"created_by": [message]}
        raise InvalidRequest(errors, status_code=400)

    # if it's already redacted, then just return 200 straight away.
    if not template.redact_personalisation:
        dao_redact_template(template, data["created_by"])
    return "null", 200
