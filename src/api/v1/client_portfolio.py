"""Client-facing portfolio API endpoints."""

from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_current_client
from src.db.session import get_db
from src.models.account import Account, BankConnection
from src.models.holding import Holding, Instrument
from src.models.transaction import Transaction
from src.schemas.client_portfolio import (
    PortfolioSummary,
    ClientAccountSummary,
    ClientAccountList,
    ClientAccountDetail,
    ClientHolding,
    ClientHoldingsList,
    ClientTransaction,
    ClientTransactionList,
    PerformanceMetrics,
    AllocationBreakdown,
    AllocationItem,
    PortfolioPerformance,
)
from src.services.performance_service import PerformanceService

router = APIRouter(prefix="/client", tags=["Client Portfolio"])


def mask_account_number(account_number: str) -> str:
    """Mask account number showing only last 4 digits."""
    if len(account_number) <= 4:
        return account_number
    return "****" + account_number[-4:]


# ============================================================================
# Portfolio Summary
# ============================================================================

@router.get(
    "/portfolio/summary",
    response_model=PortfolioSummary,
    summary="Get portfolio summary",
    description="Get high-level portfolio summary including net worth, account count, and performance.",
)
async def get_portfolio_summary(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> PortfolioSummary:
    """Get portfolio summary for the authenticated client."""
    client_id = current_client["client_id"]
    
    # Get all active accounts for this client
    result = await db.execute(
        select(Account)
        .where(
            Account.client_id == client_id,
            Account.is_active == True,
        )
    )
    accounts = result.scalars().all()
    
    if not accounts:
        return PortfolioSummary(
            net_worth=Decimal("0"),
            currency="USD",
            total_accounts=0,
            total_holdings=0,
            cash_balance=Decimal("0"),
            invested_value=Decimal("0"),
            performance=None,
            last_updated=datetime.now(timezone.utc),
        )
    
    # Calculate totals
    total_value = sum(acc.total_value or Decimal("0") for acc in accounts)
    total_cash = sum(acc.cash_balance or Decimal("0") for acc in accounts)
    invested_value = total_value - total_cash
    
    # Count holdings
    holdings_result = await db.execute(
        select(func.count(Holding.id))
        .join(Account)
        .where(Account.client_id == client_id)
    )
    total_holdings = holdings_result.scalar() or 0
    
    # Calculate performance using PerformanceService
    perf_service = PerformanceService(db)
    metrics = await perf_service.get_performance_metrics(client_id)
    
    performance = PerformanceMetrics(
        period_1m=metrics.get("1M"),
        period_3m=metrics.get("3M"),
        period_6m=metrics.get("6M"),
        period_ytd=metrics.get("YTD"),
        period_1y=metrics.get("1Y"),
    )
    
    return PortfolioSummary(
        net_worth=total_value,
        currency="USD",  # TODO: Support base currency preference
        total_accounts=len(accounts),
        total_holdings=total_holdings,
        cash_balance=total_cash,
        invested_value=invested_value,
        performance=performance,
        last_updated=datetime.now(timezone.utc),
    )


# ============================================================================
# Accounts
# ============================================================================

@router.get(
    "/accounts",
    response_model=ClientAccountList,
    summary="List client accounts",
    description="Get list of all accounts for the authenticated client.",
)
async def list_accounts(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> ClientAccountList:
    """List all accounts for the authenticated client."""
    client_id = current_client["client_id"]
    
    # Get accounts with bank connection
    result = await db.execute(
        select(Account)
        .options(selectinload(Account.bank_connection))
        .where(Account.client_id == client_id)
        .order_by(Account.account_name)
    )
    accounts = result.scalars().all()
    
    account_summaries = []
    for acc in accounts:
        bank_name = acc.bank_connection.bank_name if acc.bank_connection else None
        
        account_summaries.append(
            ClientAccountSummary(
                id=acc.id,
                account_name=acc.account_name,
                account_number_masked=mask_account_number(acc.account_number),
                account_type=acc.account_type.value,
                bank_name=bank_name,
                currency=acc.currency,
                total_value=acc.total_value or Decimal("0"),
                cash_balance=acc.cash_balance or Decimal("0"),
                performance_1y=None,  # TODO: Calculate from historical data
                is_active=acc.is_active,
            )
        )
    
    return ClientAccountList(
        accounts=account_summaries,
        total_count=len(account_summaries),
    )


@router.get(
    "/accounts/{account_id}",
    response_model=ClientAccountDetail,
    summary="Get account detail",
    description="Get detailed account information including holdings.",
)
async def get_account_detail(
    account_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> ClientAccountDetail:
    """Get detailed account information including holdings."""
    client_id = current_client["client_id"]
    
    # Get account with holdings
    result = await db.execute(
        select(Account)
        .options(
            selectinload(Account.bank_connection),
            selectinload(Account.holdings).selectinload(Holding.instrument),
        )
        .where(
            Account.id == account_id,
            Account.client_id == client_id,  # Security: verify ownership
        )
    )
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    bank_name = account.bank_connection.bank_name if account.bank_connection else None
    
    # Build holdings list
    holdings = []
    total_invested = Decimal("0")
    
    for holding in account.holdings:
        instrument = holding.instrument
        holdings.append(
            ClientHolding(
                id=holding.id,
                account_id=account.id,
                instrument_name=instrument.name if instrument else "Unknown",
                instrument_ticker=instrument.ticker if instrument else None,
                instrument_type=instrument.instrument_type.value if instrument else "other",
                asset_class=instrument.asset_class.value if instrument else "other",
                quantity=holding.quantity,
                current_price=instrument.last_price if instrument else None,
                cost_basis=holding.cost_basis,
                market_value=holding.market_value,
                currency=holding.currency,
                unrealized_pnl=holding.unrealized_pnl,
                unrealized_pnl_percent=float(holding.unrealized_pnl_percent) if holding.unrealized_pnl_percent else None,
                weight=None,  # Calculated below
                as_of_date=holding.as_of_date,
            )
        )
        total_invested += holding.market_value
    
    # Calculate weights
    if total_invested > 0:
        for h in holdings:
            h.weight = float((h.market_value / total_invested) * 100)
    
    return ClientAccountDetail(
        id=account.id,
        account_name=account.account_name,
        account_number_masked=mask_account_number(account.account_number),
        account_type=account.account_type.value,
        bank_name=bank_name,
        currency=account.currency,
        total_value=account.total_value or Decimal("0"),
        cash_balance=account.cash_balance or Decimal("0"),
        invested_value=total_invested,
        holdings_count=len(holdings),
        holdings=holdings,
        allocation=None,  # TODO: Calculate allocation breakdown
        is_active=account.is_active,
        last_updated=datetime.now(timezone.utc),
    )


# ============================================================================
# Holdings
# ============================================================================

@router.get(
    "/holdings",
    response_model=ClientHoldingsList,
    summary="List all holdings",
    description="Get all holdings across all accounts for the authenticated client.",
)
async def list_holdings(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    asset_class: Optional[str] = Query(None, description="Filter by asset class"),
    currency: Optional[str] = Query(None, description="Filter by currency"),
    account_id: Optional[str] = Query(None, description="Filter by account"),
) -> ClientHoldingsList:
    """List all holdings across all client accounts."""
    client_id = current_client["client_id"]
    
    # Validate account_id belongs to this client if provided
    if account_id:
        acc_check = await db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.client_id == client_id,
            )
        )
        if not acc_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found",
            )
    
    # Build query
    query = (
        select(Holding)
        .join(Account)
        .options(selectinload(Holding.instrument))
        .where(Account.client_id == client_id)
    )
    
    # Apply filters at DB level
    if account_id:
        query = query.where(Holding.account_id == account_id)
    if currency:
        query = query.where(Holding.currency == currency)
    
    result = await db.execute(query.order_by(Holding.market_value.desc()))
    holdings_db = result.scalars().all()
    
    # Filter by asset_class in Python (instrument already loaded via selectinload)
    if asset_class:
        holdings_db = [
            h for h in holdings_db 
            if h.instrument and h.instrument.asset_class.value == asset_class
        ]
    
    total_value = Decimal("0")
    holdings = []
    
    for holding in holdings_db:
        instrument = holding.instrument
        holdings.append(
            ClientHolding(
                id=holding.id,
                account_id=holding.account_id,
                instrument_name=instrument.name if instrument else "Unknown",
                instrument_ticker=instrument.ticker if instrument else None,
                instrument_type=instrument.instrument_type.value if instrument else "other",
                asset_class=instrument.asset_class.value if instrument else "other",
                quantity=holding.quantity,
                current_price=instrument.last_price if instrument else None,
                cost_basis=holding.cost_basis,
                market_value=holding.market_value,
                currency=holding.currency,
                unrealized_pnl=holding.unrealized_pnl,
                unrealized_pnl_percent=float(holding.unrealized_pnl_percent) if holding.unrealized_pnl_percent else None,
                weight=None,
                as_of_date=holding.as_of_date,
            )
        )
        total_value += holding.market_value
    
    # Calculate weights
    if total_value > 0:
        for h in holdings:
            h.weight = float((h.market_value / total_value) * 100)
    
    return ClientHoldingsList(
        holdings=holdings,
        total_count=len(holdings),
        total_market_value=total_value,
        currency="USD",  # TODO: Support multi-currency
    )


# ============================================================================
# Transactions
# ============================================================================

@router.get(
    "/accounts/{account_id}/transactions",
    response_model=ClientTransactionList,
    summary="List account transactions",
    description="Get transaction history for a specific account with pagination.",
)
async def list_account_transactions(
    account_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100, description="Number of transactions to return"),
    offset: int = Query(0, ge=0, description="Number of transactions to skip"),
    transaction_type: Optional[str] = Query(None, description="Filter by transaction type"),
    start_date: Optional[date] = Query(None, description="Filter by start date"),
    end_date: Optional[date] = Query(None, description="Filter by end date"),
) -> ClientTransactionList:
    """Get transaction history for an account."""
    client_id = current_client["client_id"]
    
    # Verify account belongs to client
    account_result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.client_id == client_id,
        )
    )
    account = account_result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    # Build query
    query = select(Transaction).where(Transaction.account_id == account_id)
    count_query = select(func.count(Transaction.id)).where(Transaction.account_id == account_id)
    
    # Apply filters
    if transaction_type:
        query = query.where(Transaction.transaction_type == transaction_type)
        count_query = count_query.where(Transaction.transaction_type == transaction_type)
    if start_date:
        query = query.where(Transaction.trade_date >= start_date)
        count_query = count_query.where(Transaction.trade_date >= start_date)
    if end_date:
        query = query.where(Transaction.trade_date <= end_date)
        count_query = count_query.where(Transaction.trade_date <= end_date)
    
    # Get total count
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0
    
    # Get paginated results
    query = query.order_by(Transaction.trade_date.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    transactions_db = result.scalars().all()
    
    transactions = [
        ClientTransaction(
            id=txn.id,
            trade_date=txn.trade_date,
            settlement_date=txn.settlement_date,
            transaction_type=txn.transaction_type.value,
            status=txn.status.value,
            instrument_name=txn.instrument_name,
            quantity=txn.quantity,
            price=txn.price,
            gross_amount=txn.gross_amount,
            fees=txn.fees,
            net_amount=txn.net_amount,
            currency=txn.currency,
            description=txn.description,
        )
        for txn in transactions_db
    ]
    
    return ClientTransactionList(
        transactions=transactions,
        total_count=total_count,
        page=(offset // limit) + 1,
        limit=limit,
        has_more=(offset + limit) < total_count,
    )


# ============================================================================
# Performance
# ============================================================================

@router.get(
    "/performance",
    response_model=PortfolioPerformance,
    summary="Get portfolio performance",
    description="Get performance metrics for the client's portfolio.",
)
async def get_portfolio_performance(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> PortfolioPerformance:
    """Get performance metrics for the portfolio."""
    client_id = current_client["client_id"]
    
    perf_service = PerformanceService(db)
    metrics = await perf_service.get_performance_metrics(client_id)
    
    # Calculate 1Y absolute return
    accounts_result = await db.execute(
        select(Account).where(Account.client_id == client_id)
    )
    accounts = accounts_result.scalars().all()
    total_value = sum(acc.total_value or Decimal("0") for acc in accounts)
    
    # Estimate 1Y absolute return
    absolute_return = None
    if metrics.get("1Y") is not None:
        absolute_return = total_value * Decimal(str(metrics["1Y"])) / 100
    
    return PortfolioPerformance(
        overall=PerformanceMetrics(
            period_1m=metrics.get("1M"),
            period_3m=metrics.get("3M"),
            period_6m=metrics.get("6M"),
            period_ytd=metrics.get("YTD"),
            period_1y=metrics.get("1Y"),
        ),
        absolute_return_1y=absolute_return,
        by_account=None,  # TODO: Implement per-account performance
        by_asset_class=None,  # TODO: Implement per-asset-class performance
        as_of_date=date.today(),
        is_estimated=True,  # No historical valuation data available yet
    )


# ============================================================================
# Allocation
# ============================================================================

@router.get(
    "/allocation",
    response_model=AllocationBreakdown,
    summary="Get portfolio allocation",
    description="Get portfolio allocation breakdown by asset class, sector, geography, and currency.",
)
async def get_portfolio_allocation(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> AllocationBreakdown:
    """Get portfolio allocation breakdown."""
    client_id = current_client["client_id"]
    
    perf_service = PerformanceService(db)
    allocation = await perf_service.get_full_allocation(client_id)
    
    # Convert to response schema
    return AllocationBreakdown(
        by_asset_class=[
            AllocationItem(
                category=item["category"],
                value=item["value"],
                percentage=item["percentage"],
                count=item["count"],
            )
            for item in allocation["by_asset_class"]
        ],
        by_geography=[
            AllocationItem(
                category=item["category"],
                value=item["value"],
                percentage=item["percentage"],
                count=item["count"],
            )
            for item in allocation["by_geography"]
        ],
        by_sector=[
            AllocationItem(
                category=item["category"],
                value=item["value"],
                percentage=item["percentage"],
                count=item["count"],
            )
            for item in allocation["by_sector"]
        ],
        by_currency=[
            AllocationItem(
                category=item["category"],
                value=item["value"],
                percentage=item["percentage"],
                count=item["count"],
            )
            for item in allocation["by_currency"]
        ],
        total_value=allocation["total_value"],
        as_of_date=allocation["as_of_date"],
    )

