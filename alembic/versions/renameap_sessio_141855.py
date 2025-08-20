"""Auto-generated migration: Rename column appt_date to appt_datee in sessions table

Revision ID: renameap_sessio_141855
Revises: renameap_sessio_141834
Create Date: 20250820_141855

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'renameap_sessio_141855'
down_revision = 'renameap_sessio_141834'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Rename column appt_date to appt_datee in sessions table"""
    op.alter_column('sessions', 'appt_date', new_column_name='appt_datee')

def downgrade() -> None:
    """Rename column appt_datee back to appt_date in sessions table"""
    op.alter_column('sessions', 'appt_datee', new_column_name='appt_date')
