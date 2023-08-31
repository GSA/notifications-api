"""empty message

Revision ID: 0058_add_letters_flag
Revises: 0056_minor_updates
Create Date: 2016-10-25 17:37:27.660723

"""

# revision identifiers, used by Alembic.
revision = "0058_add_letters_flag"
down_revision = "0056_minor_updates"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        "services",
        sa.Column(
            "can_send_letters", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "services_history",
        sa.Column(
            "can_send_letters", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade():
    op.drop_column("services_history", "can_send_letters")
    op.drop_column("services", "can_send_letters")
