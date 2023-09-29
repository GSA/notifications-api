from datetime import datetime, timedelta

from flask import current_app
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES
from notifications_utils.recipients import (
    InvalidEmailError,
    try_validate_and_format_phone_number,
    validate_and_format_email_address,
)
from sqlalchemy import asc, desc, func, or_, union
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import functions
from sqlalchemy.sql.expression import case
from werkzeug.datastructures import MultiDict

from app import create_uuid, db
from app.dao.dao_utils import autocommit
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    NOTIFICATION_PENDING,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_TEMPORARY_FAILURE,
    SMS_TYPE,
    FactNotificationStatus,
    Notification,
    NotificationHistory,
)
from app.utils import (
    escape_special_characters,
    get_midnight_in_utc,
    midnight_n_days_ago,
)


def dao_get_last_date_template_was_used(template_id, service_id):
    last_date_from_notifications = (
        db.session.query(functions.max(Notification.created_at))
        .filter(
            Notification.service_id == service_id,
            Notification.template_id == template_id,
            Notification.key_type != KEY_TYPE_TEST,
        )
        .scalar()
    )

    if last_date_from_notifications:
        return last_date_from_notifications

    last_date = (
        db.session.query(functions.max(FactNotificationStatus.local_date))
        .filter(
            FactNotificationStatus.template_id == template_id,
            FactNotificationStatus.key_type != KEY_TYPE_TEST,
        )
        .scalar()
    )

    return last_date


@autocommit
def dao_create_notification(notification):
    if not notification.id:
        # need to populate defaulted fields before we create the notification history object
        notification.id = create_uuid()
    if not notification.status:
        notification.status = NOTIFICATION_CREATED

    db.session.add(notification)


def country_records_delivery(phone_prefix):
    dlr = INTERNATIONAL_BILLING_RATES[phone_prefix]["attributes"]["dlr"]
    return dlr and dlr.lower() == "yes"


def _decide_permanent_temporary_failure(current_status, status):
    # If we go from pending to delivered we need to set failure type as temporary-failure
    if (
        current_status == NOTIFICATION_PENDING
        and status == NOTIFICATION_PERMANENT_FAILURE
    ):
        status = NOTIFICATION_TEMPORARY_FAILURE
    return status


def _update_notification_status(notification, status, provider_response=None):
    status = _decide_permanent_temporary_failure(
        current_status=notification.status, status=status
    )
    notification.status = status
    if provider_response:
        notification.provider_response = provider_response
    dao_update_notification(notification)
    return notification


@autocommit
def update_notification_status_by_id(
    notification_id, status, sent_by=None, provider_response=None
):
    notification = (
        Notification.query.with_for_update()
        .filter(Notification.id == notification_id)
        .first()
    )

    if not notification:
        current_app.logger.info(
            "notification not found for id {} (update to status {})".format(
                notification_id, status
            )
        )
        return None

    if notification.status not in {
        NOTIFICATION_CREATED,
        NOTIFICATION_SENDING,
        NOTIFICATION_PENDING,
        NOTIFICATION_SENT,
        NOTIFICATION_PENDING_VIRUS_CHECK,
    }:
        _duplicate_update_warning(notification, status)
        return None

    if (
        notification.notification_type == SMS_TYPE
        and notification.international
        and not country_records_delivery(notification.phone_prefix)
    ):
        return None
    if provider_response:
        notification.provider_response = provider_response
    if not notification.sent_by and sent_by:
        notification.sent_by = sent_by
    return _update_notification_status(
        notification=notification,
        status=status,
        provider_response=notification.provider_response,
    )


@autocommit
def update_notification_status_by_reference(reference, status):
    # this is used to update emails
    notification = Notification.query.filter(
        Notification.reference == reference
    ).first()

    if not notification:
        current_app.logger.error(
            "notification not found for reference {} (update to {})".format(
                reference, status
            )
        )
        return None

    if notification.status not in {NOTIFICATION_SENDING, NOTIFICATION_PENDING}:
        _duplicate_update_warning(notification, status)
        return None

    return _update_notification_status(notification=notification, status=status)


@autocommit
def dao_update_notification(notification):
    notification.updated_at = datetime.utcnow()
    db.session.add(notification)


def get_notifications_for_job(
    service_id, job_id, filter_dict=None, page=1, page_size=None
):
    if page_size is None:
        page_size = current_app.config["PAGE_SIZE"]
    query = Notification.query.filter_by(service_id=service_id, job_id=job_id)
    query = _filter_query(query, filter_dict)
    return query.order_by(asc(Notification.job_row_number)).paginate(
        page=page, per_page=page_size
    )


def dao_get_notification_count_for_job_id(*, job_id):
    return Notification.query.filter_by(job_id=job_id).count()


def get_notification_with_personalisation(service_id, notification_id, key_type):
    filter_dict = {"service_id": service_id, "id": notification_id}
    if key_type:
        filter_dict["key_type"] = key_type

    return (
        Notification.query.filter_by(**filter_dict)
        .options(joinedload("template"))
        .one()
    )


def get_notification_by_id(notification_id, service_id=None, _raise=False):
    filters = [Notification.id == notification_id]

    if service_id:
        filters.append(Notification.service_id == service_id)

    query = Notification.query.filter(*filters)

    return query.one() if _raise else query.first()


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
            .filter(Notification.id == older_than)
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
        filters.append(Notification.key_type != KEY_TYPE_TEST)

    if client_reference is not None:
        filters.append(Notification.client_reference == client_reference)

    query = Notification.query.filter(*filters)
    query = _filter_query(query, filter_dict)
    if personalisation:
        query = query.options(joinedload("template"))

    return query.order_by(desc(Notification.created_at)).paginate(
        page=page,
        per_page=page_size,
        count=count_pages,
        error_out=error_out,
    )


def _filter_query(query, filter_dict=None):
    if filter_dict is None:
        return query

    multidict = MultiDict(filter_dict)

    # filter by status
    statuses = multidict.getlist("status")

    if statuses:
        query = query.filter(Notification.status.in_(statuses))

    # filter by template
    template_types = multidict.getlist("template_type")
    if template_types:
        query = query.filter(Notification.notification_type.in_(template_types))

    return query


def sanitize_successful_notification_by_id(notification_id, provider_response):
    update_query = """
    update notifications set provider_response=:response, notification_status='delivered', "to"='1', normalised_to='1'
    where id=:notification_id
    """
    input_params = {"notification_id": notification_id, "response": provider_response}

    db.session.execute(update_query, input_params)
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
              created_by_id, document_download_count
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

    db.session.execute(select_into_temp_table, input_params)

    result = db.session.execute("select count(*) from NOTIFICATION_ARCHIVE").fetchone()[
        0
    ]

    db.session.execute(insert_query)

    db.session.execute(delete_query)

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
    Notification.query.filter(
        Notification.notification_type == notification_type,
        Notification.service_id == service_id,
        Notification.created_at < timestamp_to_delete_backwards_from,
        Notification.key_type == KEY_TYPE_TEST,
    ).delete(synchronize_session=False)
    db.session.commit()

    return deleted


@autocommit
def dao_delete_notifications_by_id(notification_id):
    db.session.query(Notification).filter(Notification.id == notification_id).delete(
        synchronize_session="fetch"
    )


def dao_timeout_notifications(cutoff_time, limit=100000):
    """
    Set email and SMS notifications (only) to "temporary-failure" status
    if they're still sending from before the specified cutoff_time.
    """
    updated_at = datetime.utcnow()
    current_statuses = [NOTIFICATION_SENDING, NOTIFICATION_PENDING]
    new_status = NOTIFICATION_TEMPORARY_FAILURE

    notifications = (
        Notification.query.filter(
            Notification.created_at < cutoff_time,
            Notification.status.in_(current_statuses),
            Notification.notification_type.in_([SMS_TYPE, EMAIL_TYPE]),
        )
        .limit(limit)
        .all()
    )

    Notification.query.filter(
        Notification.id.in_([n.id for n in notifications]),
    ).update(
        {"status": new_status, "updated_at": updated_at}, synchronize_session=False
    )

    db.session.commit()
    return notifications


@autocommit
def dao_update_notifications_by_reference(references, update_dict):
    updated_count = Notification.query.filter(
        Notification.reference.in_(references)
    ).update(update_dict, synchronize_session=False)

    updated_history_count = 0
    if updated_count != len(references):
        updated_history_count = NotificationHistory.query.filter(
            NotificationHistory.reference.in_(references)
        ).update(update_dict, synchronize_session=False)

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
    if notification_type == SMS_TYPE:
        normalised = try_validate_and_format_phone_number(search_term)

        for character in {"(", ")", " ", "-"}:
            normalised = normalised.replace(character, "")

        normalised = normalised.lstrip("+0")

    elif notification_type == EMAIL_TYPE:
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
        raise TypeError(f"Notification type must be {EMAIL_TYPE}, {SMS_TYPE}, or None")

    normalised = escape_special_characters(normalised)
    search_term = escape_special_characters(search_term)

    filters = [
        Notification.service_id == service_id,
        or_(
            Notification.normalised_to.like("%{}%".format(normalised)),
            Notification.client_reference.ilike("%{}%".format(search_term)),
        ),
        Notification.key_type != KEY_TYPE_TEST,
    ]

    if statuses:
        filters.append(Notification.status.in_(statuses))
    if notification_type:
        filters.append(Notification.notification_type == notification_type)

    results = (
        db.session.query(Notification)
        .filter(*filters)
        .order_by(desc(Notification.created_at))
        .paginate(page=page, per_page=page_size, count=False, error_out=error_out)
    )
    return results


def dao_get_notification_by_reference(reference):
    return Notification.query.filter(Notification.reference == reference).one()


def dao_get_notification_history_by_reference(reference):
    try:
        # This try except is necessary because in test keys and research mode does not create notification history.
        # Otherwise we could just search for the NotificationHistory object
        return Notification.query.filter(Notification.reference == reference).one()
    except NoResultFound:
        return NotificationHistory.query.filter(
            NotificationHistory.reference == reference
        ).one()


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
    sum_column = functions.coalesce(
        functions.sum(case([(under_10_secs, 1)], else_=0)), 0
    )

    return (
        db.session.query(
            func.count(Notification.id).label("messages_total"),
            sum_column.label("messages_within_10_secs"),
        )
        .filter(
            Notification.created_at >= start_date,
            Notification.created_at < end_date,
            Notification.api_key_id.isnot(None),
            Notification.key_type != KEY_TYPE_TEST,
        )
        .one()
    )


def dao_get_last_notification_added_for_job_id(job_id):
    last_notification_added = (
        Notification.query.filter(Notification.job_id == job_id)
        .order_by(Notification.job_row_number.desc())
        .first()
    )

    return last_notification_added


def notifications_not_yet_sent(should_be_sending_after_seconds, notification_type):
    older_than_date = datetime.utcnow() - timedelta(
        seconds=should_be_sending_after_seconds
    )

    notifications = Notification.query.filter(
        Notification.created_at <= older_than_date,
        Notification.notification_type == notification_type,
        Notification.status == NOTIFICATION_CREATED,
    ).all()
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
            time_diff=datetime.utcnow()
            - (notification.updated_at or notification.created_at),
            type=notification.notification_type,
            sent_by=notification.sent_by,
            service_id=notification.service_id,
        )
    )


def get_service_ids_with_notifications_before(notification_type, timestamp):
    return {
        row.service_id
        for row in db.session.query(Notification.service_id)
        .filter(
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
    ).filter(
        Notification.notification_type == notification_type,
        # using >= + < is much more efficient than date(created_at)
        Notification.created_at >= start_date,
        Notification.created_at < end_date,
    )

    # Looking at this table is more efficient for historical notifications,
    # provided the task to populate it has run before they were archived.
    ft_status_table_query = db.session.query(
        FactNotificationStatus.service_id.label("service_id")
    ).filter(
        FactNotificationStatus.notification_type == notification_type,
        FactNotificationStatus.local_date == date,
    )

    return {
        row.service_id
        for row in db.session.query(
            union(notification_table_query, ft_status_table_query).subquery()
        ).distinct()
    }
