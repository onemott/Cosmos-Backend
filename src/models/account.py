"""Account and BankConnection models."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import String, ForeignKey, Numeric, Enum as SQLEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from src.db.base import Base, TimestampMixin, UUID

if TYPE_CHECKING:
    from src.models.client import Client
    from src.models.holding import Holding
    from src.models.transaction import Transaction
    from src.models.account_valuation import AccountValuation


class AccountType(str, enum.Enum):
    """Account type enumeration."""

    INVESTMENT = "investment"
    CUSTODY = "custody"
    CASH = "cash"
    MARGIN = "margin"


class ConnectionStatus(str, enum.Enum):
    """Bank connection status."""

    ACTIVE = "active"
    PENDING = "pending"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class BankConnection(Base, TimestampMixin):
    """Bank/custodian connection model."""

    __tablename__ = "bank_connections"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("clients.id"), nullable=False
    )

    # Bank information
    bank_code: Mapped[str] = mapped_column(String(50), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ConnectionStatus] = mapped_column(
        SQLEnum(ConnectionStatus), default=ConnectionStatus.PENDING
    )

    # Connection details (encrypted reference, not actual credentials)
    credentials_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_sync_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="bank_connections")
    accounts: Mapped[list["Account"]] = relationship(
        "Account", back_populates="bank_connection"
    )


class Account(Base, TimestampMixin):
    """Investment account model."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("clients.id"), nullable=False
    )
    bank_connection_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bank_connections.id"), nullable=True
    )

    # Account details
    account_number: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        SQLEnum(AccountType), default=AccountType.INVESTMENT
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Valuations
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), default=Decimal("0")
    )
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), default=Decimal("0")
    )

    # External reference
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="accounts")
    bank_connection: Mapped[Optional["BankConnection"]] = relationship(
        "BankConnection", back_populates="accounts"
    )
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding", back_populates="account", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="account", cascade="all, delete-orphan"
    )
    valuations: Mapped[list["AccountValuation"]] = relationship(
        "AccountValuation", back_populates="account", cascade="all, delete-orphan"
    )

