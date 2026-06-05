"""

Revision ID: 0298_add_mou_signed_receipt
Revises: 0297_template_redacted_fix
Create Date: 2019-05-22 16:58:52.929661

"""

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = "0298_add_mou_signed_receipt"
down_revision = "0297_template_redacted_fix"


templates = [
    {
        "id": "4fd2e43c-309b-4e50-8fb8-1955852d9d71",
        "name": "MOU Signed By Receipt",
        "type": "email",
        "subject": "You’ve accepted the GOV.​UK Notify data sharing and financial agreement",
        "content_lines": [
            "Hi ((signed_by_name)),",
            "",
            "((org_name)) has accepted the GOV.​UK Notify data sharing and financial agreement. ",
            "",
            "If you need another copy of the agreement you can download it here: ((mou_link))",
            "",
            "If you need to add Cabinet Office as a supplier, here are the details you need:",
            "",
            "TO BE ADDED MANUALLY",
            "",
            "Thanks,",
            "GOV.​UK Notify team",
            "",
            "https://www.gov.uk/notify",
        ],
    },
    {
        "id": "c20206d5-bf03-4002-9a90-37d5032d9e84",
        "name": "MOU Signed On Behalf Of Receipt - Signed by",
        "type": "email",
        "subject": "You’ve accepted the GOV.​UK Notify data sharing and financial agreement",
        "content_lines": [
            "Hi ((signed_by_name)),",
            "",
            "((org_name)) has accepted the GOV.​UK Notify data sharing and financial agreement. We’ve emailed ((on_behalf_of_name)) to let them know too.",
            "",
            "If you need another copy of the agreement you can download it here: ((mou_link))",
            "",
            "If you need to add Cabinet Office as a supplier, here are the details you need:",
            "",
            "TO BE ADDED MANUALLY",
            "",
            "Thanks,",
            "GOV.​UK Notify team",
            "",
            "https://www.gov.uk/notify",
        ],
    },
    {
        "id": "522b6657-5ca5-4368-a294-6b527703bd0b",
        "name": "MOU Signed On Behalf Of Receipt - On Behalf Of",
        "type": "email",
        "subject": "((org_name)) has accepted the GOV.​UK Notify data sharing and financial agreement",
        "content_lines": [
            "Hi ((on_behalf_of_name)),",
            "",
            "((signed_by_name)) has accepted the GOV.​UK Notify data sharing and financial agreement on your behalf, for ((org_name)).",
            "",
            "GOV.​UK Notify lets teams in the public sector send emails, text messages and letters. It’s built and run by a team in the Government Digital Service (part of Cabinet Office).",
            "",
            "If you need another copy of the agreement you can download it here: ((mou_link))",
            "",
            "If you need to add Cabinet Office as a supplier, here are the details you need.",
            "",
            "TO BE ADDED MANUALLY",
            "",
            "Thanks,",
            "GOV.​UK Notify team",
            "",
            "https://www.gov.uk/notify",
        ],
    },
    {
        "id": "d0e66c4c-0c50-43f0-94f5-f85b613202d4",
        "name": "MOU Signed Notify Team Alert",
        "type": "email",
        "subject": "Someone signed an MOU for an org on Notify",
        "content_lines": [
            "What’s up Notifiers,",
            "",
            "((signed_by_name)) just accepted the data sharing and financial agreement for ((org_name)).",
            "",
            "See how ((org_name)) is using Notify here: ((org_dashboard_link))",
        ],
    },
]


def upgrade():
    insert_t = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject,
        created_by_id, version, process_type, hidden)
        VALUES (:template_id, :template_name, :template_type, current_timestamp,
        :content, False, :notify_service_id, :subject, :user_id, 1, :process_type, false)
    """
    insert_th = """
            INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject,
            created_by_id, version, process_type, hidden)
        VALUES (:template_id, :template_name, :template_type, current_timestamp,
        :content, False, :notify_service_id, :subject, :user_id, 1, :process_type, false)

        """

    for template in templates:
        input_params = {
            "template_id": template["id"],
            "template_name": template["name"],
            "template_type": template["type"],
            "content": "\n".join(template["content_lines"]),
            "notify_service_id": current_app.config["NOTIFY_SERVICE_ID"],
            "subject": template.get("subject"),
            "user_id": current_app.config["NOTIFY_USER_ID"],
            "process_type": "normal",
        }
        conn = op.get_bind()

        conn.execute(text(insert_t), input_params)

        conn.execute(text(insert_th), input_params)

        input_params = {
            "template_id": template["id"],
            "user_id": current_app.config["NOTIFY_USER_ID"],
        }
        conn.execute(
            text("""
            INSERT INTO template_redacted
            (
                template_id,
                redact_personalisation,
                updated_at,
                updated_by_id
            ) VALUES ( :template_id, false, current_timestamp, :user_id )
            """),
            input_params,
        )


def downgrade():
    conn = op.get_bind()
    for template in templates:
        input_params = {"template_id": template["id"]}
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
            text("DELETE FROM templates WHERE id = :template_id"), input_params
        )
        conn.execute(
            text("DELETE FROM templates_history WHERE id = :template_id"), input_params
        )
