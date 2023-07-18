"""empty message

Revision ID: 0075_create_rates_table
Revises: 0074_update_sms_rate
Create Date: 2017-04-24 15:12:18.907629

"""

# revision identifiers, used by Alembic.
import uuid

from sqlalchemy import text

revision = '0075_create_rates_table'
down_revision = '0074_update_sms_rate'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    notification_types = postgresql.ENUM('email', 'sms', 'letter', name='notification_type', create_type=False)
    op.create_table('rates',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('valid_from', sa.DateTime(), nullable=False),
    sa.Column('rate', sa.Numeric(), nullable=False),
    sa.Column('notification_type', notification_types, nullable=False),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_index(op.f('ix_rates_notification_type'), 'rates', ['notification_type'], unique=False)

    conn = op.get_bind()
    input_params = {
        "id": uuid.uuid4()
    }
    conn.execute(text("INSERT INTO rates(id, valid_from, rate, notification_type) "
               "VALUES(:id, '2016-05-18 00:00:00', 1.65, 'sms')"), input_params)
    input_params = {
        "id": uuid.uuid4()
    }
    conn.execute(text("INSERT INTO rates(id, valid_from, rate, notification_type) "
               "VALUES(:id, '2017-04-01 00:00:00', 1.58, 'sms')"), input_params)


def downgrade():
    op.drop_index(op.f('ix_rates_notification_type'), table_name='rates')
    op.drop_table('rates')
