"""

Revision ID: 0388_no_serv_letter_contact
Revises: 0387_remove_letter_perms_
Create Date: 2023-02-17 14:42:52.679425

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0388_no_serv_letter_contact"
down_revision = "0387_remove_letter_perms_"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        "ix_service_letter_contacts_service_id", table_name="service_letter_contacts"
    )
    op.drop_constraint(
        "templates_service_letter_contact_id_fkey", "templates", type_="foreignkey"
    )
    op.drop_column("templates", "service_letter_contact_id")
    op.drop_constraint(
        "templates_history_service_letter_contact_id_fkey",
        "templates_history",
        type_="foreignkey",
    )
    op.drop_column("templates_history", "service_letter_contact_id")
    op.drop_table("service_letter_contacts")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "templates_history",
        sa.Column(
            "service_letter_contact_id",
            postgresql.UUID(),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "templates_history_service_letter_contact_id_fkey",
        "templates_history",
        "service_letter_contacts",
        ["service_letter_contact_id"],
        ["id"],
    )
    op.add_column(
        "templates",
        sa.Column(
            "service_letter_contact_id",
            postgresql.UUID(),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "templates_service_letter_contact_id_fkey",
        "templates",
        "service_letter_contacts",
        ["service_letter_contact_id"],
        ["id"],
    )
    op.create_table(
        "service_letter_contacts",
        sa.Column("id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("service_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("contact_block", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column("is_default", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=False
        ),
        sa.Column(
            "updated_at", postgresql.TIMESTAMP(), autoincrement=False, nullable=True
        ),
        sa.Column(
            "archived",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="service_letter_contacts_service_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="service_letter_contacts_pkey"),
    )
    op.create_index(
        "ix_service_letter_contacts_service_id",
        "service_letter_contacts",
        ["service_id"],
        unique=False,
    )
    # ### end Alembic commands ###
