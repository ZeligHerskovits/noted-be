"""Auto-generated migration: Rename column appt_date to appt_datee in sessions table

Revision ID: renameap_sessio_151047
Revises: renamete_sessio_145222
Create Date: 20250820_151047

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'renameap_sessio_151047'
down_revision = 'renamete_sessio_145222'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Rename column appt_date to appt_datee in sessions table"""
    op.alter_column('sessions', 'appt_date', new_column_name='appt_datee')

def downgrade() -> None:
    """Rename column appt_datee back to appt_date in sessions table"""
    op.alter_column('sessions', 'appt_datee', new_column_name='appt_date')
