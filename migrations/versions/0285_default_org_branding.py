"""empty message

Revision ID: 0285_default_org_branding
Revises: 0284_0283_retry
Create Date: 2016-10-25 17:37:27.660723

"""

# revision identifiers, used by Alembic.
revision = "0285_default_org_branding"
down_revision = "0284_0283_retry"

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.execute("""UPDATE organisation SET email_branding_id = email_branding.id
    FROM email_branding
    WHERE email_branding.domain in (SELECT domain FROM domain WHERE domain.organisation_id = organisation.id)
    """)

    op.execute("""UPDATE organisation SET letter_branding_id = letter_branding.id
    FROM letter_branding
    WHERE letter_branding.domain in (SELECT domain FROM domain WHERE domain.organisation_id = organisation.id)
    """)


def downgrade():
    op.execute("""UPDATE organisation SET email_branding_id = null""")
    op.execute("""UPDATE organisation SET letter_branding_id = null""")
