"""

Revision ID: 0238_add_validation_failed
Revises: 0237_add_filename_to_dvla_org
Create Date: 2018-09-03 11:24:58.773824

"""
from alembic import op
import sqlalchemy as sa


revision = "0238_add_validation_failed"
down_revision = "0237_add_filename_to_dvla_org"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute(
        "INSERT INTO notification_status_types (name) VALUES ('validation-failed')"
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute(
        "UPDATE notifications SET notification_status = 'permanent-failure' WHERE notification_status = 'validation-failed'"
    )
    op.execute(
        "UPDATE notification_history SET notification_status = 'permanent-failure' WHERE notification_status = 'validation-failed'"
    )

    op.execute("DELETE FROM notification_status_types WHERE name = 'validation-failed'")
    # ### end Alembic commands ###
