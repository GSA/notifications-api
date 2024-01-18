import pytest

from app.dao.service_permissions_dao import (
    dao_fetch_service_permissions,
    dao_remove_service_permission,
)
from app.models import ServicePermissionType
from tests.app.db import create_service, create_service_permission


@pytest.fixture(scope="function")
def service_without_permissions(notify_db_session):
    return create_service(service_permissions=[])


def test_create_service_permission(service_without_permissions):
    service_permissions = create_service_permission(
        service_id=service_without_permissions.id, permission=ServicePermissionType.SMS
    )

    assert len(service_permissions) == 1
    assert service_permissions[0].service_id == service_without_permissions.id
    assert service_permissions[0].permission == ServicePermissionType.SMS


def test_fetch_service_permissions_gets_service_permissions(
    service_without_permissions,
):
    create_service_permission(
        service_id=service_without_permissions.id,
        permission=ServicePermissionType.INTERNATIONAL_SMS,
    )
    create_service_permission(
        service_id=service_without_permissions.id, permission=ServicePermissionType.SMS
    )

    service_permissions = dao_fetch_service_permissions(service_without_permissions.id)

    assert len(service_permissions) == 2
    assert all(
        sp.service_id == service_without_permissions.id for sp in service_permissions
    )
    assert all(
        sp.permission in {
            ServicePermissionType.INTERNATIONAL_SMS,
            ServicePermissionType.SMS,
        }
        for sp in service_permissions
    )


def test_remove_service_permission(service_without_permissions):
    create_service_permission(
        service_id=service_without_permissions.id,
        permission=ServicePermissionType.EMAIL,
    )
    create_service_permission(
        service_id=service_without_permissions.id,
        permission=ServicePermissionType.INBOUND_SMS,
    )

    dao_remove_service_permission(
        service_without_permissions.id,
        ServicePermissionType.EMAIL,
    )

    permissions = dao_fetch_service_permissions(service_without_permissions.id)
    assert len(permissions) == 1
    assert permissions[0].permission == ServicePermissionType.INBOUND_SMS
    assert permissions[0].service_id == service_without_permissions.id
