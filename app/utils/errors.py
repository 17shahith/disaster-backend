"""Exceptions raised by services and routes; converted to JSON by error handlers."""


class APIError(Exception):
    status_code = 400
    default_message = "Request could not be processed"

    def __init__(self, message=None, errors=None, status_code=None):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.errors = errors or {}
        if status_code is not None:
            self.status_code = status_code


class ValidationError(APIError):
    status_code = 400
    default_message = "Invalid input"


class UnauthorizedError(APIError):
    status_code = 401
    default_message = "Authentication required"


class ForbiddenError(APIError):
    status_code = 403
    default_message = "You do not have permission to perform this action"


class NotFoundError(APIError):
    status_code = 404
    default_message = "Resource not found"


class ConflictError(APIError):
    status_code = 409
    default_message = "Request conflicts with the current state of the resource"
