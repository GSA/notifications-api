"""

Revision ID: 0416_readd_e2e_test_user
Revises: 0415_add_message_cost
Create Date: 2025-03-17 11:35:22.873930

"""

import datetime
import os
import uuid

import sqlalchemy as sa
from alembic import op

from app import db
from app.dao.users_dao import get_user_by_email
from app.enums import AuthType
from app.models import User
from app.utils import utc_now

revision = "0416_readd_e2e_test_user"
down_revision = "0415_add_message_cost"


def upgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL")
    password = os.getenv("NOTIFY_E2E_TEST_PASSWORD")
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

    # delete the old user because
    delete_sql = """
        delete from users where email_address='e2e-test-notify-user@fake.gov'
        """

    insert_sql = """
        insert into users (id, name, email_address, _password, mobile_number, state, created_at, password_changed_at, failed_login_count, platform_admin, email_access_validated_at, auth_type)
        values (:id, :name, :email_address, :password, :mobile_number, :state, :created_at, :password_changed_at, :failed_login_count, :platform_admin, :email_access_validated_at, :auth_type)
        """
    conn.execute(sa.text(delete_sql))

    conn.execute(sa.text(insert_sql), data)


def downgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL")
    user_to_delete = get_user_by_email(email_address)
    if not user_to_delete:
        return
    db.session.remove(user_to_delete)
    db.session.commit()
