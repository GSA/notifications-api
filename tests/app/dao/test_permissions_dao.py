from app.dao import DAOClass
from app.dao.permissions_dao import permission_dao
from app.enums import PermissionType
from tests.app.db import create_service


def test_get_permissions_by_user_id_returns_all_permissions(sample_service):
    permissions = permission_dao.get_permissions_by_user_id(
        user_id=sample_service.users[0].id
    )
    assert len(permissions) == 7
    assert sorted(
        [
            PermissionType.MANAGE_USERS,
            PermissionType.MANAGE_TEMPLATES,
            PermissionType.MANAGE_SETTINGS,
            PermissionType.SEND_TEXTS,
            PermissionType.SEND_EMAILS,
            PermissionType.MANAGE_API_KEYS,
            PermissionType.VIEW_ACTIVITY,
        ]
    ) == sorted([i.permission for i in permissions])


def test_get_permissions_by_user_id_returns_only_active_service(sample_user):
    active_service = create_service(user=sample_user, service_name="Active service")
    inactive_service = create_service(
        user=sample_user, service_name="Inactive service", active=False
    )

    permissions = permission_dao.get_permissions_by_user_id(user_id=sample_user.id)
    assert len(permissions) == 7
    assert active_service in [i.service for i in permissions]
    assert inactive_service not in [i.service for i in permissions]


def test_dao_class(sample_user):
    create_service(user=sample_user, service_name="Active service")
    create_service(user=sample_user, service_name="Inactive service", active=False)

    permissions_orig = permission_dao.get_permissions_by_user_id(user_id=sample_user.id)
    assert len(permissions_orig) == 7
    dao = DAOClass()

    for permission in permissions_orig:
        dao.delete_instance(permission, True)
    permissions = permission_dao.get_permissions_by_user_id(user_id=sample_user.id)
    assert len(permissions) == 0
