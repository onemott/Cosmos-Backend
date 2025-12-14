"""Portfolio performance calculation service."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.account import Account
from src.models.holding import Holding, Instrument, AssetClass
from src.models.transaction import Transaction, TransactionType


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
        
        This is a simplified calculation:
        Return = (End Value - Start Value - Net Deposits) / Start Value * 100
        
        Note: For accurate TWRR, we need daily valuations which aren't available yet.
        """
        # Get all accounts for client
        accounts_result = await self.db.execute(
            select(Account).where(Account.client_id == client_id)
        )
        accounts = accounts_result.scalars().all()
        
        if not accounts:
            return None
        
        account_ids = [acc.id for acc in accounts]
        
        # Current value (end value)
        end_value = sum(acc.total_value or Decimal("0") for acc in accounts)
        
        # Get net cash flows in period
        flows_result = await self.db.execute(
            select(
                func.sum(Transaction.net_amount)
            ).where(
                Transaction.account_id.in_(account_ids),
                Transaction.trade_date >= start_date,
                Transaction.trade_date <= end_date,
                Transaction.transaction_type.in_([
                    TransactionType.DEPOSIT,
                    TransactionType.WITHDRAWAL,
                ])
            )
        )
        net_flows = flows_result.scalar() or Decimal("0")
        
        # Estimate start value (current - gains - flows)
        # This is a rough approximation without historical data
        start_value = end_value - net_flows
        
        if start_value <= 0:
            return None
        
        # Simple return calculation
        return_pct = float(((end_value - start_value) / start_value) * 100)
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

