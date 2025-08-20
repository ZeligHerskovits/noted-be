"""Auto-generated migration: Add no_show_action field to sessions table

Revision ID: addnosho_sessio_152641
Revises: addisnos_sessio_152137
Create Date: 20250820_152641

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addnosho_sessio_152641'
down_revision = 'addisnos_sessio_152137'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add no_show_action field to sessions table"""
    op.add_column('sessions', sa.Column('no_show_action', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove no_show_action field from sessions table"""
    op.drop_column('sessions', 'no_show_action')
