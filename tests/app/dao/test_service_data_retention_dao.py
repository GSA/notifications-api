import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db
from app.dao.service_data_retention_dao import (
    fetch_service_data_retention,
    fetch_service_data_retention_by_id,
    fetch_service_data_retention_by_notification_type,
    insert_service_data_retention,
    update_service_data_retention,
)
from app.enums import NotificationType
from app.models import ServiceDataRetention
from app.utils import utc_now
from tests.app.db import create_service, create_service_data_retention


def test_fetch_service_data_retention(sample_service):
    email_data_retention = insert_service_data_retention(
        sample_service.id,
        NotificationType.EMAIL,
        3,
    )
    sms_data_retention = insert_service_data_retention(
        sample_service.id,
        NotificationType.SMS,
        5,
    )

    list_of_data_retention = fetch_service_data_retention(sample_service.id)

    assert len(list_of_data_retention) == 2
    data_retentions = [email_data_retention, sms_data_retention]
    assert list_of_data_retention[0] in data_retentions
    assert list_of_data_retention[1] in data_retentions


def test_fetch_service_data_retention_only_returns_row_for_service(sample_service):
    another_service = create_service(service_name="Another service")
    email_data_retention = insert_service_data_retention(
        sample_service.id,
        NotificationType.EMAIL,
        3,
    )
    insert_service_data_retention(another_service.id, NotificationType.SMS, 5)

    list_of_data_retention = fetch_service_data_retention(sample_service.id)
    assert len(list_of_data_retention) == 1
    assert list_of_data_retention[0] == email_data_retention


def test_fetch_service_data_retention_returns_empty_list_when_no_rows_for_service(
    sample_service,
):
    empty_list = fetch_service_data_retention(sample_service.id)
    assert not empty_list


def test_fetch_service_data_retention_by_id(sample_service):
    email_data_retention = insert_service_data_retention(
        sample_service.id,
        NotificationType.EMAIL,
        3,
    )
    insert_service_data_retention(sample_service.id, NotificationType.SMS, 13)
    result = fetch_service_data_retention_by_id(
        sample_service.id, email_data_retention.id
    )
    assert result == email_data_retention


def test_fetch_service_data_retention_by_id_returns_none_if_not_found(sample_service):
    result = fetch_service_data_retention_by_id(sample_service.id, uuid.uuid4())
    assert not result


def test_fetch_service_data_retention_by_id_returns_none_if_id_not_for_service(
    sample_service,
):
    another_service = create_service(service_name="Another service")
    email_data_retention = insert_service_data_retention(
        sample_service.id,
        NotificationType.EMAIL,
        3,
    )
    result = fetch_service_data_retention_by_id(
        another_service.id, email_data_retention.id
    )
    assert not result


def test_insert_service_data_retention(sample_service):
    insert_service_data_retention(
        service_id=sample_service.id,
        notification_type=NotificationType.EMAIL,
        days_of_retention=3,
    )

    results = db.session.execute(select(ServiceDataRetention)).scalars().all()
    assert len(results) == 1
    assert results[0].service_id == sample_service.id
    assert results[0].notification_type == NotificationType.EMAIL
    assert results[0].days_of_retention == 3
    assert results[0].created_at.date() == utc_now().date()


def test_insert_service_data_retention_throws_unique_constraint(sample_service):
    insert_service_data_retention(
        service_id=sample_service.id,
        notification_type=NotificationType.EMAIL,
        days_of_retention=3,
    )
    with pytest.raises(expected_exception=IntegrityError):
        insert_service_data_retention(
            service_id=sample_service.id,
            notification_type=NotificationType.EMAIL,
            days_of_retention=5,
        )


def test_update_service_data_retention(sample_service):
    data_retention = insert_service_data_retention(
        service_id=sample_service.id,
        notification_type=NotificationType.SMS,
        days_of_retention=3,
    )
    updated_count = update_service_data_retention(
        service_data_retention_id=data_retention.id,
        service_id=sample_service.id,
        days_of_retention=5,
    )
    assert updated_count == 1
    results = db.session.execute(select(ServiceDataRetention)).scalars().all()
    assert len(results) == 1
    assert results[0].id == data_retention.id
    assert results[0].service_id == sample_service.id
    assert results[0].notification_type == NotificationType.SMS
    assert results[0].days_of_retention == 5
    assert results[0].created_at.date() == utc_now().date()
    assert results[0].updated_at.date() == utc_now().date()


def test_update_service_data_retention_does_not_update_if_row_does_not_exist(
    sample_service,
):
    updated_count = update_service_data_retention(
        service_data_retention_id=uuid.uuid4(),
        service_id=sample_service.id,
        days_of_retention=5,
    )
    assert updated_count == 0
    assert len(db.session.execute(select(ServiceDataRetention)).scalars().all()) == 0


def test_update_service_data_retention_does_not_update_row_if_data_retention_is_for_different_service(
    sample_service,
):
    data_retention = insert_service_data_retention(
        service_id=sample_service.id,
        notification_type=NotificationType.EMAIL,
        days_of_retention=3,
    )
    updated_count = update_service_data_retention(
        service_data_retention_id=data_retention.id,
        service_id=uuid.uuid4(),
        days_of_retention=5,
    )
    assert updated_count == 0


@pytest.mark.parametrize(
    "notification_type, alternate",
    [
        (NotificationType.SMS, NotificationType.EMAIL),
        (NotificationType.EMAIL, NotificationType.SMS),
    ],
)
def test_fetch_service_data_retention_by_notification_type(
    sample_service, notification_type, alternate
):
    data_retention = create_service_data_retention(
        service=sample_service, notification_type=notification_type
    )
    create_service_data_retention(service=sample_service, notification_type=alternate)
    result = fetch_service_data_retention_by_notification_type(
        sample_service.id, notification_type
    )
    assert result == data_retention


def test_fetch_service_data_retention_by_notification_type_returns_none_when_no_rows(
    sample_service,
):
    assert not fetch_service_data_retention_by_notification_type(
        sample_service.id,
        NotificationType.EMAIL,
    )
