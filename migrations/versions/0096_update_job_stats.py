"""empty message

Revision ID: 0096_update_job_stats
Revises: 0095_migrate_existing_svc_perms
Create Date: 2017-06-08 15:46:49.637642

"""

# revision identifiers, used by Alembic.
revision = "0096_update_job_stats"
down_revision = "0095_migrate_existing_svc_perms"

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


def upgrade():
    query = text("""
        UPDATE job_statistics
        SET sent = sms_sent + emails_sent + letters_sent,
        delivered = sms_delivered + emails_delivered,
        failed = sms_failed + emails_failed + letters_failed
    """)

    conn = op.get_bind()
    conn.execute(query)


def downgrade():
    query = text("""
        UPDATE job_statistics
        SET sent = 0,
        delivered = 0,
        failed = 0
    """)

    conn = op.get_bind()
    conn.execute(query)
