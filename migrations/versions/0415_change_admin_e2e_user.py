import datetime
import os
import uuid

import sqlalchemy as sa
from alembic import op

from app import db
from app.dao.users_dao import get_user_by_email
from app.models import User
from app.utils import utc_now

revision = "0415_change_admin_e2e_user"
down_revision = "0414_change_total_message_limit"


def upgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL")
    conn = op.get_bind()
    update_sql = """
        UPDATE users SET platform_admin = 't' WHERE email_address = :email_address
        """
    conn.execute(sa.text(update_sql), {"email_address": email_address})


def downgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL")
    conn = op.get_bind()
    update_sql = """
        UPDATE users SET platform_admin = 'f' WHERE email_address = :email_address
        """
    conn.execute(sa.text(update_sql), {"email_address": email_address})
