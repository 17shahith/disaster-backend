"""Behaviour the React frontend relies on (CORS, dashboard/report payloads, editable fields)."""
import pytest


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_preflight_allows_vite_dev_server(client, origin):
    resp = client.options("/api/incidents", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type"})
    assert resp.headers.get("Access-Control-Allow-Origin") == origin
    assert "authorization" in resp.headers.get("Access-Control-Allow-Headers", "").lower()


def test_cors_rejects_unknown_origin(client):
    resp = client.options("/api/incidents", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "Access-Control-Allow-Origin" not in resp.headers


def test_incident_report_source_and_time(api):
    incident = api.incident(reported_source="District Police", reported_at="2026-11-20T08:30:00Z")
    assert incident["reported_source"] == "District Police"
    assert incident["reported_at"] == "2026-11-20T08:30:00Z"
    # reported_at falls back to the registration time when not supplied
    other = api.incident(title="No Time Given")
    assert other["reported_at"] == other["created_at"]


def test_invalid_reported_at(client, headers):
    resp = client.post("/api/incidents", headers=headers("operator"), json={
        "title": "Bad Time", "incident_type": "Fire", "description": "d", "location": "l",
        "reported_at": "yesterday"})
    assert resp.status_code == 400
    assert "reported_at" in resp.get_json()["errors"]


def test_request_with_explicit_location_and_contact(api):
    """Regression: supplying `location` on create used to raise a TypeError (500)."""
    incident = api.incident(location="Ward 9")
    req = api.request(incident["id"], location="Bridge road", contact_name="Ward Officer",
                      contact_phone="+91 90000 11111", people_affected=14)
    assert req["location"] == "Bridge road"
    assert req["contact_name"] == "Ward Officer"


def test_dashboard_includes_charts_and_feeds(api):
    incident = api.incident(severity="Critical")
    api.request(incident["id"], priority="High")
    team = api.team()
    api.allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"])
    data = api.get("/api/reports/dashboard", "lead")

    assert data["incident_status"]["Reported"] == 1
    assert data["priority_distribution"] == {"Critical": 1, "High": 1, "Medium": 0, "Low": 0}
    assert data["recent_incidents"][0]["id"] == incident["id"]
    assert data["recent_allocations"][0]["resource_name"] == "Alpha Team"
    feed = data["recent_activities"]
    assert feed and all(entry["entity_type"] != "user" for entry in feed)
    assert "ip_address" not in feed[0] and feed[0]["user"]


def test_report_summary_snapshot(api):
    api.supply(quantity=40, low_stock_threshold=50)
    data = api.get("/api/reports/summary", "coordinator")
    assert set(data) == {"generated_at", "dashboard", "incidents", "resources", "shelters", "teams"}
    assert data["resources"]["supplies"][0]["low_stock_threshold"] == 50


def test_dispatch_driver_and_resubmitting_unchanged_fields(api):
    incident = api.incident()
    supply = api.supply(quantity=100)
    alloc = api.approved_allocation(incident_id=incident["id"], resource_type="Supply", supply_id=supply["id"],
                                    quantity=20)
    dispatch = api.dispatch(alloc["id"], driver_name="R. Kumar", vehicle_details="TN-01-1234")
    assert dispatch["driver_name"] == "R. Kumar"
    api.advance_dispatch(dispatch["id"], "Dispatched")

    # A full edit form re-sends quantity unchanged: allowed. Changing it is still blocked.
    resp = api.put(f"/api/dispatch/{dispatch['id']}", "coordinator",
                   {"quantity": 20, "driver_name": "S. Rao", "destination": "Ward 4"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["driver_name"] == "S. Rao"
    assert api.put(f"/api/dispatch/{dispatch['id']}", "coordinator", {"quantity": 10}).status_code == 409
