"""Authentication / role-based authorisation.

The user's role is always read from the database (via ``current_user``), never
trusted from the token, so role changes and deactivation take effect immediately.
"""
from functools import wraps

from flask_jwt_extended import current_user, jwt_required

from ..constants import Role
from ..extensions import db, jwt
from ..models import TokenBlocklist, User
from ..utils.errors import ForbiddenError
from ..utils.responses import error_response


def role_required(*roles):
    """Require a valid access token and (optionally) one of ``roles``.

    Administrators can access every module and always pass.
    """

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            if roles and current_user.role != Role.ADMIN and current_user.role not in roles:
                raise ForbiddenError(
                    "You do not have permission to perform this action",
                    {"required_roles": list(roles), "your_role": current_user.role},
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def authenticated(fn):
    """Any active, authenticated user."""
    return role_required()(fn)


def register_jwt_callbacks():
    @jwt.user_identity_loader
    def user_identity_lookup(user):
        return str(user.id) if isinstance(user, User) else str(user)

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        try:
            user_id = int(jwt_data["sub"])
        except (KeyError, TypeError, ValueError):
            return None
        user = db.session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(_jwt_header, jwt_payload):
        jti = jwt_payload.get("jti")
        return db.session.query(TokenBlocklist.id).filter_by(jti=jti).scalar() is not None

    @jwt.additional_claims_loader
    def add_claims(user):
        return {"role": user.role} if isinstance(user, User) else {}

    @jwt.unauthorized_loader
    def missing_token(reason):
        return error_response("Authorization token is missing", 401, {"token": reason})

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return error_response("Invalid authorization token", 401, {"token": reason})

    @jwt.expired_token_loader
    def expired_token(_jwt_header, _jwt_payload):
        return error_response("Authorization token has expired", 401, {"token": "Token expired"})

    @jwt.revoked_token_loader
    def revoked_token(_jwt_header, _jwt_payload):
        return error_response("Authorization token has been revoked", 401, {"token": "Token revoked"})

    @jwt.user_lookup_error_loader
    def user_lookup_error(_jwt_header, _jwt_payload):
        return error_response("User account not found or inactive", 401, {"token": "Unknown user"})

    @jwt.needs_fresh_token_loader
    def needs_fresh(_jwt_header, _jwt_payload):
        return error_response("Fresh authorization token required", 401)
