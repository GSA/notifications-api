import datetime
import os
import uuid

import sqlalchemy as sa
from alembic import op

# from app import db
# from app.dao.users_dao import get_user_by_email
# from app.models import User
from app.enums import AuthType
from app.utils import utc_now

revision = "0415_add_second_e2e_test_user"
down_revision = "0414_change_total_message_limit"


def upgrade():
    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL_TWO")
    password = os.getenv("NOTIFY_E2E_TEST_PASSWORD_TWO")

    # TODO remove
    email_address = f"{uuid.uuid4()}@fake.gov"
    password = f"{uuid.uuid4()}password"
    # end TODO

    if not email_address or not password:
        raise ValueError(
            "Required variables [NOTIFY_E2E_TEST_EMAIL_TWO] and [NOTIFY_E2E_TEST_PASSWORD_TWO] missing!"
        )
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
        "auth_type": AuthType.SMS,
        "email_access_validated_at": utc_now(),
    }
    conn = op.get_bind()
    insert_sql = """
        insert into users (id, name, email_address, _password, mobile_number, state, created_at, password_changed_at, failed_login_count, platform_admin, email_access_validated_at)
        values (:id, :name, :email_address, :password, :mobile_number, :state, :created_at, :password_changed_at, :failed_login_count, :platform_admin, :email_access_validated_at)
        """
    conn.execute(sa.text(insert_sql), data)


# def downgrade():
#    email_address = os.getenv("NOTIFY_E2E_TEST_EMAIL_TWO")
#    user_to_delete = get_user_by_email(email_address)
#    if not user_to_delete:
#        return
#    db.session.remove(user_to_delete)
#    db.session.commit()


if __name__ == "__main__":
    # Execute when the module is not initialized from an import statement.
    upgrade()
