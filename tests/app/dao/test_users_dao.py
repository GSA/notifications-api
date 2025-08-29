import uuid
from datetime import timedelta

import pytest
from freezegun import freeze_time
from sqlalchemy import func, select
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.service_user_dao import dao_get_service_user, dao_update_service_user
from app.dao.users_dao import (
    _remove_values_for_keys_if_present,
    count_user_verify_codes,
    create_secret_code,
    dao_archive_user,
    delete_codes_older_created_more_than_a_day_ago,
    delete_model_user,
    get_login_gov_user,
    get_user_by_email,
    get_user_by_id,
    increment_failed_login_count,
    reset_failed_login_count,
    save_model_user,
    save_user_attribute,
    update_user_password,
    user_can_be_archived,
)
from app.enums import AuthType, CodeType, PermissionType, UserState
from app.errors import InvalidRequest
from app.models import User, VerifyCode
from app.utils import utc_now
from tests.app.db import (
    create_permissions,
    create_service,
    create_template_folder,
    create_user,
)


def _get_user_query_count():
    stmt = select(func.count(User.id))
    return db.session.execute(stmt).scalar() or 0


def _get_user_query_first():
    stmt = select(User)
    return db.session.execute(stmt).scalars().first()


def _get_verify_code_query_count():
    stmt = select(func.count(VerifyCode.id))
    return db.session.execute(stmt).scalar() or 0


@freeze_time("2020-01-28T12:00:00")
@pytest.mark.parametrize(
    "phone_number, expected_phone_number",
    [
        ("2028675309", "+12028675309"),
        ("+1-800-555-5555", "+18005555555"),
    ],
)
def test_create_user(notify_db_session, phone_number, expected_phone_number):
    email = "notify@digital.fake.gov"
    data = {
        "name": "Test User",
        "email_address": email,
        "password": "password",
        "mobile_number": phone_number,
    }
    user = User(**data)
    save_model_user(user, password="password", validated_email_access=True)
    stmt = select(func.count(User.id))
    assert db.session.execute(stmt).scalar() == 1
    stmt = select(User)
    user = db.session.execute(stmt).scalars().first()
    assert user.email_address == email
    assert user.id == user.id
    assert user.mobile_number == expected_phone_number
    assert user.email_access_validated_at == utc_now()
    assert not user.platform_admin


def test_get_all_users(notify_db_session):
    create_user(email="1@test.com")
    create_user(email="2@test.com")

    stmt = select(func.count(User.id))
    assert db.session.execute(stmt).scalar() == 2
    assert len(get_user_by_id()) == 2


def test_get_user(notify_db_session):
    email = "1@test.com"
    user = create_user(email=email)
    assert get_user_by_id(user_id=user.id).email_address == email


def test_get_user_not_exists(notify_db_session, fake_uuid):
    with pytest.raises(NoResultFound):
        get_user_by_id(user_id=fake_uuid)


def test_get_user_invalid_id(notify_db_session):
    with pytest.raises(DataError):
        get_user_by_id(user_id="blah")


def test_delete_users(sample_user):
    stmt = select(func.count(User.id))
    assert db.session.execute(stmt).scalar() == 1
    delete_model_user(sample_user)
    assert db.session.execute(stmt).scalar() == 0


def test_increment_failed_login_should_increment_failed_logins(sample_user):
    assert sample_user.failed_login_count == 0
    increment_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 1


def test_reset_failed_login_should_set_failed_logins_to_0(sample_user):
    increment_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 1
    reset_failed_login_count(sample_user)
    assert sample_user.failed_login_count == 0


def test_get_user_by_email(sample_user):
    user_from_db = get_user_by_email(sample_user.email_address)
    assert sample_user == user_from_db


def test_get_login_gov_user(sample_user):
    user_from_db = get_login_gov_user("123456", sample_user.email_address)
    assert sample_user.email_address == user_from_db.email_address
    assert user_from_db.login_uuid is not None


def test_get_user_by_email_is_case_insensitive(sample_user):
    email = sample_user.email_address
    user_from_db = get_user_by_email(email.upper())
    assert sample_user == user_from_db


def test_should_delete_all_verification_codes_more_than_one_day_old(sample_user):
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")
    stmt = select(func.count(VerifyCode.id))
    assert db.session.execute(stmt).scalar() == 2
    delete_codes_older_created_more_than_a_day_ago()
    assert db.session.execute(stmt).scalar() == 0


def test_should_not_delete_verification_codes_less_than_one_day_old(sample_user):
    make_verify_code(
        sample_user, age=timedelta(hours=23, minutes=59, seconds=59), code="12345"
    )
    make_verify_code(sample_user, age=timedelta(hours=24), code="54321")
    stmt = select(func.count(VerifyCode.id))
    assert db.session.execute(stmt).scalar() == 2
    delete_codes_older_created_more_than_a_day_ago()
    stmt = select(VerifyCode)
    assert db.session.execute(stmt).scalars().one()._code == "12345"


def make_verify_code(user, age=None, expiry_age=None, code="12335", code_used=False):
    verify_code = VerifyCode(
        code_type=CodeType.SMS,
        _code=code,
        created_at=utc_now() - (age or timedelta(hours=0)),
        expiry_datetime=utc_now() - (expiry_age or timedelta(0)),
        user=user,
        code_used=code_used,
    )
    db.session.add(verify_code)
    db.session.commit()


@pytest.mark.parametrize(
    "user_attribute, user_value",
    [
        ("name", "New User"),
        ("email_address", "newuser@mail.com"),
        ("mobile_number", "+4407700900460"),
    ],
)
def test_update_user_attribute(client, sample_user, user_attribute, user_value):
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {user_attribute: user_value}
    save_user_attribute(sample_user, update_dict)
    assert getattr(sample_user, user_attribute) == user_value


@freeze_time("2020-01-24T12:00:00")
def test_update_user_password(notify_api, notify_db_session, sample_user):
    sample_user.password_changed_at = utc_now() - timedelta(days=1)
    password = "newpassword"
    assert not sample_user.check_password(password)
    update_user_password(sample_user, password)
    assert sample_user.check_password(password)
    assert sample_user.password_changed_at == utc_now()


def test_count_user_verify_codes(sample_user):
    with freeze_time(utc_now() + timedelta(hours=1)):
        make_verify_code(sample_user, code_used=True)
        make_verify_code(sample_user, expiry_age=timedelta(hours=2))
        [make_verify_code(sample_user) for i in range(5)]

    assert count_user_verify_codes(sample_user) == 5


def test_create_secret_code_different_subsequent_codes():
    code1 = create_secret_code()
    code2 = create_secret_code()
    assert code1 != code2


def test_create_secret_code_returns_6_digits():
    code = create_secret_code()
    assert len(code) == 6


def test_create_secret_code_can_customize_digits():
    code_length = 10
    code = create_secret_code(code_length)
    assert len(code) == code_length


@freeze_time("2018-07-07 12:00:00")
def test_dao_archive_user(sample_user, sample_organization, fake_uuid):
    sample_user.current_session_id = fake_uuid

    # create 2 services for sample_user to be a member of (each with another active user)
    service_1 = create_service(service_name="Service 1")
    service_1_user = create_user(email="1@test.com")
    service_1.users = [sample_user, service_1_user]
    create_permissions(sample_user, service_1, PermissionType.MANAGE_SETTINGS)
    create_permissions(
        service_1_user,
        service_1,
        PermissionType.MANAGE_SETTINGS,
        PermissionType.VIEW_ACTIVITY,
    )

    service_2 = create_service(service_name="Service 2")
    service_2_user = create_user(email="2@test.com")
    service_2.users = [sample_user, service_2_user]
    create_permissions(sample_user, service_2, PermissionType.VIEW_ACTIVITY)
    create_permissions(service_2_user, service_2, PermissionType.MANAGE_SETTINGS)

    # make sample_user an org member
    sample_organization.users = [sample_user]

    # give sample_user folder permissions for a service_1 folder
    folder = create_template_folder(service_1)
    service_user = dao_get_service_user(sample_user.id, service_1.id)
    service_user.folders = [folder]
    dao_update_service_user(service_user)

    dao_archive_user(sample_user)

    assert sample_user.get_permissions() == {}
    assert sample_user.services == []
    assert sample_user.organizations == []
    assert sample_user.auth_type == AuthType.EMAIL
    assert sample_user.email_address == "_archived_2018-07-07_notify@digital.fake.gov"
    assert sample_user.mobile_number is None
    assert sample_user.current_session_id == uuid.UUID(
        "00000000-0000-0000-0000-000000000000"
    )
    assert sample_user.state == UserState.INACTIVE
    assert not sample_user.check_password("password")


def test_user_can_be_archived_if_they_do_not_belong_to_any_services(sample_user):
    assert sample_user.services == []
    assert user_can_be_archived(sample_user)


def test_user_can_be_archived_if_they_do_not_belong_to_any_active_services(
    sample_user, sample_service
):
    sample_user.services = [sample_service]
    sample_service.active = False

    assert len(sample_user.services) == 1
    assert user_can_be_archived(sample_user)


def test_user_can_be_archived_if_the_other_service_members_have_the_manage_settings_permission(
    sample_service,
):
    user_1 = create_user(email="1@test.com")
    user_2 = create_user(email="2@test.com")
    user_3 = create_user(email="3@test.com")

    sample_service.users = [user_1, user_2, user_3]

    create_permissions(user_1, sample_service, PermissionType.MANAGE_SETTINGS)
    create_permissions(
        user_2,
        sample_service,
        PermissionType.MANAGE_SETTINGS,
        PermissionType.VIEW_ACTIVITY,
    )
    create_permissions(
        user_3,
        sample_service,
        PermissionType.MANAGE_SETTINGS,
        PermissionType.SEND_EMAILS,
        PermissionType.SEND_TEXTS,
    )

    assert len(sample_service.users) == 3
    assert user_can_be_archived(user_1)


def test_dao_archive_user_raises_error_if_user_cannot_be_archived(sample_user, mocker):
    mocker.patch("app.dao.users_dao.user_can_be_archived", return_value=False)

    with pytest.raises(InvalidRequest):
        dao_archive_user(sample_user.id)


def test_user_cannot_be_archived_if_they_belong_to_a_service_with_no_other_active_users(
    sample_service,
):
    active_user = create_user(email="1@test.com")
    pending_user = create_user(email="2@test.com", state=UserState.PENDING)
    inactive_user = create_user(email="3@test.com", state=UserState.INACTIVE)

    sample_service.users = [active_user, pending_user, inactive_user]

    assert len(sample_service.users) == 3
    assert not user_can_be_archived(active_user)


def test_user_cannot_be_archived_if_the_other_service_members_do_not_have_the_manage_setting_permission(
    sample_service,
):
    active_user = create_user(email="1@test.com")
    pending_user = create_user(email="2@test.com")
    inactive_user = create_user(email="3@test.com")

    sample_service.users = [active_user, pending_user, inactive_user]

    create_permissions(active_user, sample_service, PermissionType.MANAGE_SETTINGS)
    create_permissions(pending_user, sample_service, PermissionType.VIEW_ACTIVITY)
    create_permissions(
        inactive_user,
        sample_service,
        PermissionType.SEND_EMAILS,
        PermissionType.SEND_TEXTS,
    )

    assert len(sample_service.users) == 3
    assert not user_can_be_archived(active_user)


def test_remove_values_for_keys_if_present():
    keys = {"a", "b", "c"}
    my_dict = {
        "a": 1,
        "b": 2,
        "c": 3,
        "d": 4,
    }
    _remove_values_for_keys_if_present(my_dict, keys)

    assert my_dict == {"d": 4}
