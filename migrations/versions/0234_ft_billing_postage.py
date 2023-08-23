"""

Revision ID: 0234_ft_billing_postage
Revises: 0232_noti_postage_constraint_3
Create Date: 2018-09-28 14:43:26.100884

"""
from alembic import op
import sqlalchemy as sa


revision = "0234_ft_billing_postage"
down_revision = "0232_noti_postage_constraint_3"


def upgrade():
    op.add_column("ft_billing", sa.Column("postage", sa.String(), nullable=True))
    op.execute(
        "UPDATE ft_billing SET postage = (CASE WHEN notification_type = 'letter' THEN 'second' ELSE 'none' END)"
    )


def downgrade():
    op.drop_column("ft_billing", "postage")
