"""Auto-generated migration: Add delivered_off_site field to sessions table

Revision ID: adddeliv_sessio_153043
Revises: addservi_sessio_153030
Create Date: 20250820_153043

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'adddeliv_sessio_153043'
down_revision = 'addservi_sessio_153030'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add delivered_off_site field to sessions table"""
    op.add_column('sessions', sa.Column('delivered_off_site', sa.TEXT(), nullable=True))

def downgrade() -> None:
    """Remove delivered_off_site field from sessions table"""
    op.drop_column('sessions', 'delivered_off_site')
