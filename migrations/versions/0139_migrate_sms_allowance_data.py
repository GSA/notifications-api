"""

Revision ID: 0139_migrate_sms_allowance_data.py
Revises: 0138_sms_sender_nullable.py
Create Date: 2017-11-10 21:42:59.715203

"""
from datetime import datetime
from alembic import op
import uuid

from sqlalchemy import text

from app.dao.date_util import get_current_calendar_year_start_year


revision = '0139_migrate_sms_allowance_data'
down_revision = '0138_sms_sender_nullable'


def upgrade():
    current_year = get_current_calendar_year_start_year()
    default_limit = 250000

    # Step 1: update the column free_sms_fragment_limit in service table if it is empty
    update_service_table = """
        UPDATE services SET free_sms_fragment_limit = :default_limit where free_sms_fragment_limit is null
    """
    input_params = {
        "default_limit": default_limit
    }
    conn = op.get_bind()
    conn.execute(text(update_service_table), input_params)

    # Step 2: insert at least one row for every service in current year if none exist for that service
    input_params = {
        "current_year": current_year,
        "default_limit": default_limit,
        "time_now": datetime.utcnow()
    }
    insert_row_if_not_exist = """
        INSERT INTO annual_billing 
        (id, service_id, financial_year_start, free_sms_fragment_limit, created_at, updated_at) 
         SELECT uuid_in(md5(random()::text)::cstring), id, :current_year, :default_limit, :time_now, :time_now 
         FROM services WHERE id NOT IN 
        (select service_id from annual_billing)
    """
    conn.execute(text(insert_row_if_not_exist), input_params)

    # Step 3: copy the free_sms_fragment_limit data from the services table across to annual_billing table.
    update_sms_allowance = """
        UPDATE annual_billing SET free_sms_fragment_limit = services.free_sms_fragment_limit
        FROM services
        WHERE annual_billing.service_id = services.id
    """
    op.execute(update_sms_allowance)


def downgrade():
    # There is no schema change. Only data migration and filling in gaps.
    print('There is no action for downgrading to the previous version.')