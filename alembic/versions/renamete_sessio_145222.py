"""Auto-generated migration: Rename column test_field to updated_test_field in sessions table

Revision ID: renamete_sessio_145222
Revises: addtestf_sessio_145156
Create Date: 20250820_145222

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'renamete_sessio_145222'
down_revision = 'addtestf_sessio_145156'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Rename column test_field to updated_test_field in sessions table"""
    op.alter_column('sessions', 'test_field', new_column_name='updated_test_field')

def downgrade() -> None:
    """Rename column updated_test_field back to test_field in sessions table"""
    op.alter_column('sessions', 'updated_test_field', new_column_name='test_field')
