from datetime import datetime, timezone
import json
from typing import Any, Optional
from uuid import uuid4

from sqlmodel import Session

from backend.models.models import AuditLog


def log_audit_event(
    session: Session,
    entity_name: str,
    record_id: str,
    action: str,
    actor_role: str,
    actor_name: str,
    old_values: Optional[Any] = None,
    new_values: Optional[Any] = None,
    reason: Optional[str] = None,
    commit: bool = False
) -> AuditLog:
    """
    Persist state changes as explicit audit log events without overwriting history.
    """
    old_str = json.dumps(old_values, default=str) if isinstance(old_values, (dict, list)) else (str(old_values) if old_values is not None else None)
    new_str = json.dumps(new_values, default=str) if isinstance(new_values, (dict, list)) else (str(new_values) if new_values is not None else None)

    log_entry = AuditLog(
        log_id=f"AUD-{uuid4().hex[:10].upper()}",
        entity_name=entity_name,
        record_id=str(record_id),
        action=action.upper(),
        actor_role=actor_role.upper(),
        actor_name=actor_name,
        old_values=old_str,
        new_values=new_str,
        reason=reason,
        timestamp=datetime.now(timezone.utc)
    )

    session.add(log_entry)
    if commit:
        session.commit()
        session.refresh(log_entry)

    return log_entry

