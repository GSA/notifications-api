"""

Revision ID: 0367_add_reach
Revises: 0366_letter_rates_2022
Create Date: 2022-03-24 16:00:00

"""
import itertools
import uuid
from datetime import datetime

from alembic import op
from sqlalchemy.sql import text


revision = '0367_add_reach'
down_revision = '0366_letter_rates_2022'


def upgrade():
    conn = op.get_bind()
    input_params = {
        "id": uuid.uuid4()
    }
    conn.execute(text(
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
        """), input_params
    )


def downgrade():
    conn = op.get_bind()
    conn.execute("DELETE FROM provider_details WHERE identifier = 'reach'")
