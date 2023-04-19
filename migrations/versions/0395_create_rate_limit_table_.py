"""

Revision ID: 0395_create_rate_limit_table
Revises: 0394_remove_contact_list
Create Date: 2023-04-19 08:19:28.598206

"""
from alembic import op
import sqlalchemy as sa


revision = '0395_create_rate_limit_table'
down_revision = '0394_remove_contact_list'


def upgrade():
    op.create_table(
        "service_rate_limit",
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('service_id', sa.String, nullable=False),
        sa.Column('timestamp', sa.Integer, nullable=False)
    )


def downgrade():
    op.drop_table("service_rate_limit")
