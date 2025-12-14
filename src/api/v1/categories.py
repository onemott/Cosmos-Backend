"""Product Category endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.api.deps import (
    get_current_user,
    get_current_superuser,
    get_current_tenant_admin,
)
from src.db.repositories.product_repo import ProductCategoryRepository
from src.schemas.product import (
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductCategoryResponse,
)

router = APIRouter()


# ============================================================================
# Category Listing Endpoints
# ============================================================================


@router.get("/", response_model=List[ProductCategoryResponse])
async def list_categories(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[ProductCategoryResponse]:
    """List categories available to the current user's tenant.

    Returns both platform default categories (tenant_id=NULL) and tenant-specific categories.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    repo = ProductCategoryRepository(db)
    categories = await repo.get_categories_for_tenant(
        tenant_id, include_inactive=include_inactive
    )

    return [ProductCategoryResponse.model_validate(c) for c in categories]


@router.get("/defaults", response_model=List[ProductCategoryResponse])
async def list_default_categories(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> List[ProductCategoryResponse]:
    """List all platform default categories (platform admin only).

    Platform default categories have tenant_id=NULL and are available to all tenants.
    """
    repo = ProductCategoryRepository(db)
    categories = await repo.get_default_categories(include_inactive=include_inactive)

    return [ProductCategoryResponse.model_validate(c) for c in categories]


# ============================================================================
# Category CRUD Endpoints
# ============================================================================


@router.get("/{category_id}", response_model=ProductCategoryResponse)
async def get_category(
    category_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ProductCategoryResponse:
    """Get a specific category by ID.

    Only returns category if it's a platform default or belongs to user's tenant.
    """
    tenant_id = current_user.get("tenant_id")

    repo = ProductCategoryRepository(db)
    category = await repo.get(category_id)

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    # Check access: platform default (NULL tenant) or same tenant
    if category.tenant_id is not None and category.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return ProductCategoryResponse.model_validate(category)


@router.post("/", response_model=ProductCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_in: ProductCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductCategoryResponse:
    """Create a new tenant-specific category (tenant admin only).

    The category will be created with the current user's tenant_id.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    repo = ProductCategoryRepository(db)

    # Check if code already exists for this tenant or as platform default
    existing = await repo.get_by_code(category_in.code, tenant_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category with code '{category_in.code}' already exists",
        )

    # Create tenant-specific category
    category_data = category_in.model_dump()
    category_data["tenant_id"] = tenant_id
    category = await repo.create(category_data)
    await db.commit()

    return ProductCategoryResponse.model_validate(category)


@router.post("/defaults", response_model=ProductCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_default_category(
    category_in: ProductCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> ProductCategoryResponse:
    """Create a new platform default category (platform admin only).

    Platform default categories are available to all tenants.
    """
    repo = ProductCategoryRepository(db)

    # Check if code already exists as platform default
    existing = await repo.get_by_code(category_in.code, tenant_id=None)
    if existing and existing.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Default category with code '{category_in.code}' already exists",
        )

    # Create platform default category
    category = await repo.create_default_category(category_in.model_dump())
    await db.commit()

    return ProductCategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=ProductCategoryResponse)
async def update_category(
    category_id: str,
    category_in: ProductCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ProductCategoryResponse:
    """Update a category (tenant admin for tenant categories, platform admin for defaults).

    Note: code cannot be changed after creation.
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )

    repo = ProductCategoryRepository(db)
    category = await repo.get(category_id)

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    # Check permissions
    if category.tenant_id is None:
        # Platform default - only platform admins can update
        if not is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can update default categories",
            )
    else:
        # Tenant category - must belong to user's tenant
        if category.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    # Update category
    update_data = category_in.model_dump(exclude_unset=True)
    category = await repo.update(category, update_data)
    await db.commit()

    return ProductCategoryResponse.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Delete a category (tenant admin for tenant categories, platform admin for defaults).

    Warning: Deleting a category may affect products that reference it.
    """
    tenant_id = current_user.get("tenant_id")
    is_platform_admin = any(
        role in current_user.get("roles", [])
        for role in ["super_admin", "platform_admin"]
    )

    repo = ProductCategoryRepository(db)
    category = await repo.get(category_id)

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    # Check permissions
    if category.tenant_id is None:
        # Platform default - only platform admins can delete
        if not is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only platform admins can delete default categories",
            )
    else:
        # Tenant category - must belong to user's tenant
        if category.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    await repo.delete(category)
    await db.commit()
