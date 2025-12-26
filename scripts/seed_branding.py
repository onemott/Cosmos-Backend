#!/usr/bin/env python3
"""
Seed script to add sample branding data to existing tenants.

This script updates existing tenants with branding information for demo purposes.
Run after seed_admin.py to ensure tenants exist.

Usage:
    cd /path/to/backend
    source venv/bin/activate
    python scripts/seed_branding.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.db.session import AsyncSessionLocal
from src.models.tenant import Tenant


# Sample branding configurations for different EAM firms
BRANDING_CONFIGS = [
    {
        "slug": "demo-eam",
        "branding": {
            "app_name": "Demo Wealth",
            "primary_color": "#1E40AF",  # Blue
            "has_logo": False,
        },
    },
    {
        "slug": "acme-wealth",
        "branding": {
            "app_name": "Acme Wealth Portal",
            "primary_color": "#059669",  # Emerald
            "has_logo": False,
        },
    },
    {
        "slug": "prestige-capital",
        "branding": {
            "app_name": "Prestige Capital",
            "primary_color": "#7C3AED",  # Violet
            "has_logo": False,
        },
    },
]


async def seed_branding():
    """Update existing tenants with sample branding data."""
    print("=" * 60)
    print("Seeding Branding Data")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for config in BRANDING_CONFIGS:
                # Find tenant by slug
                result = await session.execute(
                    select(Tenant).where(Tenant.slug == config["slug"])
                )
                tenant = result.scalar_one_or_none()

                if tenant:
                    # Merge with existing branding or replace
                    existing_branding = tenant.branding or {}
                    new_branding = {**existing_branding, **config["branding"]}
                    tenant.branding = new_branding

                    print(f"✓ Updated branding for: {tenant.name}")
                    print(f"  - App Name: {new_branding.get('app_name')}")
                    print(f"  - Primary Color: {new_branding.get('primary_color')}")
                else:
                    print(f"✗ Tenant not found: {config['slug']}")

            await session.commit()

    print()
    print("=" * 60)
    print("Branding seeding complete!")
    print()
    print("To test the branding:")
    print("1. Log into the admin panel")
    print("2. Navigate to Tenants → select a tenant → Branding")
    print("3. Upload a logo and/or customize the colors")
    print("4. The mobile app will show the updated branding after login")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed_branding())

