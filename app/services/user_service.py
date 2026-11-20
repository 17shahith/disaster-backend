"""User accounts, authentication and token revocation."""
from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from ..constants import Role
from ..extensions import db
from ..models import TokenBlocklist, User
from ..utils.errors import ConflictError, ForbiddenError, UnauthorizedError, ValidationError
from ..utils.time import utcnow
from ..utils.validators import validate_password_strength
from .activity_service import log_activity
from .common import apply_changes, atomic


class SystemActor:
    """Actor used by trusted internal tooling (CLI bootstrap, seeding) before any admin exists."""

    id = None
    role = Role.ADMIN
    is_admin = True


SYSTEM = SystemActor()


def _ensure_unique(username=None, email=None, exclude_id=None):
    errors = {}
    if username is not None:
        stmt = select(User.id).where(func.lower(User.username) == username.lower())
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        if db.session.execute(stmt).first():
            errors["username"] = "Username is already taken."
    if email is not None:
        stmt = select(User.id).where(func.lower(User.email) == email.lower())
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        if db.session.execute(stmt).first():
            errors["email"] = "Email is already registered."
    if errors:
        raise ConflictError("User already exists", errors)


def _check_password(password):
    problem = validate_password_strength(password)
    if problem:
        raise ValidationError("Password does not meet requirements", {"password": problem})


def create_user(data, actor=None):
    """Create a user. Without an admin ``actor`` (public registration) the admin role is refused."""
    role = data.get("role") or Role.OPERATOR
    if role == Role.ADMIN and not (actor and actor.is_admin):
        raise ForbiddenError(
            "Administrator accounts can only be created by an administrator",
            {"role": "Self-registration is allowed for: " + ", ".join(Role.SELF_REGISTERABLE)},
        )
    _check_password(data["password"])
    _ensure_unique(data["username"], data["email"])

    with atomic():
        user = User(
            username=data["username"],
            email=data["email"].lower(),
            full_name=data["full_name"],
            phone=data.get("phone"),
            role=role,
            is_active=data.get("is_active", True),
        )
        user.set_password(data["password"])
        db.session.add(user)
        db.session.flush()
        log_activity(
            user if actor in (None, SYSTEM) else actor,
            "USER_REGISTERED" if actor is None else "USER_CREATED",
            "user",
            user.id,
            f"User '{user.username}' created with role {user.role}",
            {"role": user.role},
        )
    return user


def authenticate(identifier, password):
    user = db.session.execute(
        select(User).where(
            or_(func.lower(User.username) == identifier.lower(), func.lower(User.email) == identifier.lower())
        )
    ).scalar_one_or_none()
    if user is None or not user.check_password(password):
        raise UnauthorizedError("Invalid username or password", {"credentials": "Invalid credentials"})
    if not user.is_active:
        raise ForbiddenError("This account has been deactivated. Contact an administrator.")
    with atomic():
        user.last_login_at = utcnow()
        log_activity(user, "USER_LOGIN", "user", user.id, f"User '{user.username}' logged in")
    return user


def revoke_token(jwt_payload, user):
    expires = jwt_payload.get("exp")
    with atomic():
        db.session.add(
            TokenBlocklist(
                jti=jwt_payload["jti"],
                token_type=jwt_payload.get("type", "access"),
                user_id=user.id,
                expires_at=(
                    datetime.fromtimestamp(expires, tz=timezone.utc).replace(tzinfo=None) if expires else None
                ),
            )
        )
        log_activity(user, "USER_LOGOUT", "user", user.id, f"User '{user.username}' logged out")


def update_profile(user, data):
    password = data.pop("password", None)
    current_password = data.pop("current_password", None)
    if "email" in data:
        data["email"] = data["email"].lower()
        _ensure_unique(email=data["email"], exclude_id=user.id)
    with atomic():
        changes = apply_changes(user, data, fields=("full_name", "email", "phone"))
        if password:
            if not current_password or not user.check_password(current_password):
                raise ValidationError(
                    "Current password is incorrect", {"current_password": "Required to change password."}
                )
            _check_password(password)
            user.set_password(password)
            changes["password"] = "changed"
        log_activity(user, "PROFILE_UPDATED", "user", user.id, "Profile updated", {"changes": list(changes)})
    return user


def admin_update_user(user, data, actor):
    if user.id == actor.id and (data.get("role", Role.ADMIN) != Role.ADMIN or data.get("is_active") is False):
        raise ConflictError("Administrators cannot demote or deactivate their own account")
    password = data.pop("password", None)
    if "email" in data:
        data["email"] = data["email"].lower()
        _ensure_unique(email=data["email"], exclude_id=user.id)
    if "username" in data:
        _ensure_unique(username=data["username"], exclude_id=user.id)
    with atomic():
        changes = apply_changes(user, data, fields=("username", "full_name", "email", "phone", "role", "is_active"))
        if password:
            _check_password(password)
            user.set_password(password)
            changes["password"] = "reset"
        action = "USER_ROLE_CHANGED" if "role" in changes else "USER_UPDATED"
        log_activity(actor, action, "user", user.id, f"User '{user.username}' updated by administrator", {"changes": changes})
    return user


def deactivate_user(user, actor):
    if user.id == actor.id:
        raise ConflictError("Administrators cannot deactivate their own account")
    with atomic():
        user.is_active = False
        log_activity(actor, "USER_DEACTIVATED", "user", user.id, f"User '{user.username}' deactivated")
    return user
