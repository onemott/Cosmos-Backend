"""Task and workflow models."""

from typing import TYPE_CHECKING, Optional
from uuid import uuid4
from datetime import datetime

from sqlalchemy import String, ForeignKey, Enum as SQLEnum, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from src.db.base import Base, TimestampMixin, UUID

if TYPE_CHECKING:
    from src.models.client import Client


class TaskType(str, enum.Enum):
    """Task type enumeration."""

    ONBOARDING = "onboarding"
    KYC_REVIEW = "kyc_review"
    DOCUMENT_REVIEW = "document_review"
    PROPOSAL_APPROVAL = "proposal_approval"
    PRODUCT_REQUEST = "product_request"  # Client-initiated investment product request
    COMPLIANCE_CHECK = "compliance_check"
    RISK_REVIEW = "risk_review"
    ACCOUNT_OPENING = "account_opening"
    GENERAL = "general"


class TaskStatus(str, enum.Enum):
    """Task status enumeration."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class WorkflowState(str, enum.Enum):
    """Workflow state for client approval tasks."""

    DRAFT = "draft"  # Task created, not yet sent to client
    PENDING_EAM = "pending_eam"  # Client-initiated, awaiting EAM review
    PENDING_CLIENT = "pending_client"  # Awaiting client action
    APPROVED = "approved"  # Client approved
    DECLINED = "declined"  # Client declined
    EXPIRED = "expired"  # Deadline passed without action


class ApprovalAction(str, enum.Enum):
    """Client approval action."""

    APPROVED = "approved"
    DECLINED = "declined"


class TaskPriority(str, enum.Enum):
    """Task priority enumeration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base, TimestampMixin):
    """Task / workflow item model."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )
    client_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("clients.id"), nullable=True
    )

    # Task details
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    task_type: Mapped[TaskType] = mapped_column(
        SQLEnum(TaskType), default=TaskType.GENERAL
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus), default=TaskStatus.PENDING
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(TaskPriority), default=TaskPriority.MEDIUM
    )

    # Assignment
    assigned_to_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )
    created_by_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True
    )

    # Dates
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Additional data
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # Workflow fields for client approval
    workflow_state: Mapped[Optional[WorkflowState]] = mapped_column(
        SQLEnum(WorkflowState), nullable=True
    )
    approval_required_by: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_client_user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("client_users.id"), nullable=True
    )
    approval_action: Mapped[Optional[ApprovalAction]] = mapped_column(
        SQLEnum(ApprovalAction), nullable=True
    )
    approval_comment: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    approval_acted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proposal_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="tasks")

