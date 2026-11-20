"""Consistent JSON response envelopes."""
from flask import jsonify


def success_response(data=None, message="Success", status_code=200):
    return (
        jsonify({"success": True, "message": message, "data": data if data is not None else {}}),
        status_code,
    )


def error_response(message, status_code=400, errors=None):
    return (
        jsonify({"success": False, "message": message, "errors": errors or {}}),
        status_code,
    )
