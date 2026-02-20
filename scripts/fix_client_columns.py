#!/usr/bin/env python3
"""临时脚本：为clients表添加缺失的字段"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.db.session import async_session_factory


async def add_missing_client_columns():
    """为clients表添加缺失的列"""
    async with async_session_factory() as session:
        try:
            # 检查并添加 assigned_to_user_id 列
            print("检查 assigned_to_user_id 列...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'clients' AND column_name = 'assigned_to_user_id'
            """))
            if not result.fetchone():
                print("添加 assigned_to_user_id 列...")
                await session.execute(text("""
                    ALTER TABLE clients 
                    ADD COLUMN assigned_to_user_id UUID REFERENCES users(id)
                """))
                print("✓ assigned_to_user_id 列已添加")
            else:
                print("✓ assigned_to_user_id 列已存在")

            # 检查并添加 created_by_user_id 列
            print("检查 created_by_user_id 列...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'clients' AND column_name = 'created_by_user_id'
            """))
            if not result.fetchone():
                print("添加 created_by_user_id 列...")
                await session.execute(text("""
                    ALTER TABLE clients 
                    ADD COLUMN created_by_user_id UUID REFERENCES users(id)
                """))
                print("✓ created_by_user_id 列已添加")
            else:
                print("✓ created_by_user_id 列已存在")

            # 检查并添加 group_id 列
            print("检查 group_id 列...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'clients' AND column_name = 'group_id'
            """))
            if not result.fetchone():
                print("添加 group_id 列...")
                await session.execute(text("""
                    ALTER TABLE clients 
                    ADD COLUMN group_id UUID
                """))
                print("✓ group_id 列已添加")
            else:
                print("✓ group_id 列已存在")

            await session.commit()
            print("\n✅ 所有缺失的客户端列已成功添加!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ 错误: {e}")
            raise


if __name__ == "__main__":
    print("🔧 修复 Clients 表结构...")
    print("")
    asyncio.run(add_missing_client_columns())