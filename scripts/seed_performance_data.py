#!/usr/bin/env python3
"""
Seed script for generating historical valuation data for performance calculation.

This script creates:
- Monthly account valuations for the past 12 months
- Simulated market performance with realistic returns
- Cash flow transactions (deposits, withdrawals, dividends)

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_performance_data.py
    
    # With reset (clears existing valuations first):
    python scripts/seed_performance_data.py --reset
"""

import asyncio
import argparse
import random
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory
from src.models.tenant import Tenant
from src.models.client import Client
from src.models.client_user import ClientUser
from src.models.account import Account
from src.models.account_valuation import AccountValuation
from src.models.transaction import Transaction, TransactionType, TransactionStatus


# ============================================================================
# Performance Simulation Parameters
# ============================================================================

# Realistic annual return expectations by risk profile
RISK_PROFILE_RETURNS = {
    "conservative": {"mean": 0.04, "volatility": 0.06},   # 4% annual return, 6% volatility
    "balanced": {"mean": 0.07, "volatility": 0.12},       # 7% annual return, 12% volatility
    "growth": {"mean": 0.10, "volatility": 0.18},         # 10% annual return, 18% volatility
    "aggressive": {"mean": 0.12, "volatility": 0.25},     # 12% annual return, 25% volatility
}

# Monthly deposit probability and range
DEPOSIT_PROBABILITY = 0.3  # 30% chance of deposit each month
DEPOSIT_RANGE = (2000, 10000)  # Deposit amount range

# Monthly withdrawal probability and range  
WITHDRAWAL_PROBABILITY = 0.1  # 10% chance of withdrawal each month
WITHDRAWAL_RANGE = (1000, 5000)  # Withdrawal amount range

# Dividend yield (annual, paid quarterly)
DIVIDEND_YIELD_RANGE = (0.015, 0.03)  # 1.5% - 3% annual dividend yield


# ============================================================================
# Helper Functions
# ============================================================================

def simulate_monthly_return(
    annual_mean: float,
    annual_volatility: float,
    months_elapsed: int,
) -> float:
    """Simulate a realistic monthly return using geometric Brownian motion.
    
    This creates a more realistic return path with some autocorrelation
    and fat tails typical of financial markets.
    """
    # Convert annual parameters to monthly
    monthly_mean = annual_mean / 12
    monthly_vol = annual_volatility / math.sqrt(12)
    
    # Generate random return with slight autocorrelation
    random_return = random.gauss(monthly_mean, monthly_vol)
    
    # Add some momentum/reversion effect
    momentum = random.random() * 0.002  # Small momentum component
    
    return random_return + momentum


def generate_valuation_path(
    start_value: Decimal,
    months: int,
    risk_profile: str,
) -> list[Decimal]:
    """Generate a realistic valuation path over time.
    
    Returns a list of monthly valuations simulating market performance.
    """
    profile_params = RISK_PROFILE_RETURNS.get(risk_profile, RISK_PROFILE_RETURNS["balanced"])
    annual_mean = profile_params["mean"]
    annual_vol = profile_params["volatility"]
    
    valuations = [start_value]
    current_value = float(start_value)
    
    for month in range(1, months + 1):
        # Get monthly return
        monthly_return = simulate_monthly_return(annual_mean, annual_vol, month)
        
        # Apply return to current value
        current_value *= (1 + monthly_return)
        
        # Ensure value doesn't go negative
        current_value = max(current_value, 1000)
        
        valuations.append(Decimal(str(round(current_value, 2))))
    
    return valuations


# ============================================================================
# Seed Functions
# ============================================================================

async def get_clients_with_accounts(db: AsyncSession) -> list[tuple[Client, list[Account]]]:
    """Get all clients with their accounts."""
    result = await db.execute(
        select(Client)
    )
    clients = result.scalars().all()
    
    clients_with_accounts = []
    for client in clients:
        accounts_result = await db.execute(
            select(Account).where(Account.client_id == client.id)
        )
        accounts = accounts_result.scalars().all()
        if accounts:
            clients_with_accounts.append((client, accounts))
    
    return clients_with_accounts


async def clear_existing_valuations(db: AsyncSession, account_ids: list[str]):
    """Delete existing valuations for the given accounts."""
    if account_ids:
        await db.execute(
            delete(AccountValuation).where(AccountValuation.account_id.in_(account_ids))
        )


async def seed_valuations_for_account(
    db: AsyncSession,
    account: Account,
    risk_profile: str,
    months: int = 12,
):
    """Seed historical valuations for a single account."""
    today = date.today()
    
    # Get current account value as the end point
    current_value = account.total_value or Decimal("100000")
    
    # Generate valuation path working backwards from current value
    # We simulate forward performance to get to current value
    profile_params = RISK_PROFILE_RETURNS.get(risk_profile, RISK_PROFILE_RETURNS["balanced"])
    
    # Calculate what the starting value should have been to reach current value
    # with the expected return
    expected_annual_return = profile_params["mean"]
    expected_total_return = (1 + expected_annual_return) ** (months / 12)
    estimated_start_value = float(current_value) / expected_total_return
    
    # Add some randomness to the start value
    start_value = Decimal(str(round(estimated_start_value * random.uniform(0.9, 1.1), 2)))
    start_value = max(start_value, Decimal("10000"))  # Minimum start value
    
    # Generate forward path
    valuations = generate_valuation_path(start_value, months, risk_profile)
    
    # Adjust the last value to match current (minor adjustment for accuracy)
    if valuations:
        adjustment_factor = float(current_value) / float(valuations[-1])
        valuations = [Decimal(str(round(float(v) * adjustment_factor, 2))) for v in valuations]
    
    # Create valuation records (one per month)
    for i, value in enumerate(valuations):
        valuation_date = today - timedelta(days=30 * (months - i))
        
        # Split between cash and invested (roughly 10-20% cash)
        cash_pct = random.uniform(0.10, 0.20)
        cash = Decimal(str(round(float(value) * cash_pct, 2)))
        invested = value - cash
        
        valuation = AccountValuation(
            id=str(uuid4()),
            tenant_id=account.tenant_id,
            account_id=account.id,
            valuation_date=valuation_date,
            total_value=value,
            cash_balance=cash,
            invested_value=invested,
            currency=account.currency,
            holdings_count=random.randint(8, 15),
        )
        db.add(valuation)
    
    # Generate cash flow transactions based on valuations
    await seed_cash_flows_for_account(db, account, valuations, months)
    
    return len(valuations)


async def seed_cash_flows_for_account(
    db: AsyncSession,
    account: Account,
    valuations: list[Decimal],
    months: int,
):
    """Seed cash flow transactions (deposits, withdrawals, dividends) for an account."""
    today = date.today()
    
    for month_idx in range(1, months + 1):
        txn_date = today - timedelta(days=30 * (months - month_idx))
        settlement_date = txn_date + timedelta(days=2)
        
        # Deposit (occasional)
        if random.random() < DEPOSIT_PROBABILITY:
            amount = Decimal(str(random.randint(*DEPOSIT_RANGE)))
            txn = Transaction(
                id=str(uuid4()),
                tenant_id=account.tenant_id,
                account_id=account.id,
                transaction_type=TransactionType.DEPOSIT,
                status=TransactionStatus.SETTLED,
                instrument_id=None,
                instrument_name=None,
                quantity=None,
                price=None,
                gross_amount=amount,
                fees=Decimal("0"),
                net_amount=amount,
                currency=account.currency,
                trade_date=txn_date,
                settlement_date=settlement_date,
                booked_at=datetime.combine(settlement_date, datetime.min.time()),
                description="Monthly deposit",
            )
            db.add(txn)
        
        # Withdrawal (rare)
        if random.random() < WITHDRAWAL_PROBABILITY:
            amount = Decimal(str(random.randint(*WITHDRAWAL_RANGE)))
            txn = Transaction(
                id=str(uuid4()),
                tenant_id=account.tenant_id,
                account_id=account.id,
                transaction_type=TransactionType.WITHDRAWAL,
                status=TransactionStatus.SETTLED,
                instrument_id=None,
                instrument_name=None,
                quantity=None,
                price=None,
                gross_amount=amount,
                fees=Decimal("0"),
                net_amount=-amount,
                currency=account.currency,
                trade_date=txn_date,
                settlement_date=settlement_date,
                booked_at=datetime.combine(settlement_date, datetime.min.time()),
                description="Withdrawal",
            )
            db.add(txn)
        
        # Dividend (quarterly - months 3, 6, 9, 12)
        if month_idx % 3 == 0:
            # Calculate dividend based on portfolio value
            if month_idx <= len(valuations):
                portfolio_value = float(valuations[month_idx])
                dividend_yield = random.uniform(*DIVIDEND_YIELD_RANGE)
                quarterly_dividend = portfolio_value * dividend_yield / 4
                amount = Decimal(str(round(quarterly_dividend, 2)))
                
                if amount > 0:
                    txn = Transaction(
                        id=str(uuid4()),
                        tenant_id=account.tenant_id,
                        account_id=account.id,
                        transaction_type=TransactionType.DIVIDEND,
                        status=TransactionStatus.SETTLED,
                        instrument_id=None,
                        instrument_name="Portfolio Dividend",
                        quantity=None,
                        price=None,
                        gross_amount=amount,
                        fees=Decimal("0"),
                        net_amount=amount,
                        currency=account.currency,
                        trade_date=txn_date,
                        settlement_date=settlement_date,
                        booked_at=datetime.combine(settlement_date, datetime.min.time()),
                        description="Quarterly dividend distribution",
                    )
                    db.add(txn)
        
        # Interest (monthly for cash holdings)
        if month_idx <= len(valuations):
            cash_value = float(valuations[month_idx]) * random.uniform(0.10, 0.20)
            monthly_interest = cash_value * 0.04 / 12  # ~4% annual interest on cash
            amount = Decimal(str(round(monthly_interest, 2)))
            
            if amount > 0:
                txn = Transaction(
                    id=str(uuid4()),
                    tenant_id=account.tenant_id,
                    account_id=account.id,
                    transaction_type=TransactionType.INTEREST,
                    status=TransactionStatus.SETTLED,
                    instrument_id=None,
                    instrument_name="Cash Interest",
                    quantity=None,
                    price=None,
                    gross_amount=amount,
                    fees=Decimal("0"),
                    net_amount=amount,
                    currency=account.currency,
                    trade_date=txn_date,
                    settlement_date=settlement_date,
                    booked_at=datetime.combine(settlement_date, datetime.min.time()),
                    description="Monthly interest on cash balance",
                )
                db.add(txn)


async def main(reset: bool = False, months: int = 12):
    """Main seed function."""
    print("=" * 60)
    print("Performance Data Seed Script")
    print("=" * 60)
    
    async with async_session_factory() as db:
        # Get all clients with accounts
        clients_with_accounts = await get_clients_with_accounts(db)
        
        if not clients_with_accounts:
            print("\nNo clients with accounts found. Please run seed_client_portfolio.py first.")
            return
        
        print(f"\nFound {len(clients_with_accounts)} clients with accounts")
        
        total_valuations = 0
        total_transactions = 0
        
        for client, accounts in clients_with_accounts:
            print(f"\nProcessing client: {client.email}")
            print(f"  Risk profile: {client.risk_profile.value if client.risk_profile else 'balanced'}")
            print(f"  Accounts: {len(accounts)}")
            
            if reset:
                account_ids = [acc.id for acc in accounts]
                await clear_existing_valuations(db, account_ids)
                print("  Cleared existing valuations")
            
            for account in accounts:
                num_valuations = await seed_valuations_for_account(
                    db, 
                    account, 
                    client.risk_profile.value if client.risk_profile else "balanced",
                    months
                )
                total_valuations += num_valuations
                print(f"  Created {num_valuations} valuations for {account.account_name}")
        
        await db.commit()
        
        print("\n" + "=" * 60)
        print("Seed complete!")
        print("=" * 60)
        print(f"\nTotal valuations created: {total_valuations}")
        print(f"Total clients processed: {len(clients_with_accounts)}")
        print("\nPerformance metrics will now be calculated from historical data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed performance data for portfolio calculations")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset existing valuations before seeding",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=12,
        help="Number of months of historical data to generate (default: 12)",
    )
    args = parser.parse_args()
    
    asyncio.run(main(reset=args.reset, months=args.months))
