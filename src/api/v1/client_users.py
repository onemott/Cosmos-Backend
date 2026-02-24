"""Client Users API - Admin endpoints for managing client login credentials.

This module provides EAM staff with the ability to:
- Create login credentials for clients
- View client user accounts
- Reset passwords
- Enable/disable client access
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.api.deps import get_current_user, require_tenant_user, get_current_tenant_admin
from src.models.client_user import ClientUser
from src.models.client import Client
from src.core.security import hash_password, generate_temp_password

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class ClientUserCreate(BaseModel):
    """Schema for creating a client user account."""
    client_id: str = Field(..., description="ID of the client to create credentials for")
    email: EmailStr = Field(..., description="Login email for the client")
    password: Optional[str] = Field(None, min_length=8, description="Password (auto-generated if not provided)")
    send_welcome_email: bool = Field(default=False, description="Send welcome email with credentials")


class ClientUserUpdate(BaseModel):
    """Schema for updating a client user account."""
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class ClientUserPasswordReset(BaseModel):
    """Schema for resetting a client user's password."""
    new_password: Optional[str] = Field(None, min_length=8, description="New password (auto-generated if not provided)")
    send_email: bool = Field(default=False, description="Send email with new password")


class ClientUserResponse(BaseModel):
    """Response schema for client user."""
    id: str
    client_id: str
    tenant_id: str
    email: str
    is_active: bool
    mfa_enabled: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Client info
    client_name: Optional[str] = None
    client_type: Optional[str] = None

    class Config:
        from_attributes = True


class ClientUserCreateResponse(BaseModel):
    """Response after creating a client user (includes temp password if generated)."""
    id: str
    client_id: str
    email: str
    is_active: bool
    temp_password: Optional[str] = Field(None, description="Temporary password (only shown once)")
    message: str


class ClientUserListResponse(BaseModel):
    """Paginated list of client users."""
    client_users: list[ClientUserResponse]
    total_count: int
    skip: int
    limit: int


class PasswordResetResponse(BaseModel):
    """Response after password reset."""
    success: bool
    message: str
    temp_password: Optional[str] = Field(None, description="New temporary password (only shown once)")


# ============================================================================
# Helper Functions
# ============================================================================

def build_client_user_response(client_user: ClientUser) -> ClientUserResponse:
    """Build response from ClientUser model."""
    client_name = None
    client_type = None
    
    if client_user.client:
        client_type = client_user.client.client_type.value if hasattr(client_user.client.client_type, 'value') else str(client_user.client.client_type)
        if client_type == "individual":
            client_name = f"{client_user.client.first_name} {client_user.client.last_name}"
        else:
            client_name = client_user.client.entity_name
    
    return ClientUserResponse(
        id=client_user.id,
        client_id=client_user.client_id,
        tenant_id=client_user.tenant_id,
        email=client_user.email,
        is_active=client_user.is_active,
        mfa_enabled=client_user.mfa_enabled,
        last_login_at=client_user.last_login_at,
        created_at=client_user.created_at,
        updated_at=client_user.updated_at,
        client_name=client_name,
        client_type=client_type,
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/", response_model=ClientUserListResponse)
async def list_client_users(
    search: Optional[str] = Query(None, description="Search by email or client name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> ClientUserListResponse:
    """List all client users for the current tenant.
    
    EAM staff can see all client credentials they've created.
    """
    tenant_id = current_user.get("tenant_id")
    
    # Build query with client relationship
    query = (
        select(ClientUser)
        .options(selectinload(ClientUser.client))
    )
    
    # Tenant scoping
    if tenant_id:
        query = query.where(ClientUser.tenant_id == tenant_id)
    
    # Apply filters
    if is_active is not None:
        query = query.where(ClientUser.is_active == is_active)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(ClientUser.email.ilike(search_term))
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0
    
    # Apply pagination and ordering
    query = query.order_by(ClientUser.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    client_users = result.scalars().all()
    
    return ClientUserListResponse(
        client_users=[build_client_user_response(cu) for cu in client_users],
        total_count=total_count,
        skip=skip,
        limit=limit,
    )


@router.get("/{client_user_id}", response_model=ClientUserResponse)
async def get_client_user(
    client_user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> ClientUserResponse:
    """Get a specific client user by ID."""
    tenant_id = current_user.get("tenant_id")
    
    query = (
        select(ClientUser)
        .options(selectinload(ClientUser.client))
        .where(ClientUser.id == client_user_id)
    )
    
    if tenant_id:
        query = query.where(ClientUser.tenant_id == tenant_id)
    
    result = await db.execute(query)
    client_user = result.scalar_one_or_none()
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client user not found",
        )
    
    return build_client_user_response(client_user)


@router.post("/", response_model=ClientUserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_client_user(
    data: ClientUserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ClientUserCreateResponse:
    """Create login credentials for a client.
    
    Only tenant admins can create client credentials.
    The client must exist and belong to the same tenant.
    """
    tenant_id = current_user.get("tenant_id")
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )
    
    # Verify client exists and belongs to tenant
    client_result = await db.execute(
        select(Client).where(
            Client.id == data.client_id,
            Client.tenant_id == tenant_id,
        )
    )
    client = client_result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found in your organization",
        )
    
    # Check if client already has credentials
    existing_result = await db.execute(
        select(ClientUser).where(ClientUser.client_id == data.client_id)
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client already has login credentials",
        )
    
    # Check if email is already in use
    email_check = await db.execute(
        select(ClientUser).where(ClientUser.email == data.email)
    )
    if email_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already in use",
        )
    
    # Generate password if not provided
    temp_password = None
    if data.password:
        password = data.password
    else:
        password = generate_temp_password()
        temp_password = password  # Return to admin for sharing with client
    
    # Create client user
    client_user = ClientUser(
        id=str(uuid4()),
        client_id=data.client_id,
        tenant_id=tenant_id,
        email=data.email,
        hashed_password=hash_password(password),
        is_active=True,
    )
    
    db.add(client_user)
    await db.commit()
    await db.refresh(client_user)
    
    # TODO: Send welcome email if requested
    # if data.send_welcome_email:
    #     send_client_welcome_email(data.email, temp_password or password)
    
    return ClientUserCreateResponse(
        id=client_user.id,
        client_id=client_user.client_id,
        email=client_user.email,
        is_active=client_user.is_active,
        temp_password=temp_password,
        message="Client credentials created successfully" + 
                (" - temporary password included" if temp_password else ""),
    )


@router.patch("/{client_user_id}", response_model=ClientUserResponse)
async def update_client_user(
    client_user_id: str,
    data: ClientUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> ClientUserResponse:
    """Update a client user's email or active status."""
    tenant_id = current_user.get("tenant_id")
    
    query = (
        select(ClientUser)
        .options(selectinload(ClientUser.client))
        .where(ClientUser.id == client_user_id)
    )
    
    if tenant_id:
        query = query.where(ClientUser.tenant_id == tenant_id)
    
    result = await db.execute(query)
    client_user = result.scalar_one_or_none()
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client user not found",
        )
    
    # Apply updates
    if data.email is not None and data.email != client_user.email:
        # Check if new email is already in use
        email_check = await db.execute(
            select(ClientUser).where(
                ClientUser.email == data.email,
                ClientUser.id != client_user_id,
            )
        )
        if email_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address is already in use",
            )
        client_user.email = data.email
    
    if data.is_active is not None:
        client_user.is_active = data.is_active
    
    await db.commit()
    await db.refresh(client_user)
    
    return build_client_user_response(client_user)


@router.post("/{client_user_id}/reset-password", response_model=PasswordResetResponse)
async def reset_client_password(
    client_user_id: str,
    data: ClientUserPasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> PasswordResetResponse:
    """Reset a client user's password.
    
    EAM admins can reset client passwords when clients forget them.
    """
    tenant_id = current_user.get("tenant_id")
    
    query = select(ClientUser).where(ClientUser.id == client_user_id)
    
    if tenant_id:
        query = query.where(ClientUser.tenant_id == tenant_id)
    
    result = await db.execute(query)
    client_user = result.scalar_one_or_none()
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client user not found",
        )
    
    # Generate or use provided password
    temp_password = None
    if data.new_password:
        password = data.new_password
    else:
        password = generate_temp_password()
        temp_password = password
    
    client_user.hashed_password = hash_password(password)
    
    await db.commit()
    
    # TODO: Send password reset email if requested
    # if data.send_email:
    #     send_password_reset_email(client_user.email, temp_password or password)
    
    return PasswordResetResponse(
        success=True,
        message="Password reset successfully" +
                (" - new temporary password included" if temp_password else ""),
        temp_password=temp_password,
    )


@router.delete("/{client_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client_user(
    client_user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Delete a client user's login credentials.
    
    This removes the client's ability to log in but does not delete the client record.
    """
    tenant_id = current_user.get("tenant_id")
    
    query = select(ClientUser).where(ClientUser.id == client_user_id)
    
    if tenant_id:
        query = query.where(ClientUser.tenant_id == tenant_id)
    
    result = await db.execute(query)
    client_user = result.scalar_one_or_none()
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client user not found",
        )
    
    await db.delete(client_user)
    await db.commit()


@router.get("/by-client/{client_id}", response_model=ClientUserResponse)
async def get_client_user_by_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> ClientUserResponse:
    """Get client user credentials by client ID.
    
    Useful for checking if a client already has login credentials.
    """
    tenant_id = current_user.get("tenant_id")
    
    query = (
        select(ClientUser)
        .options(selectinload(ClientUser.client))
        .where(ClientUser.client_id == client_id)
    )
    
    if tenant_id:
        query = query.where(ClientUser.tenant_id == tenant_id)
    
    result = await db.execute(query)
    client_user = result.scalar_one_or_none()
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No login credentials found for this client",
        )
    
    return build_client_user_response(client_user)

