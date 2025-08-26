"""Auto-generated migration: Add client__id field to sessions table

Revision ID: addclien_sessio_144829
Revises: addclien_sessio_153213
Create Date: 20250826_144829

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addclien_sessio_144829'
down_revision = 'addclien_sessio_153213'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add client__id field to sessions table"""
    op.add_column('sessions', sa.Column('client__id', sa.Text(), nullable=True))

def downgrade() -> None:
    """Remove client__id field from sessions table"""
    op.drop_column('sessions', 'client__id')
