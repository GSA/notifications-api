"""

Revision ID: 0294_add_verify_reply_to
Revises: 0293_drop_complaint_fk
Create Date: 2019-05-22 16:58:52.929661

"""

from datetime import datetime

from alembic import op
from flask import current_app
from sqlalchemy import text

from app.utils import utc_now

revision = "0294_add_verify_reply_to"
down_revision = "0293_drop_complaint_fk"

email_template_id = "a42f1d17-9404-46d5-a647-d013bdfca3e1"


def upgrade():
    template_insert = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject,
        created_by_id, version, process_type, hidden)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False, :notify_service_id,
        :subject, :user_id, 1, :process_type, false)
    """
    template_history_insert = """
        INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject,
        created_by_id, version, process_type, hidden)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False, :notify_service_id,
        :subject, :user_id, 1, :process_type, false)

    """

    email_template_content = "\n".join(
        [
            "Hi,",
            "",
            "This address has been provided as a reply-to email address for a GOV.​UK Notify account.",
            "Any replies from users to emails they receive through GOV.​UK Notify will come back to this email address.",
            "",
            "This is just a quick check to make sure the address is valid.",
            "",
            "No need to reply.",
            "",
            "Thanks",
            "",
            "GOV.​UK Notify team",
            "https://www.gov.uk/notify",
        ]
    )

    email_template_name = "Verify email reply-to address for a service"
    email_template_subject = "Your GOV.UK Notify reply-to email address"

    input_params = {
        "template_id": email_template_id,
        "template_name": email_template_name,
        "template_type": "email",
        "time_now": utc_now(),
        "content": email_template_content,
        "notify_service_id": current_app.config["NOTIFY_SERVICE_ID"],
        "subject": email_template_subject,
        "user_id": current_app.config["NOTIFY_USER_ID"],
        "process_type": "normal",
    }
    conn = op.get_bind()
    conn.execute(text(template_history_insert), input_params)

    conn.execute(text(template_insert), input_params)


def downgrade():
    conn = op.get_bind()
    input_params = {"template_id": email_template_id}
    conn.execute(
        text("DELETE FROM notifications WHERE template_id = :template_id"), input_params
    )
    conn.execute(
        text("DELETE FROM notification_history WHERE template_id = :template_id"),
        input_params,
    )
    conn.execute(
        text("DELETE FROM template_redacted WHERE template_id = :template_id"),
        input_params,
    )
    conn.execute(
        text("DELETE FROM templates_history WHERE id = :template_id"), input_params
    )
    conn.execute(text("DELETE FROM templates WHERE id = :template_id"), input_params)
