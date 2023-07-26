"""

Revision ID: 0391_update_sms_numbers
Revises: 0390_drop_dvla_provider.py
Create Date: 2023-03-01 12:36:38.226954

"""
from alembic import op
from flask import current_app
import sqlalchemy as sa
from sqlalchemy import text

revision = '0391_update_sms_numbers'
down_revision = '0390_drop_dvla_provider.py'
OLD_SMS_NUMBER = "18446120782"
NEW_SMS_NUMBER = current_app.config['NOTIFY_INTERNATIONAL_SMS_SENDER'].strip('+')


def upgrade():
    conn = op.get_bind()
    op.alter_column("service_sms_senders", "sms_sender", type_=sa.types.String(length=255))
    op.alter_column("inbound_numbers", "number", type_=sa.types.String(length=255))
    input_params = {
        "new_sms_plus": f"+{NEW_SMS_NUMBER}",
        "old_sms_number": OLD_SMS_NUMBER,
        "new_sms_number": NEW_SMS_NUMBER
    }
    conn.execute(text("UPDATE service_sms_senders SET sms_sender = :new_sms_plus "
                      "WHERE sms_sender IN (:old_sms_number, :new_sms_number)"), input_params)
    conn.execute(text("UPDATE inbound_numbers SET number = :new_sms_plus "
                      "WHERE number IN (:old_sms_number, :new_sms_number)"), input_params)


def downgrade():
    conn = op.get_bind()
    input_params = {
        "old_sms_number": OLD_SMS_NUMBER,
        "new_sms_plus": f"+{NEW_SMS_NUMBER}"
    }
    conn.execute(text("UPDATE service_sms_senders SET sms_sender = :old_sms_number "
                      "WHERE sms_sender = :new_sms_plus"), input_params)
    conn.execute(text("UPDATE inbound_numbers SET number = :old_sms_number "
                      "WHERE number = :new_sms_plus"), input_params)
    op.alter_column("service_sms_senders", "sms_sender", type_=sa.types.String(length=11))
    op.alter_column("inbound_numbers", "number", type_=sa.types.String(length=11))
