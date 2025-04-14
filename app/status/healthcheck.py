from flask import Blueprint, jsonify, make_response, request
from sqlalchemy import text

from app import db, version
from app.dao.organization_dao import dao_count_organizations_with_live_services
from app.dao.services_dao import dao_count_live_services

status = Blueprint("status", __name__)


@status.route("/", methods=["GET"])
@status.route("/_status", methods=["GET", "POST"])
def show_status():
    if request.args.get("simple", None):
        return jsonify(status="ok"), 200
    else:
        return (
            jsonify(
                status="ok",  # This should be considered part of the public API
                git_commit=version.__git_commit__,
                build_time=version.__time__,
                db_version=get_db_version(),
            ),
            200,
        )


@status.route("/_status/live-service-and-organization-counts")
def live_service_and_organization_counts():
    response = make_response(
        jsonify(
            organizations=dao_count_organizations_with_live_services(),
            services=dao_count_live_services(),
        ),
        200,
    )
    response.headers["Content-Type"] = "application/json"
    return response


def get_db_version():
    query = "SELECT version_num FROM alembic_version"
    full_name = db.session.execute(text(query)).fetchone()[0]
    return full_name
