import pytest


def test_dashboard_counts(api):
    incident = api.incident(severity="Critical")
    api.incident(title="Minor", severity="Low")
    api.request(incident["id"])
    team = api.team()
    api.team(name="Spare")
    api.shelter(capacity=100, current_occupancy=10)
    supply = api.supply(quantity=500)
    api.allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"])
    alloc = api.approved_allocation(incident_id=incident["id"], resource_type="Supply", supply_id=supply["id"],
                                    quantity=100)
    dispatch = api.dispatch(alloc["id"])
    api.advance_dispatch(dispatch["id"], "Dispatched")

    data = api.get("/api/reports/dashboard", "lead")
    assert data["total_incidents"] == 2
    assert data["active_incidents"] == 2
    assert data["critical_incidents"] == 1
    assert data["pending_requests"] == 1
    assert data["available_teams"] == 1
    assert data["active_shelters"] == 1
    assert data["available_shelter_beds"] == 90
    assert data["total_available_supplies"] == 400
    assert data["active_allocations"] == 2
    assert data["dispatched_resources"] == 1
    assert data["completed_operations"]["allocations"] == 0


def test_dashboard_requires_auth(client):
    assert client.get("/api/reports/dashboard").status_code == 401


def test_incident_report(api):
    api.incident(incident_type="Fire", severity="Critical")
    api.incident(title="Quake", incident_type="Earthquake")
    data = api.get("/api/reports/incidents", "operator")
    assert data["by_type"]["Fire"] == 1 and data["by_type"]["Cyclone"] == 0
    assert data["by_severity"]["Critical"] == 1
    assert len(data["critical_active_incidents"]) == 1


def test_resource_report(api):
    supply = api.supply(quantity=100, low_stock_threshold=50)
    api.allocation(incident_id=api.incident()["id"], resource_type="Supply", supply_id=supply["id"], quantity=60)
    data = api.get("/api/reports/resources", "coordinator")
    assert data["supplies"][0]["utilization_rate"] == 60.0
    assert data["low_stock_items"][0]["id"] == supply["id"]
    assert data["allocations"]["by_status"]["Pending"] == 1
    assert data["by_category"]["Drinking Water"]["reserved"] == 60


def test_shelter_report(api):
    api.shelter(name="Hall A", capacity=100, current_occupancy=50)
    api.shelter(name="Hall B", capacity=100, current_occupancy=100)
    data = api.get("/api/reports/shelters", "operator")
    assert data["total_capacity"] == 200
    assert data["overall_occupancy_rate"] == 75.0
    assert data["by_status"]["Full"] == 1
    assert data["total_available_beds"] == 50


def test_team_report(api):
    api.team(name="Team A")
    b = api.team(name="Team B")
    api.put(f"/api/teams/{b['id']}", "lead", {"availability": "Unavailable"})
    data = api.get("/api/reports/teams", "coordinator")
    assert data["by_availability"] == {"Available": 1, "Assigned": 0, "Busy": 0, "Unavailable": 1}
    assert data["availability_rate"] == 50.0


@pytest.mark.parametrize("path", ["incidents", "resources", "shelters", "teams"])
def test_reports_available_to_all_roles(client, headers, path):
    for role in ("admin", "operator", "lead", "coordinator"):
        assert client.get(f"/api/reports/{path}", headers=headers(role)).status_code == 200
