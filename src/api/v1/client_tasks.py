"""Client-facing task API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_client
from src.db.session import get_db
from src.models.task import (
    Task,
    TaskType,
    TaskStatus,
    TaskPriority,
    WorkflowState,
    ApprovalAction,
    TaskMessage,
    TaskMessageAuthorType,
)
from src.models.client import Client
from src.models.client_user import ClientUser
from src.models.user import User
from src.schemas.client_task import (
    ClientTaskSummary,
    ClientTaskDetail,
    ClientTaskList,
    TaskApprovalRequest,
    TaskActionResponse,
    TaskMessageCreate,
    TaskMessageResponse,
    TaskMessageList,
    ProductRequestCreate,
    ProductRequestResponse,
    LightweightInterestCreate,
    LightweightInterestResponse,
)
from src.workers.notification_tasks import send_push_notification, send_email_notification

router = APIRouter(prefix="/client/tasks", tags=["Client Tasks"])


def task_requires_action(task: Task) -> bool:
    """Check if a task requires client action."""
    return (
        task.workflow_state == WorkflowState.PENDING_CLIENT
        and task.status == TaskStatus.PENDING
    )


async def get_client_and_assignee(
    db: AsyncSession,
    client_id: str,
    tenant_id: str,
) -> tuple[Client, Optional[User]]:
    result = await db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.tenant_id == tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    
    assigned_user = None
    if client.assigned_to_user_id:
        user_result = await db.execute(
            select(User).where(User.id == client.assigned_to_user_id)
        )
        assigned_user = user_result.scalar_one_or_none()
    
    return client, assigned_user


def notify_assigned_advisor(
    assigned_user: Optional[User],
    title: str,
    body: str,
    data: dict,
) -> None:
    if not assigned_user:
        return
    send_push_notification.delay(
        user_id=str(assigned_user.id),
        title=title,
        body=body,
        data=data,
    )
    if assigned_user.email:
        send_email_notification.delay(
            email=assigned_user.email,
            subject=title,
            template="client_interest",
            context={**data, "title": title, "body": body},
        )


async def create_task_message(
    db: AsyncSession,
    task: Task,
    author_type: TaskMessageAuthorType,
    body: str,
    author_user_id: Optional[str] = None,
    author_client_user_id: Optional[str] = None,
    reply_to_id: Optional[str] = None,
) -> TaskMessage:
    max_version_result = await db.execute(
        select(func.max(TaskMessage.version)).where(TaskMessage.task_id == task.id)
    )
    version = (max_version_result.scalar() or 0) + 1
    message = TaskMessage(
        tenant_id=task.tenant_id,
        task_id=task.id,
        client_id=task.client_id,
        author_type=author_type,
        author_user_id=author_user_id,
        author_client_user_id=author_client_user_id,
        body=body,
        reply_to_id=reply_to_id,
        version=version,
    )
    db.add(message)
    await db.flush()
    return message


async def build_task_message_responses(
    db: AsyncSession,
    messages: list[TaskMessage],
) -> list[TaskMessageResponse]:
    user_ids = {m.author_user_id for m in messages if m.author_user_id}
    client_user_ids = {m.author_client_user_id for m in messages if m.author_client_user_id}

    users_map = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(list(user_ids))))
        users_map = {str(u.id): u for u in users_result.scalars().all()}

    client_users_map = {}
    if client_user_ids:
        client_users_result = await db.execute(
            select(ClientUser).where(ClientUser.id.in_(list(client_user_ids)))
        )
        client_users_map = {str(c.id): c for c in client_users_result.scalars().all()}

    responses = []
    for message in messages:
        author_name = None
        if message.author_type == TaskMessageAuthorType.EAM and message.author_user_id:
            user = users_map.get(str(message.author_user_id))
            if user:
                author_name = user.display_name or user.email
        elif message.author_type == TaskMessageAuthorType.CLIENT and message.author_client_user_id:
            client_user = client_users_map.get(str(message.author_client_user_id))
            if client_user:
                author_name = client_user.display_name
        elif message.author_type == TaskMessageAuthorType.SYSTEM:
            author_name = "系统"

        responses.append(
            TaskMessageResponse(
                id=message.id,
                task_id=message.task_id,
                client_id=message.client_id,
                author_type=message.author_type.value,
                author_user_id=message.author_user_id,
                author_client_user_id=message.author_client_user_id,
                author_name=author_name,
                body=message.body,
                reply_to_id=message.reply_to_id,
                version=message.version,
                created_at=message.created_at,
            )
        )
    return responses


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
    count_query = select(func.count()).select_from(Task).where(
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
    pending_count_query = select(func.count()).select_from(Task).where(
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


@router.get(
    "/{task_id}/messages",
    response_model=TaskMessageList,
    summary="List task messages",
    description="Get communication messages for a task.",
)
async def list_task_messages(
    task_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> TaskMessageList:
    client_id = current_client["client_id"]
    task_result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.client_id == client_id,
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    message_query = select(TaskMessage).where(TaskMessage.task_id == task_id)
    count_result = await db.execute(
        select(func.count()).select_from(message_query.subquery())
    )
    total = count_result.scalar() or 0

    message_query = message_query.order_by(
        TaskMessage.version.asc(),
        TaskMessage.created_at.asc(),
    ).offset(skip).limit(limit)
    messages_result = await db.execute(message_query)
    messages = messages_result.scalars().all()

    return TaskMessageList(
        items=await build_task_message_responses(db, messages),
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/{task_id}/messages",
    response_model=TaskMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create task message",
    description="Post a message for a task.",
)
async def create_task_message_endpoint(
    task_id: str,
    payload: TaskMessageCreate,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> TaskMessageResponse:
    client_id = current_client["client_id"]
    client_user_id = current_client["client_user_id"]
    task_result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.client_id == client_id,
        )
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if payload.reply_to_id:
        reply_check = await db.execute(
            select(TaskMessage).where(
                TaskMessage.id == payload.reply_to_id,
                TaskMessage.task_id == task_id,
            )
        )
        if not reply_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reply target not found in this task",
            )

    message = await create_task_message(
        db=db,
        task=task,
        author_type=TaskMessageAuthorType.CLIENT,
        body=payload.body,
        author_client_user_id=client_user_id,
        reply_to_id=payload.reply_to_id,
    )
    await db.commit()

    responses = await build_task_message_responses(db, [message])
    return responses[0]


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

    if request.comment:
        await create_task_message(
            db=db,
            task=task,
            author_type=TaskMessageAuthorType.CLIENT,
            body=request.comment,
            author_client_user_id=client_user_id,
        )

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

    if request.comment:
        await create_task_message(
            db=db,
            task=task,
            author_type=TaskMessageAuthorType.CLIENT,
            body=request.comment,
            author_client_user_id=client_user_id,
        )

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
    
    client, assigned_user = await get_client_and_assignee(db, client_id, tenant_id)
    
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
        assigned_to_id=client.assigned_to_user_id,
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
    
    notify_assigned_advisor(
        assigned_user=assigned_user,
        title="New product request",
        body=f"{client.display_name} submitted a product request.",
        data={
            "task_id": str(task.id),
            "client_id": client_id,
            "client_name": client.display_name,
            "task_type": task.task_type.value,
            "product_count": len(request.products),
        },
    )
    
    return ProductRequestResponse(
        task_id=task.id,
        message="Your product interest has been submitted to your advisor for review.",
        products_count=len(request.products),
    )


@router.post(
    "/lightweight-interest",
    response_model=LightweightInterestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit lightweight product interest",
    description="Submit a lightweight interest request from a product detail page.",
)
async def create_lightweight_interest(
    request: LightweightInterestCreate,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> LightweightInterestResponse:
    client_id = current_client["client_id"]
    tenant_id = current_client["tenant_id"]
    
    client, assigned_user = await get_client_and_assignee(db, client_id, tenant_id)
    
    title = f"Lightweight Interest: {request.product_name}"
    description = (
        f"Client expressed interest in {request.product_name} ({request.interest_type}). "
        "Please follow up with the client."
    )
    
    task = Task(
        tenant_id=tenant_id,
        client_id=client_id,
        title=title,
        description=description,
        task_type=TaskType.LIGHTWEIGHT_INTEREST,
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        workflow_state=WorkflowState.PENDING_EAM,
        assigned_to_id=client.assigned_to_user_id,
        proposal_data={
            "product_id": request.product_id,
            "product_name": request.product_name,
            "module_code": request.module_code,
            "interest_type": request.interest_type,
            "client_notes": request.client_notes,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    notify_assigned_advisor(
        assigned_user=assigned_user,
        title="New product interest",
        body=f"{client.display_name} requested {request.interest_type} for {request.product_name}.",
        data={
            "task_id": str(task.id),
            "client_id": client_id,
            "client_name": client.display_name,
            "task_type": task.task_type.value,
            "product_id": request.product_id,
            "product_name": request.product_name,
            "interest_type": request.interest_type,
        },
    )
    
    return LightweightInterestResponse(
        task_id=task.id,
        message="Your interest has been sent to your advisor.",
    )
