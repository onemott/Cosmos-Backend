"""Tenant schemas."""

import re
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


# ============================================================================
# Branding Schemas
# ============================================================================

class BrandingConfig(BaseModel):
    """Branding configuration schema.
    
    This defines the structure of the branding JSON field stored in tenants.
    """
    
    app_name: Optional[str] = None
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    has_logo: bool = False
    
    @field_validator("primary_color")
    @classmethod
    def validate_hex_color(cls, v: Optional[str]) -> Optional[str]:
        """Validate that primary_color is a valid hex color."""
        if v is None:
            return v
        # Remove leading # if present for validation
        color = v.lstrip("#")
        if not re.match(r"^[0-9A-Fa-f]{6}$", color):
            raise ValueError("primary_color must be a valid 6-digit hex color (e.g., #1E40AF)")
        # Return with # prefix
        return f"#{color.upper()}"
    
    class Config:
        """Pydantic config."""
        from_attributes = True


class BrandingUpdate(BaseModel):
    """Schema for updating branding configuration."""
    
    app_name: Optional[str] = None
    primary_color: Optional[str] = None
    
    @field_validator("primary_color")
    @classmethod
    def validate_hex_color(cls, v: Optional[str]) -> Optional[str]:
        """Validate that primary_color is a valid hex color."""
        if v is None:
            return v
        # Remove leading # if present for validation
        color = v.lstrip("#")
        if not re.match(r"^[0-9A-Fa-f]{6}$", color):
            raise ValueError("primary_color must be a valid 6-digit hex color (e.g., #1E40AF)")
        # Return with # prefix
        return f"#{color.upper()}"


class BrandingResponse(BaseModel):
    """Response schema for branding data."""
    
    tenant_id: str
    tenant_name: str
    app_name: Optional[str] = None
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    has_logo: bool = False
    
    class Config:
        """Pydantic config."""
        from_attributes = True


# ============================================================================
# Tenant Schemas
# ============================================================================

class TenantBase(BaseModel):
    """Base tenant schema."""

    name: str
    slug: str
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None


class TenantCreate(TenantBase):
    """Tenant creation schema."""

    branding: Optional[dict] = None
    settings: Optional[dict] = None


class TenantUpdate(BaseModel):
    """Tenant update schema."""

    name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    branding: Optional[dict] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class TenantResponse(TenantBase):
    """Tenant response schema."""

    id: str
    is_active: bool
    branding: Optional[dict] = None
    settings: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True

