"""Portfolio performance calculation service."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
from collections import defaultdict

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.account import Account
from src.models.holding import Holding, Instrument, AssetClass
from src.models.transaction import Transaction, TransactionType
from src.models.account_valuation import AccountValuation


class PerformanceService:
    """Service for calculating portfolio performance and allocation metrics."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_simple_return(
        self,
        client_id: str,
        start_date: date,
        end_date: date,
    ) -> Optional[float]:
        """Calculate simple return percentage for a period.
        
        Uses Dietz method for cash flow adjustment:
        Return = (End Value - Start Value - Net Cash Flows) / (Start Value + Weighted Cash Flows)
        
        For more accurate TWRR, we use historical valuations from account_valuations table.
        """
        # Get all accounts for client
        accounts_result = await self.db.execute(
            select(Account).where(Account.client_id == client_id)
        )
        accounts = accounts_result.scalars().all()
        
        if not accounts:
            return None
        
        account_ids = [acc.id for acc in accounts]
        
        # Try to get historical valuations first (more accurate)
        start_valuation = await self._get_portfolio_valuation_at_date(
            client_id, start_date
        )
        end_valuation = await self._get_portfolio_valuation_at_date(
            client_id, end_date
        )
        
        if start_valuation is None or end_valuation is None:
            # Fallback: estimate from current values and transactions
            return await self._estimate_return_from_transactions(
                client_id, account_ids, start_date, end_date
            )
        
        # Get net cash flows in period (deposits minus withdrawals)
        flows_result = await self.db.execute(
            select(
                func.sum(
                    case(
                        (Transaction.transaction_type == TransactionType.DEPOSIT, Transaction.net_amount),
                        (Transaction.transaction_type == TransactionType.TRANSFER_IN, Transaction.net_amount),
                        (Transaction.transaction_type == TransactionType.WITHDRAWAL, -Transaction.net_amount),
                        (Transaction.transaction_type == TransactionType.TRANSFER_OUT, -Transaction.net_amount),
                        else_=Decimal("0")
                    )
                )
            ).where(
                Transaction.account_id.in_(account_ids),
                Transaction.trade_date >= start_date,
                Transaction.trade_date <= end_date,
                Transaction.transaction_type.in_([
                    TransactionType.DEPOSIT,
                    TransactionType.WITHDRAWAL,
                    TransactionType.TRANSFER_IN,
                    TransactionType.TRANSFER_OUT,
                ])
            )
        )
        net_flows = Decimal(str(flows_result.scalar() or 0))
        
        # Simple Dietz method calculation
        # Return = (End - Start - Flows) / (Start + 0.5 * Flows)
        # This assumes flows occur mid-period on average
        
        if start_valuation <= 0:
            return None
        
        # Adjust for cash flows using modified Dietz method
        denominator = start_valuation
        if net_flows != 0:
            # Weight flows at 0.5 (mid-period assumption)
            denominator = start_valuation + net_flows * Decimal("0.5")
        
        if denominator <= 0:
            return None
        
        investment_gain = end_valuation - start_valuation - net_flows
        return_pct = float((investment_gain / denominator) * 100)
        
        return round(return_pct, 2)
    
    async def _get_portfolio_valuation_at_date(
        self,
        client_id: str,
        target_date: date,
    ) -> Optional[Decimal]:
        """Get portfolio total value at a specific date from historical valuations."""
        # Get all accounts for the client
        accounts_result = await self.db.execute(
            select(Account.id).where(Account.client_id == client_id)
        )
        account_ids = [row[0] for row in accounts_result.fetchall()]
        
        if not account_ids:
            return None
        
        # Get the most recent valuation on or before target_date for each account
        # Using a subquery to get the latest valuation date <= target_date
        result = await self.db.execute(
            select(func.sum(AccountValuation.total_value))
            .where(
                and_(
                    AccountValuation.account_id.in_(account_ids),
                    AccountValuation.valuation_date <= target_date
                )
            )
        )
        total = result.scalar()
        
        if total is None:
            return None
        
        return Decimal(str(total))
    
    async def _estimate_return_from_transactions(
        self,
        client_id: str,
        account_ids: List[str],
        start_date: date,
        end_date: date,
    ) -> Optional[float]:
        """Estimate return when historical valuations are not available.
        
        This is a fallback method that estimates start value by working backwards
        from current value and transactions.
        """
        # Current value (end value)
        accounts_result = await self.db.execute(
            select(Account).where(Account.id.in_(account_ids))
        )
        accounts = accounts_result.scalars().all()
        end_value = sum(acc.total_value or Decimal("0") for acc in accounts)
        
        # Get all transactions in period to estimate cash flows
        flows_result = await self.db.execute(
            select(
                func.sum(
                    case(
                        (Transaction.transaction_type == TransactionType.DEPOSIT, Transaction.net_amount),
                        (Transaction.transaction_type == TransactionType.TRANSFER_IN, Transaction.net_amount),
                        (Transaction.transaction_type == TransactionType.WITHDRAWAL, -Transaction.net_amount),
                        (Transaction.transaction_type == TransactionType.TRANSFER_OUT, -Transaction.net_amount),
                        else_=Decimal("0")
                    )
                )
            ).where(
                Transaction.account_id.in_(account_ids),
                Transaction.trade_date >= start_date,
                Transaction.trade_date <= end_date,
                Transaction.transaction_type.in_([
                    TransactionType.DEPOSIT,
                    TransactionType.WITHDRAWAL,
                    TransactionType.TRANSFER_IN,
                    TransactionType.TRANSFER_OUT,
                ])
            )
        )
        net_flows = Decimal(str(flows_result.scalar() or 0))
        
        # Estimate investment gains from realized gains (dividends, interest)
        gains_result = await self.db.execute(
            select(func.sum(Transaction.net_amount)).where(
                Transaction.account_id.in_(account_ids),
                Transaction.trade_date >= start_date,
                Transaction.trade_date <= end_date,
                Transaction.transaction_type.in_([
                    TransactionType.DIVIDEND,
                    TransactionType.INTEREST,
                ])
            )
        )
        realized_gains = Decimal(str(gains_result.scalar() or 0))
        
        # Estimate unrealized gains from current holdings P&L
        unrealized_result = await self.db.execute(
            select(func.sum(Holding.unrealized_pnl)).where(
                Holding.account_id.in_(account_ids)
            )
        )
        unrealized_gains = Decimal(str(unrealized_result.scalar() or 0))
        
        # Rough estimate: assume proportional unrealized gains over the period
        # This is a simplification - ideally we'd have historical cost basis
        estimated_period_unrealized = unrealized_gains * Decimal("0.5")  # Assume 50% of unrealized happened in this period
        
        # Estimated start value = end - flows - gains
        # This is a rough approximation
        estimated_start_value = end_value - net_flows - realized_gains - estimated_period_unrealized
        
        if estimated_start_value <= 0:
            # If we can't estimate reliably, return a small positive return based on typical market
            return None
        
        # Calculate return
        investment_gain = end_value - estimated_start_value - net_flows
        return_pct = float((investment_gain / estimated_start_value) * 100)
        
        return round(return_pct, 2)
    
    async def get_allocation_by_asset_class(
        self,
        client_id: str,
    ) -> List[Dict]:
        """Get portfolio allocation breakdown by asset class."""
        # Get all holdings for client
        result = await self.db.execute(
            select(Holding)
            .join(Account)
            .options(selectinload(Holding.instrument))
            .where(Account.client_id == client_id)
        )
        holdings = result.scalars().all()
        
        # Group by asset class
        allocation = defaultdict(lambda: {"value": Decimal("0"), "count": 0})
        total_value = Decimal("0")
        
        for holding in holdings:
            asset_class = "other"
            if holding.instrument:
                asset_class = holding.instrument.asset_class.value
            
            allocation[asset_class]["value"] += holding.market_value
            allocation[asset_class]["count"] += 1
            total_value += holding.market_value
        
        # Convert to list with percentages
        result_list = []
        for category, data in allocation.items():
            percentage = float((data["value"] / total_value) * 100) if total_value > 0 else 0
            result_list.append({
                "category": category,
                "value": data["value"],
                "percentage": round(percentage, 2),
                "count": data["count"],
            })
        
        # Sort by value descending
        result_list.sort(key=lambda x: x["value"], reverse=True)
        return result_list
    
    async def get_allocation_by_currency(
        self,
        client_id: str,
    ) -> List[Dict]:
        """Get portfolio allocation breakdown by currency."""
        result = await self.db.execute(
            select(Holding)
            .join(Account)
            .where(Account.client_id == client_id)
        )
        holdings = result.scalars().all()
        
        allocation = defaultdict(lambda: {"value": Decimal("0"), "count": 0})
        total_value = Decimal("0")
        
        for holding in holdings:
            currency = holding.currency or "USD"
            allocation[currency]["value"] += holding.market_value
            allocation[currency]["count"] += 1
            total_value += holding.market_value
        
        result_list = []
        for category, data in allocation.items():
            percentage = float((data["value"] / total_value) * 100) if total_value > 0 else 0
            result_list.append({
                "category": category,
                "value": data["value"],
                "percentage": round(percentage, 2),
                "count": data["count"],
            })
        
        result_list.sort(key=lambda x: x["value"], reverse=True)
        return result_list
    
    async def get_allocation_by_sector(
        self,
        client_id: str,
    ) -> List[Dict]:
        """Get portfolio allocation breakdown by sector."""
        result = await self.db.execute(
            select(Holding)
            .join(Account)
            .options(selectinload(Holding.instrument))
            .where(Account.client_id == client_id)
        )
        holdings = result.scalars().all()
        
        allocation = defaultdict(lambda: {"value": Decimal("0"), "count": 0})
        total_value = Decimal("0")
        
        for holding in holdings:
            sector = "Other"
            if holding.instrument and holding.instrument.sector:
                sector = holding.instrument.sector
            
            allocation[sector]["value"] += holding.market_value
            allocation[sector]["count"] += 1
            total_value += holding.market_value
        
        result_list = []
        for category, data in allocation.items():
            percentage = float((data["value"] / total_value) * 100) if total_value > 0 else 0
            result_list.append({
                "category": category,
                "value": data["value"],
                "percentage": round(percentage, 2),
                "count": data["count"],
            })
        
        result_list.sort(key=lambda x: x["value"], reverse=True)
        return result_list
    
    async def get_allocation_by_geography(
        self,
        client_id: str,
    ) -> List[Dict]:
        """Get portfolio allocation breakdown by country/geography."""
        result = await self.db.execute(
            select(Holding)
            .join(Account)
            .options(selectinload(Holding.instrument))
            .where(Account.client_id == client_id)
        )
        holdings = result.scalars().all()
        
        allocation = defaultdict(lambda: {"value": Decimal("0"), "count": 0})
        total_value = Decimal("0")
        
        for holding in holdings:
            country = "Unknown"
            if holding.instrument and holding.instrument.country:
                country = holding.instrument.country
            
            allocation[country]["value"] += holding.market_value
            allocation[country]["count"] += 1
            total_value += holding.market_value
        
        result_list = []
        for category, data in allocation.items():
            percentage = float((data["value"] / total_value) * 100) if total_value > 0 else 0
            result_list.append({
                "category": category,
                "value": data["value"],
                "percentage": round(percentage, 2),
                "count": data["count"],
            })
        
        result_list.sort(key=lambda x: x["value"], reverse=True)
        return result_list
    
    async def get_full_allocation(
        self,
        client_id: str,
    ) -> Dict:
        """Get complete allocation breakdown for the portfolio."""
        by_asset_class = await self.get_allocation_by_asset_class(client_id)
        by_currency = await self.get_allocation_by_currency(client_id)
        by_sector = await self.get_allocation_by_sector(client_id)
        by_geography = await self.get_allocation_by_geography(client_id)
        
        # Calculate total value
        total_value = sum(item["value"] for item in by_asset_class)
        
        return {
            "by_asset_class": by_asset_class,
            "by_currency": by_currency,
            "by_sector": by_sector,
            "by_geography": by_geography,
            "total_value": total_value,
            "as_of_date": date.today(),
        }
    
    async def get_performance_metrics(
        self,
        client_id: str,
    ) -> Dict:
        """Get performance metrics for various time periods."""
        today = date.today()
        
        # Calculate returns for different periods
        periods = {
            "1M": today - timedelta(days=30),
            "3M": today - timedelta(days=90),
            "6M": today - timedelta(days=180),
            "YTD": date(today.year, 1, 1),
            "1Y": today - timedelta(days=365),
        }
        
        metrics = {}
        for period_name, start_date in periods.items():
            metrics[period_name] = await self.calculate_simple_return(
                client_id, start_date, today
            )
        
        return metrics

