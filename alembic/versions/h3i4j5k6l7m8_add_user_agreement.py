"""Add UserAgreement model

Revision ID: h3i4j5k6l7m8
Revises: f7g8h9i0j1k2
Create Date: 2026-02-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h3i4j5k6l7m8'
down_revision: Union[str, None] = 'f7g8h9i0j1k2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_agreements table
    op.create_table('user_agreements',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('client_user_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('agreement_type', sa.String(length=50), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('device_info', sa.String(length=255), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['client_user_id'], ['client_users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_agreements_user_id'), 'user_agreements', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_agreements_client_user_id'), 'user_agreements', ['client_user_id'], unique=False)
    op.create_index(op.f('ix_user_agreements_agreement_type'), 'user_agreements', ['agreement_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_agreements_agreement_type'), table_name='user_agreements')
    op.drop_index(op.f('ix_user_agreements_client_user_id'), table_name='user_agreements')
    op.drop_index(op.f('ix_user_agreements_user_id'), table_name='user_agreements')
    op.drop_table('user_agreements')
