"""

Revises: 0407_fix_preferred_timezone

"""

from alembic import op

down_revision = "0407_fix_preferred_timezone"
revision = "0408_fix_timezone_again"


def upgrade():
    op.execute(
        "update users set preferred_timezone='US/Eastern' where (preferred_timezone='') is not false"
    )


def downgrade():
    pass
