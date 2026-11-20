"""Pagination helper for list endpoints (``?page=1&per_page=20``)."""
from flask import current_app, request

from ..extensions import db
from .errors import ValidationError


def _positive_int_arg(name, default):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError("Invalid pagination parameters", {name: "Must be a positive integer."}) from None
    if value < 1:
        raise ValidationError("Invalid pagination parameters", {name: "Must be a positive integer."})
    return value


def page_args():
    """Validated ``(page, per_page)`` from the query string."""
    page = _positive_int_arg("page", 1)
    per_page = min(
        _positive_int_arg("per_page", current_app.config["DEFAULT_PAGE_SIZE"]),
        current_app.config["MAX_PAGE_SIZE"],
    )
    return page, per_page


def paginate(statement, serializer=lambda obj: obj.to_dict()):
    page, per_page = page_args()
    result = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return {
        "items": [serializer(item) for item in result.items],
        "pagination": {
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        },
    }


def filter_choice_arg(name, choices):
    """Return a validated query-string filter value, or ``None`` when absent."""
    value = request.args.get(name)
    if value is None or value == "":
        return None
    if value not in choices:
        raise ValidationError(
            "Invalid filter value", {name: "Must be one of: " + ", ".join(choices) + "."}
        )
    return value


def int_arg(name):
    value = request.args.get(name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise ValidationError("Invalid filter value", {name: "Must be an integer."}) from None
