"""

Revision ID: 0405_add_preferred_timezone
Revises: 0404_expire_invites

"""

import sqlalchemy as sa
from alembic import op
from flask import current_app

down_revision = "0404_expire_invites"
revision = "0405_add_preferred_timezone"


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN preferred_timezone text")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN preferred_timezone text")
