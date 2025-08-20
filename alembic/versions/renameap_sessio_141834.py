"""Auto-generated migration: Rename column appt_datee to appt_date in sessions table

Revision ID: renameap_sessio_141834
Revises: 3c7694b9a164
Create Date: 20250820_141834

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'renameap_sessio_141834'
down_revision = '3c7694b9a164'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Rename column appt_datee to appt_date in sessions table"""
    op.alter_column('sessions', 'appt_datee', new_column_name='appt_date')

def downgrade() -> None:
    """Rename column appt_date back to appt_datee in sessions table"""
    op.alter_column('sessions', 'appt_date', new_column_name='appt_datee')
