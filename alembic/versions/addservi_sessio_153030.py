"""Auto-generated migration: Add service_facility_address field to sessions table

Revision ID: addservi_sessio_153030
Revises: addlocat_sessio_153018
Create Date: 20250820_153030

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addservi_sessio_153030'
down_revision = 'addlocat_sessio_153018'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add service_facility_address field to sessions table"""
    op.add_column('sessions', sa.Column('service_facility_address', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove service_facility_address field from sessions table"""
    op.drop_column('sessions', 'service_facility_address')
