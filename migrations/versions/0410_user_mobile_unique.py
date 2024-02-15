"""

Revision ID: 0410_user_mobile_unique
Revises: 0409_fix_service_name

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import column

revision = "0410_user_mobile_unique"
down_revision = "0409_fix_service_name"


def upgrade():
    # Note if you try to do this the sqlalchemy way, it will appear to work
    # when you run the migration, but the unique constraint will never be
    # applied.  Must use raw sql here.
    op.execute("ALTER TABLE users ADD CONSTRAINT UQ_mobile_number UNIQUE(mobile_number)")



def downgrade():
    op.execute("ALTER TABLE users DROP CONSTRAINT UQ_mobile_number")
