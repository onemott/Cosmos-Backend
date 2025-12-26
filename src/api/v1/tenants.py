"""Tenant management endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.db.repositories.tenant_repo import TenantRepository
from src.schemas.tenant import (
    TenantCreate, 
    TenantUpdate, 
    TenantResponse,
    BrandingUpdate,
    BrandingResponse,
)
from src.api.deps import get_current_superuser, get_platform_user, get_current_tenant_admin
from src.services.branding_service import (
    get_logo_path,
    get_logo_url,
    get_logo_mime_type,
    has_logo,
    save_logo,
    delete_logo,
    InvalidFileTypeError,
    FileTooLargeError,
)

router = APIRouter()


def verify_tenant_ownership(current_user: dict, tenant_id: str) -> None:
    """Verify user can manage the specified tenant.
    
    Platform admins can manage any tenant.
    Tenant admins can only manage their own tenant.
    
    Raises:
        HTTPException: If user cannot manage the tenant
    """
    user_roles = set(current_user.get("roles", []))
    platform_roles = {"super_admin", "platform_admin"}
    
    if not platform_roles.intersection(user_roles):
        if current_user.get("tenant_id") != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only manage your own tenant's branding",
            )


@router.get("/", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_platform_user),  # Read access for all platform users
) -> List[TenantResponse]:
    """List all tenants.
    
    Accessible by all platform-level users (platform_admin, platform_user).
    """
    repo = TenantRepository(db)
    
    if search:
        tenants = await repo.search_tenants(search, skip=skip, limit=limit)
    else:
        tenants = await repo.get_all(skip=skip, limit=limit)
    
    return [TenantResponse.model_validate(t) for t in tenants]


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_in: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> TenantResponse:
    """Create a new tenant (super admin only)."""
    repo = TenantRepository(db)
    
    # Check if slug already exists
    existing = await repo.get_by_slug(tenant_in.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with slug '{tenant_in.slug}' already exists",
        )
    
    # Create tenant
    tenant_data = tenant_in.model_dump()
    tenant = await repo.create(tenant_data)
    
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_platform_user),  # Read access for all platform users
) -> TenantResponse:
    """Get tenant by ID.
    
    Accessible by all platform-level users (platform_admin, platform_user).
    """
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    return TenantResponse.model_validate(tenant)


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    tenant_in: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> TenantResponse:
    """Update tenant (super admin only)."""
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Update only provided fields
    update_data = tenant_in.model_dump(exclude_unset=True)
    if update_data:
        tenant = await repo.update(tenant, update_data)
    
    return TenantResponse.model_validate(tenant)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> None:
    """Deactivate tenant (soft delete - sets is_active to False)."""
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Soft delete by setting is_active to False
    await repo.update(tenant, {"is_active": False})


@router.delete("/{tenant_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant_permanent(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> None:
    """Permanently delete tenant and all associated data.
    
    WARNING: This action cannot be undone. All users, clients, accounts,
    and other data associated with this tenant will be permanently deleted.
    """
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Prevent deletion of platform tenant
    if str(tenant_id) == "00000000-0000-0000-0000-000000000000":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete the platform tenant",
        )
    
    # Hard delete - this will cascade to related records
    await repo.delete(tenant)


# ============================================================================
# Branding Endpoints
# ============================================================================

@router.get("/{tenant_id}/branding", response_model=BrandingResponse)
async def get_tenant_branding(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> BrandingResponse:
    """Get tenant branding configuration.
    
    This is a PUBLIC endpoint - no authentication required.
    Used by client apps to display tenant branding before/after login.
    """
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Parse branding from JSON field
    branding = tenant.branding or {}
    
    # Check logo once to avoid duplicate filesystem access
    tenant_has_logo = has_logo(str(tenant.id))
    
    return BrandingResponse(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        app_name=branding.get("app_name"),
        primary_color=branding.get("primary_color"),
        logo_url=get_logo_url(str(tenant.id)) if tenant_has_logo else None,
        has_logo=tenant_has_logo,
    )


@router.post("/{tenant_id}/branding", response_model=BrandingResponse)
async def update_tenant_branding(
    tenant_id: str,
    branding_in: BrandingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> BrandingResponse:
    """Update tenant branding configuration.
    
    Tenant admins can only update their own tenant's branding.
    Platform admins can update any tenant's branding.
    """
    verify_tenant_ownership(current_user, tenant_id)
    
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Merge new branding with existing
    existing_branding = tenant.branding or {}
    update_data = branding_in.model_dump(exclude_unset=True)
    
    # Update branding fields
    new_branding = {**existing_branding, **update_data}
    
    # Update has_logo flag based on actual file existence
    new_branding["has_logo"] = has_logo(tenant_id)
    if new_branding["has_logo"]:
        new_branding["logo_url"] = get_logo_url(tenant_id)
    
    # Save to database
    await repo.update(tenant, {"branding": new_branding})
    
    return BrandingResponse(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        app_name=new_branding.get("app_name"),
        primary_color=new_branding.get("primary_color"),
        logo_url=new_branding.get("logo_url"),
        has_logo=new_branding.get("has_logo", False),
    )


@router.post("/{tenant_id}/logo", response_model=BrandingResponse)
async def upload_tenant_logo(
    tenant_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> BrandingResponse:
    """Upload a logo for a tenant.
    
    Tenant admins can only upload to their own tenant.
    Platform admins can upload to any tenant.
    
    Accepts PNG and JPG files, max 2MB.
    """
    verify_tenant_ownership(current_user, tenant_id)
    
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Save the logo file
    try:
        await save_logo(tenant_id, file)
    except InvalidFileTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileTooLargeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Update branding to reflect new logo
    existing_branding = tenant.branding or {}
    new_branding = {
        **existing_branding,
        "has_logo": True,
        "logo_url": get_logo_url(tenant_id),
    }
    await repo.update(tenant, {"branding": new_branding})
    
    return BrandingResponse(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        app_name=new_branding.get("app_name"),
        primary_color=new_branding.get("primary_color"),
        logo_url=new_branding.get("logo_url"),
        has_logo=True,
    )


@router.delete("/{tenant_id}/logo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant_logo(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Delete a tenant's logo.
    
    Tenant admins can only delete their own tenant's logo.
    Platform admins can delete any tenant's logo.
    """
    verify_tenant_ownership(current_user, tenant_id)
    
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    # Delete the logo file
    delete_logo(tenant_id)
    
    # Update branding to reflect logo removal
    existing_branding = tenant.branding or {}
    new_branding = {
        **existing_branding,
        "has_logo": False,
        "logo_url": None,
    }
    await repo.update(tenant, {"branding": new_branding})


@router.get("/{tenant_id}/logo")
async def get_tenant_logo(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Get a tenant's logo file.
    
    This is a PUBLIC endpoint - no authentication required.
    Used by client apps to display tenant logos.
    """
    repo = TenantRepository(db)
    tenant = await repo.get(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    logo_path = get_logo_path(tenant_id)
    
    if not logo_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No logo found for this tenant",
        )
    
    mime_type = get_logo_mime_type(tenant_id) or "image/png"
    
    return FileResponse(
        path=str(logo_path),
        media_type=mime_type,
        filename=f"{tenant.slug}-logo{logo_path.suffix}",
        headers={"Cache-Control": "public, max-age=86400"},  # 24 hours
    )

