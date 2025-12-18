"""Schemas for admin document APIs (client and product documents)."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    """Base document fields."""
    
    name: Optional[str] = Field(None, description="Document display name (defaults to filename)")
    description: Optional[str] = Field(None, max_length=1000, description="Document description")


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""
    
    id: str = Field(..., description="Document UUID")
    name: str = Field(..., description="Document display name")
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    document_type: str = Field(..., description="Document type")
    status: str = Field(..., description="Document status")
    description: Optional[str] = Field(None, description="Document description")
    created_at: datetime = Field(..., description="Upload timestamp")
    uploaded_by_id: Optional[str] = Field(None, description="User who uploaded")

    class Config:
        from_attributes = True


class ProductDocumentSummary(BaseModel):
    """Product document summary for list view."""
    
    id: str = Field(..., description="Document UUID")
    name: str = Field(..., description="Document display name")
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    description: Optional[str] = Field(None, description="Document description")
    created_at: datetime = Field(..., description="Upload timestamp")
    uploaded_by_id: Optional[str] = Field(None, description="User who uploaded")

    class Config:
        from_attributes = True


class ProductDocumentList(BaseModel):
    """List of product documents."""
    
    documents: List[ProductDocumentSummary]
    total_count: int


class ClientDocumentUpload(BaseModel):
    """Schema for client document upload metadata."""
    
    document_type: str = Field(..., description="Document type (kyc, statement, report, etc.)")
    name: Optional[str] = Field(None, description="Document display name (defaults to filename)")
    description: Optional[str] = Field(None, max_length=1000, description="Document description")


class AdminDocumentSummary(BaseModel):
    """Document summary for admin views."""
    
    id: str = Field(..., description="Document UUID")
    name: str = Field(..., description="Document display name")
    document_type: str = Field(..., description="Document type")
    status: str = Field(..., description="Document status")
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    description: Optional[str] = Field(None, description="Document description")
    created_at: datetime = Field(..., description="Upload timestamp")
    uploaded_by_id: Optional[str] = Field(None, description="User who uploaded")
    client_id: Optional[str] = Field(None, description="Associated client ID")
    product_id: Optional[str] = Field(None, description="Associated product ID")

    class Config:
        from_attributes = True


class AdminDocumentList(BaseModel):
    """List of documents for admin views."""
    
    documents: List[AdminDocumentSummary]
    total_count: int


class DocumentDownloadInfo(BaseModel):
    """Information for downloading a document."""
    
    document_id: str = Field(..., description="Document UUID")
    file_name: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    file_size: int = Field(..., description="File size in bytes")
    download_url: Optional[str] = Field(
        None,
        description="Presigned URL for download (S3 storage only)"
    )
    is_direct_download: bool = Field(
        True,
        description="If true, use the /download endpoint directly; if false, use download_url"
    )

