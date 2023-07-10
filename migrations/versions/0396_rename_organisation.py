"""

Revision ID: d2db89558026
Revises: 0395_add_total_message_limit
Create Date: 2023-04-27 14:59:39.428607

"""
from alembic import op
import sqlalchemy as sa


revision = '0396_rename_organisation'
down_revision = '0395_remove_intl_letters_perm'


def upgrade():
    op.execute('ALTER TABLE services RENAME COLUMN organisation_type to organization_type')
    op.execute('ALTER TABLE services_history RENAME COLUMN organisation_type to organization_type')
    op.execute('ALTER TABLE services RENAME COLUMN organisation_id to organization_id')
    op.execute('ALTER TABLE services_history RENAME COLUMN organisation_id to organization_id')
    op.execute('ALTER TABLE domain RENAME COLUMN organisation_id to organization_id')
    op.execute('ALTER TABLE user_to_organisation RENAME to user_to_organization')
    op.execute('ALTER TABLE invited_organisation_users RENAME to invited_organization_users')
    op.execute('ALTER TABLE user_to_organization RENAME COLUMN organisation_id to organization_id')
    op.execute('ALTER TABLE invited_organization_users RENAME COLUMN organisation_id to organization_id')
    op.execute('ALTER TABLE organisation RENAME COLUMN organisation_type to organization_type')
    op.execute('ALTER TABLE organisation RENAME to organization')


def downgrade():
    pass
