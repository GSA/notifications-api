"""empty message

Revision ID: 0376_add_provider_response
Revises: 0375_fix_service_name
Create Date: 2022-09-14 11:04:15.888017

"""

# revision identifiers, used by Alembic.
from datetime import datetime

revision = "0376_add_provider_response"
down_revision = "0375_fix_service_name"

import sqlalchemy as sa
from alembic import op


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "notifications", sa.Column("provider_response", sa.Text(), nullable=True)
    )
    op.add_column("notifications", sa.Column("queue_name", sa.Text(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("notifications", "provider_response")
    op.drop_column("notifications", "queue_name")
    ### end Alembic commands ###
