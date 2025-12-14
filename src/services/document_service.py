"""Document storage service with local filesystem backend.

This service provides an abstraction layer for document storage,
currently using local filesystem with the ability to migrate to S3 later.
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, BinaryIO
from uuid import uuid4
import mimetypes

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document import Document, DocumentType, DocumentStatus


class DocumentService:
    """Service for document storage and retrieval.
    
    Uses local filesystem storage for development.
    Designed for future S3 migration with minimal code changes.
    """
    
    # Base storage directory (relative to backend folder)
    STORAGE_BASE = Path("storage/documents")
    
    # Security constraints
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".csv"}
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._ensure_storage_exists()
    
    def _ensure_storage_exists(self):
        """Create storage directories if they don't exist."""
        self.STORAGE_BASE.mkdir(parents=True, exist_ok=True)
    
    def _get_tenant_path(self, tenant_id: str) -> Path:
        """Get storage path for a tenant."""
        return self.STORAGE_BASE / "tenants" / tenant_id
    
    def _get_client_path(self, tenant_id: str, client_id: str) -> Path:
        """Get storage path for a client."""
        path = self._get_tenant_path(tenant_id) / "clients" / client_id
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def _generate_storage_filename(self, original_filename: str) -> str:
        """Generate a unique filename for storage."""
        ext = Path(original_filename).suffix
        return f"{uuid4()}{ext}"
    
    def _detect_mime_type(self, filename: str) -> str:
        """Detect MIME type from filename."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
    
    def validate_file(self, file_content: bytes, file_name: str) -> None:
        """Validate file size and type.
        
        Args:
            file_content: Binary content of the file
            file_name: Original filename
            
        Raises:
            ValueError: If file fails validation
        """
        # Validate file size
        if len(file_content) > self.MAX_FILE_SIZE:
            max_mb = self.MAX_FILE_SIZE // 1024 // 1024
            raise ValueError(f"File size exceeds maximum allowed ({max_mb}MB)")
        
        # Validate file extension
        ext = Path(file_name).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File type '{ext}' not allowed. "
                f"Allowed types: {', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )
    
    async def save_document(
        self,
        file_content: bytes,
        file_name: str,
        client_id: str,
        tenant_id: str,
        document_type: DocumentType,
        document_name: Optional[str] = None,
        description: Optional[str] = None,
        uploaded_by_id: Optional[str] = None,
    ) -> Document:
        """Save a document to local storage and create DB record.
        
        Args:
            file_content: Binary content of the file
            file_name: Original filename
            client_id: Client UUID
            tenant_id: Tenant UUID
            document_type: Type of document (kyc, statement, report, etc.)
            document_name: Display name (defaults to file_name)
            description: Optional description
            uploaded_by_id: UUID of staff user who uploaded (if applicable)
            
        Returns:
            Document model instance
            
        Raises:
            ValueError: If file fails validation (size/type)
        """
        # Validate file before saving
        self.validate_file(file_content, file_name)
        
        # Generate storage path
        client_path = self._get_client_path(tenant_id, client_id)
        storage_filename = self._generate_storage_filename(file_name)
        full_path = client_path / storage_filename
        
        # Write file to disk
        with open(full_path, "wb") as f:
            f.write(file_content)
        
        # Determine MIME type
        mime_type = self._detect_mime_type(file_name)
        
        # Create relative path for storage (from STORAGE_BASE)
        relative_path = str(full_path.relative_to(self.STORAGE_BASE))
        
        # Create document record
        document = Document(
            id=str(uuid4()),
            tenant_id=tenant_id,
            client_id=client_id,
            name=document_name or file_name,
            document_type=document_type,
            status=DocumentStatus.APPROVED,  # Auto-approve for MVP
            description=description,
            file_name=file_name,
            file_size=len(file_content),
            mime_type=mime_type,
            # For local storage, use s3_bucket/s3_key to store local path
            # This allows future migration to S3 with minimal schema changes
            s3_bucket="local",
            s3_key=relative_path,
            uploaded_by_id=uploaded_by_id,
        )
        
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        
        return document
    
    async def get_document(self, document_id: str) -> Optional[Document]:
        """Get a document by ID."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()
    
    async def get_client_documents(
        self,
        client_id: str,
        document_type: Optional[DocumentType] = None,
    ) -> list[Document]:
        """Get all documents for a client."""
        query = select(Document).where(Document.client_id == client_id)
        
        if document_type:
            query = query.where(Document.document_type == document_type)
        
        query = query.order_by(Document.created_at.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    def get_file_path(self, document: Document) -> Optional[Path]:
        """Get the local filesystem path for a document.
        
        Args:
            document: Document model instance
            
        Returns:
            Path to file, or None if not found or not local storage
        """
        if document.s3_bucket != "local":
            # Not local storage (future S3 migration would handle this differently)
            return None
        
        full_path = self.STORAGE_BASE / document.s3_key
        
        if not full_path.exists():
            return None
        
        return full_path
    
    def read_file(self, document: Document) -> Optional[bytes]:
        """Read file content from storage.
        
        Args:
            document: Document model instance
            
        Returns:
            File content as bytes, or None if not found
        """
        path = self.get_file_path(document)
        if not path:
            return None
        
        with open(path, "rb") as f:
            return f.read()
    
    async def delete_document(self, document: Document) -> bool:
        """Delete a document from storage and database.
        
        Args:
            document: Document model instance
            
        Returns:
            True if deleted, False otherwise
        """
        # Delete file from storage
        path = self.get_file_path(document)
        if path and path.exists():
            path.unlink()
        
        # Delete database record
        await self.db.delete(document)
        await self.db.commit()
        
        return True
    
    async def verify_client_access(
        self,
        document_id: str,
        client_id: str,
    ) -> Optional[Document]:
        """Verify that a client has access to a document.
        
        Args:
            document_id: Document UUID
            client_id: Client UUID
            
        Returns:
            Document if accessible, None otherwise
        """
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.client_id == client_id,
            )
        )
        return result.scalar_one_or_none()

