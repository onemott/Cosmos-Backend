"""Schemas for client-facing document APIs."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ClientDocumentSummary(BaseModel):
    """Document summary for list view."""
    
    id: str = Field(..., description="Document UUID")
    name: str = Field(..., description="Document display name")
    document_type: str = Field(..., description="Type (statement, kyc, report, etc.)")
    status: str = Field(..., description="Status (pending, approved, etc.)")
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    description: Optional[str] = Field(None, description="Document description")
    created_at: datetime = Field(..., description="Upload timestamp")
    uploaded_by_id: Optional[str] = Field(None, description="ID of the user who uploaded the document (null if uploaded by client)")

    class Config:
        from_attributes = True


class ClientDocumentList(BaseModel):
    """List of client documents."""
    
    documents: List[ClientDocumentSummary]
    total_count: int


class DocumentDownloadResponse(BaseModel):
    """Response for document download request."""
    
    document_id: str = Field(..., description="Document UUID")
    file_name: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    file_size: int = Field(..., description="File size in bytes")
    # For local storage, we return the file directly via FileResponse
    # For S3, this would contain a presigned URL
    download_url: Optional[str] = Field(
        None, 
        description="Presigned URL for download (S3 only, not used for local storage)"
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="URL expiration time (S3 only)"
    )

