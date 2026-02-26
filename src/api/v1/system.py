from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.schemas.system_config import SystemConfigResponse

router = APIRouter()

@router.get("/config/{key}", response_model=SystemConfigResponse)
async def get_system_config(
    key: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a public system configuration by key.
    Useful for fetching Privacy Policy, Terms of Service, etc.
    """
    repo = SystemConfigRepository(db)
    config = await repo.get_public_config(key)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration '{key}' not found or not public"
        )
    return config
