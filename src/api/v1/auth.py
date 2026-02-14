"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.schemas.auth import TokenResponse, RefreshTokenRequest
from src.models.user import User
from src.models.tenant import Tenant
from src.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from pydantic import BaseModel

# Redefine LoginRequest locally to avoid import issues or EmailStr issues
class SimpleLoginRequest(BaseModel):
    email: str
    password: str

router = APIRouter()

async def check_tenant_active(db: AsyncSession, tenant_id: str) -> bool:
    """Check if a tenant is active."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    return tenant is not None and tenant.is_active


@router.post("/login", response_model=TokenResponse)
async def login(
    request: SimpleLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        # Inline query to avoid repo dependency issues
        query = (
            select(User)
            .where(User.email == request.email)
            .options(selectinload(User.roles))
        )
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
        
        # Check if user's tenant is active
        if not await check_tenant_active(db, str(user.tenant_id)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your organization's account has been deactivated. Please contact support.",
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
        
        # Load roles
        roles = [role.name for role in user.roles]
        
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
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except Exception as e:
        # Re-raise HTTP exceptions as is
        if isinstance(e, HTTPException):
            raise e
        # Log other errors and raise 500
        import traceback
        traceback.print_exc()
        raise e

# ... keep other endpoints as they were ...
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # We can use UserRepository here as it was before, assuming it works for other things
    from src.db.repositories.user_repo import UserRepository
    repo = UserRepository(db)
    
    payload = decode_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await repo.get_with_roles(payload.sub)
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
    
    if not await check_tenant_active(db, str(user.tenant_id)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your organization's account has been deactivated. Please contact support.",
        )
    
    roles = [role.name for role in user.roles]
    
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
    return {"message": "Successfully logged out"}
