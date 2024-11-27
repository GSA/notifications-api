import pytest
from flask import current_app
from app.utils import hilite
from sqlalchemy import func, select

from app import db
from app.dao.services_dao import dao_add_user_to_service, dao_fetch_active_users_for_service
from app.enums import NotificationType, TemplateType
from app.models import Notification
from app.service.sender import send_notification_to_service_users
from tests.app.db import create_service, create_template, create_user


@pytest.mark.parametrize(
    "notification_type", [NotificationType.EMAIL, NotificationType.SMS]
)
def test_send_notification_to_service_users_persists_notifications_correctly(
    notify_service, notification_type, sample_service, mocker
):
    mocker.patch("app.service.sender.send_notification_to_queue")

    template = create_template(sample_service, template_type=notification_type)
    send_notification_to_service_users(
        service_id=sample_service.id, template_id=template.id
    )

    notification = Notification.query.one()

    stmt = select(func.count()).select_from(Notification)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 1
    assert notification.to == "1"
    assert str(notification.service_id) == current_app.config["NOTIFY_SERVICE_ID"]
    assert notification.template.id == template.id
    assert notification.template.template_type == notification_type
    assert notification.notification_type == notification_type
    assert (
        notification.reply_to_text
        == notify_service.get_default_reply_to_email_address()
    )


def test_send_notification_to_service_users_sends_to_queue(
    notify_service, sample_service, mocker
):
    send_mock = mocker.patch("app.service.sender.send_notification_to_queue")

    template = create_template(sample_service, template_type=NotificationType.EMAIL)
    send_notification_to_service_users(
        service_id=sample_service.id, template_id=template.id
    )

    assert send_mock.called
    assert send_mock.call_count == 1


def test_send_notification_to_service_users_includes_user_fields_in_personalisation(
    notify_service, sample_service, mocker
):
    persist_mock = mocker.patch("app.service.sender.persist_notification")
    mocker.patch("app.service.sender.send_notification_to_queue")
    mocker.patch("app.service.sender.redis_store")

    user = sample_service.users[0]

    template = create_template(sample_service, template_type=TemplateType.EMAIL)
    send_notification_to_service_users(
        service_id=sample_service.id,
        template_id=template.id,
        include_user_fields=["name", "email_address", "state"],
    )

    persist_call = persist_mock.call_args_list[0][1]

    assert len(persist_mock.call_args_list) == 1
    assert persist_call["personalisation"] == {
        "name": user.name,
        "email_address": user.email_address,
        "state": user.state,
    }


def test_send_notification_to_service_users_sends_to_active_users_only(
    notify_service, mocker
):
    mocker.patch("app.service.sender.send_notification_to_queue")
    mocker.patch(
        "app.service.sender.redis_store",
    )

    first_active_user = create_user(email="foo@bar.com", state="active")
    second_active_user = create_user(email="foo1@bar.com", state="active")
    pending_user = create_user(email="foo2@bar.com", state="pending")
    service = create_service(user=first_active_user)
    print(hilite(f"CREATED THE SERVICE {service} with user {first_active_user}"))
    dao_add_user_to_service(service, second_active_user)
    print(hilite(f"ADDED user {second_active_user}"))

    dao_add_user_to_service(service, pending_user)
    print(hilite(f"ADDED PENDING USER {pending_user}"))

    active_users = dao_fetch_active_users_for_service(service.id)
    print(hilite(f"ACTIVE USERS IN THE TEST {active_users}"))
    template = create_template(service, template_type=TemplateType.EMAIL)

    send_notification_to_service_users(service_id=service.id, template_id=template.id)

    stmt = select(func.count()).select_from(Notification)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 2
