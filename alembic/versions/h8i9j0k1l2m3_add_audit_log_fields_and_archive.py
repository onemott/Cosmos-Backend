"""add audit log fields and archive table

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-02-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("level", sa.String(length=20), nullable=False, server_default="info"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("category", sa.String(length=50), nullable=False, server_default="system"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("outcome", sa.String(length=20), nullable=False, server_default="success"),
    )
    op.add_column("audit_logs", sa.Column("event_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("tags", sa.JSON(), nullable=True))

    op.create_index("ix_audit_logs_level", "audit_logs", ["level"])
    op.create_index("ix_audit_logs_category", "audit_logs", ["category"])
    op.create_index("ix_audit_logs_outcome", "audit_logs", ["outcome"])
    op.create_index("ix_audit_logs_event_hash", "audit_logs", ["event_hash"])

    op.create_table(
        "audit_logs_archive",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_archive_tenant_id", "audit_logs_archive", ["tenant_id"])
    op.create_index("ix_audit_logs_archive_event_type", "audit_logs_archive", ["event_type"])
    op.create_index("ix_audit_logs_archive_level", "audit_logs_archive", ["level"])
    op.create_index("ix_audit_logs_archive_category", "audit_logs_archive", ["category"])
    op.create_index("ix_audit_logs_archive_outcome", "audit_logs_archive", ["outcome"])
    op.create_index("ix_audit_logs_archive_event_hash", "audit_logs_archive", ["event_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_archive_event_hash", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_outcome", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_category", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_level", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_event_type", table_name="audit_logs_archive")
    op.drop_index("ix_audit_logs_archive_tenant_id", table_name="audit_logs_archive")
    op.drop_table("audit_logs_archive")

    op.drop_index("ix_audit_logs_event_hash", table_name="audit_logs")
    op.drop_index("ix_audit_logs_outcome", table_name="audit_logs")
    op.drop_index("ix_audit_logs_category", table_name="audit_logs")
    op.drop_index("ix_audit_logs_level", table_name="audit_logs")

    op.drop_column("audit_logs", "tags")
    op.drop_column("audit_logs", "prev_hash")
    op.drop_column("audit_logs", "event_hash")
    op.drop_column("audit_logs", "outcome")
    op.drop_column("audit_logs", "category")
    op.drop_column("audit_logs", "level")
