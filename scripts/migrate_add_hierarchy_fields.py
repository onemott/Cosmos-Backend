#!/usr/bin/env python3
"""Database migration script to add hierarchy and assignment fields.

This script adds the following fields:
1. users.supervisor_id - User's supervisor (self-referential FK)
2. users.department - Department name
3. users.employee_code - Employee code
4. clients.assigned_to_user_id - User responsible for this client
5. clients.created_by_user_id - User who created this client

Usage:
    cd backend
    source venv/bin/activate
    python scripts/migrate_add_hierarchy_fields.py
    
For rollback:
    python scripts/migrate_add_hierarchy_fields.py --rollback
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.db.session import async_session_factory


# Migration SQL statements
UPGRADE_SQL = """
-- Add organizational hierarchy fields to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS supervisor_id UUID REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_code VARCHAR(50);

-- Create index for supervisor_id
CREATE INDEX IF NOT EXISTS ix_users_supervisor_id ON users(supervisor_id);

-- Add client assignment fields
ALTER TABLE clients ADD COLUMN IF NOT EXISTS assigned_to_user_id UUID REFERENCES users(id);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id);

-- Create indexes for client assignment fields
CREATE INDEX IF NOT EXISTS ix_clients_assigned_to_user_id ON clients(assigned_to_user_id);
CREATE INDEX IF NOT EXISTS ix_clients_created_by_user_id ON clients(created_by_user_id);
"""

DOWNGRADE_SQL = """
-- Remove indexes first
DROP INDEX IF EXISTS ix_clients_created_by_user_id;
DROP INDEX IF EXISTS ix_clients_assigned_to_user_id;
DROP INDEX IF EXISTS ix_users_supervisor_id;

-- Remove client assignment fields
ALTER TABLE clients DROP COLUMN IF EXISTS created_by_user_id;
ALTER TABLE clients DROP COLUMN IF EXISTS assigned_to_user_id;

-- Remove user hierarchy fields
ALTER TABLE users DROP COLUMN IF EXISTS employee_code;
ALTER TABLE users DROP COLUMN IF EXISTS department;
ALTER TABLE users DROP COLUMN IF EXISTS supervisor_id;
"""


async def run_migration(rollback: bool = False):
    """Run the migration."""
    async with async_session_factory() as session:
        try:
            if rollback:
                print("🔄 Rolling back migration...")
                sql = DOWNGRADE_SQL
            else:
                print("🚀 Running migration...")
                sql = UPGRADE_SQL
            
            # Execute each statement separately
            for statement in sql.strip().split(';'):
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    print(f"  Executing: {statement[:60]}...")
                    await session.execute(text(statement))
            
            await session.commit()
            
            if rollback:
                print("\n✅ Rollback complete!")
            else:
                print("\n✅ Migration complete!")
                print("\nNew fields added:")
                print("  users.supervisor_id    - UUID FK to users(id)")
                print("  users.department       - VARCHAR(100)")
                print("  users.employee_code    - VARCHAR(50)")
                print("  clients.assigned_to_user_id - UUID FK to users(id)")
                print("  clients.created_by_user_id  - UUID FK to users(id)")
            
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise


async def verify_migration():
    """Verify the migration was successful."""
    async with async_session_factory() as session:
        try:
            print("\n🔍 Verifying migration...")
            
            # Check users table columns
            result = await session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('supervisor_id', 'department', 'employee_code')
            """))
            user_columns = result.fetchall()
            
            # Check clients table columns
            result = await session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'clients' 
                AND column_name IN ('assigned_to_user_id', 'created_by_user_id')
            """))
            client_columns = result.fetchall()
            
            print("\nUsers table new columns:")
            for col in user_columns:
                print(f"  ✓ {col[0]}: {col[1]}")
            
            print("\nClients table new columns:")
            for col in client_columns:
                print(f"  ✓ {col[0]}: {col[1]}")
            
            expected_user_cols = {'supervisor_id', 'department', 'employee_code'}
            expected_client_cols = {'assigned_to_user_id', 'created_by_user_id'}
            
            actual_user_cols = {col[0] for col in user_columns}
            actual_client_cols = {col[0] for col in client_columns}
            
            if expected_user_cols == actual_user_cols and expected_client_cols == actual_client_cols:
                print("\n✅ All expected columns exist!")
                return True
            else:
                missing_user = expected_user_cols - actual_user_cols
                missing_client = expected_client_cols - actual_client_cols
                if missing_user:
                    print(f"\n⚠️  Missing user columns: {missing_user}")
                if missing_client:
                    print(f"\n⚠️  Missing client columns: {missing_client}")
                return False
                
        except Exception as e:
            print(f"\n❌ Verification failed: {e}")
            return False


async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run database migration for hierarchy fields')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    parser.add_argument('--verify', action='store_true', help='Verify migration status only')
    args = parser.parse_args()
    
    if args.verify:
        await verify_migration()
    else:
        await run_migration(rollback=args.rollback)
        if not args.rollback:
            await verify_migration()


if __name__ == "__main__":
    asyncio.run(main())
