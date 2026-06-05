"""empty message

Revision ID: 0130_service_email_reply_to_row
Revises: 0129_add_email_auth_permission
Create Date: 2017-08-29 14:09:41.042061

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = "0130_service_email_reply_to_row"
down_revision = "0129_add_email_auth_permission"

from alembic import op

NOTIFY_SERVICE_ID = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"
EMAIL_REPLY_TO_ID = "b3a58d57-2337-662a-4cba-40792a9322f2"


def upgrade():
    conn = op.get_bind()
    input_params = {
        "email_reply_to": EMAIL_REPLY_TO_ID,
        "notify_service_id": NOTIFY_SERVICE_ID,
    }
    conn.execute(
        text("""
        INSERT INTO service_email_reply_to
        (id, service_id, email_address, is_default, created_at)
        VALUES
        (:email_reply_to, :notify_service_id, 'testsender@dispostable.com', 'f', NOW())
    """),
        input_params,
    )


def downgrade():
    conn = op.get_bind()
    input_params = {
        "email_reply_to": EMAIL_REPLY_TO_ID,
    }
    conn.execute(
        text("""
        DELETE FROM service_email_reply_to
        WHERE id = :email_reply_to
    """),
        input_params,
    )
