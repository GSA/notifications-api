"""

Revision ID: 0402_total_message_limit_default
Revises: 0401_add_e2e_test_user
Create Date: 2023-09-18 10:04:58.957374

"""
from alembic import op
from flask import current_app
import sqlalchemy as sa


revision = "0402_total_message_limit_default"
down_revision = "0401_add_e2e_test_user"


def upgrade():
    # Set a default value for the total_message_limit column in the
    # services table to match the current TOTAL_MESSAGE_LIMIT app
    # config.
    op.execute(
        "UPDATE services SET total_message_limit = {total_message_limit} WHERE total_message_limit IS NULL".format(
            total_message_limit=current_app.config["TOTAL_MESSAGE_LIMIT"]
        )
    )


def downgrade():
    # There is no downgrade from this migration as it would cause a bug
    # in the app; if it needs to be removed, then you have to remove the
    # column added in migration 0400.
    pass
