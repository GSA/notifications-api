"""

Revision ID: 0404_expire_invites
Revises: 0403_add_carrier
Create Date: 2023-11-10 15:52:07.348485

"""
from re import I
from alembic import op
import sqlalchemy as sa


revision = "0404_expire_invites"
down_revision = "0403_add_carrier"


def upgrade():
    op.execute("insert into invite_status_type values ('expired')")


def downgrade():
    op.execute("delete from invite_status_type where name = 'expired'")
