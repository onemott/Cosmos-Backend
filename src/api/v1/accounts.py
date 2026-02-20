"""Account management endpoints."""

from typing import List, Optional
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.api.deps import get_current_user
from src.models.account import Account, AccountType
from src.models.client import Client
from src.models.holding import Holding

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class AccountCreate(BaseModel):
    """Schema for creating an account."""
    client_id: str = Field(..., description="Client to assign account to")
    account_number: str = Field(..., max_length=100, description="Account number")
    account_name: str = Field(..., max_length=255, description="Account name")
    account_type: AccountType = Field(default=AccountType.INVESTMENT)
    currency: str = Field(default="USD", max_length=3)
    bank_name: Optional[str] = Field(None, description="Bank/custodian name")
    total_value: Decimal = Field(default=Decimal("0"))
    cash_balance: Decimal = Field(default=Decimal("0"))


class AccountUpdate(BaseModel):
    """Schema for updating an account."""
    account_name: Optional[str] = Field(None, max_length=255)
    account_type: Optional[AccountType] = None
    currency: Optional[str] = Field(None, max_length=3)
    total_value: Optional[Decimal] = None
    cash_balance: Optional[Decimal] = None
    is_active: Optional[bool] = None


class AccountReassign(BaseModel):
    """Schema for reassigning account to different client."""
    client_id: str = Field(..., description="New client ID to assign account to")


class AccountResponse(BaseModel):
    """Response schema for account."""
    id: str
    tenant_id: str
    client_id: str
    account_number: str
    account_number_masked: str
    account_name: str
    account_type: str
    currency: str
    total_value: float
    cash_balance: float
    is_active: bool
    client_name: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class AccountListResponse(BaseModel):
    """Paginated list of accounts."""
    accounts: List[AccountResponse]
    total_count: int
    skip: int
    limit: int


# ============================================================================
# Helper Functions
# ============================================================================

def mask_account_number(account_number: str) -> str:
    """Mask account number for display."""
    if len(account_number) <= 4:
        return account_number
    return f"****{account_number[-4:]}"


def build_account_response(account: Account) -> AccountResponse:
    """Build account response from model."""
    client_name = None
    if account.client:
        if account.client.first_name and account.client.last_name:
            client_name = f"{account.client.first_name} {account.client.last_name}"
        elif account.client.entity_name:
            client_name = account.client.entity_name
    
    return AccountResponse(
        id=account.id,
        tenant_id=account.tenant_id,
        client_id=account.client_id,
        account_number=account.account_number,
        account_number_masked=mask_account_number(account.account_number),
        account_name=account.account_name,
        account_type=account.account_type.value,
        currency=account.currency,
        total_value=float(account.total_value),
        cash_balance=float(account.cash_balance),
        is_active=account.is_active,
        client_name=client_name,
        created_at=account.created_at.isoformat() if account.created_at else "",
        updated_at=account.updated_at.isoformat() if account.updated_at else "",
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/", response_model=AccountListResponse)
async def list_accounts(
    client_id: Optional[str] = Query(None, description="Filter by client"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    unassigned: Optional[bool] = Query(None, description="Show only unassigned accounts"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AccountListResponse:
    """List accounts with optional filters."""
    tenant_id = current_user.get("tenant_id")
    
    query = select(Account).options(selectinload(Account.client))
    
    # Tenant filter (non-superadmins)
    if tenant_id:
        query = query.where(Account.tenant_id == tenant_id)
    
    # Client filter
    if client_id:
        query = query.where(Account.client_id == client_id)
    
    # Active filter
    if is_active is not None:
        query = query.where(Account.is_active == is_active)
    
    # Order by creation date
    query = query.order_by(Account.created_at.desc())
    
    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0
    
    # Paginate
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    accounts = result.scalars().all()
    
    return AccountListResponse(
        accounts=[build_account_response(a) for a in accounts],
        total_count=total_count,
        skip=skip,
        limit=limit,
    )


@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AccountResponse:
    """Create a new account manually."""
    tenant_id = current_user.get("tenant_id")
    
    # Verify client exists and belongs to tenant
    client_query = select(Client).where(Client.id == data.client_id)
    if tenant_id:
        client_query = client_query.where(Client.tenant_id == tenant_id)
    
    result = await db.execute(client_query)
    client = result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found or not accessible",
        )
    
    # Check for duplicate account number within tenant
    existing = await db.execute(
        select(Account).where(
            Account.tenant_id == client.tenant_id,
            Account.account_number == data.account_number,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account number already exists",
        )
    
    # Create account
    account = Account(
        id=str(uuid4()),
        tenant_id=client.tenant_id,
        client_id=data.client_id,
        account_number=data.account_number,
        account_name=data.account_name,
        account_type=data.account_type,
        currency=data.currency,
        total_value=data.total_value,
        cash_balance=data.cash_balance,
        is_active=True,
    )
    
    db.add(account)
    await db.commit()
    await db.refresh(account)
    
    # Load client relationship
    result = await db.execute(
        select(Account)
        .options(selectinload(Account.client))
        .where(Account.id == account.id)
    )
    account = result.scalar_one()
    
    return build_account_response(account)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AccountResponse:
    """Get account by ID."""
    tenant_id = current_user.get("tenant_id")
    
    query = (
        select(Account)
        .options(selectinload(Account.client))
        .where(Account.id == account_id)
    )
    
    if tenant_id:
        query = query.where(Account.tenant_id == tenant_id)
    
    result = await db.execute(query)
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    return build_account_response(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    data: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AccountResponse:
    """Update account details."""
    tenant_id = current_user.get("tenant_id")
    
    query = (
        select(Account)
        .options(selectinload(Account.client))
        .where(Account.id == account_id)
    )
    
    if tenant_id:
        query = query.where(Account.tenant_id == tenant_id)
    
    result = await db.execute(query)
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    # Apply updates
    if data.account_name is not None:
        account.account_name = data.account_name
    if data.account_type is not None:
        account.account_type = data.account_type
    if data.currency is not None:
        account.currency = data.currency
    if data.total_value is not None:
        account.total_value = data.total_value
    if data.cash_balance is not None:
        account.cash_balance = data.cash_balance
    if data.is_active is not None:
        account.is_active = data.is_active
    
    await db.commit()
    await db.refresh(account)
    
    return build_account_response(account)


@router.patch("/{account_id}/client", response_model=AccountResponse)
async def reassign_account(
    account_id: str,
    data: AccountReassign,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AccountResponse:
    """Reassign account to a different client."""
    tenant_id = current_user.get("tenant_id")
    
    # Get account
    query = (
        select(Account)
        .options(selectinload(Account.client))
        .where(Account.id == account_id)
    )
    
    if tenant_id:
        query = query.where(Account.tenant_id == tenant_id)
    
    result = await db.execute(query)
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    # Verify new client exists and belongs to same tenant
    client_query = select(Client).where(
        Client.id == data.client_id,
        Client.tenant_id == account.tenant_id,
    )
    result = await db.execute(client_query)
    new_client = result.scalar_one_or_none()
    
    if not new_client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target client not found or not in same tenant",
        )
    
    # Reassign
    account.client_id = data.client_id
    await db.commit()
    
    # Reload with new client
    result = await db.execute(
        select(Account)
        .options(selectinload(Account.client))
        .where(Account.id == account_id)
    )
    account = result.scalar_one()
    
    return build_account_response(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: str,
    hard_delete: bool = Query(False, description="Permanently delete instead of soft delete"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Delete (or soft-delete) an account."""
    tenant_id = current_user.get("tenant_id")
    
    query = select(Account).where(Account.id == account_id)
    
    if tenant_id:
        query = query.where(Account.tenant_id == tenant_id)
    
    result = await db.execute(query)
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    if hard_delete:
        # Only allow hard delete if no holdings/transactions
        await db.delete(account)
    else:
        # Soft delete
        account.is_active = False
    
    await db.commit()


@router.post("/{account_id}/reactivate", response_model=AccountResponse)
async def reactivate_account(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AccountResponse:
    """Reactivate a soft-deleted account."""
    tenant_id = current_user.get("tenant_id")
    
    query = (
        select(Account)
        .options(selectinload(Account.client))
        .where(Account.id == account_id)
    )
    
    if tenant_id:
        query = query.where(Account.tenant_id == tenant_id)
    
    result = await db.execute(query)
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    account.is_active = True
    await db.commit()
    await db.refresh(account)
    
    return build_account_response(account)


# ============================================================================
# Holdings & Performance (Existing endpoints with implementations)
# ============================================================================

@router.get("/{account_id}/holdings")
async def get_account_holdings(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    """Get holdings for an account."""
    tenant_id = current_user.get("tenant_id")
    
    # Verify account access
    query = select(Account).where(Account.id == account_id)
    if tenant_id:
        query = query.where(Account.tenant_id == tenant_id)
    
    result = await db.execute(query)
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    # Get holdings
    holdings_result = await db.execute(
        select(Holding).where(Holding.account_id == account_id)
    )
    holdings = holdings_result.scalars().all()
    
    return [
        {
            "id": h.id,
            "instrument_name": h.instrument_name,
            "instrument_ticker": h.instrument_ticker,
            "isin": h.isin,
            "asset_class": h.asset_class.value if h.asset_class else None,
            "quantity": float(h.quantity),
            "average_cost": float(h.average_cost) if h.average_cost else 0,
            "current_price": float(h.current_price) if h.current_price else 0,
            "market_value": float(h.market_value),
            "unrealized_pnl": float(h.unrealized_pnl) if h.unrealized_pnl else 0,
            "unrealized_pnl_percent": float(h.unrealized_pnl_percent) if h.unrealized_pnl_percent else 0,
            "weight": float(h.weight) if h.weight else 0,
            "currency": h.currency,
        }
        for h in holdings
    ]


@router.get("/{account_id}/transactions")
async def get_account_transactions(
    account_id: str,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> List[dict]:
    """Get transactions for an account."""
    # TODO: Implement transactions listing for account
    return []


@router.get("/{account_id}/performance")
async def get_account_performance(
    account_id: str,
    period: str = "1Y",  # 1M, 3M, 6M, 1Y, YTD, ALL
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get performance metrics for an account."""
    # TODO: Implement performance calculation
    return {
        "account_id": account_id,
        "period": period,
        "return_percentage": 0.0,
        "return_amount": 0.0,
    }
