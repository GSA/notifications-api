"""

Revision ID: 0323_broadcast_message
Revises: 0322_broadcast_service_perm
Create Date: 2020-07-02 11:59:38.734650

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import column, func
from sqlalchemy.dialects import postgresql

revision = '0323_broadcast_message'
down_revision = '0322_broadcast_service_perm'


STATUSES = [
    'draft',
    'pending-approval',
    'rejected',
    'broadcasting',
    'completed',
    'cancelled',
    'technical-failure',
]


def upgrade():
    pass


def downgrade():
    pass
