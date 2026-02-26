from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.system_config import SystemConfig
from src.schemas.system_config import SystemConfigCreate, SystemConfigUpdate

class SystemConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_key(self, key: str) -> Optional[SystemConfig]:
        query = select(SystemConfig).where(SystemConfig.key == key)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, config_in: SystemConfigCreate) -> SystemConfig:
        config = SystemConfig(
            key=config_in.key,
            value=config_in.value,
            version=config_in.version,
            description=config_in.description,
            is_public=config_in.is_public
        )
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def update(self, key: str, config_in: SystemConfigUpdate) -> Optional[SystemConfig]:
        config = await self.get_by_key(key)
        if not config:
            return None

        update_data = config_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)

        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def get_public_config(self, key: str) -> Optional[SystemConfig]:
        query = select(SystemConfig).where(
            SystemConfig.key == key,
            SystemConfig.is_public == True
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
