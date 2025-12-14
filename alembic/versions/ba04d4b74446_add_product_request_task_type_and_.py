"""Add PRODUCT_REQUEST task type and PENDING_EAM workflow state

Revision ID: ba04d4b74446
Revises: ded53a0e3a76
Create Date: 2025-12-12 23:32:50.906784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba04d4b74446'
down_revision: Union[str, None] = 'ded53a0e3a76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new enum values for TaskType and WorkflowState
    # PostgreSQL requires ALTER TYPE to add enum values
    # Note: Enum values must match SQLAlchemy's Enum naming convention (uppercase NAME)
    
    # Add PRODUCT_REQUEST to tasktype enum
    op.execute("ALTER TYPE tasktype ADD VALUE IF NOT EXISTS 'PRODUCT_REQUEST'")
    
    # Add PENDING_EAM to workflowstate enum
    op.execute("ALTER TYPE workflowstate ADD VALUE IF NOT EXISTS 'PENDING_EAM'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly
    # Would need to recreate the type, which is complex
    # For now, leave enum values in place (they don't hurt anything)
    pass
