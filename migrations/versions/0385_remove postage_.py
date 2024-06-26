"""

Revision ID: 0385_remove postage_
Revises: 0384_remove_letter_branding_
Create Date: 2023-02-10 12:20:39.411493

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0385_remove_postage_"
down_revision = "0384_remove_letter_branding_"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint("ft_billing_pkey", "ft_billing", type_="primary")
    op.create_primary_key(
        "ft_billing_pkey",
        "ft_billing",
        [
            "local_date",
            "template_id",
            "service_id",
            "notification_type",
            "provider",
            "rate_multiplier",
            "international",
            "rate",
        ],
    )

    # we need to replace the entire notifications_all_time_view in order to update it
    op.execute("DROP VIEW notifications_all_time_view;")
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

    op.drop_column("notification_history", "postage")
    op.drop_column("notifications", "postage")
    op.drop_column("templates", "postage")
    op.drop_column("templates_history", "postage")
    op.drop_column("ft_billing", "postage")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "ft_billing",
        sa.Column("postage", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "templates_history",
        sa.Column("postage", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "templates",
        sa.Column("postage", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("postage", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "notification_history",
        sa.Column("postage", sa.VARCHAR(), autoincrement=False, nullable=True),
    )

    op.drop_constraint("ft_billing_pkey", "ft_billing", type_="primary")
    op.create_primary_key(
        "ft_billing_pkey",
        "ft_billing",
        [
            "local_date",
            "template_id",
            "service_id",
            "notification_type",
            "provider",
            "rate_multiplier",
            "international",
            "rate",
            "postage",
        ],
    )

    op.execute("DROP VIEW notifications_all_time_view;")
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
                postage,
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
                postage,
                created_by_id,
                document_download_count
            FROM notification_history
        )
    """
    )
    # ### end Alembic commands ###
