from zoneinfo import ZoneInfo

import dateutil
from flask import Blueprint, current_app, jsonify, request

from app import db
from app.aws.s3 import (
    extract_personalisation,
    extract_phones,
    get_job_from_s3,
    get_job_metadata_from_s3,
    get_personalisation_from_s3,
    get_phone_number_from_s3,
)
from app.celery.tasks import process_job
from app.config import QueueNames
from app.dao.fact_notification_status_dao import fetch_notification_statuses_for_job
from app.dao.jobs_dao import (
    dao_create_job,
    dao_get_future_scheduled_job_by_id_and_service_id,
    dao_get_job_by_service_id_and_job_id,
    dao_get_jobs_by_service_id,
    dao_get_notification_outcomes_for_job,
    dao_get_scheduled_job_stats,
    dao_update_job,
)
from app.dao.notifications_dao import (
    dao_get_notification_count_for_job_id,
    get_notifications_for_job,
    get_recent_notifications_for_job,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.enums import JobStatus, NotificationStatus
from app.errors import InvalidRequest, register_errors
from app.schemas import (
    JobSchema,
    UnarchivedTemplateSchema,
    notification_with_template_schema,
    notifications_filter_schema,
)
from app.utils import check_suspicious_id, hilite, midnight_n_days_ago, pagination_links

job_blueprint = Blueprint("job", __name__, url_prefix="/service/<uuid:service_id>/job")


register_errors(job_blueprint)


@job_blueprint.route("/<job_id>", methods=["GET"])
def get_job_by_service_and_job_id(service_id, job_id):
    check_suspicious_id(service_id, job_id)
    job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    statistics = dao_get_notification_outcomes_for_job(service_id, job_id)
    data = JobSchema(session=db.session).dump(job)

    data["statistics"] = [
        {"status": statistic[1], "count": statistic[0]} for statistic in statistics
    ]

    return jsonify(data=data)


@job_blueprint.route("/<job_id>/status", methods=["GET"])
def get_job_status(service_id, job_id):
    """Fast job status endpoint for real-time polling. No S3 calls, no caching."""
    check_suspicious_id(service_id, job_id)

    job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    statistics = dao_get_notification_outcomes_for_job(service_id, job_id)

    delivered_statuses = (NotificationStatus.DELIVERED, NotificationStatus.SENT)
    failed_statuses = (NotificationStatus.FAILED,) + NotificationStatus.failed_types()

    delivered_count = failed_count = 0
    for stat in statistics:
        if stat.status in delivered_statuses:
            delivered_count += stat.count
        elif stat.status in failed_statuses:
            failed_count += stat.count

    total_count = job.notification_count or 0
    pending_calculated = max(0, total_count - delivered_count - failed_count)

    is_finished = job.processing_finished is not None and pending_calculated == 0

    response_data = {
        "total": total_count,
        "delivered": delivered_count,
        "failed": failed_count,
        "pending": pending_calculated,
        "finished": is_finished,
    }

    return jsonify(response_data)


@job_blueprint.route("/<job_id>/cancel", methods=["POST"])
def cancel_job(service_id, job_id):
    check_suspicious_id(service_id, job_id)

    job = dao_get_future_scheduled_job_by_id_and_service_id(job_id, service_id)
    job.job_status = JobStatus.CANCELLED
    dao_update_job(job)

    return get_job_by_service_and_job_id(service_id, job_id)


@job_blueprint.route("/<job_id>/notifications", methods=["GET"])
def get_all_notifications_for_service_job(service_id, job_id):

    check_suspicious_id(service_id, job_id)

    job = get_job_from_s3(service_id, job_id)
    phones = extract_phones(job, service_id, job_id)
    personalisation = extract_personalisation(job)
    data = notifications_filter_schema.load(request.args)
    page = data["page"] if "page" in data else 1
    page_size = (
        data["page_size"]
        if "page_size" in data
        else current_app.config.get("PAGE_SIZE")
    )
    paginated_notifications = get_notifications_for_job(
        service_id, job_id, filter_dict=data, page=page, page_size=page_size
    )

    kwargs = request.args.to_dict()
    kwargs["service_id"] = service_id
    kwargs["job_id"] = job_id

    for notification in paginated_notifications.items:
        if notification.job_id is not None:
            recipient = phones[notification.job_row_number]
            notification.to = recipient
            notification.normalised_to = recipient

    for notification in paginated_notifications.items:
        if notification.job_id is not None:
            notification.personalisation = personalisation[notification.job_row_number]

    notifications = None
    if data.get("format_for_csv"):
        notifications = [
            notification.serialize_for_csv()
            for notification in paginated_notifications.items
        ]
    else:
        notifications = notification_with_template_schema.dump(
            paginated_notifications.items, many=True
        )

    return (
        jsonify(
            notifications=notifications,
            page_size=page_size,
            total=paginated_notifications.total,
            links=pagination_links(
                paginated_notifications,
                ".get_all_notifications_for_service_job",
                **kwargs,
            ),
        ),
        200,
    )


@job_blueprint.route("/<job_id>/recent_notifications", methods=["GET"])
def get_recent_notifications_for_service_job(service_id, job_id):

    current_app.logger.info(hilite("ENTER get_recent_notifications_for_service_job"))
    check_suspicious_id(service_id, job_id)

    data = notifications_filter_schema.load(request.args)
    page = data["page"] if "page" in data else 1
    page_size = (
        data["page_size"]
        if "page_size" in data
        else current_app.config.get("PAGE_SIZE")
    )
    paginated_notifications = get_recent_notifications_for_job(
        service_id,
        job_id,
        filter_dict=data,
        page=page,
        page_size=page_size,
    )

    kwargs = request.args.to_dict()
    kwargs["service_id"] = service_id
    kwargs["job_id"] = job_id

    for notification in paginated_notifications.items:
        if notification.job_id is not None:
            recipient = get_phone_number_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )
            notification.to = recipient
            notification.normalised_to = recipient

    for notification in paginated_notifications.items:
        if notification.job_id is not None:
            notification.personalisation = get_personalisation_from_s3(
                notification.service_id,
                notification.job_id,
                notification.job_row_number,
            )

    notifications = None
    if data.get("format_for_csv"):
        notifications = [
            notification.serialize_for_csv()
            for notification in paginated_notifications.items
        ]
    else:
        notifications = notification_with_template_schema.dump(
            paginated_notifications.items, many=True
        )

    return (
        jsonify(
            notifications=notifications,
            page_size=page_size,
            total=paginated_notifications.total,
            links=pagination_links(
                paginated_notifications,
                ".get_all_notifications_for_service_job",
                **kwargs,
            ),
        ),
        200,
    )


@job_blueprint.route("/<job_id>/notification_count", methods=["GET"])
def get_notification_count_for_job_id(service_id, job_id):
    check_suspicious_id(service_id, job_id)

    dao_get_job_by_service_id_and_job_id(service_id, job_id)
    count = dao_get_notification_count_for_job_id(job_id=job_id)
    return jsonify(count=count), 200


@job_blueprint.route("", methods=["GET"])
def get_jobs_by_service(service_id):
    check_suspicious_id(service_id)
    if request.args.get("limit_days"):
        try:
            limit_days = int(request.args["limit_days"])
        except ValueError:
            errors = {"limit_days": [f"{request.args['limit_days']} is not an integer"]}
            raise InvalidRequest(errors, status_code=400)
    else:
        limit_days = None

    use_processing_time = (
        request.args.get("use_processing_time", "false").lower() == "true"
    )

    valid_statuses = set(JobStatus)
    statuses_arg = request.args.get("statuses", "")
    if statuses_arg == "":
        statuses = None
    else:
        statuses = []
        for x in statuses_arg.split(","):
            status = x.strip()
            if status in valid_statuses:
                statuses.append(status)
            else:
                statuses.append(None)
    return jsonify(
        **get_paginated_jobs(
            service_id,
            limit_days=limit_days,
            use_processing_time=use_processing_time,
            statuses=statuses,
            page=int(request.args.get("page", 1)),
        )
    )


@job_blueprint.route("", methods=["POST"])
def create_job(service_id):
    check_suspicious_id(service_id)

    """Entry point from UI for one-off messages as well as CSV uploads."""
    service = dao_fetch_service_by_id(service_id)
    if not service.active:
        raise InvalidRequest("Create job is not allowed: service is inactive ", 403)

    data = request.get_json()
    original_file_name = data.get("original_file_name")
    data.update({"service": service_id})
    try:
        data.update(**get_job_metadata_from_s3(service_id, data["id"]))
    except KeyError:
        raise InvalidRequest(
            {"id": ["Missing data for required field."]}, status_code=400
        )

    data["template"] = data.pop("template_id")
    check_suspicious_id(data["template"])
    template = dao_get_template_by_id(data["template"])

    if data.get("valid") != "True":
        raise InvalidRequest("File is not valid, can't create job", 400)

    schema = UnarchivedTemplateSchema(session=db.session)
    errors = schema.validate({"archived": template.archived})

    if errors:
        raise InvalidRequest(errors, status_code=400)

    data.update({"template_version": template.version})

    job = JobSchema(session=db.session).load(data)
    # See admin #1148, for whatever reason schema loading doesn't load this
    if original_file_name is not None:
        job.original_file_name = original_file_name

    if job.scheduled_for:
        job.job_status = JobStatus.SCHEDULED

    dao_create_job(job)

    sender_id = data.get("sender_id")
    check_suspicious_id(sender_id)
    # Kick off job in tasks.py
    if job.job_status == JobStatus.PENDING:
        process_job.apply_async(
            [str(job.id)], {"sender_id": sender_id}, queue=QueueNames.JOBS
        )

    job_json = JobSchema(session=db.session).dump(job)
    job_json["statistics"] = []

    return jsonify(data=job_json), 201


@job_blueprint.route("/scheduled-job-stats", methods=["GET"])
def get_scheduled_job_stats(service_id):
    check_suspicious_id(service_id)

    count, soonest_scheduled_for = dao_get_scheduled_job_stats(service_id)
    return (
        jsonify(
            count=count,
            soonest_scheduled_for=(
                soonest_scheduled_for.replace(tzinfo=ZoneInfo("UTC")).isoformat()
                if soonest_scheduled_for
                else None
            ),
        ),
        200,
    )


def get_paginated_jobs(
    service_id,
    *,
    limit_days,
    use_processing_time,
    statuses,
    page,
):

    current_app.logger.info(hilite("ENTER get_paginated_jobs"))
    pagination = dao_get_jobs_by_service_id(
        service_id,
        limit_days=limit_days,
        use_processing_time=use_processing_time,
        page=page,
        page_size=current_app.config["PAGE_SIZE"],
        statuses=statuses,
    )
    data = JobSchema(session=db.session).dump(pagination.items, many=True)
    for job_data in data:
        start = job_data["processing_started"]
        start = dateutil.parser.parse(start).replace(tzinfo=None) if start else None

        if start is None:
            statistics = []
        elif start.replace(tzinfo=None) < midnight_n_days_ago(3):
            # ft_notification_status table
            statistics = fetch_notification_statuses_for_job(job_data["id"])
        else:
            # notifications table
            statistics = dao_get_notification_outcomes_for_job(
                service_id, job_data["id"]
            )
        job_data["statistics"] = [
            {"status": statistic.status, "count": statistic.count}
            for statistic in statistics
        ]

    return {
        "data": data,
        "page_size": pagination.per_page,
        "total": pagination.total,
        "links": pagination_links(
            pagination, ".get_jobs_by_service", service_id=service_id
        ),
    }
