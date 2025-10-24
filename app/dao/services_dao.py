import uuid
from datetime import timedelta

from flask import current_app
from sqlalchemy import Float, cast, delete, select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import and_, asc, case, func

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.dao.date_util import (
    generate_date_range,
    generate_hourly_range,
    get_current_calendar_year,
)
from app.dao.organization_dao import dao_get_organization_by_email_address
from app.dao.service_sms_sender_dao import insert_service_sms_sender
from app.dao.service_user_dao import dao_get_service_user
from app.dao.template_folder_dao import dao_get_valid_template_folders_by_id
from app.enums import (
    KeyType,
    NotificationStatus,
    NotificationType,
    ServicePermissionType,
    UserState,
)
from app.models import (
    AnnualBilling,
    ApiKey,
    FactBilling,
    InboundNumber,
    InvitedUser,
    Job,
    Notification,
    NotificationAllTimeView,
    NotificationHistory,
    Organization,
    Permission,
    Service,
    ServiceEmailReplyTo,
    ServicePermission,
    ServiceSmsSender,
    Template,
    TemplateHistory,
    TemplateRedacted,
    User,
    VerifyCode,
)
from app.service import statistics
from app.utils import (
    escape_special_characters,
    get_archived_db_column_value,
    get_midnight_in_utc,
    utc_now,
)


def dao_fetch_all_services(only_active=False):

    stmt = select(Service)

    if only_active:
        stmt = stmt.where(Service.active)

    stmt = stmt.order_by(asc(Service.created_at)).options(joinedload(Service.users))

    result = db.session.execute(stmt)
    return result.unique().scalars().all()


def get_services_by_partial_name(service_name):
    service_name = escape_special_characters(service_name)
    stmt = select(Service).where(Service.name.ilike("%{}%".format(service_name)))
    result = db.session.execute(stmt)
    return result.scalars().all()


def dao_count_live_services():
    stmt = (
        select(func.count())
        .select_from(Service)
        .where(
            Service.active, Service.count_as_live, Service.restricted == False  # noqa
        )
    )
    result = db.session.execute(stmt)
    return result.scalar()  # Retrieves the count


def dao_fetch_live_services_data():
    year_start_date, year_end_date = get_current_calendar_year()

    most_recent_annual_billing = (
        select(
            AnnualBilling.service_id,
            func.max(AnnualBilling.financial_year_start).label("year"),
        )
        .group_by(AnnualBilling.service_id)
        .subquery()
    )

    this_year_ft_billing = (
        select(FactBilling)
        .where(
            FactBilling.local_date >= year_start_date,
            FactBilling.local_date <= year_end_date,
        )
        .subquery()
    )

    stmt = (
        select(
            Service.id.label("service_id"),
            Service.name.label("service_name"),
            Organization.name.label("organization_name"),
            Organization.organization_type.label("organization_type"),
            Service.consent_to_research.label("consent_to_research"),
            User.name.label("contact_name"),
            User.email_address.label("contact_email"),
            User.mobile_number.label("contact_mobile"),
            Service.go_live_at.label("live_date"),
            Service.volume_sms.label("sms_volume_intent"),
            Service.volume_email.label("email_volume_intent"),
            case(
                (
                    this_year_ft_billing.c.notification_type == NotificationType.EMAIL,
                    func.sum(this_year_ft_billing.c.notifications_sent),
                ),
                else_=0,
            ).label("email_totals"),
            case(
                (
                    this_year_ft_billing.c.notification_type == NotificationType.SMS,
                    func.sum(this_year_ft_billing.c.notifications_sent),
                ),
                else_=0,
            ).label("sms_totals"),
            AnnualBilling.free_sms_fragment_limit,
        )
        .join(Service.annual_billing)
        .join(
            most_recent_annual_billing,
            and_(
                Service.id == most_recent_annual_billing.c.service_id,
                AnnualBilling.financial_year_start == most_recent_annual_billing.c.year,
            ),
        )
        .outerjoin(Service.organization)
        .outerjoin(
            this_year_ft_billing, Service.id == this_year_ft_billing.c.service_id
        )
        .outerjoin(User, Service.go_live_user_id == User.id)
        .where(
            Service.count_as_live.is_(True),
            Service.active.is_(True),
            Service.restricted.is_(False),
        )
        .group_by(
            Service.id,
            Organization.name,
            Organization.organization_type,
            Service.name,
            Service.consent_to_research,
            Service.count_as_live,
            Service.go_live_user_id,
            User.name,
            User.email_address,
            User.mobile_number,
            Service.go_live_at,
            Service.volume_sms,
            Service.volume_email,
            this_year_ft_billing.c.notification_type,
            AnnualBilling.free_sms_fragment_limit,
        )
        .order_by(asc(Service.go_live_at))
    )

    data = db.session.execute(stmt).all()
    results = []
    for row in data:
        existing_service = next(
            (x for x in results if x["service_id"] == row.service_id), None
        )

        if existing_service is not None:
            existing_service["email_totals"] += row.email_totals
            existing_service["sms_totals"] += row.sms_totals
        else:
            results.append(row._asdict())
    return results


def dao_fetch_service_by_id(service_id, only_active=False):
    stmt = (
        select(Service)
        .where(Service.id == service_id)
        .options(joinedload(Service.users))
    )

    if only_active:
        stmt = stmt.where(Service.active)

    result = db.session.execute(stmt)
    return result.unique().scalars().unique().one()


def dao_fetch_service_by_inbound_number(number):
    stmt = select(InboundNumber).where(
        InboundNumber.number == number, InboundNumber.active
    )
    result = db.session.execute(stmt)
    inbound_number = result.scalars().first()

    if not inbound_number:
        return None

    stmt = select(Service).where(Service.id == inbound_number.service_id)
    result = db.session.execute(stmt)
    return result.scalars().first()


def dao_fetch_service_by_id_with_api_keys(service_id, only_active=False):
    stmt = (
        select(Service)
        .where(Service.id == service_id)
        .options(joinedload(Service.api_keys))
    )
    if only_active:
        stmt = stmt.where(Service.active)
    return db.session.execute(stmt).scalars().unique().one()


def dao_fetch_all_services_by_user(user_id, only_active=False):

    stmt = (
        select(Service)
        .where(Service.users.any(id=user_id))
        .order_by(asc(Service.created_at))
        .options(joinedload(Service.users))
    )
    if only_active:
        stmt = stmt.where(Service.active)
    return db.session.execute(stmt).scalars().unique().all()


def dao_fetch_all_services_created_by_user(user_id):

    stmt = (
        select(Service)
        .where(Service.created_by_id == user_id)
        .order_by(asc(Service.created_at))
    )

    return db.session.execute(stmt).scalars().all()


def dao_get_service_primary_contacts(service_ids):

    if not service_ids:
        return {}

    stmt = select(
        Service.id.label("service_id"),
        Service.billing_contact_email_addresses.label("email_address"),
    ).where(Service.id.in_(service_ids))

    results = db.session.execute(stmt).all()

    return {service_id: email_address for service_id, email_address in results}


@autocommit
@version_class(
    VersionOptions(ApiKey, must_write_history=False),
    VersionOptions(Service),
    VersionOptions(Template, history_class=TemplateHistory, must_write_history=False),
)
def dao_archive_service(service_id):
    stmt = (
        select(Service)
        .options(
            joinedload(Service.templates).subqueryload(Template.template_redacted),
            joinedload(Service.api_keys),
        )
        .where(Service.id == service_id)
    )
    service = db.session.execute(stmt).scalars().unique().one()

    service.active = False
    service.name = get_archived_db_column_value(service.name)
    service.email_from = get_archived_db_column_value(service.email_from)

    for template in service.templates:
        if not template.archived:
            template.archived = True

    for api_key in service.api_keys:
        if not api_key.expiry_date:
            api_key.expiry_date = utc_now()


def dao_fetch_service_by_id_and_user(service_id, user_id):

    stmt = (
        select(Service)
        .where(Service.users.any(id=user_id), Service.id == service_id)
        .options(joinedload(Service.users))
    )
    result = db.session.execute(stmt).scalar_one()
    return result


@autocommit
@version_class(Service)
def dao_create_service(
    service,
    user,
    service_id=None,
    service_permissions=None,
):
    if not user:
        raise ValueError("Can't create a service without a user")

    if service_permissions is None:
        service_permissions = ServicePermissionType.defaults()

    organization = dao_get_organization_by_email_address(user.email_address)

    from app.dao.permissions_dao import permission_dao

    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.id = (
        service_id or uuid.uuid4()
    )  # must be set now so version history model can use same id
    service.active = True

    for permission in service_permissions:
        service_permission = ServicePermission(
            service_id=service.id, permission=permission
        )
        service.permissions.append(service_permission)

    # do we just add the default - or will we get a value from FE?
    insert_service_sms_sender(service, current_app.config["FROM_NUMBER"])

    if organization:
        service.organization_id = organization.id
        service.organization_type = organization.organization_type

        if organization.email_branding:
            service.email_branding = organization.email_branding

    service.count_as_live = not user.platform_admin

    db.session.add(service)


@autocommit
@version_class(Service)
def dao_update_service(service):
    db.session.add(service)


def dao_add_user_to_service(service, user, permissions=None, folder_permissions=None):
    permissions = permissions or []
    folder_permissions = folder_permissions or []

    try:
        from app.dao.permissions_dao import permission_dao

        # As per SQLAlchemy 2.0, we need to add the user to the service only if the user is not already added;
        # otherwise it throws sqlalchemy.exc.IntegrityError:
        # (psycopg2.errors.UniqueViolation) duplicate key value violates unique constraint "uix_user_to_service"
        service_user = dao_get_service_user(user.id, service.id)
        if service_user is None:
            service.users.append(user)
        permission_dao.set_user_service_permission(
            user, service, permissions, _commit=False
        )
        db.session.add(service)

        service_user = dao_get_service_user(user.id, service.id)
        valid_template_folders = dao_get_valid_template_folders_by_id(
            folder_permissions
        )
        service_user.folders = valid_template_folders
        db.session.add(service_user)

    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def dao_remove_user_from_service(service, user):
    try:
        from app.dao.permissions_dao import permission_dao

        permission_dao.remove_user_service_permissions(user, service)

        service_user = dao_get_service_user(user.id, service.id)
        db.session.delete(service_user)
    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def delete_service_and_all_associated_db_objects(service):
    def _delete_commit(stmt):
        db.session.execute(stmt)
        db.session.commit()

    subq = select(Template.id).where(Template.service == service).subquery()

    stmt = delete(TemplateRedacted).where(TemplateRedacted.template_id.in_(subq))
    _delete_commit(stmt)

    _delete_commit(delete(ServiceSmsSender).where(ServiceSmsSender.service == service))
    _delete_commit(
        delete(ServiceEmailReplyTo).where(ServiceEmailReplyTo.service == service)
    )
    _delete_commit(delete(InvitedUser).where(InvitedUser.service == service))
    _delete_commit(delete(Permission).where(Permission.service == service))
    _delete_commit(
        delete(NotificationHistory).where(NotificationHistory.service == service)
    )
    _delete_commit(delete(Notification).where(Notification.service == service))
    _delete_commit(delete(Job).where(Job.service == service))
    _delete_commit(delete(Template).where(Template.service == service))
    _delete_commit(
        delete(TemplateHistory).where(TemplateHistory.service_id == service.id)
    )
    _delete_commit(
        delete(ServicePermission).where(ServicePermission.service_id == service.id)
    )
    _delete_commit(delete(ApiKey).where(ApiKey.service == service))
    _delete_commit(
        delete(ApiKey.get_history_model()).where(
            ApiKey.get_history_model().service_id == service.id
        )
    )
    _delete_commit(delete(AnnualBilling).where(AnnualBilling.service_id == service.id))

    stmt = (
        select(VerifyCode).join(User).where(User.id.in_([x.id for x in service.users]))
    )
    verify_codes = db.session.execute(stmt).scalars().all()
    list(map(db.session.delete, verify_codes))
    db.session.commit()
    users = [x for x in service.users]
    for user in users:
        user.organizations = []
        service.users.remove(user)
    _delete_commit(delete(Service.get_history_model()).where(Service.id == service.id))
    db.session.delete(service)
    db.session.commit()
    for user in users:
        db.session.delete(user)
    db.session.commit()


def dao_fetch_todays_stats_for_service(service_id):
    today = utc_now().date()
    start_date = get_midnight_in_utc(today)
    stmt = (
        select(
            Notification.notification_type,
            Notification.status,
            func.count(Notification.id).label("count"),
        )
        .where(
            Notification.service_id == service_id,
            Notification.key_type != KeyType.TEST,
            Notification.created_at >= start_date,
        )
        .group_by(
            Notification.notification_type,
            Notification.status,
        )
    )
    return db.session.execute(stmt).all()


def dao_fetch_stats_for_service_from_days(service_id, start_date, end_date):
    start_date = get_midnight_in_utc(start_date)
    end_date = get_midnight_in_utc(end_date + timedelta(days=1))

    total_substmt = (
        select(
            func.date_trunc("day", NotificationAllTimeView.created_at).label("day"),
            Job.notification_count.label("notification_count"),
        )
        .join(Job, NotificationAllTimeView.job_id == Job.id)
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type != KeyType.TEST,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
        )
        .group_by(
            Job.id,
            Job.notification_count,
            func.date_trunc("day", NotificationAllTimeView.created_at),
        )
        .subquery()
    )

    total_stmt = select(
        total_substmt.c.day,
        func.sum(total_substmt.c.notification_count).label("total_notifications"),
    ).group_by(total_substmt.c.day)

    total_notifications = {
        row.day: row.total_notifications for row in db.session.execute(total_stmt).all()
    }

    stmt = (
        select(
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
            func.date_trunc("day", NotificationAllTimeView.created_at).label("day"),
            func.count(NotificationAllTimeView.id).label("count"),
        )
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type != KeyType.TEST,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
        )
        .group_by(
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
            func.date_trunc("day", NotificationAllTimeView.created_at),
        )
    )

    data = db.session.execute(stmt).all()

    return total_notifications, data


def dao_fetch_stats_for_service_from_hours(service_id, start_date, end_date):
    start_date = get_midnight_in_utc(start_date)
    end_date = get_midnight_in_utc(end_date + timedelta(days=1))

    # Update to group by HOUR instead of DAY
    total_substmt = (
        select(
            func.date_trunc("hour", NotificationAllTimeView.created_at).label(
                "hour"
            ),  # UPDATED
            Job.notification_count.label("notification_count"),
        )
        .join(Job, NotificationAllTimeView.job_id == Job.id)
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type != KeyType.TEST,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
        )
        .group_by(
            Job.id,
            Job.notification_count,
            func.date_trunc("hour", NotificationAllTimeView.created_at),  # UPDATED
        )
        .subquery()
    )

    # Also update this to group by hour
    total_stmt = select(
        total_substmt.c.hour,  # UPDATED
        func.sum(total_substmt.c.notification_count).label("total_notifications"),
    ).group_by(
        total_substmt.c.hour
    )  # UPDATED

    # Ensure we're using hourly timestamps in the response
    total_notifications = {
        row.hour: row.total_notifications
        for row in db.session.execute(total_stmt).all()
    }

    # Update the second query to also use "hour"
    stmt = (
        select(
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
            func.date_trunc("hour", NotificationAllTimeView.created_at).label(
                "hour"
            ),  # UPDATED
            func.count(NotificationAllTimeView.id).label("count"),
        )
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type != KeyType.TEST,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
        )
        .group_by(
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
            func.date_trunc("hour", NotificationAllTimeView.created_at),  # UPDATED
        )
    )

    data = db.session.execute(stmt).all()

    return total_notifications, data


def dao_fetch_stats_for_service_from_days_for_user(
    service_id, start_date, end_date, user_id
):
    start_date = get_midnight_in_utc(start_date)
    end_date = get_midnight_in_utc(end_date + timedelta(days=1))

    total_substmt = (
        select(
            func.date_trunc("hour", NotificationAllTimeView.created_at).label("hour"),
            Job.notification_count.label("notification_count"),
        )
        .join(Job, NotificationAllTimeView.job_id == Job.id)
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type != KeyType.TEST,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
            NotificationAllTimeView.created_by_id == user_id,
        )
        .group_by(
            Job.id,
            Job.notification_count,
            func.date_trunc("hour", NotificationAllTimeView.created_at),
        )
        .subquery()
    )

    total_stmt = select(
        total_substmt.c.hour,
        func.sum(total_substmt.c.notification_count).label("total_notifications"),
    ).group_by(total_substmt.c.hour)

    total_notifications = {
        row.hour: row.total_notifications
        for row in db.session.execute(total_stmt).all()
    }

    stmt = (
        select(
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
            func.date_trunc("hour", NotificationAllTimeView.created_at).label("hour"),
            func.count(NotificationAllTimeView.id).label("count"),
        )
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.key_type != KeyType.TEST,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
            NotificationAllTimeView.created_by_id == user_id,
        )
        .group_by(
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
            func.date_trunc("hour", NotificationAllTimeView.created_at),
        )
    )

    data = db.session.execute(stmt).all()

    return total_notifications, data


def dao_fetch_todays_stats_for_all_services(
    include_from_test_key=True, only_active=True
):
    today = utc_now().date()
    start_date = get_midnight_in_utc(today)
    end_date = get_midnight_in_utc(today + timedelta(days=1))

    substmt = (
        select(
            Notification.notification_type,
            Notification.status,
            Notification.service_id,
            func.count(Notification.id).label("count"),
        )
        .where(
            Notification.created_at >= start_date, Notification.created_at < end_date
        )
        .group_by(
            Notification.notification_type, Notification.status, Notification.service_id
        )
    )

    if not include_from_test_key:
        substmt = substmt.where(Notification.key_type != KeyType.TEST)

    substmt = substmt.subquery()

    stmt = (
        select(
            Service.id.label("service_id"),
            Service.name,
            Service.restricted,
            Service.active,
            Service.created_at,
            substmt.c.notification_type,
            substmt.c.status,
            substmt.c.count,
        )
        .outerjoin(substmt, substmt.c.service_id == Service.id)
        .order_by(Service.id)
    )

    if only_active:
        stmt = stmt.where(Service.active)

    return db.session.execute(stmt).all()


@autocommit
@version_class(
    VersionOptions(ApiKey, must_write_history=False),
    VersionOptions(Service),
)
def dao_suspend_service(service_id):

    stmt = (
        select(Service)
        .options(joinedload(Service.api_keys))
        .where(Service.id == service_id)
    )
    service = db.session.execute(stmt).scalars().unique().one()

    for api_key in service.api_keys:
        if not api_key.expiry_date:
            api_key.expiry_date = utc_now()

    service.active = False


@autocommit
@version_class(Service)
def dao_resume_service(service_id):
    service = db.session.get(Service, service_id)

    service.active = True


def dao_fetch_active_users_for_service(service_id):

    stmt = select(User).where(
        User.services.any(id=service_id), User.state == UserState.ACTIVE
    )
    result = db.session.execute(stmt)
    return result.scalars().all()


def dao_find_services_sending_to_tv_numbers(start_date, end_date, threshold=500):

    stmt = (
        select(
            Notification.service_id.label("service_id"),
            func.count(Notification.id).label("notification_count"),
        )
        .where(
            Notification.service_id == Service.id,
            Notification.created_at >= start_date,
            Notification.created_at <= end_date,
            Notification.key_type != KeyType.TEST,
            Notification.notification_type == NotificationType.SMS,
            func.substr(Notification.normalised_to, 3, 7) == "7700900",
            Service.restricted == False,  # noqa
            Service.active == True,  # noqa
        )
        .group_by(
            Notification.service_id,
        )
        .having(func.count(Notification.id) > threshold)
    )
    return db.session.execute(stmt).all()


def dao_find_services_with_high_failure_rates(start_date, end_date, threshold=10000):
    substmt = (
        select(
            func.count(Notification.id).label("total_count"),
            Notification.service_id.label("service_id"),
        )
        .where(
            Notification.service_id == Service.id,
            Notification.created_at >= start_date,
            Notification.created_at <= end_date,
            Notification.key_type != KeyType.TEST,
            Notification.notification_type == NotificationType.SMS,
            Service.restricted == False,  # noqa
            Service.active == True,  # noqa
        )
        .group_by(
            Notification.service_id,
        )
        .having(func.count(Notification.id) >= threshold)
    )

    substmt = substmt.subquery()

    stmt = (
        select(
            Notification.service_id.label("service_id"),
            func.count(Notification.id).label("permanent_failure_count"),
            substmt.c.total_count.label("total_count"),
            (
                cast(func.count(Notification.id), Float)
                / cast(substmt.c.total_count, Float)
            ).label("permanent_failure_rate"),
        )
        .join(substmt, substmt.c.service_id == Notification.service_id)
        .where(
            Notification.service_id == Service.id,
            Notification.created_at >= start_date,
            Notification.created_at <= end_date,
            Notification.key_type != KeyType.TEST,
            Notification.notification_type == NotificationType.SMS,
            Notification.status == NotificationStatus.PERMANENT_FAILURE,
            Service.restricted == False,  # noqa
            Service.active == True,  # noqa
        )
        .group_by(Notification.service_id, substmt.c.total_count)
        .having(
            cast(func.count(Notification.id), Float)
            / cast(substmt.c.total_count, Float)
            >= 0.25
        )
    )

    return db.session.execute(stmt).all()


def get_live_services_with_organization():

    stmt = (
        select(
            Service.id.label("service_id"),
            Service.name.label("service_name"),
            Organization.id.label("organization_id"),
            Organization.name.label("organization_name"),
        )
        .select_from(Service)
        .outerjoin(Service.organization)
        .where(
            Service.count_as_live.is_(True),
            Service.active.is_(True),
            Service.restricted.is_(False),
        )
        .order_by(Organization.name, Service.name)
    )

    return db.session.execute(stmt).all()


def fetch_notification_stats_for_service_by_month_by_user(
    start_date, end_date, service_id, user_id
):

    stmt = (
        select(
            func.date_trunc("month", NotificationAllTimeView.created_at).label("month"),
            NotificationAllTimeView.notification_type,
            (NotificationAllTimeView.status).label("notification_status"),
            func.count(NotificationAllTimeView.id).label("count"),
        )
        .where(
            NotificationAllTimeView.service_id == service_id,
            NotificationAllTimeView.created_at >= start_date,
            NotificationAllTimeView.created_at < end_date,
            NotificationAllTimeView.key_type != KeyType.TEST,
            NotificationAllTimeView.created_by_id == user_id,
        )
        .group_by(
            func.date_trunc("month", NotificationAllTimeView.created_at).label("month"),
            NotificationAllTimeView.notification_type,
            NotificationAllTimeView.status,
        )
    )
    return db.session.execute(stmt).all()


def get_specific_days_stats(
    data, start_date, days=None, end_date=None, total_notifications=None
):
    if days is not None and end_date is not None:
        raise ValueError("Only set days OR set end_date, not both.")
    elif days is not None:
        gen_range = generate_date_range(start_date, days=days)
    elif end_date is not None:
        gen_range = generate_date_range(start_date, end_date)
    else:
        raise ValueError("Either days or end_date must be set.")

    grouped_data = {date: [] for date in gen_range} | {
        day: [row for row in data if row.day == day]
        for day in {item.day for item in data}
    }

    stats = {
        day.strftime("%Y-%m-%d"): statistics.format_statistics(
            rows,
            total_notifications=(
                total_notifications.get(day, 0)
                if total_notifications is not None
                else None
            ),
        )
        for day, rows in grouped_data.items()
    }
    return stats


def get_specific_hours_stats(
    data, start_date, hours=None, end_date=None, total_notifications=None
):
    if hours is not None and end_date is not None:
        raise ValueError("Only set hours OR set end_date, not both.")
    elif hours is not None:
        gen_range = [start_date + timedelta(hours=i) for i in range(hours)]
    elif end_date is not None:
        gen_range = generate_hourly_range(start_date, end_date=end_date)
    else:
        raise ValueError("Either hours or end_date must be set.")

    # Ensure all hours exist in the output (even if empty)
    grouped_data = {hour: [] for hour in gen_range}

    # Group notifications based on full hour timestamps
    for row in data:
        notification_type, status, timestamp, count = row

        row_hour = timestamp.replace(minute=0, second=0, microsecond=0)
        if row_hour in grouped_data:
            grouped_data[row_hour].append(row)

    # Format statistics, returning only hours with results
    stats = {
        hour.strftime("%Y-%m-%dT%H:00:00Z"): statistics.format_statistics(
            rows, total_notifications.get(hour, 0) if total_notifications else None
        )
        for hour, rows in grouped_data.items()
        if rows
    }

    return stats
