"""Document storage service with pluggable storage backends.

This service provides document management functionality with support for
both local filesystem and AWS S3 storage backends.
"""

from pathlib import Path
from typing import Optional
from uuid import uuid4
import mimetypes

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.document import Document, DocumentType, DocumentStatus
from src.services.storage import StorageBackend, get_storage_backend


class DocumentService:
    """Service for document storage and retrieval.
    
    Uses a pluggable storage backend (local filesystem or S3).
    """
    
    def __init__(
        self,
        db: AsyncSession,
        storage: Optional[StorageBackend] = None,
    ):
        """Initialize document service.
        
        Args:
            db: Database session
            storage: Optional storage backend (uses default if not provided)
        """
        self.db = db
        self.storage = storage or get_storage_backend()
    
    def _generate_storage_filename(self, original_filename: str) -> str:
        """Generate a unique filename for storage."""
        ext = Path(original_filename).suffix
        return f"{uuid4()}{ext}"
    
    def _detect_mime_type(self, filename: str) -> str:
        """Detect MIME type from filename."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
    
    async def save_client_document(
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
        """Save a client document to storage and create DB record.
        
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
        self.storage.validate_file(file_content, file_name)
        
        # Generate storage path
        storage_filename = self._generate_storage_filename(file_name)
        storage_path = self.storage.generate_storage_path(
            tenant_id=tenant_id,
            client_id=client_id,
            filename=storage_filename,
        )
        
        # Determine MIME type
        mime_type = self._detect_mime_type(file_name)
        
        # Save file to storage first
        await self.storage.save_file(file_content, storage_path, mime_type)
        
        try:
            # Create document record
            document = Document(
                id=str(uuid4()),
                tenant_id=tenant_id,
                client_id=client_id,
                product_id=None,
                name=document_name or file_name,
                document_type=document_type,
                status=DocumentStatus.APPROVED,  # Auto-approve for MVP
                description=description,
                file_name=file_name,
                file_size=len(file_content),
                mime_type=mime_type,
                s3_bucket=self._get_bucket_name(),
                s3_key=storage_path,
                uploaded_by_id=uploaded_by_id,
            )

            self.db.add(document)
            await self.db.commit()
            await self.db.refresh(document)

            return document
        except Exception as e:
            # Rollback DB changes and clean up the file we just saved
            await self.db.rollback()
            try:
                await self.storage.delete_file(storage_path)
            except Exception:
                pass  # Best effort cleanup
            raise
    
    async def save_product_document(
        self,
        file_content: bytes,
        file_name: str,
        product_id: str,
        tenant_id: str,
        document_name: Optional[str] = None,
        description: Optional[str] = None,
        uploaded_by_id: Optional[str] = None,
    ) -> Document:
        """Save a product document to storage and create DB record.
        
        Args:
            file_content: Binary content of the file
            file_name: Original filename
            product_id: Product UUID
            tenant_id: Tenant UUID
            document_name: Display name (defaults to file_name)
            description: Optional description
            uploaded_by_id: UUID of staff user who uploaded (if applicable)
            
        Returns:
            Document model instance
            
        Raises:
            ValueError: If file fails validation (size/type)
        """
        # Validate file before saving
        self.storage.validate_file(file_content, file_name)
        
        # Generate storage path
        storage_filename = self._generate_storage_filename(file_name)
        storage_path = self.storage.generate_storage_path(
            tenant_id=tenant_id,
            product_id=product_id,
            filename=storage_filename,
        )
        
        # Determine MIME type
        mime_type = self._detect_mime_type(file_name)
        
        # Save file to storage first
        await self.storage.save_file(file_content, storage_path, mime_type)
        
        try:
            # Create document record - product documents use OTHER type
            document = Document(
                id=str(uuid4()),
                tenant_id=tenant_id,
                client_id=None,
                product_id=product_id,
                name=document_name or file_name,
                document_type=DocumentType.OTHER,  # Product docs don't need specific types
                status=DocumentStatus.APPROVED,
                description=description,
                file_name=file_name,
                file_size=len(file_content),
                mime_type=mime_type,
                s3_bucket=self._get_bucket_name(),
                s3_key=storage_path,
                uploaded_by_id=uploaded_by_id,
            )
            
            self.db.add(document)
            await self.db.commit()
            await self.db.refresh(document)
            
            return document
        except Exception as e:
            # Rollback DB changes and clean up the file we just saved
            await self.db.rollback()
            try:
                await self.storage.delete_file(storage_path)
            except Exception:
                pass  # Best effort cleanup
            raise
    
    def _get_bucket_name(self) -> str:
        """Get the bucket name for storage.
        
        Returns "local" for local storage, or the S3 bucket name.
        """
        from src.services.storage.local import LocalStorageBackend
        from src.services.storage.s3 import S3StorageBackend
        
        if isinstance(self.storage, LocalStorageBackend):
            return "local"
        elif isinstance(self.storage, S3StorageBackend):
            return self.storage.bucket_name
        else:
            return "unknown"
    
    # Backwards compatibility alias
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
        """Save a client document (backwards compatibility alias)."""
        return await self.save_client_document(
            file_content=file_content,
            file_name=file_name,
            client_id=client_id,
            tenant_id=tenant_id,
            document_type=document_type,
            document_name=document_name,
            description=description,
            uploaded_by_id=uploaded_by_id,
        )
    
    async def get_document(self, document_id: str) -> Optional[Document]:
        """Get a document by ID."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()
    
    async def get_document_by_id_and_tenant(
        self,
        document_id: str,
        tenant_id: str,
    ) -> Optional[Document]:
        """Get a document by ID with tenant isolation."""
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()
    
    async def get_client_documents(
        self,
        client_id: str,
        document_type: Optional[DocumentType] = None,
    ) -> list[Document]:
        """Get all documents for a client."""
        query = select(Document).where(
            Document.client_id == client_id,
            Document.product_id.is_(None),  # Only client documents
        )
        
        if document_type:
            query = query.where(Document.document_type == document_type)
        
        query = query.order_by(Document.created_at.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_product_documents(
        self,
        product_id: str,
        tenant_id: Optional[str] = None,
    ) -> list[Document]:
        """Get all documents for a product.
        
        Args:
            product_id: Product UUID
            tenant_id: Optional tenant UUID for additional security filtering
            
        Returns:
            List of documents belonging to the product
        """
        query = select(Document).where(
            Document.product_id == product_id,
            Document.client_id.is_(None),  # Only product documents
        )
        
        # Defense in depth: filter by tenant if provided
        if tenant_id:
            query = query.where(Document.tenant_id == tenant_id)
        
        query = query.order_by(Document.created_at.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_file_content(self, document: Document) -> Optional[bytes]:
        """Get file content from storage.
        
        Args:
            document: Document model instance
            
        Returns:
            File content as bytes, or None if not found
        """
        try:
            return await self.storage.get_file(document.s3_key)
        except Exception:
            return None
    
    def get_file_path(self, document: Document) -> Optional[Path]:
        """Get the local filesystem path for a document.
        
        Args:
            document: Document model instance
            
        Returns:
            Path to file, or None if not local storage or not found
        """
        return self.storage.get_file_path(document.s3_key)
    
    def get_download_url(
        self,
        document: Document,
        expires_in: int = 900,
    ) -> str:
        """Get a download URL for a document.
        
        Args:
            document: Document model instance
            expires_in: URL expiry in seconds (default 15 minutes)
            
        Returns:
            Download URL (presigned URL for S3, storage key for local)
        """
        return self.storage.get_download_url(
            document.s3_key,
            expires_in=expires_in,
            filename=document.file_name,
        )
    
    def read_file(self, document: Document) -> Optional[bytes]:
        """Read file content from storage (synchronous).
        
        Args:
            document: Document model instance
            
        Returns:
            File content as bytes, or None if not found
        
        Note: This is a synchronous method for backwards compatibility.
              Use get_file_content() for async operations.
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
        try:
            await self.storage.delete_file(document.s3_key)
        except Exception:
            # Continue even if file deletion fails
            pass
        
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

    async def verify_product_access(
        self,
        document_id: str,
        product_id: str,
    ) -> Optional[Document]:
        """Verify that a document belongs to a product.
        
        Args:
            document_id: Document UUID
            product_id: Product UUID
            
        Returns:
            Document if it belongs to the product, None otherwise
        """
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.product_id == product_id,
            )
        )
        return result.scalar_one_or_none()
