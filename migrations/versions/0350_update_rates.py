"""

Revision ID: 0350_update_rates
Revises: 0349_add_ft_processing_time
Create Date: 2021-04-01 08:00:24.775338

"""
import uuid

from alembic import op
from sqlalchemy import text

revision = '0350_update_rates'
down_revision = '0349_add_ft_processing_time'


def upgrade():
    conn = op.get_bind()
    input_params = {
        "id": uuid.uuid4()
    }
    conn.execute(text("INSERT INTO rates(id, valid_from, rate, notification_type) "
               "VALUES(:id, '2021-03-31 23:00:00', 0.0160, 'sms')"), input_params)


def downgrade():
    pass
