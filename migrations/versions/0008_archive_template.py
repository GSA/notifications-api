"""empty message

Revision ID: 0008_archive_template
Revises: 0007_template_history
Create Date: 2016-04-25 14:16:49.787229

"""

# revision identifiers, used by Alembic.
revision = "0008_archive_template"
down_revision = "0007_template_history"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column("templates", sa.Column("archived", sa.Boolean(), nullable=True))
    op.add_column(
        "templates_history", sa.Column("archived", sa.Boolean(), nullable=True)
    )
    op.get_bind()
    op.execute("UPDATE templates SET archived = FALSE")
    op.execute("UPDATE templates_history set archived = FALSE")
    op.alter_column("templates", "archived", nullable=False)
    op.alter_column("templates", "archived", nullable=False)
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("templates_history", "archived")
    op.drop_column("templates", "archived")
    ### end Alembic commands ###
