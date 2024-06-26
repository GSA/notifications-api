"""

Revision ID: 0390_drop_dvla_provider
Revises: 0389_no_more_letters
Create Date: 2023-02-28 14:25:50.751952

"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0390_drop_dvla_provider"
down_revision = "0389_no_more_letters"


def upgrade():
    # based on migration 0066, but without provider_rates
    op.execute("DELETE FROM provider_details_history where display_name = 'DVLA'")
    op.execute("DELETE FROM provider_details where display_name = 'DVLA'")
    # ### end Alembic commands ###


def downgrade():
    # migration 0066 in reverse
    provider_id = str(uuid.uuid4())
    input_params = {"provider_id": provider_id}
    conn = op.get_bind()
    conn.execute(
        text(
            "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active, version) values (:provider_id, 'DVLA', 'dvla', 50, 'letter', true, 1)"
        ),
        input_params,
    )
    conn.execute(
        text(
            "INSERT INTO provider_details_history (id, display_name, identifier, priority, notification_type, active, version) values (:provider_id, 'DVLA', 'dvla', 50, 'letter', true, 1)"
        ),
        input_params,
    )
    # ### end Alembic commands ###
