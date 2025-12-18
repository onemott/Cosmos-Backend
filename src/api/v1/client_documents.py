"""Client-facing document API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_client
from src.db.session import get_db
from src.models.document import DocumentType
from src.services.document_service import DocumentService
from src.schemas.client_document import (
    ClientDocumentSummary,
    ClientDocumentList,
    DocumentDownloadResponse,
)

router = APIRouter(prefix="/client/documents", tags=["Client Documents"])


@router.get(
    "",
    response_model=ClientDocumentList,
    summary="List client documents",
    description="Get all documents for the authenticated client.",
)
async def list_documents(
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
) -> ClientDocumentList:
    """List all documents for the authenticated client."""
    client_id = current_client["client_id"]
    
    doc_service = DocumentService(db)
    
    # Convert string to enum if provided
    doc_type_enum = None
    if document_type:
        try:
            doc_type_enum = DocumentType(document_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document type: {document_type}",
            )
    
    documents = await doc_service.get_client_documents(
        client_id=client_id,
        document_type=doc_type_enum,
    )
    
    return ClientDocumentList(
        documents=[
            ClientDocumentSummary(
                id=doc.id,
                name=doc.name,
                document_type=doc.document_type.value,
                status=doc.status.value,
                file_name=doc.file_name,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                description=doc.description,
                created_at=doc.created_at,
            )
            for doc in documents
        ],
        total_count=len(documents),
    )


@router.get(
    "/{document_id}",
    response_model=ClientDocumentSummary,
    summary="Get document details",
    description="Get details of a specific document.",
)
async def get_document(
    document_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> ClientDocumentSummary:
    """Get details of a specific document."""
    client_id = current_client["client_id"]
    
    doc_service = DocumentService(db)
    document = await doc_service.verify_client_access(document_id, client_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    return ClientDocumentSummary(
        id=document.id,
        name=document.name,
        document_type=document.document_type.value,
        status=document.status.value,
        file_name=document.file_name,
        file_size=document.file_size,
        mime_type=document.mime_type,
        description=document.description,
        created_at=document.created_at,
    )


@router.get(
    "/{document_id}/download",
    summary="Download document",
    description="Download a document file. Returns the file directly for local storage, or redirects to presigned URL for S3.",
    responses={
        200: {
            "description": "File download (local storage)",
            "content": {"application/octet-stream": {}},
        },
        302: {
            "description": "Redirect to presigned URL (S3 storage)",
        },
        404: {"description": "Document not found"},
    },
)
async def download_document(
    document_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """Download a document file.
    
    For local storage: Returns the file directly using FileResponse.
    For S3 storage: Redirects to a presigned URL (15 minute expiry).
    """
    client_id = current_client["client_id"]
    
    doc_service = DocumentService(db)
    document = await doc_service.verify_client_access(document_id, client_id)
    
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


@router.get(
    "/{document_id}/download-info",
    response_model=DocumentDownloadResponse,
    summary="Get download information",
    description="Get download URL and metadata for a document (useful for S3 storage).",
)
async def get_download_info(
    document_id: str,
    current_client: dict = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> DocumentDownloadResponse:
    """Get download information for a document.
    
    Returns metadata and download URL (for S3) or indicates direct download (for local).
    Useful for mobile apps that need to handle downloads differently.
    """
    client_id = current_client["client_id"]
    
    doc_service = DocumentService(db)
    document = await doc_service.verify_client_access(document_id, client_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    # Check storage type
    file_path = doc_service.get_file_path(document)
    
    if file_path:
        # Local storage - direct download
        return DocumentDownloadResponse(
            document_id=document.id,
            file_name=document.file_name,
            mime_type=document.mime_type,
            file_size=document.file_size,
            download_url=None,
            expires_at=None,
        )
    else:
        # S3 storage - provide presigned URL
        from datetime import datetime, timedelta, timezone
        
        download_url = doc_service.get_download_url(document, expires_in=900)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=900)
        
        return DocumentDownloadResponse(
            document_id=document.id,
            file_name=document.file_name,
            mime_type=document.mime_type,
            file_size=document.file_size,
            download_url=download_url,
            expires_at=expires_at,
        )

