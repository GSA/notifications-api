"""

Revision ID: 0412_add_message_parts
Revises: 0411_add_login_uuid

"""

import sqlalchemy as sa
from alembic import op
from flask import current_app

down_revision = "0411_add_login_uuid"
revision = "0412_add_message_parts"


def upgrade():
    op.execute("ALTER TABLE notifications ADD COLUMN message_parts integer")


def downgrade():
    op.execute("ALTER TABLE notifications DROP COLUMN message_parts integer")
