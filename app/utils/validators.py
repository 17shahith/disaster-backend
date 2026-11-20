"""Lightweight declarative request validation.

Example::

    SCHEMA = {
        "title": Field(str, required=True, max_length=200),
        "severity": Field(str, choices=SEVERITIES, default="Medium"),
    }
    data = validate(get_json_body(), SCHEMA)               # create
    data = validate(get_json_body(), SCHEMA, partial=True)  # update

``validate`` returns only known, cleaned fields and raises ``ValidationError``
with a per-field ``errors`` dict when anything is invalid.
"""
import re
from datetime import datetime

from flask import request

from .errors import ValidationError

_MISSING = object()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,80}$")
PHONE_RE = re.compile(r"^[0-9+()\-\s]{6,30}$")


class Field:
    def __init__(
        self,
        type_=str,
        required=False,
        nullable=False,
        choices=None,
        min_value=None,
        max_value=None,
        min_length=None,
        max_length=None,
        pattern=None,
        pattern_message=None,
        default=_MISSING,
    ):
        self.type_ = type_
        self.required = required
        self.nullable = nullable
        self.choices = choices
        self.min_value = min_value
        self.max_value = max_value
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = re.compile(pattern) if isinstance(pattern, str) else pattern
        self.pattern_message = pattern_message
        self.default = default

    def clean(self, value):
        """Return the cleaned value or raise ``ValueError`` with a message."""
        if value is None:
            if self.nullable:
                return None
            raise ValueError("This field cannot be null.")

        if self.type_ is str:
            if not isinstance(value, str):
                raise ValueError("Must be a string.")
            value = value.strip()
            if value == "":
                if self.nullable:
                    return None
                raise ValueError("This field cannot be blank.")
            if self.min_length is not None and len(value) < self.min_length:
                raise ValueError(f"Must be at least {self.min_length} characters.")
            if self.max_length is not None and len(value) > self.max_length:
                raise ValueError(f"Must be at most {self.max_length} characters.")
            if self.pattern is not None and not self.pattern.match(value):
                raise ValueError(self.pattern_message or "Invalid format.")
        elif self.type_ is int:
            if isinstance(value, bool):
                raise ValueError("Must be an integer.")
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            elif isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
                value = int(value.strip())
            if not isinstance(value, int):
                raise ValueError("Must be an integer.")
        elif self.type_ is float:
            if isinstance(value, bool):
                raise ValueError("Must be a number.")
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError("Must be a number.") from None
        elif self.type_ is bool:
            if not isinstance(value, bool):
                raise ValueError("Must be true or false.")
        elif self.type_ is datetime:
            if not isinstance(value, str):
                raise ValueError("Must be an ISO-8601 datetime string.")
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("Must be an ISO-8601 datetime string.") from None
            if parsed.tzinfo is not None:
                from .time import isoformat  # local import avoids cycles

                parsed = datetime.fromisoformat(isoformat(parsed)[:-1])
            value = parsed

        if self.choices is not None and value not in self.choices:
            raise ValueError("Must be one of: " + ", ".join(str(c) for c in self.choices) + ".")
        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"Must be greater than or equal to {self.min_value}.")
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"Must be less than or equal to {self.max_value}.")
        return value


def validate(payload, schema, partial=False, message="Invalid input data"):
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")

    cleaned, errors = {}, {}
    for name, field in schema.items():
        if name not in payload:
            if partial:
                continue
            if field.required:
                errors[name] = "This field is required."
            elif field.default is not _MISSING:
                cleaned[name] = field.default() if callable(field.default) else field.default
            continue
        try:
            cleaned[name] = field.clean(payload[name])
        except ValueError as exc:
            errors[name] = str(exc)

    if errors:
        raise ValidationError(message, errors)
    if partial and not cleaned:
        raise ValidationError("No valid fields provided for update", {
            "fields": "Allowed fields: " + ", ".join(schema.keys())
        })
    return cleaned


def get_json_body():
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("Request body must be valid JSON")
    return payload


def validate_password_strength(password):
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None
