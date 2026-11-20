"""Helpers shared by services."""
from contextlib import contextmanager
from datetime import datetime

from ..extensions import db
from ..utils.errors import NotFoundError
from ..utils.time import isoformat


def get_or_404(model, obj_id, label):
    obj = db.session.get(model, obj_id) if obj_id is not None else None
    if obj is None:
        raise NotFoundError(f"{label} not found", {"id": f"No {label.lower()} exists with id {obj_id}"})
    return obj


@contextmanager
def atomic():
    """Run a block as one database transaction: commit on success, roll back on any error."""
    try:
        yield
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _json_safe(value):
    return isoformat(value) if isinstance(value, datetime) else value


def apply_changes(obj, data, fields=None):
    """Set attributes from ``data`` and return ``{field: {"from": old, "to": new}}`` for real changes."""
    changes = {}
    for key, value in data.items():
        if fields is not None and key not in fields:
            continue
        old = getattr(obj, key)
        if old != value:
            setattr(obj, key, value)
            changes[key] = {"from": _json_safe(old), "to": _json_safe(value)}
    return changes
