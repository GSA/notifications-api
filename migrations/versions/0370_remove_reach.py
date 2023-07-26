"""

Revision ID: 0370_remove_reach
Revises: 0369_update_sms_rates
Create Date: 2022-04-27 16:00:00

"""
import itertools
import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text


revision = '0370_remove_reach'
down_revision = '0369_update_sms_rates'


def upgrade():
    conn = op.get_bind()
    conn.execute("DELETE FROM provider_details WHERE identifier = 'reach'")


def downgrade():
    conn = op.get_bind()
    input_params = {
        "id": str(uuid.uuid4()),
    }
    conn.execute(
        text(
        """
        INSERT INTO provider_details (
            id,
            display_name,
            identifier,
            priority,
            notification_type,
            active,
            version,
            created_by_id
        )
        VALUES (
            :id,
            'Reach',
            'reach',
            0,
            'sms',
            false,
            1,
            null
        )
        """), input_params)
