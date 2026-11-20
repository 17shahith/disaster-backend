"""Application configuration classes.

All sensitive values are read from environment variables (see ``.env.example``).
"""
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

_DEV_SECRET = "dev-only-secret-change-me"


def _int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _csv_env(name, default):
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", _DEV_SECRET)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", _DEV_SECRET + "-jwt")

    # Relative SQLite paths are resolved by Flask-SQLAlchemy against the
    # Flask instance folder (``instance/``), which is mounted as a Docker volume.
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///disaster_response.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Wait for SQLite write locks instead of failing immediately under concurrent requests.
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 15}}

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_int_env("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 60))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_int_env("JWT_REFRESH_TOKEN_EXPIRES_DAYS", 7))
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_ERROR_MESSAGE_KEY = "message"

    CORS_ORIGINS = _csv_env("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")

    PASSWORD_HASH_METHOD = "scrypt"

    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # Password used for demo accounts created by ``flask seed``.
    SEED_DEFAULT_PASSWORD = os.getenv("SEED_DEFAULT_PASSWORD", "Password@123")

    JSON_SORT_KEYS = False
    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    # Each test gets its own database file; conftest overrides this URI.
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///test_disaster_response.db")
    JWT_SECRET_KEY = "test-jwt-secret-key-with-sufficient-length"
    SECRET_KEY = "test-secret-key"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    # Cheaper hashing keeps the suite fast; production uses Werkzeug's scrypt default.
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"


class ProductionConfig(Config):
    @classmethod
    def validate(cls):
        def insecure(value):
            return not value or value.startswith(_DEV_SECRET) or "change-me" in value or len(value) < 32

        missing = [name for name in ("SECRET_KEY", "JWT_SECRET_KEY") if insecure(os.getenv(name, ""))]
        if missing:
            raise RuntimeError(
                "Production requires strong secrets (32+ random characters) for: " + ", ".join(missing)
            )


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    name = (name or os.getenv("FLASK_ENV") or os.getenv("APP_ENV") or "development").lower()
    config_class = CONFIG_BY_NAME.get(name, DevelopmentConfig)
    if config_class is ProductionConfig:
        ProductionConfig.validate()
    return config_class
