"""Schemas for admin task management."""

from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field
from enum import Enum


class TaskTypeEnum(str, Enum):
    ONBOARDING = "onboarding"
    KYC_REVIEW = "kyc_review"
    DOCUMENT_REVIEW = "document_review"
    PROPOSAL_APPROVAL = "proposal_approval"
    PRODUCT_REQUEST = "product_request"
    LIGHTWEIGHT_INTEREST = "lightweight_interest"
    COMPLIANCE_CHECK = "compliance_check"
    RISK_REVIEW = "risk_review"
    ACCOUNT_OPENING = "account_opening"
    GENERAL = "general"


class TaskStatusEnum(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class WorkflowStateEnum(str, Enum):
    DRAFT = "draft"
    PENDING_EAM = "pending_eam"
    PENDING_CLIENT = "pending_client"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"


class TaskPriorityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskMessageAuthorTypeEnum(str, Enum):
    EAM = "eam"
    CLIENT = "client"
    SYSTEM = "system"


# ============================================================================
# Request Schemas
# ============================================================================

class TaskCreate(BaseModel):
    """Schema for creating a new task (EAM-initiated)."""
    
    client_id: str = Field(..., description="Client UUID")
    title: str = Field(..., max_length=255, description="Task title")
    description: Optional[str] = Field(None, max_length=2000, description="Task description")
    task_type: TaskTypeEnum = Field(default=TaskTypeEnum.GENERAL, description="Task type")
    priority: TaskPriorityEnum = Field(default=TaskPriorityEnum.MEDIUM, description="Priority level")
    assigned_to_id: Optional[str] = Field(None, description="Assigned user UUID")
    due_date: Optional[datetime] = Field(None, description="Due date")
    workflow_state: Optional[WorkflowStateEnum] = Field(None, description="Workflow state")
    approval_required_by: Optional[datetime] = Field(None, description="Approval deadline")
    proposal_data: Optional[dict] = Field(None, description="Proposal details (for approval tasks)")


class TaskUpdate(BaseModel):
    """Schema for updating a task."""
    
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[TaskStatusEnum] = None
    priority: Optional[TaskPriorityEnum] = None
    assigned_to_id: Optional[str] = None
    due_date: Optional[datetime] = None
    workflow_state: Optional[WorkflowStateEnum] = None
    approval_required_by: Optional[datetime] = None
    proposal_data: Optional[dict] = None


class TaskRespondRequest(BaseModel):
    """Schema for EAM responding to a task (e.g., after client action)."""
    
    action: str = Field(..., description="Action: 'acknowledge', 'send_to_client', 'revise', 'complete'")
    comment: Optional[str] = Field(None, max_length=2000, description="Response comment")
    proposal_data: Optional[dict] = Field(None, description="Updated proposal data (for revision)")


class TaskMessageCreate(BaseModel):
    body: str = Field(..., max_length=2000, description="Message content")
    reply_to_id: Optional[str] = Field(None, description="Reply to message ID")


# ============================================================================
# Response Schemas
# ============================================================================

class ClientSummary(BaseModel):
    """Minimal client info for task responses."""
    
    id: str
    display_name: str
    email: Optional[str] = None
    client_type: str

    class Config:
        from_attributes = True


class UserSummary(BaseModel):
    """Minimal user info for task responses."""
    
    id: str
    email: str
    display_name: Optional[str] = None

    class Config:
        from_attributes = True


class TaskResponse(BaseModel):
    """Full task response schema."""
    
    id: str
    tenant_id: str
    client_id: Optional[str] = None
    client: Optional[ClientSummary] = None
    
    title: str
    description: Optional[str] = None
    task_type: str
    status: str
    priority: str
    
    assigned_to_id: Optional[str] = None
    assigned_to: Optional[UserSummary] = None
    created_by_id: Optional[str] = None
    created_by: Optional[UserSummary] = None
    
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    escalation_level: int = 0
    escalated_at: Optional[datetime] = None
    escalated_to_id: Optional[str] = None
    
    workflow_state: Optional[str] = None
    approval_required_by: Optional[datetime] = None
    approval_action: Optional[str] = None
    approval_comment: Optional[str] = None
    approval_acted_at: Optional[datetime] = None
    proposal_data: Optional[dict] = None
    
    requires_eam_action: bool = Field(..., description="True if EAM needs to act on this task")
    
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskSummary(BaseModel):
    """Summarized task for list views."""
    
    id: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    
    title: str
    task_type: str
    status: str
    priority: str
    workflow_state: Optional[str] = None
    
    assigned_to_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    
    due_date: Optional[datetime] = None
    requires_eam_action: bool
    
    created_at: datetime

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Paginated task list response."""
    
    tasks: List[TaskSummary]
    total_count: int
    pending_eam_count: int = Field(..., description="Number of tasks requiring EAM action")
    skip: int
    limit: int


class TaskActionResponse(BaseModel):
    """Response after task action."""
    
    task_id: str
    action: str
    message: str
    new_status: Optional[str] = None
    new_workflow_state: Optional[str] = None


class TaskMessageResponse(BaseModel):
    id: str
    task_id: str
    tenant_id: str
    client_id: Optional[str] = None
    author_type: TaskMessageAuthorTypeEnum
    author_user_id: Optional[str] = None
    author_client_user_id: Optional[str] = None
    author_name: Optional[str] = None
    body: str
    reply_to_id: Optional[str] = None
    version: int
    created_at: datetime

    class Config:
        from_attributes = True


class TaskMessageListResponse(BaseModel):
    items: List[TaskMessageResponse]
    total: int
    skip: int
    limit: int

