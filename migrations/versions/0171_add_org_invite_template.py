"""

Revision ID: 0171_add_org_invite_template
Revises: 0170_hidden_non_nullable
Create Date: 2018-02-16 14:16:43.618062

"""

from datetime import datetime

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = "0171_add_org_invite_template"
down_revision = "0170_hidden_non_nullable"


template_id = "203566f0-d835-47c5-aa06-932439c86573"


def upgrade():
    template_insert = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject,
        created_by_id, version, process_type, hidden)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False,
        :notify_service_id, :subject, :user_id, 1, :process_type, false)
    """
    template_history_insert = """
        INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject,
        created_by_id, version, process_type, hidden)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False,
        :notify_service_id, :subject, :user_id, 1, :process_type, false)
    """

    template_content = "\n".join(
        [
            "((user_name)) has invited you to collaborate on ((organisation_name)) on GOV.UK Notify.",
            "",
            "GOV.UK Notify makes it easy to keep people updated by helping you send text messages, emails and letters.",
            "",
            "Open this link to create an account on GOV.UK Notify:",
            "((url))",
            "",
            "This invitation will stop working at midnight tomorrow. This is to keep ((organisation_name)) secure.",
        ]
    )

    template_name = "Notify organisation invitation email"
    template_subject = "((user_name)) has invited you to collaborate on ((organisation_name)) on GOV.UK Notify"

    input_params = {
        "template_id": template_id,
        "template_name": template_name,
        "template_type": "email",
        "time_now": datetime.utcnow(),
        "content": template_content,
        "notify_service_id": current_app.config["NOTIFY_SERVICE_ID"],
        "subject": template_subject,
        "user_id": current_app.config["NOTIFY_USER_ID"],
        "process_type": "normal",
    }
    conn = op.get_bind()
    conn.execute(text(template_history_insert), input_params)

    conn.execute(text(template_insert), input_params)

    # clean up constraints on org_to_service - service_id-org_id constraint is redundant
    op.drop_constraint(
        "organisation_to_service_service_id_organisation_id_key",
        "organisation_to_service",
        type_="unique",
    )


def downgrade():
    input_params = {"template_id": template_id}
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
    op.create_unique_constraint(
        "organisation_to_service_service_id_organisation_id_key",
        "organisation_to_service",
        ["service_id", "organisation_id"],
    )
