"""Client authentication endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import (
    verify_password,
    hash_password,
    create_client_access_token,
    create_client_refresh_token,
    decode_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from src.db.session import get_db
from src.api.deps import get_current_tenant_admin
from src.models.client import Client
from src.models.client_user import ClientUser
from src.models.tenant import Tenant
from src.schemas.client_auth import (
    ClientLoginRequest,
    ClientRegisterRequest,
    ClientTokenResponse,
    ClientRefreshRequest,
    ClientUserProfile,
    MessageResponse,
)

router = APIRouter(prefix="/client/auth", tags=["Client Authentication"])
security = HTTPBearer(auto_error=False)


async def get_client_user_by_email(db: AsyncSession, email: str) -> Optional[ClientUser]:
    """Get a ClientUser by email."""
    result = await db.execute(
        select(ClientUser)
        .options(selectinload(ClientUser.client))
        .where(ClientUser.email == email)
    )
    return result.scalar_one_or_none()


async def get_client_user_by_id(db: AsyncSession, client_user_id: str) -> Optional[ClientUser]:
    """Get a ClientUser by ID."""
    result = await db.execute(
        select(ClientUser)
        .options(selectinload(ClientUser.client))
        .where(ClientUser.id == client_user_id)
    )
    return result.scalar_one_or_none()


async def check_tenant_active(db: AsyncSession, tenant_id: str) -> bool:
    """Check if a tenant is active."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    return tenant is not None and tenant.is_active


@router.post(
    "/register",
    response_model=ClientUserProfile,
    status_code=status.HTTP_201_CREATED,
    summary="Register a client user",
    description="Create a ClientUser account for an existing Client record. "
                "Requires tenant admin authentication. Admin can only register "
                "users for clients within their own tenant.",
)
async def register_client_user(
    request: ClientRegisterRequest,
    current_admin: dict = Depends(get_current_tenant_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientUserProfile:
    """Register a new client user for an existing client.
    
    Security:
    - Requires tenant admin or higher authentication
    - Admin can only register users for clients in their own tenant
    """
    
    # Check if email already exists
    existing_user = await get_client_user_by_email(db, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Get the client record
    result = await db.execute(
        select(Client).where(Client.id == request.client_id)
    )
    client = result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    
    # SECURITY: Verify admin belongs to the same tenant as the client
    admin_tenant_id = current_admin.get("tenant_id")
    if admin_tenant_id and str(client.tenant_id) != str(admin_tenant_id):
        # Platform admins (super_admin, platform_admin) have null tenant_id and can register for any tenant
        admin_roles = set(current_admin.get("roles", []))
        platform_roles = {"super_admin", "platform_admin"}
        if not platform_roles.intersection(admin_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only register users for clients in your own organization",
            )
    
    # Check if client already has a user account
    existing_client_user = await db.execute(
        select(ClientUser).where(ClientUser.client_id == request.client_id)
    )
    if existing_client_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client already has a user account",
        )
    
    # Check tenant is active
    if not await check_tenant_active(db, client.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not active",
        )
    
    # Create the client user
    client_user = ClientUser(
        client_id=request.client_id,
        tenant_id=client.tenant_id,
        email=request.email,
        hashed_password=hash_password(request.password),
        is_active=True,
    )
    
    db.add(client_user)
    await db.commit()
    await db.refresh(client_user)
    
    # Reload with client relationship
    client_user = await get_client_user_by_id(db, client_user.id)
    
    return ClientUserProfile(
        id=client_user.id,
        client_id=client_user.client_id,
        tenant_id=client_user.tenant_id,
        email=client_user.email,
        client_name=client_user.display_name,
        is_active=client_user.is_active,
        last_login_at=client_user.last_login_at,
        mfa_enabled=client_user.mfa_enabled,
        created_at=client_user.created_at,
    )


@router.post(
    "/login",
    response_model=ClientTokenResponse,
    summary="Client login",
    description="Authenticate a client and receive access and refresh tokens.",
)
async def login(
    request: ClientLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> ClientTokenResponse:
    """Authenticate a client and return tokens."""
    
    # Find client user by email
    client_user = await get_client_user_by_email(db, request.email)
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Verify password
    if not verify_password(request.password, client_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Check if account is active
    if not client_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    
    # Check if tenant is active
    if not await check_tenant_active(db, client_user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization's account has been deactivated",
        )
    
    # Update last login
    client_user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    
    # Generate tokens
    access_token = create_client_access_token(
        client_user_id=client_user.id,
        client_id=client_user.client_id,
        tenant_id=client_user.tenant_id,
    )
    refresh_token = create_client_refresh_token(
        client_user_id=client_user.id,
        client_id=client_user.client_id,
        tenant_id=client_user.tenant_id,
    )
    
    return ClientTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        client_id=client_user.client_id,
        client_name=client_user.display_name,
        tenant_id=client_user.tenant_id,
    )


@router.post(
    "/refresh",
    response_model=ClientTokenResponse,
    summary="Refresh access token",
    description="Get a new access token using a valid refresh token.",
)
async def refresh_token(
    request: ClientRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> ClientTokenResponse:
    """Refresh an access token using a refresh token."""
    
    # Decode the refresh token
    payload = decode_token(request.refresh_token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    # Verify it's a client refresh token
    if payload.user_type != "client":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    
    # Get the client user
    client_user = await get_client_user_by_id(db, payload.sub)
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not client_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    
    # Check if tenant is still active
    if not await check_tenant_active(db, client_user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization's account has been deactivated",
        )
    
    # Generate new tokens
    access_token = create_client_access_token(
        client_user_id=client_user.id,
        client_id=client_user.client_id,
        tenant_id=client_user.tenant_id,
    )
    new_refresh_token = create_client_refresh_token(
        client_user_id=client_user.id,
        client_id=client_user.client_id,
        tenant_id=client_user.tenant_id,
    )
    
    return ClientTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        client_id=client_user.client_id,
        client_name=client_user.display_name,
        tenant_id=client_user.tenant_id,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Client logout",
    description="Log out the current client session. "
                "Note: JWT tokens are stateless, so this is primarily for client-side cleanup.",
)
async def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> MessageResponse:
    """Logout endpoint for client cleanup.
    
    Note: Since JWTs are stateless, actual token invalidation would require
    a token blacklist (not implemented in MVP). This endpoint exists for 
    client-side coordination and future token blacklist support.
    """
    # In a production system, you would add the token to a blacklist here
    # For MVP, we just acknowledge the logout request
    return MessageResponse(
        message="Logged out successfully",
        success=True,
    )


@router.get(
    "/me",
    response_model=ClientUserProfile,
    summary="Get current client profile",
    description="Get the profile of the currently authenticated client.",
)
async def get_current_client_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> ClientUserProfile:
    """Get the current authenticated client's profile."""
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode and validate token
    payload = decode_token(credentials.credentials)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify it's a client token
    if payload.user_type != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required",
        )
    
    # Get the client user
    client_user = await get_client_user_by_id(db, payload.sub)
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client user not found",
        )
    
    if not client_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    
    # Fetch client and tenant info for extended profile
    from src.models.client import Client
    from src.models.tenant import Tenant
    
    client_result = await db.execute(
        select(Client).where(Client.id == client_user.client_id)
    )
    client = client_result.scalar_one_or_none()
    
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == client_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    
    return ClientUserProfile(
        id=client_user.id,
        client_id=client_user.client_id,
        tenant_id=client_user.tenant_id,
        email=client_user.email,
        client_name=client_user.display_name,
        is_active=client_user.is_active,
        last_login_at=client_user.last_login_at,
        mfa_enabled=client_user.mfa_enabled,
        created_at=client_user.created_at,
        tenant_name=tenant.name if tenant else None,
        risk_profile=client.risk_profile.value if client and client.risk_profile else None,
    )

