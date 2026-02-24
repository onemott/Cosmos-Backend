"""Report generation endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.api.deps import get_current_user, require_tenant_user

router = APIRouter()


@router.get("/")
async def list_reports(
    client_id: str = None,
    report_type: str = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> List[dict]:
    """List generated reports."""
    return []


@router.post("/generate")
async def generate_report(
    report_type: str,
    client_id: str = None,
    period_start: str = None,
    period_end: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> dict:
    """Request report generation."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Report generation not yet implemented",
    )


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> dict:
    """Get report metadata and status."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> dict:
    """Get presigned URL for report download."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Report download not yet implemented",
    )

