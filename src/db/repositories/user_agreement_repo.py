"""User Agreement repository."""

from typing import Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user_agreement import UserAgreement
from src.schemas.user_agreement import UserAgreementCreate

class UserAgreementRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, 
        agreement_in: UserAgreementCreate, 
        user_id: Optional[str] = None,
        client_user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> UserAgreement:
        agreement = UserAgreement(
            user_id=user_id,
            client_user_id=client_user_id,
            agreement_type=agreement_in.agreement_type,
            version=agreement_in.version,
            user_agent=agreement_in.user_agent,
            device_info=agreement_in.device_info,
            ip_address=ip_address
        )
        self.session.add(agreement)
        await self.session.commit()
        await self.session.refresh(agreement)
        return agreement

    async def get_latest_agreement(
        self, 
        agreement_type: str,
        user_id: Optional[str] = None,
        client_user_id: Optional[str] = None
    ) -> Optional[UserAgreement]:
        query = select(UserAgreement).where(
            UserAgreement.agreement_type == agreement_type
        )
        
        if user_id:
            query = query.where(UserAgreement.user_id == user_id)
        elif client_user_id:
            query = query.where(UserAgreement.client_user_id == client_user_id)
        else:
            return None
            
        query = query.order_by(desc(UserAgreement.accepted_at)).limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
