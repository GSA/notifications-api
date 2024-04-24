"""empty message

Revision ID: 0094_job_stats_update
Revises: 0092_add_inbound_provider
Create Date: 2017-06-06 14:37:30.051647

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0094_job_stats_update"
down_revision = "0092_add_inbound_provider"


def upgrade():
    op.add_column("job_statistics", sa.Column("sent", sa.BigInteger(), nullable=True))
    op.add_column(
        "job_statistics", sa.Column("delivered", sa.BigInteger(), nullable=True)
    )
    op.add_column("job_statistics", sa.Column("failed", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("job_statistics", "sent")
    op.drop_column("job_statistics", "failed")
    op.drop_column("job_statistics", "delivered")
