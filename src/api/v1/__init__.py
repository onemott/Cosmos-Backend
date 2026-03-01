"""API v1 router."""

from fastapi import APIRouter

from src.api.v1 import auth, tenants, users, clients, accounts, holdings, transactions
from src.api.v1 import documents, tasks, modules, reports, stats, roles
from src.api.v1 import categories, products, invitations, client_users, audit_logs
from src.api.v1 import client_auth, client_portfolio, client_documents, client_tasks, client_products, client_notifications, client_agreements
from src.api.v1 import chat, client_chat, chat_ws
from src.api.v1 import system
from src.api.v1.admin import system as admin_system
from src.api.v1.admin import notifications as admin_notifications

router = APIRouter()

# Admin/Staff APIs
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(roles.router, prefix="/roles", tags=["Roles"])
router.include_router(clients.router, prefix="/clients", tags=["Clients"])
router.include_router(client_users.router, prefix="/client-users", tags=["Client Users"])
router.include_router(invitations.router, prefix="/invitations", tags=["Invitations"])
router.include_router(accounts.router, prefix="/accounts", tags=["Accounts"])
router.include_router(holdings.router, prefix="/holdings", tags=["Holdings"])
router.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
router.include_router(documents.router, prefix="/documents", tags=["Documents"])
router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
router.include_router(modules.router, prefix="/modules", tags=["Modules"])
router.include_router(categories.router, prefix="/categories", tags=["Categories"])
router.include_router(products.router, prefix="/products", tags=["Products"])
router.include_router(reports.router, prefix="/reports", tags=["Reports"])
router.include_router(stats.router, prefix="/stats", tags=["Statistics"])
router.include_router(audit_logs.router, prefix="/audit-logs", tags=["Audit Logs"])
router.include_router(chat.router, prefix="/chat", tags=["Chat (Admin)"])

# System APIs
router.include_router(system.router, prefix="/system", tags=["System"])
router.include_router(admin_system.router, prefix="/admin/system", tags=["Admin System"])
router.include_router(admin_notifications.router, prefix="/admin", tags=["Admin Notifications"])

# Client-Facing APIs (prefix already included in router)
router.include_router(client_auth.router)
router.include_router(client_portfolio.router)
router.include_router(client_documents.router)
router.include_router(client_tasks.router)
router.include_router(client_products.router)
router.include_router(client_notifications.router)
router.include_router(client_agreements.router, prefix="/client/agreements", tags=["Client Agreements"])
router.include_router(client_chat.router, prefix="/client/chat", tags=["Chat (Client)"])
router.include_router(chat_ws.router, tags=["Chat (WebSocket)"])
