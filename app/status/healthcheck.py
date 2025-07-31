from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text
from werkzeug.exceptions import ServiceUnavailable

from app import db, version
from app.dao.organization_dao import dao_count_organizations_with_live_services
from app.dao.services_dao import dao_count_live_services

status = Blueprint("status", __name__)


@status.route("/", methods=["GET"])
@status.route("/_status", methods=["GET", "POST"])
def show_status():
    try:
        if request.args.get("simple", None):
            response = jsonify(status="ok")
        else:
            response = jsonify(
                status="ok",  # This should be considered part of the public API
                git_commit=version.__git_commit__,
                build_time=version.__time__,
                db_version=get_db_version(),
            )

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response, 200
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error in show_status: {str(e)}", exc_info=True
        )
        # raise Exception(status_code=503, detail="Service temporarily unavailable")
        raise ServiceUnavailable("Service temporarily unavailable")


@status.route("/_status/live-service-and-organization-counts")
def live_service_and_organization_counts():
    try:
        response = jsonify(
            organizations=dao_count_organizations_with_live_services(),
            services=dao_count_live_services(),
        )

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response, 200
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error in live_service_and_organization_counts: {str(e)}",
            exc_info=True,
        )
        # raise Exception(status_code=503, detail="Service temporarily unavailable")
        raise ServiceUnavailable("Service temporarily unavailable")


def get_db_version():
    try:
        query = "SELECT version_num FROM alembic_version"
        full_name = db.session.execute(text(query)).fetchone()[0]
        return full_name
    except Exception as e:
        current_app.logger.error(
            f"Unexpected error in get_db_version: {str(e)}",
            exc_info=True,
        )
        raise Exception(status_code=503, detail="Database temporarily unavailable")
