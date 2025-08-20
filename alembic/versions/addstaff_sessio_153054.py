"""Auto-generated migration: Add staff_providing_service field to sessions table

Revision ID: addstaff_sessio_153054
Revises: adddeliv_sessio_153043
Create Date: 20250820_153054

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addstaff_sessio_153054'
down_revision = 'adddeliv_sessio_153043'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add staff_providing_service field to sessions table"""
    op.add_column('sessions', sa.Column('staff_providing_service', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove staff_providing_service field from sessions table"""
    op.drop_column('sessions', 'staff_providing_service')
