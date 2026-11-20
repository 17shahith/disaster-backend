"""Administrator-only user management and system activity monitoring."""
from flask import Blueprint, request
from flask_jwt_extended import current_user
from sqlalchemy import or_, select

from ..constants import Role
from ..middleware import role_required
from ..models import ActivityLog, User
from ..services import user_service
from ..services.common import get_or_404
from ..utils.pagination import filter_choice_arg, int_arg, paginate
from ..utils.responses import success_response
from ..utils.validators import EMAIL_RE, PHONE_RE, USERNAME_RE, Field, get_json_body, validate
from .auth import REGISTER_SCHEMA

bp = Blueprint("users", __name__, url_prefix="/api")

UPDATE_SCHEMA = {
    "username": Field(str, pattern=USERNAME_RE, pattern_message="3-80 characters: letters, numbers, '.', '_' or '-'."),
    "email": Field(str, max_length=120, pattern=EMAIL_RE, pattern_message="Invalid email address."),
    "full_name": Field(str, min_length=2, max_length=120),
    "phone": Field(str, nullable=True, pattern=PHONE_RE, pattern_message="Invalid phone number."),
    "role": Field(str, choices=Role.ALL),
    "is_active": Field(bool),
    "password": Field(str, max_length=128),
}


@bp.get("/users")
@role_required(Role.ADMIN)
def list_users():
    stmt = select(User).order_by(User.id)
    role = filter_choice_arg("role", Role.ALL)
    if role:
        stmt = stmt.where(User.role == role)
    active = request.args.get("is_active")
    if active in ("true", "false"):
        stmt = stmt.where(User.is_active == (active == "true"))
    search = request.args.get("search")
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.full_name.ilike(like), User.email.ilike(like)))
    return success_response(paginate(stmt), "Users retrieved successfully")


@bp.post("/users")
@role_required(Role.ADMIN)
def create_user():
    schema = {**REGISTER_SCHEMA, "is_active": Field(bool, default=True)}
    data = validate(get_json_body(), schema, message="Invalid user information")
    user = user_service.create_user(data, actor=current_user)
    return success_response(user.to_dict(), "User created successfully", 201)


@bp.get("/users/<int:user_id>")
@role_required(Role.ADMIN)
def get_user(user_id):
    return success_response(get_or_404(User, user_id, "User").to_dict(), "User retrieved successfully")


@bp.put("/users/<int:user_id>")
@role_required(Role.ADMIN)
def update_user(user_id):
    user = get_or_404(User, user_id, "User")
    data = validate(get_json_body(), UPDATE_SCHEMA, partial=True, message="Invalid user information")
    user = user_service.admin_update_user(user, data, current_user)
    return success_response(user.to_dict(), "User updated successfully")


@bp.delete("/users/<int:user_id>")
@role_required(Role.ADMIN)
def deactivate_user(user_id):
    user = get_or_404(User, user_id, "User")
    user = user_service.deactivate_user(user, current_user)
    return success_response(user.to_dict(), "User deactivated successfully")


@bp.get("/activity-logs")
@role_required(Role.ADMIN)
def list_activity_logs():
    stmt = select(ActivityLog).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    for arg, column in (("entity_type", ActivityLog.entity_type), ("action", ActivityLog.action)):
        value = request.args.get(arg)
        if value:
            stmt = stmt.where(column == value)
    for arg, column in (("user_id", ActivityLog.user_id), ("entity_id", ActivityLog.entity_id)):
        value = int_arg(arg)
        if value is not None:
            stmt = stmt.where(column == value)
    return success_response(paginate(stmt), "Activity logs retrieved successfully")
