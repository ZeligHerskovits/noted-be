"""Auto-generated migration: Add test field to sessions table

Revision ID: addtest_sessio_143432
Revises: addclien_sessio_144829
Create Date: 20250827_143432

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addtest_sessio_143432'
down_revision = 'addclien_sessio_144829'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add test field to sessions table"""
    op.add_column('sessions', sa.Column('test', sa.Text(), nullable=True))

def downgrade() -> None:
    """Remove test field from sessions table"""
    op.drop_column('sessions', 'test')
