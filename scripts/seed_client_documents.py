#!/usr/bin/env python3
"""
Seed script for creating test documents for clients.

This script creates sample PDF documents for testing the document
management features. Since we don't have actual PDF files, we create
simple placeholder files.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/seed_client_documents.py
"""

import asyncio
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
from src.models.document import Document, DocumentType, DocumentStatus
from src.services.document_service import DocumentService


# Sample document definitions
SAMPLE_DOCUMENTS = [
    {
        "name": "Q4 2024 Portfolio Statement",
        "file_name": "Q4_2024_Portfolio_Statement.pdf",
        "document_type": DocumentType.STATEMENT,
        "description": "Quarterly portfolio statement for October - December 2024",
    },
    {
        "name": "Q3 2024 Portfolio Statement",
        "file_name": "Q3_2024_Portfolio_Statement.pdf",
        "document_type": DocumentType.STATEMENT,
        "description": "Quarterly portfolio statement for July - September 2024",
    },
    {
        "name": "2024 Annual Report",
        "file_name": "2024_Annual_Report.pdf",
        "document_type": DocumentType.REPORT,
        "description": "Annual investment performance report for 2024",
    },
    {
        "name": "Investment Policy Statement",
        "file_name": "Investment_Policy_Statement.pdf",
        "document_type": DocumentType.CONTRACT,
        "description": "Your personalized investment policy statement",
    },
    {
        "name": "KYC Verification - Completed",
        "file_name": "KYC_Verification_2024.pdf",
        "document_type": DocumentType.KYC,
        "description": "Know Your Customer verification documentation",
    },
    {
        "name": "Tax Summary 2024",
        "file_name": "Tax_Summary_2024.pdf",
        "document_type": DocumentType.TAX,
        "description": "Summary of taxable events for 2024 tax year",
    },
]


def create_placeholder_pdf(client_name: str, doc_name: str) -> bytes:
    """Create a simple placeholder PDF-like content.
    
    In a real scenario, you would generate actual PDFs using reportlab
    or similar. For testing purposes, we create a simple text file
    with a .pdf extension.
    """
    content = f"""
================================================================================
                          PLACEHOLDER DOCUMENT
================================================================================

Document: {doc_name}
Client: {client_name}
Generated: {datetime.now().isoformat()}

This is a placeholder document created for testing purposes.
In a production environment, this would be an actual PDF document
containing financial statements, reports, or other client documents.

================================================================================
                        END OF PLACEHOLDER DOCUMENT
================================================================================
""".encode('utf-8')
    return content


async def seed_documents_for_client(
    db: AsyncSession,
    doc_service: DocumentService,
    client: Client,
    tenant_id: str,
) -> list[Document]:
    """Create test documents for a client."""
    documents = []
    client_name = client.display_name
    
    for doc_def in SAMPLE_DOCUMENTS:
        # Create placeholder content
        content = create_placeholder_pdf(client_name, doc_def["name"])
        
        try:
            document = await doc_service.save_document(
                file_content=content,
                file_name=doc_def["file_name"],
                client_id=client.id,
                tenant_id=tenant_id,
                document_type=doc_def["document_type"],
                document_name=doc_def["name"],
                description=doc_def["description"],
            )
            documents.append(document)
        except ValueError as e:
            print(f"  Warning: Failed to save {doc_def['name']}: {e}")
    
    return documents


async def main():
    """Main seed function."""
    print("=" * 60)
    print("Client Documents Seed Script")
    print("=" * 60)
    
    async with async_session_factory() as db:
        doc_service = DocumentService(db)
        
        # Get all client users (created by portfolio seed script)
        result = await db.execute(select(ClientUser))
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
            
            print(f"\nSeeding documents for: {client.display_name} ({client_user.email})")
            
            # Check if documents already exist for this client
            existing_result = await db.execute(
                select(Document).where(Document.client_id == client.id).limit(1)
            )
            if existing_result.scalar_one_or_none():
                print(f"  Documents already exist, skipping...")
                continue
            
            documents = await seed_documents_for_client(
                db, doc_service, client, client_user.tenant_id
            )
            print(f"  Created {len(documents)} documents:")
            
            for doc in documents:
                print(f"    - {doc.name} ({doc.file_name})")
    
    print("\n" + "=" * 60)
    print("Document seeding complete!")
    print("=" * 60)
    print("\nDocuments are stored in: backend/storage/documents/")


if __name__ == "__main__":
    asyncio.run(main())

