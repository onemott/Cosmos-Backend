"""Add SystemConfig and notification content_format

Revision ID: f7g8h9i0j1k2
Revises: e5f8d4568108
Create Date: 2026-02-26 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7g8h9i0j1k2'
down_revision: Union[str, None] = 'e5f8d4568108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create system_configs table
    op.create_table('system_configs',
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False, server_default='1.0'),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True, default=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )
    
    # Add content_format to notifications
    op.add_column('notifications', sa.Column('content_format', sa.String(length=20), nullable=True, server_default='text'))


def downgrade() -> None:
    # Remove content_format from notifications
    op.drop_column('notifications', 'content_format')
    
    # Drop system_configs table
    op.drop_table('system_configs')
