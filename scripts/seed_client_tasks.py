#!/usr/bin/env python3
"""
Seed script for creating test tasks for clients.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_client_tasks.py
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory
from src.models.client import Client
from src.models.client_user import ClientUser
from src.models.task import Task, TaskType, TaskStatus, TaskPriority, WorkflowState


# Sample proposal data for investment proposals
SAMPLE_PROPOSALS = [
    {
        "title": "Q1 2025 Portfolio Rebalancing Proposal",
        "description": "We recommend rebalancing your equity allocation to align with your risk profile and market conditions.",
        "proposal_data": {
            "summary": "Reduce tech exposure, increase fixed income allocation",
            "proposed_trades": [
                {"action": "SELL", "ticker": "AAPL", "quantity": 50, "reason": "Reduce tech concentration"},
                {"action": "SELL", "ticker": "NVDA", "quantity": 25, "reason": "Take profits"},
                {"action": "BUY", "ticker": "BND", "quantity": 200, "reason": "Increase bond allocation"},
                {"action": "BUY", "ticker": "VTI", "quantity": 100, "reason": "Diversify equity exposure"},
            ],
            "expected_impact": {
                "equity_allocation_change": "-5%",
                "fixed_income_change": "+5%",
                "estimated_dividend_increase": "$1,200/year",
            },
            "risk_assessment": "This rebalancing reduces portfolio volatility by approximately 8%",
            "document_id": None,  # Would link to detailed PDF
        },
    },
    {
        "title": "New Investment Opportunity - Private Equity Fund",
        "description": "Exclusive access to our new private equity fund focusing on tech startups.",
        "proposal_data": {
            "fund_name": "EAM Tech Growth Fund III",
            "minimum_investment": 100000,
            "currency": "USD",
            "expected_return": "15-20% IRR",
            "lock_up_period": "5 years",
            "key_holdings": ["Series B fintech", "AI/ML startups", "Cloud infrastructure"],
            "risk_level": "High",
            "recommended_allocation": "5-10% of portfolio",
        },
    },
    {
        "title": "Tax Loss Harvesting Opportunity",
        "description": "Year-end tax optimization through strategic loss harvesting.",
        "proposal_data": {
            "estimated_tax_savings": 12500,
            "currency": "USD",
            "positions_to_sell": [
                {"ticker": "META", "unrealized_loss": -8500, "holding_period": "8 months"},
                {"ticker": "GOOGL", "unrealized_loss": -4000, "holding_period": "5 months"},
            ],
            "replacement_positions": [
                {"ticker": "QQQ", "reason": "Maintains tech exposure without wash sale"},
            ],
            "deadline": "December 31, 2025",
        },
    },
]

GENERAL_TASKS = [
    {
        "title": "Annual KYC Update Required",
        "description": "Please review and confirm your personal information is up to date for regulatory compliance.",
        "task_type": TaskType.KYC_REVIEW,
    },
    {
        "title": "Sign Updated Investment Agreement",
        "description": "We've updated our investment management agreement. Please review and sign the new version.",
        "task_type": TaskType.DOCUMENT_REVIEW,
    },
]


async def seed_tasks_for_client(
    db: AsyncSession,
    client: Client,
    tenant_id: str,
) -> list[Task]:
    """Create test tasks for a client."""
    tasks = []
    
    # Create 2-3 proposal approval tasks
    num_proposals = random.randint(2, 3)
    selected_proposals = random.sample(SAMPLE_PROPOSALS, min(num_proposals, len(SAMPLE_PROPOSALS)))
    
    for i, proposal in enumerate(selected_proposals):
        # Vary the due dates and priorities
        due_date = datetime.now(timezone.utc) + timedelta(days=random.randint(3, 14))
        priority = random.choice([TaskPriority.HIGH, TaskPriority.MEDIUM, TaskPriority.URGENT])
        
        task = Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title=proposal["title"],
            description=proposal["description"],
            task_type=TaskType.PROPOSAL_APPROVAL,
            status=TaskStatus.PENDING,
            priority=priority,
            due_date=due_date,
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=due_date,
            proposal_data=proposal.get("proposal_data"),
        )
        db.add(task)
        tasks.append(task)
    
    # Create 1-2 general tasks
    num_general = random.randint(1, 2)
    selected_general = random.sample(GENERAL_TASKS, min(num_general, len(GENERAL_TASKS)))
    
    for task_data in selected_general:
        due_date = datetime.now(timezone.utc) + timedelta(days=random.randint(7, 30))
        
        task = Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title=task_data["title"],
            description=task_data["description"],
            task_type=task_data["task_type"],
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            due_date=due_date,
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=due_date,
        )
        db.add(task)
        tasks.append(task)
    
    # Create 1 already-completed task for history
    completed_task = Task(
        id=str(uuid4()),
        tenant_id=tenant_id,
        client_id=client.id,
        title="Q4 2024 Portfolio Review - Approved",
        description="Quarterly portfolio review and rebalancing proposal.",
        task_type=TaskType.PROPOSAL_APPROVAL,
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.MEDIUM,
        due_date=datetime.now(timezone.utc) - timedelta(days=30),
        completed_at=datetime.now(timezone.utc) - timedelta(days=28),
        workflow_state=WorkflowState.APPROVED,
    )
    db.add(completed_task)
    tasks.append(completed_task)
    
    return tasks


async def main():
    """Main seed function."""
    print("=" * 60)
    print("Client Tasks Seed Script")
    print("=" * 60)
    
    async with async_session_factory() as db:
        # Get all client users (created by portfolio seed script)
        result = await db.execute(
            select(ClientUser).options()
        )
        client_users = result.scalars().all()
        
        if not client_users:
            print("\nNo client users found. Run seed_client_portfolio.py first.")
            return
        
        print(f"\nFound {len(client_users)} client users")
        
        for client_user in client_users:
            # Get the client
            client_result = await db.execute(
                select(Client).where(Client.id == client_user.client_id)
            )
            client = client_result.scalar_one_or_none()
            
            if not client:
                continue
            
            print(f"\nSeeding tasks for: {client.display_name} ({client_user.email})")
            
            # Check if tasks already exist for this client
            existing_result = await db.execute(
                select(Task).where(Task.client_id == client.id).limit(1)
            )
            if existing_result.scalar_one_or_none():
                print(f"  Tasks already exist, skipping...")
                continue
            
            tasks = await seed_tasks_for_client(db, client, client_user.tenant_id)
            print(f"  Created {len(tasks)} tasks")
            
            for task in tasks:
                status_str = f"[{task.workflow_state.value}]" if task.workflow_state else ""
                print(f"    - {task.title} {status_str}")
        
        await db.commit()
    
    print("\n" + "=" * 60)
    print("Task seeding complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

