"""Administrator user management, role-based authorization and activity logs."""
import pytest


@pytest.mark.parametrize("role", ["operator", "lead", "coordinator"])
def test_non_admin_cannot_manage_users(client, headers, role):
    resp = client.get("/api/users", headers=headers(role))
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False
    assert body["errors"]["required_roles"] == ["admin"]


def test_admin_lists_and_filters_users(client, headers):
    resp = client.get("/api/users?role=response_team_lead", headers=headers("admin"))
    data = resp.get_json()["data"]
    assert resp.status_code == 200
    assert data["pagination"]["total"] == 2
    assert {u["username"] for u in data["items"]} == {"lead", "lead2"}


def test_admin_creates_admin(client, headers):
    resp = client.post("/api/users", headers=headers("admin"), json={
        "username": "admin2", "email": "admin2@test.local", "full_name": "Second Admin",
        "password": "Secure123", "role": "admin"})
    assert resp.status_code == 201
    assert resp.get_json()["data"]["role"] == "admin"


def test_admin_changes_role(client, headers, users):
    resp = client.put(f"/api/users/{users['operator'].id}", json={"role": "relief_coordinator"},
                      headers=headers("admin"))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["role"] == "relief_coordinator"


def test_admin_cannot_demote_self(client, headers, users):
    resp = client.put(f"/api/users/{users['admin'].id}", json={"role": "control_room_operator"},
                      headers=headers("admin"))
    assert resp.status_code == 409


def test_admin_deactivates_user(client, headers, users):
    resp = client.delete(f"/api/users/{users['lead'].id}", headers=headers("admin"))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["is_active"] is False


def test_user_not_found(client, headers):
    resp = client.get("/api/users/9999", headers=headers("admin"))
    assert resp.status_code == 404
    assert resp.get_json()["message"] == "User not found"


def test_activity_logs_record_operations(client, headers, api):
    api.incident()
    resp = client.get("/api/activity-logs?entity_type=incident", headers=headers("admin"))
    items = resp.get_json()["data"]["items"]
    assert resp.status_code == 200
    assert items[0]["action"] == "INCIDENT_CREATED"
    assert items[0]["user"]["username"] == "operator"


def test_activity_logs_admin_only(client, headers):
    assert client.get("/api/activity-logs", headers=headers("coordinator")).status_code == 403


def test_unknown_route_returns_json_404(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json() == {"success": False, "message": "Resource not found", "errors": {}}


def test_method_not_allowed(client, headers):
    resp = client.patch("/api/incidents", headers=headers("admin"))
    assert resp.status_code == 405


def test_health(client):
    assert client.get("/api/health").get_json()["data"]["status"] == "ok"


def test_invalid_pagination(client, headers):
    resp = client.get("/api/incidents?page=0", headers=headers("admin"))
    assert resp.status_code == 400
    assert "page" in resp.get_json()["errors"]
