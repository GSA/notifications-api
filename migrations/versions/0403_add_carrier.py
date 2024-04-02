"""

Revision ID: 0403_add_carrier
Revises: 0402_total_message_limit_default

"""

import sqlalchemy as sa
from alembic import op
from flask import current_app

down_revision = "0402_total_message_limit_default"
revision = "0403_add_carrier"


def upgrade():
    op.execute("ALTER TABLE notifications ADD COLUMN carrier text")
    op.execute("ALTER TABLE notification_history ADD COLUMN carrier text")


def downgrade():
    op.execute("ALTER TABLE notifications DROP COLUMN carrier text")
    op.execute("ALTER TABLE notification_history DROP COLUMN carrier text")
