import pytest


@pytest.fixture
def setup(api):
    return {"incident": api.incident(), "supply": api.supply(quantity=500), "team": api.team()}


def test_supply_allocation_reserves_inventory(api, setup):
    alloc = api.allocation(incident_id=setup["incident"]["id"], resource_type="Supply",
                           supply_id=setup["supply"]["id"], quantity=200)
    assert alloc["status"] == "Pending"
    assert alloc["resource_name"] == "Bottled Water"
    supply = api.get(f"/api/supplies/{setup['supply']['id']}")
    assert supply["reserved_quantity"] == 200 and supply["available_quantity"] == 300


def test_allocation_cannot_exceed_inventory(api, client, headers, setup):
    resp = client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": setup["incident"]["id"], "resource_type": "Supply", "supply_id": setup["supply"]["id"],
        "quantity": 501})
    assert resp.status_code == 409
    assert "only 500 available" in resp.get_json()["errors"]["quantity"]


def test_reservations_count_against_availability(api, client, headers, setup):
    api.allocation(incident_id=setup["incident"]["id"], resource_type="Supply",
                   supply_id=setup["supply"]["id"], quantity=400)
    other = api.incident(title="Other")
    resp = client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": other["id"], "resource_type": "Supply", "supply_id": setup["supply"]["id"], "quantity": 101})
    assert resp.status_code == 409


@pytest.mark.parametrize("payload, field", [
    ({"resource_type": "Supply", "quantity": 5}, "supply_id"),
    ({"resource_type": "Supply", "supply_id": 1}, "quantity"),
    ({"resource_type": "Team", "team_id": 1, "supply_id": 1}, "supply_id"),
    ({"resource_type": "Vehicle"}, "resource_type"),
    ({"resource_type": "Supply", "supply_id": 1, "quantity": -5}, "quantity"),
    ({"resource_type": "Supply", "supply_id": 1, "quantity": 0}, "quantity"),
])
def test_allocation_validation(client, headers, setup, payload, field):
    resp = client.post("/api/allocations", headers=headers("coordinator"),
                       json={"incident_id": setup["incident"]["id"], **payload})
    assert resp.status_code == 400
    assert field in resp.get_json()["errors"]


def test_duplicate_active_allocation_rejected(api, client, headers, setup):
    api.allocation(incident_id=setup["incident"]["id"], resource_type="Supply",
                   supply_id=setup["supply"]["id"], quantity=10)
    resp = client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": setup["incident"]["id"], "resource_type": "Supply", "supply_id": setup["supply"]["id"],
        "quantity": 10})
    assert resp.status_code == 409
    assert "already has an active allocation" in resp.get_json()["message"]


def test_completed_incident_cannot_receive_allocations_until_reopened(api, client, headers, setup):
    incident_id = setup["incident"]["id"]
    api.put(f"/api/incidents/{incident_id}", "operator", {"status": "Completed"})
    payload = {"incident_id": incident_id, "resource_type": "Team", "team_id": setup["team"]["id"]}
    resp = client.post("/api/allocations", headers=headers("coordinator"), json=payload)
    assert resp.status_code == 409
    assert "Reopen" in resp.get_json()["errors"]["incident_id"]

    api.put(f"/api/incidents/{incident_id}", "operator", {"status": "Active"})
    assert client.post("/api/allocations", headers=headers("coordinator"), json=payload).status_code == 201


def test_request_must_belong_to_incident(api, client, headers, setup):
    other_req = api.request(api.incident(title="Other")["id"])
    resp = client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": setup["incident"]["id"], "resource_type": "Team", "team_id": setup["team"]["id"],
        "request_id": other_req["id"]})
    assert resp.status_code == 400


def test_status_workflow(api, setup):
    alloc = api.allocation(incident_id=setup["incident"]["id"], resource_type="Supply",
                           supply_id=setup["supply"]["id"], quantity=50)
    url = f"/api/allocations/{alloc['id']}"
    assert api.put(url, "coordinator", {"status": "Completed"}).status_code == 409  # cannot skip
    data = api.put(url, "coordinator", {"status": "Approved"}).get_json()["data"]
    assert data["approved_by"]["username"] == "coordinator" and data["approved_at"]
    assert api.put(url, "coordinator", {"status": "Pending"}).status_code == 409  # no going back


def test_cancel_releases_reservation(api, setup):
    alloc = api.approved_allocation(incident_id=setup["incident"]["id"], resource_type="Supply",
                                    supply_id=setup["supply"]["id"], quantity=120)
    resp = api.put(f"/api/allocations/{alloc['id']}", "coordinator",
                   {"status": "Cancelled", "cancellation_reason": "Duplicate request"})
    data = resp.get_json()["data"]
    assert data["status"] == "Cancelled" and data["cancellation_reason"] == "Duplicate request"
    assert api.get(f"/api/supplies/{setup['supply']['id']}")["reserved_quantity"] == 0
    assert api.put(f"/api/allocations/{alloc['id']}", "coordinator", {"status": "Approved"}).status_code == 409


def test_change_quantity_adjusts_reservation(api, setup):
    alloc = api.allocation(incident_id=setup["incident"]["id"], resource_type="Supply",
                           supply_id=setup["supply"]["id"], quantity=100)
    url = f"/api/allocations/{alloc['id']}"
    assert api.put(url, "coordinator", {"quantity": 300}).status_code == 200
    assert api.get(f"/api/supplies/{setup['supply']['id']}")["reserved_quantity"] == 300
    assert api.put(url, "coordinator", {"quantity": 600}).status_code == 409
    assert api.put(url, "coordinator", {"quantity": 50}).status_code == 200
    assert api.get(f"/api/supplies/{setup['supply']['id']}")["reserved_quantity"] == 50


def test_operator_can_assign_teams_but_not_supplies(api, client, headers, setup):
    resp = client.post("/api/allocations", headers=headers("operator"), json={
        "incident_id": setup["incident"]["id"], "resource_type": "Supply", "supply_id": setup["supply"]["id"],
        "quantity": 1})
    assert resp.status_code == 403
    alloc = api.allocation(role="operator", incident_id=setup["incident"]["id"], resource_type="Team",
                           team_id=setup["team"]["id"])
    assert alloc["quantity"] == 5  # team size


def test_team_lead_permissions_on_allocations(api, client, headers, setup):
    alloc = api.approved_allocation(incident_id=setup["incident"]["id"], resource_type="Team",
                                    team_id=setup["team"]["id"])
    url = f"/api/allocations/{alloc['id']}"
    assert client.post("/api/allocations", headers=headers("lead"), json={}).status_code == 403
    assert api.put(url, "lead2", {"progress_notes": "x"}).status_code == 403
    assert api.put(url, "lead", {"status": "Cancelled"}).status_code == 403
    assert api.put(url, "lead", {"notes": "x"}).status_code == 403
    resp = api.put(url, "lead", {"progress_notes": "Reached site, evacuating"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["progress_notes"] == "Reached site, evacuating"
    assert [a["id"] for a in api.get("/api/allocations", "lead")["items"]] == [alloc["id"]]
    assert api.get("/api/allocations", "lead2")["items"] == []


def test_allocation_failure_rolls_back_everything(api, client, headers, setup, app):
    """A failed allocation must not leave a partial allocation row or reservation behind."""
    from app.models import ResourceAllocation

    client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": setup["incident"]["id"], "resource_type": "Supply", "supply_id": setup["supply"]["id"],
        "quantity": 9999})
    assert ResourceAllocation.query.count() == 0
    assert api.get(f"/api/supplies/{setup['supply']['id']}")["reserved_quantity"] == 0


def test_allocation_not_found(client, headers):
    assert client.get("/api/allocations/123", headers=headers("coordinator")).status_code == 404
