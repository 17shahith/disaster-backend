"""Shared model helpers."""
from sqlalchemy import CheckConstraint

from ..extensions import db
from ..utils.time import utcnow


def in_check(column, values, name):
    """CHECK constraint restricting ``column`` to a fixed vocabulary."""
    quoted = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
