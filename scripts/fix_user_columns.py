#!/usr/bin/env python3
"""临时脚本：为users表添加缺失的组织架构字段"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.db.session import async_session_factory


async def add_missing_columns():
    """为users表添加缺失的列"""
    async with async_session_factory() as session:
        try:
            # 检查并添加 supervisor_id 列
            print("检查 supervisor_id 列...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'supervisor_id'
            """))
            if not result.fetchone():
                print("添加 supervisor_id 列...")
                await session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN supervisor_id UUID REFERENCES users(id)
                """))
                print("✓ supervisor_id 列已添加")
            else:
                print("✓ supervisor_id 列已存在")

            # 检查并添加 department 列
            print("检查 department 列...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'department'
            """))
            if not result.fetchone():
                print("添加 department 列...")
                await session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN department VARCHAR(100)
                """))
                print("✓ department 列已添加")
            else:
                print("✓ department 列已存在")

            # 检查并添加 employee_code 列
            print("检查 employee_code 列...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'employee_code'
            """))
            if not result.fetchone():
                print("添加 employee_code 列...")
                await session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN employee_code VARCHAR(50)
                """))
                print("✓ employee_code 列已添加")
            else:
                print("✓ employee_code 列已存在")

            await session.commit()
            print("\n✅ 所有缺失的列已成功添加!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ 错误: {e}")
            raise


if __name__ == "__main__":
    print("🔧 修复 Users 表结构...")
    print("")
    asyncio.run(add_missing_columns())