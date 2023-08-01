"""

Revision ID: 0226_service_postage
Revises: 0224_returned_letter_status
Create Date: 2018-09-13 16:23:59.168877

"""
from alembic import op
import sqlalchemy as sa


revision = '0226_service_postage'
down_revision = '0224_returned_letter_status'


def upgrade():
    op.add_column('services', sa.Column('postage', sa.String(length=255), nullable=True))
    op.add_column('services_history', sa.Column('postage', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('services_history', 'postage')
    op.drop_column('services', 'postage')
