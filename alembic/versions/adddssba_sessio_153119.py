"""Auto-generated migration: Add dss___ba field to sessions table

Revision ID: adddssba_sessio_153119
Revises: adddssna_sessio_153106
Create Date: 20250820_153119

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'adddssba_sessio_153119'
down_revision = 'adddssna_sessio_153106'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add dss___ba field to sessions table"""
    op.add_column('sessions', sa.Column('dss___ba', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove dss___ba field from sessions table"""
    op.drop_column('sessions', 'dss___ba')
