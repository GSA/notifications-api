import json
import os
from datetime import datetime, timedelta
from time import time

from flask import current_app
from sqlalchemy import (
    TIMESTAMP,
    asc,
    cast,
    delete,
    desc,
    func,
    or_,
    select,
    text,
    union,
    update,
)
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import functions
from sqlalchemy.sql.expression import case
from werkzeug.datastructures import MultiDict

from app import create_uuid, db
from app.dao.dao_utils import autocommit
from app.dao.inbound_sms_dao import Pagination
from app.enums import KeyType, NotificationStatus, NotificationType
from app.models import (
    FactNotificationStatus,
    Notification,
    NotificationHistory,
    Template,
)
from app.utils import (
    escape_special_characters,
    get_midnight_in_utc,
    midnight_n_days_ago,
    utc_now,
)
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES
from notifications_utils.recipients import (
    InvalidEmailError,
    try_validate_and_format_phone_number,
    validate_and_format_email_address,
)


def dao_get_last_date_template_was_used(template_id, service_id):
    last_date_from_notifications = (
        db.session.query(functions.max(Notification.created_at))
        .where(
            Notification.service_id == service_id,
            Notification.template_id == template_id,
            Notification.key_type != KeyType.TEST,
        )
        .scalar()
    )

    if last_date_from_notifications:
        return last_date_from_notifications

    last_date = (
        db.session.query(functions.max(FactNotificationStatus.local_date))
        .where(
            FactNotificationStatus.template_id == template_id,
            FactNotificationStatus.key_type != KeyType.TEST,
        )
        .scalar()
    )

    return last_date


def dao_notification_exists(notification_id) -> bool:
    stmt = select(Notification).where(Notification.id == notification_id)
    result = db.session.execute(stmt).scalar()
    return result is not None


@autocommit
def dao_create_notification(notification):
    if not notification.id:
        # need to populate defaulted fields before we create the notification history object
        notification.id = create_uuid()
    if not notification.status:
        notification.status = NotificationStatus.CREATED

    # notify-api-749 do not write to db
    # if we have a verify_code we know this is the authentication notification at login time
    # and not csv (containing PII) provided by the user, so allow verify_code to continue to exist
    if "verify_code" in str(notification.personalisation):
        pass
    else:
        notification.personalisation = ""

    # notify-api-742 remove phone numbers from db
    notification.to = "1"
    notification.normalised_to = "1"

    # notify-api-1454 insert only if it doesn't exist
    if not dao_notification_exists(notification.id):
        db.session.add(notification)
        # There have been issues with invites expiring.
        # Ensure the created at value is set and debug.
        if notification.notification_type == "email":
            orig_time = notification.created_at
            now_time = utc_now()
            try:
                diff_time = now_time - orig_time
            except TypeError:
                try:
                    orig_time = datetime.strptime(orig_time, "%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    orig_time = datetime.strptime(orig_time, "%Y-%m-%d")
                diff_time = now_time - orig_time
            current_app.logger.warning(
                f"dao_create_notification orig created at: {orig_time} and now created at: {now_time}"
            )
            if diff_time.total_seconds() > 300:
                current_app.logger.warning(
                    "Something is wrong with notification.created_at in email!"
                )
                if os.getenv("NOTIFY_ENVIRONMENT") not in ["test"]:
                    notification.created_at = now_time
                    dao_update_notification(notification)
                    current_app.logger.warning(
                        f"Email notification created_at reset to   {notification.created_at}"
                    )


def country_records_delivery(phone_prefix):
    dlr = INTERNATIONAL_BILLING_RATES[phone_prefix]["attributes"]["dlr"]
    return dlr and dlr.lower() == "yes"


def _decide_permanent_temporary_failure(current_status, status):
    # If we go from pending to delivered we need to set failure type as temporary-failure
    if (
        current_status == NotificationStatus.PENDING
        and status == NotificationStatus.PERMANENT_FAILURE
    ):
        status = NotificationStatus.TEMPORARY_FAILURE
    return status


def _update_notification_status(
    notification, status, provider_response=None, carrier=None
):
    status = _decide_permanent_temporary_failure(
        current_status=notification.status, status=status
    )
    notification.status = status
    notification.sent_at = utc_now()
    if provider_response:
        notification.provider_response = provider_response
    if carrier:
        notification.carrier = carrier
    dao_update_notification(notification)
    return notification


def update_notification_message_id(notification_id, message_id):
    stmt = (
        update(Notification)
        .where(Notification.id == notification_id)
        .values(message_id=message_id)
    )
    db.session.execute(stmt)
    db.session.commit()


@autocommit
def update_notification_status_by_id(
    notification_id, status, sent_by=None, provider_response=None, carrier=None
):
    stmt = (
        select(Notification).with_for_update().where(Notification.id == notification_id)
    )
    notification = db.session.execute(stmt).scalars().first()

    if not notification:
        current_app.logger.info(
            "notification not found for id {} (update to status {})".format(
                notification_id, status
            )
        )
        return None

    if notification.status not in {
        NotificationStatus.CREATED,
        NotificationStatus.SENDING,
        NotificationStatus.PENDING,
        NotificationStatus.SENT,
        NotificationStatus.PENDING_VIRUS_CHECK,
    }:
        _duplicate_update_warning(notification, status)
        return None

    if (
        notification.notification_type == NotificationType.SMS
        and notification.international
        and not country_records_delivery(notification.phone_prefix)
    ):
        return None
    if provider_response:
        notification.provider_response = provider_response
    if carrier:
        notification.carrier = carrier
    if not notification.sent_by and sent_by:
        notification.sent_by = sent_by
    return _update_notification_status(
        notification=notification,
        status=status,
        provider_response=notification.provider_response,
        carrier=notification.carrier,
    )


@autocommit
def update_notification_status_by_reference(reference, status):
    # this is used to update emails
    stmt = select(Notification).where(Notification.reference == reference)
    notification = db.session.execute(stmt).scalars().first()

    if not notification:
        current_app.logger.error(
            "notification not found for reference {} (update to {})".format(
                reference, status
            ),
        )
        return None

    if notification.status not in {
        NotificationStatus.SENDING,
        NotificationStatus.PENDING,
    }:
        _duplicate_update_warning(notification, status)
        return None

    return _update_notification_status(notification=notification, status=status)


@autocommit
def dao_update_notification(notification):
    notification.updated_at = utc_now()
    # notify-api-742 remove phone numbers from db
    notification.to = "1"
    notification.normalised_to = "1"
    db.session.add(notification)


def get_notifications_for_job(
    service_id, job_id, filter_dict=None, page=1, page_size=None
):
    if page_size is None:
        page_size = current_app.config["PAGE_SIZE"]

    stmt = select(Notification).where(
        Notification.service_id == service_id, Notification.job_id == job_id
    )
    stmt = _filter_query(stmt, filter_dict)
    stmt = stmt.order_by(asc(Notification.job_row_number))

    results = db.session.execute(stmt).scalars().all()

    page_size = current_app.config["PAGE_SIZE"]
    offset = (page - 1) * page_size
    paginated_results = results[offset : offset + page_size]
    pagination = Pagination(paginated_results, page, page_size, len(results))
    return pagination


def get_recent_notifications_for_job(
    service_id, job_id, filter_dict=None, page=1, page_size=None
):
    if page_size is None:
        page_size = current_app.config["PAGE_SIZE"]

    stmt = select(Notification).where(
        Notification.service_id == service_id,
        Notification.job_id == job_id,
    )

    stmt = _filter_query(stmt, filter_dict)
    stmt = stmt.order_by(desc(Notification.job_row_number))
    results = db.session.execute(stmt).scalars().all()

    page_size = current_app.config["PAGE_SIZE"]
    offset = (page - 1) * page_size
    paginated_results = results[offset : offset + page_size]

    pagination = Pagination(paginated_results, page, page_size, len(results))
    return pagination


def dao_get_notification_count_for_job_id(*, job_id):
    stmt = select(func.count(Notification.id)).where(Notification.job_id == job_id)
    return db.session.execute(stmt).scalar()


def dao_get_notification_count_for_service(*, service_id):
    stmt = select(func.count(Notification.id)).where(
        Notification.service_id == service_id
    )
    return db.session.execute(stmt).scalar()


def dao_get_notification_count_for_service_message_ratio(service_id, current_year):
    start_date = datetime(current_year, 6, 16)
    end_date = datetime(current_year + 1, 6, 16)
    stmt1 = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.service_id == service_id,
            Notification.status
            not in [
                NotificationStatus.CANCELLED,
                NotificationStatus.CREATED,
                NotificationStatus.SENDING,
            ],
            Notification.created_at >= start_date,
            Notification.created_at < end_date,
        )
    )
    stmt2 = (
        select(func.count())
        .select_from(NotificationHistory)
        .where(
            NotificationHistory.service_id == service_id,
            NotificationHistory.status
            not in [
                NotificationStatus.CANCELLED,
                NotificationStatus.CREATED,
                NotificationStatus.SENDING,
            ],
            NotificationHistory.created_at >= start_date,
            NotificationHistory.created_at < end_date,
        )
    )
    recent_count = db.session.execute(stmt1).scalar_one()
    old_count = db.session.execute(stmt2).scalar_one()
    return recent_count + old_count


def dao_get_notification_counts_per_service(service_ids, current_year):
    """
    Get notification counts for multiple services in a single organization.
    """
    if not service_ids:
        return {}

    start_date = datetime(current_year, 6, 16)
    end_date = datetime(current_year + 1, 6, 16)

    stmt1 = (
        select(Notification.service_id, func.count().label("count"))
        .where(
            Notification.service_id.in_(service_ids),
            Notification.status
            not in [
                NotificationStatus.CANCELLED,
                NotificationStatus.CREATED,
                NotificationStatus.SENDING,
            ],
            Notification.created_at >= start_date,
            Notification.created_at < end_date,
        )
        .group_by(Notification.service_id)
    )

    stmt2 = (
        select(NotificationHistory.service_id, func.count().label("count"))
        .where(
            NotificationHistory.service_id.in_(service_ids),
            NotificationHistory.status
            not in [
                NotificationStatus.CANCELLED,
                NotificationStatus.CREATED,
                NotificationStatus.SENDING,
            ],
            NotificationHistory.created_at >= start_date,
            NotificationHistory.created_at < end_date,
        )
        .group_by(NotificationHistory.service_id)
    )

    result_dict = {}

    recent_results = db.session.execute(stmt1).all()
    for service_id, count in recent_results:
        result_dict[service_id] = count

    history_results = db.session.execute(stmt2).all()
    for service_id, count in history_results:
        result_dict[service_id] = result_dict.get(service_id, 0) + count

    return result_dict


def dao_get_recent_sms_template_per_service(service_ids):

    if not service_ids:
        return {}

    stmt = (
        select(
            Notification.service_id,
            Template.name.label("template_name"),
        )
        .join(Template, Template.id == Notification.template_id)
        .where(
            Notification.service_id.in_(service_ids),
            Notification.notification_type == NotificationType.SMS,
            Notification.key_type != KeyType.TEST,
        )
        .distinct(Notification.service_id)
        .order_by(Notification.service_id, desc(Notification.created_at))
    )

    results = db.session.execute(stmt).all()

    return {service_id: template_name for service_id, template_name in results}


def dao_get_failed_notification_count():
    stmt = select(func.count(Notification.id)).where(
        Notification.status == NotificationStatus.FAILED
    )
    return db.session.execute(stmt).scalar()


def get_notification_with_personalisation(service_id, notification_id, key_type):

    stmt = (
        select(Notification)
        .where(
            Notification.service_id == service_id, Notification.id == notification_id
        )
        .options(joinedload(Notification.template))
    )
    if key_type:
        stmt = (
            select(Notification)
            .where(
                Notification.service_id == service_id,
                Notification.id == notification_id,
                Notification.key_type == key_type,
            )
            .options(joinedload(Notification.template))
        )
    return db.session.execute(stmt).scalars().one()


def get_notification_by_id(notification_id, service_id=None, _raise=False):
    filters = [Notification.id == notification_id]

    if service_id:
        filters.append(Notification.service_id == service_id)

    stmt = select(Notification).where(*filters)

    return (
        db.session.execute(stmt).scalars().one()
        if _raise
        else db.session.execute(stmt).scalars().first()
    )


def get_notifications_for_service(
    service_id,
    filter_dict=None,
    page=1,
    page_size=None,
    count_pages=True,
    limit_days=None,
    key_type=None,
    personalisation=False,
    include_jobs=False,
    include_from_test_key=False,
    older_than=None,
    client_reference=None,
    include_one_off=True,
    error_out=True,
):
    if page_size is None:
        page_size = current_app.config["PAGE_SIZE"]

    filters = [Notification.service_id == service_id]

    if limit_days is not None:
        filters.append(Notification.created_at >= midnight_n_days_ago(limit_days))

    if older_than is not None:
        older_than_created_at = (
            db.session.query(Notification.created_at)
            .where(Notification.id == older_than)
            .as_scalar()
        )
        filters.append(Notification.created_at < older_than_created_at)

    if not include_jobs:
        filters.append(Notification.job_id == None)  # noqa

    if not include_one_off:
        filters.append(Notification.created_by_id == None)  # noqa

    if key_type is not None:
        filters.append(Notification.key_type == key_type)
    elif not include_from_test_key:
        filters.append(Notification.key_type != KeyType.TEST)

    if client_reference is not None:
        filters.append(Notification.client_reference == client_reference)

    stmt = select(Notification).where(*filters)
    stmt = _filter_query(stmt, filter_dict)
    if personalisation:
        stmt = stmt.options(joinedload(Notification.template))

    stmt = stmt.order_by(desc(Notification.created_at))
    results = db.session.execute(stmt).scalars().all()
    offset = (page - 1) * page_size
    paginated_results = results[offset : offset + page_size]
    pagination = Pagination(paginated_results, page, page_size, len(results))
    return pagination


def _filter_query(stmt, filter_dict=None):
    if filter_dict is None:
        return stmt

    multidict = MultiDict(filter_dict)

    # filter by status
    statuses = multidict.getlist("status")

    if statuses:
        stmt = stmt.where(Notification.status.in_(statuses))

    # filter by template
    template_types = multidict.getlist("template_type")
    if template_types:
        stmt = stmt.where(Notification.notification_type.in_(template_types))

    return stmt


def sanitize_successful_notification_by_id(notification_id, carrier, provider_response):
    update_query = """
    update notifications set provider_response=:response, carrier=:carrier,
    notification_status='delivered', sent_at=:sent_at, "to"='1', normalised_to='1'
    where id=:notification_id
    """

    input_params = {
        "notification_id": notification_id,
        "carrier": carrier,
        "response": provider_response,
        "sent_at": utc_now(),
    }

    db.session.execute(text(update_query), input_params)
    db.session.commit()


@autocommit
def insert_notification_history_delete_notifications(
    notification_type, service_id, timestamp_to_delete_backwards_from, qry_limit=50000
):
    """
    Delete up to 50,000 notifications that are past retention for a notification type and service.


    Steps are as follows:

    Create a temporary notifications table
    Populate that table with up to 50k notifications that are to be deleted. (Note: no specified order)
    Insert everything in the temp table into notification history
    Delete from notifications if notification id is in the temp table
    Drop the temp table (automatically when the transaction commits)

    Temporary tables are in a separate postgres schema, and only visible to the current session (db connection,
    in a celery task there's one connection per thread.)
    """
    # Setting default query limit to 50,000 which take about 48 seconds on current table size
    # 10, 000 took 11s and 100,000 took 1 min 30 seconds.
    select_into_temp_table = """
         CREATE TEMP TABLE NOTIFICATION_ARCHIVE ON COMMIT DROP AS
         SELECT id, job_id, job_row_number, service_id, template_id, template_version, api_key_id,
             key_type, notification_type, created_at, sent_at, sent_by, updated_at, reference, billable_units,
             client_reference, international, phone_prefix, rate_multiplier, notification_status,
              created_by_id, document_download_count, message_cost
          FROM notifications
        WHERE service_id = :service_id
          AND notification_type = :notification_type
          AND created_at < :timestamp_to_delete_backwards_from
          AND key_type in ('normal', 'team')
        limit :qry_limit
        """
    # Insert into NotificationHistory if the row already exists do nothing.
    insert_query = """
        insert into notification_history
         SELECT * from NOTIFICATION_ARCHIVE
          ON CONFLICT ON CONSTRAINT notification_history_pkey
          DO NOTHING
    """
    delete_query = """
        DELETE FROM notifications
        where id in (select id from NOTIFICATION_ARCHIVE)
    """
    input_params = {
        "service_id": service_id,
        "notification_type": notification_type,
        "timestamp_to_delete_backwards_from": timestamp_to_delete_backwards_from,
        "qry_limit": qry_limit,
    }

    db.session.execute(text(select_into_temp_table), input_params)

    result = db.session.execute(
        text("select count(*) from NOTIFICATION_ARCHIVE")
    ).fetchone()[0]

    db.session.execute(text(insert_query))

    db.session.execute(text(delete_query))

    return result


def move_notifications_to_notification_history(
    notification_type, service_id, timestamp_to_delete_backwards_from, qry_limit=50000
):
    deleted = 0
    delete_count_per_call = 1
    while delete_count_per_call > 0:
        delete_count_per_call = insert_notification_history_delete_notifications(
            notification_type=notification_type,
            service_id=service_id,
            timestamp_to_delete_backwards_from=timestamp_to_delete_backwards_from,
            qry_limit=qry_limit,
        )
        deleted += delete_count_per_call

    # Deleting test Notifications, test notifications are not persisted to NotificationHistory
    stmt = delete(Notification).where(
        Notification.notification_type == notification_type,
        Notification.service_id == service_id,
        Notification.created_at < timestamp_to_delete_backwards_from,
        Notification.key_type == KeyType.TEST,
    )
    db.session.execute(stmt)
    db.session.commit()

    return deleted


@autocommit
def dao_delete_notifications_by_id(notification_id):
    db.session.query(Notification).where(Notification.id == notification_id).delete(
        synchronize_session="fetch"
    )


def dao_timeout_notifications(cutoff_time, limit=100000):
    """
    Set email and SMS notifications (only) to "temporary-failure" status
    if they're still sending from before the specified cutoff_time.
    """
    updated_at = utc_now()
    current_statuses = [NotificationStatus.SENDING, NotificationStatus.PENDING]
    new_status = NotificationStatus.TEMPORARY_FAILURE

    stmt = (
        select(Notification)
        .where(
            Notification.created_at < cutoff_time,
            Notification.status.in_(current_statuses),
            Notification.notification_type.in_(
                [NotificationType.SMS, NotificationType.EMAIL]
            ),
        )
        .limit(limit)
    )
    notifications = db.session.execute(stmt).scalars().all()

    stmt = (
        update(Notification)
        .where(Notification.id.in_([n.id for n in notifications]))
        .values({"status": new_status, "updated_at": updated_at})
    )
    db.session.execute(stmt)

    db.session.commit()
    return notifications


@autocommit
def dao_update_notifications_by_reference(references, update_dict):
    stmt = (
        update(Notification)
        .where(Notification.reference.in_(references))
        .values(update_dict)
    )
    result = db.session.execute(stmt)
    updated_count = result.rowcount

    updated_history_count = 0
    if updated_count != len(references):
        stmt = (
            update(NotificationHistory)
            .where(NotificationHistory.reference.in_(references))
            .values(update_dict)
        )
        result = db.session.execute(stmt)
        updated_history_count = result.rowcount

    return updated_count, updated_history_count


def dao_get_notifications_by_recipient_or_reference(
    service_id,
    search_term,
    notification_type=None,
    statuses=None,
    page=1,
    page_size=None,
    error_out=True,
):
    if notification_type == NotificationType.SMS:
        normalised = try_validate_and_format_phone_number(search_term)

        for character in {"(", ")", " ", "-"}:
            normalised = normalised.replace(character, "")

        normalised = normalised.lstrip("+0")

    elif notification_type == NotificationType.EMAIL:
        try:
            normalised = validate_and_format_email_address(search_term)
        except InvalidEmailError:
            normalised = search_term.lower()

    elif notification_type is None:
        # This happens when a notification type isn’t provided (this will
        # happen if a user doesn’t have permission to see the dashboard)
        # because email addresses and phone numbers will never be stored
        # with spaces either.
        normalised = "".join(search_term.split()).lower()

    else:
        raise TypeError(
            f"Notification type must be {NotificationType.EMAIL}, {NotificationType.SMS}, or None"
        )

    normalised = escape_special_characters(normalised)
    search_term = escape_special_characters(search_term)

    filters = [
        Notification.service_id == service_id,
        or_(
            Notification.normalised_to.like("%{}%".format(normalised)),
            Notification.client_reference.ilike("%{}%".format(search_term)),
        ),
        Notification.key_type != KeyType.TEST,
    ]

    if statuses:
        filters.append(Notification.status.in_(statuses))
    if notification_type:
        filters.append(Notification.notification_type == notification_type)

    results = (
        db.session.query(Notification)
        .where(*filters)
        .order_by(desc(Notification.created_at))
        .paginate(page=page, per_page=page_size, count=False, error_out=error_out)
    )
    return results


def dao_get_notification_by_reference(reference):
    stmt = select(Notification).where(Notification.reference == reference)
    return db.session.execute(stmt).scalars().one()


def dao_get_notification_history_by_reference(reference):
    try:
        # This try except is necessary because in test keys and research mode does not create notification history.
        # Otherwise we could just search for the NotificationHistory object
        stmt = select(Notification).where(Notification.reference == reference)
        return db.session.execute(stmt).scalars().one()
    except NoResultFound:
        stmt = select(NotificationHistory).where(
            NotificationHistory.reference == reference
        )
        return db.session.execute(stmt).scalars().one()


def dao_get_notifications_processing_time_stats(start_date, end_date):
    """
    For a given time range, returns the number of notifications sent and the number of
    those notifications that we processed within 10 seconds

    SELECT
    count(notifications),
    coalesce(sum(CASE WHEN sent_at - created_at <= interval '10 seconds' THEN 1 ELSE 0 END), 0)
    FROM notifications
    WHERE
    created_at > 'START DATE' AND
    created_at < 'END DATE' AND
    api_key_id IS NOT NULL AND
    key_type != 'test';
    """
    under_10_secs = Notification.sent_at - Notification.created_at <= timedelta(
        seconds=10
    )
    sum_column = functions.coalesce(functions.sum(case((under_10_secs, 1), else_=0)), 0)

    stmt = select(
        functions.count(Notification.id).label("messages_total"),
        sum_column.label("messages_within_10_secs"),
    ).where(
        Notification.created_at >= start_date,
        Notification.created_at < end_date,
        Notification.api_key_id.isnot(None),
        Notification.key_type != KeyType.TEST,
    )

    result = db.session.execute(stmt)
    return result.one()


def dao_get_last_notification_added_for_job_id(job_id):
    stmt = (
        select(Notification)
        .where(Notification.job_id == job_id)
        .order_by(Notification.job_row_number.desc())
    )
    last_notification_added = db.session.execute(stmt).scalars().first()

    return last_notification_added


def notifications_not_yet_sent(should_be_sending_after_seconds, notification_type):
    older_than_date = utc_now() - timedelta(seconds=should_be_sending_after_seconds)

    stmt = select(Notification).where(
        Notification.created_at <= older_than_date,
        Notification.notification_type == notification_type,
        Notification.status == NotificationStatus.CREATED,
    )
    notifications = db.session.execute(stmt).scalars().all()
    return notifications


def _duplicate_update_warning(notification, status):
    current_app.logger.info(
        (
            "Duplicate callback received for service {service_id}. "
            "Notification ID {id} with type {type} sent by {sent_by}. "
            "New status was {new_status}, current status is {old_status}. "
            "This happened {time_diff} after being first set."
        ).format(
            id=notification.id,
            old_status=notification.status,
            new_status=status,
            time_diff=utc_now() - (notification.updated_at or notification.created_at),
            type=notification.notification_type,
            sent_by=notification.sent_by,
            service_id=notification.service_id,
        )
    )


def get_service_ids_with_notifications_before(notification_type, timestamp):
    return {
        row.service_id
        for row in db.session.query(Notification.service_id)
        .where(
            Notification.notification_type == notification_type,
            Notification.created_at < timestamp,
        )
        .distinct()
    }


def get_service_ids_with_notifications_on_date(notification_type, date):
    start_date = get_midnight_in_utc(date)
    end_date = get_midnight_in_utc(date + timedelta(days=1))

    notification_table_query = db.session.query(
        Notification.service_id.label("service_id")
    ).where(
        Notification.notification_type == notification_type,
        # using >= + < is much more efficient than date(created_at)
        Notification.created_at >= start_date,
        Notification.created_at < end_date,
    )

    # Looking at this table is more efficient for historical notifications,
    # provided the task to populate it has run before they were archived.
    ft_status_table_query = db.session.query(
        FactNotificationStatus.service_id.label("service_id")
    ).where(
        FactNotificationStatus.notification_type == notification_type,
        FactNotificationStatus.local_date == date,
    )

    return {
        row.service_id
        for row in db.session.query(
            union(notification_table_query, ft_status_table_query).subquery()
        ).distinct()
    }


def dao_update_delivery_receipts(receipts, delivered):
    start_time_millis = time() * 1000
    new_receipts = []
    for r in receipts:
        if isinstance(r, str):
            r = json.loads(r)
        new_receipts.append(r)

    receipts = new_receipts
    id_to_carrier = {
        r["notification.messageId"]: r["delivery.phoneCarrier"] for r in receipts
    }
    id_to_provider_response = {
        r["notification.messageId"]: r["delivery.providerResponse"] for r in receipts
    }
    id_to_timestamp = {r["notification.messageId"]: r["@timestamp"] for r in receipts}

    id_to_message_cost = {
        r["notification.messageId"]: r["delivery.priceInUSD"] for r in receipts
    }
    status_to_update_with = NotificationStatus.DELIVERED
    if not delivered:
        status_to_update_with = NotificationStatus.FAILED

    stmt = (
        update(Notification)
        .where(Notification.message_id.in_(id_to_carrier.keys()))
        .values(
            carrier=case(
                *[
                    (Notification.message_id == key, value)
                    for key, value in id_to_carrier.items()
                ]
            ),
            status=status_to_update_with,
            sent_at=case(
                *[
                    (Notification.message_id == key, cast(value, TIMESTAMP))
                    for key, value in id_to_timestamp.items()
                ]
            ),
            provider_response=case(
                *[
                    (Notification.message_id == key, value)
                    for key, value in id_to_provider_response.items()
                ]
            ),
            message_cost=case(
                *[
                    (Notification.message_id == key, value)
                    for key, value in id_to_message_cost.items()
                ]
            ),
        )
    )
    db.session.execute(stmt)
    db.session.commit()
    elapsed_time = (time() * 1000) - start_time_millis
    current_app.logger.info(
        f"#loadtestperformance batch update query time: \
        updated {len(receipts)} notification in {elapsed_time} ms"
    )


def dao_close_out_delivery_receipts():
    THREE_DAYS_AGO = utc_now() - timedelta(minutes=3)
    stmt = (
        update(Notification)
        .where(
            Notification.status == NotificationStatus.PENDING,
            Notification.sent_at < THREE_DAYS_AGO,
        )
        .values(status=NotificationStatus.FAILED, provider_response="Technical Failure")
    )
    result = db.session.execute(stmt)

    db.session.commit()
    if result:
        current_app.logger.info(
            f"Marked {result.rowcount} notifications as technical failures"
        )


def dao_batch_insert_notifications(batch):
    db.session.bulk_save_objects(batch)
    db.session.commit()
    current_app.logger.info(f"Batch inserted notifications: {len(batch)}")
    return len(batch)
