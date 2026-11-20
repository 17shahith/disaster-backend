"""Disaster Response Resource Coordinator - Flask application factory."""
import logging
import os

from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import get_config
from .extensions import cors, db, jwt, migrate
from .utils.responses import success_response


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite ignores foreign keys unless enabled per connection."""
    module = type(dbapi_connection).__module__
    if "sqlite" in module:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(config_name=None, config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    if config_overrides:
        app.config.update(config_overrides)
    app.json.sort_keys = False
    os.makedirs(app.instance_path, exist_ok=True)

    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    from . import models  # noqa: F401  (register models with SQLAlchemy metadata)
    from .cli import register_cli
    from .middleware.auth import register_jwt_callbacks
    from .middleware.error_handlers import register_error_handlers
    from .routes import register_blueprints

    register_jwt_callbacks()
    register_error_handlers(app)
    register_blueprints(app)
    register_cli(app)

    @app.get("/api/health")
    def health():
        return success_response({"status": "ok"}, "Service is healthy")

    return app
