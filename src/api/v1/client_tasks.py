"""Client-facing task API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_client
from src.db.session import get_db
from src.models.task import Task, TaskType, TaskStatus, TaskPriority, WorkflowState, ApprovalAction
from src.schemas.client_task import (
    ClientTaskSummary,
    ClientTaskDetail,
    ClientTaskList,
    TaskApprovalRequest,
    TaskActionResponse,
    ProductRequestCreate,
    ProductRequestResponse,
)

router = APIRouter(prefix="/client/tasks", tags=["Client Tasks"])


def task_requires_action(task: Task) -> bool:
    """Check if a task requires client action."""
    return (
        task.workflow_state == WorkflowState.PENDING_CLIENT
        and task.status == TaskStatus.PENDING
    )


@router.get(
    "",
    response_model=ClientTaskList,
    summary="List client tasks",
    description="Get all tasks assigned to the authenticated client.",
)
async def list_tasks(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    pending_only: bool = Query(False, description="Only show tasks requiring action"),
    is_archived: bool = Query(False, description="Filter by archived status"),
    skip: int = Query(0, ge=0, description="Number of tasks to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max number of tasks to return"),
) -> ClientTaskList:
    """List all tasks for the authenticated client."""
    client_id = current_client["client_id"]
    
    # Build query
    query = select(Task).where(
        Task.client_id == client_id,
        Task.is_archived == is_archived,
    )
    
    # Apply filters
    if status_filter:
        try:
            status_enum = TaskStatus(status_filter)
            query = query.where(Task.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )
    
    if task_type:
        try:
            type_enum = TaskType(task_type)
            query = query.where(Task.task_type == type_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid task type: {task_type}",
            )
    
    if pending_only:
        query = query.where(
            Task.workflow_state == WorkflowState.PENDING_CLIENT,
            Task.status == TaskStatus.PENDING,
        )
    
    # Order by priority and due date
    query = query.order_by(
        Task.priority.desc(),
        Task.due_date.asc().nullslast(),
        Task.created_at.desc(),
    )
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Get total count for pagination
    count_query = select(func.count(Task.id)).where(
        Task.client_id == client_id,
        Task.is_archived == is_archived,
    )
    
    # Apply filters to count query
    if status_filter:
        try:
            status_enum = TaskStatus(status_filter)
            count_query = count_query.where(Task.status == status_enum)
        except ValueError:
            pass # Should have been caught above
            
    if task_type:
        try:
            type_enum = TaskType(task_type)
            count_query = count_query.where(Task.task_type == type_enum)
        except ValueError:
            pass # Should have been caught above
            
    if pending_only:
        count_query = count_query.where(
            Task.workflow_state == WorkflowState.PENDING_CLIENT,
            Task.status == TaskStatus.PENDING,
        )

    total_count_result = await db.execute(count_query)
    total_count = total_count_result.scalar() or 0

    # Count pending tasks (from non-archived only)
    # We need a separate query for total pending count because pagination filters the results
    pending_count_query = select(func.count(Task.id)).where(
        Task.client_id == client_id,
        Task.workflow_state == WorkflowState.PENDING_CLIENT,
        Task.status == TaskStatus.PENDING,
        Task.is_archived == False,
    )
    pending_count_result = await db.execute(pending_count_query)
    pending_count = pending_count_result.scalar() or 0
    
    return ClientTaskList(
        tasks=[
            ClientTaskSummary(
                id=task.id,
                title=task.title,
                description=task.description,
                task_type=task.task_type.value,
                status=task.status.value,
                priority=task.priority.value,
                workflow_state=task.workflow_state.value if task.workflow_state else None,
                due_date=task.due_date,
                created_at=task.created_at,
                requires_action=task_requires_action(task),
                is_archived=task.is_archived,
            )
            for task in tasks
        ],
        total_count=total_count,
        pending_count=pending_count,
    )


@router.get(
    "/{task_id}",
    response_model=ClientTaskDetail,
    summary="Get task detail",
    description="Get detailed information about a specific task.",
)
async def get_task_detail(
    task_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> ClientTaskDetail:
    """Get detailed task information."""
    client_id = current_client["client_id"]
    
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.client_id == client_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    return ClientTaskDetail(
        id=task.id,
        title=task.title,
        description=task.description,
        task_type=task.task_type.value,
        status=task.status.value,
        priority=task.priority.value,
        workflow_state=task.workflow_state.value if task.workflow_state else None,
        due_date=task.due_date,
        approval_required_by=task.approval_required_by,
        proposal_data=task.proposal_data,
        approval_action=task.approval_action.value if task.approval_action else None,
        approval_comment=task.approval_comment,
        approval_acted_at=task.approval_acted_at,
        created_at=task.created_at,
        requires_action=task_requires_action(task),
    )


@router.post(
    "/{task_id}/approve",
    response_model=TaskActionResponse,
    summary="Approve task",
    description="Approve a pending task (e.g., investment proposal).",
)
async def approve_task(
    task_id: str,
    request: TaskApprovalRequest,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> TaskActionResponse:
    """Approve a task."""
    client_id = current_client["client_id"]
    client_user_id = current_client["client_user_id"]
    
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.client_id == client_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Verify task can be approved
    if not task_requires_action(task):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This task cannot be approved (already processed or not pending)",
        )
    
    # Update task
    task.workflow_state = WorkflowState.APPROVED
    task.approval_action = ApprovalAction.APPROVED
    task.approval_comment = request.comment
    task.approval_acted_at = datetime.now(timezone.utc)
    task.approved_by_client_user_id = client_user_id
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return TaskActionResponse(
        task_id=task.id,
        action="approved",
        message="Task has been approved successfully",
        workflow_state=WorkflowState.APPROVED.value,
    )


@router.post(
    "/{task_id}/decline",
    response_model=TaskActionResponse,
    summary="Decline task",
    description="Decline a pending task (e.g., investment proposal).",
)
async def decline_task(
    task_id: str,
    request: TaskApprovalRequest,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> TaskActionResponse:
    """Decline a task."""
    # Require comment when declining (helps advisors improve proposals)
    if not request.comment or not request.comment.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A comment explaining the reason for declining is required",
        )
    
    client_id = current_client["client_id"]
    client_user_id = current_client["client_user_id"]
    
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.client_id == client_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Verify task can be declined
    if not task_requires_action(task):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This task cannot be declined (already processed or not pending)",
        )
    
    # Update task
    task.workflow_state = WorkflowState.DECLINED
    task.approval_action = ApprovalAction.DECLINED
    task.approval_comment = request.comment
    task.approval_acted_at = datetime.now(timezone.utc)
    task.approved_by_client_user_id = client_user_id
    # Don't mark as completed - staff may want to revise and resubmit
    task.status = TaskStatus.ON_HOLD
    
    await db.commit()
    
    return TaskActionResponse(
        task_id=task.id,
        action="declined",
        message="Task has been declined",
        workflow_state=WorkflowState.DECLINED.value,
    )


@router.post(
    "/{task_id}/archive",
    response_model=TaskActionResponse,
    summary="Archive task",
    description="Archive a completed or cancelled task.",
)
async def archive_task(
    task_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> TaskActionResponse:
    """Archive a task."""
    client_id = current_client["client_id"]
    
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.client_id == client_id,
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Verify task can be archived (must be completed or cancelled)
    if task.status not in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
        # Allow archiving if it's been approved/declined even if status isn't technically COMPLETED yet
        if task.workflow_state not in [WorkflowState.APPROVED, WorkflowState.DECLINED]:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only completed or cancelled tasks can be archived",
            )
    
    task.is_archived = True
    
    await db.commit()
    
    return TaskActionResponse(
        task_id=task.id,
        action="archived",
        message="Task has been archived",
        workflow_state=task.workflow_state.value if task.workflow_state else "unknown",
    )


@router.post(
    "/product-request",
    response_model=ProductRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit product interest request",
    description="Submit a request for investment products from the Allocation Lab.",
)
async def create_product_request(
    request: ProductRequestCreate,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> ProductRequestResponse:
    """
    Create a product interest request from the Allocation Lab.
    
    This creates a task that will be reviewed by the EAM.
    The EAM can then create a formal proposal for the client to approve.
    """
    client_id = current_client["client_id"]
    tenant_id = current_client["tenant_id"]
    
    # Build product list for description
    product_names = [p.product_name for p in request.products]
    product_list = ", ".join(product_names[:3])
    if len(product_names) > 3:
        product_list += f" and {len(product_names) - 3} more"
    
    # Calculate total minimum investment and total requested amount
    total_min = sum(p.min_investment for p in request.products)
    total_requested = sum(p.requested_amount for p in request.products)
    
    # Build orders array for structured display
    orders = [{
        "product_id": p.product_id,
        "product_name": p.product_name,
        "module_code": p.module_code,
        "min_investment": p.min_investment,
        "requested_amount": p.requested_amount,
        "currency": p.currency,
    } for p in request.products]
    
    # Create task
    task = Task(
        tenant_id=tenant_id,
        client_id=client_id,
        title=f"Product Interest: {product_list}",
        description=f"Client has expressed interest in {len(request.products)} investment product(s). "
                    f"Total requested investment: ${total_requested:,.2f} (minimum: ${total_min:,.2f}). "
                    f"Please review and prepare a proposal if appropriate.",
        task_type=TaskType.PRODUCT_REQUEST,
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        workflow_state=WorkflowState.PENDING_EAM,
        proposal_data={
            "orders": orders,
            "products": [p.model_dump() for p in request.products],  # Keep for backward compatibility
            "client_notes": request.client_notes,
            "total_min_investment": total_min,
            "total_requested_amount": total_requested,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    return ProductRequestResponse(
        task_id=task.id,
        message="Your product interest has been submitted to your advisor for review.",
        products_count=len(request.products),
    )

