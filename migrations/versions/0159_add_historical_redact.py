"""empty message

Revision ID: 0159_add_historical_redact
Revises: 0158_remove_rate_limit_default
Create Date: 2017-01-17 15:00:00.000000

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = "0159_add_historical_redact"
down_revision = "0158_remove_rate_limit_default"

import sqlalchemy as sa
from alembic import op
from flask import current_app
from sqlalchemy.dialects import postgresql


def upgrade():
    conn = op.get_bind()
    input_params = {"notify_user": current_app.config["NOTIFY_USER_ID"]}
    conn.execute(
        text("""
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
            :notify_user
        FROM
            templates
        LEFT JOIN template_redacted on template_redacted.template_id = templates.id
        WHERE template_redacted.template_id IS NULL
        """),
        input_params,
    )


def downgrade():
    pass
