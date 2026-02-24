#!/usr/bin/env python3
"""
Seed script for creating realistic client portfolio test data.

This script creates:
- 2 test clients with ClientUser credentials
- 2-3 accounts per client
- 15-20 holdings per client (stocks, bonds, funds)
- 50-100 transactions per client (12 months history)

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_client_portfolio.py
    
    # With reset (clears existing test data first):
    python scripts/seed_client_portfolio.py --reset
"""

import asyncio
import argparse
import random
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
from src.core.security import hash_password
from src.models.tenant import Tenant
from src.models.client import Client, ClientType, KYCStatus, RiskProfile
from src.models.client_user import ClientUser
from src.models.account import Account, AccountType, BankConnection, ConnectionStatus
from src.models.holding import Holding, Instrument, AssetClass, InstrumentType
from src.models.transaction import Transaction, TransactionType, TransactionStatus


# ============================================================================
# Test Data Definitions
# ============================================================================

TEST_CLIENTS = [
    {
        "email": "client1@test.com",
        "password": "Test1234!",
        "first_name": "John",
        "last_name": "Smith",
        "client_type": ClientType.INDIVIDUAL,
        "risk_profile": RiskProfile.BALANCED,
        "kyc_status": KYCStatus.APPROVED,
    },
    {
        "email": "client2@test.com",
        "password": "Test1234!",
        "first_name": "Sarah",
        "last_name": "Johnson",
        "client_type": ClientType.INDIVIDUAL,
        "risk_profile": RiskProfile.GROWTH,
        "kyc_status": KYCStatus.APPROVED,
    },
]

BANKS = [
    {"code": "ubs", "name": "UBS Switzerland"},
    {"code": "cs", "name": "Credit Suisse"},
    {"code": "hsbc", "name": "HSBC Private Bank"},
    {"code": "jpmorgan", "name": "JP Morgan Private Bank"},
]

INSTRUMENTS = [
    # US Stocks
    {"ticker": "AAPL", "name": "Apple Inc.", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Technology", "price": Decimal("178.50")},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Technology", "price": Decimal("378.25")},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Technology", "price": Decimal("141.80")},
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Consumer Discretionary", "price": Decimal("178.35")},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Technology", "price": Decimal("495.50")},
    {"ticker": "META", "name": "Meta Platforms Inc.", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Technology", "price": Decimal("505.75")},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Financials", "price": Decimal("195.20")},
    {"ticker": "V", "name": "Visa Inc.", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Financials", "price": Decimal("275.40")},
    # European Stocks
    {"ticker": "NESN.SW", "name": "Nestlé S.A.", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "CHF", "country": "CH", "sector": "Consumer Staples", "price": Decimal("98.50")},
    {"ticker": "NOVN.SW", "name": "Novartis AG", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "CHF", "country": "CH", "sector": "Healthcare", "price": Decimal("89.75")},
    {"ticker": "ROG.SW", "name": "Roche Holding AG", "type": InstrumentType.STOCK, "asset_class": AssetClass.EQUITY, "currency": "CHF", "country": "CH", "sector": "Healthcare", "price": Decimal("245.30")},
    # ETFs
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "type": InstrumentType.ETF, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Broad Market", "price": Decimal("478.50")},
    {"ticker": "QQQ", "name": "Invesco QQQ Trust", "type": InstrumentType.ETF, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Technology", "price": Decimal("405.20")},
    {"ticker": "VTI", "name": "Vanguard Total Stock Market ETF", "type": InstrumentType.ETF, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "Broad Market", "price": Decimal("238.75")},
    {"ticker": "VXUS", "name": "Vanguard Total International Stock ETF", "type": InstrumentType.ETF, "asset_class": AssetClass.EQUITY, "currency": "USD", "country": "US", "sector": "International", "price": Decimal("56.80")},
    # Bonds
    {"ticker": "BND", "name": "Vanguard Total Bond Market ETF", "type": InstrumentType.ETF, "asset_class": AssetClass.FIXED_INCOME, "currency": "USD", "country": "US", "sector": "Bonds", "price": Decimal("72.45")},
    {"ticker": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "type": InstrumentType.ETF, "asset_class": AssetClass.FIXED_INCOME, "currency": "USD", "country": "US", "sector": "Government Bonds", "price": Decimal("92.30")},
    {"ticker": "LQD", "name": "iShares iBoxx $ Investment Grade Corporate Bond ETF", "type": InstrumentType.ETF, "asset_class": AssetClass.FIXED_INCOME, "currency": "USD", "country": "US", "sector": "Corporate Bonds", "price": Decimal("108.15")},
    # Alternatives
    {"ticker": "GLD", "name": "SPDR Gold Shares", "type": InstrumentType.ETF, "asset_class": AssetClass.COMMODITIES, "currency": "USD", "country": "US", "sector": "Commodities", "price": Decimal("185.60")},
    {"ticker": "VNQ", "name": "Vanguard Real Estate ETF", "type": InstrumentType.ETF, "asset_class": AssetClass.REAL_ESTATE, "currency": "USD", "country": "US", "sector": "Real Estate", "price": Decimal("82.40")},
]


# ============================================================================
# Helper Functions
# ============================================================================

def mask_account_number(account_number: str) -> str:
    """Mask account number showing only last 4 digits."""
    if len(account_number) <= 4:
        return account_number
    return "****" + account_number[-4:]


def generate_account_number() -> str:
    """Generate a random account number."""
    return f"{random.randint(1000, 9999)}-{random.randint(100000, 999999)}"


def random_date_in_range(start: date, end: date) -> date:
    """Generate a random date between start and end."""
    delta = end - start
    random_days = random.randint(0, delta.days)
    return start + timedelta(days=random_days)


def calculate_cost_basis(price: Decimal, quantity: Decimal) -> Decimal:
    """Calculate cost basis with slight historical variance."""
    # Assume bought at slightly different price (±15%)
    variance = Decimal(str(random.uniform(0.85, 1.15)))
    return (price * variance * quantity).quantize(Decimal("0.01"))


# ============================================================================
# Seed Functions
# ============================================================================

async def get_or_create_tenant(db: AsyncSession) -> Tenant:
    """Get the first tenant or create a default one."""
    result = await db.execute(select(Tenant).limit(1))
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        tenant = Tenant(
            id=str(uuid4()),
            name="Demo EAM Firm",
            slug="demo-eam",
            is_active=True,
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        print(f"Created tenant: {tenant.name}")
    else:
        print(f"Using existing tenant: {tenant.name}")
    
    return tenant


async def seed_instruments(db: AsyncSession) -> list[Instrument]:
    """Seed financial instruments."""
    instruments = []
    
    for inst_data in INSTRUMENTS:
        # Check if instrument already exists
        result = await db.execute(
            select(Instrument).where(Instrument.ticker == inst_data["ticker"])
        )
        instrument = result.scalars().first()
        
        if not instrument:
            instrument = Instrument(
                id=str(uuid4()),
                ticker=inst_data["ticker"],
                name=inst_data["name"],
                instrument_type=inst_data["type"],
                asset_class=inst_data["asset_class"],
                currency=inst_data["currency"],
                country=inst_data["country"],
                sector=inst_data["sector"],
                last_price=inst_data["price"],
                price_date=date.today(),
            )
            db.add(instrument)
            print(f"  Created instrument: {inst_data['ticker']}")
        else:
            # Update price
            instrument.last_price = inst_data["price"]
            instrument.price_date = date.today()
        
        instruments.append(instrument)
    
    await db.commit()
    return instruments


async def seed_client_with_portfolio(
    db: AsyncSession,
    tenant: Tenant,
    client_data: dict,
    instruments: list[Instrument],
) -> Client:
    """Seed a single client with complete portfolio data."""
    
    # Check if client already exists
    result = await db.execute(
        select(ClientUser).where(ClientUser.email == client_data["email"])
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        print(f"\n  Client {client_data['email']} already exists, skipping...")
        return None
    
    print(f"\n  Creating client: {client_data['first_name']} {client_data['last_name']}")
    
    # Create Client
    client = Client(
        id=str(uuid4()),
        tenant_id=tenant.id,
        client_type=client_data["client_type"],
        first_name=client_data["first_name"],
        last_name=client_data["last_name"],
        email=client_data["email"],
        phone=f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
        kyc_status=client_data["kyc_status"],
        risk_profile=client_data["risk_profile"],
    )
    db.add(client)
    await db.flush()
    
    # Create ClientUser (login credentials)
    client_user = ClientUser(
        id=str(uuid4()),
        client_id=client.id,
        tenant_id=tenant.id,
        email=client_data["email"],
        hashed_password=hash_password(client_data["password"]),
        is_active=True,
    )
    db.add(client_user)
    print(f"    Created login: {client_data['email']} / {client_data['password']}")
    
    # Create Bank Connections and Accounts
    num_banks = random.randint(2, 3)
    selected_banks = random.sample(BANKS, num_banks)
    accounts = []
    
    for bank_data in selected_banks:
        bank_connection = BankConnection(
            id=str(uuid4()),
            tenant_id=tenant.id,
            client_id=client.id,
            bank_code=bank_data["code"],
            bank_name=bank_data["name"],
            status=ConnectionStatus.ACTIVE,
            last_sync_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(bank_connection)
        await db.flush()
        
        # Create 1-2 accounts per bank
        num_accounts = random.randint(1, 2)
        account_types = [AccountType.INVESTMENT, AccountType.CUSTODY]
        
        for i in range(num_accounts):
            account_type = account_types[i] if i < len(account_types) else AccountType.INVESTMENT
            account = Account(
                id=str(uuid4()),
                tenant_id=tenant.id,
                client_id=client.id,
                bank_connection_id=bank_connection.id,
                account_number=generate_account_number(),
                account_name=f"{bank_data['name']} - {account_type.value.title()} Account",
                account_type=account_type,
                currency="USD" if bank_data["code"] != "ubs" else "CHF",
                is_active=True,
            )
            db.add(account)
            accounts.append(account)
            print(f"    Created account: {account.account_name}")
    
    await db.flush()
    
    # Distribute holdings across accounts
    num_holdings = random.randint(15, 20)
    selected_instruments = random.sample(instruments, min(num_holdings, len(instruments)))
    
    total_portfolio_value = Decimal("0")
    
    for i, instrument in enumerate(selected_instruments):
        # Assign to a random account
        account = random.choice(accounts)
        
        # Generate realistic quantity and values
        if instrument.instrument_type == InstrumentType.STOCK:
            quantity = Decimal(str(random.randint(50, 500)))
        elif instrument.instrument_type == InstrumentType.ETF:
            quantity = Decimal(str(random.randint(100, 1000)))
        else:
            quantity = Decimal(str(random.randint(10, 200)))
        
        market_value = (instrument.last_price * quantity).quantize(Decimal("0.01"))
        cost_basis = calculate_cost_basis(instrument.last_price, quantity)
        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_pct = ((market_value / cost_basis - 1) * 100).quantize(Decimal("0.01")) if cost_basis > 0 else Decimal("0")
        
        holding = Holding(
            id=str(uuid4()),
            tenant_id=tenant.id,
            account_id=account.id,
            instrument_id=instrument.id,
            quantity=quantity,
            cost_basis=cost_basis,
            market_value=market_value,
            currency=instrument.currency,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_percent=unrealized_pnl_pct,
            as_of_date=date.today(),
        )
        db.add(holding)
        total_portfolio_value += market_value
    
    print(f"    Created {len(selected_instruments)} holdings")
    
    # Update account values
    for account in accounts:
        # Get holdings for this account
        holdings_result = await db.execute(
            select(Holding).where(Holding.account_id == account.id)
        )
        account_holdings = holdings_result.scalars().all()
        
        invested = sum(h.market_value for h in account_holdings)
        cash = Decimal(str(random.randint(10000, 100000)))
        account.total_value = invested + cash
        account.cash_balance = cash
    
    await db.flush()
    
    # Generate transactions (last 12 months)
    num_transactions = random.randint(50, 100)
    start_date = date.today() - timedelta(days=365)
    end_date = date.today()
    
    transaction_types_weights = [
        (TransactionType.BUY, 30),
        (TransactionType.SELL, 15),
        (TransactionType.DIVIDEND, 20),
        (TransactionType.DEPOSIT, 10),
        (TransactionType.WITHDRAWAL, 5),
        (TransactionType.FEE, 10),
        (TransactionType.INTEREST, 10),
    ]
    
    for _ in range(num_transactions):
        account = random.choice(accounts)
        txn_type = random.choices(
            [t[0] for t in transaction_types_weights],
            weights=[t[1] for t in transaction_types_weights]
        )[0]
        
        trade_date = random_date_in_range(start_date, end_date)
        settlement_date = trade_date + timedelta(days=2)
        
        # Generate amounts based on transaction type
        if txn_type in [TransactionType.BUY, TransactionType.SELL]:
            instrument = random.choice(instruments)
            quantity = Decimal(str(random.randint(10, 100)))
            price = instrument.last_price * Decimal(str(random.uniform(0.9, 1.1)))
            gross = (quantity * price).quantize(Decimal("0.01"))
            fees = (gross * Decimal("0.001")).quantize(Decimal("0.01"))
            net = gross + fees if txn_type == TransactionType.BUY else gross - fees
            instrument_name = instrument.name
        elif txn_type == TransactionType.DIVIDEND:
            instrument = random.choice([i for i in instruments if i.asset_class == AssetClass.EQUITY])
            quantity = None
            price = None
            gross = Decimal(str(random.randint(50, 500)))
            fees = Decimal("0")
            net = gross
            instrument_name = instrument.name
        elif txn_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL]:
            quantity = None
            price = None
            gross = Decimal(str(random.randint(5000, 50000)))
            fees = Decimal("0")
            net = gross if txn_type == TransactionType.DEPOSIT else -gross
            instrument_name = None
            instrument = None
        else:  # FEE, INTEREST
            quantity = None
            price = None
            gross = Decimal(str(random.randint(10, 200)))
            fees = Decimal("0")
            net = -gross if txn_type == TransactionType.FEE else gross
            instrument_name = None
            instrument = None
        
        transaction = Transaction(
            id=str(uuid4()),
            tenant_id=tenant.id,
            account_id=account.id,
            transaction_type=txn_type,
            status=TransactionStatus.SETTLED,
            instrument_id=instrument.id if instrument else None,
            instrument_name=instrument_name,
            quantity=quantity,
            price=price,
            gross_amount=abs(gross),
            fees=fees,
            net_amount=net,
            currency=account.currency,
            trade_date=trade_date,
            settlement_date=settlement_date,
            booked_at=datetime.combine(settlement_date, datetime.min.time()),
            description=f"{txn_type.value.replace('_', ' ').title()}" + (f" - {instrument_name}" if instrument_name else ""),
        )
        db.add(transaction)
    
    print(f"    Created {num_transactions} transactions")
    
    await db.commit()
    
    return client


async def reset_test_data(db: AsyncSession):
    """Delete existing test data."""
    print("\nResetting test data...")
    
    # Get test client users
    result = await db.execute(
        select(ClientUser).where(
            ClientUser.email.in_([c["email"] for c in TEST_CLIENTS])
        )
    )
    test_users = result.scalars().all()
    
    for user in test_users:
        # Delete transactions
        await db.execute(
            delete(Transaction).where(
                Transaction.account_id.in_(
                    select(Account.id).where(Account.client_id == user.client_id)
                )
            )
        )
        
        # Delete holdings
        await db.execute(
            delete(Holding).where(
                Holding.account_id.in_(
                    select(Account.id).where(Account.client_id == user.client_id)
                )
            )
        )
        
        # Delete accounts
        await db.execute(
            delete(Account).where(Account.client_id == user.client_id)
        )
        
        # Delete bank connections
        await db.execute(
            delete(BankConnection).where(BankConnection.client_id == user.client_id)
        )
        
        # Delete client user
        await db.execute(
            delete(ClientUser).where(ClientUser.id == user.id)
        )
        
        # Delete client
        await db.execute(
            delete(Client).where(Client.id == user.client_id)
        )
        
        print(f"  Deleted test data for: {user.email}")
    
    await db.commit()
    print("Reset complete.")


async def main(reset: bool = False):
    """Main seed function."""
    print("=" * 60)
    print("Client Portfolio Seed Script")
    print("=" * 60)
    
    async with async_session_factory() as db:
        if reset:
            await reset_test_data(db)
        
        # Get or create tenant
        tenant = await get_or_create_tenant(db)
        
        # Seed instruments
        print("\nSeeding instruments...")
        instruments = await seed_instruments(db)
        print(f"  {len(instruments)} instruments ready")
        
        # Seed clients with portfolios
        print("\nSeeding clients with portfolios...")
        for client_data in TEST_CLIENTS:
            await seed_client_with_portfolio(db, tenant, client_data, instruments)
    
    print("\n" + "=" * 60)
    print("Seed complete!")
    print("=" * 60)
    print("\nTest credentials:")
    for client in TEST_CLIENTS:
        print(f"  Email: {client['email']}")
        print(f"  Password: {client['password']}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed client portfolio test data")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset existing test data before seeding",
    )
    args = parser.parse_args()
    
    asyncio.run(main(reset=args.reset))

