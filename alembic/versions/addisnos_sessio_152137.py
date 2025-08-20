"""Auto-generated migration: Add is_no_show field to sessions table

Revision ID: addisnos_sessio_152137
Revises: renameap_sessio_151322
Create Date: 20250820_152137

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addisnos_sessio_152137'
down_revision = 'renameap_sessio_151322'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add is_no_show field to sessions table"""
    op.add_column('sessions', sa.Column('is_no_show', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove is_no_show field from sessions table"""
    op.drop_column('sessions', 'is_no_show')
