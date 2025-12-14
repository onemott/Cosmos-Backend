"""Module/feature flag endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.api.deps import (
    get_current_user,
    get_current_superuser,
    get_platform_user,
    get_current_tenant_admin,
)
from src.models.module import Module, TenantModule, ModuleCategory
from src.models.tenant import Tenant
from src.schemas.module import (
    ModuleResponse,
    TenantModuleResponse,
    ModuleCreate,
    ModuleUpdate,
    ModuleAccessRequest,
    ModuleAccessRequestResponse,
)

router = APIRouter()


# ============================================================================
# Module Listing Endpoints
# ============================================================================


@router.get("/", response_model=List[TenantModuleResponse])
async def list_my_tenant_modules(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[TenantModuleResponse]:
    """List available modules for current user's tenant with enabled status.

    For each module:
    - Core modules (is_core=True) are always enabled
    - Non-core modules are enabled only if there's a TenantModule record with is_enabled=True
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )

    # Get all active modules with their tenant-specific status
    query = (
        select(Module)
        .where(Module.is_active == True)
        .order_by(Module.category, Module.name)
    )
    result = await db.execute(query)
    modules = result.scalars().all()

    # Get tenant module statuses
    tm_query = select(TenantModule).where(TenantModule.tenant_id == tenant_id)
    tm_result = await db.execute(tm_query)
    tenant_modules = {tm.module_id: tm for tm in tm_result.scalars().all()}

    # Build response with effective enabled status
    response = []
    for module in modules:
        tm = tenant_modules.get(module.id)
        # Core modules are always enabled; non-core need explicit TenantModule.is_enabled=True
        is_enabled = module.is_core or (tm is not None and tm.is_enabled)

        response.append(
            TenantModuleResponse(
                id=module.id,
                code=module.code,
                name=module.name,
                name_zh=module.name_zh,
                description=module.description,
                description_zh=module.description_zh,
                category=module.category,
                version=module.version,
                is_core=module.is_core,
                is_active=module.is_active,
                is_enabled=is_enabled,
                created_at=module.created_at,
                updated_at=module.updated_at,
            )
        )

    return response


@router.get("/all", response_model=List[ModuleResponse])
async def list_all_modules(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_platform_user),
) -> List[ModuleResponse]:
    """List all modules in the platform catalogue (platform users only).

    Returns all modules regardless of active status for platform administration.
    """
    query = select(Module).order_by(Module.category, Module.name)
    result = await db.execute(query)
    modules = result.scalars().all()

    return [ModuleResponse.model_validate(m) for m in modules]


@router.get("/tenant/{tenant_id}", response_model=List[TenantModuleResponse])
async def list_tenant_modules(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_platform_user),
) -> List[TenantModuleResponse]:
    """List modules for a specific tenant with their enabled status (platform users only).

    Platform users can view any tenant's module configuration.
    """
    # Verify tenant exists
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Get all active modules
    query = (
        select(Module)
        .where(Module.is_active == True)
        .order_by(Module.category, Module.name)
    )
    result = await db.execute(query)
    modules = result.scalars().all()

    # Get tenant module statuses
    tm_query = select(TenantModule).where(TenantModule.tenant_id == tenant_id)
    tm_result = await db.execute(tm_query)
    tenant_modules = {tm.module_id: tm for tm in tm_result.scalars().all()}

    # Build response
    response = []
    for module in modules:
        tm = tenant_modules.get(module.id)
        is_enabled = module.is_core or (tm is not None and tm.is_enabled)

        response.append(
            TenantModuleResponse(
                id=module.id,
                code=module.code,
                name=module.name,
                name_zh=module.name_zh,
                description=module.description,
                description_zh=module.description_zh,
                category=module.category,
                version=module.version,
                is_core=module.is_core,
                is_active=module.is_active,
                is_enabled=is_enabled,
                created_at=module.created_at,
                updated_at=module.updated_at,
            )
        )

    return response


# ============================================================================
# Module Enable/Disable Endpoints (Platform Admin Only)
# ============================================================================


@router.post("/{module_id}/enable", response_model=TenantModuleResponse)
async def enable_module(
    module_id: str,
    tenant_id: str = Query(..., description="The tenant ID to enable the module for"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> TenantModuleResponse:
    """Enable a module for a specific tenant (platform admin only).

    Core modules are always enabled and cannot be toggled.
    """
    # Get the module
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    if not module.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot enable an inactive module",
        )

    if module.is_core:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Core modules are always enabled and cannot be toggled",
        )

    # Verify tenant exists
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Find or create TenantModule record
    query = select(TenantModule).where(
        and_(TenantModule.tenant_id == tenant_id, TenantModule.module_id == module_id)
    )
    result = await db.execute(query)
    tm = result.scalar_one_or_none()

    if tm:
        tm.is_enabled = True
    else:
        tm = TenantModule(
            tenant_id=tenant_id,
            module_id=module_id,
            is_enabled=True,
        )
        db.add(tm)

    await db.commit()

    return TenantModuleResponse(
        id=module.id,
        code=module.code,
        name=module.name,
        name_zh=module.name_zh,
        description=module.description,
        description_zh=module.description_zh,
        category=module.category,
        version=module.version,
        is_core=module.is_core,
        is_active=module.is_active,
        is_enabled=True,
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


@router.post("/{module_id}/disable", response_model=TenantModuleResponse)
async def disable_module(
    module_id: str,
    tenant_id: str = Query(..., description="The tenant ID to disable the module for"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> TenantModuleResponse:
    """Disable a module for a specific tenant (platform admin only).

    Core modules cannot be disabled.
    """
    # Get the module
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    if module.is_core:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Core modules cannot be disabled",
        )

    # Verify tenant exists
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Find or create TenantModule record
    query = select(TenantModule).where(
        and_(TenantModule.tenant_id == tenant_id, TenantModule.module_id == module_id)
    )
    result = await db.execute(query)
    tm = result.scalar_one_or_none()

    if tm:
        tm.is_enabled = False
    else:
        tm = TenantModule(
            tenant_id=tenant_id,
            module_id=module_id,
            is_enabled=False,
        )
        db.add(tm)

    await db.commit()

    return TenantModuleResponse(
        id=module.id,
        code=module.code,
        name=module.name,
        name_zh=module.name_zh,
        description=module.description,
        description_zh=module.description_zh,
        category=module.category,
        version=module.version,
        is_core=module.is_core,
        is_active=module.is_active,
        is_enabled=False,
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


# ============================================================================
# Module CRUD Endpoints (Platform Admin Only)
# ============================================================================


@router.post("/", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(
    module_in: ModuleCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> ModuleResponse:
    """Create a new module in the platform catalogue (platform admin only)."""
    # Check if code already exists
    query = select(Module).where(Module.code == module_in.code)
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Module with code '{module_in.code}' already exists",
        )

    # Create module
    module = Module(**module_in.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)

    return ModuleResponse.model_validate(module)


@router.get("/{module_id}", response_model=ModuleResponse)
async def get_module(
    module_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_platform_user),
) -> ModuleResponse:
    """Get a specific module by ID (platform users only)."""
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    return ModuleResponse.model_validate(module)


@router.patch("/{module_id}", response_model=ModuleResponse)
async def update_module(
    module_id: str,
    module_in: ModuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> ModuleResponse:
    """Update a module (platform admin only).

    Note: code and is_core cannot be changed after creation.
    """
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    # Update only provided fields
    update_data = module_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(module, key, value)

    await db.commit()
    await db.refresh(module)

    return ModuleResponse.model_validate(module)


@router.delete("/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_superuser),
) -> None:
    """Delete a module (platform admin only).

    Warning: Deleting core modules will affect all tenants and clients.
    """
    module = await db.get(Module, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    await db.delete(module)
    await db.commit()


# ============================================================================
# Module Access Request Endpoint (Tenant Admins)
# ============================================================================


@router.post(
    "/requests",
    response_model=ModuleAccessRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_module_access(
    request: ModuleAccessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ModuleAccessRequestResponse:
    """Request access to a module (tenant admin only).

    This is a stub endpoint - actual messaging/notification will be implemented later.
    """
    tenant_id = current_user.get("tenant_id")

    # Verify module exists
    query = select(Module).where(Module.code == request.module_code)
    result = await db.execute(query)
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module with code '{request.module_code}' not found",
        )

    if module.is_core:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Core modules are always enabled and do not require access requests",
        )

    # Check if already enabled for this tenant
    tm_query = select(TenantModule).where(
        and_(TenantModule.tenant_id == tenant_id, TenantModule.module_id == module.id)
    )
    tm_result = await db.execute(tm_query)
    tm = tm_result.scalar_one_or_none()

    if tm and tm.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Module is already enabled for your tenant",
        )

    # TODO: Implement actual messaging/notification to platform admins
    # For now, just log and return a success response
    print(
        f"[MODULE REQUEST] Tenant {tenant_id} requested access to module {request.module_code}"
    )
    if request.message:
        print(f"  Message: {request.message}")

    return ModuleAccessRequestResponse(
        status="pending",
        message="Your request has been submitted and will be reviewed by platform administrators.",
    )
