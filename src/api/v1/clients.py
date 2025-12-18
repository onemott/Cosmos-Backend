"""Client management endpoints.

AUTHORIZATION MODEL:
- Clients are ALWAYS scoped to tenant_id.
- Even super admins can only see/manage clients within their OWN tenant.
- Super admins manage the platform (tenants, users), not other EAMs' clients.
- If your company needs to manage its own clients, it does so as a normal tenant.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.db.repositories.client_repo import ClientRepository
from src.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientSummaryResponse,
)
from src.api.deps import get_current_user
from src.models.client import Client
from src.models.account import Account
from src.models.document import Document

router = APIRouter()


@router.get("/", response_model=List[ClientSummaryResponse])
async def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    kyc_status: Optional[str] = Query(None, description="Filter by KYC status (pending, in_progress, approved, rejected, expired)"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[ClientSummaryResponse]:
    """List clients for the current user's tenant only.

    All users (including super admins) only see clients belonging to their own tenant.
    This ensures proper data isolation between EAM firms.
    """
    repo = ClientRepository(db)

    # STRICT TENANT SCOPING: Always filter by current user's tenant
    tenant_id = current_user.get("tenant_id")

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant to access clients",
        )

    if search:
        clients = await repo.search_clients(
            search, tenant_id=tenant_id, skip=skip, limit=limit
        )
    else:
        clients = await repo.get_clients_by_tenant(tenant_id, skip=skip, limit=limit)

    # Apply kyc_status filter if provided
    if kyc_status:
        clients = [c for c in clients if c.kyc_status == kyc_status]

    # Build summary responses with AUM
    result = []
    for client in clients:
        aum = await repo.get_client_aum(client.id)
        result.append(
            ClientSummaryResponse(
                id=client.id,
                display_name=client.display_name,
                client_type=client.client_type,
                kyc_status=client.kyc_status,
                total_aum=float(aum) if aum else None,
            )
        )

    return result


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_in: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ClientResponse:
    """Create a new client."""
    repo = ClientRepository(db)

    # Check if email already exists in tenant
    tenant_id = current_user.get("tenant_id", "00000000-0000-0000-0000-000000000000")
    if client_in.email:
        existing = await repo.get_by_email(client_in.email, tenant_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Client with email '{client_in.email}' already exists",
            )

    # Prepare client data
    client_data = client_in.model_dump()
    client_data["tenant_id"] = tenant_id

    # Create client
    client = await repo.create(client_data)

    return ClientResponse.model_validate(client)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ClientResponse:
    """Get client by ID. Only accessible if client belongs to user's tenant."""
    repo = ClientRepository(db)
    client = await repo.get(client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # STRICT TENANT SCOPING: No cross-tenant access, even for super admins
    if client.tenant_id != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return ClientResponse.model_validate(client)


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    client_in: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ClientResponse:
    """Update client. Only accessible if client belongs to user's tenant."""
    repo = ClientRepository(db)
    client = await repo.get(client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # STRICT TENANT SCOPING: No cross-tenant access, even for super admins
    if client.tenant_id != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Update only provided fields
    update_data = client_in.model_dump(exclude_unset=True)
    if update_data:
        client = await repo.update(client, update_data)

    return ClientResponse.model_validate(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Delete client. Only accessible if client belongs to user's tenant."""
    repo = ClientRepository(db)
    client = await repo.get(client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # STRICT TENANT SCOPING: No cross-tenant access, even for super admins
    if client.tenant_id != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    await repo.delete(client)


@router.get("/{client_id}/accounts")
async def get_client_accounts(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    """Get all accounts for a client. Only accessible if client belongs to user's tenant."""
    repo = ClientRepository(db)
    client = await repo.get_with_accounts(client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # STRICT TENANT SCOPING: No cross-tenant access
    if client.tenant_id != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return [
        {
            "id": acc.id,
            "account_number": acc.account_number,
            "account_name": acc.account_name,
            "account_type": acc.account_type.value,
            "currency": acc.currency,
            "total_value": float(acc.total_value),
            "cash_balance": float(acc.cash_balance),
            "is_active": acc.is_active,
        }
        for acc in client.accounts
    ]


@router.get("/{client_id}/documents")
async def get_client_documents(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    """Get all documents for a client. Only accessible if client belongs to user's tenant."""
    repo = ClientRepository(db)
    client = await repo.get(client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # STRICT TENANT SCOPING: No cross-tenant access
    if client.tenant_id != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Get documents for client
    query = select(Document).where(Document.client_id == client_id)
    result = await db.execute(query)
    documents = result.scalars().all()

    return [
        {
            "id": doc.id,
            "name": doc.name,
            "document_type": (
                doc.document_type.value
                if hasattr(doc.document_type, "value")
                else doc.document_type
            ),
            "file_path": doc.s3_key,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
        for doc in documents
    ]


# ============================================================================
# Client Module Endpoints
# ============================================================================

from src.models.module import Module, TenantModule, ClientModule
from src.schemas.module import ClientModuleResponse
from src.api.deps import get_current_tenant_admin
from sqlalchemy import and_


@router.get("/{client_id}/modules", response_model=List[ClientModuleResponse])
async def get_client_modules(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[ClientModuleResponse]:
    """Get all modules for a client with their enabled status.
    
    Returns modules that are:
    - Active globally (module.is_active=True)
    - Enabled for the tenant (is_core=True OR tenant_modules.is_enabled=True)
    
    For each module, is_client_enabled indicates if the client has access.
    """
    repo = ClientRepository(db)
    client = await repo.get(client_id)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    
    # STRICT TENANT SCOPING
    tenant_id = current_user.get("tenant_id")
    if client.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Get all active modules
    modules_query = select(Module).where(Module.is_active == True).order_by(Module.category, Module.name)
    modules_result = await db.execute(modules_query)
    modules = modules_result.scalars().all()
    
    # Get tenant module statuses
    tm_query = select(TenantModule).where(TenantModule.tenant_id == tenant_id)
    tm_result = await db.execute(tm_query)
    tenant_modules = {tm.module_id: tm for tm in tm_result.scalars().all()}
    
    # Get client module statuses
    cm_query = select(ClientModule).where(ClientModule.client_id == client_id)
    cm_result = await db.execute(cm_query)
    client_modules = {cm.module_id: cm for cm in cm_result.scalars().all()}
    
    # Build response
    response = []
    for module in modules:
        tm = tenant_modules.get(module.id)
        cm = client_modules.get(module.id)
        
        # Check if tenant has access (core or explicitly enabled)
        is_tenant_enabled = module.is_core or (tm is not None and tm.is_enabled)
        
        # Client is enabled if:
        # - Module is core (always enabled), OR
        # - Tenant has access AND (no client_module record OR client_module.is_enabled=True)
        if module.is_core:
            is_client_enabled = True
        elif not is_tenant_enabled:
            is_client_enabled = False
        else:
            # Tenant has access; check client-level override
            # Default to enabled if no ClientModule record exists
            is_client_enabled = cm.is_enabled if cm is not None else True
        
        response.append(ClientModuleResponse(
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
            is_tenant_enabled=is_tenant_enabled,
            is_client_enabled=is_client_enabled,
            created_at=module.created_at,
            updated_at=module.updated_at,
        ))
    
    return response


@router.post("/{client_id}/modules/{module_id}/enable", response_model=ClientModuleResponse)
async def enable_client_module(
    client_id: str,
    module_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ClientModuleResponse:
    """Enable a module for a specific client (tenant admin only).
    
    The module must be enabled for the tenant first.
    Core modules are always enabled.
    """
    repo = ClientRepository(db)
    client = await repo.get(client_id)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    
    tenant_id = current_user.get("tenant_id")
    if client.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
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
            detail="Core modules are always enabled",
        )
    
    # Check tenant has access to this module
    tm_query = select(TenantModule).where(
        and_(TenantModule.tenant_id == tenant_id, TenantModule.module_id == module_id)
    )
    tm_result = await db.execute(tm_query)
    tm = tm_result.scalar_one_or_none()
    
    if not tm or not tm.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Module is not enabled for your tenant. Request access from platform admin first.",
        )
    
    # Find or create ClientModule record
    cm_query = select(ClientModule).where(
        and_(ClientModule.client_id == client_id, ClientModule.module_id == module_id)
    )
    cm_result = await db.execute(cm_query)
    cm = cm_result.scalar_one_or_none()
    
    if cm:
        cm.is_enabled = True
    else:
        cm = ClientModule(
            tenant_id=tenant_id,
            client_id=client_id,
            module_id=module_id,
            is_enabled=True,
        )
        db.add(cm)
    
    await db.commit()
    
    return ClientModuleResponse(
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
        is_tenant_enabled=True,
        is_client_enabled=True,
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


@router.post("/{client_id}/modules/{module_id}/disable", response_model=ClientModuleResponse)
async def disable_client_module(
    client_id: str,
    module_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ClientModuleResponse:
    """Disable a module for a specific client (tenant admin only).
    
    Core modules cannot be disabled.
    """
    repo = ClientRepository(db)
    client = await repo.get(client_id)
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    
    tenant_id = current_user.get("tenant_id")
    if client.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
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
    
    # Check tenant has access to this module
    tm_query = select(TenantModule).where(
        and_(TenantModule.tenant_id == tenant_id, TenantModule.module_id == module_id)
    )
    tm_result = await db.execute(tm_query)
    tm = tm_result.scalar_one_or_none()
    is_tenant_enabled = tm is not None and tm.is_enabled
    
    # Find or create ClientModule record
    cm_query = select(ClientModule).where(
        and_(ClientModule.client_id == client_id, ClientModule.module_id == module_id)
    )
    cm_result = await db.execute(cm_query)
    cm = cm_result.scalar_one_or_none()
    
    if cm:
        cm.is_enabled = False
    else:
        cm = ClientModule(
            tenant_id=tenant_id,
            client_id=client_id,
            module_id=module_id,
            is_enabled=False,
        )
        db.add(cm)
    
    await db.commit()
    
    return ClientModuleResponse(
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
        is_tenant_enabled=is_tenant_enabled,
        is_client_enabled=False,
        created_at=module.created_at,
        updated_at=module.updated_at,
    )
