"""API dependencies for authentication and authorization."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.security import decode_token, TokenPayload
from src.core.tenancy import set_current_tenant_id
from src.db.session import get_db
from src.models.tenant import Tenant
from src.models.client_user import ClientUser

security = HTTPBearer(auto_error=False)


async def check_tenant_active(db: AsyncSession, tenant_id: str) -> bool:
    """Check if a tenant is active."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    return tenant is not None and tenant.is_active

# Development mode mock user for unauthenticated requests
# Using valid UUID format for database compatibility
DEV_MOCK_USER = {
    "user_id": "00000000-0000-0000-0000-000000000001",
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "roles": ["super_admin"],
    "email": "dev@eam-platform.dev",
}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current authenticated user from JWT token.
    
    In development mode with no token, returns a mock super admin user.
    Also checks if the user's tenant is still active.
    """
    # Development mode bypass - allow unauthenticated access
    if settings.debug and (credentials is None or not credentials.credentials):
        import logging
        logging.warning("Using DEV_MOCK_USER for unauthenticated request")
        return DEV_MOCK_USER
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        # In dev mode, allow invalid tokens too
        if settings.debug:
            return DEV_MOCK_USER
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject client tokens on admin endpoints (defense-in-depth)
    if payload.user_type == "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client tokens cannot access admin APIs",
        )

    # Check if user's tenant is still active
    if payload.tenant_id:
        if not await check_tenant_active(db, payload.tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your organization's account has been deactivated. Please contact support.",
            )
        set_current_tenant_id(payload.tenant_id)

    return {
        "user_id": payload.sub,
        "tenant_id": payload.tenant_id,
        "roles": payload.roles or [],
    }


async def get_current_superuser(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Ensure current user is a platform admin (super_admin or platform_admin).
    
    Use for write operations (create/update/delete) on platform resources.
    """
    platform_roles = {"super_admin", "platform_admin"}
    user_roles = set(current_user.get("roles", []))
    
    if not platform_roles.intersection(user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required",
        )
    return current_user


async def get_platform_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Ensure current user has platform-level access (read-only or admin).
    
    Allowed roles:
    - super_admin, platform_admin: Full platform access
    - platform_user: Read-only platform access
    
    Use for read operations on platform resources like tenants list.
    """
    platform_roles = {"super_admin", "platform_admin", "platform_user"}
    user_roles = set(current_user.get("roles", []))
    
    if not platform_roles.intersection(user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform access required",
        )
    return current_user


async def get_current_tenant_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Ensure current user is a tenant admin or higher.
    
    Allowed roles:
    - super_admin, platform_admin: Platform-level access
    - tenant_admin: Tenant-level admin access
    """
    allowed_roles = {"super_admin", "platform_admin", "tenant_admin"}
    user_roles = set(current_user.get("roles", []))
    
    if not allowed_roles.intersection(user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """Get current user if authenticated, None otherwise.
    
    Useful for endpoints that work differently for authenticated vs anonymous users.
    """
    if credentials is None or not credentials.credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_permission(permission: str):
    """Dependency factory for permission checking."""

    async def check_permission(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        # TODO: Implement proper permission checking against database
        # For now, just return the user (permission check will be added later)
        return current_user

    return check_permission


def require_module(module_code: str):
    """Dependency factory for module access checking.
    
    Checks if the current user's tenant has access to the specified module.
    Core modules are always accessible.
    
    Usage:
        @router.get("/some-feature")
        async def some_feature(
            current_user: dict = Depends(require_module("custom_portfolio")),
        ):
            ...
    """
    from sqlalchemy import select, and_
    from src.models.module import Module, TenantModule
    
    async def check_module_access(
        current_user: dict = Depends(get_current_user),
        db = None,  # Will be injected via Depends in the actual route
    ) -> dict:
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must belong to a tenant",
            )
        
        # Import here to avoid circular imports
        from src.db.session import get_db
        
        # This is a placeholder - the actual implementation would need
        # to be done differently since we can't easily inject db here.
        # For now, this serves as documentation of the intended pattern.
        # The actual check should be done in the route handler or via
        # a more sophisticated dependency injection approach.
        
        # TODO: Implement actual module check when features are built
        return current_user

    return check_module_access


# ============================================================================
# Client Authentication Dependencies
# ============================================================================

async def get_current_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current authenticated client from JWT token.
    
    This dependency is for client-facing APIs only. It verifies:
    1. Token is valid and not expired
    2. Token is a client token (user_type == "client")
    3. ClientUser exists and is active
    4. Tenant is active
    
    Returns:
        dict with keys: client_user_id, client_id, tenant_id, user_type, roles
    
    Raises:
        401 if not authenticated or token invalid
        403 if account/tenant is deactivated
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify this is a client token
    if payload.user_type != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required. Staff users cannot access client APIs.",
        )
    
    # Verify client_id is present
    if not payload.client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client token",
        )

    # Load ClientUser and verify it exists and is active
    result = await db.execute(
        select(ClientUser)
        .options(selectinload(ClientUser.client))
        .where(ClientUser.id == payload.sub)
    )
    client_user = result.scalar_one_or_none()
    
    if not client_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client account not found",
        )
    
    if not client_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client account is deactivated",
        )

    # Check if tenant is still active
    if not await check_tenant_active(db, client_user.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization's account has been deactivated. Please contact support.",
        )
    
    # Set tenant context
    set_current_tenant_id(client_user.tenant_id)

    return {
        "client_user_id": str(client_user.id),
        "client_id": str(client_user.client_id),
        "tenant_id": str(client_user.tenant_id),
        "user_type": "client",
        "roles": ["client"],
        "email": client_user.email,
    }


def require_client_module(module_code: str):
    """Dependency factory for client module access checking.
    
    Checks if:
    1. The tenant has the module enabled
    2. The specific client has the module enabled
    
    Usage:
        @router.get("/client/analytics")
        async def get_analytics(
            current_client: dict = Depends(require_client_module("portfolio_analytics")),
        ):
            ...
    """
    from src.models.module import Module, TenantModule, ClientModule
    
    async def check_client_module_access(
        current_client: dict = Depends(get_current_client),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        tenant_id = current_client["tenant_id"]
        client_id = current_client["client_id"]
        
        # Check if module exists
        module_result = await db.execute(
            select(Module).where(Module.code == module_code)
        )
        module = module_result.scalar_one_or_none()
        
        if not module:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module '{module_code}' not found",
            )
        
        # Core modules are always accessible
        if module.is_core:
            return current_client
        
        # Check tenant has module enabled
        tenant_module_result = await db.execute(
            select(TenantModule).where(
                TenantModule.tenant_id == tenant_id,
                TenantModule.module_id == module.id,
                TenantModule.is_enabled == True,
            )
        )
        tenant_module = tenant_module_result.scalar_one_or_none()
        
        if not tenant_module:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_code}' is not enabled for your organization",
            )
        
        # Check client has module enabled
        client_module_result = await db.execute(
            select(ClientModule).where(
                ClientModule.client_id == client_id,
                ClientModule.module_id == module.id,
                ClientModule.is_enabled == True,
            )
        )
        client_module = client_module_result.scalar_one_or_none()
        
        if not client_module:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module_code}' is not enabled for your account",
            )
        
        return current_client

    return check_client_module_access

