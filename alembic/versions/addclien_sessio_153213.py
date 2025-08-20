"""Auto-generated migration: Add client field to sessions table

Revision ID: addclien_sessio_153213
Revises: adddurat_sessio_153201
Create Date: 20250820_153213

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addclien_sessio_153213'
down_revision = 'adddurat_sessio_153201'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add client field to sessions table"""
    op.add_column('sessions', sa.Column('client', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove client field from sessions table"""
    op.drop_column('sessions', 'client')
