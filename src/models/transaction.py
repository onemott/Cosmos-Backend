"""Transaction model."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4
from decimal import Decimal
from datetime import date, datetime

from sqlalchemy import String, ForeignKey, Numeric, Enum as SQLEnum, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from src.db.base import Base, TimestampMixin, UUID

if TYPE_CHECKING:
    from src.models.account import Account


class TransactionType(str, enum.Enum):
    """Transaction type enumeration."""

    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    CORPORATE_ACTION = "corporate_action"
    OTHER = "other"


class TransactionStatus(str, enum.Enum):
    """Transaction status enumeration."""

    PENDING = "pending"
    SETTLED = "settled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Transaction(Base, TimestampMixin):
    """Transaction / trade model."""

    __tablename__ = "transactions"

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

    # Transaction details
    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType), nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(TransactionStatus), default=TransactionStatus.PENDING
    )

    # Instrument (optional, not all transactions have instruments)
    instrument_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("instruments.id"), nullable=True
    )
    instrument_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Amounts
    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=6), nullable=True
    )
    price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=6), nullable=True
    )
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), nullable=False
    )
    fees: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), default=Decimal("0")
    )
    net_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Dates
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    booked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Description and reference
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="transactions")

