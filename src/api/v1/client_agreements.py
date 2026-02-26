from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_client
from src.db.repositories.user_agreement_repo import UserAgreementRepository
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.schemas.user_agreement import UserAgreementCreate, UserAgreementResponse, AgreementStatus

router = APIRouter()

@router.post("/", response_model=UserAgreementResponse)
async def accept_agreement(
    request: Request,
    agreement_in: UserAgreementCreate,
    db: AsyncSession = Depends(get_db),
    current_client: dict = Depends(get_current_client),
):
    """
    Record user acceptance of an agreement.
    """
    repo = UserAgreementRepository(db)
    client_user_id = current_client.get("client_user_id")
    
    # Get IP address
    ip_address = request.client.host if request.client else None
    
    agreement = await repo.create(
        agreement_in=agreement_in,
        client_user_id=client_user_id,
        ip_address=ip_address
    )
    return agreement

@router.get("/status", response_model=Dict[str, AgreementStatus])
async def get_agreement_status(
    agreement_type: str = "privacy_policy",
    db: AsyncSession = Depends(get_db),
    current_client: dict = Depends(get_current_client),
):
    """
    Check if the current user has accepted the latest version of an agreement.
    """
    agreement_repo = UserAgreementRepository(db)
    config_repo = SystemConfigRepository(db)
    
    client_user_id = current_client.get("client_user_id")
    
    # Get latest version from system config
    config = await config_repo.get_by_key(agreement_type)
    latest_version = config.version if config else "1.0"
    
    # Get user's latest acceptance
    user_agreement = await agreement_repo.get_latest_agreement(
        agreement_type=agreement_type,
        client_user_id=client_user_id
    )
    
    accepted = False
    current_version = None
    
    if user_agreement:
        current_version = user_agreement.version
        # Simple string comparison for now, assuming semantic versioning or timestamp string
        # If user version is same or newer than system version, consider accepted
        if current_version >= latest_version:
            accepted = True
            
    return {
        agreement_type: AgreementStatus(
            accepted=accepted,
            version=current_version,
            latest_version=latest_version
        )
    }
