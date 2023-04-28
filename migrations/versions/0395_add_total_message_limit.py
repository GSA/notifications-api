"""

Revision ID: d2db89558026
Revises: 0394_remove_contact_list
Create Date: 2023-04-24 11:35:22.873930

"""
from alembic import op
import sqlalchemy as sa


revision = '0395_add_total_message_limit'
down_revision = '0394_remove_contact_list'


def upgrade():
    op.add_column('services', sa.Column('total_message_limit', sa.Integer))
    op.add_column('services_history', sa.Column('total_message_limit', sa.Integer))


def downgrade():
    op.drop_column('services', 'total_message_limit')
    op.drop_column('services_history', 'total_message_limit')
