"""Situation-report snapshots stored in MongoDB (mongomock in tests)."""
import pytest

from app import create_app
from app.extensions import db
from app.models import ActivityLog


def _save(api, role="operator", **payload):
    body = {"title": "Morning briefing", "notes": "08:00 situation", **payload}
    resp = api.client.post("/api/reports/snapshots", json=body, headers=api.h(role))
    return resp


def test_save_snapshot_freezes_current_report(api):
    api.incident(severity="Critical")
    resp = _save(api)
    assert resp.status_code == 201
    snap = resp.get_json()["data"]
    assert snap["title"] == "Morning briefing"
    assert snap["created_by"]["username"] == "operator"
    assert snap["highlights"]["total_incidents"] == 1
    assert snap["highlights"]["critical_incidents"] == 1
    assert "data" not in snap  # list/create responses stay small

    # Live data changes; the stored snapshot does not.
    api.incident(title="Later incident")
    full = api.get(f"/api/reports/snapshots/{snap['id']}", "lead")
    assert full["data"]["dashboard"]["total_incidents"] == 1
    assert set(full["data"]) == {"generated_at", "dashboard", "incidents", "resources", "shelters", "teams"}
    assert api.get("/api/reports/dashboard")["total_incidents"] == 2


def test_list_snapshots_newest_first_and_paginated(api):
    for title in ("First report", "Second report", "Third report"):
        assert _save(api, "coordinator", title=title).status_code == 201
    page = api.get("/api/reports/snapshots?per_page=2", "lead")
    assert [s["title"] for s in page["items"]] == ["Third report", "Second report"]
    assert page["pagination"] == {"page": 1, "per_page": 2, "total": 3, "pages": 2}
    assert all("data" not in s for s in page["items"])


def test_snapshot_validation(api):
    resp = _save(api, title="")
    assert resp.status_code == 400
    assert "title" in resp.get_json()["errors"]


@pytest.mark.parametrize("role", ["lead"])
def test_team_lead_cannot_save(api, role):
    assert _save(api, role).status_code == 403


def test_only_admin_deletes(api, client, headers):
    snap = _save(api).get_json()["data"]
    assert client.delete(f"/api/reports/snapshots/{snap['id']}", headers=headers("operator")).status_code == 403
    assert client.delete(f"/api/reports/snapshots/{snap['id']}", headers=headers("admin")).status_code == 200
    assert client.get(f"/api/reports/snapshots/{snap['id']}", headers=headers("admin")).status_code == 404


@pytest.mark.parametrize("bad_id", ["not-an-id", "64b000000000000000000000"])
def test_unknown_snapshot_is_404(client, headers, bad_id):
    resp = client.get(f"/api/reports/snapshots/{bad_id}", headers=headers("operator"))
    assert resp.status_code == 404
    assert resp.get_json()["message"] == "Situation report not found"


def test_snapshot_actions_are_audited_in_sql(api, app):
    snap = _save(api).get_json()["data"]
    entry = ActivityLog.query.filter_by(action="SITUATION_REPORT_SAVED").one()
    assert entry.details["snapshot_id"] == snap["id"]
    assert entry.user.username == "operator"


def test_health_reports_mongodb(client):
    assert client.get("/api/health").get_json()["data"]["mongodb"] == "ok"


def test_without_mongodb_only_snapshots_are_unavailable(tmp_path):
    app = create_app("testing", {
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'nomongo.db').as_posix()}",
        "MONGO_URI": "",
    })
    with app.app_context():
        db.create_all()
        from flask_jwt_extended import create_access_token
        from app.constants import Role
        from app.services.user_service import SYSTEM, create_user

        user = create_user({"username": "op", "email": "op@test.local", "full_name": "Op", "password": "Password123",
                            "role": Role.OPERATOR}, actor=SYSTEM)
        auth = {"Authorization": f"Bearer {create_access_token(identity=user)}"}
        client = app.test_client()

        resp = client.post("/api/reports/snapshots", json={"title": "Briefing"}, headers=auth)
        assert resp.status_code == 503
        assert resp.get_json()["success"] is False
        # Everything stored in SQLite keeps working.
        assert client.get("/api/reports/summary", headers=auth).status_code == 200
        assert client.get("/api/health").get_json()["data"] == {"status": "ok", "mongodb": "disabled"}
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
