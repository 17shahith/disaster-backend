"""MongoDB document store, used alongside SQLite.

SQLite (via SQLAlchemy) remains the system of record for incidents, teams, stock,
allocations and dispatches, where relational integrity rules matter. MongoDB holds
document-shaped data that has no relational constraints: saved situation-report
snapshots.

MongoDB is optional. Without ``MONGO_URI`` (or if the server is unreachable) only the
features that need it answer 503; the rest of the API is unaffected.
"""
from flask import current_app
from pymongo import DESCENDING, MongoClient
from pymongo.errors import PyMongoError

from .utils.errors import APIError

DEFAULT_DB_NAME = "disaster_response"


class ServiceUnavailableError(APIError):
    status_code = 503
    default_message = "The document store (MongoDB) is not available"


def init_mongo(app):
    uri = app.config.get("MONGO_URI")
    state = {"client": None, "db": None, "indexes_ready": False}
    if uri:
        if uri.startswith("mongomock://"):  # in-memory fake used by the test suite
            import mongomock

            client = mongomock.MongoClient()
        else:
            # Connects lazily: app start-up never blocks on MongoDB.
            client = MongoClient(uri, serverSelectionTimeoutMS=app.config.get("MONGO_TIMEOUT_MS", 3000))
        state["client"] = client
        db_name = app.config.get("MONGO_DB_NAME") or _db_name_from_uri(uri) or DEFAULT_DB_NAME
        state["db"] = client[db_name]
    app.extensions["mongo"] = state


def _db_name_from_uri(uri):
    path = uri.split("://", 1)[-1].split("/", 1)
    if len(path) < 2:
        return None
    return path[1].split("?", 1)[0] or None


def _ensure_indexes(db):
    db.situation_reports.create_index([("created_at", DESCENDING)])


def get_db():
    """Return the MongoDB database or raise a 503 if MongoDB is disabled/unreachable."""
    state = current_app.extensions.get("mongo") or {}
    db = state.get("db")
    if db is None:
        raise ServiceUnavailableError(
            "Situation-report snapshots need MongoDB, which is not configured",
            {"mongodb": "Set MONGO_URI (e.g. mongodb://localhost:27017/disaster_response)"},
        )
    if not state["indexes_ready"]:
        try:
            _ensure_indexes(db)
        except PyMongoError:
            current_app.logger.warning("MongoDB unreachable", exc_info=True)
            raise ServiceUnavailableError(
                "The document store (MongoDB) is not reachable",
                {"mongodb": "Check that the MongoDB server is running"},
            ) from None
        state["indexes_ready"] = True
    return db


def mongo_status():
    """'ok', 'unavailable' or 'disabled' (for the health endpoint)."""
    state = current_app.extensions.get("mongo") or {}
    if state.get("client") is None:
        return "disabled"
    try:
        state["client"].admin.command("ping")
        return "ok"
    except PyMongoError:
        return "unavailable"
