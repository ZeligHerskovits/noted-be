"""Auto-generated migration: Add duration field to sessions table

Revision ID: adddurat_sessio_153201
Revises: adddssba_sessio_153119
Create Date: 20250820_153201

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'adddurat_sessio_153201'
down_revision = 'adddssba_sessio_153119'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add duration field to sessions table"""
    op.add_column('sessions', sa.Column('duration', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove duration field from sessions table"""
    op.drop_column('sessions', 'duration')
