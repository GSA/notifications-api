"""

Revision ID: 0400_add_total_message_limit
Revises: 0399_remove_research_mode
Create Date: 2023-04-24 11:35:22.873930

"""
import datetime
import os
import uuid

import sqlalchemy as sa
from alembic import op

from app import db
from app.dao.users_dao import get_user_by_email
from app.models import User

revision = "0401_add_e2e_test_user"
down_revision = "0400_add_total_message_limit"


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
        "created_at": datetime.datetime.utcnow(),
        "password_changed_at": datetime.datetime.utcnow(),
        "failed_login_count": 0,
        "platform_admin": "f",
        "email_access_validated_at": datetime.datetime.utcnow(),
    }
    conn = op.get_bind()
    insert_sql = """
        insert into users (id, name, email_address, _password, mobile_number, state, created_at, password_changed_at, failed_login_count, platform_admin, email_access_validated_at)
        values (:id, :name, :email_address, :password, :mobile_number, :state, :created_at, :password_changed_at, :failed_login_count, :platform_admin, :email_access_validated_at)
        """
    conn.execute(sa.text(insert_sql), data)


def downgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL")
    user_to_delete = get_user_by_email(email_address)
    if not user_to_delete:
        return
    db.session.remove(user_to_delete)
    db.session.commit()
