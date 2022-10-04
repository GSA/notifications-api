"""

Revision ID: 0332_broadcast_provider_msg
Revises: 0331_add_broadcast_org
Create Date: 2020-10-26 16:28:11.917468

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0332_broadcast_provider_msg'
down_revision = '0331_add_broadcast_org'

STATUSES = [
    'technical-failure',
    'sending',
    'returned-ack',
    'returned-error',
]


def upgrade():

    pass


def downgrade():
    pass