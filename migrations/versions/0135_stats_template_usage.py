"""

Revision ID: 0135_stats_template_usage
Revises: 0134_add_email_2fa_template
Create Date: 2017-11-07 14:35:04.798561

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0135_stats_template_usage"
down_revision = "0134_add_email_2fa_template"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "stats_template_usage_by_month",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
        ),
        sa.PrimaryKeyConstraint("template_id", "month", "year"),
    )
    op.create_index(
        op.f("ix_stats_template_usage_by_month_month"),
        "stats_template_usage_by_month",
        ["month"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stats_template_usage_by_month_template_id"),
        "stats_template_usage_by_month",
        ["template_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_stats_template_usage_by_month_year"),
        "stats_template_usage_by_month",
        ["year"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_stats_template_usage_by_month_year"),
        table_name="stats_template_usage_by_month",
    )
    op.drop_index(
        op.f("ix_stats_template_usage_by_month_template_id"),
        table_name="stats_template_usage_by_month",
    )
    op.drop_index(
        op.f("ix_stats_template_usage_by_month_month"),
        table_name="stats_template_usage_by_month",
    )
    op.drop_table("stats_template_usage_by_month")
    # ### end Alembic commands ###
