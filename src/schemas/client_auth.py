"""Schemas for client authentication."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class TenantBrandingInfo(BaseModel):
    """Embedded tenant branding information for client responses."""
    
    app_name: Optional[str] = Field(None, description="Custom app name for the tenant")
    primary_color: Optional[str] = Field(None, description="Primary brand color (hex)")
    logo_url: Optional[str] = Field(None, description="URL to tenant logo")
    has_logo: bool = Field(default=False, description="Whether tenant has a logo")

    class Config:
        from_attributes = True


class ClientLoginRequest(BaseModel):
    """Request schema for client login."""
    
    email: EmailStr = Field(..., description="Client email address")
    password: str = Field(..., min_length=8, description="Client password")


class ClientRegisterRequest(BaseModel):
    """Request schema for creating a ClientUser for an existing Client."""
    
    client_id: str = Field(..., description="UUID of the existing Client record")
    email: EmailStr = Field(..., description="Email address for login")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)")


class ClientTokenResponse(BaseModel):
    """Response schema for client authentication tokens."""
    
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiry in seconds")
    client_id: str = Field(..., description="Client UUID")
    client_name: str = Field(..., description="Client display name")
    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_name: Optional[str] = Field(None, description="Tenant/EAM firm name")
    tenant_branding: Optional[TenantBrandingInfo] = Field(None, description="Tenant branding info")


class ClientRefreshRequest(BaseModel):
    """Request schema for token refresh."""
    
    refresh_token: str = Field(..., description="Refresh token from login")


class ClientUserProfile(BaseModel):
    """Response schema for client user profile (no sensitive data)."""
    
    id: str = Field(..., description="ClientUser UUID")
    client_id: str = Field(..., description="Associated Client UUID")
    tenant_id: str = Field(..., description="Tenant UUID")
    email: str = Field(..., description="Email address")
    client_name: str = Field(..., description="Client display name")
    is_active: bool = Field(..., description="Whether account is active")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")
    mfa_enabled: bool = Field(..., description="Whether MFA is enabled")
    created_at: datetime = Field(..., description="Account creation timestamp")
    # Extended fields from joins
    tenant_name: Optional[str] = Field(None, description="Tenant/EAM firm name")
    risk_profile: Optional[str] = Field(None, description="Client risk profile")
    # User preferences
    language: str = Field(default="en", description="Preferred language (en, zh-CN)")
    # Tenant branding
    tenant_branding: Optional[TenantBrandingInfo] = Field(None, description="Tenant branding info")

    class Config:
        from_attributes = True


class ClientPasswordChangeRequest(BaseModel):
    """Request schema for password change."""
    
    current_password: str = Field(..., min_length=8, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")


class ClientLanguageUpdateRequest(BaseModel):
    """Request schema for updating language preference."""
    
    language: str = Field(
        ..., 
        pattern="^(en|zh-CN)$",
        description="Language code (en or zh-CN)"
    )


class MessageResponse(BaseModel):
    """Generic message response."""
    
    message: str = Field(..., description="Response message")
    success: bool = Field(default=True, description="Whether operation succeeded")

