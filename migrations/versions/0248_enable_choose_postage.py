"""

Revision ID: 0248_enable_choose_postage
Revises: 0246_notifications_index
Create Date: 2018-12-14 12:09:31.375634

"""

import sqlalchemy as sa
from alembic import op

revision = "0248_enable_choose_postage"
down_revision = "0246_notifications_index"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute("INSERT INTO service_permission_types VALUES ('choose_postage')")
    op.add_column("templates", sa.Column("postage", sa.String(), nullable=True))
    op.add_column("templates_history", sa.Column("postage", sa.String(), nullable=True))
    op.execute(
        """
        ALTER TABLE templates ADD CONSTRAINT "chk_templates_postage_null"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage in ('first', 'second') OR
                postage is null
            ELSE
                postage is null
            END
        )
    """
    )
    op.execute(
        """
        ALTER TABLE templates_history ADD CONSTRAINT "chk_templates_history_postage_null"
        CHECK (
            CASE WHEN template_type = 'letter' THEN
                postage in ('first', 'second') OR
                postage is null
            ELSE
                postage is null
            END
        )
    """
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        "chk_templates_history_postage_null", "templates_history", type_="check"
    )
    op.drop_constraint("chk_templates_postage_null", "templates", type_="check")
    op.drop_column("templates_history", "postage")
    op.drop_column("templates", "postage")
    op.execute("DELETE FROM service_permissions WHERE permission = 'choose_postage'")
    op.execute("DELETE FROM service_permission_types WHERE name = 'choose_postage'")
    # ### end Alembic commands ###
