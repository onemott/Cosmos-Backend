"""add_language_to_client_users

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2025-12-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add language column to client_users table
    op.add_column(
        'client_users',
        sa.Column('language', sa.String(length=10), nullable=False, server_default='en')
    )


def downgrade() -> None:
    # Remove language column from client_users table
    op.drop_column('client_users', 'language')

