"""Task and workflow endpoints for admin/EAM users."""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.session import get_db
from src.api.deps import get_current_user, get_current_tenant_admin
from src.models.task import Task, TaskType, TaskStatus, WorkflowState, TaskPriority
from src.models.client import Client
from src.models.user import User
from src.schemas.task import (
    TaskCreate,
    TaskUpdate,
    TaskRespondRequest,
    TaskResponse,
    TaskSummary,
    TaskListResponse,
    TaskActionResponse,
    ClientSummary,
    UserSummary,
)

router = APIRouter()


def task_requires_eam_action(task: Task) -> bool:
    """Check if a task requires EAM action."""
    # EAM needs to act when:
    # 1. Task is PENDING_EAM (client submitted something)
    # 2. Task is DECLINED by client (EAM may want to revise)
    # 3. Task is newly created and not yet assigned
    if task.workflow_state == WorkflowState.PENDING_EAM:
        return True
    if task.workflow_state == WorkflowState.DECLINED and task.status != TaskStatus.CANCELLED:
        return True
    if task.status == TaskStatus.PENDING and not task.assigned_to_id:
        return True
    return False


def build_task_summary(task: Task, client: Optional[Client] = None, assigned_user: Optional[User] = None) -> TaskSummary:
    """Build a TaskSummary from a Task model."""
    client_name = None
    if client:
        if client.client_type == "individual":
            client_name = f"{client.first_name} {client.last_name}"
        else:
            client_name = client.entity_name
    
    assigned_name = None
    if assigned_user:
        assigned_name = assigned_user.display_name or assigned_user.email
    
    return TaskSummary(
        id=task.id,
        client_id=task.client_id,
        client_name=client_name,
        title=task.title,
        task_type=task.task_type.value if task.task_type else "general",
        status=task.status.value if task.status else "pending",
        priority=task.priority.value if task.priority else "medium",
        workflow_state=task.workflow_state.value if task.workflow_state else None,
        assigned_to_id=task.assigned_to_id,
        assigned_to_name=assigned_name,
        due_date=task.due_date,
        requires_eam_action=task_requires_eam_action(task),
        created_at=task.created_at,
    )


def build_task_response(
    task: Task, 
    client: Optional[Client] = None, 
    assigned_user: Optional[User] = None,
    created_user: Optional[User] = None
) -> TaskResponse:
    """Build a full TaskResponse from a Task model."""
    client_summary = None
    if client:
        display_name = f"{client.first_name} {client.last_name}" if client.client_type == "individual" else client.entity_name
        client_summary = ClientSummary(
            id=client.id,
            display_name=display_name,
            email=client.email,
            client_type=client.client_type.value if hasattr(client.client_type, 'value') else str(client.client_type),
        )
    
    assigned_to_summary = None
    if assigned_user:
        assigned_to_summary = UserSummary(
            id=assigned_user.id,
            email=assigned_user.email,
            display_name=assigned_user.display_name,
        )
    
    created_by_summary = None
    if created_user:
        created_by_summary = UserSummary(
            id=created_user.id,
            email=created_user.email,
            display_name=created_user.display_name,
        )
    
    return TaskResponse(
        id=task.id,
        tenant_id=task.tenant_id,
        client_id=task.client_id,
        client=client_summary,
        title=task.title,
        description=task.description,
        task_type=task.task_type.value if task.task_type else "general",
        status=task.status.value if task.status else "pending",
        priority=task.priority.value if task.priority else "medium",
        assigned_to_id=task.assigned_to_id,
        assigned_to=assigned_to_summary,
        created_by_id=task.created_by_id,
        created_by=created_by_summary,
        due_date=task.due_date,
        completed_at=task.completed_at,
        workflow_state=task.workflow_state.value if task.workflow_state else None,
        approval_required_by=task.approval_required_by,
        approval_action=task.approval_action.value if task.approval_action else None,
        approval_comment=task.approval_comment,
        approval_acted_at=task.approval_acted_at,
        proposal_data=task.proposal_data,
        requires_eam_action=task_requires_eam_action(task),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    client_id: Optional[str] = Query(None, description="Filter by client"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    task_type: Optional[str] = Query(None, description="Filter by task type"),
    workflow_state: Optional[str] = Query(None, description="Filter by workflow state"),
    assigned_to_me: bool = Query(False, description="Only show tasks assigned to me"),
    pending_eam_only: bool = Query(False, description="Only show tasks requiring EAM action"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TaskListResponse:
    """List tasks with optional filters.
    
    Accessible by tenant users (sees their tenant's tasks) and platform users (sees all).
    """
    user_id = current_user.get("sub")
    tenant_id = current_user.get("tenant_id")
    
    # Build query
    query = select(Task)
    
    # Tenant scoping - tenant users only see their tenant's tasks
    if tenant_id:
        query = query.where(Task.tenant_id == tenant_id)
    
    # Apply filters
    if client_id:
        query = query.where(Task.client_id == client_id)
    
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
    
    if workflow_state:
        try:
            state_enum = WorkflowState(workflow_state)
            query = query.where(Task.workflow_state == state_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid workflow state: {workflow_state}",
            )
    
    if assigned_to_me:
        query = query.where(Task.assigned_to_id == user_id)
    
    if pending_eam_only:
        # Tasks requiring EAM action
        query = query.where(
            or_(
                Task.workflow_state == WorkflowState.PENDING_EAM,
                and_(
                    Task.workflow_state == WorkflowState.DECLINED,
                    Task.status != TaskStatus.CANCELLED,
                ),
                and_(
                    Task.status == TaskStatus.PENDING,
                    Task.assigned_to_id.is_(None),
                ),
            )
        )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0
    
    # Count pending EAM tasks
    pending_eam_query = select(func.count()).select_from(
        query.where(
            or_(
                Task.workflow_state == WorkflowState.PENDING_EAM,
                and_(
                    Task.workflow_state == WorkflowState.DECLINED,
                    Task.status != TaskStatus.CANCELLED,
                ),
            )
        ).subquery()
    )
    pending_eam_result = await db.execute(pending_eam_query)
    pending_eam_count = pending_eam_result.scalar() or 0
    
    # Order by priority (urgent first) and due date
    query = query.order_by(
        Task.priority.desc(),
        Task.due_date.asc().nullslast(),
        Task.created_at.desc(),
    )
    
    # Apply pagination
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Fetch clients and users for display names
    client_ids = [t.client_id for t in tasks if t.client_id]
    user_ids = [t.assigned_to_id for t in tasks if t.assigned_to_id]
    
    clients_map = {}
    if client_ids:
        clients_result = await db.execute(
            select(Client).where(Client.id.in_(client_ids))
        )
        clients_map = {c.id: c for c in clients_result.scalars().all()}
    
    users_map = {}
    if user_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        users_map = {u.id: u for u in users_result.scalars().all()}
    
    task_summaries = [
        build_task_summary(
            task,
            clients_map.get(task.client_id),
            users_map.get(task.assigned_to_id),
        )
        for task in tasks
    ]
    
    return TaskListResponse(
        tasks=task_summaries,
        total_count=total_count,
        pending_eam_count=pending_eam_count,
        skip=skip,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TaskResponse:
    """Get task by ID with full details."""
    tenant_id = current_user.get("tenant_id")
    
    query = select(Task).where(Task.id == task_id)
    
    # Tenant scoping
    if tenant_id:
        query = query.where(Task.tenant_id == tenant_id)
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Fetch related data
    client = None
    if task.client_id:
        client_result = await db.execute(
            select(Client).where(Client.id == task.client_id)
        )
        client = client_result.scalar_one_or_none()
    
    assigned_user = None
    if task.assigned_to_id:
        user_result = await db.execute(
            select(User).where(User.id == task.assigned_to_id)
        )
        assigned_user = user_result.scalar_one_or_none()
    
    created_user = None
    if task.created_by_id:
        user_result = await db.execute(
            select(User).where(User.id == task.created_by_id)
        )
        created_user = user_result.scalar_one_or_none()
    
    return build_task_response(task, client, assigned_user, created_user)


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> TaskResponse:
    """Create a new task (EAM-initiated).
    
    For example: Create a proposal for a client to approve.
    """
    user_id = current_user.get("sub")
    tenant_id = current_user.get("tenant_id")
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required to create tasks",
        )
    
    # Verify client exists and belongs to tenant
    client_result = await db.execute(
        select(Client).where(
            Client.id == task_in.client_id,
            Client.tenant_id == tenant_id,
        )
    )
    client = client_result.scalar_one_or_none()
    
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found in your organization",
        )
    
    # Create task
    task = Task(
        tenant_id=tenant_id,
        client_id=task_in.client_id,
        title=task_in.title,
        description=task_in.description,
        task_type=TaskType(task_in.task_type.value),
        priority=TaskPriority(task_in.priority.value),
        status=TaskStatus.PENDING,
        assigned_to_id=task_in.assigned_to_id or user_id,  # Default to creator
        created_by_id=user_id,
        due_date=task_in.due_date,
        workflow_state=WorkflowState(task_in.workflow_state.value) if task_in.workflow_state else WorkflowState.DRAFT,
        approval_required_by=task_in.approval_required_by,
        proposal_data=task_in.proposal_data,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    return build_task_response(task, client)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TaskResponse:
    """Update task status, assignment, or other fields."""
    tenant_id = current_user.get("tenant_id")
    
    query = select(Task).where(Task.id == task_id)
    if tenant_id:
        query = query.where(Task.tenant_id == tenant_id)
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Apply updates
    update_data = task_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if value is not None:
            if field == "status":
                setattr(task, field, TaskStatus(value.value if hasattr(value, 'value') else value))
            elif field == "priority":
                setattr(task, field, TaskPriority(value.value if hasattr(value, 'value') else value))
            elif field == "workflow_state":
                setattr(task, field, WorkflowState(value.value if hasattr(value, 'value') else value))
            else:
                setattr(task, field, value)
    
    # If status is completed, set completed_at
    if task_update.status and task_update.status.value == "completed":
        task.completed_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(task)
    
    # Fetch client for response
    client = None
    if task.client_id:
        client_result = await db.execute(
            select(Client).where(Client.id == task.client_id)
        )
        client = client_result.scalar_one_or_none()
    
    return build_task_response(task, client)


@router.post("/{task_id}/respond", response_model=TaskActionResponse)
async def respond_to_task(
    task_id: str,
    request: TaskRespondRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TaskActionResponse:
    """EAM responds to a task (after client action or for workflow management).
    
    Actions:
    - 'acknowledge': Mark as reviewed (for client-initiated requests)
    - 'send_to_client': Send proposal to client for approval
    - 'revise': Update and resend (after client decline)
    - 'complete': Mark task as completed
    - 'cancel': Cancel the task
    """
    tenant_id = current_user.get("tenant_id")
    
    query = select(Task).where(Task.id == task_id)
    if tenant_id:
        query = query.where(Task.tenant_id == tenant_id)
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    action = request.action.lower()
    message = ""
    new_status = None
    new_workflow_state = None
    
    if action == "acknowledge":
        # EAM acknowledges a client-initiated task
        task.status = TaskStatus.IN_PROGRESS
        new_status = "in_progress"
        message = "Task acknowledged and marked as in progress"
    
    elif action == "send_to_client":
        # Send proposal to client for approval
        if request.proposal_data:
            task.proposal_data = request.proposal_data
        
        # Store EAM's message in proposal_data
        if request.comment:
            if task.proposal_data is None:
                task.proposal_data = {}
            task.proposal_data = {
                **task.proposal_data,
                "eam_message": request.comment,
                "sent_to_client_at": datetime.now(timezone.utc).isoformat(),
            }
        
        task.workflow_state = WorkflowState.PENDING_CLIENT
        task.status = TaskStatus.PENDING
        new_workflow_state = "pending_client"
        new_status = "pending"
        message = "Proposal sent to client for approval"
    
    elif action == "revise":
        # Revise proposal after client decline
        if task.workflow_state != WorkflowState.DECLINED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only revise declined tasks",
            )
        if request.proposal_data:
            task.proposal_data = request.proposal_data
        task.workflow_state = WorkflowState.DRAFT
        task.status = TaskStatus.IN_PROGRESS
        task.approval_action = None
        task.approval_comment = None
        task.approval_acted_at = None
        new_workflow_state = "draft"
        new_status = "in_progress"
        message = "Task revised and ready to resend"
    
    elif action == "complete":
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        new_status = "completed"
        message = "Task marked as completed"
    
    elif action == "cancel":
        task.status = TaskStatus.CANCELLED
        new_status = "cancelled"
        message = "Task cancelled"
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action: {action}. Valid actions: acknowledge, send_to_client, revise, complete, cancel",
        )
    
    await db.commit()
    
    return TaskActionResponse(
        task_id=task.id,
        action=action,
        message=message,
        new_status=new_status,
        new_workflow_state=new_workflow_state,
    )


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: str,
    user_id: str = Query(..., description="User ID to assign to"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TaskResponse:
    """Assign a task to a user."""
    tenant_id = current_user.get("tenant_id")
    
    query = select(Task).where(Task.id == task_id)
    if tenant_id:
        query = query.where(Task.tenant_id == tenant_id)
    
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    
    # Verify user exists
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    task.assigned_to_id = user_id
    
    await db.commit()
    await db.refresh(task)
    
    # Fetch client for response
    client = None
    if task.client_id:
        client_result = await db.execute(
            select(Client).where(Client.id == task.client_id)
        )
        client = client_result.scalar_one_or_none()
    
    return build_task_response(task, client, user)
