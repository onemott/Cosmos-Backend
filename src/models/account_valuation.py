"""Account valuation history model for performance calculation."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4
from decimal import Decimal
from datetime import date

from sqlalchemy import String, ForeignKey, Numeric, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUID

if TYPE_CHECKING:
    from src.models.account import Account


class AccountValuation(Base, TimestampMixin):
    """Historical account valuation snapshots for performance calculation.
    
    This model stores periodic (daily/weekly/monthly) snapshots of account
    values to enable accurate performance calculations without requiring
    real-time historical data from external systems.
    """

    __tablename__ = "account_valuations"
    __table_args__ = (
        UniqueConstraint('account_id', 'valuation_date', name='uq_account_valuation_date'),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("accounts.id"), nullable=False, index=True
    )
    
    # Valuation date (the date this snapshot represents)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # Account values at this point in time
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), nullable=False
    )
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), default=Decimal("0")
    )
    invested_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4), default=Decimal("0")
    )
    
    # Currency of the valuation
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    
    # Number of holdings at this point
    holdings_count: Mapped[int] = mapped_column(default=0)
    
    # External reference (for reconciliation)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="valuations")
