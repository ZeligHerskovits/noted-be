"""Auto-generated migration: Add program_name field to sessions table

Revision ID: addprogr_sessio_153003
Revises: addnosho_sessio_152641
Create Date: 20250820_153003

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addprogr_sessio_153003'
down_revision = 'addnosho_sessio_152641'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add program_name field to sessions table"""
    op.add_column('sessions', sa.Column('program_name', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove program_name field from sessions table"""
    op.drop_column('sessions', 'program_name')
