"""

Revision ID: 0383_update_default_templates.py
Revises: 0381_encrypted_column_types
Create Date: 2023-01-10 11:42:25.633265

"""
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from flask import current_app

revision = '0383_update_default_templates.py'
down_revision = '0381_encrypted_column_types'


def upgrade():
    update = """
        UPDATE {} SET name = '{}', template_type = '{}', content = '{}', subject = '{}'
        WHERE id = '{}'
    """

    with open(current_app.config['CONFIG_FILES'] + '/templates.json') as f:
        data = json.load(f)
        for d in data:
            for table_name in 'templates', 'templates_history':
                op.execute(
                    update.format(
                        table_name,
                        d['name'],
                        d['type'],
                        '\n'.join(d['content']),
                        d.get('subject'),
                        d['id']
                    )
                )

            # op.execute(
            #     """
            #     INSERT INTO template_redacted
            #     (
            #         template_id,
            #         redact_personalisation,
            #         updated_at,
            #         updated_by_id
            #     ) VALUES ( '{}', false, current_timestamp, '{}' )
            #     """.format(d['id'], current_app.config['NOTIFY_USER_ID'])
            # )
   

def downgrade():
    # with associated code changes, edits to templates should no longer be made via migration.
    # instead, update the fixture and run the flask command to update.
    pass
