import uuid
from datetime import timedelta
from secrets import randbelow

import sqlalchemy
from flask import current_app
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import joinedload

from app import db
from app.dao.dao_utils import autocommit
from app.dao.permissions_dao import permission_dao
from app.dao.service_user_dao import dao_get_service_users_by_user_id
from app.enums import AuthType, PermissionType, UserState
from app.errors import InvalidRequest
from app.models import Organization, Service, User, VerifyCode
from app.utils import escape_special_characters, get_archived_db_column_value, utc_now


def _remove_values_for_keys_if_present(dict, keys):
    for key in keys:
        dict.pop(key, None)


def create_secret_code(length=6):
    random_number = randbelow(10**length)
    return "{:0{length}d}".format(random_number, length=length)


def get_login_gov_user(login_uuid, email_address):
    """
    We want to check to see if the user is registered with login.gov
    If we can find the login.gov uuid in our user table, then they are.

    Also, because we originally keyed off email address we might have a few
    older users who registered with login.gov but we don't know what their
    login.gov uuids are.  Eventually the code that checks by email address
    should be removed.
    """
    stmt = select(User).where(User.login_uuid == login_uuid)
    user = db.session.execute(stmt).scalars().first()
    if user:
        if user.email_address != email_address:
            try:
                save_user_attribute(user, {"email_address": email_address})
            except sqlalchemy.exc.IntegrityError:
                # We are trying to change the email address as a courtesy,
                # based on the assumption that the user has somehow changed their
                # address in login.gov.
                # But if we cannot change the email address, at least we don't
                # want to fail here, otherwise the user will be locked out.
                current_app.logger.exception("Error getting login.gov user")
                db.session.rollback()

        return user

    # Handle the case of the brand new user.  We know their email from the
    # invitation but need to related the login_uuid to it.
    stmt = select(User).where(User.email_address.ilike(email_address))
    user = db.session.execute(stmt).scalars().first()

    if user:
        save_user_attribute(user, {"login_uuid": login_uuid})
        return user

    return None


def save_user_attribute(usr, update_dict=None):
    db.session.query(User).where(User.id == usr.id).update(update_dict or {})
    db.session.commit()


def save_model_user(
    user,
    update_dict=None,
    password=None,
    validated_email_access=False,
):
    if password:
        user.password = password
        user.password_changed_at = utc_now()
    if validated_email_access:
        user.email_access_validated_at = utc_now()
    if update_dict:
        _remove_values_for_keys_if_present(update_dict, ["id", "password_changed_at"])
        db.session.query(User).where(User.id == user.id).update(update_dict or {})
    else:
        db.session.add(user)
    db.session.commit()


def create_user_code(user, code, code_type):
    verify_code = VerifyCode(
        code_type=code_type,
        expiry_datetime=utc_now() + timedelta(minutes=30),
        user=user,
    )
    verify_code.code = code
    db.session.add(verify_code)
    db.session.commit()
    return verify_code


def get_user_code(user, code, code_type):
    # Get the most recent codes to try and reduce the
    # time searching for the correct code.
    stmt = (
        select(VerifyCode)
        .where(VerifyCode.user == user, VerifyCode.code_type == code_type)
        .order_by(VerifyCode.created_at.desc())
    )
    codes = db.session.execute(stmt).scalars().all()
    return next((x for x in codes if x.check_code(code)), None)


def delete_codes_older_created_more_than_a_day_ago():
    stmt = delete(VerifyCode).where(
        VerifyCode.created_at < utc_now() - timedelta(hours=24)
    )

    deleted = db.session.execute(stmt)
    db.session.commit()
    return deleted


def use_user_code(id):
    verify_code = db.session.get(VerifyCode, id)
    verify_code.code_used = True
    db.session.add(verify_code)
    db.session.commit()


def delete_model_user(user):
    db.session.delete(user)
    db.session.commit()


def delete_user_verify_codes(user):
    stmt = delete(VerifyCode).where(VerifyCode.user == user)
    db.session.execute(stmt)
    db.session.commit()


def count_user_verify_codes(user):
    stmt = select(func.count(VerifyCode.id)).where(
        VerifyCode.user == user,
        VerifyCode.expiry_datetime > utc_now(),
        VerifyCode.code_used.is_(False),
    )
    result = db.session.execute(stmt).scalar()
    return result or 0


def get_user_by_id(user_id=None):
    if user_id:
        stmt = select(User).where(User.id == user_id)
        return db.session.execute(stmt).scalars().one()
    return get_users()


def get_users():
    stmt = select(User)
    return db.session.execute(stmt).scalars().all()


def get_user_by_email(email):
    stmt = select(User).where(func.lower(User.email_address) == func.lower(email))
    return db.session.execute(stmt).scalars().one()


def get_users_by_partial_email(email):
    email = escape_special_characters(email)
    stmt = select(User).where(User.email_address.ilike("%{}%".format(email)))
    return db.session.execute(stmt).scalars().all()


def increment_failed_login_count(user):
    user.failed_login_count += 1
    db.session.add(user)
    db.session.commit()


def reset_failed_login_count(user):
    if user.failed_login_count > 0:
        user.failed_login_count = 0
        db.session.add(user)
        db.session.commit()


def update_user_password(user, password):
    # reset failed login count - they've just reset their password so should be fine
    user.password = password
    user.password_changed_at = utc_now()
    db.session.add(user)
    db.session.commit()


def get_user_and_accounts(user_id):
    # TODO: With sqlalchemy 2.0 change as below because of the breaking change
    # at User.organizations.services, we need to verify that the below subqueryload
    # that we have put is functionally doing the same thing as before
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            # eagerly load the user's services and organizations, and also the service's org and vice versa
            # (so we can see if the user knows about it)
            joinedload(User.services).joinedload(Service.organization),
            joinedload(User.organizations).subqueryload(Organization.services),
        )
    )
    return db.session.execute(stmt).scalars().unique().one()


@autocommit
def dao_archive_user(user):
    if not user_can_be_archived(user):
        msg = "User can’t be removed from a service - check all services have another team member with manage_settings"
        raise InvalidRequest(msg, 400)

    permission_dao.remove_user_service_permissions_for_all_services(user)

    service_users = dao_get_service_users_by_user_id(user.id)
    for service_user in service_users:
        db.session.delete(service_user)

    user.organizations = []

    user.auth_type = AuthType.EMAIL
    user.email_address = get_archived_db_column_value(user.email_address)
    user.mobile_number = None
    user.password = str(uuid.uuid4())
    # Changing the current_session_id signs the user out
    user.current_session_id = "00000000-0000-0000-0000-000000000000"
    user.state = UserState.INACTIVE

    db.session.add(user)


def user_can_be_archived(user):
    active_services = [x for x in user.services if x.active]

    for service in active_services:
        other_active_users = [
            x for x in service.users if x.state == UserState.ACTIVE and x != user
        ]

        if not other_active_users:
            return False

        if not any(
            PermissionType.MANAGE_SETTINGS in user.get_permissions(service.id)
            for user in other_active_users
        ):
            # no-one else has manage settings
            return False

    return True


def dao_report_users():
    sql = """
    select users.name, users.email_address, users.mobile_number, services.name as service_name
    from users
    inner join user_to_service on users.id=user_to_service.user_id
    inner join services on services.id=user_to_service.service_id
    where services.name not like '_archived%'
    order by users.name asc
    """
    return db.session.execute(text(sql))
