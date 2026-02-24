"""Invitation API endpoints for client self-registration.

This module provides:
- Admin endpoints for EAMs to create and manage invitations
- Public endpoints for clients to validate and use invitation codes
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.api.deps import get_current_user, require_tenant_user, get_current_tenant_admin
from src.models.invitation import Invitation, InvitationStatus
from src.models.client import Client, ClientType
from src.models.client_user import ClientUser
from src.models.tenant import Tenant
from src.core.security import hash_password


router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class InvitationCreate(BaseModel):
    """Schema for creating an invitation."""
    email: Optional[EmailStr] = Field(None, description="Pre-fill email for invitee")
    invitee_name: Optional[str] = Field(None, max_length=255, description="Name hint for invitee")
    message: Optional[str] = Field(None, max_length=2000, description="Message from EAM to invitee")
    client_id: Optional[str] = Field(None, description="Pre-assign to existing client record")
    expires_in_days: int = Field(7, ge=1, le=30, description="Days until expiration (1-30)")


class InvitationResponse(BaseModel):
    """Response schema for an invitation."""
    id: str
    code: str
    tenant_id: str
    tenant_name: Optional[str] = None
    email: Optional[str]
    invitee_name: Optional[str]
    message: Optional[str]
    client_id: Optional[str]
    client_name: Optional[str] = None
    status: str
    expires_at: datetime
    created_at: datetime
    created_by_user_id: Optional[str]
    created_by_name: Optional[str] = None
    used_at: Optional[datetime]
    used_by_client_user_id: Optional[str]
    is_valid: bool
    is_expired: bool

    class Config:
        from_attributes = True


class InvitationListResponse(BaseModel):
    """Paginated list of invitations."""
    invitations: List[InvitationResponse]
    total_count: int
    skip: int
    limit: int


# Public validation response
class InvitationValidateResponse(BaseModel):
    """Response for validating an invitation code."""
    valid: bool
    code: str
    email: Optional[str] = None
    invitee_name: Optional[str] = None
    message: Optional[str] = None
    tenant_name: str
    expires_at: datetime
    error: Optional[str] = None


# Registration request
class ClientRegistrationRequest(BaseModel):
    """Schema for client self-registration."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)


class ClientRegistrationResponse(BaseModel):
    """Response after successful registration."""
    success: bool
    message: str
    client_id: str
    client_user_id: str
    requires_approval: bool = False  # For future use


# ============================================================================
# Helper Functions
# ============================================================================

def normalize_invitation_code(code: str) -> str:
    """Normalize an invitation code to match database format (XXX-XXX-XXX).
    
    Handles codes entered with or without dashes.
    """
    # Remove all non-alphanumeric, uppercase
    cleaned = ''.join(c for c in code if c.isalnum()).upper()
    
    # If 9 characters, add dashes
    if len(cleaned) == 9:
        return f"{cleaned[:3]}-{cleaned[3:6]}-{cleaned[6:9]}"
    
    # Otherwise return as-is (will fail validation)
    return code.strip().upper()


def build_invitation_response(invitation: Invitation) -> InvitationResponse:
    """Build response from Invitation model."""
    # Get client name if linked
    client_name = None
    if invitation.client:
        if invitation.client.client_type == ClientType.INDIVIDUAL:
            client_name = f"{invitation.client.first_name} {invitation.client.last_name}"
        else:
            client_name = invitation.client.entity_name

    # Get creator name
    created_by_name = None
    if invitation.created_by:
        created_by_name = f"{invitation.created_by.first_name} {invitation.created_by.last_name}"

    # Get tenant name
    tenant_name = None
    if invitation.tenant:
        tenant_name = invitation.tenant.name

    return InvitationResponse(
        id=invitation.id,
        code=invitation.code,
        tenant_id=invitation.tenant_id,
        tenant_name=tenant_name,
        email=invitation.email,
        invitee_name=invitation.invitee_name,
        message=invitation.message,
        client_id=invitation.client_id,
        client_name=client_name,
        status=invitation.status.value,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        created_by_user_id=invitation.created_by_user_id,
        created_by_name=created_by_name,
        used_at=invitation.used_at,
        used_by_client_user_id=invitation.used_by_client_user_id,
        is_valid=invitation.is_valid,
        is_expired=invitation.is_expired,
    )


# ============================================================================
# Admin Endpoints
# ============================================================================

@router.post("/", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    data: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> InvitationResponse:
    """Create a new invitation for client self-registration.
    
    Only tenant admins can create invitations.
    """
    tenant_id = current_user.get("tenant_id")
    user_id = current_user.get("user_id")

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    # Validate client_id if provided
    if data.client_id:
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

        # Check if client already has a pending invitation
        existing_invitation = await db.execute(
            select(Invitation).where(
                Invitation.client_id == data.client_id,
                Invitation.status == InvitationStatus.PENDING,
            )
        )
        if existing_invitation.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Client already has a pending invitation",
            )

    # Create invitation
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)
    invitation = Invitation(
        id=str(uuid4()),
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        email=data.email,
        invitee_name=data.invitee_name,
        message=data.message,
        client_id=data.client_id,
        expires_at=expires_at,
        status=InvitationStatus.PENDING,
    )

    db.add(invitation)
    await db.commit()

    # Refresh with relationships
    await db.refresh(invitation)
    result = await db.execute(
        select(Invitation)
        .options(
            selectinload(Invitation.tenant),
            selectinload(Invitation.created_by),
            selectinload(Invitation.client),
        )
        .where(Invitation.id == invitation.id)
    )
    invitation = result.scalar_one()

    return build_invitation_response(invitation)


@router.get("/", response_model=InvitationListResponse)
async def list_invitations(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by email or name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> InvitationListResponse:
    """List invitations for the current tenant."""
    tenant_id = current_user.get("tenant_id")

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    # Build query
    query = (
        select(Invitation)
        .options(
            selectinload(Invitation.tenant),
            selectinload(Invitation.created_by),
            selectinload(Invitation.client),
        )
        .where(Invitation.tenant_id == tenant_id)
    )

    # Apply filters
    if status_filter:
        try:
            status_enum = InvitationStatus(status_filter)
            query = query.where(Invitation.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Invitation.email.ilike(search_term),
                Invitation.invitee_name.ilike(search_term),
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(Invitation.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    invitations = result.scalars().all()

    return InvitationListResponse(
        invitations=[build_invitation_response(inv) for inv in invitations],
        total_count=total_count,
        skip=skip,
        limit=limit,
    )


@router.get("/{invitation_id}", response_model=InvitationResponse)
async def get_invitation(
    invitation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> InvitationResponse:
    """Get a specific invitation by ID."""
    tenant_id = current_user.get("tenant_id")

    query = (
        select(Invitation)
        .options(
            selectinload(Invitation.tenant),
            selectinload(Invitation.created_by),
            selectinload(Invitation.client),
        )
        .where(Invitation.id == invitation_id)
    )

    if tenant_id:
        query = query.where(Invitation.tenant_id == tenant_id)

    result = await db.execute(query)
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    return build_invitation_response(invitation)


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    invitation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Cancel a pending invitation.
    
    Only pending invitations can be cancelled.
    """
    tenant_id = current_user.get("tenant_id")

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    result = await db.execute(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.tenant_id == tenant_id,
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel invitation with status: {invitation.status.value}",
        )

    invitation.cancel()
    await db.commit()


# ============================================================================
# Public Endpoints (No auth required)
# ============================================================================

@router.get("/public/{code}/validate", response_model=InvitationValidateResponse)
async def validate_invitation_code(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> InvitationValidateResponse:
    """Validate an invitation code (public endpoint).
    
    This is called by the client app to check if a code is valid before
    showing the registration form.
    """
    # Normalize code to database format (XXX-XXX-XXX)
    code = normalize_invitation_code(code)

    result = await db.execute(
        select(Invitation)
        .options(selectinload(Invitation.tenant))
        .where(Invitation.code == code)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        return InvitationValidateResponse(
            valid=False,
            code=code,
            tenant_name="",
            expires_at=datetime.now(timezone.utc),
            error="Invalid invitation code",
        )

    # Check if expired
    if invitation.is_expired:
        # Update status if needed
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.EXPIRED
            await db.commit()

        return InvitationValidateResponse(
            valid=False,
            code=code,
            tenant_name=invitation.tenant.name if invitation.tenant else "",
            expires_at=invitation.expires_at,
            error="This invitation has expired",
        )

    # Check if already used
    if invitation.status == InvitationStatus.USED:
        return InvitationValidateResponse(
            valid=False,
            code=code,
            tenant_name=invitation.tenant.name if invitation.tenant else "",
            expires_at=invitation.expires_at,
            error="This invitation has already been used",
        )

    # Check if cancelled
    if invitation.status == InvitationStatus.CANCELLED:
        return InvitationValidateResponse(
            valid=False,
            code=code,
            tenant_name=invitation.tenant.name if invitation.tenant else "",
            expires_at=invitation.expires_at,
            error="This invitation has been cancelled",
        )

    # Valid!
    return InvitationValidateResponse(
        valid=True,
        code=code,
        email=invitation.email,
        invitee_name=invitation.invitee_name,
        message=invitation.message,
        tenant_name=invitation.tenant.name if invitation.tenant else "",
        expires_at=invitation.expires_at,
    )


@router.post("/public/{code}/register", response_model=ClientRegistrationResponse)
async def register_with_invitation(
    code: str,
    data: ClientRegistrationRequest,
    db: AsyncSession = Depends(get_db),
) -> ClientRegistrationResponse:
    """Register as a client using an invitation code (public endpoint).
    
    This creates:
    1. A Client record (if not pre-assigned)
    2. A ClientUser record (login credentials)
    And marks the invitation as used.
    """
    # Normalize code to database format (XXX-XXX-XXX)
    code = normalize_invitation_code(code)

    # Fetch invitation with tenant (lock row to prevent race condition)
    result = await db.execute(
        select(Invitation)
        .options(selectinload(Invitation.tenant))
        .where(Invitation.code == code)
        .with_for_update()
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invitation code",
        )

    # Validate invitation
    if not invitation.is_valid:
        if invitation.is_expired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has expired",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is not valid (status: {invitation.status.value})",
        )

    # Check if email is already in use
    existing_user = await db.execute(
        select(ClientUser).where(ClientUser.email == data.email)
    )
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Create or use pre-assigned client
    if invitation.client_id:
        # Use pre-assigned client
        client_result = await db.execute(
            select(Client).where(Client.id == invitation.client_id)
        )
        client = client_result.scalar_one_or_none()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Pre-assigned client not found",
            )
        # Update client info if needed
        if not client.email:
            client.email = data.email
        if not client.phone and data.phone:
            client.phone = data.phone
    else:
        # Create new client
        client = Client(
            id=str(uuid4()),
            tenant_id=invitation.tenant_id,
            client_type=ClientType.INDIVIDUAL,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            kyc_status="pending",  # New clients start with pending KYC
        )
        db.add(client)
        await db.flush()

    # Create ClientUser
    client_user = ClientUser(
        id=str(uuid4()),
        client_id=client.id,
        tenant_id=invitation.tenant_id,
        email=data.email,
        hashed_password=hash_password(data.password),
        is_active=True,
    )
    db.add(client_user)
    await db.flush()

    # Mark invitation as used
    invitation.mark_as_used(client_user.id)

    await db.commit()

    return ClientRegistrationResponse(
        success=True,
        message="Registration successful! You can now log in.",
        client_id=client.id,
        client_user_id=client_user.id,
        requires_approval=False,
    )

