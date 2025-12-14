"""Schemas for client-facing portfolio APIs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================================
# Performance Schemas
# ============================================================================

class PerformanceMetrics(BaseModel):
    """Performance metrics for various time periods."""
    
    period_1m: Optional[float] = Field(None, alias="1M", description="1 month return %")
    period_3m: Optional[float] = Field(None, alias="3M", description="3 month return %")
    period_6m: Optional[float] = Field(None, alias="6M", description="6 month return %")
    period_ytd: Optional[float] = Field(None, alias="YTD", description="Year-to-date return %")
    period_1y: Optional[float] = Field(None, alias="1Y", description="1 year return %")
    
    class Config:
        populate_by_name = True


# ============================================================================
# Portfolio Summary
# ============================================================================

class PortfolioSummary(BaseModel):
    """High-level portfolio summary for dashboard view."""
    
    net_worth: Decimal = Field(..., description="Total portfolio value across all accounts")
    currency: str = Field(default="USD", description="Base currency for valuation")
    total_accounts: int = Field(..., description="Number of active accounts")
    total_holdings: int = Field(..., description="Number of unique holdings")
    cash_balance: Decimal = Field(..., description="Total cash across accounts")
    invested_value: Decimal = Field(..., description="Total invested (non-cash) value")
    performance: Optional[PerformanceMetrics] = Field(None, description="Performance metrics")
    last_updated: datetime = Field(..., description="Last data update timestamp")


# ============================================================================
# Account Schemas
# ============================================================================

class ClientAccountSummary(BaseModel):
    """Account summary for list view (sensitive data masked)."""
    
    id: str = Field(..., description="Account UUID")
    account_name: str = Field(..., description="Account display name")
    account_number_masked: str = Field(..., description="Masked account number (e.g., ****1234)")
    account_type: str = Field(..., description="Account type (investment, custody, etc.)")
    bank_name: Optional[str] = Field(None, description="Associated bank/custodian name")
    currency: str = Field(..., description="Account currency")
    total_value: Decimal = Field(..., description="Current total value")
    cash_balance: Decimal = Field(..., description="Cash portion")
    performance_1y: Optional[float] = Field(None, description="1-year return %")
    is_active: bool = Field(..., description="Whether account is active")

    class Config:
        from_attributes = True


class ClientAccountList(BaseModel):
    """List of client accounts."""
    
    accounts: List[ClientAccountSummary]
    total_count: int


# ============================================================================
# Holding Schemas
# ============================================================================

class ClientHolding(BaseModel):
    """Individual holding/position."""
    
    id: str = Field(..., description="Holding UUID")
    account_id: str = Field(..., description="Parent account UUID")
    instrument_name: str = Field(..., description="Security name")
    instrument_ticker: Optional[str] = Field(None, description="Ticker symbol")
    instrument_type: str = Field(..., description="Type (stock, bond, etf, etc.)")
    asset_class: str = Field(..., description="Asset class")
    quantity: Decimal = Field(..., description="Number of units held")
    current_price: Optional[Decimal] = Field(None, description="Current market price")
    cost_basis: Optional[Decimal] = Field(None, description="Cost basis")
    market_value: Decimal = Field(..., description="Current market value")
    currency: str = Field(..., description="Holding currency")
    unrealized_pnl: Optional[Decimal] = Field(None, description="Unrealized profit/loss")
    unrealized_pnl_percent: Optional[float] = Field(None, description="Unrealized P&L %")
    weight: Optional[float] = Field(None, description="Weight in portfolio %")
    as_of_date: date = Field(..., description="Valuation date")

    class Config:
        from_attributes = True


class ClientAccountDetail(BaseModel):
    """Detailed account view with holdings."""
    
    id: str
    account_name: str
    account_number_masked: str
    account_type: str
    bank_name: Optional[str]
    currency: str
    total_value: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    holdings_count: int
    holdings: List[ClientHolding]
    allocation: Optional["AllocationBreakdown"] = None
    is_active: bool
    last_updated: datetime

    class Config:
        from_attributes = True


class ClientHoldingsList(BaseModel):
    """Aggregated holdings across all accounts."""
    
    holdings: List[ClientHolding]
    total_count: int
    total_market_value: Decimal
    currency: str


# ============================================================================
# Transaction Schemas
# ============================================================================

class ClientTransaction(BaseModel):
    """Transaction record for client view."""
    
    id: str = Field(..., description="Transaction UUID")
    trade_date: date = Field(..., description="Trade date")
    settlement_date: Optional[date] = Field(None, description="Settlement date")
    transaction_type: str = Field(..., description="Type (buy, sell, dividend, etc.)")
    status: str = Field(..., description="Status (pending, settled, etc.)")
    instrument_name: Optional[str] = Field(None, description="Security name")
    quantity: Optional[Decimal] = Field(None, description="Quantity traded")
    price: Optional[Decimal] = Field(None, description="Price per unit")
    gross_amount: Decimal = Field(..., description="Gross amount")
    fees: Decimal = Field(..., description="Fees and commissions")
    net_amount: Decimal = Field(..., description="Net amount")
    currency: str = Field(..., description="Transaction currency")
    description: Optional[str] = Field(None, description="Transaction description")

    class Config:
        from_attributes = True


class ClientTransactionList(BaseModel):
    """Paginated transaction list."""
    
    transactions: List[ClientTransaction]
    total_count: int
    page: int
    limit: int
    has_more: bool


# ============================================================================
# Allocation Schemas
# ============================================================================

class AllocationItem(BaseModel):
    """Single allocation category."""
    
    category: str = Field(..., description="Category name")
    value: Decimal = Field(..., description="Market value in this category")
    percentage: float = Field(..., description="Percentage of total")
    count: int = Field(..., description="Number of holdings in category")


class AllocationBreakdown(BaseModel):
    """Portfolio allocation breakdown."""
    
    by_asset_class: List[AllocationItem] = Field(default_factory=list)
    by_geography: List[AllocationItem] = Field(default_factory=list)
    by_sector: List[AllocationItem] = Field(default_factory=list)
    by_currency: List[AllocationItem] = Field(default_factory=list)
    total_value: Decimal
    as_of_date: date


# ============================================================================
# Performance Schemas (Extended)
# ============================================================================

class PortfolioPerformance(BaseModel):
    """Comprehensive portfolio performance."""
    
    overall: PerformanceMetrics
    absolute_return_1y: Optional[Decimal] = Field(None, description="Absolute $ return (1Y)")
    by_account: Optional[List[dict]] = Field(None, description="Performance by account")
    by_asset_class: Optional[List[dict]] = Field(None, description="Performance by asset class")
    as_of_date: date
    is_estimated: bool = Field(
        default=True, 
        description="True if calculations are estimates (no historical data available). "
                    "Accurate TWRR requires daily valuation snapshots."
    )


# Update forward reference
ClientAccountDetail.model_rebuild()

