from datetime import timedelta

from flask import current_app
from sqlalchemy import desc, func, select

from app import db
from app.dao.dao_utils import autocommit
from app.dao.inbound_sms_dao import Pagination
from app.models import Complaint
from app.utils import get_midnight_in_utc


@autocommit
def save_complaint(complaint):
    db.session.add(complaint)


def fetch_paginated_complaints(page=1):
    page_size = current_app.config["PAGE_SIZE"]
    total_count = db.session.scalar(select(func.count()).select_from(Complaint))
    offset = (page - 1) * page_size
    stmt = (
        select(Complaint)
        .order_by(desc(Complaint.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = db.session.execute(stmt).scalars().all()
    pagination = Pagination(result, page=page, per_page=page_size, total=total_count)
    return pagination


def fetch_complaints_by_service(service_id):
    stmt = (
        select(Complaint)
        .filter_by(service_id=service_id)
        .order_by(desc(Complaint.created_at))
    )
    return db.session.execute(stmt).scalars().all()


def fetch_count_of_complaints(start_date, end_date):
    start_date = get_midnight_in_utc(start_date)
    end_date = get_midnight_in_utc(end_date + timedelta(days=1))

    stmt = (
        select(func.count())
        .select_from(Complaint)
        .filter(Complaint.created_at >= start_date, Complaint.created_at < end_date)
    )
    return db.session.execute(stmt).scalar() or 0
