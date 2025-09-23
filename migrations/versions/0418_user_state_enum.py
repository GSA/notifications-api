"""

Revision ID: 0418_user_state_enum
Revises: 0417_change_total_message_limit
Create Date: 2025-08-28 12:34:32.857422

"""

revision = "0418_user_state_enum"
down_revision = "0417_change_total_message_limit"

from contextlib import contextmanager
from enum import Enum
from typing import Iterator, TypedDict

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.enums import (
    UserState,
)


class EnumValues(TypedDict):
    values: list[str]
    name: str


_enum_params: dict[Enum, EnumValues] = {
    UserState: {
        "values": ["active", "inactive", "pending"],
        "name": "user_states",
    },
}


def enum_create(values: list[str], name: str) -> None:
    enum_db_type = postgresql.ENUM(*values, name=name)
    enum_db_type.create(op.get_bind())


def enum_drop(values: list[str], name: str) -> None:
    enum_db_type = postgresql.ENUM(*values, name=name)
    enum_db_type.drop(op.get_bind())


def enum_using(column_name: str, enum: Enum) -> str:
    return f"{column_name}::text::{_enum_params[enum]['name']}"


def enum_type(enum: Enum) -> sa.Enum:
    return sa.Enum(
        *_enum_params[enum]["values"],
        name=_enum_params[enum]["name"],
        values_callable=(lambda x: [e.value for e in x]),
    )


@contextmanager
def view_handler() -> Iterator[None]:
    op.execute("DROP VIEW notifications_all_time_view")

    yield

    op.execute(
        """
        CREATE VIEW notifications_all_time_view AS
        (
            SELECT
                id,
                job_id,
                job_row_number,
                service_id,
                template_id,
                template_version,
                api_key_id,
                key_type,
                billable_units,
                notification_type,
                created_at,
                sent_at,
                sent_by,
                updated_at,
                notification_status,
                reference,
                client_reference,
                international,
                phone_prefix,
                rate_multiplier,
                created_by_id,
                document_download_count
            FROM notifications
        ) UNION
        (
            SELECT
                id,
                job_id,
                job_row_number,
                service_id,
                template_id,
                template_version,
                api_key_id,
                key_type,
                billable_units,
                notification_type,
                created_at,
                sent_at,
                sent_by,
                updated_at,
                notification_status,
                reference,
                client_reference,
                international,
                phone_prefix,
                rate_multiplier,
                created_by_id,
                document_download_count
            FROM notification_history
        )
    """
    )


def upgrade():
    with view_handler():

        for enum_data in _enum_params.values():
            enum_create(**enum_data)

        # alter existing columns to use new enums
        op.alter_column(
            "users",
            "state",
            existing_type=sa.VARCHAR(length=255),
            type_=enum_type(UserState),
            existing_nullable=True,
            postgresql_using=enum_using("state", UserState),
        )


def downgrade():
    with view_handler():
        # Create old enum types.
        # Alter columns back

        op.alter_column(
            "users",
            "state",
            existing_type=enum_type(UserState),
            type_=sa.VARCHAR(length=255),
            existing_nullable=True,
        )

        for enum_data in _enum_params.values():
            enum_drop(**enum_data)
