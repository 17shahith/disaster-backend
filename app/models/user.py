from flask import current_app, has_app_context
from werkzeug.security import check_password_hash, generate_password_hash

from ..constants import Role
from ..extensions import db
from ..utils.time import isoformat, utcnow
from .base import TimestampMixin, in_check


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (in_check("role", Role.ALL, "valid_role"),)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(40), nullable=False, default=Role.OPERATOR)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)

    def set_password(self, password):
        method = current_app.config.get("PASSWORD_HASH_METHOD", "scrypt") if has_app_context() else "scrypt"
        self.password_hash = generate_password_hash(password, method=method)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "phone": self.phone,
            "role": self.role,
            "is_active": self.is_active,
            "last_login_at": isoformat(self.last_login_at),
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }

    def to_summary(self):
        return {"id": self.id, "username": self.username, "full_name": self.full_name}


class TokenBlocklist(db.Model):
    """Revoked JWTs (logout). Checked on every authenticated request."""

    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), nullable=False, unique=True, index=True)
    token_type = db.Column(db.String(10), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime)
