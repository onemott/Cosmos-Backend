from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_superuser, get_db
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.schemas.system_config import SystemConfigCreate, SystemConfigUpdate, SystemConfigResponse

router = APIRouter()

@router.put("/config/{key}", response_model=SystemConfigResponse)
async def update_system_config(
    key: str,
    config_in: SystemConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_superuser),
):
    """
    Update a system configuration.
    Only accessible by superusers.
    """
    repo = SystemConfigRepository(db)
    config = await repo.update(key, config_in)
    if not config:
        # If not exists, create it (upsert behavior)
        if not config_in.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Value is required for creating new config"
            )
        create_in = SystemConfigCreate(
            key=key,
            value=config_in.value,
            version=config_in.version or "1.0",
            description=config_in.description,
            is_public=config_in.is_public if config_in.is_public is not None else False
        )
        config = await repo.create(create_in)
    
    return config

@router.get("/config/{key}", response_model=SystemConfigResponse)
async def get_system_config(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_superuser),
):
    """
    Get a system configuration.
    Only accessible by superusers.
    """
    repo = SystemConfigRepository(db)
    config = await repo.get_by_key(key)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )
    return config

@router.post("/config", response_model=SystemConfigResponse)
async def create_system_config(
    config_in: SystemConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_superuser),
):
    """
    Create a new system configuration.
    Only accessible by superusers.
    """
    repo = SystemConfigRepository(db)
    existing = await repo.get_by_key(config_in.key)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configuration '{config_in.key}' already exists"
        )
    
    return await repo.create(config_in)
