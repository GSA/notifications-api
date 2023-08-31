"""

Revision ID: 0205_service_callback_type
Revises: 0204_service_data_retention
Create Date: 2018-07-17 15:51:10.776698

"""
from alembic import op
import sqlalchemy as sa


revision = "0205_service_callback_type"
down_revision = "0204_service_data_retention"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "service_callback_type",
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.execute(
        "insert into service_callback_type values ('delivery_status'), ('complaint')"
    )
    op.add_column(
        "service_callback_api", sa.Column("callback_type", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "service_callback_api_type_fk",
        "service_callback_api",
        "service_callback_type",
        ["callback_type"],
        ["name"],
    )
    op.add_column(
        "service_callback_api_history",
        sa.Column("callback_type", sa.String(), nullable=True),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("service_callback_api_history", "callback_type")
    op.drop_constraint(
        "service_callback_api_type_fk", "service_callback_api", type_="foreignkey"
    )
    op.drop_column("service_callback_api", "callback_type")
    op.drop_table("service_callback_type")
    # ### end Alembic commands ###
