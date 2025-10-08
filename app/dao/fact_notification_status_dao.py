from datetime import timedelta

from sqlalchemy import Date, case, cast, delete, desc, func, select, union_all
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import extract, literal
from sqlalchemy.types import DateTime, Integer, Text

from app import db
from app.dao.dao_utils import autocommit
from app.enums import KeyType, NotificationStatus, NotificationType
from app.models import (
    FactNotificationStatus,
    Notification,
    NotificationAllTimeView,
    Service,
    Template,
    TemplateFolder,
    User,
    template_folder_map,
)
from app.utils import (
    get_midnight_in_utc,
    get_month_from_utc_column,
    midnight_n_days_ago,
    utc_now,
)


@autocommit
def update_fact_notification_status(process_day, notification_type, service_id):
    start_date = get_midnight_in_utc(process_day)
    end_date = get_midnight_in_utc(process_day + timedelta(days=1))

    # delete any existing rows in case some no longer exist e.g. if all messages are sent
    stmt = delete(FactNotificationStatus).where(
        FactNotificationStatus.local_date == process_day,
        FactNotificationStatus.notification_type == notification_type,
        FactNotificationStatus.service_id == service_id,
    )
    db.session.execute(stmt)
    db.session.commit()

    query = (
        select(
            literal(process_day).label("process_day"),
            NotificationAllTimeView.template_id,
            literal(service_id).label("service_id"),
            func.coalesce(
                NotificationAllTimeView.job_id, "00000000-0000-0000-0000-000000000000"
            ).label("job_id"),
            literal(notification_type).label("notification_type"),
            NotificationAllTimeView.key_type,
            NotificationAllTimeView.status,
            func.count().label("notification_count"),
        )
        .select_from(NotificationAllTimeView)
        .where(
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
            NotificationAllTimeView.notification_type == notification_type,
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type.in_((KeyType.NORMAL, KeyType.TEAM)),
        )
        .group_by(
            NotificationAllTimeView.template_id,
            NotificationAllTimeView.template_id,
            "job_id",
            NotificationAllTimeView.key_type,
            NotificationAllTimeView.status,
        )
    )

    db.session.connection().execute(
        insert(FactNotificationStatus.__table__).from_select(
            [
                FactNotificationStatus.local_date,
                FactNotificationStatus.template_id,
                FactNotificationStatus.service_id,
                FactNotificationStatus.job_id,
                FactNotificationStatus.notification_type,
                FactNotificationStatus.key_type,
                FactNotificationStatus.notification_status,
                FactNotificationStatus.notification_count,
            ],
            query,
        )
    )


def fetch_notification_status_for_service_by_month(start_date, end_date, service_id):
    stmt = (
        select(
            func.date_trunc("month", NotificationAllTimeView.created_at).label("month"),
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status.label("notification_status"),
            func.count(NotificationAllTimeView.id).label("count"),
        )
        .select_from(NotificationAllTimeView)
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
            NotificationAllTimeView.key_type != KeyType.TEST,
        )
        .group_by(
            func.date_trunc("month", NotificationAllTimeView.created_at).label("month"),
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
        )
        .order_by(desc(func.date_trunc("month", NotificationAllTimeView.created_at)))
    )
    return db.session.execute(stmt).all()


def fetch_notification_status_for_service_for_day(fetch_day, service_id):
    stmt = (
        select(
            # return current month as a datetime so the data has the same shape as the ft_notification_status query
            literal(fetch_day.replace(day=1), type_=DateTime).label("month"),
            Notification.notification_type,
            Notification.status.label("notification_status"),
            func.count().label("count"),
        )
        .select_from(Notification)
        .where(
            Notification.created_at >= get_midnight_in_utc(fetch_day),
            Notification.created_at
            < get_midnight_in_utc(fetch_day + timedelta(days=1)),
            Notification.service_id == service_id,
            Notification.key_type != KeyType.TEST,
        )
        .group_by(Notification.notification_type, Notification.status)
    )
    return db.session.execute(stmt).all()


def fetch_notification_status_for_service_for_today_and_7_previous_days(
    service_id: str, by_template: bool = False, limit_days: int = 7
) -> list[dict | None]:
    start_date = midnight_n_days_ago(limit_days)
    now = get_midnight_in_utc(utc_now())

    # Query for the last 7 days
    stats_for_7_days = select(
        cast(FactNotificationStatus.notification_type, Text).label("notification_type"),
        cast(FactNotificationStatus.notification_status, Text).label("status"),
        *(
            [
                FactNotificationStatus.template_id.label("template_id"),
                FactNotificationStatus.local_date.label("date_used"),
            ]
            if by_template
            else []
        ),
        FactNotificationStatus.notification_count.label("count"),
    ).where(
        FactNotificationStatus.service_id == service_id,
        FactNotificationStatus.local_date >= start_date,
        FactNotificationStatus.key_type != KeyType.TEST,
    )

    # Query for today's stats
    stats_for_today = (
        select(
            cast(Notification.notification_type, Text),
            cast(Notification.status, Text),
            *(
                [
                    Notification.template_id,
                    literal(now).label("date_used"),
                ]
                if by_template
                else []
            ),
            func.count().label("count"),
        )
        .where(
            Notification.created_at >= now,
            Notification.service_id == service_id,
            Notification.key_type != KeyType.TEST,
        )
        .group_by(
            Notification.notification_type,
            *([Notification.template_id] if by_template else []),
            Notification.status,
        )
    )

    # Combine the queries using union_all
    all_stats_union = union_all(stats_for_7_days, stats_for_today).subquery()
    all_stats_alias = aliased(all_stats_union, name="all_stats")

    # Final query with optional template joins
    stmt = select(
        *(
            [
                TemplateFolder.name.label("folder"),
                Template.name.label("template_name"),
                False,  # TODO: Handle `is_precompiled_letter`
                template_folder_map.c.template_folder_id,
                all_stats_alias.c.template_id,
                User.name.label("created_by"),
                Template.created_by_id,
                func.max(all_stats_alias.c.date_used).label(
                    "last_used"
                ),  # Get the most recent date
            ]
            if by_template
            else []
        ),
        all_stats_alias.c.notification_type,
        all_stats_alias.c.status,
        cast(func.sum(all_stats_alias.c.count), Integer).label("count"),
    )

    if by_template:
        stmt = (
            stmt.join(Template, all_stats_alias.c.template_id == Template.id)
            .join(User, Template.created_by_id == User.id)
            .outerjoin(
                template_folder_map, Template.id == template_folder_map.c.template_id
            )
            .outerjoin(
                TemplateFolder,
                TemplateFolder.id == template_folder_map.c.template_folder_id,
            )
        )

    # Group by all necessary fields except date_used
    stmt = stmt.group_by(
        *(
            [
                TemplateFolder.name,
                Template.name,
                all_stats_alias.c.template_id,
                User.name,
                template_folder_map.c.template_folder_id,
                Template.created_by_id,
            ]
            if by_template
            else []
        ),
        all_stats_alias.c.notification_type,
        all_stats_alias.c.status,
    )

    # Execute the query using Flask-SQLAlchemy's session
    result = db.session.execute(stmt)
    return result.mappings().all()


def fetch_notification_status_totals_for_all_services(start_date, end_date):
    stats = (
        select(
            FactNotificationStatus.notification_type.cast(db.Text).label(
                "notification_type"
            ),
            FactNotificationStatus.notification_status.cast(db.Text).label("status"),
            FactNotificationStatus.key_type.cast(db.Text).label("key_type"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .select_from(FactNotificationStatus)
        .where(
            FactNotificationStatus.local_date >= start_date,
            FactNotificationStatus.local_date <= end_date,
        )
        .group_by(
            FactNotificationStatus.notification_type,
            FactNotificationStatus.notification_status,
            FactNotificationStatus.key_type,
        )
    )
    today = get_midnight_in_utc(utc_now())
    if start_date <= utc_now().date() <= end_date:
        stats_for_today = (
            select(
                Notification.notification_type.cast(db.Text).label("notification_type"),
                Notification.status.cast(db.Text),
                Notification.key_type.cast(db.Text),
                func.count().label("count"),
            )
            .where(Notification.created_at >= today)
            .group_by(
                Notification.notification_type,
                Notification.status,
                Notification.key_type,
            )
        )
        all_stats_table = stats.union_all(stats_for_today).subquery()
        query = (
            select(
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
                all_stats_table.c.key_type,
                func.cast(func.sum(all_stats_table.c.count), Integer).label("count"),
            )
            .group_by(
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
                all_stats_table.c.key_type,
            )
            .order_by(all_stats_table.c.notification_type)
        )
    else:
        query = stats.order_by(FactNotificationStatus.notification_type)
    return db.session.execute(query).all()


def fetch_notification_statuses_for_job(job_id):
    stmt = (
        select(
            FactNotificationStatus.notification_status.label("status"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .select_from(FactNotificationStatus)
        .where(
            FactNotificationStatus.job_id == job_id,
        )
        .group_by(FactNotificationStatus.notification_status)
    )
    return db.session.execute(stmt).all()


def fetch_stats_for_all_services_by_date_range(
    start_date, end_date, include_from_test_key=True
):
    stats = (
        select(
            FactNotificationStatus.service_id.label("service_id"),
            Service.name.label("name"),
            Service.restricted.label("restricted"),
            Service.active.label("active"),
            Service.created_at.label("created_at"),
            FactNotificationStatus.notification_type.cast(db.Text).label(
                "notification_type"
            ),
            FactNotificationStatus.notification_status.cast(db.Text).label("status"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .select_from(FactNotificationStatus)
        .where(
            FactNotificationStatus.local_date >= start_date,
            FactNotificationStatus.local_date <= end_date,
            FactNotificationStatus.service_id == Service.id,
        )
        .group_by(
            FactNotificationStatus.service_id.label("service_id"),
            Service.name,
            Service.restricted,
            Service.active,
            Service.created_at,
            FactNotificationStatus.notification_type,
            FactNotificationStatus.notification_status,
        )
        .order_by(
            FactNotificationStatus.service_id, FactNotificationStatus.notification_type
        )
    )
    if not include_from_test_key:
        stats = stats.where(FactNotificationStatus.key_type != KeyType.TEST)

    if start_date <= utc_now().date() <= end_date:
        today = get_midnight_in_utc(utc_now())
        substmt = (
            select(
                Notification.notification_type.label("notification_type"),
                Notification.status.label("status"),
                Notification.service_id.label("service_id"),
                func.count(Notification.id).label("count"),
            )
            .select_from(Notification)
            .where(Notification.created_at >= today)
            .group_by(
                Notification.notification_type,
                Notification.status,
                Notification.service_id,
            )
        )
        if not include_from_test_key:
            substmt = substmt.where(Notification.key_type != KeyType.TEST)
        substmt = substmt.subquery()

        stats_for_today = select(
            Service.id.label("service_id"),
            Service.name.label("name"),
            Service.restricted.label("restricted"),
            Service.active.label("active"),
            Service.created_at.label("created_at"),
            substmt.c.notification_type.cast(db.Text).label("notification_type"),
            substmt.c.status.cast(db.Text).label("status"),
            substmt.c.count.label("count"),
        ).outerjoin(substmt, substmt.c.service_id == Service.id)

        all_stats_table = stats.union_all(stats_for_today).subquery()
        query = (
            select(
                all_stats_table.c.service_id,
                all_stats_table.c.name,
                all_stats_table.c.restricted,
                all_stats_table.c.active,
                all_stats_table.c.created_at,
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
                func.cast(func.sum(all_stats_table.c.count), Integer).label("count"),
            )
            .group_by(
                all_stats_table.c.service_id,
                all_stats_table.c.name,
                all_stats_table.c.restricted,
                all_stats_table.c.active,
                all_stats_table.c.created_at,
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
            )
            .order_by(
                all_stats_table.c.name,
                all_stats_table.c.notification_type,
                all_stats_table.c.status,
            )
        )
    else:
        query = stats
    return db.session.execute(query).all()


def fetch_monthly_template_usage_for_service(start_date, end_date, service_id):
    # services_dao.replaces dao_fetch_monthly_historical_usage_by_template_for_service
    stats = (
        select(
            FactNotificationStatus.template_id.label("template_id"),
            Template.name.label("name"),
            Template.template_type.label("template_type"),
            extract("month", FactNotificationStatus.local_date).label("month"),
            extract("year", FactNotificationStatus.local_date).label("year"),
            func.sum(FactNotificationStatus.notification_count).label("count"),
        )
        .join(Template, FactNotificationStatus.template_id == Template.id)
        .where(
            FactNotificationStatus.service_id == service_id,
            FactNotificationStatus.local_date >= start_date,
            FactNotificationStatus.local_date <= end_date,
            FactNotificationStatus.key_type != KeyType.TEST,
            FactNotificationStatus.notification_status != NotificationStatus.CANCELLED,
        )
        .group_by(
            FactNotificationStatus.template_id,
            Template.name,
            Template.template_type,
            extract("month", FactNotificationStatus.local_date).label("month"),
            extract("year", FactNotificationStatus.local_date).label("year"),
        )
        .order_by(
            extract("year", FactNotificationStatus.local_date),
            extract("month", FactNotificationStatus.local_date),
            Template.name,
        )
    )

    if start_date <= utc_now() <= end_date:
        today = get_midnight_in_utc(utc_now())
        month = get_month_from_utc_column(Notification.created_at)

        stats_for_today = (
            select(
                Notification.template_id.label("template_id"),
                Template.name.label("name"),
                Template.template_type.label("template_type"),
                extract("month", month).label("month"),
                extract("year", month).label("year"),
                func.count().label("count"),
            )
            .join(
                Template,
                Notification.template_id == Template.id,
            )
            .where(
                Notification.created_at >= today,
                Notification.service_id == service_id,
                Notification.key_type != KeyType.TEST,
                Notification.status != NotificationStatus.CANCELLED,
            )
            .group_by(
                Notification.template_id,
                Template.hidden,
                Template.name,
                Template.template_type,
                month,
            )
        )

        all_stats_table = stats.union_all(stats_for_today).subquery()
        query = (
            select(
                all_stats_table.c.template_id,
                all_stats_table.c.name,
                all_stats_table.c.template_type,
                func.cast(all_stats_table.c.month, Integer).label("month"),
                func.cast(all_stats_table.c.year, Integer).label("year"),
                func.cast(func.sum(all_stats_table.c.count), Integer).label("count"),
            )
            .group_by(
                all_stats_table.c.template_id,
                all_stats_table.c.name,
                all_stats_table.c.template_type,
                all_stats_table.c.month,
                all_stats_table.c.year,
            )
            .order_by(
                all_stats_table.c.year, all_stats_table.c.month, all_stats_table.c.name
            )
        )
    else:
        query = stats
    return db.session.execute(query).all()


def get_total_notifications_for_date_range(start_date, end_date):
    stmt = (
        select(
            FactNotificationStatus.local_date.label("local_date"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_type
                        == NotificationType.EMAIL,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("emails"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_type
                        == NotificationType.SMS,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("sms"),
        )
        .where(
            FactNotificationStatus.key_type != KeyType.TEST,
        )
        .group_by(FactNotificationStatus.local_date)
        .order_by(FactNotificationStatus.local_date)
    )
    if start_date and end_date:
        stmt = stmt.where(
            FactNotificationStatus.local_date >= start_date,
            FactNotificationStatus.local_date <= end_date,
        )
    return db.session.execute(stmt).all()


def fetch_monthly_notification_statuses_per_service(start_date, end_date):
    stmt = (
        select(
            func.date_trunc("month", FactNotificationStatus.local_date)
            .cast(Date)
            .label("date_created"),
            Service.id.label("service_id"),
            Service.name.label("service_name"),
            FactNotificationStatus.notification_type,
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status.in_(
                            [NotificationStatus.SENDING, NotificationStatus.PENDING]
                        ),
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_sending"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status
                        == NotificationStatus.DELIVERED,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_delivered"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status.in_(
                            [
                                NotificationStatus.TECHNICAL_FAILURE,
                                NotificationStatus.FAILED,
                            ]
                        ),
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_technical_failure"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status
                        == NotificationStatus.TEMPORARY_FAILURE,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_temporary_failure"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status
                        == NotificationStatus.PERMANENT_FAILURE,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_permanent_failure"),
            func.sum(
                case(
                    (
                        FactNotificationStatus.notification_status
                        == NotificationStatus.SENT,
                        FactNotificationStatus.notification_count,
                    ),
                    else_=0,
                )
            ).label("count_sent"),
        )
        .join(Service, FactNotificationStatus.service_id == Service.id)
        .where(
            FactNotificationStatus.notification_status != NotificationStatus.CREATED,
            Service.active.is_(True),
            FactNotificationStatus.key_type != KeyType.TEST,
            Service.restricted.is_(False),
            FactNotificationStatus.local_date >= start_date,
            FactNotificationStatus.local_date <= end_date,
        )
        .group_by(
            Service.id,
            Service.name,
            func.date_trunc("month", FactNotificationStatus.local_date).cast(Date),
            FactNotificationStatus.notification_type,
        )
        .order_by(
            func.date_trunc("month", FactNotificationStatus.local_date).cast(Date),
            Service.id,
            FactNotificationStatus.notification_type,
        )
    )
    return db.session.execute(stmt).all()
