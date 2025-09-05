import itertools
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request
from jsonschema import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.datastructures import MultiDict

from app import db
from app.aws.s3 import get_personalisation_from_s3, get_phone_number_from_s3
from app.config import QueueNames
from app.dao import fact_notification_status_dao, notifications_dao
from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.api_key_dao import (
    expire_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    save_model_api_key,
)
from app.dao.dao_utils import dao_rollback, transaction
from app.dao.date_util import get_calendar_year, get_month_start_and_end_date_in_utc
from app.dao.fact_notification_status_dao import (
    fetch_monthly_template_usage_for_service,
    fetch_notification_status_for_service_by_month,
    fetch_notification_status_for_service_for_day,
    fetch_notification_status_for_service_for_today_and_7_previous_days,
    fetch_stats_for_all_services_by_date_range,
)
from app.dao.inbound_numbers_dao import dao_allocate_number_for_service
from app.dao.notifications_dao import (
    dao_get_notification_count_for_service,
    dao_get_notification_count_for_service_message_ratio,
)
from app.dao.organization_dao import dao_get_organization_by_service_id
from app.dao.service_data_retention_dao import (
    fetch_service_data_retention,
    fetch_service_data_retention_by_id,
    fetch_service_data_retention_by_notification_type,
    insert_service_data_retention,
    update_service_data_retention,
)
from app.dao.service_email_reply_to_dao import (
    add_reply_to_email_address_for_service,
    archive_reply_to_email_address,
    dao_get_reply_to_by_id,
    dao_get_reply_to_by_service_id,
    update_reply_to_email_address,
)
from app.dao.service_guest_list_dao import (
    dao_add_and_commit_guest_list_contacts,
    dao_fetch_service_guest_list,
    dao_remove_service_guest_list,
)
from app.dao.service_sms_sender_dao import (
    archive_sms_sender,
    dao_add_sms_sender_for_service,
    dao_get_service_sms_senders_by_id,
    dao_get_sms_senders_by_service_id,
    dao_update_service_sms_sender,
    update_existing_sms_sender_with_inbound_number,
)
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_archive_service,
    dao_create_service,
    dao_fetch_all_services,
    dao_fetch_all_services_by_user,
    dao_fetch_live_services_data,
    dao_fetch_service_by_id,
    dao_fetch_stats_for_service_from_days,
    dao_fetch_stats_for_service_from_days_for_user,
    dao_fetch_stats_for_service_from_hours,
    dao_fetch_todays_stats_for_all_services,
    dao_fetch_todays_stats_for_service,
    dao_remove_user_from_service,
    dao_resume_service,
    dao_suspend_service,
    dao_update_service,
    fetch_notification_stats_for_service_by_month_by_user,
    get_services_by_partial_name,
    get_specific_days_stats,
    get_specific_hours_stats,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.users_dao import get_user_by_id
from app.enums import KeyType
from app.errors import InvalidRequest, register_errors
from app.models import EmailBranding, Permission, Service
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.schema_validation import validate
from app.schemas import (
    api_key_schema,
    detailed_service_schema,
    email_data_request_schema,
    notification_with_template_schema,
    notifications_filter_schema,
    service_schema,
)
from app.service import statistics
from app.service.send_notification import send_one_off_notification
from app.service.sender import send_notification_to_service_users
from app.service.service_data_retention_schema import (
    add_service_data_retention_request,
    update_service_data_retention_request,
)
from app.service.service_senders_schema import (
    add_service_email_reply_to_request,
    add_service_sms_sender_request,
)
from app.service.utils import get_guest_list_objects
from app.user.users_schema import post_set_permissions_schema
from app.utils import (
    check_suspicious_id,
    get_prev_next_pagination_links,
    utc_now,
)

celery_logger = logging.getLogger(__name__)

service_blueprint = Blueprint("service", __name__)

register_errors(service_blueprint)


@service_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint on ix_organization_name
    """
    if any(
        'duplicate key value violates unique constraint "{}"'.format(constraint)
        in str(exc)
        for constraint in {"services_name_key", "services_email_from_key"}
    ):
        return (
            jsonify(
                result="error",
                message={
                    "name": [
                        "Duplicate service name '{}'".format(
                            exc.params.get("name", exc.params.get("email_from", ""))
                        )
                    ]
                },
            ),
            400,
        )
    current_app.logger.exception(exc)
    return jsonify(result="error", message="Internal server error"), 500


@service_blueprint.route("", methods=["GET"])
def get_services():
    only_active = request.args.get("only_active") == "True"
    detailed = request.args.get("detailed") == "True"
    user_id = request.args.get("user_id", None)
    include_from_test_key = request.args.get("include_from_test_key", "True") != "False"

    # If start and end date are not set, we are expecting today's stats.
    today = str(utc_now().date())

    start_date = datetime.strptime(
        request.args.get("start_date", today), "%Y-%m-%d"
    ).date()
    end_date = datetime.strptime(request.args.get("end_date", today), "%Y-%m-%d").date()

    if user_id:
        services = dao_fetch_all_services_by_user(user_id, only_active)
    elif detailed:
        result = jsonify(
            data=get_detailed_services(
                start_date=start_date,
                end_date=end_date,
                only_active=only_active,
                include_from_test_key=include_from_test_key,
            )
        )
        return result
    else:
        services = dao_fetch_all_services(only_active)
    data = service_schema.dump(services, many=True)
    return jsonify(data=data)


@service_blueprint.route("/find-services-by-name", methods=["GET"])
def find_services_by_name():
    service_name = request.args.get("service_name")
    if not service_name:
        errors = {"service_name": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    fetched_services = get_services_by_partial_name(service_name)
    data = [service.serialize_for_org_dashboard() for service in fetched_services]
    return jsonify(data=data), 200


@service_blueprint.route("/live-services-data", methods=["GET"])
def get_live_services_data():
    data = dao_fetch_live_services_data()
    return jsonify(data=data)


@service_blueprint.route("/<uuid:service_id>", methods=["GET"])
def get_service_by_id(service_id):
    check_suspicious_id(service_id)
    if request.args.get("detailed") == "True":
        data = get_detailed_service(
            service_id, today_only=request.args.get("today_only") == "True"
        )
    else:
        fetched = dao_fetch_service_by_id(service_id)

        data = service_schema.dump(fetched)

    current_app.logger.debug(f'>> SERVICE: {data["id"]}; {data}')
    return jsonify(data=data)


@service_blueprint.route("/<uuid:service_id>/statistics")
def get_service_notification_statistics(service_id):
    check_suspicious_id(service_id)
    return jsonify(
        data=get_service_statistics(
            service_id,
            request.args.get("today_only") == "True",
            int(request.args.get("limit_days", 8)),
        )
    )


@service_blueprint.route("/<uuid:service_id>/statistics/<string:start>/<int:days>")
def get_service_notification_statistics_by_day(service_id, start, days):
    check_suspicious_id(service_id)
    return jsonify(
        data=get_service_statistics_for_specific_days(service_id, start, int(days))
    )


def get_service_statistics_for_specific_days(service_id, start, days=1):
    check_suspicious_id(service_id)
    # Calculate start and end date range
    end_date = datetime.strptime(start, "%Y-%m-%d")
    start_date = end_date - timedelta(days=days - 1)

    # Fetch hourly stats from DB
    total_notifications, results = dao_fetch_stats_for_service_from_hours(
        service_id,
        start_date,
        end_date,
    )

    hours = days * 24

    # Process data using new hourly stats function
    stats = get_specific_hours_stats(
        results,
        start_date,
        hours=hours,
        total_notifications=total_notifications,
    )

    return stats


@service_blueprint.route(
    "/<uuid:service_id>/statistics/user/<uuid:user_id>/<string:start>/<int:days>"
)
def get_service_notification_statistics_by_day_by_user(
    service_id, user_id, start, days
):
    check_suspicious_id(service_id, user_id)
    return jsonify(
        data=get_service_statistics_for_specific_days_by_user(
            service_id, user_id, start, int(days)
        )
    )


def get_service_statistics_for_specific_days_by_user(
    service_id, user_id, start, days=1
):
    # start and end dates needs to be reversed because
    # the end date is today and the start is x days in the past
    # a day needs to be substracted to allow for today
    end_date = datetime.strptime(start, "%Y-%m-%d")
    start_date = end_date - timedelta(days=days - 1)

    total_notifications, results = dao_fetch_stats_for_service_from_days_for_user(
        service_id, start_date, end_date, user_id
    )

    hours = days * 24

    stats = get_specific_hours_stats(
        results,
        start_date,
        hours=hours,
        total_notifications=total_notifications,
    )
    return stats


@service_blueprint.route("", methods=["POST"])
def create_service():
    data = request.get_json()

    if not data.get("user_id"):
        errors = {"user_id": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data.pop("service_domain", None)

    data["total_message_limit"] = current_app.config["TOTAL_MESSAGE_LIMIT"]

    # validate json with marshmallow
    service_schema.load(data, session=db.session)

    user = get_user_by_id(data.pop("user_id"))

    # unpack valid json into service object
    valid_service = Service.from_json(data)

    with transaction():
        dao_create_service(valid_service, user)
        set_default_free_allowance_for_service(service=valid_service, year_start=None)

    return jsonify(data=service_schema.dump(valid_service)), 201


@service_blueprint.route("/<uuid:service_id>", methods=["POST"])
def update_service(service_id):
    check_suspicious_id(service_id)
    req_json = request.get_json()
    fetched_service = dao_fetch_service_by_id(service_id)
    service_going_live = fetched_service.restricted and not req_json.get(
        "restricted", True
    )
    current_data = dict(service_schema.dump(fetched_service).items())
    current_data.update(req_json)

    try:
        service = service_schema.load(
            current_data, session=db.session, instance=fetched_service, partial=True
        )
    except ValidationError as e:
        current_app.logger.error(
            f"Validation error during service update: {e.messages}"
        )
        return jsonify(errors=e.messages), 400

    if "email_branding" in req_json:
        email_branding_id = req_json["email_branding"]
        service.email_branding = (
            None
            if not email_branding_id
            else db.session.get(EmailBranding, email_branding_id)
        )

    dao_update_service(service)

    if service_going_live:
        send_notification_to_service_users(
            service_id=service_id,
            template_id=current_app.config["SERVICE_NOW_LIVE_TEMPLATE_ID"],
            personalisation={"service_name": current_data["name"]},
            include_user_fields=["name"],
        )

    return jsonify(data=service_schema.dump(fetched_service)), 200


@service_blueprint.route("/<uuid:service_id>/api-key", methods=["POST"])
def create_api_key(service_id=None):
    if service_id:
        check_suspicious_id(service_id)
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    valid_api_key = api_key_schema.load(request.get_json(), session=db.session)
    valid_api_key.service = fetched_service
    save_model_api_key(valid_api_key)
    unsigned_api_key = get_unsigned_secret(valid_api_key.id)
    return jsonify(data=unsigned_api_key), 201


@service_blueprint.route(
    "/<uuid:service_id>/api-key/revoke/<uuid:api_key_id>", methods=["POST"]
)
def revoke_api_key(service_id, api_key_id):
    check_suspicious_id(service_id, api_key_id)
    expire_api_key(service_id=service_id, api_key_id=api_key_id)
    return jsonify(), 202


@service_blueprint.route("/<uuid:service_id>/api-keys", methods=["GET"])
@service_blueprint.route("/<uuid:service_id>/api-keys/<uuid:key_id>", methods=["GET"])
def get_api_keys(service_id, key_id=None):
    if key_id:
        check_suspicious_id(service_id, key_id)
    else:
        check_suspicious_id(service_id)
    dao_fetch_service_by_id(service_id=service_id)

    try:
        if key_id:
            api_keys = [get_model_api_keys(service_id=service_id, id=key_id)]
        else:
            api_keys = get_model_api_keys(service_id=service_id)
    except NoResultFound:
        error = "API key not found for id: {}".format(service_id)
        raise InvalidRequest(error, status_code=404)

    return jsonify(apiKeys=api_key_schema.dump(api_keys, many=True)), 200


@service_blueprint.route("/<uuid:service_id>/users", methods=["GET"])
def get_users_for_service(service_id):
    check_suspicious_id(service_id)
    fetched = dao_fetch_service_by_id(service_id)
    return jsonify(data=[x.serialize() for x in fetched.users])


@service_blueprint.route("/<uuid:service_id>/users/<user_id>", methods=["POST"])
def add_user_to_service(service_id, user_id):
    check_suspicious_id(service_id, user_id)
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)
    if user in service.users:
        error = f"User id: {user_id} already part of service id: {service_id}"
        raise InvalidRequest(error, status_code=400)

    data = request.get_json()
    validate(data, post_set_permissions_schema)

    permissions = [
        Permission(service_id=service_id, user_id=user_id, permission=p["permission"])
        for p in data["permissions"]
    ]
    folder_permissions = data.get("folder_permissions", [])

    dao_add_user_to_service(service, user, permissions, folder_permissions)

    data = service_schema.dump(service)
    return jsonify(data=data), 201


@service_blueprint.route("/<uuid:service_id>/users/<user_id>", methods=["DELETE"])
def remove_user_from_service(service_id, user_id):
    check_suspicious_id(service_id, user_id)
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)
    if user not in service.users:
        error = "User not found"
        raise InvalidRequest(error, status_code=404)

    elif len(service.users) == 1:
        error = "You cannot remove the only user for a service"
        raise InvalidRequest(error, status_code=400)

    dao_remove_user_from_service(service, user)
    return jsonify({}), 204


# This is placeholder get method until more thought
# goes into how we want to fetch and view various items in history
# tables. This is so product owner can pass stories as done
@service_blueprint.route("/<uuid:service_id>/history", methods=["GET"])
def get_service_history(service_id):
    check_suspicious_id(service_id)
    from app.models import ApiKey, Service, TemplateHistory
    from app.schemas import (
        api_key_history_schema,
        service_history_schema,
        template_history_schema,
    )

    service_history = (
        db.session.execute(
            select(Service.get_history_model()).where(
                Service.get_history_model().id == service_id
            )
        )
        .scalars()
        .all()
    )
    service_data = service_history_schema.dump(service_history, many=True)
    api_key_history = (
        db.session.execute(
            select(ApiKey.get_history_model()).where(
                ApiKey.get_history_model().service_id == service_id
            )
        )
        .scalars()
        .all()
    )
    api_keys_data = api_key_history_schema.dump(api_key_history, many=True)

    template_history = (
        db.session.execute(
            select(TemplateHistory).where(TemplateHistory.service_id == service_id)
        )
        .scalars()
        .all()
    )
    template_data = template_history_schema.dump(template_history, many=True)

    data = {
        "service_history": service_data,
        "api_key_history": api_keys_data,
        "template_history": template_data,
        "events": [],
    }

    return jsonify(data=data)


@service_blueprint.route("/<uuid:service_id>/notifications", methods=["GET", "POST"])
def get_all_notifications_for_service(service_id):
    check_suspicious_id(service_id)
    current_app.logger.debug("enter get_all_notifications_for_service")
    if request.method == "GET":
        data = notifications_filter_schema.load(request.args)
        current_app.logger.debug(
            f"use GET, request.args {request.args} and data {data}"
        )
    elif request.method == "POST":
        # Must transform request.get_json() to MultiDict as NotificationsFilterSchema expects a MultiDict.
        # Unlike request.args, request.get_json() does not return a MultiDict but instead just a dict.
        data = notifications_filter_schema.load(MultiDict(request.get_json()))
        current_app.logger.debug(f"use POST, request {request.get_json()} data {data}")

    page = data["page"] if "page" in data else 1
    page_size = (
        data["page_size"]
        if "page_size" in data
        else current_app.config.get("PAGE_SIZE")
    )
    # HARD CODE TO 100 for now.  1000 or 10000 causes reports to time out before they complete (if big)
    # Tests are relying on the value in config (20), whereas the UI seems to pass 10000
    if page_size > 100:
        page_size = 100
    limit_days = data.get("limit_days")
    include_jobs = data.get("include_jobs", True)
    include_from_test_key = data.get("include_from_test_key", False)
    include_one_off = data.get("include_one_off", True)

    # count_pages is not being used for whether to count the number of pages, but instead as a flag
    # for whether to show pagination links
    count_pages = data.get("count_pages", True)

    current_app.logger.debug(
        f"get pagination with {service_id} service_id filters {data} \
                             limit_days {limit_days} include_jobs {include_jobs} include_one_off {include_one_off}"
    )
    start_time = time.time()
    current_app.logger.debug(f"Start report generation  with page.size {page_size}")
    pagination = notifications_dao.get_notifications_for_service(
        service_id,
        filter_dict=data,
        page=page,
        page_size=page_size,
        count_pages=False,
        limit_days=limit_days,
        include_jobs=include_jobs,
        include_from_test_key=include_from_test_key,
        include_one_off=include_one_off,
    )
    current_app.logger.debug(f"Query complete at {int(time.time()-start_time)*1000}")

    for notification in pagination.items:
        if notification.job_id is not None:
            current_app.logger.debug(
                f"Processing job_id {notification.job_id} at {int(time.time()-start_time)*1000}"
            )
            notification.personalisation = get_personalisation_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )

            recipient = get_phone_number_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )

            notification.to = recipient
            notification.normalised_to = recipient

        else:
            notification.to = ""
            notification.normalised_to = ""

    kwargs = request.args.to_dict()
    kwargs["service_id"] = service_id

    if data.get("format_for_csv"):
        notifications = [
            notification.serialize_for_csv() for notification in pagination.items
        ]
    else:
        notifications = notification_with_template_schema.dump(
            pagination.items, many=True
        )
    current_app.logger.debug(f"number of notifications are {len(notifications)}")

    # We try and get the next page of results to work out if we need provide a pagination link to the next page
    # in our response if it exists. Note, this could be done instead by changing `count_pages` in the previous
    # call to be True which will enable us to use Flask-Sqlalchemy to tell if there is a next page of results but
    # this way is much more performant for services with many results (unlike Flask SqlAlchemy, this approach
    # doesn't do an additional query to count all the results of which there could be millions but instead only
    # asks for a single extra page of results).
    next_page_of_pagination = notifications_dao.get_notifications_for_service(
        service_id,
        filter_dict=data,
        page=page + 1,
        page_size=page_size,
        count_pages=False,
        limit_days=limit_days,
        include_jobs=include_jobs,
        include_from_test_key=include_from_test_key,
        include_one_off=include_one_off,
        error_out=False,  # False so that if there are no results, it doesn't end in aborting with a 404
    )

    return (
        jsonify(
            notifications=notifications,
            page_size=page_size,
            links=(
                get_prev_next_pagination_links(
                    page,
                    len(next_page_of_pagination.items),
                    ".get_all_notifications_for_service",
                    **kwargs,
                )
                if count_pages
                else {}
            ),
        ),
        200,
    )


@service_blueprint.route(
    "/<uuid:service_id>/notifications/<uuid:notification_id>", methods=["GET"]
)
def get_notification_for_service(service_id, notification_id):
    check_suspicious_id(service_id, notification_id)
    notification = notifications_dao.get_notification_with_personalisation(
        service_id,
        notification_id,
        key_type=None,
    )
    return (
        jsonify(
            notification_with_template_schema.dump(notification),
        ),
        200,
    )


@service_blueprint.route("/<uuid:service_id>/notifications/monthly", methods=["GET"])
def get_monthly_notification_stats(service_id):
    check_suspicious_id(service_id)
    # check service_id validity
    dao_fetch_service_by_id(service_id)

    try:
        year = int(request.args.get("year", "NaN"))
    except ValueError:
        raise InvalidRequest("Year must be a number", status_code=400)

    start_date, end_date = get_calendar_year(year)

    data = statistics.create_empty_monthly_notification_status_stats_dict(year)

    stats = fetch_notification_status_for_service_by_month(
        start_date, end_date, service_id
    )

    statistics.add_monthly_notification_status_stats(data, stats)

    now = utc_now()
    if end_date > now:
        todays_deltas = fetch_notification_status_for_service_for_day(
            now, service_id=service_id
        )
        statistics.add_monthly_notification_status_stats(data, todays_deltas)

    return jsonify(data=data)


@service_blueprint.route(
    "/<uuid:service_id>/notifications/<uuid:user_id>/monthly", methods=["GET"]
)
def get_monthly_notification_stats_by_user(service_id, user_id):
    check_suspicious_id(service_id, user_id)
    # check service_id validity
    dao_fetch_service_by_id(service_id)
    # user = get_user_by_id(user_id=user_id)

    try:
        year = int(request.args.get("year", "NaN"))
    except ValueError:
        raise InvalidRequest("Year must be a number", status_code=400)

    start_date, end_date = get_calendar_year(year)

    data = statistics.create_empty_monthly_notification_status_stats_dict(year)

    stats = fetch_notification_stats_for_service_by_month_by_user(
        start_date, end_date, service_id, user_id
    )

    statistics.add_monthly_notification_status_stats(data, stats)

    now = utc_now()
    if end_date > now:
        todays_deltas = fetch_notification_status_for_service_for_day(
            now, service_id=service_id
        )
        statistics.add_monthly_notification_status_stats(data, todays_deltas)

    return jsonify(data=data)


@service_blueprint.route(
    "/<uuid:service_id>/notifications/<uuid:user_id>/month", methods=["GET"]
)
def get_single_month_notification_stats_by_user(service_id, user_id):
    check_suspicious_id(service_id, user_id)
    # check service_id validity
    dao_fetch_service_by_id(service_id)

    try:
        month = int(request.args.get("month", "NaN"))
        year = int(request.args.get("year", "NaN"))
    except ValueError:
        raise InvalidRequest(
            "Both a month and year are required as numbers", status_code=400
        )

    month_year = datetime(year, month, 10, 00, 00, 00)
    start_date, end_date = get_month_start_and_end_date_in_utc(month_year)

    total_notifications, results = dao_fetch_stats_for_service_from_days_for_user(
        service_id, start_date, end_date, user_id
    )

    stats = get_specific_days_stats(
        results,
        start_date,
        end_date=end_date,
        total_notifications=total_notifications,
    )
    return jsonify(stats)


@service_blueprint.route("/<uuid:service_id>/notifications/month", methods=["GET"])
def get_single_month_notification_stats_for_service(service_id):
    check_suspicious_id(service_id)
    # check service_id validity
    dao_fetch_service_by_id(service_id)

    try:
        month = int(request.args.get("month", "NaN"))
        year = int(request.args.get("year", "NaN"))
    except ValueError:
        raise InvalidRequest(
            "Both a month and year are required as numbers", status_code=400
        )

    month_year = datetime(year, month, 10, 00, 00, 00)
    start_date, end_date = get_month_start_and_end_date_in_utc(month_year)

    __, results = dao_fetch_stats_for_service_from_days(
        service_id, start_date, end_date
    )

    stats = get_specific_days_stats(results, start_date, end_date=end_date)
    return jsonify(stats)


def get_detailed_service(service_id, today_only=False):
    check_suspicious_id(service_id)
    service = dao_fetch_service_by_id(service_id)

    service.statistics = get_service_statistics(service_id, today_only)
    return detailed_service_schema.dump(service)


def get_service_statistics(service_id, today_only, limit_days=8):
    check_suspicious_id(service_id)
    # today_only flag is used by the send page to work out if the service will exceed their daily usage by sending a job
    if today_only:
        stats = dao_fetch_todays_stats_for_service(service_id)
    else:
        stats = fetch_notification_status_for_service_for_today_and_7_previous_days(
            service_id, limit_days=limit_days
        )

    return statistics.format_statistics(stats)


def get_detailed_services(
    start_date, end_date, only_active=False, include_from_test_key=True
):
    if start_date == utc_now().date():
        stats = dao_fetch_todays_stats_for_all_services(
            include_from_test_key=include_from_test_key, only_active=only_active
        )
    else:
        stats = fetch_stats_for_all_services_by_date_range(
            start_date=start_date,
            end_date=end_date,
            include_from_test_key=include_from_test_key,
        )
    results = []

    mylist = itertools.groupby(stats, lambda x: x.service_id)
    for _service_id, rows in mylist:
        rows = list(rows)
        s = statistics.format_statistics(rows)
        results.append(
            {
                "id": str(rows[0].service_id),
                "name": rows[0].name,
                "notification_type": rows[0].notification_type,
                "restricted": rows[0].restricted,
                "active": rows[0].active,
                "created_at": rows[0].created_at,
                "statistics": s,
            }
        )
    return results


@service_blueprint.route("/<uuid:service_id>/guest-list", methods=["GET"])
def get_guest_list(service_id):
    check_suspicious_id(service_id)
    from app.enums import RecipientType

    service = dao_fetch_service_by_id(service_id)

    if not service:
        raise InvalidRequest("Service does not exist", status_code=404)

    guest_list = dao_fetch_service_guest_list(service.id)
    return jsonify(
        email_addresses=[
            item.recipient
            for item in guest_list
            if item.recipient_type == RecipientType.EMAIL
        ],
        phone_numbers=[
            item.recipient
            for item in guest_list
            if item.recipient_type == RecipientType.MOBILE
        ],
    )


@service_blueprint.route("/<uuid:service_id>/guest-list", methods=["PUT"])
def update_guest_list(service_id):
    check_suspicious_id(service_id)
    # doesn't commit so if there are any errors, we preserve old values in db
    dao_remove_service_guest_list(service_id)
    try:
        guest_list_objects = get_guest_list_objects(service_id, request.get_json())
    except ValueError as e:
        current_app.logger.exception(e)
        dao_rollback()
        msg = "{} is not a valid email address or phone number".format(str(e))
        raise InvalidRequest(msg, 400)
    else:
        dao_add_and_commit_guest_list_contacts(guest_list_objects)
        return "", 204


@service_blueprint.route("/<uuid:service_id>/archive", methods=["POST"])
def archive_service(service_id):
    check_suspicious_id(service_id)
    """
    When a service is archived the service is made inactive, templates are archived and api keys are revoked.
    There is no coming back from this operation.
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if service.active:
        dao_archive_service(service.id)

    return "", 204


@service_blueprint.route("/<uuid:service_id>/suspend", methods=["POST"])
def suspend_service(service_id):
    check_suspicious_id(service_id)
    """
    Suspending a service will mark the service as inactive and revoke API keys.
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if service.active:
        dao_suspend_service(service.id)

    return "", 204


@service_blueprint.route("/<uuid:service_id>/resume", methods=["POST"])
def resume_service(service_id):
    check_suspicious_id(service_id)
    """
    Resuming a service that has been suspended will mark the service as active.
    The service will need to re-create API keys
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if not service.active:
        dao_resume_service(service.id)

    return "", 204


@service_blueprint.route(
    "/<uuid:service_id>/notifications/templates_usage/monthly", methods=["GET"]
)
def get_monthly_template_usage(service_id):
    check_suspicious_id(service_id)
    try:
        start_date, end_date = get_calendar_year(int(request.args.get("year", "NaN")))
        data = fetch_monthly_template_usage_for_service(
            start_date=start_date, end_date=end_date, service_id=service_id
        )
        stats = list()
        for i in data:
            stats.append(
                {
                    "template_id": str(i.template_id),
                    "name": i.name,
                    "type": i.template_type,
                    "month": i.month,
                    "year": i.year,
                    "count": i.count,
                }
            )

        return jsonify(stats=stats), 200
    except ValueError:
        raise InvalidRequest("Year must be a number", status_code=400)


@service_blueprint.route("/<uuid:service_id>/send-notification", methods=["POST"])
def create_one_off_notification(service_id):
    check_suspicious_id(service_id)
    resp = send_one_off_notification(service_id, request.get_json())
    return jsonify(resp), 201


@service_blueprint.route("/<uuid:service_id>/email-reply-to", methods=["GET"])
def get_email_reply_to_addresses(service_id):
    check_suspicious_id(service_id)
    result = dao_get_reply_to_by_service_id(service_id)
    return jsonify([i.serialize() for i in result]), 200


@service_blueprint.route(
    "/<uuid:service_id>/email-reply-to/<uuid:reply_to_id>", methods=["GET"]
)
def get_email_reply_to_address(service_id, reply_to_id):
    check_suspicious_id(service_id, reply_to_id)
    result = dao_get_reply_to_by_id(service_id=service_id, reply_to_id=reply_to_id)
    return jsonify(result.serialize()), 200


@service_blueprint.route("/<uuid:service_id>/email-reply-to/verify", methods=["POST"])
def verify_reply_to_email_address(service_id):
    check_suspicious_id(service_id)
    email_address = email_data_request_schema.load(request.get_json())

    check_if_reply_to_address_already_in_use(service_id, email_address["email"])
    template = dao_get_template_by_id(
        current_app.config["REPLY_TO_EMAIL_ADDRESS_VERIFICATION_TEMPLATE_ID"]
    )
    notify_service = db.session.get(Service, current_app.config["NOTIFY_SERVICE_ID"])
    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=email_address["email"],
        service=notify_service,
        personalisation="",
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KeyType.NORMAL,
        reply_to_text=notify_service.get_default_reply_to_email_address(),
    )

    send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    return jsonify(data={"id": saved_notification.id}), 201


@service_blueprint.route("/<uuid:service_id>/email-reply-to", methods=["POST"])
def add_service_reply_to_email_address(service_id):
    check_suspicious_id(service_id)
    # validate the service exists, throws ResultNotFound exception.
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_email_reply_to_request)
    check_if_reply_to_address_already_in_use(service_id, form["email_address"])
    new_reply_to = add_reply_to_email_address_for_service(
        service_id=service_id,
        email_address=form["email_address"],
        is_default=form.get("is_default", True),
    )
    return jsonify(data=new_reply_to.serialize()), 201


@service_blueprint.route(
    "/<uuid:service_id>/email-reply-to/<uuid:reply_to_email_id>", methods=["POST"]
)
def update_service_reply_to_email_address(service_id, reply_to_email_id):
    check_suspicious_id(service_id, reply_to_email_id)
    # validate the service exists, throws ResultNotFound exception.
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_email_reply_to_request)
    new_reply_to = update_reply_to_email_address(
        service_id=service_id,
        reply_to_id=reply_to_email_id,
        email_address=form["email_address"],
        is_default=form.get("is_default", True),
    )
    return jsonify(data=new_reply_to.serialize()), 200


@service_blueprint.route(
    "/<uuid:service_id>/email-reply-to/<uuid:reply_to_email_id>/archive",
    methods=["POST"],
)
def delete_service_reply_to_email_address(service_id, reply_to_email_id):
    check_suspicious_id(service_id, reply_to_email_id)
    archived_reply_to = archive_reply_to_email_address(service_id, reply_to_email_id)

    return jsonify(data=archived_reply_to.serialize()), 200


@service_blueprint.route("/<uuid:service_id>/sms-sender", methods=["POST"])
def add_service_sms_sender(service_id):
    check_suspicious_id(service_id)
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_sms_sender_request)
    inbound_number_id = form.get("inbound_number_id", None)
    sms_sender = form.get("sms_sender")

    if inbound_number_id:
        updated_number = dao_allocate_number_for_service(
            service_id=service_id, inbound_number_id=inbound_number_id
        )
        # the sms_sender in the form is not set, use the inbound number
        sms_sender = updated_number.number
        existing_sms_sender = dao_get_sms_senders_by_service_id(service_id)
        # we don't want to create a new sms sender for the service if we are allocating an inbound number.
        if len(existing_sms_sender) == 1:
            update_existing_sms_sender = existing_sms_sender[0]
            new_sms_sender = update_existing_sms_sender_with_inbound_number(
                service_sms_sender=update_existing_sms_sender,
                sms_sender=sms_sender,
                inbound_number_id=inbound_number_id,
            )

            return jsonify(new_sms_sender.serialize()), 201

    new_sms_sender = dao_add_sms_sender_for_service(
        service_id=service_id,
        sms_sender=sms_sender,
        is_default=form["is_default"],
        inbound_number_id=inbound_number_id,
    )
    return jsonify(new_sms_sender.serialize()), 201


@service_blueprint.route(
    "/<uuid:service_id>/sms-sender/<uuid:sms_sender_id>", methods=["POST"]
)
def update_service_sms_sender(service_id, sms_sender_id):
    check_suspicious_id(service_id, sms_sender_id)
    form = validate(request.get_json(), add_service_sms_sender_request)

    sms_sender_to_update = dao_get_service_sms_senders_by_id(
        service_id=service_id, service_sms_sender_id=sms_sender_id
    )
    if (
        sms_sender_to_update.inbound_number_id
        and form["sms_sender"] != sms_sender_to_update.sms_sender
    ):
        raise InvalidRequest(
            "You can not change the inbound number for service {}".format(service_id),
            status_code=400,
        )

    new_sms_sender = dao_update_service_sms_sender(
        service_id=service_id,
        service_sms_sender_id=sms_sender_id,
        is_default=form["is_default"],
        sms_sender=form["sms_sender"],
    )
    return jsonify(new_sms_sender.serialize()), 200


@service_blueprint.route(
    "/<uuid:service_id>/sms-sender/<uuid:sms_sender_id>/archive", methods=["POST"]
)
def delete_service_sms_sender(service_id, sms_sender_id):
    check_suspicious_id(service_id, sms_sender_id)
    sms_sender = archive_sms_sender(service_id, sms_sender_id)

    return jsonify(data=sms_sender.serialize()), 200


@service_blueprint.route(
    "/<uuid:service_id>/sms-sender/<uuid:sms_sender_id>", methods=["GET"]
)
def get_service_sms_sender_by_id(service_id, sms_sender_id):
    check_suspicious_id(service_id, sms_sender_id)

    sms_sender = dao_get_service_sms_senders_by_id(
        service_id=service_id, service_sms_sender_id=sms_sender_id
    )
    return jsonify(sms_sender.serialize()), 200


@service_blueprint.route("/<uuid:service_id>/sms-sender", methods=["GET"])
def get_service_sms_senders_for_service(service_id):
    check_suspicious_id(service_id)

    sms_senders = dao_get_sms_senders_by_service_id(service_id=service_id)
    return jsonify([sms_sender.serialize() for sms_sender in sms_senders]), 200


@service_blueprint.route("/<uuid:service_id>/organization", methods=["GET"])
def get_organization_for_service(service_id):
    check_suspicious_id(service_id)
    organization = dao_get_organization_by_service_id(service_id=service_id)
    return jsonify(organization.serialize() if organization else {}), 200


@service_blueprint.route("/<uuid:service_id>/data-retention", methods=["GET"])
def get_data_retention_for_service(service_id):
    check_suspicious_id(service_id)
    data_retention_list = fetch_service_data_retention(service_id)
    return (
        jsonify([data_retention.serialize() for data_retention in data_retention_list]),
        200,
    )


@service_blueprint.route(
    "/<uuid:service_id>/data-retention/notification-type/<notification_type>",
    methods=["GET"],
)
def get_data_retention_for_service_notification_type(service_id, notification_type):
    check_suspicious_id(service_id)
    data_retention = fetch_service_data_retention_by_notification_type(
        service_id, notification_type
    )
    return jsonify(data_retention.serialize() if data_retention else {}), 200


@service_blueprint.route(
    "/<uuid:service_id>/data-retention/<uuid:data_retention_id>", methods=["GET"]
)
def get_data_retention_for_service_by_id(service_id, data_retention_id):
    check_suspicious_id(service_id, data_retention_id)
    data_retention = fetch_service_data_retention_by_id(service_id, data_retention_id)
    return jsonify(data_retention.serialize() if data_retention else {}), 200


@service_blueprint.route("/<uuid:service_id>/data-retention", methods=["POST"])
def create_service_data_retention(service_id):
    check_suspicious_id(service_id)
    form = validate(request.get_json(), add_service_data_retention_request)
    try:
        new_data_retention = insert_service_data_retention(
            service_id=service_id,
            notification_type=form.get("notification_type"),
            days_of_retention=form.get("days_of_retention"),
        )
    except IntegrityError:
        raise InvalidRequest(
            message="Service already has data retention for {} notification type".format(
                form.get("notification_type")
            ),
            status_code=400,
        )

    return jsonify(result=new_data_retention.serialize()), 201


@service_blueprint.route(
    "/<uuid:service_id>/data-retention/<uuid:data_retention_id>", methods=["POST"]
)
def modify_service_data_retention(service_id, data_retention_id):
    check_suspicious_id(service_id, data_retention_id)
    form = validate(request.get_json(), update_service_data_retention_request)

    update_count = update_service_data_retention(
        service_data_retention_id=data_retention_id,
        service_id=service_id,
        days_of_retention=form.get("days_of_retention"),
    )
    if update_count == 0:
        raise InvalidRequest(
            message="The service data retention for id: {} was not found for service: {}".format(
                data_retention_id, service_id
            ),
            status_code=404,
        )

    return "", 204


@service_blueprint.route("/get-service-message-ratio")
def get_service_message_ratio():
    service_id = request.args.get("service_id")

    current_year = datetime.now(tz=ZoneInfo("UTC")).year
    my_service = dao_fetch_service_by_id(service_id)
    messages_sent = dao_get_notification_count_for_service_message_ratio(
        service_id, current_year
    )
    messages_remaining = my_service.total_message_limit - messages_sent

    if my_service.total_message_limit - messages_sent < 0:
        raise Exception(
            f"Math error get_service_message_ratio(), \
                        total {my_service.total_message_limit} \
                        messages_sent {messages_sent} remaining {messages_remaining} \
                        service_id {service_id} current_year {current_year}"
        )

    return {
        "messages_sent": messages_sent,
        "messages_remaining": messages_remaining,
        "total_message_limit": my_service.total_message_limit,
    }, 200


@service_blueprint.route("/monthly-data-by-service")
def get_monthly_notification_data_by_service():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    rows = fact_notification_status_dao.fetch_monthly_notification_statuses_per_service(
        start_date, end_date
    )

    serialized_results = [
        [
            str(row.date_created),
            str(row.service_id),
            row.service_name,
            row.notification_type,
            row.count_sending,
            row.count_delivered,
            row.count_technical_failure,
            row.count_temporary_failure,
            row.count_permanent_failure,
            row.count_sent,
        ]
        for row in rows
    ]
    return jsonify(serialized_results)


def check_request_args(request):
    service_id = request.args.get("service_id")
    name = request.args.get("name", None)
    email_from = request.args.get("email_from", None)
    errors = []
    if not service_id:
        errors.append({"service_id": ["Can't be empty"]})
    if not name:
        errors.append({"name": ["Can't be empty"]})
    if not email_from:
        errors.append({"email_from": ["Can't be empty"]})
    if errors:
        raise InvalidRequest(errors, status_code=400)
    return service_id, name, email_from


def check_if_reply_to_address_already_in_use(service_id, email_address):
    existing_reply_to_addresses = dao_get_reply_to_by_service_id(service_id)
    if email_address in [i.email_address for i in existing_reply_to_addresses]:
        raise InvalidRequest(
            "Your service already uses ‘{}’ as an email reply-to address.".format(
                email_address
            ),
            status_code=409,
        )


@service_blueprint.route("/<uuid:service_id>/notification-count", methods=["GET"])
def get_notification_count_for_service_id(service_id):
    check_suspicious_id(service_id)
    count = dao_get_notification_count_for_service(service_id=service_id)
    return jsonify(count=count), 200
