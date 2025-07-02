import uuid
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import MagicMock, Mock, patch

import pytest
import sqlalchemy
from freezegun import freeze_time
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.inbound_numbers_dao import (
    dao_get_available_inbound_numbers,
    dao_set_inbound_number_active_flag,
    dao_set_inbound_number_to_service,
)
from app.dao.organization_dao import dao_add_service_to_organization
from app.dao.service_permissions_dao import dao_remove_service_permission
from app.dao.service_user_dao import dao_get_service_user, dao_update_service_user
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_create_service,
    dao_fetch_active_users_for_service,
    dao_fetch_all_services,
    dao_fetch_all_services_by_user,
    dao_fetch_live_services_data,
    dao_fetch_service_by_id,
    dao_fetch_service_by_id_with_api_keys,
    dao_fetch_service_by_inbound_number,
    dao_fetch_stats_for_service_from_hours,
    dao_fetch_todays_stats_for_all_services,
    dao_fetch_todays_stats_for_service,
    dao_find_services_sending_to_tv_numbers,
    dao_find_services_with_high_failure_rates,
    dao_remove_user_from_service,
    dao_resume_service,
    dao_suspend_service,
    dao_update_service,
    delete_service_and_all_associated_db_objects,
    get_live_services_with_organization,
    get_services_by_partial_name,
    get_specific_days_stats,
)
from app.dao.users_dao import create_user_code, save_model_user
from app.enums import (
    CodeType,
    KeyType,
    NotificationStatus,
    NotificationType,
    OrganizationType,
    PermissionType,
    ServicePermissionType,
    StatisticsType,
    TemplateType,
)
from app.models import (
    ApiKey,
    InvitedUser,
    Job,
    Notification,
    NotificationHistory,
    Organization,
    Permission,
    Service,
    ServicePermission,
    ServiceUser,
    Template,
    TemplateHistory,
    User,
    VerifyCode,
    user_folder_permissions,
)
from app.utils import utc_now
from tests.app.db import (
    create_annual_billing,
    create_api_key,
    create_ft_billing,
    create_inbound_number,
    create_invited_user,
    create_notification,
    create_notification_history,
    create_organization,
    create_service,
    create_service_with_defined_sms_sender,
    create_service_with_inbound_number,
    create_template,
    create_template_folder,
    create_user,
)


def _get_service_query_count():
    stmt = select(func.count(Service.id))
    return db.session.execute(stmt).scalar() or 0


def _get_service_history_query_count():
    stmt = select(func.count(Service.get_history_model().id))
    return db.session.execute(stmt).scalar() or 0


def _get_first_service():
    stmt = select(Service).limit(1)
    service = db.session.execute(stmt).scalars().first()
    return service


def _get_service_by_id(service_id):
    stmt = select(Service).where(Service.id == service_id)

    service = db.session.execute(stmt).scalars().one()
    return service


def test_create_service(notify_db_session):
    user = create_user()
    assert _get_service_query_count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        organization_type=OrganizationType.FEDERAL,
        created_by=user,
    )
    dao_create_service(service, user)
    assert _get_service_query_count() == 1
    service_db = _get_first_service()
    assert service_db.name == "service_name"
    assert service_db.id == service.id
    assert service_db.email_from == "email_from"
    assert service_db.prefix_sms is True
    assert service.active is True
    assert user in service_db.users
    assert service_db.organization_type == OrganizationType.FEDERAL
    assert not service.organization_id


def test_create_service_with_organization(notify_db_session):
    user = create_user(email="local.authority@local-authority.gov.uk")
    organization = create_organization(
        name="Some local authority",
        organization_type=OrganizationType.STATE,
        domains=["local-authority.gov.uk"],
    )
    assert _get_service_query_count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        organization_type=OrganizationType.FEDERAL,
        created_by=user,
    )
    dao_create_service(service, user)
    assert _get_service_query_count() == 1
    service_db = _get_first_service()
    organization = db.session.get(Organization, organization.id)
    assert service_db.name == "service_name"
    assert service_db.id == service.id
    assert service_db.email_from == "email_from"
    assert service_db.prefix_sms is True
    assert service.active is True
    assert user in service_db.users
    assert service_db.organization_type == OrganizationType.STATE
    assert service.organization_id == organization.id
    assert service.organization == organization


def test_fetch_service_by_id_with_api_keys(notify_db_session):
    user = create_user(email="local.authority@local-authority.gov.uk")
    organization = create_organization(
        name="Some local authority",
        organization_type=OrganizationType.STATE,
        domains=["local-authority.gov.uk"],
    )
    assert _get_service_query_count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        organization_type=OrganizationType.FEDERAL,
        created_by=user,
    )
    dao_create_service(service, user)
    assert _get_service_query_count() == 1
    service_db = _get_first_service()
    organization = db.session.get(Organization, organization.id)
    assert service_db.name == "service_name"
    assert service_db.id == service.id
    assert service_db.email_from == "email_from"
    assert service_db.prefix_sms is True
    assert service.active is True
    assert user in service_db.users
    assert service_db.organization_type == OrganizationType.STATE
    assert service.organization_id == organization.id
    assert service.organization == organization

    service = dao_fetch_service_by_id_with_api_keys(service.id, False)
    assert service is not None
    assert service.api_keys is not None
    service = dao_fetch_service_by_id_with_api_keys(service.id, True)
    assert service is not None


def test_cannot_create_two_services_with_same_name(notify_db_session):
    user = create_user()
    assert _get_service_query_count() == 0
    service1 = Service(
        name="service_name",
        email_from="email_from1",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )

    service2 = Service(
        name="service_name",
        email_from="email_from2",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert 'duplicate key value violates unique constraint "services_name_key"' in str(
        excinfo.value
    )


def test_cannot_create_two_services_with_same_email_from(notify_db_session):
    user = create_user()
    assert _get_service_query_count() == 0
    service1 = Service(
        name="service_name1",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    service2 = Service(
        name="service_name2",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert (
        'duplicate key value violates unique constraint "services_email_from_key"'
        in str(excinfo.value)
    )


def test_cannot_create_service_with_no_user(notify_db_session):
    user = create_user()
    assert _get_service_query_count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    with pytest.raises(ValueError) as excinfo:
        dao_create_service(service, None)
    assert "Can't create a service without a user" in str(excinfo.value)


def test_should_add_user_to_service(notify_db_session):
    user = create_user()
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    dao_create_service(service, user)
    assert user in _get_first_service().users
    new_user = User(
        name="Test User",
        email_address="new_user@digital.fake.gov",
        password="password",
        mobile_number="+12028675309",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service, new_user)
    assert new_user in _get_first_service().users


def test_dao_add_user_to_service_sets_folder_permissions(sample_user, sample_service):
    folder_1 = create_template_folder(sample_service)
    folder_2 = create_template_folder(sample_service)

    assert not folder_1.users
    assert not folder_2.users

    folder_permissions = [str(folder_1.id), str(folder_2.id)]

    dao_add_user_to_service(
        sample_service, sample_user, folder_permissions=folder_permissions
    )

    service_user = dao_get_service_user(
        user_id=sample_user.id, service_id=sample_service.id
    )
    assert len(service_user.folders) == 2
    assert folder_1 in service_user.folders
    assert folder_2 in service_user.folders


def test_dao_add_user_to_service_ignores_folders_which_do_not_exist_when_setting_permissions(
    sample_user, sample_service, fake_uuid
):
    valid_folder = create_template_folder(sample_service)
    folder_permissions = [fake_uuid, str(valid_folder.id)]

    dao_add_user_to_service(
        sample_service, sample_user, folder_permissions=folder_permissions
    )

    service_user = dao_get_service_user(sample_user.id, sample_service.id)

    assert service_user.folders == [valid_folder]


def test_dao_add_user_to_service_raises_error_if_adding_folder_permissions_for_a_different_service(
    sample_service,
):
    user = create_user()
    other_service = create_service(service_name="other service")
    other_service_folder = create_template_folder(other_service)
    folder_permissions = [str(other_service_folder.id)]

    stmt = select(func.count(ServiceUser.service_id))
    assert db.session.execute(stmt).scalar() == 2

    with pytest.raises(IntegrityError) as e:
        dao_add_user_to_service(
            sample_service, user, folder_permissions=folder_permissions
        )

    db.session.rollback()
    assert (
        'insert or update on table "user_folder_permissions" violates foreign key constraint'
        in str(e.value)
    )
    stmt = select(func.count(ServiceUser.service_id))
    assert db.session.execute(stmt).scalar() == 2


def test_should_remove_user_from_service(notify_db_session):
    user = create_user()
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    dao_create_service(service, user)
    new_user = User(
        name="Test User",
        email_address="new_user@digital.fake.gov",
        password="password",
        mobile_number="+12028675309",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service, new_user)
    assert new_user in _get_first_service().users
    dao_remove_user_from_service(service, new_user)
    assert new_user not in _get_first_service().users


def test_should_remove_user_from_service_exception(notify_db_session):
    user = create_user()
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    dao_create_service(service, user)
    new_user = User(
        name="Test User",
        email_address="new_user@digital.fake.gov",
        password="password",
        mobile_number="+12028675309",
    )
    save_model_user(new_user, validated_email_access=True)
    wrong_user = User(
        name="Wrong User",
        email_address="wrong_user@digital.fake.gov",
        password="password",
        mobile_number="+12028675309",
    )
    with pytest.raises(expected_exception=Exception):
        dao_remove_user_from_service(service, wrong_user)


def test_removing_a_user_from_a_service_deletes_their_permissions(
    sample_user, sample_service
):
    stmt = select(Permission)
    assert len(db.session.execute(stmt).all()) == 7

    dao_remove_user_from_service(sample_service, sample_user)

    assert db.session.execute(stmt).all() == []


def test_removing_a_user_from_a_service_deletes_their_folder_permissions_for_that_service(
    sample_user, sample_service
):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_2 = create_service(sample_user, service_name="other service")
    tf3 = create_template_folder(service_2)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    service_2_user = dao_get_service_user(sample_user.id, service_2.id)
    service_2_user.folders = [tf3]
    dao_update_service_user(service_2_user)

    dao_remove_user_from_service(sample_service, sample_user)

    user_folder_permission = db.session.query(user_folder_permissions).one()
    assert user_folder_permission.user_id == service_2_user.user_id
    assert user_folder_permission.service_id == service_2_user.service_id
    assert user_folder_permission.template_folder_id == tf3.id


def test_get_all_services(notify_db_session):
    create_service(service_name="service 1", email_from="service.1")
    assert len(dao_fetch_all_services()) == 1
    assert dao_fetch_all_services()[0].name == "service 1"

    create_service(service_name="service 2", email_from="service.2")
    assert len(dao_fetch_all_services()) == 2
    assert dao_fetch_all_services()[1].name == "service 2"


def test_get_all_services_should_return_in_created_order(notify_db_session):
    create_service(service_name="service 1", email_from="service.1")
    create_service(service_name="service 2", email_from="service.2")
    create_service(service_name="service 3", email_from="service.3")
    create_service(service_name="service 4", email_from="service.4")
    assert len(dao_fetch_all_services()) == 4
    assert dao_fetch_all_services()[0].name == "service 1"
    assert dao_fetch_all_services()[1].name == "service 2"
    assert dao_fetch_all_services()[2].name == "service 3"
    assert dao_fetch_all_services()[3].name == "service 4"


def test_get_all_services_should_return_empty_list_if_no_services():
    assert len(dao_fetch_all_services()) == 0


def test_get_all_services_for_user(notify_db_session):
    user = create_user()
    create_service(service_name="service 1", user=user, email_from="service.1")
    create_service(service_name="service 2", user=user, email_from="service.2")
    create_service(service_name="service 3", user=user, email_from="service.3")
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == "service 1"
    assert dao_fetch_all_services_by_user(user.id)[1].name == "service 2"
    assert dao_fetch_all_services_by_user(user.id)[2].name == "service 3"


def test_get_services_by_partial_name(notify_db_session):
    create_service(service_name="Tadfield Police")
    create_service(service_name="Tadfield Air Base")
    create_service(service_name="London M25 Management Body")
    services_from_db = get_services_by_partial_name("Tadfield")
    assert len(services_from_db) == 2
    assert sorted([service.name for service in services_from_db]) == [
        "Tadfield Air Base",
        "Tadfield Police",
    ]


def test_get_services_by_partial_name_is_case_insensitive(notify_db_session):
    create_service(service_name="Tadfield Police")
    services_from_db = get_services_by_partial_name("tadfield")
    assert services_from_db[0].name == "Tadfield Police"


def test_get_all_user_services_only_returns_services_user_has_access_to(
    notify_db_session,
):
    user = create_user()
    create_service(service_name="service 1", user=user, email_from="service.1")
    create_service(service_name="service 2", user=user, email_from="service.2")
    service_3 = create_service(
        service_name="service 3", user=user, email_from="service.3"
    )
    new_user = User(
        name="Test User",
        email_address="new_user@digital.fake.gov",
        password="password",
        mobile_number="+12028675309",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service_3, new_user)
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == "service 1"
    assert dao_fetch_all_services_by_user(user.id)[1].name == "service 2"
    assert dao_fetch_all_services_by_user(user.id)[2].name == "service 3"
    assert len(dao_fetch_all_services_by_user(new_user.id)) == 1
    assert dao_fetch_all_services_by_user(new_user.id)[0].name == "service 3"


def test_get_all_user_services_should_return_empty_list_if_no_services_for_user(
    notify_db_session,
):
    user = create_user()
    assert len(dao_fetch_all_services_by_user(user.id)) == 0


@freeze_time("2019-04-23T10:00:00")
def test_dao_fetch_live_services_data(sample_user):
    org = create_organization(organization_type=OrganizationType.FEDERAL)
    service = create_service(go_live_user=sample_user, go_live_at="2014-04-20T10:00:00")
    sms_template = create_template(service=service)
    service_2 = create_service(
        service_name="second",
        go_live_at="2017-04-20T10:00:00",
        go_live_user=sample_user,
    )
    service_3 = create_service(service_name="third", go_live_at="2016-04-20T10:00:00")
    # below services should be filtered out:
    create_service(service_name="restricted", restricted=True)
    create_service(service_name="not_active", active=False)
    create_service(service_name="not_live", count_as_live=False)
    email_template = create_template(service=service, template_type=TemplateType.EMAIL)
    dao_add_service_to_organization(service=service, organization_id=org.id)
    # two sms billing records for 1st service within current financial year:
    create_ft_billing(local_date="2019-04-20", template=sms_template)
    create_ft_billing(local_date="2019-04-21", template=sms_template)
    # one sms billing record for 1st service from previous financial year, should not appear in the result:
    create_ft_billing(local_date="2018-04-20", template=sms_template)
    # one email billing record for 1st service within current financial year:
    create_ft_billing(local_date="2019-04-20", template=email_template)

    # 1st service: billing from 2018 and 2019
    create_annual_billing(service.id, 500, 2018)
    create_annual_billing(service.id, 100, 2019)
    # 2nd service: billing from 2018
    create_annual_billing(service_2.id, 300, 2018)
    # 3rd service: billing from 2019
    create_annual_billing(service_3.id, 200, 2019)

    results = dao_fetch_live_services_data()
    assert len(results) == 3
    # checks the results and that they are ordered by date:
    assert results == [
        {
            "service_id": mock.ANY,
            "service_name": "Sample service",
            "organization_name": "test_org_1",
            "organization_type": OrganizationType.FEDERAL,
            "consent_to_research": None,
            "contact_name": "Test User",
            "contact_email": "notify@digital.fake.gov",
            "contact_mobile": "+12028675309",
            "live_date": datetime(2014, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "email_volume_intent": None,
            "sms_totals": 2,
            "email_totals": 1,
            "free_sms_fragment_limit": 100,
        },
        {
            "service_id": mock.ANY,
            "service_name": "third",
            "organization_name": None,
            "consent_to_research": None,
            "organization_type": None,
            "contact_name": None,
            "contact_email": None,
            "contact_mobile": None,
            "live_date": datetime(2016, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "email_volume_intent": None,
            "sms_totals": 0,
            "email_totals": 0,
            "free_sms_fragment_limit": 200,
        },
        {
            "service_id": mock.ANY,
            "service_name": "second",
            "organization_name": None,
            "consent_to_research": None,
            "contact_name": "Test User",
            "contact_email": "notify@digital.fake.gov",
            "contact_mobile": "+12028675309",
            "live_date": datetime(2017, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "organization_type": None,
            "email_volume_intent": None,
            "sms_totals": 0,
            "email_totals": 0,
            "free_sms_fragment_limit": 300,
        },
    ]


def test_get_service_by_id_returns_none_if_no_service(notify_db_session):
    with pytest.raises(NoResultFound) as e:
        dao_fetch_service_by_id(str(uuid.uuid4()))
    assert "No row was found when one was required" in str(e.value)


def test_get_service_by_id_returns_service(notify_db_session):
    service = create_service(service_name="testing", email_from="testing")
    assert dao_fetch_service_by_id(service.id).name == "testing"


def test_create_service_returns_service_with_default_permissions(notify_db_session):
    service = create_service(
        service_name="testing", email_from="testing", service_permissions=None
    )

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(
        service.permissions,
        (
            ServicePermissionType.SMS,
            ServicePermissionType.EMAIL,
            ServicePermissionType.INTERNATIONAL_SMS,
        ),
    )


@pytest.mark.parametrize(
    "permission_to_remove, permissions_remaining",
    [
        (
            ServicePermissionType.SMS,
            (
                ServicePermissionType.EMAIL,
                ServicePermissionType.INTERNATIONAL_SMS,
            ),
        ),
        (
            ServicePermissionType.EMAIL,
            (
                ServicePermissionType.SMS,
                ServicePermissionType.INTERNATIONAL_SMS,
            ),
        ),
    ],
)
def test_remove_permission_from_service_by_id_returns_service_with_correct_permissions(
    notify_db_session, permission_to_remove, permissions_remaining
):
    service = create_service(service_permissions=None)
    dao_remove_service_permission(
        service_id=service.id, permission=permission_to_remove
    )

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(service.permissions, permissions_remaining)


def test_removing_all_permission_returns_service_with_no_permissions(notify_db_session):
    service = create_service()
    dao_remove_service_permission(
        service_id=service.id,
        permission=ServicePermissionType.SMS,
    )
    dao_remove_service_permission(
        service_id=service.id,
        permission=ServicePermissionType.EMAIL,
    )
    dao_remove_service_permission(
        service_id=service.id,
        permission=ServicePermissionType.INTERNATIONAL_SMS,
    )

    service = dao_fetch_service_by_id(service.id)
    assert len(service.permissions) == 0


def test_create_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert _get_service_query_count() == 0
    assert _get_service_history_query_count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    dao_create_service(service, user)
    assert _get_service_query_count() == 1
    assert _get_service_history_query_count() == 1

    service_from_db = _get_first_service()
    stmt = select(Service.get_history_model())
    service_history = db.session.execute(stmt).scalars().first()

    assert service_from_db.id == service_history.id
    assert service_from_db.name == service_history.name
    assert service_from_db.version == 1
    assert service_from_db.version == service_history.version
    assert user.id == service_history.created_by_id
    assert service_from_db.created_by.id == service_history.created_by_id


def test_update_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert _get_service_query_count() == 0
    assert _get_service_history_query_count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    dao_create_service(service, user)

    assert _get_service_query_count() == 1
    assert _get_first_service().version == 1
    assert _get_service_history_query_count() == 1

    service.name = "updated_service_name"
    dao_update_service(service)

    assert _get_service_query_count() == 1
    assert _get_service_history_query_count() == 2

    service_from_db = _get_first_service()

    assert service_from_db.version == 2
    stmt = select(Service.get_history_model()).where(
        Service.get_history_model().name == "service_name"
    )
    assert db.session.execute(stmt).scalars().one().version == 1
    stmt = select(Service.get_history_model()).where(
        Service.get_history_model().name == "updated_service_name"
    )
    assert db.session.execute(stmt).scalars().one().version == 2


def test_update_service_permission_creates_a_history_record_with_current_data(
    notify_db_session,
):
    user = create_user()
    assert _get_service_query_count() == 0
    assert _get_service_history_query_count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )
    dao_create_service(
        service,
        user,
        service_permissions=[
            ServicePermissionType.SMS,
            # ServicePermissionType.EMAIL,
            ServicePermissionType.INTERNATIONAL_SMS,
        ],
    )

    assert _get_service_query_count() == 1

    service.permissions.append(
        ServicePermission(service_id=service.id, permission=ServicePermissionType.EMAIL)
    )
    dao_update_service(service)

    assert _get_service_query_count() == 1
    assert _get_service_history_query_count() == 2

    service_from_db = _get_first_service()

    assert service_from_db.version == 2

    _assert_service_permissions(
        service.permissions,
        (
            ServicePermissionType.SMS,
            ServicePermissionType.EMAIL,
            ServicePermissionType.INTERNATIONAL_SMS,
        ),
    )

    permission = [
        p for p in service.permissions if p.permission == ServicePermissionType.SMS
    ][0]
    service.permissions.remove(permission)
    dao_update_service(service)

    assert _get_service_query_count() == 1
    assert _get_service_history_query_count() == 3

    service_from_db = _get_first_service()
    assert service_from_db.version == 3
    _assert_service_permissions(
        service.permissions,
        (
            ServicePermissionType.EMAIL,
            ServicePermissionType.INTERNATIONAL_SMS,
        ),
    )

    stmt = (
        select(Service.get_history_model())
        .where(Service.get_history_model().name == "service_name")
        .order_by("version")
    )
    history = db.session.execute(stmt).scalars().all()
    assert len(history) == 3
    assert history[2].version == 3


def test_create_service_and_history_is_transactional(notify_db_session):
    user = create_user()
    assert _get_service_query_count() == 0
    assert _get_service_history_query_count() == 0
    service = Service(
        name=None,
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )

    try:
        dao_create_service(service, user)
    except sqlalchemy.exc.IntegrityError as seeei:
        assert (
            'null value in column "name" of relation "services_history" violates not-null constraint'
            in str(seeei)
        )

    assert _get_service_query_count() == 0
    assert _get_service_history_query_count() == 0


def test_delete_service_and_associated_objects(notify_db_session):
    user = create_user()
    organization = create_organization()
    service = create_service(
        user=user, service_permissions=None, organization=organization
    )
    create_user_code(user=user, code="somecode", code_type=CodeType.EMAIL)
    create_user_code(user=user, code="somecode", code_type=CodeType.SMS)
    template = create_template(service=service)
    api_key = create_api_key(service=service)
    create_notification(template=template, api_key=api_key)
    create_invited_user(service=service)
    user.organizations = [organization]
    stmt = select(func.count(ServicePermission.service_id))
    assert db.session.execute(stmt).scalar() == len(
        (
            ServicePermissionType.SMS,
            ServicePermissionType.EMAIL,
            ServicePermissionType.INTERNATIONAL_SMS,
        )
    )

    delete_service_and_all_associated_db_objects(service)
    stmt = select(VerifyCode)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(ApiKey)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(ApiKey.get_history_model())
    assert db.session.execute(stmt).scalar() is None
    stmt = select(Template)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(TemplateHistory)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(Job)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(Notification)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(Permission)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(User)
    assert db.session.execute(stmt).scalar() is None
    stmt = select(InvitedUser)
    assert db.session.execute(stmt).scalar() is None

    assert _get_service_query_count() == 0
    assert _get_service_history_query_count() == 0
    stmt = select(ServicePermission)
    assert db.session.execute(stmt).scalar() is None

    # the organization hasn't been deleted
    stmt = select(func.count(Organization.id))
    assert db.session.execute(stmt).scalar() == 1


def test_add_existing_user_to_another_service_doesnot_change_old_permissions(
    notify_db_session,
):
    user = create_user()

    service_one = Service(
        name="service_one",
        email_from="service_one",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )

    dao_create_service(service_one, user)
    assert user.id == service_one.users[0].id
    stmt = select(Permission).where(
        Permission.service == service_one, Permission.user == user
    )
    test_user_permissions = db.session.execute(stmt).all()
    assert len(test_user_permissions) == 7

    other_user = User(
        name="Other Test User",
        email_address="other_user@digital.fake.gov",
        password="password",
        mobile_number="+12028672000",
    )
    save_model_user(other_user, validated_email_access=True)
    service_two = Service(
        name="service_two",
        email_from="service_two",
        message_limit=1000,
        restricted=False,
        created_by=other_user,
    )
    dao_create_service(service_two, other_user)

    assert other_user.id == service_two.users[0].id
    stmt = select(Permission).where(
        Permission.service == service_two, Permission.user == other_user
    )
    other_user_permissions = db.session.execute(stmt).all()
    assert len(other_user_permissions) == 7
    stmt = select(Permission).where(
        Permission.service == service_one, Permission.user == other_user
    )
    other_user_service_one_permissions = db.session.execute(stmt).all()

    assert len(other_user_service_one_permissions) == 0

    # adding the other_user to service_one should leave all other_user permissions on service_two intact
    permissions = []
    for p in [PermissionType.SEND_EMAILS, PermissionType.SEND_TEXTS]:
        permissions.append(Permission(permission=p))

    dao_add_user_to_service(service_one, other_user, permissions=permissions)
    stmt = select(Permission).where(
        Permission.service == service_one, Permission.user == other_user
    )
    other_user_service_one_permissions = db.session.execute(stmt).all()
    assert len(other_user_service_one_permissions) == 2

    stmt = select(Permission).where(
        Permission.service == service_two, Permission.user == other_user
    )
    other_user_service_two_permissions = db.session.execute(stmt).all()
    assert len(other_user_service_two_permissions) == 7


def test_fetch_stats_filters_on_service(notify_db_session):
    service_one = create_service()
    create_notification(template=create_template(service=service_one))

    service_two = Service(
        name="service_two",
        created_by=service_one.created_by,
        email_from="hello",
        restricted=False,
        message_limit=1000,
    )
    dao_create_service(service_two, service_one.created_by)

    stats = dao_fetch_todays_stats_for_service(service_two.id)
    assert len(stats) == 0


def test_fetch_stats_ignores_historical_notification_data(sample_template):
    create_notification_history(template=sample_template)
    stmt = select(func.count(Notification.id))
    assert db.session.execute(stmt).scalar() == 0
    stmt = select(func.count(NotificationHistory.id))
    assert db.session.execute(stmt).scalar() == 1

    stats = dao_fetch_todays_stats_for_service(sample_template.service_id)
    assert len(stats) == 0


def test_dao_fetch_todays_stats_for_service(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type=TemplateType.EMAIL)
    # two created email, one failed email, and one created sms
    create_notification(template=email_template, status=NotificationStatus.CREATED)
    create_notification(template=email_template, status=NotificationStatus.CREATED)
    create_notification(
        template=email_template, status=NotificationStatus.TECHNICAL_FAILURE
    )
    create_notification(template=sms_template, status=NotificationStatus.CREATED)

    stats = dao_fetch_todays_stats_for_service(service.id)
    stats = sorted(stats, key=lambda x: (x.notification_type, x.status))
    assert len(stats) == 3

    assert stats[0].notification_type == NotificationType.EMAIL
    assert stats[0].status == NotificationStatus.CREATED
    assert stats[0].count == 2

    assert stats[1].notification_type == NotificationType.EMAIL
    assert stats[1].status == NotificationStatus.TECHNICAL_FAILURE
    assert stats[1].count == 1

    assert stats[2].notification_type == NotificationType.SMS
    assert stats[2].status == NotificationStatus.CREATED
    assert stats[2].count == 1


def test_dao_fetch_todays_stats_for_service_should_ignore_test_key(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    live_api_key = create_api_key(service=service, key_type=KeyType.NORMAL)
    team_api_key = create_api_key(service=service, key_type=KeyType.TEAM)
    test_api_key = create_api_key(service=service, key_type=KeyType.TEST)

    # two created email, one failed email, and one created sms
    create_notification(
        template=template, api_key=live_api_key, key_type=live_api_key.key_type
    )
    create_notification(
        template=template, api_key=test_api_key, key_type=test_api_key.key_type
    )
    create_notification(
        template=template, api_key=team_api_key, key_type=team_api_key.key_type
    )
    create_notification(template=template)

    stats = dao_fetch_todays_stats_for_service(service.id)
    assert len(stats) == 1
    assert stats[0].notification_type == NotificationType.SMS
    assert stats[0].status == NotificationStatus.CREATED
    assert stats[0].count == 3


def test_dao_fetch_todays_stats_for_service_only_includes_today(notify_db_session):
    template = create_template(service=create_service())
    # two created email, one failed email, and one created sms
    with freeze_time("2001-01-02T04:59:00"):
        # just_before_midnight_yesterday
        create_notification(
            template=template,
            to_field="1",
            status=NotificationStatus.DELIVERED,
        )

    with freeze_time("2001-01-02T05:01:00"):
        # just_after_midnight_today
        create_notification(
            template=template,
            to_field="2",
            status=NotificationStatus.FAILED,
        )

    with freeze_time("2001-01-02T12:00:00"):
        # right_now
        create_notification(
            template=template,
            to_field="3",
            status=NotificationStatus.CREATED,
        )

        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert stats[NotificationStatus.DELIVERED] == 1
    assert stats[NotificationStatus.FAILED] == 1
    assert stats[NotificationStatus.CREATED] == 1


@pytest.mark.skip(reason="Need a better way to test variable DST date")
def test_dao_fetch_todays_stats_for_service_only_includes_today_when_clocks_spring_forward(
    notify_db_session,
):
    template = create_template(service=create_service())
    with freeze_time("2021-03-27T23:59:59"):
        # just before midnight yesterday in UTC -- not included
        create_notification(
            template=template,
            to_field="1",
            status=NotificationStatus.PERMANENT_FAILURE,
        )
    with freeze_time("2021-03-28T00:01:00"):
        # just after midnight yesterday in UTC -- included
        create_notification(
            template=template,
            to_field="2",
            status=NotificationStatus.FAILED,
        )
    with freeze_time("2021-03-28T12:00:00"):
        # we have entered BST at this point but had not for the previous two notifications --included
        # collect stats for this timestamp
        create_notification(
            template=template,
            to_field="3",
            status=NotificationStatus.CREATED,
        )
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert NotificationStatus.DELIVERED not in stats
    assert stats[NotificationStatus.FAILED] == 1
    assert stats[NotificationStatus.CREATED] == 1
    assert not stats.get(NotificationStatus.PERMANENT_FAILURE)
    assert not stats.get(NotificationStatus.TEMPORARY_FAILURE)


def test_dao_fetch_todays_stats_for_service_only_includes_today_during_bst(
    notify_db_session,
):
    template = create_template(service=create_service())
    with freeze_time("2021-03-28T23:59:59"):
        # just before midnight BST -- not included
        create_notification(
            template=template, to_field="1", status=NotificationStatus.PERMANENT_FAILURE
        )
    with freeze_time("2021-03-29T04:00:01"):
        # just after midnight BST -- included
        create_notification(
            template=template, to_field="2", status=NotificationStatus.FAILED
        )
    with freeze_time("2021-03-29T12:00:00"):
        # well after midnight BST -- included
        # collect stats for this timestamp
        create_notification(
            template=template, to_field="3", status=NotificationStatus.CREATED
        )
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert NotificationStatus.DELIVERED not in stats
    assert stats[NotificationStatus.FAILED] == 1
    assert stats[NotificationStatus.CREATED] == 1
    assert not stats.get(NotificationStatus.PERMANENT_FAILURE)


def test_dao_fetch_todays_stats_for_service_only_includes_today_when_clocks_fall_back(
    notify_db_session,
):
    template = create_template(service=create_service())
    with freeze_time("2021-10-30T22:59:59"):
        # just before midnight BST -- not included
        create_notification(
            template=template, to_field="1", status=NotificationStatus.PERMANENT_FAILURE
        )
    with freeze_time("2021-10-31T23:00:01"):
        # just after midnight BST -- included
        create_notification(
            template=template, to_field="2", status=NotificationStatus.FAILED
        )
    # clocks go back to UTC on 31 October at 2am
    with freeze_time("2021-10-31T12:00:00"):
        # well after midnight -- included
        # collect stats for this timestamp
        create_notification(
            template=template, to_field="3", status=NotificationStatus.CREATED
        )
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert NotificationStatus.DELIVERED not in stats
    assert stats[NotificationStatus.FAILED] == 1
    assert stats[NotificationStatus.CREATED] == 1
    assert not stats.get(NotificationStatus.PERMANENT_FAILURE)


def test_dao_fetch_todays_stats_for_service_only_includes_during_utc(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time("2021-10-30T12:59:59"):
        # just before midnight UTC -- not included
        create_notification(
            template=template, to_field="1", status=NotificationStatus.PERMANENT_FAILURE
        )
    with freeze_time("2021-10-31T05:00:01"):
        # just after midnight UTC -- included
        create_notification(
            template=template, to_field="2", status=NotificationStatus.FAILED
        )
    # clocks go back to UTC on 31 October at 2am
    with freeze_time("2021-10-31T12:00:00"):
        # well after midnight -- included
        # collect stats for this timestamp
        create_notification(
            template=template, to_field="3", status=NotificationStatus.CREATED
        )
        stats = dao_fetch_todays_stats_for_service(template.service_id)

    stats = {row.status: row.count for row in stats}
    assert NotificationStatus.DELIVERED not in stats
    assert stats[NotificationStatus.FAILED] == 1
    assert stats[NotificationStatus.CREATED] == 1
    assert not stats.get(NotificationStatus.PERMANENT_FAILURE)


def test_dao_fetch_todays_stats_for_all_services_includes_all_services(
    notify_db_session,
):
    # two services, each with an email and sms notification
    service1 = create_service(service_name="service 1", email_from="service.1")
    service2 = create_service(service_name="service 2", email_from="service.2")
    template_email_one = create_template(
        service=service1, template_type=TemplateType.EMAIL
    )
    template_sms_one = create_template(service=service1, template_type=TemplateType.SMS)
    template_email_two = create_template(
        service=service2, template_type=TemplateType.EMAIL
    )
    template_sms_two = create_template(service=service2, template_type=TemplateType.SMS)
    create_notification(template=template_email_one)
    create_notification(template=template_sms_one)
    create_notification(template=template_email_two)
    create_notification(template=template_sms_two)

    stats = dao_fetch_todays_stats_for_all_services()

    assert len(stats) == 4
    # services are ordered by service id; not explicit on email/sms or status
    assert stats == sorted(stats, key=lambda x: x.service_id)


def test_dao_fetch_todays_stats_for_all_services_only_includes_today(notify_db_session):
    template = create_template(service=create_service())
    with freeze_time("2001-01-01T23:59:00"):
        # just_before_midnight_yesterday
        create_notification(
            template=template, to_field="1", status=NotificationStatus.DELIVERED
        )

    with freeze_time("2001-01-02T05:01:00"):
        # just_after_midnight_today
        create_notification(
            template=template, to_field="2", status=NotificationStatus.FAILED
        )

    with freeze_time("2001-01-02T12:00:00"):
        stats = dao_fetch_todays_stats_for_all_services()

    stats = {row.status: row.count for row in stats}
    assert NotificationStatus.DELIVERED not in stats
    assert stats[NotificationStatus.FAILED] == 1


def test_dao_fetch_todays_stats_for_all_services_groups_correctly(notify_db_session):
    service1 = create_service(service_name="service 1", email_from="service.1")
    service2 = create_service(service_name="service 2", email_from="service.2")
    template_sms = create_template(service=service1)
    template_email = create_template(service=service1, template_type=TemplateType.EMAIL)
    template_two = create_template(service=service2)
    # service1: 2 sms with status "created" and one "failed", and one email
    create_notification(template=template_sms)
    create_notification(template=template_sms)
    create_notification(template=template_sms, status=NotificationStatus.FAILED)
    create_notification(template=template_email)
    # service2: 1 sms "created"
    create_notification(template=template_two)

    stats = dao_fetch_todays_stats_for_all_services()
    assert len(stats) == 4
    assert (
        service1.id,
        service1.name,
        service1.restricted,
        service1.active,
        service1.created_at,
        NotificationType.SMS,
        NotificationStatus.CREATED,
        2,
    ) in stats
    assert (
        service1.id,
        service1.name,
        service1.restricted,
        service1.active,
        service1.created_at,
        NotificationType.SMS,
        NotificationStatus.FAILED,
        1,
    ) in stats
    assert (
        service1.id,
        service1.name,
        service1.restricted,
        service1.active,
        service1.created_at,
        NotificationType.EMAIL,
        NotificationStatus.CREATED,
        1,
    ) in stats
    assert (
        service2.id,
        service2.name,
        service2.restricted,
        service2.active,
        service2.created_at,
        NotificationType.SMS,
        NotificationStatus.CREATED,
        1,
    ) in stats


def test_dao_fetch_todays_stats_for_all_services_includes_all_keys_by_default(
    notify_db_session,
):
    template = create_template(service=create_service())
    create_notification(template=template, key_type=KeyType.NORMAL)
    create_notification(template=template, key_type=KeyType.TEAM)
    create_notification(template=template, key_type=KeyType.TEST)

    stats = dao_fetch_todays_stats_for_all_services()

    assert len(stats) == 1
    assert stats[0].count == 3


def test_dao_fetch_todays_stats_for_all_services_can_exclude_from_test_key(
    notify_db_session,
):
    template = create_template(service=create_service())
    create_notification(template=template, key_type=KeyType.NORMAL)
    create_notification(template=template, key_type=KeyType.TEAM)
    create_notification(template=template, key_type=KeyType.TEST)

    stats = dao_fetch_todays_stats_for_all_services(include_from_test_key=False)

    assert len(stats) == 1
    assert stats[0].count == 2


@freeze_time("2001-01-01T23:59:00")
def test_dao_suspend_service_with_no_api_keys(notify_db_session):
    service = create_service()
    dao_suspend_service(service.id)
    service = _get_service_by_id(service.id)
    assert not service.active
    assert service.name == service.name
    assert service.api_keys == []


@freeze_time("2001-01-01T23:59:00")
def test_dao_suspend_service_marks_service_as_inactive_and_expires_api_keys(
    notify_db_session,
):
    service = create_service()
    api_key = create_api_key(service=service)
    dao_suspend_service(service.id)
    service = _get_service_by_id(service.id)
    assert not service.active
    assert service.name == service.name

    api_key = db.session.get(ApiKey, api_key.id)
    assert api_key.expiry_date == datetime(2001, 1, 1, 23, 59, 00)


@freeze_time("2001-01-01T23:59:00")
def test_dao_resume_service_marks_service_as_active_and_api_keys_are_still_revoked(
    notify_db_session,
):
    service = create_service()
    api_key = create_api_key(service=service)
    dao_suspend_service(service.id)
    service = _get_service_by_id(service.id)
    assert not service.active

    dao_resume_service(service.id)
    assert _get_service_by_id(service.id).active

    api_key = db.session.get(ApiKey, api_key.id)
    assert api_key.expiry_date == datetime(2001, 1, 1, 23, 59, 00)


def test_dao_fetch_active_users_for_service_returns_active_only(notify_db_session):
    active_user = create_user(email="active@foo.com", state="active")
    pending_user = create_user(email="pending@foo.com", state="pending")
    service = create_service(user=active_user)
    dao_add_user_to_service(service, pending_user)
    users = dao_fetch_active_users_for_service(service.id)

    assert len(users) == 1


def test_dao_fetch_service_by_inbound_number_with_inbound_number(notify_db_session):
    foo1 = create_service_with_inbound_number(service_name="a", inbound_number="1")
    create_service_with_defined_sms_sender(service_name="b", sms_sender_value="2")
    create_service_with_defined_sms_sender(service_name="c", sms_sender_value="3")
    create_inbound_number("2")
    create_inbound_number("3")

    service = dao_fetch_service_by_inbound_number("1")

    assert foo1.id == service.id


def test_dao_fetch_service_by_inbound_number_with_inbound_number_not_set(
    notify_db_session,
):
    create_inbound_number("1")

    service = dao_fetch_service_by_inbound_number("1")

    assert service is None


def test_dao_fetch_service_by_inbound_number_when_inbound_number_set(notify_db_session):
    service_1 = create_service_with_inbound_number(inbound_number="1", service_name="a")
    create_service(service_name="b")

    service = dao_fetch_service_by_inbound_number("1")

    assert service.id == service_1.id


def test_dao_fetch_service_by_inbound_number_with_unknown_number(notify_db_session):
    create_service_with_inbound_number(inbound_number="1", service_name="a")

    service = dao_fetch_service_by_inbound_number("9")

    assert service is None


def test_dao_fetch_service_by_inbound_number_with_inactive_number_returns_empty(
    notify_db_session,
):
    service = create_service_with_inbound_number(inbound_number="1", service_name="a")
    dao_set_inbound_number_active_flag(service_id=service.id, active=False)

    service = dao_fetch_service_by_inbound_number("1")

    assert service is None


def test_dao_allocating_inbound_number_shows_on_service(notify_db_session):
    create_service_with_inbound_number()
    create_inbound_number(number="07700900003")

    inbound_numbers = dao_get_available_inbound_numbers()

    service = create_service(service_name="test service")

    dao_set_inbound_number_to_service(service.id, inbound_numbers[0])

    assert service.inbound_number.number == inbound_numbers[0].number


def _assert_service_permissions(service_permissions, expected):
    assert len(service_permissions) == len(expected)
    assert set(expected) == set(p.permission for p in service_permissions)


@pytest.mark.skip(
    reason="We can't search on recipient if recipient is not kept in the db"
)
@freeze_time("2019-12-02 12:00:00.000000")
def test_dao_find_services_sending_to_tv_numbers(notify_db_session, fake_uuid):
    service_1 = create_service(service_name="Service 1", service_id=fake_uuid)
    service_3 = create_service(
        service_name="Service 3", restricted=True
    )  # restricted is excluded
    service_5 = create_service(
        service_name="Service 5", active=False
    )  # not active is excluded
    services = [service_1, service_3, service_5]

    tv_number = "447700900001"
    normal_number = "447711900001"
    normal_number_resembling_tv_number = "447227700900"

    for service in services:
        template = create_template(service)
        for _ in range(0, 5):
            create_notification(
                template,
                normalised_to=tv_number,
                status=NotificationStatus.PERMANENT_FAILURE,
            )

    service_6 = create_service(
        service_name="Service 6"
    )  # notifications too old are excluded
    with freeze_time("2019-11-30 15:00:00.000000"):
        template_6 = create_template(service_6)
        for _ in range(0, 5):
            create_notification(
                template_6,
                normalised_to=tv_number,
                status=NotificationStatus.PERMANENT_FAILURE,
            )

    service_2 = create_service(service_name="Service 2")  # below threshold is excluded
    template_2 = create_template(service_2)
    create_notification(
        template_2,
        normalised_to=tv_number,
        status=NotificationStatus.PERMANENT_FAILURE,
    )
    for _ in range(0, 5):
        # test key type is excluded
        create_notification(
            template_2,
            normalised_to=tv_number,
            status=NotificationStatus.PERMANENT_FAILURE,
            key_type=KeyType.TEST,
        )
    for _ in range(0, 5):
        # normal numbers are not counted by the query
        create_notification(
            template_2, normalised_to=normal_number, status=NotificationStatus.DELIVERED
        )
        create_notification(
            template_2,
            normalised_to=normal_number_resembling_tv_number,
            status=NotificationStatus.DELIVERED,
        )

    start_date = utc_now() - timedelta(days=1)
    end_date = utc_now()

    result = dao_find_services_sending_to_tv_numbers(start_date, end_date, threshold=4)
    assert len(result) == 1
    assert str(result[0].service_id) == fake_uuid


def test_dao_find_services_with_high_failure_rates(notify_db_session, fake_uuid):
    service_1 = create_service(service_name="Service 1", service_id=fake_uuid)
    service_3 = create_service(
        service_name="Service 3", restricted=True
    )  # restricted is excluded
    service_5 = create_service(
        service_name="Service 5", active=False
    )  # not active is excluded
    services = [service_1, service_3, service_5]

    for service in services:
        template = create_template(service)
        for _ in range(0, 3):
            create_notification(template, status=NotificationStatus.PERMANENT_FAILURE)
            create_notification(template, status=NotificationStatus.DELIVERED)
            create_notification(template, status=NotificationStatus.SENDING)
            create_notification(template, status=NotificationStatus.TEMPORARY_FAILURE)

    service_6 = create_service(service_name="Service 6")
    with freeze_time("2019-11-30 15:00:00.000000"):
        template_6 = create_template(service_6)
        for _ in range(0, 4):
            create_notification(
                template_6,
                status=NotificationStatus.PERMANENT_FAILURE,
            )  # notifications too old are excluded

    service_2 = create_service(service_name="Service 2")
    template_2 = create_template(service_2)
    for _ in range(0, 4):
        create_notification(
            template_2,
            status=NotificationStatus.PERMANENT_FAILURE,
            key_type=KeyType.TEST,
        )  # test key type is excluded
    create_notification(
        template_2,
        status=NotificationStatus.PERMANENT_FAILURE,
    )  # below threshold is excluded

    start_date = utc_now() - timedelta(days=1)
    end_date = utc_now()

    result = dao_find_services_with_high_failure_rates(
        start_date, end_date, threshold=3
    )
    print(result)
    assert len(result) == 1
    assert str(result[0].service_id) == fake_uuid
    assert result[0].permanent_failure_rate == 0.25


def test_get_live_services_with_organization(sample_organization):
    trial_service = create_service(service_name="trial service", restricted=True)
    live_service = create_service(service_name="count as live")
    live_service_diff_org = create_service(service_name="live service different org")
    dont_count_as_live = create_service(
        service_name="dont count as live", count_as_live=False
    )
    inactive_service = create_service(service_name="inactive", active=False)
    service_without_org = create_service(service_name="no org")
    another_org = create_organization(
        name="different org",
    )

    dao_add_service_to_organization(trial_service, sample_organization.id)
    dao_add_service_to_organization(live_service, sample_organization.id)
    dao_add_service_to_organization(dont_count_as_live, sample_organization.id)
    dao_add_service_to_organization(inactive_service, sample_organization.id)
    dao_add_service_to_organization(live_service_diff_org, another_org.id)

    services = get_live_services_with_organization()
    assert len(services) == 3
    assert ([(x.service_name, x.organization_name) for x in services]) == [
        (live_service_diff_org.name, another_org.name),
        (live_service.name, sample_organization.name),
        (service_without_org.name, None),
    ]


_this_date = utc_now() - timedelta(days=4)


@pytest.mark.parametrize(
    ["data", "start_date", "days", "end_date", "expected", "is_error"],
    [
        [None, _this_date, None, None, None, True],
        [None, _this_date, 4, _this_date - timedelta(4), None, True],
        [
            [
                {"day": _this_date, "something": "else"},
                {"day": _this_date, "something": "new"},
                {"day": _this_date + timedelta(days=1), "something": "borrowed"},
                {"day": _this_date + timedelta(days=2), "something": "old"},
                {"day": _this_date + timedelta(days=4), "something": "blue"},
            ],
            _this_date,
            4,
            None,
            {
                _this_date.date().strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 2,
                        StatisticsType.PENDING: 2,
                    },
                },
                (_this_date.date() + timedelta(days=1)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 1,
                        StatisticsType.PENDING: 0,
                    },
                },
                (_this_date.date() + timedelta(days=2)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 1,
                        StatisticsType.PENDING: 0,
                    },
                },
                (_this_date.date() + timedelta(days=3)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                },
                (_this_date.date() + timedelta(days=4)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 1,
                        StatisticsType.PENDING: 0,
                    },
                },
            },
            False,
        ],
        [
            [
                {"day": _this_date, "something": "else"},
                {"day": _this_date, "something": "new"},
                {"day": _this_date + timedelta(days=1), "something": "borrowed"},
                {"day": _this_date + timedelta(days=2), "something": "old"},
                {"day": _this_date + timedelta(days=4), "something": "blue"},
            ],
            _this_date,
            None,
            _this_date + timedelta(4),
            {
                _this_date.date().strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 2,
                        StatisticsType.PENDING: 2,
                    },
                },
                (_this_date.date() + timedelta(days=1)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 1,
                        StatisticsType.PENDING: 0,
                    },
                },
                (_this_date.date() + timedelta(days=2)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 1,
                        StatisticsType.PENDING: 0,
                    },
                },
                (_this_date.date() + timedelta(days=3)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                },
                (_this_date.date() + timedelta(days=4)).strftime("%Y-%m-%d"): {
                    TemplateType.EMAIL: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 0,
                        StatisticsType.PENDING: 0,
                    },
                    TemplateType.SMS: {
                        StatisticsType.DELIVERED: 0,
                        StatisticsType.FAILURE: 0,
                        StatisticsType.REQUESTED: 1,
                        StatisticsType.PENDING: 0,
                    },
                },
            },
            False,
        ],
    ],
)
def test_get_specific_days(data, start_date, days, end_date, expected, is_error):
    if is_error:
        with pytest.raises(ValueError):
            get_specific_days_stats(data, start_date, days, end_date)
    else:
        new_data = []
        for line in data:
            new_line = Mock()
            new_line.day = line["day"]
            new_line.notification_type = NotificationType.SMS
            new_line.count = 1
            new_line.something = line["something"]
            new_data.append(new_line)

        total_notifications = None

        date_key = _this_date.date().strftime("%Y-%m-%d")
        if expected and date_key in expected:
            sms_stats = expected[date_key].get(TemplateType.SMS, {})
            requested = sms_stats.get(StatisticsType.REQUESTED, 0)
            if requested > 0:
                total_notifications = {_this_date: requested}

        results = get_specific_days_stats(
            new_data,
            start_date,
            days,
            end_date,
            total_notifications=total_notifications,
        )
        assert results == expected


@patch("app.dao.services_dao.get_midnight_in_utc")
@patch("app.dao.services_dao.db.session.execute")
def test_dao_fetch_stats_for_service_from_hours(mock_execute, mock_get_midnight):
    service_id = "service-xyz"
    start = datetime(2025, 7, 1, 15, 30)
    end = datetime(2025, 7, 1, 18, 45)

    def _mock_midnight(dt):
        return datetime(dt.year, dt.month, dt.day)

    mock_get_midnight.side_effect = _mock_midnight
    total_result_mock = MagicMock()
    total_result_mock.all.return_value = [
        MagicMock(hour=datetime(2025, 7, 1, 16), total_notifications=100),
        MagicMock(hour=datetime(2025, 7, 1, 17), total_notifications=50),
    ]
    detail_result_mock = MagicMock()
    detail_result_mock.all.return_value = [
        MagicMock(
            notification_type="email",
            status="delivered",
            hour=datetime(2025, 7, 1, 16),
            count=60,
        ),
        MagicMock(
            notification_type="sms",
            status="failed",
            hour=datetime(2025, 7, 1, 17),
            count=20,
        ),
    ]
    mock_execute.side_effect = [total_result_mock, detail_result_mock]
    total_notifications, data = dao_fetch_stats_for_service_from_hours(
        service_id, start, end
    )
    assert total_notifications == {
        datetime(2025, 7, 1, 16): 100,
        datetime(2025, 7, 1, 17): 50,
    }
    assert len(data) == 2
    assert data[0].notification_type == "email"
    assert data[0].status == "delivered"
    assert data[0].hour == datetime(2025, 7, 1, 16)
    assert data[0].count == 60

    assert data[1].notification_type == "sms"
    assert data[1].status == "failed"
    assert data[1].hour == datetime(2025, 7, 1, 17)
    assert data[1].count == 20

    assert mock_execute.call_count == 2
