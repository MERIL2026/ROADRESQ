import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

# Sensitive keys that must NEVER be stored in audit records
REDACTED_KEYS = {
    "password",
    "password_hash",
    "otp",
    "code",
    "token",
    "access_token",
    "refresh_token",
    "jwt_secret",
}


def _sanitize_payload(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Removes sensitive keys from audit log dictionaries recursively."""
    if not data:
        return None
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        if k.lower() in REDACTED_KEYS:
            continue
        if isinstance(v, dict):
            sanitized[k] = _sanitize_payload(v)
        elif isinstance(v, uuid.UUID):
            sanitized[k] = str(v)
        else:
            sanitized[k] = v
    return sanitized


async def record_audit_event(  # noqa: PLR0913
    session: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """
    Persists an immutable audit log record.
    Guarantees secrets and raw credentials are never persisted.
    """
    safe_old = _sanitize_payload(old_data)
    safe_new = _sanitize_payload(new_data)

    log_entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_data=safe_old,
        new_data=safe_new,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(log_entry)
    await session.flush()
    return log_entry
