"""add account valuations table

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2024-01-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'i9j0k1l2m3n4'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create account_valuations table for historical performance tracking
    op.create_table(
        'account_valuations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False, index=True),
        sa.Column('account_id', sa.UUID(as_uuid=False), sa.ForeignKey('accounts.id'), nullable=False, index=True),
        sa.Column('valuation_date', sa.Date(), nullable=False, index=True),
        sa.Column('total_value', sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column('cash_balance', sa.Numeric(precision=20, scale=4), server_default='0'),
        sa.Column('invested_value', sa.Numeric(precision=20, scale=4), server_default='0'),
        sa.Column('currency', sa.String(3), server_default='USD'),
        sa.Column('holdings_count', sa.Integer(), server_default='0'),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('account_id', 'valuation_date', name='uq_account_valuation_date'),
    )


def downgrade() -> None:
    op.drop_table('account_valuations')
