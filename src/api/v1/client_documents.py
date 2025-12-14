"""Client-facing document API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_client
from src.db.session import get_db
from src.models.document import DocumentType
from src.services.document_service import DocumentService
from src.schemas.client_document import (
    ClientDocumentSummary,
    ClientDocumentList,
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
    description="Download a document file. Returns the file directly for local storage.",
    responses={
        200: {
            "description": "File download",
            "content": {"application/octet-stream": {}},
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
    
    For local storage, returns the file directly using FileResponse.
    For S3 (future), would return a presigned URL.
    """
    client_id = current_client["client_id"]
    
    doc_service = DocumentService(db)
    document = await doc_service.verify_client_access(document_id, client_id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    # Get file path for local storage
    file_path = doc_service.get_file_path(document)
    
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found in storage",
        )
    
    # Return file directly
    return FileResponse(
        path=str(file_path),
        filename=document.file_name,
        media_type=document.mime_type,
    )

