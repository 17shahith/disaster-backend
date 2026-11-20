"""Shared fixtures. Every test runs against its own fresh SQLite database file."""
import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.constants import Role
from app.extensions import db
from app.services.user_service import SYSTEM, create_user

PASSWORD = "Password123"

ROLE_USERS = {
    "admin": Role.ADMIN,
    "operator": Role.OPERATOR,
    "lead": Role.TEAM_LEAD,
    "lead2": Role.TEAM_LEAD,
    "coordinator": Role.COORDINATOR,
}


@pytest.fixture
def app(tmp_path):
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}"})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def users(app):
    return {
        key: create_user(
            {"username": key, "email": f"{key}@test.local", "full_name": f"Test {key.title()}",
             "password": PASSWORD, "role": role},
            actor=SYSTEM,
        )
        for key, role in ROLE_USERS.items()
    }


@pytest.fixture
def headers(users):
    tokens = {key: create_access_token(identity=user) for key, user in users.items()}

    def _headers(key):
        return {"Authorization": f"Bearer {tokens[key]}"}

    return _headers


class Api:
    """Small helper for building test fixtures through the public API."""

    def __init__(self, client, headers):
        self.client = client
        self.h = headers

    def _post(self, url, role, payload):
        resp = self.client.post(url, json=payload, headers=self.h(role))
        assert resp.status_code == 201, resp.get_json()
        return resp.get_json()["data"]

    def put(self, url, role, payload):
        return self.client.put(url, json=payload, headers=self.h(role))

    def incident(self, **overrides):
        payload = {"title": "Test Flood", "incident_type": "Flood", "description": "River overflow",
                   "location": "Ward 1", "severity": "High", **overrides}
        return self._post("/api/incidents", "operator", payload)

    def request(self, incident_id, **overrides):
        payload = {"incident_id": incident_id, "category": "Rescue", "description": "People stranded",
                   "priority": "High", **overrides}
        return self._post("/api/requests", "operator", payload)

    def team(self, name="Alpha Team", lead="lead", **overrides):
        payload = {"name": name, "team_type": "Rescue", "member_count": 5, **overrides}
        return self._post("/api/teams", lead, payload)

    def shelter(self, name="Hall A", capacity=100, **overrides):
        payload = {"name": name, "location": "Ward 2", "capacity": capacity, **overrides}
        return self._post("/api/shelters", "coordinator", payload)

    def supply(self, name="Bottled Water", quantity=1000, **overrides):
        payload = {"name": name, "category": "Drinking Water", "unit": "litres", "quantity": quantity,
                   "low_stock_threshold": 50, **overrides}
        return self._post("/api/supplies", "coordinator", payload)

    def allocation(self, role="coordinator", **payload):
        return self._post("/api/allocations", role, payload)

    def approved_allocation(self, **payload):
        alloc = self.allocation(**payload)
        resp = self.put(f"/api/allocations/{alloc['id']}", "coordinator", {"status": "Approved"})
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["data"]

    def dispatch(self, allocation_id, **overrides):
        return self._post("/api/dispatch", "coordinator", {"allocation_id": allocation_id, **overrides})

    def advance_dispatch(self, dispatch_id, *statuses, role="coordinator"):
        resp = None
        for status in statuses:
            resp = self.put(f"/api/dispatch/{dispatch_id}", role, {"status": status})
            assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["data"]

    def get(self, url, role="admin"):
        resp = self.client.get(url, headers=self.h(role))
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["data"]


@pytest.fixture
def api(client, headers):
    return Api(client, headers)
