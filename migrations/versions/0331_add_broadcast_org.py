"""

Revision ID: 0331_add_broadcast_org
Revises: 0330_broadcast_invite_email
Create Date: 2020-09-23 10:11:01.094412

"""
from alembic import op
import sqlalchemy as sa
import os

revision = '0331_add_broadcast_org'
down_revision = '0330_broadcast_invite_email'

environment = os.environ['NOTIFY_ENVIRONMENT']

organisation_id = '38e4bf69-93b0-445d-acee-53ea53fe02df'


def upgrade():
    pass

def downgrade():
    pass
