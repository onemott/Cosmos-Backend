"""Product and ProductCategory repository."""

from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.repositories.base import BaseRepository, USE_CURRENT_TENANT
from src.models.product import Product, ProductCategory
from src.models.module import Module, TenantModule
from src.core.tenancy import get_current_tenant_id


class ProductCategoryRepository(BaseRepository[ProductCategory]):
    """Repository for ProductCategory model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(ProductCategory, session)

    async def get_by_code(
        self, code: str, tenant_id: Optional[str] = USE_CURRENT_TENANT
    ) -> Optional[ProductCategory]:
        """Get category by code within tenant scope.

        For tenant-specific queries, also checks platform defaults (tenant_id=NULL).
        """
        if tenant_id == USE_CURRENT_TENANT:
            tenant_id = get_current_tenant_id()

        query = select(ProductCategory).where(
            ProductCategory.code == code,
            or_(
                ProductCategory.tenant_id == tenant_id,
                ProductCategory.tenant_id.is_(None),  # Platform defaults
            ),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_categories_for_tenant(
        self, tenant_id: str, include_inactive: bool = False
    ) -> Sequence[ProductCategory]:
        """Get all categories available to a tenant (platform defaults + tenant-specific).

        Categories are returned sorted by sort_order.
        """
        query = select(ProductCategory).where(
            or_(
                ProductCategory.tenant_id == tenant_id,
                ProductCategory.tenant_id.is_(None),  # Platform defaults
            )
        )

        if not include_inactive:
            query = query.where(ProductCategory.is_active == True)

        query = query.order_by(ProductCategory.sort_order, ProductCategory.name)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_default_categories(
        self, include_inactive: bool = False
    ) -> Sequence[ProductCategory]:
        """Get all platform default categories (tenant_id=NULL)."""
        query = select(ProductCategory).where(ProductCategory.tenant_id.is_(None))

        if not include_inactive:
            query = query.where(ProductCategory.is_active == True)

        query = query.order_by(ProductCategory.sort_order, ProductCategory.name)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def create_default_category(self, data: dict) -> ProductCategory:
        """Create a platform default category (tenant_id=NULL)."""
        data["tenant_id"] = None
        return await self.create(data)


class ProductRepository(BaseRepository[Product]):
    """Repository for Product model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Product, session)

    async def get_by_code(
        self,
        code: str,
        module_id: str,
        tenant_id: Optional[str] = USE_CURRENT_TENANT,
    ) -> Optional[Product]:
        """Get product by code within module and tenant scope."""
        if tenant_id == USE_CURRENT_TENANT:
            tenant_id = get_current_tenant_id()

        query = select(Product).where(
            Product.code == code,
            Product.module_id == module_id,
        )

        if tenant_id:
            # Look for tenant-specific or platform default
            query = query.where(
                or_(
                    Product.tenant_id == tenant_id,
                    Product.tenant_id.is_(None),
                )
            )
        else:
            # Platform default only
            query = query.where(Product.tenant_id.is_(None))

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_relations(self, product_id: str) -> Optional[Product]:
        """Get product with module and category relations loaded."""
        query = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.module),
                selectinload(Product.category_rel),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_products_for_tenant(
        self,
        tenant_id: str,
        module_id: Optional[str] = None,
        category_id: Optional[str] = None,
        risk_level: Optional[str] = None,
        visible_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Product]:
        """Get all products available to a tenant.

        Returns:
        - Platform default products (tenant_id=NULL) - visible to all tenants
        - Tenant-specific products only from enabled modules

        Platform admins create products and decide visibility.
        Tenant admins can see visible platform products and hide/show them.
        """
        # Get enabled module IDs for this tenant (core + enabled via TenantModule)
        enabled_modules_query = select(Module.id).where(
            Module.is_active == True,
            or_(
                Module.is_core == True,
                Module.id.in_(
                    select(TenantModule.module_id).where(
                        TenantModule.tenant_id == tenant_id,
                        TenantModule.is_enabled == True,
                    )
                ),
            ),
        )

        # Build query:
        # - Platform defaults (tenant_id=NULL) are always included (no module restriction)
        # - Tenant-specific products only from enabled modules
        query = select(Product).where(
            or_(
                Product.tenant_id.is_(None),  # Platform defaults - visible to all
                and_(
                    Product.tenant_id == tenant_id,  # Tenant-specific
                    Product.module_id.in_(enabled_modules_query),  # Only from enabled modules
                ),
            )
        )

        if module_id:
            query = query.where(Product.module_id == module_id)

        if category_id:
            query = query.where(Product.category_id == category_id)

        if risk_level:
            query = query.where(Product.risk_level == risk_level)

        if visible_only:
            query = query.where(Product.is_visible == True)

        query = (
            query.options(
                selectinload(Product.module),
                selectinload(Product.category_rel),
            )
            .order_by(Product.category, Product.name)
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_default_products(
        self,
        module_id: Optional[str] = None,
        visible_only: bool = True,
    ) -> Sequence[Product]:
        """Get all platform default products (tenant_id=NULL)."""
        query = select(Product).where(
            Product.tenant_id.is_(None),
            Product.is_default == True,
        )

        if module_id:
            query = query.where(Product.module_id == module_id)

        if visible_only:
            query = query.where(Product.is_visible == True)

        query = query.options(
            selectinload(Product.module),
            selectinload(Product.category_rel),
        ).order_by(Product.category, Product.name)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def create_default_product(self, data: dict) -> Product:
        """Create a platform default product (tenant_id=NULL, is_default=True)."""
        data["tenant_id"] = None
        data["is_default"] = True
        return await self.create(data)

    async def create_tenant_product(self, data: dict, tenant_id: str) -> Product:
        """Create a tenant-specific product."""
        data["tenant_id"] = tenant_id
        data["is_default"] = False
        return await self.create(data)

    async def copy_defaults_for_tenant(
        self, tenant_id: str, module_id: str
    ) -> Sequence[Product]:
        """Copy platform default products to a tenant.

        Creates tenant-specific copies of platform defaults for customization.
        Returns the newly created products.
        """
        # Get default products for the module
        defaults = await self.get_default_products(module_id=module_id)

        created_products = []
        for default_product in defaults:
            # Check if tenant already has this product
            existing = await self.get_by_code(
                default_product.code, module_id, tenant_id
            )
            if existing and existing.tenant_id == tenant_id:
                continue  # Skip if already exists as tenant product

            # Create tenant copy
            new_product_data = {
                "module_id": module_id,
                "tenant_id": tenant_id,
                "category_id": default_product.category_id,
                "code": default_product.code,
                "name": default_product.name,
                "name_zh": default_product.name_zh,
                "description": default_product.description,
                "description_zh": default_product.description_zh,
                "category": default_product.category,
                "risk_level": default_product.risk_level,
                "min_investment": default_product.min_investment,
                "currency": default_product.currency,
                "expected_return": default_product.expected_return,
                "is_visible": True,
                "is_default": False,
                "extra_data": default_product.extra_data,
            }
            new_product = await self.create(new_product_data)
            created_products.append(new_product)

        return created_products

    async def toggle_visibility(self, product: Product, is_visible: bool) -> Product:
        """Toggle product visibility."""
        return await self.update(product, {"is_visible": is_visible})

    async def get_products_by_module_codes(
        self,
        module_codes: list[str],
        tenant_id: str,
        visible_only: bool = True,
    ) -> dict[str, Sequence[Product]]:
        """Get products grouped by module code.

        Returns a dict with module_code as key and list of products as value.
        """
        # First get module IDs for the codes
        module_query = select(Module).where(Module.code.in_(module_codes))
        module_result = await self.session.execute(module_query)
        modules = {m.id: m.code for m in module_result.scalars().all()}

        if not modules:
            return {}

        # Get products for these modules
        query = select(Product).where(
            Product.module_id.in_(modules.keys()),
            or_(
                Product.tenant_id == tenant_id,
                Product.tenant_id.is_(None),
            ),
        )

        if visible_only:
            query = query.where(Product.is_visible == True)

        query = query.options(
            selectinload(Product.module),
            selectinload(Product.category_rel),
        ).order_by(Product.category, Product.name)

        result = await self.session.execute(query)
        products = result.scalars().all()

        # Group by module code
        grouped: dict[str, list[Product]] = {code: [] for code in module_codes}
        for product in products:
            module_code = modules.get(product.module_id)
            if module_code:
                grouped[module_code].append(product)

        return grouped
