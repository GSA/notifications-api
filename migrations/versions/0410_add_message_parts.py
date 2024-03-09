"""

Revision ID: 0410_add_message_parts
Revises: 0409_fix_service_name

"""
import sqlalchemy as sa
from alembic import op
from flask import current_app

down_revision = "0409_fix_service_name"
revision = "0410_add_message_parts"


def upgrade():
    op.execute("ALTER TABLE notifications ADD COLUMN message_parts integer")


def downgrade():
    op.execute("ALTER TABLE notifications DROP COLUMN message_parts integer")
