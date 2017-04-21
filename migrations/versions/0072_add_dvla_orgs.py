"""empty message

Revision ID: 0072_add_dvla_orgs
Revises: 0071_add_job_error_state
Create Date: 2017-04-19 15:25:45.155886

"""

# revision identifiers, used by Alembic.
revision = '0072_add_dvla_orgs'
down_revision = '0071_add_job_error_state'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('dvla_organisation',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # insert initial values - HMG and Land Reg
    op.execute("""
        INSERT INTO dvla_organisation VALUES
        ('001', 'HM Government'),
        ('500', 'Land Registry')
    """)

    op.add_column('services', sa.Column('dvla_organisation_id', sa.String(), nullable=True, server_default='001'))
    op.add_column('services_history', sa.Column('dvla_organisation_id', sa.String(), nullable=True, server_default='001'))

    # set everything to be HMG for now
    op.execute("UPDATE services SET dvla_organisation_id = '001'")
    op.execute("UPDATE services_history SET dvla_organisation_id = '001'")

    op.alter_column('services', 'dvla_organisation_id', nullable=False)
    op.alter_column('services_history', 'dvla_organisation_id', nullable=False)

    op.create_index(
        op.f('ix_services_dvla_organisation_id'),
        'services',
        ['dvla_organisation_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_services_history_dvla_organisation_id'),
        'services_history',
        ['dvla_organisation_id'],
        unique=False
    )

    op.create_foreign_key(None, 'services', 'dvla_organisation', ['dvla_organisation_id'], ['id'])

def downgrade():
    op.drop_column('services_history', 'dvla_organisation_id')
    op.drop_column('services', 'dvla_organisation_id')
    op.drop_table('dvla_organisation')
