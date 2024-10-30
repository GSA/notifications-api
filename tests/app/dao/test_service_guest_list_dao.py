import uuid

from sqlalchemy import func, select

from app import db
from app.dao.service_guest_list_dao import (
    dao_add_and_commit_guest_list_contacts,
    dao_fetch_service_guest_list,
    dao_remove_service_guest_list,
)
from app.enums import RecipientType
from app.models import ServiceGuestList
from tests.app.db import create_service


def test_fetch_service_guest_list_gets_guest_lists(sample_service_guest_list):
    guest_list = dao_fetch_service_guest_list(sample_service_guest_list.service_id)
    assert len(guest_list) == 1
    assert guest_list[0].id == sample_service_guest_list.id


def test_fetch_service_guest_list_ignores_other_service(sample_service_guest_list):
    assert len(dao_fetch_service_guest_list(uuid.uuid4())) == 0


def test_add_and_commit_guest_list_contacts_saves_data(sample_service):
    guest_list = ServiceGuestList.from_string(
        sample_service.id, RecipientType.EMAIL, "foo@example.com"
    )

    dao_add_and_commit_guest_list_contacts([guest_list])

    stmt = select(ServiceGuestList)
    db_contents = db.session.execute(stmt).scalars().all()
    assert len(db_contents) == 1
    assert db_contents[0].id == guest_list.id


def test_remove_service_guest_list_only_removes_for_my_service(notify_db_session):
    service_1 = create_service(service_name="service 1")
    service_2 = create_service(service_name="service 2")
    dao_add_and_commit_guest_list_contacts(
        [
            ServiceGuestList.from_string(
                service_1.id, RecipientType.EMAIL, "service1@example.com"
            ),
            ServiceGuestList.from_string(
                service_2.id, RecipientType.EMAIL, "service2@example.com"
            ),
        ]
    )

    dao_remove_service_guest_list(service_1.id)

    assert service_1.guest_list == []
    assert len(service_2.guest_list) == 1


def test_remove_service_guest_list_does_not_commit(
    notify_db_session, sample_service_guest_list
):
    dao_remove_service_guest_list(sample_service_guest_list.service_id)

    # since dao_remove_service_guest_list doesn't commit, we can still rollback its changes
    notify_db_session.rollback()

    stmt = select(func.count()).select_from(ServiceGuestList)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 1
