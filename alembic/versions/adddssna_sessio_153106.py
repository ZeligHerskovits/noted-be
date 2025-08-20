"""Auto-generated migration: Add dss___name field to sessions table

Revision ID: adddssna_sessio_153106
Revises: addstaff_sessio_153054
Create Date: 20250820_153106

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'adddssna_sessio_153106'
down_revision = 'addstaff_sessio_153054'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add dss___name field to sessions table"""
    op.add_column('sessions', sa.Column('dss___name', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove dss___name field from sessions table"""
    op.drop_column('sessions', 'dss___name')
