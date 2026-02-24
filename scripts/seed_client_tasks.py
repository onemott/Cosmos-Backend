#!/usr/bin/env python3
"""
Seed script for creating test tasks for clients.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_client_tasks.py
"""

import asyncio
import argparse
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select, delete
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
    """Create test tasks covering all task types for a client."""
    tasks = []
    now = datetime.now(timezone.utc)
    
    proposal = random.choice(SAMPLE_PROPOSALS)
    due_date = now + timedelta(days=7)
    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title=proposal["title"],
            description=proposal["description"],
            task_type=TaskType.PROPOSAL_APPROVAL,
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            due_date=due_date,
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=due_date,
            proposal_data={
                **proposal.get("proposal_data", {}),
                "eam_message": "We recommend reviewing the proposal highlights before approval.",
                "sent_to_client_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="Product Request: Diversified Growth Portfolio",
            description="Client requested a diversified growth allocation.",
            task_type=TaskType.PRODUCT_REQUEST,
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            workflow_state=WorkflowState.PENDING_EAM,
            proposal_data={
                "orders": [
                    {
                        "product_id": str(uuid4()),
                        "product_name": "Diversified Growth Portfolio",
                        "module_code": "custom_portfolio",
                        "min_investment": 100000,
                        "requested_amount": 125000,
                        "currency": "USD",
                    },
                    {
                        "product_id": str(uuid4()),
                        "product_name": "Capital Preservation Portfolio",
                        "module_code": "custom_portfolio",
                        "min_investment": 25000,
                        "requested_amount": 25000,
                        "currency": "USD",
                    },
                ],
                "total_min_investment": 125000,
                "total_requested_amount": 150000,
                "client_notes": "Please prioritize capital preservation options.",
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="Lightweight Interest: Balanced Strategy",
            description="Client expressed interest in a balanced strategy product.",
            task_type=TaskType.LIGHTWEIGHT_INTEREST,
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            workflow_state=WorkflowState.PENDING_EAM,
            proposal_data={
                "product_id": str(uuid4()),
                "product_name": "Balanced Strategy",
                "module_code": "custom_portfolio",
                "interest_type": "consult",
                "client_notes": "Interested in the risk profile.",
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="Onboarding Checklist",
            description="Complete onboarding checklist items.",
            task_type=TaskType.ONBOARDING,
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            due_date=now + timedelta(days=10),
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=now + timedelta(days=10),
            proposal_data={
                "checklist": ["Verify identity", "Confirm risk profile", "Upload address proof"],
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="KYC Review Update",
            description="Please review and confirm your KYC information.",
            task_type=TaskType.KYC_REVIEW,
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            due_date=now + timedelta(days=14),
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=now + timedelta(days=14),
            proposal_data={
                "risk_level": "medium",
                "documents": ["Passport", "Proof of Address"],
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="Document Review: Updated Agreement",
            description="Please review and sign the updated agreement.",
            task_type=TaskType.DOCUMENT_REVIEW,
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            due_date=now + timedelta(days=20),
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=now + timedelta(days=20),
            proposal_data={
                "documents": ["Investment Agreement v2"],
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="Compliance Check",
            description="Compliance verification required for recent account activity.",
            task_type=TaskType.COMPLIANCE_CHECK,
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            due_date=now + timedelta(days=12),
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=now + timedelta(days=12),
            proposal_data={
                "checklist": ["Source of funds confirmation", "Tax residency confirmation"],
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="Risk Review",
            description="Risk profile review required for upcoming allocation changes.",
            task_type=TaskType.RISK_REVIEW,
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            due_date=now + timedelta(days=18),
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=now + timedelta(days=18),
            proposal_data={
                "risk_level": "balanced",
                "notes": "Please confirm your risk tolerance.",
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="Account Opening Requirements",
            description="Provide required documents to open the new account.",
            task_type=TaskType.ACCOUNT_OPENING,
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
            due_date=now + timedelta(days=25),
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=now + timedelta(days=25),
            proposal_data={
                "account_type": "Managed Portfolio",
                "documents": ["Signed forms", "Tax ID"],
                "submitted_at": now.isoformat(),
            },
        )
    )

    tasks.append(
        Task(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client.id,
            title="General Follow-up",
            description="Advisor follow-up request.",
            task_type=TaskType.GENERAL,
            status=TaskStatus.PENDING,
            priority=TaskPriority.LOW,
            workflow_state=WorkflowState.PENDING_CLIENT,
            approval_required_by=now + timedelta(days=30),
            proposal_data={
                "notes": "Please share your preferred follow-up time.",
                "submitted_at": now.isoformat(),
            },
        )
    )

    for task in tasks:
        db.add(task)
    
    return tasks


async def main():
    """Main seed function."""
    parser = argparse.ArgumentParser(description="Seed client tasks")
    parser.add_argument("--email", help="Only seed tasks for a specific client email")
    parser.add_argument("--reset", action="store_true", help="Delete existing tasks before seeding")
    args = parser.parse_args()

    print("=" * 60)
    print("Client Tasks Seed Script")
    print("=" * 60)
    
    async with async_session_factory() as db:
        if args.email:
            result = await db.execute(
                select(ClientUser).where(ClientUser.email == args.email)
            )
        else:
            result = await db.execute(select(ClientUser).options())

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
            
            if args.reset:
                print("  Clearing existing tasks...")
                await db.execute(delete(Task).where(Task.client_id == client.id))
            
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

