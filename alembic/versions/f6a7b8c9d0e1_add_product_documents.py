"""Add product_id to documents table for product documents.

Revision ID: f6a7b8c9d0e1
Revises: d5cb9d36199d
Create Date: 2024-12-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "d5cb9d36199d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add product_id column to documents table
    op.add_column(
        "documents",
        sa.Column("product_id", sa.UUID(as_uuid=False), nullable=True)
    )
    
    # Create index on product_id
    op.create_index(
        op.f("ix_documents_product_id"),
        "documents",
        ["product_id"],
        unique=False
    )
    
    # Create index on client_id (was not indexed in original schema)
    op.create_index(
        op.f("ix_documents_client_id"),
        "documents",
        ["client_id"],
        unique=False
    )
    
    # Add foreign key constraint to products.id with CASCADE delete
    op.create_foreign_key(
        "fk_documents_product_id",
        "documents",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE"
    )
    
    # Update client_id foreign key to have CASCADE delete
    op.drop_constraint("documents_client_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key(
        "documents_client_id_fkey",
        "documents",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE"
    )
    
    # Add check constraint: document must have either client_id OR product_id, not both
    # Note: This constraint allows existing documents to have client_id set.
    # New documents must have either client_id OR product_id (not both).
    op.create_check_constraint(
        "ck_document_owner",
        "documents",
        "(client_id IS NOT NULL AND product_id IS NULL) OR "
        "(client_id IS NULL AND product_id IS NOT NULL)"
    )


def downgrade() -> None:
    # Drop check constraint
    op.drop_constraint("ck_document_owner", "documents", type_="check")
    
    # Restore original client_id foreign key without CASCADE
    op.drop_constraint("documents_client_id_fkey", "documents", type_="foreignkey")
    op.create_foreign_key(
        "documents_client_id_fkey",
        "documents",
        "clients",
        ["client_id"],
        ["id"]
    )
    
    # Drop product_id foreign key
    op.drop_constraint("fk_documents_product_id", "documents", type_="foreignkey")
    
    # Drop indexes
    op.drop_index(op.f("ix_documents_client_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_product_id"), table_name="documents")
    
    # Drop product_id column
    op.drop_column("documents", "product_id")

