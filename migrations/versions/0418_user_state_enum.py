"""

Revision ID: 0418_user_state_enum
Revises: 0417_change_total_message_limit
Create Date: 2025-08-28 12:34:32.857422

"""

from contextlib import contextmanager
from enum import Enum
from re import I
from typing import Iterator, TypedDict

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.enums import (
    AuthType,
)

revision = "0410_enums_for_everything"
down_revision = "0409_fix_service_name"


user_state_enum = postgresql.ENUM(
    "active", "pending", "inactive", name="user_states", create_type=False
)


def upgrade():
    user_state_enum.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        "user",
        "state",
        existing_type=sa.String(),
        type_=user_state_enum,
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "user",
        "state",
        existing_type=user_state_enum,
        type_=sa.String,
        existing_nullable=False,
    )

    user_state_enum.drop(op.get_bind(), checkfirst=True)
