"""Authentication: register, login, profile, token refresh and logout."""
from flask import Blueprint
from flask_jwt_extended import create_access_token, create_refresh_token, current_user, get_jwt, jwt_required

from ..constants import Role
from ..middleware import authenticated
from ..services import user_service
from ..utils.responses import success_response
from ..utils.validators import EMAIL_RE, PHONE_RE, USERNAME_RE, Field, get_json_body, validate

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

REGISTER_SCHEMA = {
    "username": Field(str, required=True, pattern=USERNAME_RE,
                      pattern_message="3-80 characters: letters, numbers, '.', '_' or '-'."),
    "email": Field(str, required=True, max_length=120, pattern=EMAIL_RE, pattern_message="Invalid email address."),
    "full_name": Field(str, required=True, min_length=2, max_length=120),
    "password": Field(str, required=True, max_length=128),
    "phone": Field(str, nullable=True, pattern=PHONE_RE, pattern_message="Invalid phone number."),
    "role": Field(str, choices=Role.ALL, default=Role.OPERATOR),
}

LOGIN_SCHEMA = {
    "username": Field(str, required=True, max_length=120),
    "password": Field(str, required=True, max_length=128),
}

PROFILE_SCHEMA = {
    "full_name": Field(str, min_length=2, max_length=120),
    "email": Field(str, max_length=120, pattern=EMAIL_RE, pattern_message="Invalid email address."),
    "phone": Field(str, nullable=True, pattern=PHONE_RE, pattern_message="Invalid phone number."),
    "password": Field(str, max_length=128),
    "current_password": Field(str, max_length=128),
}


def _token_payload(user):
    return {
        "access_token": create_access_token(identity=user),
        "refresh_token": create_refresh_token(identity=user),
        "token_type": "Bearer",
        "user": user.to_dict(),
    }


@bp.post("/register")
def register():
    data = validate(get_json_body(), REGISTER_SCHEMA, message="Invalid registration information")
    user = user_service.create_user(data)
    return success_response(user.to_dict(), "User registered successfully", 201)


@bp.post("/login")
def login():
    payload = get_json_body()
    if isinstance(payload, dict) and "username" not in payload and "email" in payload:
        payload = {**payload, "username": payload["email"]}
    data = validate(payload, LOGIN_SCHEMA, message="Username and password are required")
    user = user_service.authenticate(data["username"], data["password"])
    return success_response(_token_payload(user), "Login successful")


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    return success_response(
        {"access_token": create_access_token(identity=current_user), "token_type": "Bearer"},
        "Token refreshed",
    )


@bp.get("/profile")
@authenticated
def profile():
    return success_response(current_user.to_dict(), "Profile retrieved successfully")


@bp.put("/profile")
@authenticated
def update_profile():
    data = validate(get_json_body(), PROFILE_SCHEMA, partial=True, message="Invalid profile information")
    user = user_service.update_profile(current_user, data)
    return success_response(user.to_dict(), "Profile updated successfully")


@bp.post("/logout")
@jwt_required(verify_type=False)
def logout():
    user_service.revoke_token(get_jwt(), current_user)
    return success_response({}, "Logged out successfully; token revoked")
