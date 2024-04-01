"""

Revises: 0406_adjust_agreement_model

"""

from alembic import op

down_revision = "0406_adjust_agreement_model"
revision = "0407_fix_preferred_timezone"


def upgrade():
    op.execute(
        "update users set preferred_timezone='US/Eastern' where preferred_timezone=''"
    )


def downgrade():
    pass
