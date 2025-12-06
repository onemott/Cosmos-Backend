"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.session import get_db
from src.schemas.auth import LoginRequest, TokenResponse, RefreshTokenRequest
from src.models.user import User
from src.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and return tokens."""
    # Look up user by email
    query = select(User).where(User.email == request.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    # Check if user exists
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )
    
    # Verify password
    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Determine user roles
    roles = []
    if user.is_superuser:
        roles.append("super_admin")
    # TODO: Load actual roles from user.roles relationship
    # For now, add basic role based on user type
    roles.append("admin")
    
    # Generate tokens
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        roles=roles,
    )
    refresh_token = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    # Verify user still exists and is active
    user = await db.get(User, payload.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )
    
    # Determine user roles
    roles = []
    if user.is_superuser:
        roles.append("super_admin")
    roles.append("admin")
    
    # Generate new tokens
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        roles=roles,
    )
    new_refresh_token = create_refresh_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout")
async def logout() -> dict:
    """Logout user (invalidate tokens).
    
    Note: With stateless JWT tokens, logout is handled client-side by
    removing the tokens. For enhanced security, implement token blacklisting
    using Redis in production.
    """
    return {"message": "Successfully logged out"}

