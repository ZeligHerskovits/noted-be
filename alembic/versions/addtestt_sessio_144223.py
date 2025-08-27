"""Auto-generated migration: Add testt field to sessions table

Revision ID: addtestt_sessio_144223
Revises: addtest_sessio_143432
Create Date: 20250827_144223

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addtestt_sessio_144223'
down_revision = 'addtest_sessio_143432'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add testt field to sessions table"""
    op.add_column('sessions', sa.Column('testt', sa.Text(), nullable=True))

def downgrade() -> None:
    """Remove testt field from sessions table"""
    op.drop_column('sessions', 'testt')
