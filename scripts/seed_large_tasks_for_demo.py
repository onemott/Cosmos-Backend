#!/usr/bin/env python3
"""
Seed script for creating a LARGE number of test tasks for client@example.com
to test infinite scrolling and pagination.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
import uuid
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

# Target user
TARGET_EMAIL = "client@example.com"

async def main():
    print("=" * 60)
    print(f"Seeding LARGE task data for {TARGET_EMAIL}")
    print("=" * 60)
    
    async with async_session_factory() as db:
        # 1. Find the user
        result = await db.execute(
            select(ClientUser).where(ClientUser.email == TARGET_EMAIL)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"User {TARGET_EMAIL} not found!")
            return

        # 2. Find the client
        client_result = await db.execute(
            select(Client).where(Client.id == user.client_id)
        )
        client = client_result.scalar_one_or_none()
        
        if not client:
            print(f"Client for user {TARGET_EMAIL} not found!")
            return
            
        print(f"Found Client: {client.display_name} (ID: {client.id})")
        
        # 3. Clear existing tasks for a clean test
        print("Clearing existing tasks for this client...")
        await db.execute(delete(Task).where(Task.client_id == client.id))
        
        tasks_to_create = []
        tenant_id = user.tenant_id
        
        # --- Templates for Realistic Tasks ---
        PROPOSAL_TEMPLATES = [
            ("Q1 Portfolio Rebalancing - Defensive Tilt", "Review the proposed shift from high-growth tech to defensive utilities and healthcare sectors."),
            ("New Investment Opportunity: Green Energy Infrastructure Fund", "Strategic allocation proposal for the upcoming Global Renewables Fund."),
            ("Fixed Income Strategy Adjustment - Short Duration", "Proposed reduction in long-term bond exposure in favor of short-duration instruments."),
            ("Emerging Markets Exposure Update", "Recommended increase in Southeast Asian equity exposure based on recent economic indicators."),
            ("Cash Management Optimization", "Proposal to move idle cash into high-yield money market funds."),
            ("Gold & Precious Metals Allocation", "Tactical allocation to gold to hedge against potential currency volatility."),
            ("European Equity Dividend Strategy", "Proposed switch to high-dividend yield stocks in the Eurozone."),
            ("Semi-conductor Sector Profit Taking", "Recommendation to trim positions in overextended tech stocks and lock in gains."),
            ("US Small Cap Growth Opportunity", "Diversification proposal into Russell 2000 index components."),
            ("Real Estate REITs Diversification", "Proposed exposure to industrial and residential REITs for stable income.")
        ]
        
        COMPLIANCE_TEMPLATES = [
            ("Annual KYC Profile Update", "Please review and update your personal information and financial profile for regulatory compliance."),
            ("Passport/ID Document Expiry Notice", "Your identification document on file is expiring soon. Please upload a clear copy of your new passport."),
            ("Updated Terms of Business - 2026", "Please review and acknowledge the updated terms and conditions for your investment account."),
            ("Risk Tolerance Re-assessment", "It has been 24 months since your last risk profile assessment. Please complete the updated questionnaire."),
            ("Source of Wealth Declaration", "Additional documentation required for the recent account funding as per AML regulations."),
            ("W-8BEN Form Renewal", "Your tax status certification is due for renewal. Please submit the signed form."),
            ("FATCA/CRS Self-Certification", "Annual requirement to confirm your tax residency status."),
            ("Power of Attorney Verification", "Periodic review of the authorized signatories on your account.")
        ]
        
        PRODUCT_REQUEST_TEMPLATES = [
            ("Subscription: Blackstone Private Credit Fund", "Client initiated request for participation in the upcoming capital call."),
            ("Inquiry: Structured Notes - Principal Protected", "Client interested in downside protection products for the current market volatility."),
            ("Allocation Query: Macro Alpha Hedge Fund", "Client requested details on performance and liquidity terms for potential allocation."),
            ("Thematic ETF Inquiry: AI & Robotics", "Client wants to explore specialized exposure in artificial intelligence sector."),
            ("Private Equity Secondary Market Opportunity", "Client expressed interest in buying secondary stakes in established PE funds."),
            ("Venture Capital Seed Fund Info Request", "Client seeking early-stage tech investment opportunities.")
        ]

        # --- Type 1: EAM/Advisor Initiated (Pending Client Action) ---
        # Proposals (15 items)
        print("Generating Realistic Proposals...")
        for i in range(15):
            template = random.choice(PROPOSAL_TEMPLATES)
            due_date = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30))
            task = Task(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                client_id=client.id,
                title=f"{template[0]} ({i+1})",
                description=template[1],
                task_type=TaskType.PROPOSAL_APPROVAL,
                status=TaskStatus.PENDING,
                priority=random.choice([TaskPriority.HIGH, TaskPriority.MEDIUM]),
                due_date=due_date,
                workflow_state=WorkflowState.PENDING_CLIENT,
                approval_required_by=due_date,
                created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 10))
            )
            tasks_to_create.append(task)

        # Compliance / General (10 items)
        print("Generating Realistic Compliance Tasks...")
        for i in range(10):
            template = random.choice(COMPLIANCE_TEMPLATES)
            task_type = random.choice([TaskType.KYC_REVIEW, TaskType.DOCUMENT_REVIEW, TaskType.GENERAL])
            due_date = datetime.now(timezone.utc) + timedelta(days=random.randint(5, 60))
            task = Task(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                client_id=client.id,
                title=f"{'Urgent: ' if i % 3 == 0 else ''}{template[0]}",
                description=template[1],
                task_type=task_type,
                status=TaskStatus.PENDING,
                priority=TaskPriority.URGENT if i % 3 == 0 else TaskPriority.MEDIUM,
                due_date=due_date,
                workflow_state=WorkflowState.PENDING_CLIENT,
                approval_required_by=due_date,
                created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 20))
            )
            tasks_to_create.append(task)

        # --- Type 2: Client Initiated (Pending EAM Action) ---
        # Product Requests (10 items)
        print("Generating Realistic Product Requests...")
        for i in range(10):
            template = random.choice(PRODUCT_REQUEST_TEMPLATES)
            created_at = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 15))
            task = Task(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                client_id=client.id,
                title=template[0],
                description=template[1],
                task_type=TaskType.PRODUCT_REQUEST,
                status=TaskStatus.IN_PROGRESS,
                priority=TaskPriority.MEDIUM,
                due_date=None,
                workflow_state=WorkflowState.PENDING_EAM, # Waiting for Advisor
                created_at=created_at
            )
            tasks_to_create.append(task)

        # --- Type 3: System / Historical (Completed/Archived) ---
        # Completed Tasks (10 items)
        print("Generating Historical Tasks...")
        HISTORICAL_TITLES = [
            "Completed: 2025 Annual Review",
            "Archive: Account Opening Documentation",
            "Success: Global Bond Fund Subscription",
            "Finished: Risk Profile Re-assessment",
            "Closed: Dividend Reinvestment Setup",
            "Completed: Address Change Verification",
            "History: Private Equity Distribution Notice",
            "Archive: Q4 2024 Performance Report Review"
        ]
        for i in range(10):
            completed_at = datetime.now(timezone.utc) - timedelta(days=random.randint(10, 100))
            task = Task(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                client_id=client.id,
                title=random.choice(HISTORICAL_TITLES) + f" #{i+1}",
                description="This task has been successfully processed and archived.",
                task_type=TaskType.GENERAL,
                status=TaskStatus.COMPLETED,
                priority=TaskPriority.LOW,
                due_date=completed_at - timedelta(days=5),
                workflow_state=WorkflowState.APPROVED,
                completed_at=completed_at,
                created_at=completed_at - timedelta(days=10)
            )
            tasks_to_create.append(task)

        # Add all to DB
        db.add_all(tasks_to_create)
        await db.commit()
        
        print(f"\nSuccessfully created {len(tasks_to_create)} tasks for {TARGET_EMAIL}")
        print("Breakdown:")
        print(f"  - Pending Client (Proposals/Compliance): 25")
        print(f"  - Pending EAM (Product Requests): 10")
        print(f"  - Completed/History: 10")
        print("\nNow you can test infinite scrolling!")

if __name__ == "__main__":
    asyncio.run(main())
