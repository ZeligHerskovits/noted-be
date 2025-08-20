"""Auto-generated migration: Rename column appt_datee to appt_date in sessions table

Revision ID: renameap_sessio_151322
Revises: renameap_sessio_151047
Create Date: 20250820_151322

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'renameap_sessio_151322'
down_revision = 'renameap_sessio_151047'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Rename column appt_datee to appt_date in sessions table"""
    op.alter_column('sessions', 'appt_datee', new_column_name='appt_date')

def downgrade() -> None:
    """Rename column appt_date back to appt_datee in sessions table"""
    op.alter_column('sessions', 'appt_date', new_column_name='appt_datee')
