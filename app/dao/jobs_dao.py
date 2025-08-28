import os
import uuid
from datetime import timedelta

from flask import current_app
from sqlalchemy import and_, asc, desc, func, select, update

from app import db
from app.dao.pagination import Pagination
from app.enums import JobStatus
from app.models import (
    FactNotificationStatus,
    Job,
    Notification,
    ServiceDataRetention,
    Template,
)
from app.utils import midnight_n_days_ago, utc_now


def dao_get_notification_outcomes_for_job(service_id, job_id):
    stmt = (
        select(func.count(Notification.status).label("count"), Notification.status)
        .where(Notification.service_id == service_id, Notification.job_id == job_id)
        .group_by(Notification.status)
    )
    notification_statuses = db.session.execute(stmt).all()

    if not notification_statuses:
        stmt = select(
            FactNotificationStatus.notification_count.label("count"),
            FactNotificationStatus.notification_status.label("status"),
        ).where(
            FactNotificationStatus.service_id == service_id,
            FactNotificationStatus.job_id == job_id,
        )
        notification_statuses = db.session.execute(stmt).all()
    return notification_statuses


def dao_get_job_by_service_id_and_job_id(service_id, job_id):
    stmt = select(Job).where(Job.service_id == service_id, Job.id == job_id)
    return db.session.execute(stmt).scalars().one()


def dao_get_unfinished_jobs():

    stmt = select(Job).filter(Job.processing_finished.is_(None))
    return db.session.execute(stmt).scalars().all()


def dao_get_jobs_by_service_id(
    service_id,
    *,
    limit_days=None,
    use_processing_time=False,
    page=1,
    page_size=50,
    statuses=None,
):
    query_filter = [
        Job.service_id == service_id,
        Job.original_file_name != current_app.config["TEST_MESSAGE_FILENAME"],
        Job.original_file_name != current_app.config["ONE_OFF_MESSAGE_FILENAME"],
    ]
    if limit_days is not None:
        if use_processing_time:
            query_filter.append(
                func.coalesce(Job.processing_started, Job.created_at)
                >= midnight_n_days_ago(limit_days)
            )
        else:
            query_filter.append(Job.created_at >= midnight_n_days_ago(limit_days))
    if statuses is not None and statuses != [""]:
        query_filter.append(Job.job_status.in_(statuses))

    total_items = db.session.execute(
        select(func.count()).select_from(Job).where(*query_filter)
    ).scalar_one()

    offset = (page - 1) * page_size
    stmt = (
        select(Job)
        .where(*query_filter)
        .order_by(
            func.coalesce(Job.processing_started, Job.created_at).desc(), Job.id.desc()
        )
        .limit(page_size)
        .offset(offset)
    )
    items = db.session.execute(stmt).scalars().all()
    return Pagination(items, page, page_size, total_items)


def dao_get_scheduled_job_stats(
    service_id,
):

    stmt = select(
        func.count(Job.id),
        func.min(Job.scheduled_for),
    ).where(
        Job.service_id == service_id,
        Job.job_status == JobStatus.SCHEDULED,
    )
    return db.session.execute(stmt).one()


def dao_get_job_by_id(job_id):
    stmt = select(Job).where(Job.id == job_id)
    return db.session.execute(stmt).scalars().one()


def dao_archive_job(job):
    job.archived = True
    db.session.add(job)
    db.session.commit()


def dao_set_scheduled_jobs_to_pending():
    """
    Sets all past scheduled jobs to pending, and then returns them for further processing.

    this is used in the run_scheduled_jobs task, so we put a FOR UPDATE lock on the job table for the duration of
    the transaction so that if the task is run more than once concurrently, one task will block the other select
    from completing until it commits.
    """
    stmt = (
        select(Job)
        .where(
            Job.job_status == JobStatus.SCHEDULED,
            Job.scheduled_for < utc_now(),
        )
        .order_by(asc(Job.scheduled_for))
        .with_for_update()
    )
    jobs = db.session.execute(stmt).scalars().all()

    for job in jobs:
        job.job_status = JobStatus.PENDING

    db.session.add_all(jobs)
    db.session.commit()

    return jobs


def dao_get_future_scheduled_job_by_id_and_service_id(job_id, service_id):
    stmt = select(Job).where(
        Job.service_id == service_id,
        Job.id == job_id,
        Job.job_status == JobStatus.SCHEDULED,
        Job.scheduled_for > utc_now(),
    )
    return db.session.execute(stmt).scalars().one()


def dao_create_job(job):
    if not job.id:
        job.id = uuid.uuid4()
    db.session.add(job)
    db.session.commit()
    # We are seeing weird time anomalies where a job can be created on
    # 8/19 yet show a created_at time of 8/16.  This seems to be the only
    # place the created_at value is set so do some double-checking and debugging
    orig_time = job.created_at
    now_time = utc_now()
    diff_time = now_time - orig_time
    current_app.logger.warning(
        f"#notify-debug-admin-1859 dao_create_job orig created at {orig_time} and now {now_time}"
    )
    if diff_time.total_seconds() > 300:  # It should be only a few seconds diff at most
        current_app.logger.warning(
            "#notify-debug-admin-1859 Something is wrong with job.created_at!"
        )
        if os.getenv("NOTIFY_ENVIRONMENT") not in ["test"]:
            job.created_at = now_time
            dao_update_job(job)
            current_app.logger.warning(
                f"#notify-debug-admin-1859 Job created_at reset to {job.created_at}"
            )


def dao_update_job(job):
    db.session.add(job)
    db.session.commit()


def dao_update_job_status_to_error(job):
    stmt = update(Job).where(Job.id == job.id).values(job_status=JobStatus.ERROR)
    db.session.execute(stmt)
    db.session.commit()


def dao_get_jobs_older_than_data_retention(notification_types):
    stmt = select(ServiceDataRetention).where(
        ServiceDataRetention.notification_type.in_(notification_types)
    )
    flexible_data_retention = db.session.execute(stmt).scalars().all()
    jobs = []
    today = utc_now().date()
    for f in flexible_data_retention:
        end_date = today - timedelta(days=f.days_of_retention)
        stmt = (
            select(Job)
            .join(Template)
            .where(
                func.coalesce(Job.scheduled_for, Job.created_at) < end_date,
                Job.archived == False,  # noqa
                Template.template_type == f.notification_type,
                Job.service_id == f.service_id,
            )
            .order_by(desc(Job.created_at))
        )
        jobs.extend(db.session.execute(stmt).scalars().all())

    # notify-api-1287, make default data retention 7 days, 23 hours
    end_date = today - timedelta(days=7, hours=23)
    for notification_type in notification_types:
        services_with_data_retention = [
            x.service_id
            for x in flexible_data_retention
            if x.notification_type == notification_type
        ]
        stmt = (
            select(Job)
            .join(Template)
            .where(
                func.coalesce(Job.scheduled_for, Job.created_at) < end_date,
                Job.archived == False,  # noqa
                Template.template_type == notification_type,
                Job.service_id.notin_(services_with_data_retention),
            )
            .order_by(desc(Job.created_at))
        )
        jobs.extend(db.session.execute(stmt).scalars().all())

    return jobs


def find_jobs_with_missing_rows():
    # Jobs can be a maximum of 100,000 rows. It typically takes 10 minutes to create all those notifications.
    # Using 20 minutes as a condition seems reasonable.
    ten_minutes_ago = utc_now() - timedelta(minutes=20)
    yesterday = utc_now() - timedelta(days=1)
    jobs_with_rows_missing = (
        select(Job)
        .where(
            Job.job_status == JobStatus.FINISHED,
            Job.processing_finished < ten_minutes_ago,
            Job.processing_finished > yesterday,
            Job.id == Notification.job_id,
        )
        .group_by(Job)
        .having(func.count(Notification.id) != Job.notification_count)
    )

    return db.session.execute(jobs_with_rows_missing).scalars().all()


def find_missing_row_for_job(job_id, job_size):
    expected_row_numbers = select(
        func.generate_series(0, job_size - 1).label("row")
    ).subquery()

    query = (
        select(
            Notification.job_row_number, expected_row_numbers.c.row.label("missing_row")
        )
        .outerjoin(
            Notification,
            and_(
                expected_row_numbers.c.row == Notification.job_row_number,
                Notification.job_id == job_id,
            ),
        )
        .where(Notification.job_row_number == None)  # noqa
    )
    return db.session.execute(query).all()
