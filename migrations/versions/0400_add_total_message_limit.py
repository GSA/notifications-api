"""

Revision ID: 0400_add_total_message_limit
Revises: 0399_remove_research_mode
Create Date: 2023-04-24 11:35:22.873930

"""
from alembic import op
import sqlalchemy as sa


revision = "0400_add_total_message_limit"
down_revision = "0399_remove_research_mode"


def upgrade():
    op.add_column("services", sa.Column("total_message_limit", sa.Integer))
    op.add_column("services_history", sa.Column("total_message_limit", sa.Integer))


def downgrade():
    op.drop_column("services", "total_message_limit")
    op.drop_column("services_history", "total_message_limit")
