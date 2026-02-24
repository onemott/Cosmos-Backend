"""Document management endpoints for admin portal."""

from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.api.deps import get_current_user, require_tenant_user, get_current_tenant_admin
from src.models.client import Client
from src.models.document import DocumentType
from src.services.document_service import DocumentService
from src.schemas.document import (
    DocumentUploadResponse,
    AdminDocumentSummary,
    AdminDocumentList,
)

router = APIRouter()


async def _verify_client_access(
    client_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> Client:
    """Verify the client belongs to the user's tenant.
    
    Args:
        client_id: Client UUID
        tenant_id: Tenant UUID from current user
        db: Database session
        
    Returns:
        Client model instance
        
    Raises:
        HTTPException: If client not found or access denied
    """
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
    
    return client


@router.get("/", response_model=AdminDocumentList)
async def list_documents(
    client_id: Optional[str] = Query(None, description="Filter by client ID"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> AdminDocumentList:
    """List documents with optional filters.
    
    Returns documents belonging to the current user's tenant.
    Can filter by client_id and document_type.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )
    
    # If client_id provided, verify access
    if client_id:
        await _verify_client_access(client_id, tenant_id, db)
    
    # Parse document type
    doc_type_enum = None
    if document_type:
        try:
            doc_type_enum = DocumentType(document_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document type: {document_type}",
            )
    
    doc_service = DocumentService(db)
    
    if client_id:
        # Get documents for specific client
        documents = await doc_service.get_client_documents(
            client_id=client_id,
            document_type=doc_type_enum,
        )
    else:
        # For now, require client_id filter
        # TODO: Add method to get all tenant documents
        documents = []
    
    # Apply pagination
    paginated = documents[skip:skip + limit]
    
    return AdminDocumentList(
        documents=[
            AdminDocumentSummary(
                id=doc.id,
                name=doc.name,
                document_type=doc.document_type.value,
                status=doc.status.value,
                file_name=doc.file_name,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                description=doc.description,
                created_at=doc.created_at,
                uploaded_by_id=doc.uploaded_by_id,
                client_id=doc.client_id,
                product_id=doc.product_id,
            )
            for doc in paginated
        ],
        total_count=len(documents),
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(..., description="File to upload"),
    client_id: str = Form(..., description="Client ID to associate document with"),
    document_type: str = Form("other", description="Document type (kyc, statement, report, contract, tax, compliance, other)"),
    name: Optional[str] = Form(None, description="Display name (defaults to filename)"),
    description: Optional[str] = Form(None, description="Document description"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> DocumentUploadResponse:
    """Upload a document for a client.
    
    Requires tenant_admin role.
    Allowed file types: PDF, Word (.doc, .docx), Images (PNG, JPG, GIF, WebP)
    Maximum file size: 50MB
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )
    
    # Verify client belongs to tenant
    await _verify_client_access(client_id, tenant_id, db)
    
    # Parse document type
    try:
        doc_type_enum = DocumentType(document_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document type: {document_type}. Valid types: {', '.join([t.value for t in DocumentType])}",
        )
    
    # Check file size before reading into memory (prevent memory attacks)
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 50MB limit",
        )
    
    # Read file content
    file_content = await file.read()
    
    if not file_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )
    
    doc_service = DocumentService(db)
    
    try:
        document = await doc_service.save_client_document(
            file_content=file_content,
            file_name=file.filename or "document",
            client_id=client_id,
            tenant_id=tenant_id,
            document_type=doc_type_enum,
            document_name=name,
            description=description,
            uploaded_by_id=current_user.get("user_id"),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return DocumentUploadResponse(
        id=document.id,
        name=document.name,
        file_name=document.file_name,
        file_size=document.file_size,
        mime_type=document.mime_type,
        document_type=document.document_type.value,
        status=document.status.value,
        description=document.description,
        created_at=document.created_at,
        uploaded_by_id=document.uploaded_by_id,
    )


@router.get("/{document_id}", response_model=AdminDocumentSummary)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
) -> AdminDocumentSummary:
    """Get document metadata by ID."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )
    
    doc_service = DocumentService(db)
    document = await doc_service.get_document_by_id_and_tenant(document_id, tenant_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    return AdminDocumentSummary(
        id=document.id,
        name=document.name,
        document_type=document.document_type.value,
        status=document.status.value,
        file_name=document.file_name,
        file_size=document.file_size,
        mime_type=document.mime_type,
        description=document.description,
        created_at=document.created_at,
        uploaded_by_id=document.uploaded_by_id,
        client_id=document.client_id,
        product_id=document.product_id,
    )


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_tenant_user),
):
    """Download a document.
    
    For local storage: Returns the file directly.
    For S3 storage: Redirects to a presigned URL.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )
    
    doc_service = DocumentService(db)
    document = await doc_service.get_document_by_id_and_tenant(document_id, tenant_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    # Check if using local storage
    file_path = doc_service.get_file_path(document)
    
    if file_path:
        # Local storage - return file directly
        return FileResponse(
            path=str(file_path),
            filename=document.file_name,
            media_type=document.mime_type,
        )
    else:
        # S3 storage - redirect to presigned URL
        download_url = doc_service.get_download_url(document)
        return RedirectResponse(url=download_url, status_code=status.HTTP_302_FOUND)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_tenant_admin),
) -> None:
    """Delete a document.
    
    Requires tenant_admin role.
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to a tenant",
        )
    
    doc_service = DocumentService(db)
    document = await doc_service.get_document_by_id_and_tenant(document_id, tenant_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    await doc_service.delete_document(document)
