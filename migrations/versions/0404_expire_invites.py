"""

Revision ID: 0404_expire_invites
Revises: 0403_add_carrier
Create Date: 2023-11-10 15:52:07.348485

"""

from re import I

import sqlalchemy as sa
from alembic import op

# Copied pattern for adjusting a enum as defined in 0359_more_permissions

revision = "0404_expire_invites"
down_revision = "0403_add_carrier"

enum_name = "invited_users_status_types"
tmp_name = "tmp_" + enum_name

old_options = ("pending", "accepted", "cancelled")
old_type = sa.Enum(*old_options, name=enum_name)


def upgrade():
    # ALTER TYPE must be run outside of a transaction block (see link below for details)
    # https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.migration.MigrationContext.autocommit_block
    pass
    # with op.get_context().autocommit_block():
    #    op.execute(f"ALTER TYPE {enum_name} ADD VALUE 'expired'")


def downgrade():
    op.execute(f"DELETE FROM invited_users WHERE status in ('expired')")

    op.execute(f"ALTER TYPE {enum_name} RENAME TO {tmp_name}")
    old_type.create(op.get_bind())
    op.execute(
        f"ALTER TABLE invited_users ALTER COLUMN status TYPE {enum_name} using status::text::{enum_name}"
    )
    op.execute(f"DROP TYPE {tmp_name}")
