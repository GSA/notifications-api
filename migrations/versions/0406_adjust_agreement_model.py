"""

Revision ID: eb7747053d5d
Revises: 0404_expire_invites
Create Date: 2023-11-17 15:39:45.470089

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0406_adjust_agreement_model"
down_revision = "0405_add_preferred_timezone"

agreement_type_name = "agreement_types"
agreement_type_options = ("MOU", "IAA")
agreement_types = sa.Enum(*agreement_type_options, name=agreement_type_name)

agreement_status_name = "agreement_statuses"
agreement_status_options = ("active", "expired")
agreement_statuses = sa.Enum(*agreement_status_options, name=agreement_status_name)


def upgrade():
    agreement_types.create(op.get_bind())
    op.execute(
        f"ALTER TABLE agreements ALTER COLUMN type TYPE {agreement_type_name} using type::text::{agreement_type_name}"
    )

    agreement_statuses.create(op.get_bind())
    op.execute(
        f"ALTER TABLE agreements ALTER COLUMN status TYPE {agreement_status_name} using status::text::{agreement_status_name}"
    )


def downgrade():
    op.alter_column(
        "agreements",
        "status",
        existing_type=agreement_statuses,
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.execute(f"DROP TYPE {agreement_status_name}")

    op.alter_column(
        "agreements",
        "type",
        existing_type=agreement_types,
        type_=sa.VARCHAR(length=3),
        existing_nullable=False,
    )
    op.execute(f"DROP TYPE {agreement_type_name}")
