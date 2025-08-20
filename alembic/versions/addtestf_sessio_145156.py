"""Auto-generated migration: Add test_field field to sessions table

Revision ID: addtestf_sessio_145156
Revises: renameap_sessio_141913
Create Date: 20250820_145156

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addtestf_sessio_145156'
down_revision = 'renameap_sessio_141913'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add test_field field to sessions table"""
    op.add_column('sessions', sa.Column('test_field', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove test_field field from sessions table"""
    op.drop_column('sessions', 'test_field')
