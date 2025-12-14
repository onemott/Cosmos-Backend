"""Product and ProductCategory schemas."""

from decimal import Decimal
from typing import Optional
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk level enumeration."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    BALANCED = "balanced"
    GROWTH = "growth"
    AGGRESSIVE = "aggressive"


# ===== ProductCategory Schemas =====


class ProductCategoryBase(BaseModel):
    """Base product category schema."""

    name: str = Field(..., min_length=1, max_length=100)
    name_zh: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    sort_order: int = Field(default=0)


class ProductCategoryCreate(ProductCategoryBase):
    """Product category creation schema."""

    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")


class ProductCategoryUpdate(BaseModel):
    """Product category update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    name_zh: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProductCategoryResponse(ProductCategoryBase):
    """Product category response schema."""

    id: str
    tenant_id: Optional[str] = None
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


# ===== Product Schemas =====


class ProductBase(BaseModel):
    """Base product schema."""

    name: str = Field(..., min_length=1, max_length=255)
    name_zh: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    description_zh: Optional[str] = Field(None, max_length=2000)
    category: str = Field(..., max_length=100)
    category_id: Optional[str] = None
    risk_level: str = Field(..., max_length=50)
    min_investment: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="USD", max_length=3)
    expected_return: Optional[str] = Field(None, max_length=100)
    extra_data: Optional[dict] = None


class ProductCreate(ProductBase):
    """Product creation schema."""

    module_id: str = Field(..., description="Module UUID")
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")


class ProductUpdate(BaseModel):
    """Product update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    name_zh: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    description_zh: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=100)
    category_id: Optional[str] = None
    risk_level: Optional[str] = Field(None, max_length=50)
    min_investment: Optional[Decimal] = None
    currency: Optional[str] = Field(None, max_length=3)
    expected_return: Optional[str] = Field(None, max_length=100)
    is_visible: Optional[bool] = None
    extra_data: Optional[dict] = None


class ProductResponse(ProductBase):
    """Product response schema."""

    id: str
    module_id: str
    tenant_id: Optional[str] = None
    code: str
    is_visible: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime

    # Joined fields from relationships
    module_code: Optional[str] = None
    module_name: Optional[str] = None
    category_name: Optional[str] = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class ProductVisibilityUpdate(BaseModel):
    """Schema for updating product visibility."""

    is_visible: bool


class ProductSummaryResponse(BaseModel):
    """Product summary for list views."""

    id: str
    code: str
    name: str
    name_zh: Optional[str] = None
    category: str
    risk_level: str
    min_investment: Decimal
    currency: str
    is_visible: bool
    is_default: bool
    module_code: Optional[str] = None
