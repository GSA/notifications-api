"""

Revision ID: 0336_broadcast_msg_content_2
Revises: 0335_broadcast_msg_content
Create Date: 2020-12-04 15:06:22.544803

"""
from alembic import op
import sqlalchemy as sa
from notifications_utils.template import BroadcastMessageTemplate
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm.session import Session


revision = '0336_broadcast_msg_content_2'
down_revision = '0335_broadcast_msg_content'


def upgrade():
    pass


def downgrade():
    pass
