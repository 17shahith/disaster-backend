"""Activity (audit) logging. Entries join the caller's transaction and commit with it."""
from flask import has_request_context, request

from ..extensions import db
from ..models import ActivityLog


def log_activity(actor, action, entity_type, entity_id, description, details=None):
    entry = ActivityLog(
        user_id=getattr(actor, "id", None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description[:500],
        details=details or {},
        ip_address=request.remote_addr if has_request_context() else None,
    )
    db.session.add(entry)
    return entry
