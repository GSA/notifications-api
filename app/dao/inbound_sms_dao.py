from flask import current_app
from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from app import db
from app.dao.dao_utils import autocommit
from app.enums import NotificationType
from app.models import InboundSms, InboundSmsHistory, ServiceDataRetention
from app.utils import midnight_n_days_ago


@autocommit
def dao_create_inbound_sms(inbound_sms):
    db.session.add(inbound_sms)


def dao_get_inbound_sms_for_service(
    service_id, user_number=None, *, limit_days=None, limit=None
):
    q = (
        select(InboundSms)
        .where(InboundSms.service_id == service_id)
        .order_by(InboundSms.created_at.desc())
    )
    if limit_days is not None:
        start_date = midnight_n_days_ago(limit_days)
        q = q.where(InboundSms.created_at >= start_date)

    if user_number:
        q = q.where(InboundSms.user_number == user_number)

    if limit:
        q = q.limit(limit)

    return db.session.execute(q).scalars().all()


def dao_get_paginated_inbound_sms_for_service_for_public_api(
    service_id, older_than=None, page_size=None
):
    if page_size is None:
        page_size = current_app.config["PAGE_SIZE"]

    filters = [InboundSms.service_id == service_id]

    if older_than:
        older_than_created_at = (
            db.session.query(InboundSms.created_at)
            .where(InboundSms.id == older_than)
            .scalar_subquery()
        )
        filters.append(InboundSms.created_at < older_than_created_at)

    page = 1  # ?
    offset = (page - 1) * page_size
    # As part of the move to sqlalchemy 2.0, we do this manual pagination
    stmt = (
        select(InboundSms)
        .where(*filters)
        .order_by(desc(InboundSms.created_at))
        .limit(page_size)
        .offset(offset)
    )
    paginated_items = db.session.execute(stmt).scalars().all()
    total_items = db.session.execute(select(func.count()).where(*filters)).scalar() or 0
    pagination = Pagination(paginated_items, page, page_size, total_items)
    return pagination


def dao_count_inbound_sms_for_service(service_id, limit_days):
    stmt = (
        select(func.count())
        .select_from(InboundSms)
        .where(
            InboundSms.service_id == service_id,
            InboundSms.created_at >= midnight_n_days_ago(limit_days),
        )
    )
    result = db.session.execute(stmt).scalar()
    return result


def _insert_inbound_sms_history(subquery, query_limit=10000):
    offset = 0
    subquery_select = select(subquery)
    inbound_sms_stmt = select(
        InboundSms.id,
        InboundSms.created_at,
        InboundSms.service_id,
        InboundSms.notify_number,
        InboundSms.provider_date,
        InboundSms.provider_reference,
        InboundSms.provider,
    ).where(InboundSms.id.in_(subquery_select))

    count_query = select(func.count()).select_from(inbound_sms_stmt.subquery())
    inbound_sms_count = db.session.execute(count_query).scalar() or 0

    while offset < inbound_sms_count:
        statement = insert(InboundSmsHistory).from_select(
            InboundSmsHistory.__table__.c,
            inbound_sms_stmt.limit(query_limit).offset(offset),
        )

        statement = statement.on_conflict_do_nothing(
            constraint="inbound_sms_history_pkey"
        )
        db.session.execute(statement)
        db.session.commit()

        offset += query_limit


def _delete_inbound_sms(datetime_to_delete_from, query_filter):
    query_limit = 10000

    subquery = (
        select(InboundSms.id)
        .where(InboundSms.created_at < datetime_to_delete_from, *query_filter)
        .limit(query_limit)
        .subquery()
    )

    deleted = 0
    # set to nonzero just to enter the loop
    number_deleted = 1
    while number_deleted > 0:
        _insert_inbound_sms_history(subquery, query_limit=query_limit)

        stmt = delete(InboundSms).where(InboundSms.id.in_(select(subquery.c.id)))
        number_deleted = db.session.execute(stmt).rowcount
        db.session.commit()
        deleted += number_deleted

    return deleted


@autocommit
def delete_inbound_sms_older_than_retention():
    current_app.logger.info(
        "Deleting inbound sms for services with flexible data retention"
    )

    stmt = (
        select(ServiceDataRetention)
        .join(ServiceDataRetention.service)
        .where(ServiceDataRetention.notification_type == NotificationType.SMS)
    )
    flexible_data_retention = db.session.execute(stmt).scalars().all()

    deleted = 0

    for f in flexible_data_retention:
        n_days_ago = midnight_n_days_ago(f.days_of_retention)

        current_app.logger.info(
            "Deleting inbound sms for service id: {}".format(f.service_id)
        )
        deleted += _delete_inbound_sms(
            n_days_ago, query_filter=[InboundSms.service_id == f.service_id]
        )

    current_app.logger.info(
        "Deleting inbound sms for services without flexible data retention"
    )

    seven_days_ago = midnight_n_days_ago(7)

    deleted += _delete_inbound_sms(
        seven_days_ago,
        query_filter=[
            InboundSms.service_id.notin_(x.service_id for x in flexible_data_retention),
        ],
    )

    current_app.logger.info("Deleted {} inbound sms".format(deleted))

    return deleted


def dao_get_inbound_sms_by_id(service_id, inbound_id):
    stmt = select(InboundSms).where(
        InboundSms.id == inbound_id, InboundSms.service_id == service_id
    )
    return db.session.execute(stmt).scalars().one()


def dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service(
    service_id, page, limit_days
):
    """
    This query starts from inbound_sms and joins on to itself to find the most recent row for each user_number.

    Equivalent sql:

    SELECT t1.*
    FROM inbound_sms t1
    LEFT OUTER JOIN inbound_sms AS t2 ON (
        -- identifying
        t1.user_number = t2.user_number AND
        t1.service_id = t2.service_id AND
        -- ordering
        t1.created_at < t2.created_at
    )
    WHERE t2.id IS NULL AND t1.service_id = :service_id
    ORDER BY t1.created_at DESC;
    LIMIT 50 OFFSET :page
    """
    t2 = aliased(InboundSms)
    q = (
        select(InboundSms)
        .outerjoin(
            t2,
            and_(
                InboundSms.user_number == t2.user_number,
                InboundSms.service_id == t2.service_id,
                InboundSms.created_at < t2.created_at,
            ),
        )
        .where(
            t2.id.is_(None),  # noqa
            InboundSms.service_id == service_id,
            InboundSms.created_at >= midnight_n_days_ago(limit_days),
        )
        .order_by(InboundSms.created_at.desc())
    )
    result = db.session.execute(q).scalars().all()
    page_size = current_app.config["PAGE_SIZE"]
    offset = (page - 1) * page_size
    paginated_results = result[offset : offset + page_size]
    pagination = Pagination(paginated_results, page, page_size, len(result))
    return pagination


# TODO remove this when billing dao PR is merged.
class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = (total + per_page - 1) // per_page
        self.prev_num = page - 1 if page > 1 else None
        self.next_num = page + 1 if page < self.pages else None

    def has_next(self):
        return self.page < self.pages

    def has_prev(self):
        return self.page > 1
