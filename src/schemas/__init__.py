"""Pydantic schemas for request/response validation."""

from src.schemas.common import PaginationParams, PaginatedResponse
from src.schemas.auth import TokenResponse, LoginRequest
from src.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse
from src.schemas.user import UserCreate, UserUpdate, UserResponse
from src.schemas.client import ClientCreate, ClientUpdate, ClientResponse
from src.schemas.module import (
    ModuleCategory,
    ModuleCreate,
    ModuleUpdate,
    ModuleResponse,
    TenantModuleResponse,
    ModuleAccessRequest,
    ModuleAccessRequestResponse,
    ClientModuleResponse,
)
from src.schemas.client_auth import (
    ClientLoginRequest,
    ClientRegisterRequest,
    ClientTokenResponse,
    ClientRefreshRequest,
    ClientUserProfile,
    MessageResponse,
)
from src.schemas.client_portfolio import (
    PortfolioSummary,
    ClientAccountSummary,
    ClientAccountList,
    ClientAccountDetail,
    ClientHolding,
    ClientHoldingsList,
    ClientTransaction,
    ClientTransactionList,
    AllocationItem,
    AllocationBreakdown,
    PerformanceMetrics,
    PortfolioPerformance,
)
from src.schemas.product import (
    RiskLevel,
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductCategoryResponse,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductVisibilityUpdate,
    ProductSummaryResponse,
)
from src.schemas.notification import (
    NotificationCreate,
    NotificationUpdate,
    NotificationResponse,
    NotificationListResponse,
)

__all__ = [
    "PaginationParams",
    "PaginatedResponse",
    "TokenResponse",
    "LoginRequest",
    "TenantCreate",
    "TenantUpdate",
    "TenantResponse",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "ClientCreate",
    "ClientUpdate",
    "ClientResponse",
    "ModuleCategory",
    "ModuleCreate",
    "ModuleUpdate",
    "ModuleResponse",
    "TenantModuleResponse",
    "ModuleAccessRequest",
    "ModuleAccessRequestResponse",
    "ClientModuleResponse",
    # Client auth
    "ClientLoginRequest",
    "ClientRegisterRequest",
    "ClientTokenResponse",
    "ClientRefreshRequest",
    "ClientUserProfile",
    "MessageResponse",
    # Client portfolio
    "PortfolioSummary",
    "ClientAccountSummary",
    "ClientAccountList",
    "ClientAccountDetail",
    "ClientHolding",
    "ClientHoldingsList",
    "ClientTransaction",
    "ClientTransactionList",
    "AllocationItem",
    "AllocationBreakdown",
    "PerformanceMetrics",
    "PortfolioPerformance",
    # Product schemas
    "RiskLevel",
    "ProductCategoryCreate",
    "ProductCategoryUpdate",
    "ProductCategoryResponse",
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    "ProductVisibilityUpdate",
    "ProductSummaryResponse",
    # Notification
    "NotificationCreate",
    "NotificationUpdate",
    "NotificationResponse",
    "NotificationListResponse",
]

