"""Product endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.api.deps import (
    get_current_user,
    get_current_superuser,
    get_current_tenant_admin,
)
from src.db.repositories.product_repo import ProductRepository, ProductCategoryRepository
from src.models.module import Module
from src.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductVisibilityUpdate,
)

router = APIRouter()


def _build_product_response(product) -> ProductResponse:
    """Build product response with joined fields."""
    return ProductResponse(
        id=product.id,
        module_id=product.module_id,
        tenant_id=product.tenant_id,
        category_id=product.category_id,
        code=product.code,
        name=product.name,
        name_zh=product.name_zh,
        description=product.description,
        description_zh=product.description_zh,
        category=product.category,
        risk_level=product.risk_level,
        min_investment=product.min_investment,
        currency=product.currency,
        expected_return=product.expected_return,
        is_visible=product.is_visible,
        is_default=product.is_default,
        extra_data=product.extra_data,
        created_at=product.created_at,
        updated_at=product.updated_at,
        module_code=product.module.code if product.module else None,
        module_name=product.module.name if product.module else None,
        category_name=product.category_rel.name if product.category_rel else None,
    )


# ============================================================================
# Product Listing Endpoints
# ============================================================================


@router.get("/", response_model=List[ProductResponse])
async def list_products(
    module_id: Optional[str] = Query(None, description="Filter by module ID"),
    module_code: Optional[str] = Query(None, description="Filter by module code"),
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    visible_only: bool = Query(True, description="Only show visible products"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[ProductResponse]:
    """List products available to the current user's tenant.

    Returns both platform default products and tenant-specific products.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    # If module_code provided, resolve to module_id
    resolved_module_id = module_id
    if module_code and not module_id:
        module = await db.execute(
            db.query(Module).filter(Module.code == module_code).statement
        )
        module = module.scalar_one_or_none()
        if module:
            resolved_module_id = module.id

    repo = ProductRepository(db)
    products = await repo.get_products_for_tenant(
        tenant_id=tenant_id,
        module_id=resolved_module_id,
        category_id=category_id,
        risk_level=risk_level,
        visible_only=visible_only,
        skip=skip,
        limit=limit,
    )

    return [_build_product_response(p) for p in products]


@router.get("/defaults", response_model=List[ProductResponse])
async def list_default_products(
    module_id: Optional[str] = Query(None, description="Filter by module ID"),
    visible_only: bool = Query(True, description="Only show visible products"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> List[ProductResponse]:
    """List all platform default products (platform admin only).

    Platform default products have tenant_id=NULL and is_default=True.
    """
    repo = ProductRepository(db)
    products = await repo.get_default_products(
        module_id=module_id,
        visible_only=visible_only,
    )

    return [_build_product_response(p) for p in products]


# ============================================================================
# Product CRUD Endpoints
# ============================================================================


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ProductResponse:
    """Get a specific product by ID.

    Only returns product if it's a platform default or belongs to user's tenant.
    """
    tenant_id = current_user.get("tenant_id")

    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Check access: platform default (NULL tenant) or same tenant
    if product.tenant_id is not None and product.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _build_product_response(product)


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductResponse:
    """Create a new tenant-specific product (tenant admin only).

    The product will be created with the current user's tenant_id and is_default=False.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    # Verify module exists
    module = await db.get(Module, product_in.module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    repo = ProductRepository(db)

    # Check if code already exists for this module and tenant
    existing = await repo.get_by_code(product_in.code, product_in.module_id, tenant_id)
    if existing and existing.tenant_id == tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product with code '{product_in.code}' already exists in this module",
        )

    # Validate category if provided
    if product_in.category_id:
        cat_repo = ProductCategoryRepository(db)
        category = await cat_repo.get(product_in.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category not found",
            )

    # Create tenant-specific product
    product = await repo.create_tenant_product(product_in.model_dump(), tenant_id)
    await db.commit()

    # Reload with relations
    product = await repo.get_with_relations(product.id)
    return _build_product_response(product)


@router.post("/defaults", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_default_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> ProductResponse:
    """Create a new platform default product (platform admin only).

    Platform default products are available to all tenants.
    """
    # Verify module exists
    module = await db.get(Module, product_in.module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    repo = ProductRepository(db)

    # Check if code already exists as platform default for this module
    existing = await repo.get_by_code(product_in.code, product_in.module_id, tenant_id=None)
    if existing and existing.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Default product with code '{product_in.code}' already exists in this module",
        )

    # Create platform default product
    product = await repo.create_default_product(product_in.model_dump())
    await db.commit()

    # Reload with relations
    product = await repo.get_with_relations(product.id)
    return _build_product_response(product)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductResponse:
    """Update a product (tenant admin for tenant products, platform admin for defaults).

    Note: code and module_id cannot be changed after creation.
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )

    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Check permissions
    if product.tenant_id is None:
        # Platform default - only platform admins can update
        if not is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can update default products",
            )
    else:
        # Tenant product - must belong to user's tenant
        if product.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    # Validate category if being updated
    if product_in.category_id:
        cat_repo = ProductCategoryRepository(db)
        category = await cat_repo.get(product_in.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category not found",
            )

    # Update product
    update_data = product_in.model_dump(exclude_unset=True)
    product = await repo.update(product, update_data)
    await db.commit()

    # Reload with relations
    product = await repo.get_with_relations(product.id)
    return _build_product_response(product)


@router.patch("/{product_id}/visibility", response_model=ProductResponse)
async def update_product_visibility(
    product_id: str,
    visibility_in: ProductVisibilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductResponse:
    """Toggle product visibility (tenant admin only).

    Tenants can hide platform default products from their view.
    For platform defaults, this creates a tenant-specific visibility override.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    repo = ProductRepository(db)
    product = await repo.get_with_relations(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Check access
    if product.tenant_id is not None and product.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # For platform defaults, create a tenant copy first if hiding
    # (so tenant has their own visibility control without affecting others)
    if product.tenant_id is None and not visibility_in.is_visible:
        # Check if tenant already has a copy
        existing = await repo.get_by_code(product.code, product.module_id, tenant_id)
        if existing and existing.tenant_id == tenant_id:
            # Use existing tenant copy
            product = existing
        else:
            # Create tenant copy with visibility set
            await repo.copy_defaults_for_tenant(tenant_id, product.module_id)
            # Get the newly created copy
            product = await repo.get_by_code(product.code, product.module_id, tenant_id)
            if not product or product.tenant_id != tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create tenant product copy",
                )

    # Update visibility
    product = await repo.toggle_visibility(product, visibility_in.is_visible)
    await db.commit()

    # Reload with relations
    product = await repo.get_with_relations(product.id)
    return _build_product_response(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Delete a product (tenant admin for tenant products, platform admin for defaults).

    Tenant admins cannot delete platform default products.
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )

    repo = ProductRepository(db)
    product = await repo.get(product_id)

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Check permissions
    if product.tenant_id is None:
        # Platform default - only platform admins can delete
        if not is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can delete default products",
            )
    else:
        # Tenant product - must belong to user's tenant
        if product.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    await repo.delete(product)
    await db.commit()
