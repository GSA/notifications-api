"""empty message

Revision ID: 0078_sent_notification_status
Revises: 0077_add_intl_notification
Create Date: 2017-04-24 16:55:20.731069

"""

# revision identifiers, used by Alembic.
revision = "0078_sent_notification_status"
down_revision = "0077_add_intl_notification"

from alembic import op
import sqlalchemy as sa

enum_name = "notify_status_type"
tmp_name = "tmp_" + enum_name

old_options = (
    "created",
    "sending",
    "delivered",
    "pending",
    "failed",
    "technical-failure",
    "temporary-failure",
    "permanent-failure",
)
new_options = old_options + ("sent",)

old_type = sa.Enum(*old_options, name=enum_name)
new_type = sa.Enum(*new_options, name=enum_name)

alter_str = "ALTER TABLE {table} ALTER COLUMN status TYPE {enum} USING status::text::notify_status_type "


def upgrade():
    op.execute("ALTER TYPE notify_status_type RENAME TO tmp_notify_status_type")

    new_type.create(op.get_bind())
    op.execute(
        "ALTER TABLE notifications ALTER COLUMN status TYPE notify_status_type USING status::text::notify_status_type"
    )
    op.execute(
        "ALTER TABLE notification_history ALTER COLUMN status TYPE notify_status_type USING status::text::notify_status_type"
    )

    op.execute("DROP TYPE tmp_notify_status_type")


def downgrade():
    op.execute("ALTER TYPE notify_status_type RENAME TO tmp_notify_status_type")

    op.execute("UPDATE notifications SET status='sending' where status='sent'")
    op.execute("UPDATE notification_history SET status='sending' where status='sent'")

    old_type.create(op.get_bind())

    op.execute(
        "ALTER TABLE notifications ALTER COLUMN status TYPE notify_status_type USING status::text::notify_status_type"
    )
    op.execute(
        "ALTER TABLE notification_history ALTER COLUMN status TYPE notify_status_type USING status::text::notify_status_type"
    )

    op.execute("DROP TYPE tmp_notify_status_type")
