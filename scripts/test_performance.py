#!/usr/bin/env python3
"""
Test script to verify performance calculation.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select
from src.db.session import async_session_factory
from src.models.client import Client
from src.models.client_user import ClientUser
from src.services.performance_service import PerformanceService


async def test_performance():
    """Test performance calculation for all clients."""
    async with async_session_factory() as db:
        # Get all clients
        result = await db.execute(
            select(Client)
        )
        clients = result.scalars().all()
        
        print("=" * 60)
        print("Performance Calculation Test")
        print("=" * 60)
        
        perf_service = PerformanceService(db)
        
        for client in clients:
            print(f"\nClient: {client.email}")
            print(f"  Risk Profile: {client.risk_profile.value if client.risk_profile else 'N/A'}")
            
            # Get performance metrics
            metrics = await perf_service.get_performance_metrics(str(client.id))
            
            print(f"  Performance Metrics:")
            print(f"    1M:  {metrics.get('1M', 'N/A'):+.2f}%" if metrics.get('1M') else "    1M:  N/A")
            print(f"    3M:  {metrics.get('3M', 'N/A'):+.2f}%" if metrics.get('3M') else "    3M:  N/A")
            print(f"    6M:  {metrics.get('6M', 'N/A'):+.2f}%" if metrics.get('6M') else "    6M:  N/A")
            print(f"    YTD: {metrics.get('YTD', 'N/A'):+.2f}%" if metrics.get('YTD') else "    YTD: N/A")
            print(f"    1Y:  {metrics.get('1Y', 'N/A'):+.2f}%" if metrics.get('1Y') else "    1Y:  N/A")
        
        print("\n" + "=" * 60)
        print("Test complete!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_performance())
