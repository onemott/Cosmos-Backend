"""Client management endpoints.

AUTHORIZATION MODEL:
- Clients are ALWAYS scoped to tenant_id.
- Even super admins can only see/manage clients within their OWN tenant.
- Super admins manage the platform (tenants, users), not other EAMs' clients.
- If your company needs to manage its own clients, it does so as a normal tenant.

ROLE-BASED ACCESS:
- tenant_admin: Can see all clients in tenant
- eam_supervisor: Can see own assigned + all subordinates' assigned clients
- eam_staff: Can only see own assigned clients
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.db.repositories.client_repo import ClientRepository
from src.db.repositories.user_repo import UserRepository
from src.schemas.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientSummaryResponse,
)
from src.api.deps import (
    get_current_user,
    get_current_tenant_admin,
    get_supervisor_or_higher,
    get_user_role_level,
    is_tenant_admin as deps_is_tenant_admin,
    is_supervisor as deps_is_supervisor,
)
from src.models.client import Client
from src.models.account import Account
from src.models.document import Document

router = APIRouter()


class ReassignClientRequest(BaseModel):
    """Request to reassign a client to another user."""
    new_assignee_id: Optional[str] = None


class ClientWithAssigneeResponse(ClientSummaryResponse):
    """Client summary with assignee information."""
    assigned_to_user_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_name: Optional[str] = None


@router.get("/", response_model=List[ClientWithAssigneeResponse])
async def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    kyc_status: Optional[str] = Query(None, description="Filter by KYC status (pending, in_progress, approved, rejected, expired)"),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user ID"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[ClientWithAssigneeResponse]:
    """List clients for the current user's tenant with role-based filtering.

    Access rules:
    - tenant_admin: See all clients in tenant
    - eam_supervisor: See own assigned + all subordinates' assigned clients
    - eam_staff: See only own assigned clients
    """
    client_repo = ClientRepository(db)
    user_repo = UserRepository(db)

    # STRICT TENANT SCOPING: Always filter by current user's tenant
    tenant_id = current_user.get("tenant_id")
    user_id = current_user.get("user_id")

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant to access clients",
        )

    # Determine role level and get subordinate IDs if needed
    role_level = get_user_role_level(current_user)
    subordinate_ids = []
    
    if role_level in ["eam_supervisor"]:
        # Get all subordinate IDs for supervisor
        subordinate_ids = await user_repo.get_all_subordinate_ids(user_id)
    elif role_level in ["platform_admin", "tenant_admin"]:
        role_level = "tenant_admin"  # Normalize for filtering
    elif role_level == "eam_staff":
        pass  # Will only see own clients
    else:
        # For other roles, default to staff-level access
        role_level = "eam_staff"

    # Use role-based filtering
    clients = await client_repo.get_clients_for_role(
        user_id=user_id,
        subordinate_ids=subordinate_ids,
        tenant_id=tenant_id,
        role_level=role_level,
        skip=skip,
        limit=limit,
        search=search,
        assigned_to=assigned_to,
    )

    # Apply kyc_status filter if provided
    if kyc_status:
        clients = [c for c in clients if c.kyc_status == kyc_status]

    # Build summary responses with AUM and assignee info
    result = []
    for client in clients:
        aum = await client_repo.get_client_aum(client.id)
        
        # Get assignee name if assigned
        assigned_to_name = None
        if client.assigned_to_user_id:
            assignee = await user_repo.get(client.assigned_to_user_id)
            if assignee:
                assigned_to_name = f"{assignee.first_name} {assignee.last_name}"
        
        # Get creator name if available
        created_by_name = None
        if client.created_by_user_id:
            creator = await user_repo.get(client.created_by_user_id)
            if creator:
                created_by_name = f"{creator.first_name} {creator.last_name}"
        
        result.append(
            ClientWithAssigneeResponse(
                id=client.id,
                display_name=client.display_name,
                client_type=client.client_type,
                kyc_status=client.kyc_status,
                total_aum=float(aum) if aum else None,
                assigned_to_user_id=client.assigned_to_user_id,
                assigned_to_name=assigned_to_name,
                created_by_user_id=client.created_by_user_id,
                created_by_name=created_by_name,
            )
        )

    return result


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    client_in: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ClientResponse:
    """Create a new client.
    
    The client will automatically be:
    - Assigned to the current user (assigned_to_user_id)
    - Marked as created by the current user (created_by_user_id)
    """
    repo = ClientRepository(db)

    # Check if email already exists in tenant
    tenant_id = current_user.get("tenant_id", "00000000-0000-0000-0000-000000000000")
    user_id = current_user.get("user_id")
    
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
    client_data["created_by_user_id"] = user_id
    
    # Auto-assign to creator if not explicitly assigned
    if not client_data.get("assigned_to_user_id"):
        client_data["assigned_to_user_id"] = user_id

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


# ============================================================================
# Client Assignment Endpoints
# ============================================================================


@router.get("/my-assigned", response_model=List[ClientWithAssigneeResponse])
async def get_my_assigned_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[ClientWithAssigneeResponse]:
    """Get clients assigned to the current user.
    
    Quick filter to show only clients where assigned_to_user_id = current user.
    """
    client_repo = ClientRepository(db)
    user_repo = UserRepository(db)
    
    tenant_id = current_user.get("tenant_id")
    user_id = current_user.get("user_id")
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant to access clients",
        )
    
    clients = await client_repo.get_clients_by_assignee(
        user_id=user_id,
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
    )
    
    # Apply search if provided
    if search:
        search_lower = search.lower()
        clients = [c for c in clients if 
                   (c.email and search_lower in c.email.lower()) or
                   (c.first_name and search_lower in c.first_name.lower()) or
                   (c.last_name and search_lower in c.last_name.lower()) or
                   (c.entity_name and search_lower in c.entity_name.lower())]
    
    result = []
    for client in clients:
        aum = await client_repo.get_client_aum(client.id)
        result.append(
            ClientWithAssigneeResponse(
                id=client.id,
                display_name=client.display_name,
                client_type=client.client_type,
                kyc_status=client.kyc_status,
                total_aum=float(aum) if aum else None,
                assigned_to_user_id=client.assigned_to_user_id,
                assigned_to_name=f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip() or None,
                created_by_user_id=client.created_by_user_id,
                created_by_name=None,  # Not loading creator for performance
            )
        )
    
    return result


@router.get("/team-assigned", response_model=List[ClientWithAssigneeResponse])
async def get_team_assigned_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_supervisor_or_higher),
) -> List[ClientWithAssigneeResponse]:
    """Get clients assigned to the current user's team.
    
    For supervisors: Returns clients assigned to self + all subordinates.
    For tenant admins: Returns all clients in tenant.
    
    Requires supervisor or higher access.
    """
    client_repo = ClientRepository(db)
    user_repo = UserRepository(db)
    
    tenant_id = current_user.get("tenant_id")
    user_id = current_user.get("user_id")
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant to access clients",
        )
    
    # Get subordinate IDs
    subordinate_ids = await user_repo.get_all_subordinate_ids(user_id)
    all_team_ids = [user_id] + subordinate_ids
    
    # Check if tenant admin (can see all)
    if deps_is_tenant_admin(current_user):
        clients = await client_repo.get_clients_by_tenant(tenant_id, skip=skip, limit=limit)
    else:
        clients = await client_repo.get_clients_by_team(
            user_ids=all_team_ids,
            tenant_id=tenant_id,
            skip=skip,
            limit=limit,
        )
    
    # Apply search if provided
    if search:
        search_lower = search.lower()
        clients = [c for c in clients if 
                   (c.email and search_lower in c.email.lower()) or
                   (c.first_name and search_lower in c.first_name.lower()) or
                   (c.last_name and search_lower in c.last_name.lower()) or
                   (c.entity_name and search_lower in c.entity_name.lower())]
    
    # Build response with assignee info
    result = []
    user_cache = {}  # Cache user lookups
    
    for client in clients:
        aum = await client_repo.get_client_aum(client.id)
        
        # Get assignee name with caching
        assigned_to_name = None
        if client.assigned_to_user_id:
            if client.assigned_to_user_id not in user_cache:
                assignee = await user_repo.get(client.assigned_to_user_id)
                user_cache[client.assigned_to_user_id] = assignee
            assignee = user_cache.get(client.assigned_to_user_id)
            if assignee:
                assigned_to_name = f"{assignee.first_name} {assignee.last_name}"
        
        result.append(
            ClientWithAssigneeResponse(
                id=client.id,
                display_name=client.display_name,
                client_type=client.client_type,
                kyc_status=client.kyc_status,
                total_aum=float(aum) if aum else None,
                assigned_to_user_id=client.assigned_to_user_id,
                assigned_to_name=assigned_to_name,
                created_by_user_id=client.created_by_user_id,
                created_by_name=None,
            )
        )
    
    return result


@router.post("/{client_id}/reassign", response_model=ClientResponse)
async def reassign_client(
    client_id: str,
    request: ReassignClientRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ClientResponse:
    """Reassign a client to another user.
    
    Access rules:
    - tenant_admin: Can reassign to anyone in tenant
    - eam_supervisor: Can reassign to self or subordinates
    - eam_staff: Cannot reassign (403)
    
    Pass new_assignee_id: null to unassign.
    """
    client_repo = ClientRepository(db)
    user_repo = UserRepository(db)
    
    tenant_id = current_user.get("tenant_id")
    user_id = current_user.get("user_id")
    
    client = await client_repo.get(client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    
    if client.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Permission check based on role
    role_level = get_user_role_level(current_user)
    
    if role_level == "eam_staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff members cannot reassign clients",
        )
    
    if request.new_assignee_id:
        # Validate new assignee exists and is in same tenant
        new_assignee = await user_repo.get(request.new_assignee_id)
        if not new_assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="New assignee not found",
            )
        
        if str(new_assignee.tenant_id) != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New assignee must be in the same tenant",
            )
        
        # Supervisor can only assign to self or subordinates
        if role_level == "eam_supervisor":
            subordinate_ids = await user_repo.get_all_subordinate_ids(user_id)
            allowed_ids = [user_id] + subordinate_ids
            
            if request.new_assignee_id not in allowed_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Supervisors can only assign clients to themselves or their subordinates",
                )
    
    # Perform reassignment
    client = await client_repo.reassign_client(
        client_id=client_id,
        new_assignee_id=request.new_assignee_id,
        tenant_id=tenant_id,
    )
    
    await db.commit()
    
    return ClientResponse.model_validate(client)
