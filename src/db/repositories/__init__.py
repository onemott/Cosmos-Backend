"""Repository layer for data access."""

from src.db.repositories.base import BaseRepository
from src.db.repositories.tenant_repo import TenantRepository
from src.db.repositories.user_repo import UserRepository, RoleRepository
from src.db.repositories.client_repo import ClientRepository, ClientGroupRepository
from src.db.repositories.product_repo import ProductRepository, ProductCategoryRepository

__all__ = [
    "BaseRepository",
    "TenantRepository",
    "UserRepository",
    "RoleRepository",
    "ClientRepository",
    "ClientGroupRepository",
    "ProductRepository",
    "ProductCategoryRepository",
]
