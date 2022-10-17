"""

Revision ID: 0379_remove_crown
Revises: 0378_add_org_names
Create Date: 2022-10-17 17:05:07.193377

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0379_remove_crown'
down_revision = '0378_add_org_names'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('letter_rates', 'crown')
    op.drop_column('organisation', 'crown')
    op.drop_column('organisation_types', 'is_crown')
    op.drop_column('services', 'crown')
    op.drop_column('services_history', 'crown')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('services_history', sa.Column('crown', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.add_column('services', sa.Column('crown', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.add_column('organisation_types', sa.Column('is_crown', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.add_column('organisation', sa.Column('crown', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.add_column('letter_rates', sa.Column('crown', sa.BOOLEAN(), autoincrement=False, nullable=False))
    # ### end Alembic commands ###
