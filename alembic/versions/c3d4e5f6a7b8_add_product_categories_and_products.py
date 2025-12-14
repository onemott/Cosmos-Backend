"""add product_categories and products tables

Revision ID: c3d4e5f6a7b8
Revises: aac43b5b77df
Create Date: 2025-12-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'aac43b5b77df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create product_categories table
    op.create_table('product_categories',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('name_zh', sa.String(length=100), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_category_tenant_code')
    )
    op.create_index(op.f('ix_product_categories_tenant_id'), 'product_categories', ['tenant_id'], unique=False)

    # Create products table
    op.create_table('products',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('module_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('category_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('name_zh', sa.String(length=255), nullable=True),
        sa.Column('description', sa.String(length=2000), nullable=True),
        sa.Column('description_zh', sa.String(length=2000), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('risk_level', sa.String(length=50), nullable=False),
        sa.Column('min_investment', sa.Numeric(precision=18, scale=2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('expected_return', sa.String(length=100), nullable=True),
        sa.Column('is_visible', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['module_id'], ['modules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['product_categories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('module_id', 'tenant_id', 'code', name='uq_product_module_tenant_code')
    )
    op.create_index(op.f('ix_products_module_id'), 'products', ['module_id'], unique=False)
    op.create_index(op.f('ix_products_tenant_id'), 'products', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_products_category_id'), 'products', ['category_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_products_category_id'), table_name='products')
    op.drop_index(op.f('ix_products_tenant_id'), table_name='products')
    op.drop_index(op.f('ix_products_module_id'), table_name='products')
    op.drop_table('products')

    op.drop_index(op.f('ix_product_categories_tenant_id'), table_name='product_categories')
    op.drop_table('product_categories')
