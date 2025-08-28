"""Auto-generated migration: Add testtest field to sessions table

Revision ID: addtestt_sessio_101504
Revises: addtestt_sessio_144223
Create Date: 20250828_101504

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addtestt_sessio_101504'
down_revision = 'addtestt_sessio_144223'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add testtest field to sessions table"""
    op.add_column('sessions', sa.Column('testtest', sa.Date(), nullable=True))

def downgrade() -> None:
    """Remove testtest field from sessions table"""
    op.drop_column('sessions', 'testtest')
