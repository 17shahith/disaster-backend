"""Global error handlers: every error leaves the API in the standard envelope.

Internal details (stack traces, SQL) are logged, never returned to clients.
"""
from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from ..extensions import db
from ..utils.errors import APIError
from ..utils.responses import error_response

_HTTP_MESSAGES = {
    400: "Bad request",
    401: "Authentication required",
    403: "Forbidden",
    404: "Resource not found",
    405: "Method not allowed",
    409: "Conflict",
    413: "Request payload too large",
    415: "Unsupported media type",
    429: "Too many requests",
}


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(exc):
        db.session.rollback()
        return error_response(exc.message, exc.status_code, exc.errors)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        message = _HTTP_MESSAGES.get(exc.code, exc.name)
        return error_response(message, exc.code or 500)

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(exc):
        db.session.rollback()
        current_app.logger.warning("Integrity error: %s", exc.orig)
        return error_response(
            "The operation violates a data integrity rule (duplicate or invalid reference)",
            409,
            {"database": "Constraint violation"},
        )

    @app.errorhandler(SQLAlchemyError)
    def handle_db_error(exc):
        db.session.rollback()
        current_app.logger.exception("Database error")
        return error_response("A database error occurred", 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        db.session.rollback()
        current_app.logger.exception("Unhandled exception")
        return error_response("An unexpected internal error occurred", 500)
