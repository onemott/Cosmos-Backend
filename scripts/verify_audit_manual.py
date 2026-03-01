import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from sqlalchemy import text
from src.db.session import async_session_factory

async def check_audit_logs():
    """
    Query the database for recent audit logs.
    Use this script after manually performing actions in the running application.
    """
    print("Connecting to database...")
    async with async_session_factory() as session:
        print("Querying recent audit logs...")
        
        # Query logs created in the last 10 minutes (or just top 5)
        query = text("""
            SELECT 
                created_at, 
                event_type, 
                action, 
                resource_type, 
                user_id, 
                old_value, 
                new_value 
            FROM audit_logs 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        if not rows:
            print("No audit logs found.")
            return

        print(f"\nFound {len(rows)} recent audit logs:")
        print("-" * 80)
        for row in rows:
            print(f"Time:     {row.created_at}")
            print(f"Event:    {row.event_type}")
            print(f"Action:   {row.action}")
            print(f"Resource: {row.resource_type}")
            print(f"User:     {row.user_id}")
            print(f"Changes:  {row.new_value.keys() if row.new_value else 'None'}")
            print("-" * 80)

if __name__ == "__main__":
    # Ensure we are in the backend directory or PYTHONPATH is set
    # Usage: python scripts/verify_audit_manual.py
    try:
        asyncio.run(check_audit_logs())
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure you are running this from 'Cosmos-Backend' directory and dependencies are installed.")
