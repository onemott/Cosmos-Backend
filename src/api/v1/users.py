"""User management endpoints."""

from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.db.repositories.user_repo import UserRepository
from src.schemas.user import UserCreate, UserUpdate, UserResponse
from src.api.deps import (
    get_current_user,
    get_current_tenant_admin,
    get_current_superuser,
    get_supervisor_or_higher,
    is_platform_admin as deps_is_platform_admin,
    is_tenant_admin as deps_is_tenant_admin,
    get_user_role_level,
)
from src.core.config import settings
from src.services.audit_log_service import enqueue_audit_log, build_request_context

router = APIRouter()


class PasswordChangeRequest(BaseModel):
    """Password change request schema."""

    current_password: Optional[str] = None
    new_password: str


class AssignSupervisorRequest(BaseModel):
    """Request to assign a supervisor to a user."""
    
    supervisor_id: Optional[str] = None


class UserWithHierarchyResponse(BaseModel):
    """User response with hierarchy information."""
    
    id: str
    email: str
    first_name: str
    last_name: str
    tenant_id: str
    is_active: bool
    is_superuser: bool
    roles: List[str]
    supervisor_id: Optional[str] = None
    supervisor_name: Optional[str] = None
    department: Optional[str] = None
    employee_code: Optional[str] = None
    subordinate_count: int = 0
    created_at: Any
    updated_at: Any


def user_to_response(user) -> UserResponse:
    """Convert User model to UserResponse, handling roles properly."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        tenant_id=str(user.tenant_id),
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        roles=[role.name for role in user.roles] if user.roles else [],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def user_to_hierarchy_response(user, subordinate_count: int = 0) -> UserWithHierarchyResponse:
    """Convert User model to UserWithHierarchyResponse with hierarchy info."""
    supervisor_name = None
    if user.supervisor:
        supervisor_name = f"{user.supervisor.first_name} {user.supervisor.last_name}"
    
    return UserWithHierarchyResponse(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        tenant_id=str(user.tenant_id),
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        roles=[role.name for role in user.roles] if user.roles else [],
        supervisor_id=str(user.supervisor_id) if user.supervisor_id else None,
        supervisor_name=supervisor_name,
        department=user.department,
        employee_code=user.employee_code,
        subordinate_count=subordinate_count,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UserResponse:
    """Get current user information."""
    repo = UserRepository(db)

    # In dev mode, return mock user data
    if (
        settings.debug
        and current_user.get("user_id") == "00000000-0000-0000-0000-000000000001"
    ):
        return UserResponse(
            id="00000000-0000-0000-0000-000000000001",
            email="dev@eam-platform.dev",
            first_name="Dev",
            last_name="User",
            tenant_id="00000000-0000-0000-0000-000000000000",
            is_active=True,
            is_superuser=True,
            roles=["super_admin"],
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    user = await repo.get_with_roles(current_user["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user_to_response(user)


def is_platform_admin(user: dict) -> bool:
    """Check if user has platform-level admin access (can see all tenants).

    Only users with explicit platform roles can access cross-tenant data.
    - super_admin: Legacy role for backward compatibility
    - platform_admin: Standard platform administrator role
    """
    roles = set(user.get("roles", []))
    platform_roles = {"super_admin", "platform_admin"}
    return bool(platform_roles.intersection(roles))


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[UserResponse]:
    """List users.

    - Platform admins: See all users across all tenants
    - Tenant admins/users: See only users in their own tenant
    """
    repo = UserRepository(db)

    # Only platform-level admins can see all tenants
    # Tenant admins can only see their own tenant
    tenant_id = (
        None if is_platform_admin(current_user) else current_user.get("tenant_id")
    )

    if search:
        users = await repo.search_users(
            search, tenant_id=tenant_id, skip=skip, limit=limit
        )
    elif tenant_id:
        users = await repo.get_users_by_tenant(tenant_id, skip=skip, limit=limit)
    else:
        users = await repo.get_all_users(skip=skip, limit=limit)

    # Load roles for all users and convert to response
    result = []
    for user in users:
        user_with_roles = await repo.get_with_roles(user.id)
        result.append(user_to_response(user_with_roles))

    return result


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> UserResponse:
    """Create a new user.

    - Regular users: Creates user in their own tenant
    - Super admins: Can specify tenant_id to create user in any tenant
    - Can assign roles via role_ids
    """
    repo = UserRepository(db)

    # Check if email already exists
    existing = await repo.get_by_email(user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{user_in.email}' already exists",
        )

    # Prepare user data
    user_data = user_in.model_dump(exclude={"password", "role_ids", "tenant_id"})

    # Determine tenant_id
    if is_platform_admin(current_user) and user_in.tenant_id:
        # Super admin can specify tenant
        user_data["tenant_id"] = user_in.tenant_id
    else:
        # Use current user's tenant
        user_data["tenant_id"] = current_user.get(
            "tenant_id", "00000000-0000-0000-0000-000000000000"
        )

    # Hash password if provided
    if user_in.password:
        from src.core.security import hash_password

        user_data["hashed_password"] = hash_password(user_in.password)

    # Create user
    user = await repo.create(user_data)
    await db.commit()  # Ensure user is committed before assigning roles
    await db.refresh(user)

    # Assign roles if provided
    if user_in.role_ids:
        # Validate role assignments based on user's permission level
        if not is_platform_admin(current_user):
            # Non-platform admins can only assign tenant-level roles
            from sqlalchemy import select
            from src.models.user import Role

            role_query = select(Role).where(Role.id.in_(user_in.role_ids))
            role_result = await db.execute(role_query)
            roles_to_assign = role_result.scalars().all()

            platform_role_names = {"super_admin", "platform_admin", "platform_user"}
            for role in roles_to_assign:
                if role.name in platform_role_names:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Cannot assign platform role '{role.name}'. Only platform admins can assign platform-level roles.",
                    )

        user = await repo.assign_roles(user.id, user_in.role_ids)
    else:
        # Load roles anyway to return consistent response
        user = await repo.get_with_roles(user.id)

    context = build_request_context(request)
    enqueue_audit_log(
        {
            "tenant_id": str(user.tenant_id),
            "event_type": "user",
            "level": "info",
            "category": "security",
            "resource_type": "user",
            "resource_id": user.id,
            "action": "create",
            "outcome": "success",
            "user_id": current_user.get("user_id"),
            "user_email": current_user.get("email"),
            "old_value": None,
            "new_value": jsonable_encoder(user_to_response(user)),
            "extra_data": {"role_ids": user_in.role_ids or []},
            **context,
        }
    )

    return user_to_response(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UserResponse:
    """Get user by ID with roles."""
    repo = UserRepository(db)
    user = await repo.get_with_roles(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check access (can only view users in same tenant unless platform admin)
    if not is_platform_admin(current_user) and str(user.tenant_id) != current_user.get(
        "tenant_id"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return user_to_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_in: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> UserResponse:
    """Update user and optionally update roles."""
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    old_user = await repo.get_with_roles(user_id)
    old_snapshot = jsonable_encoder(user_to_response(old_user or user))

    # Check access - only platform admins can update users in other tenants
    if not is_platform_admin(current_user) and str(user.tenant_id) != current_user.get(
        "tenant_id"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Update only provided fields
    update_data = user_in.model_dump(exclude_unset=True, exclude={"role_ids"})
    if update_data:
        user = await repo.update(user, update_data)
        await db.flush()  # Flush but don't commit yet

    # Update roles if provided
    if user_in.role_ids is not None:
        # Validate role assignments based on user's permission level
        if not is_platform_admin(current_user):
            # Non-platform admins can only assign tenant-level roles
            from sqlalchemy import select
            from src.models.user import Role

            role_query = select(Role).where(Role.id.in_(user_in.role_ids))
            role_result = await db.execute(role_query)
            roles_to_assign = role_result.scalars().all()

            platform_role_names = {"super_admin", "platform_admin", "platform_user"}
            for role in roles_to_assign:
                if role.name in platform_role_names:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Cannot assign platform role '{role.name}'. Only platform admins can assign platform-level roles.",
                    )

        user = await repo.assign_roles(str(user.id), user_in.role_ids)
        updated_user = user
    else:
        # Load roles anyway to return consistent response
        await db.commit()  # Commit the update
        updated_user = await repo.get_with_roles(str(user.id))

    context = build_request_context(request)
    enqueue_audit_log(
        {
            "tenant_id": str(user.tenant_id),
            "event_type": "user",
            "level": "info",
            "category": "security",
            "resource_type": "user",
            "resource_id": str(user.id),
            "action": "update",
            "outcome": "success",
            "user_id": current_user.get("user_id"),
            "user_email": current_user.get("email"),
            "old_value": old_snapshot,
            "new_value": jsonable_encoder(user_to_response(updated_user)),
            "extra_data": {
                "updated_fields": list(update_data.keys()),
                "role_ids": user_in.role_ids,
            },
            **context,
        }
    )

    return user_to_response(updated_user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Deactivate user (soft delete - sets is_active to False)."""
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check access
    if not is_platform_admin(current_user) and str(user.tenant_id) != current_user.get(
        "tenant_id"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Can't delete yourself
    if user_id == current_user.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    old_snapshot = jsonable_encoder(user_to_response(await repo.get_with_roles(user_id) or user))

    await repo.update(user, {"is_active": False})
    await db.commit()
    updated_user = await repo.get_with_roles(user_id)

    context = build_request_context(request)
    enqueue_audit_log(
        {
            "tenant_id": str(user.tenant_id),
            "event_type": "user",
            "level": "warn",
            "category": "security",
            "resource_type": "user",
            "resource_id": str(user.id),
            "action": "deactivate",
            "outcome": "success",
            "user_id": current_user.get("user_id"),
            "user_email": current_user.get("email"),
            "old_value": old_snapshot,
            "new_value": jsonable_encoder(user_to_response(updated_user)),
            **context,
        }
    )


@router.delete("/{user_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_permanent(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Permanently delete user.

    WARNING: This action cannot be undone.
    """
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check access
    if not is_platform_admin(current_user) and str(user.tenant_id) != current_user.get(
        "tenant_id"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Can't delete yourself
    if user_id == current_user.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    # Can't delete super admins (safety measure)
    if user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot permanently delete super admin accounts",
        )

    # Hard delete
    old_snapshot = jsonable_encoder(user_to_response(await repo.get_with_roles(user_id) or user))
    await repo.delete(user)
    await db.commit()

    context = build_request_context(request)
    enqueue_audit_log(
        {
            "tenant_id": str(user.tenant_id),
            "event_type": "user",
            "level": "warn",
            "category": "security",
            "resource_type": "user",
            "resource_id": str(user.id),
            "action": "delete",
            "outcome": "success",
            "user_id": current_user.get("user_id"),
            "user_email": current_user.get("email"),
            "old_value": old_snapshot,
            "new_value": None,
            **context,
        }
    )


@router.post("/{user_id}/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    user_id: str,
    request: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Change user password.

    - Users can change their own password (requires current_password)
    - Super admins can reset any user's password (no current_password required)
    - Tenant admins can reset passwords for users in their tenant
    """
    from src.core.security import hash_password, verify_password

    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    is_self = user_id == current_user.get("user_id")
    is_same_tenant = str(user.tenant_id) == current_user.get("tenant_id")
    has_platform_access = is_platform_admin(current_user)

    # Access control - platform admins can change any password, others only within their tenant
    if not has_platform_access and not is_self and not is_same_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # If changing own password (and not a platform admin), verify current password
    if is_self and not has_platform_access:
        if not request.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required",
            )
        if not verify_password(request.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

    # Update password
    new_hash = hash_password(request.new_password)
    await repo.update(user, {"hashed_password": new_hash})

    return {"message": "Password changed successfully"}


# ============================================================================
# Team Management Endpoints
# ============================================================================


@router.get("/{user_id}/subordinates", response_model=List[UserResponse])
async def get_user_subordinates(
    user_id: str,
    direct_only: bool = Query(True, description="Only return direct reports"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[UserResponse]:
    """Get subordinates of a user.
    
    - Users can view their own subordinates
    - Supervisors can view subordinates of their team members
    - Tenant admins can view any user's subordinates in their tenant
    """
    repo = UserRepository(db)
    user = await repo.get(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Access check
    is_self = user_id == current_user.get("user_id")
    is_same_tenant = str(user.tenant_id) == current_user.get("tenant_id")
    is_admin = deps_is_tenant_admin(current_user)
    
    if not is_same_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    if not is_self and not is_admin:
        # Check if current user is a supervisor of this user
        # (Allow supervisors to see their team's subordinates)
        all_subordinate_ids = await repo.get_all_subordinate_ids(current_user.get("user_id"))
        if user_id not in all_subordinate_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied - can only view your own subordinates or those of your team",
            )
    
    subordinates = await repo.get_subordinates(user_id, direct_only=direct_only, include_roles=True)
    return [user_to_response(sub) for sub in subordinates]


@router.get("/{user_id}/team-tree")
async def get_user_team_tree(
    user_id: str,
    max_depth: int = Query(5, ge=1, le=10, description="Maximum tree depth"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get the complete team tree structure for a user.
    
    Returns a hierarchical structure showing the user and all subordinates.
    
    - Users can view their own team tree
    - Tenant admins can view any user's team tree in their tenant
    """
    repo = UserRepository(db)
    user = await repo.get(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Access check
    is_self = user_id == current_user.get("user_id")
    is_same_tenant = str(user.tenant_id) == current_user.get("tenant_id")
    role_level = get_user_role_level(current_user)
    
    if not is_same_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    if not is_self:
        if role_level in {"tenant_admin", "platform_admin"}:
            pass
        elif role_level == "eam_supervisor":
            all_subordinate_ids = await repo.get_all_subordinate_ids(current_user.get("user_id"))
            if user_id not in all_subordinate_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    
    tree = await repo.get_team_tree(user_id, max_depth=max_depth)
    return tree


@router.post("/{user_id}/assign-supervisor", response_model=UserResponse)
async def assign_supervisor(
    user_id: str,
    request: AssignSupervisorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> UserResponse:
    """Assign or update a user's supervisor.
    
    - Only tenant admins can assign supervisors
    - Supervisor must be in the same tenant
    - Cannot create circular references
    - Pass supervisor_id: null to remove supervisor
    """
    repo = UserRepository(db)
    user = await repo.get(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Access check - only same tenant
    if not deps_is_platform_admin(current_user) and str(user.tenant_id) != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Validate supervisor if provided
    if request.supervisor_id:
        supervisor = await repo.get(request.supervisor_id)
        if not supervisor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supervisor not found",
            )
        
        # Must be same tenant
        if str(supervisor.tenant_id) != str(user.tenant_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supervisor must be in the same tenant",
            )
        
        # Validate no circular reference
        is_valid = await repo.validate_supervisor_assignment(user_id, request.supervisor_id)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid supervisor assignment - would create circular reference",
            )
    
    # Update supervisor
    try:
        user = await repo.update_supervisor(user_id, request.supervisor_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Reload with roles
    user = await repo.get_with_roles(user_id)
    return user_to_response(user)


@router.get("/{user_id}/with-hierarchy", response_model=UserWithHierarchyResponse)
async def get_user_with_hierarchy(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> UserWithHierarchyResponse:
    """Get user by ID with full hierarchy information.
    
    Returns user details including supervisor info and subordinate count.
    """
    repo = UserRepository(db)
    user = await repo.get_with_hierarchy(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Access check
    if not deps_is_platform_admin(current_user) and str(user.tenant_id) != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    # Count subordinates
    subordinate_count = await repo.count_subordinates(user_id, direct_only=True)
    
    return user_to_hierarchy_response(user, subordinate_count)


@router.get("/tenant/{tenant_id}/org-tree")
async def get_tenant_org_tree(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> List[Dict[str, Any]]:
    """Get the complete organizational tree for a tenant.
    
    Returns all users organized by hierarchy, starting from users with no supervisor.
    
    - Tenant admins can view their own tenant's org tree
    - Platform admins can view any tenant's org tree
    """
    # Access check
    if not deps_is_platform_admin(current_user) and tenant_id != current_user.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    repo = UserRepository(db)
    
    # Get all users without a supervisor (top-level users)
    all_users = await repo.get_users_by_tenant(tenant_id, limit=1000)
    top_level_users = [u for u in all_users if not u.supervisor_id]
    
    # Build tree for each top-level user
    trees = []
    for user in top_level_users:
        tree = await repo.get_team_tree(str(user.id), max_depth=10)
        if tree:
            trees.append(tree)
    
    return trees
