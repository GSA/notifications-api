"""

Revision ID: 0265_add_confirm_edit_templates
Revises: 0264_add_folder_permissions_perm
Create Date: 2019-02-26 15:16:53.268135

"""

from datetime import datetime

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = "0265_add_confirm_edit_templates"
down_revision = "0264_add_folder_permissions_perm"

email_template_id = "c73f1d71-4049-46d5-a647-d013bdeca3f0"
mobile_template_id = "8a31520f-4751-4789-8ea1-fe54496725eb"


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
            "Dear ((name)),",
            "",
            "((servicemanagername)) changed your Notify account email address to:",
            "",
            "((email address))",
            "",
            "You’ll need to use this email address next time you sign in.",
            "",
            "Thanks",
            "",
            "GOV.​UK Notify team",
            "https://www.gov.uk/notify",
        ]
    )

    email_template_name = "Email address changed by service manager"
    email_template_subject = "Your GOV.UK Notify email address has changed"

    input_params = {
        "template_id": email_template_id,
        "template_name": email_template_name,
        "template_type": "email",
        "time_now": datetime.utcnow(),
        "content": email_template_content,
        "notify_service_id": current_app.config["NOTIFY_SERVICE_ID"],
        "subject": email_template_subject,
        "user_id": current_app.config["NOTIFY_USER_ID"],
        "process_type": "normal",
    }
    conn = op.get_bind()

    conn.execute(text(template_history_insert), input_params)

    conn.execute(text(template_insert), input_params)

    mobile_template_content = """Your mobile number was changed by ((servicemanagername)). Next time you sign in, your US Notify authentication code will be sent to this phone."""

    mobile_template_name = "Phone number changed by service manager"

    input_params = {
        "template_id": mobile_template_id,
        "template_name": mobile_template_name,
        "template_type": "sms",
        "time_now": datetime.utcnow(),
        "content": mobile_template_content,
        "notify_service_id": current_app.config["NOTIFY_SERVICE_ID"],
        "subject": None,
        "user_id": current_app.config["NOTIFY_USER_ID"],
        "process_type": "normal",
    }

    conn.execute(text(template_history_insert), input_params)

    conn.execute(text(template_insert), input_params)


def downgrade():
    input_params = {"template_id": email_template_id}
    conn = op.get_bind()

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

    input_params = {"template_id": mobile_template_id}
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
