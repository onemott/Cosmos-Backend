import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional, Dict

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory
from src.models.audit_log import AuditLog


SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "ssn",
    "bank_account",
    "account_number",
    "routing_number",
}

SENSITIVE_SUBSTRINGS = {"password", "token", "secret", "key"}


def _mask_sensitive(data: Any) -> Any:
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            lower_key = key.lower()
            if key in SENSITIVE_KEYS or any(s in lower_key for s in SENSITIVE_SUBSTRINGS):
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive(value)
        return masked
    if isinstance(data, list):
        return [_mask_sensitive(item) for item in data]
    return data


def _hash_payload(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_request_context(request: Optional[Request]) -> Dict[str, Optional[str]]:
    if request is None:
        return {"ip_address": None, "user_agent": None, "request_id": None}
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


class AuditLogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_log(self, data: Dict[str, Any]) -> AuditLog:
        tenant_id = data.get("tenant_id")
        level = data.get("level") or "info"
        category = data.get("category") or "system"
        outcome = data.get("outcome") or "success"
        old_value = _mask_sensitive(jsonable_encoder(data.get("old_value")))
        new_value = _mask_sensitive(jsonable_encoder(data.get("new_value")))
        extra_data = _mask_sensitive(jsonable_encoder(data.get("extra_data")))

        prev_hash = None
        if tenant_id:
            prev_query = (
                select(AuditLog.event_hash)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(1)
            )
            prev_result = await self.session.execute(prev_query)
            prev_hash = prev_result.scalar_one_or_none()

        payload_for_hash = {
            "tenant_id": tenant_id,
            "event_type": data.get("event_type"),
            "level": level,
            "category": category,
            "resource_type": data.get("resource_type"),
            "resource_id": data.get("resource_id"),
            "action": data.get("action"),
            "outcome": outcome,
            "user_id": data.get("user_id"),
            "user_email": data.get("user_email"),
            "ip_address": data.get("ip_address"),
            "user_agent": data.get("user_agent"),
            "request_id": data.get("request_id"),
            "old_value": old_value,
            "new_value": new_value,
            "extra_data": extra_data,
            "tags": data.get("tags"),
            "prev_hash": prev_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        event_hash = _hash_payload(payload_for_hash)

        log = AuditLog(
            tenant_id=tenant_id,
            event_type=data.get("event_type"),
            level=level,
            category=category,
            resource_type=data.get("resource_type"),
            resource_id=data.get("resource_id"),
            action=data.get("action"),
            outcome=outcome,
            user_id=data.get("user_id"),
            user_email=data.get("user_email"),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            request_id=data.get("request_id"),
            old_value=old_value,
            new_value=new_value,
            extra_data=extra_data,
            tags=data.get("tags"),
            event_hash=event_hash,
            prev_hash=prev_hash,
        )
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log

    @classmethod
    async def create_with_new_session(cls, data: Dict[str, Any]) -> None:
        async with async_session_factory() as session:
            service = cls(session)
            await service.create_log(data)
            await session.commit()


def enqueue_audit_log(data: Dict[str, Any]) -> None:
    asyncio.create_task(AuditLogService.create_with_new_session(data))
