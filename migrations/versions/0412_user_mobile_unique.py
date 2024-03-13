"""

Revision ID: 0412_user_mobile_unique
Revises: 0411_add_login_uuid

"""

from alembic import op


revision = "0412_user_mobile_unique"
down_revision = "0411_add_login_uuid"


def upgrade():
    # Note if you try to do this the sqlalchemy way, it will appear to work
    # when you run the migration, but the unique constraint will never be
    # applied.  Must use raw sql here.
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT UQ_mobile_number UNIQUE(mobile_number)"
    )


def downgrade():
    op.execute("ALTER TABLE users DROP CONSTRAINT UQ_mobile_number")
