from os import getenv

from flask import current_app
from sqlalchemy import String, and_, desc, func, literal, select, text, union

from app import db
from app.dao.inbound_sms_dao import Pagination
from app.enums import JobStatus, NotificationStatus, NotificationType
from app.models import Job, Notification, ServiceDataRetention, Template
from app.utils import midnight_n_days_ago, utc_now


def _get_printing_day(created_at):
    return func.date_trunc(
        "day",
        func.timezone(
            getenv("TIMEZONE", "America/New_York"), func.timezone("UTC", created_at)
        )
        + text(
            # We add 6 hours 30 minutes to the local created_at time so that
            # any letters created after 5:30pm get shifted into the next day
            "interval '6 hours 30 minutes'"
        ),
    )


def _get_printing_datetime(created_at):
    return _get_printing_day(created_at) + text(
        # Letters are printed from 5:30pm each day
        "interval '17 hours 30 minutes'"
    )


def _naive_gmt_to_utc(column):
    return func.timezone(
        "UTC", func.timezone(getenv("TIMEZONE", "America/New_York"), column)
    )


def dao_get_uploads_by_service_id(service_id, limit_days=None, page=1, page_size=50):
    # Hardcoded filter to exclude cancelled or scheduled jobs
    # for the moment, but we may want to change this method take 'statuses' as a argument in the future
    today = utc_now().date()
    jobs_query_filter = [
        Job.service_id == service_id,
        Job.original_file_name != current_app.config["TEST_MESSAGE_FILENAME"],
        Job.original_file_name != current_app.config["ONE_OFF_MESSAGE_FILENAME"],
        Job.job_status.notin_([JobStatus.CANCELLED, JobStatus.SCHEDULED]),
        func.coalesce(Job.processing_started, Job.created_at)
        >= today - func.coalesce(ServiceDataRetention.days_of_retention, 7),
    ]
    if limit_days is not None:
        jobs_query_filter.append(Job.created_at >= midnight_n_days_ago(limit_days))

    jobs_querie = (
        select(
            Job.id,
            Job.original_file_name,
            Job.notification_count,
            Template.template_type,
            func.coalesce(ServiceDataRetention.days_of_retention, 7).label(
                "days_of_retention"
            ),
            Job.created_at.label("created_at"),
            Job.scheduled_for.label("scheduled_for"),
            Job.processing_started.label("processing_started"),
            Job.job_status.label("status"),
            literal("job").label("upload_type"),
            literal(None).label("recipient"),
        )
        .select_from(Job)
        .join(Template, Job.template_id == Template.id)
        .outerjoin(
            ServiceDataRetention,
            and_(
                Template.service_id == ServiceDataRetention.service_id,
                func.cast(Template.template_type, String)
                == func.cast(ServiceDataRetention.notification_type, String),
            ),
        )
        .where(*jobs_query_filter)
    )

    letters_query_filter = [
        Notification.service_id == service_id,
        Notification.notification_type == NotificationType.LETTER,
        Notification.api_key_id == None,  # noqa
        Notification.status != NotificationStatus.CANCELLED,
        Template.hidden == True,  # noqa
        Notification.created_at
        >= today - func.coalesce(ServiceDataRetention.days_of_retention, 7),
    ]
    if limit_days is not None:
        letters_query_filter.append(
            Notification.created_at >= midnight_n_days_ago(limit_days)
        )

    letters_subquerie = (
        select(
            func.count().label("notification_count"),
            _naive_gmt_to_utc(_get_printing_datetime(Notification.created_at)).label(
                "printing_at"
            ),
        )
        .select_from(Notification)
        .join(Template, Notification.template_id == Template.id)
        .outerjoin(
            ServiceDataRetention,
            and_(
                Template.service_id == ServiceDataRetention.service_id,
                func.cast(Template.template_type, String)
                == func.cast(ServiceDataRetention.notification_type, String),
            ),
        )
        .where(*letters_query_filter)
        .group_by("printing_at")
        .subquery()
    )

    letters_querie = (
        select(
            literal(None).label("id"),
            literal("Uploaded letters").label("original_file_name"),
            letters_subquerie.c.notification_count.label("notification_count"),
            literal("letter").label("template_type"),
            literal(None).label("days_of_retention"),
            letters_subquerie.c.printing_at.label("created_at"),
            literal(None).label("scheduled_for"),
            letters_subquerie.c.printing_at.label("processing_started"),
            literal(None).label("status"),
            literal("letter_day").label("upload_type"),
            literal(None).label("recipient"),
        )
        .select_from(Notification)
        .group_by(
            letters_subquerie.c.notification_count,
            letters_subquerie.c.printing_at,
        )
    )

    stmt = union(jobs_querie, letters_querie).order_by(
        desc("processing_started"), desc("created_at")
    )

    results = db.session.execute(stmt).scalars().all()
    page_size = current_app.config["PAGE_SIZE"]
    offset = (page - 1) * page_size
    paginated_results = results[offset : offset + page_size]
    pagination = Pagination(paginated_results, page, page_size, len(results))
    return pagination
