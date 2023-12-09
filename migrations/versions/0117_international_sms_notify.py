"""empty message

Revision ID: 0117_international_sms_notify
Revises: 0115_add_inbound_numbers
Create Date: 2017-08-29 14:09:41.042061

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = "0117_international_sms_notify"
down_revision = "0115_add_inbound_numbers"

from datetime import datetime

from alembic import op

NOTIFY_SERVICE_ID = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"


def upgrade():
    input_params = {
        "notify_service_id": NOTIFY_SERVICE_ID,
        "datetime_now": datetime.utcnow(),
    }
    conn = op.get_bind()
    conn.execute(
        text(
            "INSERT INTO service_permissions VALUES (:notify_service_id, 'international_sms', :datetime_now)"
        ),
        input_params,
    )


def downgrade():
    input_params = {
        "notify_service_id": NOTIFY_SERVICE_ID,
    }
    conn = op.get_bind()
    conn.execute(
        text(
            "DELETE FROM service_permissions WHERE service_id = :notify_service_id AND permission = 'international_sms'"
        ),
        input_params,
    )
