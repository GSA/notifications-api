"""

Revision ID: d2db89558026
Revises: 0395_add_total_message_limit
Create Date: 2023-04-27 14:59:39.428607

"""

import sqlalchemy as sa
from alembic import op

revision = "0396_rename_organisation"
down_revision = "0395_remove_intl_letters_perm"


def upgrade():
    op.execute(
        "ALTER TABLE services RENAME COLUMN organisation_type to organization_type"
    )
    op.execute(
        "ALTER TABLE services_history RENAME COLUMN organisation_type to organization_type"
    )
    op.execute("ALTER TABLE services RENAME COLUMN organisation_id to organization_id")
    op.execute(
        "ALTER TABLE services_history RENAME COLUMN organisation_id to organization_id"
    )
    op.execute("ALTER TABLE domain RENAME COLUMN organisation_id to organization_id")
    op.execute("ALTER TABLE user_to_organisation RENAME to user_to_organization")
    op.execute(
        "ALTER TABLE invited_organisation_users RENAME to invited_organization_users"
    )
    op.execute(
        "ALTER TABLE user_to_organization RENAME COLUMN organisation_id to organization_id"
    )
    op.execute(
        "ALTER TABLE invited_organization_users RENAME COLUMN organisation_id to organization_id"
    )
    op.execute(
        "ALTER TABLE organisation RENAME COLUMN organisation_type to organization_type"
    )
    op.execute("ALTER TABLE organisation RENAME to organization")
    op.drop_index(op.f("ix_organisation_name"), table_name="organization")
    op.create_index(op.f("ix_organization_name"), "organization", ["name"], unique=True)


def downgrade():
    op.execute(
        "ALTER TABLE services RENAME COLUMN organization_type to organisation_type"
    )
    op.execute(
        "ALTER TABLE services_history RENAME COLUMN organization_type to organisation_type"
    )
    op.execute("ALTER TABLE services RENAME COLUMN organization_id to organisation_id")
    op.execute(
        "ALTER TABLE services_history RENAME COLUMN organization_id to organisation_id"
    )
    op.execute("ALTER TABLE domain RENAME COLUMN organization_id to organisation_id")
    op.execute("ALTER TABLE user_to_organization RENAME to user_to_organisation")
    op.execute(
        "ALTER TABLE invited_organization_users RENAME to invited_organisation_users"
    )
    op.execute(
        "ALTER TABLE user_to_organisation RENAME COLUMN organization_id to organisation_id"
    )
    op.execute(
        "ALTER TABLE invited_organisation_users RENAME COLUMN organization_id to organisation_id"
    )
    op.execute(
        "ALTER TABLE organization RENAME COLUMN organization_type to organisation_type"
    )
    op.execute("ALTER TABLE organization RENAME to organisation")
    op.drop_index(op.f("ix_organization_name"), table_name="organisation")
    op.create_index(op.f("ix_organisation_name"), "organisation", ["name"], unique=True)
