from flask import Blueprint, jsonify, request

from app.dao.fact_notification_status_dao import (
    fetch_notification_status_for_service_for_today_and_7_previous_days,
)
from app.dao.notifications_dao import dao_get_last_date_template_was_used
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.errors import InvalidRequest, register_errors
from app.utils import DATETIME_FORMAT, check_suspicious_id

template_statistics = Blueprint(
    "template_statistics",
    __name__,
    url_prefix="/service/<service_id>/template-statistics",
)

register_errors(template_statistics)


@template_statistics.route("")
def get_template_statistics_for_service_by_day(service_id):
    check_suspicious_id(service_id)
    whole_days = request.args.get("whole_days", request.args.get("limit_days", "8"))
    try:
        whole_days = int(whole_days)
    except ValueError:
        error = f"{whole_days} is not an integer"
        message = {"whole_days": [error]}
        raise InvalidRequest(message, status_code=400)

    if whole_days < 0 or whole_days > 8:
        raise InvalidRequest(
            {"whole_days": ["whole_days must be between 0 and 8"]}, status_code=400
        )
    data = fetch_notification_status_for_service_for_today_and_7_previous_days(
        service_id, by_template=True, limit_days=whole_days
    )

    return jsonify(
        data=[
            {
                "count": row.count,
                "template_id": str(row.template_id),
                "template_name": row.template_name,
                "template_folder_id": row.template_folder_id,
                "template_folder": row.folder,
                "created_by_id": row.created_by_id,
                "created_by": row.created_by,
                "last_used": row.last_used,
                "template_type": row.notification_type,
                "status": row.status,
            }
            for row in data
        ]
    )


@template_statistics.route("/last-used/<uuid:template_id>")
def get_last_used_datetime_for_template(service_id, template_id):
    check_suspicious_id(service_id, template_id)
    # Check the template and service exist
    dao_get_template_by_id_and_service_id(template_id, service_id)

    last_date_used = dao_get_last_date_template_was_used(
        template_id=template_id, service_id=service_id
    )

    return jsonify(
        last_date_used=(
            last_date_used.strftime(DATETIME_FORMAT)
            if last_date_used
            else last_date_used
        )
    )
