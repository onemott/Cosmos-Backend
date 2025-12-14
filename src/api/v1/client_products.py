"""Client-facing products API endpoints."""

from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_client
from src.db.session import get_db
from src.db.repositories.product_repo import ProductRepository, ProductCategoryRepository
from src.models.module import Module, TenantModule, ClientModule

router = APIRouter(prefix="/client", tags=["Client Products"])


# ============================================================================
# Response Models for Client API
# ============================================================================


class ClientProductResponse(BaseModel):
    """Product response for client API."""
    id: str
    code: str
    name: str
    name_zh: Optional[str] = None
    description: Optional[str] = None
    description_zh: Optional[str] = None
    category: str
    risk_level: str
    min_investment: Decimal
    currency: str
    expected_return: Optional[str] = None
    tags: List[str] = []

    class Config:
        from_attributes = True


class ClientProductModule(BaseModel):
    """Module with products for client API."""
    code: str
    name: str
    name_zh: Optional[str] = None
    description: Optional[str] = None
    description_zh: Optional[str] = None
    is_enabled: bool
    products: List[ClientProductResponse] = []


class ClientCategoryResponse(BaseModel):
    """Category response for client API."""
    id: str
    code: str
    name: str
    name_zh: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True


# ============================================================================
# Helper Functions
# ============================================================================


async def get_client_enabled_modules(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
) -> List[Module]:
    """Get modules that are enabled for the client.

    A module is enabled for a client if:
    1. It's a core module (always enabled), OR
    2. It's enabled for the tenant AND enabled for the client
    """
    # Get all modules with their tenant/client status
    modules_query = select(Module).where(Module.is_active == True)
    result = await db.execute(modules_query)
    all_modules = result.scalars().all()

    # Get tenant module statuses
    tm_query = select(TenantModule).where(TenantModule.tenant_id == tenant_id)
    tm_result = await db.execute(tm_query)
    tenant_modules = {tm.module_id: tm for tm in tm_result.scalars().all()}

    # Get client module statuses
    cm_query = select(ClientModule).where(
        ClientModule.tenant_id == tenant_id,
        ClientModule.client_id == client_id,
    )
    cm_result = await db.execute(cm_query)
    client_modules = {cm.module_id: cm for cm in cm_result.scalars().all()}

    enabled_modules = []
    for module in all_modules:
        # Core modules are always enabled
        if module.is_core:
            enabled_modules.append(module)
            continue

        # Check tenant has module enabled
        tm = tenant_modules.get(module.id)
        if not tm or not tm.is_enabled:
            continue

        # Check client has module enabled (default to enabled if no record)
        cm = client_modules.get(module.id)
        if cm and not cm.is_enabled:
            continue

        enabled_modules.append(module)

    return enabled_modules


# ============================================================================
# Client Products Endpoints
# ============================================================================


@router.get(
    "/products",
    response_model=List[ClientProductModule],
    summary="Get products grouped by module",
    description="Get all products available to the client, grouped by their enabled modules.",
)
async def get_client_products(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> List[ClientProductModule]:
    """Get products for the authenticated client, grouped by module.

    Only returns products from modules that are enabled for the client.
    """
    tenant_id = current_client["tenant_id"]
    client_id = current_client["client_id"]

    # Get enabled modules for this client
    enabled_modules = await get_client_enabled_modules(db, tenant_id, client_id)

    if not enabled_modules:
        return []

    # Get products for these modules
    product_repo = ProductRepository(db)
    module_codes = [m.code for m in enabled_modules]
    products_by_module = await product_repo.get_products_by_module_codes(
        module_codes=module_codes,
        tenant_id=tenant_id,
        visible_only=True,
    )

    # Build response
    response = []
    for module in enabled_modules:
        products = products_by_module.get(module.code, [])

        module_response = ClientProductModule(
            code=module.code,
            name=module.name,
            name_zh=module.name_zh,
            description=module.description,
            description_zh=module.description_zh,
            is_enabled=True,
            products=[
                ClientProductResponse(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    name_zh=p.name_zh,
                    description=p.description,
                    description_zh=p.description_zh,
                    category=p.category,
                    risk_level=p.risk_level,
                    min_investment=p.min_investment,
                    currency=p.currency,
                    expected_return=p.expected_return,
                    tags=p.extra_data.get("tags", []) if p.extra_data else [],
                )
                for p in products
            ],
        )
        response.append(module_response)

    return response


@router.get(
    "/products/{module_code}",
    response_model=List[ClientProductResponse],
    summary="Get products for a specific module",
    description="Get all products from a specific module available to the client.",
)
async def get_module_products(
    module_code: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> List[ClientProductResponse]:
    """Get products for a specific module.

    Returns 403 if the module is not enabled for the client.
    """
    tenant_id = current_client["tenant_id"]
    client_id = current_client["client_id"]

    # Check module exists
    module_query = select(Module).where(
        Module.code == module_code,
        Module.is_active == True,
    )
    result = await db.execute(module_query)
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_code}' not found",
        )

    # Check if module is enabled for this client
    enabled_modules = await get_client_enabled_modules(db, tenant_id, client_id)
    enabled_module_ids = {m.id for m in enabled_modules}

    if module.id not in enabled_module_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Module '{module_code}' is not enabled for your account",
        )

    # Get products for this module
    product_repo = ProductRepository(db)
    products = await product_repo.get_products_for_tenant(
        tenant_id=tenant_id,
        module_id=module.id,
        visible_only=True,
    )

    return [
        ClientProductResponse(
            id=p.id,
            code=p.code,
            name=p.name,
            name_zh=p.name_zh,
            description=p.description,
            description_zh=p.description_zh,
            category=p.category,
            risk_level=p.risk_level,
            min_investment=p.min_investment,
            currency=p.currency,
            expected_return=p.expected_return,
            tags=p.extra_data.get("tags", []) if p.extra_data else [],
        )
        for p in products
    ]


@router.get(
    "/categories",
    response_model=List[ClientCategoryResponse],
    summary="Get available categories",
    description="Get all product categories available to the client.",
)
async def get_client_categories(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> List[ClientCategoryResponse]:
    """Get product categories available to the client.

    Returns both platform default categories and tenant-specific categories.
    """
    tenant_id = current_client["tenant_id"]

    category_repo = ProductCategoryRepository(db)
    categories = await category_repo.get_categories_for_tenant(
        tenant_id=tenant_id,
        include_inactive=False,
    )

    return [
        ClientCategoryResponse(
            id=c.id,
            code=c.code,
            name=c.name,
            name_zh=c.name_zh,
            description=c.description,
            icon=c.icon,
            sort_order=c.sort_order,
        )
        for c in categories
    ]
