import asyncio
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.session import async_session_factory
from src.models.system_config import SystemConfig

async def seed_privacy_policy():
    async with async_session_factory() as session:
        print("Checking privacy policy...")
        stmt = select(SystemConfig).where(SystemConfig.key == "privacy_policy")
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        
        default_content = """# 隐私政策与服务条款

**更新日期：2026年3月1日**

欢迎使用 Cosmos EAM 财富管理平台。我们非常重视您的隐私保护。

## 1. 我们收集的信息
我们可能会收集您的姓名、联系方式、财务信息以及设备信息，以便为您提供更好的服务。

## 2. 信息使用
我们将仅出于为您提供投资建议、执行交易和改进服务的目的使用您的信息。

## 3. 信息共享
除非法律要求或获得您的明确同意，我们不会向第三方出售或共享您的个人信息。

## 4. 数据安全
我们采用业界标准的安全措施来保护您的数据安全。

## 5. 联系我们
如果您有任何疑问，请联系您的专属顾问或客服团队。
"""

        if not config:
            print("Creating privacy policy...")
            config = SystemConfig(
                key="privacy_policy",
                value=default_content,
                version="1.0",
                description="Default Privacy Policy",
                is_public=True
            )
            session.add(config)
            await session.commit()
            print("Privacy policy created successfully.")
        else:
            print("Privacy policy already exists. Updating content...")
            config.value = default_content
            config.is_public = True
            session.add(config)
            await session.commit()
            print("Privacy policy updated successfully.")

if __name__ == "__main__":
    asyncio.run(seed_privacy_policy())
