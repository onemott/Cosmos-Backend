"""Holdings/positions endpoints."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.api.deps import get_current_user, require_tenant_user

router = APIRouter()


@router.get("/")
async def list_holdings(
    client_id: str = None,
    account_id: str = None,
    asset_class: str = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> List[dict]:
    """List holdings with optional filters."""
    # TODO: Implement holdings listing
    return []


@router.get("/summary")
async def get_holdings_summary(
    client_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> dict:
    """Get holdings summary (allocation by asset class, region, etc.)."""
    # TODO: Implement holdings summary
    return {
        "total_value": 0.0,
        "by_asset_class": [],
        "by_currency": [],
        "by_region": [],
    }


@router.get("/allocation")
async def get_allocation(
    client_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> dict:
    """Get portfolio allocation breakdown."""
    # TODO: Implement allocation calculation
    return {
        "by_asset_class": [],
        "by_sector": [],
        "by_geography": [],
        "by_currency": [],
    }

