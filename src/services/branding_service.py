"""Branding service for tenant logo and branding management."""

from pathlib import Path
from typing import Optional

from fastapi import UploadFile

# Base storage path for logos
LOGO_STORAGE_PATH = Path(__file__).parent.parent.parent / "storage" / "logos"

# Allowed file extensions and MIME types
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB


class BrandingServiceError(Exception):
    """Base exception for branding service errors."""
    pass


class InvalidFileTypeError(BrandingServiceError):
    """Raised when file type is not allowed."""
    pass


class FileTooLargeError(BrandingServiceError):
    """Raised when file exceeds size limit."""
    pass


def ensure_logo_directory(tenant_id: str) -> Path:
    """Ensure the logo directory exists for a tenant.
    
    Args:
        tenant_id: The tenant's UUID
        
    Returns:
        Path to the tenant's logo directory
    """
    tenant_logo_dir = LOGO_STORAGE_PATH / tenant_id
    tenant_logo_dir.mkdir(parents=True, exist_ok=True)
    return tenant_logo_dir


def get_logo_path(tenant_id: str) -> Optional[Path]:
    """Get the path to a tenant's logo file if it exists.
    
    Args:
        tenant_id: The tenant's UUID
        
    Returns:
        Path to the logo file, or None if no logo exists
    """
    tenant_logo_dir = LOGO_STORAGE_PATH / tenant_id
    
    if not tenant_logo_dir.exists():
        return None
    
    # Check for logo file with any allowed extension
    for ext in ALLOWED_EXTENSIONS:
        logo_path = tenant_logo_dir / f"logo{ext}"
        if logo_path.exists():
            return logo_path
    
    return None


def get_logo_url(tenant_id: str, api_base: str = "/api/v1") -> Optional[str]:
    """Get the URL to a tenant's logo if it exists.
    
    Args:
        tenant_id: The tenant's UUID
        api_base: The API base path
        
    Returns:
        URL to the logo endpoint, or None if no logo exists
    """
    if get_logo_path(tenant_id):
        return f"{api_base}/tenants/{tenant_id}/logo"
    return None


async def save_logo(tenant_id: str, file: UploadFile) -> str:
    """Save a logo file for a tenant.
    
    Args:
        tenant_id: The tenant's UUID
        file: The uploaded file
        
    Returns:
        The filename that was saved
        
    Raises:
        InvalidFileTypeError: If file type is not allowed
        FileTooLargeError: If file exceeds size limit
    """
    # Validate MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise InvalidFileTypeError(
            f"File type '{file.content_type}' not allowed. "
            f"Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
        )
    
    # Get file extension from original filename
    original_filename = file.filename or "logo.png"
    ext = Path(original_filename).suffix.lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        # Fall back to extension from MIME type
        ext = ".png" if file.content_type == "image/png" else ".jpg"
    
    # Read file content and check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        size_mb = len(content) / 1024 / 1024
        raise FileTooLargeError(
            f"File size ({size_mb:.1f}MB) exceeds maximum of 2MB"
        )
    
    # Ensure directory exists
    tenant_logo_dir = ensure_logo_directory(tenant_id)
    
    # Remove any existing logo files
    delete_logo(tenant_id)
    
    # Save new logo
    logo_filename = f"logo{ext}"
    logo_path = tenant_logo_dir / logo_filename
    
    with open(logo_path, "wb") as f:
        f.write(content)
    
    return logo_filename


def delete_logo(tenant_id: str) -> bool:
    """Delete a tenant's logo file.
    
    Args:
        tenant_id: The tenant's UUID
        
    Returns:
        True if a logo was deleted, False otherwise
    """
    tenant_logo_dir = LOGO_STORAGE_PATH / tenant_id
    
    if not tenant_logo_dir.exists():
        return False
    
    deleted = False
    for ext in ALLOWED_EXTENSIONS:
        logo_path = tenant_logo_dir / f"logo{ext}"
        if logo_path.exists():
            logo_path.unlink()
            deleted = True
    
    return deleted


def get_logo_mime_type(tenant_id: str) -> Optional[str]:
    """Get the MIME type of a tenant's logo.
    
    Args:
        tenant_id: The tenant's UUID
        
    Returns:
        MIME type string, or None if no logo exists
    """
    logo_path = get_logo_path(tenant_id)
    if not logo_path:
        return None
    
    ext = logo_path.suffix.lower()
    if ext == ".png":
        return "image/png"
    elif ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    
    return None


def has_logo(tenant_id: str) -> bool:
    """Check if a tenant has a logo uploaded.
    
    Args:
        tenant_id: The tenant's UUID
        
    Returns:
        True if logo exists, False otherwise
    """
    return get_logo_path(tenant_id) is not None

