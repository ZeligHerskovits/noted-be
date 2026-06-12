"""create emr_type_field_responses table

Revision ID: addemrtyperesponses_20260607
Revises: addtestt_sessio_101504
Create Date: 2026-06-07 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "addemrtyperesponses_20260607"
down_revision: Union[str, Sequence[str], None] = "addtestt_sessio_101504"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emr_type_field_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("emr_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_value", sa.String(length=20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "response_value IN ('response 1', 'response 2', 'response 3')",
            name="ck_emr_type_field_response_value",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["emr_type_id"], ["emr_type.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("emr_type_id", "field_name", name="uq_emr_type_field_name"),
    )
    op.create_index(op.f("ix_emr_type_field_responses_id"), "emr_type_field_responses", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_emr_type_field_responses_id"), table_name="emr_type_field_responses")
    op.drop_table("emr_type_field_responses")
