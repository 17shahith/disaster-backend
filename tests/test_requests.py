import pytest


def test_create_request_linked_to_incident(api):
    incident = api.incident(location="Ward 5")
    req = api.request(incident["id"], category="Medical Assistance", priority="Critical", people_affected=20)
    assert req["status"] == "Pending"
    assert req["incident_id"] == incident["id"]
    assert req["location"] == "Ward 5"  # defaults to incident location


def test_request_validation(client, headers, api):
    incident = api.incident()
    resp = client.post("/api/requests", headers=headers("operator"), json={
        "incident_id": incident["id"], "category": "Pizza", "priority": "Urgent", "people_affected": -1,
        "quantity_requested": 0})
    assert resp.status_code == 400
    assert set(resp.get_json()["errors"]) >= {"category", "priority", "people_affected", "quantity_requested",
                                              "description"}


def test_request_for_missing_incident(client, headers):
    resp = client.post("/api/requests", headers=headers("operator"), json={
        "incident_id": 999, "category": "Food", "description": "x"})
    assert resp.status_code == 404


def test_request_for_closed_incident(api, client, headers):
    incident = api.incident()
    api.put(f"/api/incidents/{incident['id']}", "operator", {"status": "Closed"})
    resp = client.post("/api/requests", headers=headers("operator"), json={
        "incident_id": incident["id"], "category": "Food", "description": "x"})
    assert resp.status_code == 409


@pytest.mark.parametrize("role", ["coordinator", "lead"])
def test_only_operators_create_requests(client, headers, api, role):
    incident = api.incident()
    resp = client.post("/api/requests", headers=headers(role), json={
        "incident_id": incident["id"], "category": "Food", "description": "x"})
    assert resp.status_code == 403


def test_list_filters(api):
    incident = api.incident()
    api.request(incident["id"], category="Food", priority="Low")
    api.request(incident["id"], category="Rescue", priority="Critical")
    data = api.get(f"/api/requests?incident_id={incident['id']}&priority=Critical", "coordinator")
    assert [r["category"] for r in data["items"]] == ["Rescue"]


def test_complete_request_records_completion(api):
    req = api.request(api.incident()["id"])
    resp = api.put(f"/api/requests/{req['id']}", "coordinator",
                   {"status": "Completed", "completion_notes": "Delivered"})
    data = resp.get_json()["data"]
    assert resp.status_code == 200
    assert data["completed_at"] is not None and data["completion_notes"] == "Delivered"
    data = api.put(f"/api/requests/{req['id']}", "operator", {"status": "In Progress"}).get_json()["data"]
    assert data["completed_at"] is None


def test_team_lead_updates_status_of_assigned_request_only(api):
    incident = api.incident()
    req = api.request(incident["id"])
    other_req = api.request(api.incident(title="Elsewhere")["id"])
    team = api.team()
    api.allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"], request_id=req["id"])

    assert api.put(f"/api/requests/{req['id']}", "lead", {"status": "Completed"}).status_code == 200
    assert api.put(f"/api/requests/{req['id']}", "lead", {"priority": "Low"}).status_code == 403
    assert api.put(f"/api/requests/{other_req['id']}", "lead", {"status": "Completed"}).status_code == 403


def test_allocation_marks_request_in_progress(api):
    incident = api.incident()
    req = api.request(incident["id"])
    team = api.team()
    api.allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"], request_id=req["id"])
    assert api.get(f"/api/requests/{req['id']}")["status"] == "In Progress"


def test_delete_request(api, client, headers):
    req = api.request(api.incident()["id"])
    assert client.delete(f"/api/requests/{req['id']}", headers=headers("operator")).status_code == 200
    assert client.get(f"/api/requests/{req['id']}", headers=headers("operator")).status_code == 404


def test_cannot_delete_request_with_active_allocation(api, client, headers):
    incident = api.incident()
    req = api.request(incident["id"])
    team = api.team()
    api.allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"], request_id=req["id"])
    assert client.delete(f"/api/requests/{req['id']}", headers=headers("operator")).status_code == 409
