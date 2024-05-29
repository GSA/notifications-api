"""empty message

Revision ID: 0025_notify_service_data
Revises: 0024_add_research_mode_defaults
Create Date: 2016-06-01 14:17:01.963181

"""

import uuid

# revision identifiers, used by Alembic.
from datetime import datetime

from alembic import op
from sqlalchemy import text

from app.hashing import hashpw

revision = "0025_notify_service_data"
down_revision = "0024_add_research_mode_defaults"


user_id = "6af522d0-2915-4e52-83a3-3690455a5fe6"
service_id = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"


def upgrade():
    password = hashpw(str(uuid.uuid4()))
    conn = op.get_bind()
    user_insert = """INSERT INTO users (id, name, email_address, created_at, failed_login_count, _password, mobile_number, state, platform_admin)
                     VALUES (:user_id, 'Notify service user', 'testsender@dispostable.com', :time_now, 0,:password, '+441234123412', 'active', False)
                  """
    conn.execute(
        text(user_insert),
        {"user_id": user_id, "time_now": datetime.utcnow(), "password": password},
    )
    service_history_insert = """INSERT INTO services_history (id, name, created_at, active, message_limit, restricted, research_mode, email_from, created_by_id, reply_to_email_address, version)
                        VALUES (:service_id, 'Notify service', :time_now, True, 1000, False, False, 'testsender@dispostable.com',
                        :user_id, 'testsender@dispostable.com', 1)

                     """
    conn.execute(
        text(service_history_insert),
        {"service_id": service_id, "time_now": datetime.utcnow(), "user_id": user_id},
    )
    service_insert = """INSERT INTO services (id, name, created_at, active, message_limit, restricted, research_mode, email_from, created_by_id, reply_to_email_address, version)
                        VALUES (:service_id, 'Notify service', :time_now, True, 1000, False, False, 'testsender@dispostable.com',
                        :user_id, 'testsender@dispostable.com', 1)
                    """
    conn.execute(
        text(service_insert),
        {"service_id": service_id, "time_now": datetime.utcnow(), "user_id": user_id},
    )
    user_to_service_insert = """INSERT INTO user_to_service (user_id, service_id) VALUES (:user_id, :service_id)"""
    conn.execute(
        text(user_to_service_insert), {"user_id": user_id, "service_id": service_id}
    )

    template_history_insert = """INSERT INTO templates_history (id, name, template_type, created_at,
                                                                content, archived, service_id,
                                                                subject, created_by_id, version)
                                 VALUES (:template_id, :template_name, :template_type, :time_now,
                                 :content, False, :service_id, :subject, :user_id, 1)
                              """
    template_insert = """INSERT INTO templates (id, name, template_type, created_at,
                                                content, archived, service_id, subject, created_by_id, version)
                                 VALUES (:template_id, :template_name, :template_type, :time_now,
                                 :content, False, :service_id, :subject, :user_id, 1)
                              """
    email_verification_content = """Hi ((name)),\n\nTo complete your registration for GOV.UK Notify please click the link below\n\n((url))"""
    conn.execute(
        text(template_history_insert),
        {
            "template_id": uuid.uuid4(),
            "template_name": "Notify email verification code",
            "template_type": "email",
            "time_now": datetime.utcnow(),
            "content": email_verification_content,
            "service_id": service_id,
            "subject": "Confirm GOV.UK Notify registration",
            "user_id": user_id,
        },
    )
    conn.execute(
        text(template_insert),
        {
            "template_id": "ece42649-22a8-4d06-b87f-d52d5d3f0a27",
            "template_name": "Notify email verification code",
            "template_type": "email",
            "time_now": datetime.utcnow(),
            "content": email_verification_content,
            "service_id": service_id,
            "subject": "Confirm GOV.UK Notify registration",
            "user_id": user_id,
        },
    )

    invitation_subject = "((user_name)) has invited you to collaborate on ((service_name)) on GOV.UK Notify"
    invitation_content = """((user_name)) has invited you to collaborate on ((service_name)) on GOV.UK Notify.\n\n
        GOV.UK Notify makes it easy to keep people updated by helping you send text messages, emails and letters.\n\n
        Click this link to create an account on GOV.UK Notify:\n((url))\n\n
        This invitation will stop working at midnight tomorrow. This is to keep ((service_name)) secure.
        """
    conn.execute(
        text(template_history_insert),
        {
            "template_id": "4f46df42-f795-4cc4-83bb-65ca312f49cc",
            "template_name": "Notify invitation email",
            "template_type": "email",
            "time_now": datetime.utcnow(),
            "content": invitation_content,
            "service_id": service_id,
            "subject": invitation_subject,
            "user_id": user_id,
        },
    )
    conn.execute(
        text(template_insert),
        {
            "template_id": "4f46df42-f795-4cc4-83bb-65ca312f49cc",
            "template_name": "Notify invitation email",
            "template_type": "email",
            "time_now": datetime.utcnow(),
            "content": invitation_content,
            "service_id": service_id,
            "subject": invitation_subject,
            "user_id": user_id,
        },
    )

    sms_code_content = "((verify_code)) is your US Notify authentication code"
    conn.execute(
        text(template_history_insert),
        {
            "template_id": "36fb0730-6259-4da1-8a80-c8de22ad4246",
            "template_name": "Notify SMS verify code",
            "template_type": "sms",
            "time_now": datetime.utcnow(),
            "content": sms_code_content,
            "service_id": service_id,
            "subject": None,
            "user_id": user_id,
        },
    )

    conn.execute(
        text(template_insert),
        {
            "template_id": "36fb0730-6259-4da1-8a80-c8de22ad4246",
            "template_name": "Notify SMS verify code",
            "template_type": "sms",
            "time_now": datetime.utcnow(),
            "content": sms_code_content,
            "service_id": service_id,
            "subject": None,
            "user_id": user_id,
        },
    )

    password_reset_content = (
        "Hi ((user_name)),\n\n"
        "We received a request to reset your password on GOV.UK Notify.\n\n"
        "If you didn''t request this email, you can ignore it – "
        "your password has not been changed.\n\n"
        "To reset your password, click this link:\n\n"
        "((url))"
    )

    conn.execute(
        text(template_history_insert),
        {
            "template_id": "474e9242-823b-4f99-813d-ed392e7f1201",
            "template_name": "Notify password reset email",
            "template_type": "email",
            "time_now": datetime.utcnow(),
            "content": password_reset_content,
            "service_id": service_id,
            "subject": "Reset your GOV.UK Notify password",
            "user_id": user_id,
        },
    )

    conn.execute(
        text(template_insert),
        {
            "template_id": "474e9242-823b-4f99-813d-ed392e7f1201",
            "template_name": "Notify password reset email",
            "template_type": "email",
            "time_now": datetime.utcnow(),
            "content": password_reset_content,
            "service_id": service_id,
            "subject": "Reset your GOV.UK Notify password",
            "user_id": user_id,
        },
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        text("delete from templates where service_id = :service_id"),
        service_id=service_id,
    )
    conn.execute(
        text("delete from templates_history where service_id = :service_id"),
        service_id=service_id,
    )
    conn.execute(
        text("delete from user_to_service where service_id = :service_id"),
        service_id=service_id,
    )
    conn.execute(
        text("delete from services_history where id = :service_id"),
        service_id=service_id,
    )
    conn.execute(
        text("delete from services where id = :service_id"), service_id=service_id
    )
    conn.execute(
        text("delete from users where id = :service_id"), service_id=service_id
    )
