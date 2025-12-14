"""Schemas for client-facing task APIs."""

from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class ClientTaskSummary(BaseModel):
    """Task summary for list view."""
    
    id: str = Field(..., description="Task UUID")
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    task_type: str = Field(..., description="Type (proposal_approval, kyc_review, etc.)")
    status: str = Field(..., description="Status (pending, in_progress, completed, etc.)")
    priority: str = Field(..., description="Priority (low, medium, high, urgent)")
    workflow_state: Optional[str] = Field(None, description="Workflow state for approval tasks")
    due_date: Optional[datetime] = Field(None, description="Due date")
    created_at: datetime = Field(..., description="Creation timestamp")
    requires_action: bool = Field(..., description="True if client action is needed")
    is_archived: bool = Field(False, description="Whether the task is archived")

    class Config:
        from_attributes = True


class ClientTaskDetail(BaseModel):
    """Detailed task view with proposal data."""
    
    id: str
    title: str
    description: Optional[str]
    task_type: str
    status: str
    priority: str
    workflow_state: Optional[str]
    due_date: Optional[datetime]
    approval_required_by: Optional[datetime] = Field(None, description="Deadline for approval")
    proposal_data: Optional[dict] = Field(None, description="Proposal details (trades, impact, etc.)")
    approval_action: Optional[str] = Field(None, description="Client's action if taken")
    approval_comment: Optional[str] = Field(None, description="Client's comment if provided")
    approval_acted_at: Optional[datetime] = Field(None, description="When action was taken")
    created_at: datetime
    requires_action: bool
    is_archived: bool = False

    class Config:
        from_attributes = True


class ClientTaskList(BaseModel):
    """List of client tasks."""
    
    tasks: List[ClientTaskSummary]
    total_count: int
    pending_count: int = Field(..., description="Number of tasks requiring action")


class TaskApprovalRequest(BaseModel):
    """Request schema for approving/declining a task."""
    
    comment: Optional[str] = Field(
        None, 
        max_length=2000,
        description="Optional comment explaining the decision"
    )


class TaskActionResponse(BaseModel):
    """Response after task action."""
    
    task_id: str
    action: str = Field(..., description="Action taken (approved/declined)")
    message: str
    workflow_state: str


# ============================================================================
# Product Request (Allocation Lab submission)
# ============================================================================

class ProductRequestItem(BaseModel):
    """A product selected by the client."""
    
    product_id: str = Field(..., description="Product ID")
    product_name: str = Field(..., description="Product name")
    module_code: str = Field(..., description="Module code the product belongs to")
    min_investment: float = Field(..., description="Minimum investment amount")
    currency: str = Field(default="USD", description="Currency")


class ProductRequestCreate(BaseModel):
    """Request schema for creating a product interest request from Allocation Lab."""
    
    products: List[ProductRequestItem] = Field(
        ..., 
        min_length=1,
        description="List of selected products"
    )
    client_notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional notes from client about their interest"
    )


class ProductRequestResponse(BaseModel):
    """Response after creating a product request."""
    
    task_id: str = Field(..., description="Created task ID")
    message: str = Field(..., description="Success message")
    products_count: int = Field(..., description="Number of products requested")

