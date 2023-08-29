"""empty message

Revision ID: 0103_add_historical_redact
Revises: db6d9d9f06bc
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = "0103_add_historical_redact"
down_revision = "db6d9d9f06bc"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from flask import current_app


def upgrade():
    conn = op.get_bind()
    input_params = {"notify_user_id": current_app.config["NOTIFY_USER_ID"]}
    conn.execute(
        text(
            """
        INSERT INTO template_redacted
        (
            template_id,
            redact_personalisation,
            updated_at,
            updated_by_id
        )
        SELECT
            templates.id,
            false,
            now(),
            :notify_user_id
        FROM
            templates
        LEFT JOIN template_redacted on template_redacted.template_id = templates.id
        WHERE template_redacted.template_id IS NULL
        """
        ),
        input_params,
    )


def downgrade():
    # data migration, no downloads
    pass
