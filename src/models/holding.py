"""Holding and Instrument models."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import String, ForeignKey, Numeric, Enum as SQLEnum, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from datetime import date

from src.db.base import Base, TimestampMixin, UUID

if TYPE_CHECKING:
    from src.models.account import Account


class AssetClass(str, enum.Enum):
    """Asset class enumeration."""

    EQUITY = "equity"
    FIXED_INCOME = "fixed_income"
    CASH = "cash"
    ALTERNATIVES = "alternatives"
    REAL_ESTATE = "real_estate"
    COMMODITIES = "commodities"
    CRYPTO = "crypto"
    OTHER = "other"


class InstrumentType(str, enum.Enum):
    """Instrument type enumeration."""

    STOCK = "stock"
    BOND = "bond"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    STRUCTURED_PRODUCT = "structured_product"
    OPTION = "option"
    FUTURE = "future"
    FOREX = "forex"
    CASH = "cash"
    OTHER = "other"


class Instrument(Base, TimestampMixin):
    """Financial instrument / security model."""

    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Identifiers
    isin: Mapped[Optional[str]] = mapped_column(String(12), unique=True, nullable=True)
    cusip: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    sedol: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    ticker: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        SQLEnum(InstrumentType), default=InstrumentType.OTHER
    )
    asset_class: Mapped[AssetClass] = mapped_column(
        SQLEnum(AssetClass), default=AssetClass.OTHER
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Pricing
    last_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=6), nullable=True
    )
    price_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Relationships
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding", back_populates="instrument"
    )


class Holding(Base, TimestampMixin):
    """Portfolio holding / position model."""

    __tablename__ = "holdings"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id"), nullable=False
    )
    instrument_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("instruments.id"), nullable=False
    )

    # Position details
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=6), nullable=False
    )
    cost_basis: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=4), nullable=True
    )
    market_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Performance
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=4), nullable=True
    )
    unrealized_pnl_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )

    # Valuation date
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    # External reference
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="holdings")
    instrument: Mapped["Instrument"] = relationship(
        "Instrument", back_populates="holdings"
    )

