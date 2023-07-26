"""

Revision ID: 0383_update_default_templates.py
Revises: 0381_encrypted_column_types
Create Date: 2023-01-10 11:42:25.633265

"""
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from flask import current_app

revision = '0383_update_default_templates.py'
down_revision = '0381_encrypted_column_types'


def upgrade():
    update_t = """
        UPDATE templates SET name = :name, template_type = :type, content = :content, subject = :subject
        WHERE id = :id
    """

    update_th = """
            UPDATE templates_history SET name = :name, template_type = :type, content = :content, subject = :subject
            WHERE id = :id
        """
    conn = op.get_bind()
    with open(current_app.config['CONFIG_FILES'] + '/templates.json') as f:
        data = json.load(f)
        for d in data:
            input_params = {
                'name': d['name'],
                'type': d['type'],
                'content': '\n'.join(d['content']),
                'subject': d.get('subject'),
                'id': d['id']
            }
            conn.execute(
                text(update_t), input_params
            )
            conn.execute(
                text(update_th), input_params
            )


def downgrade():
    # with associated code changes, edits to templates should no longer be made via migration.
    # instead, update the fixture and run the flask command to update.
    pass
