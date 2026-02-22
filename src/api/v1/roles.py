"""Role management endpoints."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.config import settings
from src.db.session import get_db
from src.models.user import Role
from src.schemas.role import RoleResponse
from src.api.deps import get_current_user

router = APIRouter()


@router.get("/", response_model=List[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[RoleResponse]:
    """List available roles based on user's permission level.
    
    - Platform admins: See all roles (platform + tenant)
    - Tenant admins: See only tenant-level roles
    """
    query = select(Role).order_by(Role.name)
    result = await db.execute(query)
    roles = result.scalars().all()
    
    # Check if user is platform admin
    platform_roles_set = set(settings.platform_admin_roles)
    user_roles = set(current_user.get("roles", []))
    is_platform_admin = bool(platform_roles_set.intersection(user_roles)) or current_user.get("is_superuser", False)
    
    # Filter roles based on user level
    if is_platform_admin:
        # Platform admins can see all roles
        return [RoleResponse.model_validate(r) for r in roles]
    else:
        # Tenant admins can only see tenant-level roles
        platform_role_names = set(settings.platform_roles)
        filtered_roles = [r for r in roles if r.name not in platform_role_names]
        return [RoleResponse.model_validate(r) for r in filtered_roles]

