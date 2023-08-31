"""

Revision ID: 0347_add_dvla_volumes_template
Revises: 0346_notify_number_sms_sender
Create Date: 2021-02-15 15:36:34.654275

"""
import os
from datetime import datetime

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = "0347_add_dvla_volumes_template"
down_revision = "0346_notify_number_sms_sender"

email_template_id = "11fad854-fd38-4a7c-bd17-805fb13dfc12"
environment = os.environ["NOTIFY_ENVIRONMENT"]


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
            "((total_volume)) letters (((total_sheets)) sheets) sent via Notify are coming in today''s batch. These include: ",
            "",
            "((first_class_volume)) first class letters (((first_class_sheets)) sheets).",
            "((second_class_volume)) second class letters (((second_class_sheets)) sheets).",
            "((international_volume)) international letters (((international_sheets)) sheets).",
            "",
            "Thanks",
            "",
            "GOV.​UK Notify team",
            "https://www.gov.uk/notify",
        ]
    )

    email_template_name = "Notify daily letter volumes"
    email_template_subject = "Notify letter volume for ((date)): ((total_volume)) letters, ((total_sheets)) sheets"

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


def downgrade():
    conn = op.get_bind()
    input_params = {"template_id": email_template_id}
    if environment not in ["live", "production"]:
        conn.execute(
            text("DELETE FROM notifications WHERE template_id = :template_id"),
            input_params,
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
        conn.execute(
            text("DELETE FROM templates WHERE id = :template_id"), input_params
        )
