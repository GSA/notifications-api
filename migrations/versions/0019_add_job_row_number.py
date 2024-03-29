"""empty message

Revision ID: 0019_add_job_row_number
Revises: 0018_remove_subject_uniqueness
Create Date: 2016-05-18 15:04:24.513071

"""

# revision identifiers, used by Alembic.
revision = "0019_add_job_row_number"
down_revision = "0018_remove_subject_uniqueness"

import sqlalchemy as sa
from alembic import op


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "notifications", sa.Column("job_row_number", sa.Integer(), nullable=True)
    )
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("notifications", "job_row_number")
    ### end Alembic commands ###
