"""Auto-generated migration: Add location_where_session_took_place field to sessions table

Revision ID: addlocat_sessio_153018
Revises: addprogr_sessio_153003
Create Date: 20250820_153018

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'addlocat_sessio_153018'
down_revision = 'addprogr_sessio_153003'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add location_where_session_took_place field to sessions table"""
    op.add_column('sessions', sa.Column('location_where_session_took_place', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove location_where_session_took_place field from sessions table"""
    op.drop_column('sessions', 'location_where_session_took_place')
