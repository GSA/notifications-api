import datetime
import os
import uuid

import sqlalchemy as sa
from alembic import op

from app import db
from app.dao.users_dao import get_user_by_email
from app.models import User
from app.utils import utc_now
from app.enums import AuthType

revision = "0417_add_second_e2e_test_user"
down_revision = "0416_readd_e2e_test_user"


def upgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL_TWO")
    password = os.getenv("NOTIFY_E2E_TEST_PASSWORD_TWO")
    if not email_address or not password:
        raise ValueError("Required variables [NOTIFY_E2E_TEST_EMAIL_TWO] and [NOTIFY_E2E_TEST_PASSWORD_TWO] missing!")
    name = f"e2e_test_user_{uuid.uuid4()}"
    data = {
        "id": uuid.uuid4(),
        "name": name,
        "email_address": email_address,
        "password": password,
        "mobile_number": "+12025555555",
        "state": "active",
        "created_at": utc_now(),
        "password_changed_at": utc_now(),
        "failed_login_count": 0,
        "platform_admin": "f",
        "email_access_validated_at": utc_now(),
        "auth_type": AuthType.SMS,
    }
    conn = op.get_bind()
    insert_sql = """
        insert into users (id, name, email_address, _password, mobile_number, state, created_at, password_changed_at, failed_login_count, platform_admin, email_access_validated_at, auth_type)
        values (:id, :name, :email_address, :password, :mobile_number, :state, :created_at, :password_changed_at, :failed_login_count, :platform_admin, :email_access_validated_at, :auth_type)
        """
    conn.execute(sa.text(insert_sql), data)


def downgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL_TWO")
    user_to_delete = get_user_by_email(email_address)
    if not user_to_delete:
        return
    db.session.remove(user_to_delete)
    db.session.commit()
