import pytest


@pytest.fixture
def supply_alloc(api):
    incident = api.incident(location="Ward 4 Relief Point")
    supply = api.supply(quantity=1000)
    alloc = api.approved_allocation(incident_id=incident["id"], resource_type="Supply", supply_id=supply["id"],
                                    quantity=300)
    return {"incident": incident, "supply": supply, "alloc": alloc}


def test_create_dispatch(api, supply_alloc):
    dispatch = api.dispatch(supply_alloc["alloc"]["id"], quantity=100)
    assert dispatch["status"] == "Prepared"
    assert dispatch["destination"] == "Ward 4 Relief Point"
    assert dispatch["resource_type"] == "Supply"


def test_dispatch_defaults_to_remaining_quantity(api, supply_alloc):
    assert api.dispatch(supply_alloc["alloc"]["id"])["quantity"] == 300


def test_dispatch_requires_valid_allocation(client, headers):
    resp = client.post("/api/dispatch", headers=headers("coordinator"), json={"allocation_id": 999})
    assert resp.status_code == 404


def test_dispatch_requires_approved_allocation(api, client, headers):
    alloc = api.allocation(incident_id=api.incident()["id"], resource_type="Supply",
                           supply_id=api.supply()["id"], quantity=5)
    resp = client.post("/api/dispatch", headers=headers("coordinator"), json={"allocation_id": alloc["id"]})
    assert resp.status_code == 409


@pytest.mark.parametrize("quantity, status", [(301, 400), (0, 400), (-5, 400)])
def test_invalid_dispatch_quantity(client, headers, supply_alloc, quantity, status):
    resp = client.post("/api/dispatch", headers=headers("coordinator"),
                       json={"allocation_id": supply_alloc["alloc"]["id"], "quantity": quantity})
    assert resp.status_code == status


def test_cannot_dispatch_more_than_remaining(api, client, headers, supply_alloc):
    api.dispatch(supply_alloc["alloc"]["id"], quantity=250)
    resp = client.post("/api/dispatch", headers=headers("coordinator"),
                       json={"allocation_id": supply_alloc["alloc"]["id"], "quantity": 51})
    assert resp.status_code == 400
    assert "Maximum dispatchable quantity is 50" in resp.get_json()["errors"]["quantity"]


def test_inventory_updated_after_dispatch(api, supply_alloc):
    dispatch = api.dispatch(supply_alloc["alloc"]["id"], quantity=100)
    supply_url = f"/api/supplies/{supply_alloc['supply']['id']}"
    assert api.get(supply_url)["quantity"] == 1000  # prepared: nothing left the warehouse yet

    data = api.advance_dispatch(dispatch["id"], "Dispatched")
    assert data["dispatched_at"] is not None
    supply = api.get(supply_url)
    assert supply["quantity"] == 900
    assert supply["reserved_quantity"] == 200
    assert supply["dispatched_quantity"] == 100
    assert api.get(f"/api/allocations/{supply_alloc['alloc']['id']}")["status"] == "Allocated"
    history = api.get(f"{supply_url}/history", "coordinator")["items"]
    assert history[0]["transaction_type"] == "Dispatched" and history[0]["dispatch_id"] == dispatch["id"]


def test_full_lifecycle_completes_allocation(api, supply_alloc):
    dispatch = api.dispatch(supply_alloc["alloc"]["id"])
    data = api.advance_dispatch(dispatch["id"], "Dispatched", "In Transit", "Delivered")
    assert data["delivered_at"] is not None
    resp = api.put(f"/api/dispatch/{dispatch['id']}", "coordinator",
                   {"status": "Completed", "completion_notes": "Received by camp manager"})
    data = resp.get_json()["data"]
    assert data["completed_at"] and data["completion_notes"] == "Received by camp manager"
    alloc = api.get(f"/api/allocations/{supply_alloc['alloc']['id']}")
    assert alloc["status"] == "Completed"
    assert alloc["remaining_quantity"] == 0


def test_invalid_status_transitions(api, supply_alloc):
    dispatch = api.dispatch(supply_alloc["alloc"]["id"])
    url = f"/api/dispatch/{dispatch['id']}"
    assert api.put(url, "coordinator", {"status": "Delivered"}).status_code == 409
    api.advance_dispatch(dispatch["id"], "Dispatched")
    assert api.put(url, "coordinator", {"status": "Prepared"}).status_code == 409
    assert api.put(url, "coordinator", {"status": "Lost"}).status_code == 400
    assert api.put(url, "coordinator", {"quantity": 10}).status_code == 409  # only while Prepared


def test_cancelling_dispatched_allocation_blocked(api, supply_alloc):
    dispatch = api.dispatch(supply_alloc["alloc"]["id"], quantity=10)
    api.advance_dispatch(dispatch["id"], "Dispatched")
    resp = api.put(f"/api/allocations/{supply_alloc['alloc']['id']}", "coordinator", {"status": "Cancelled"})
    assert resp.status_code == 409


def test_completing_allocation_requires_delivered_dispatches(api, supply_alloc):
    alloc_url = f"/api/allocations/{supply_alloc['alloc']['id']}"
    dispatch = api.dispatch(supply_alloc["alloc"]["id"], quantity=100)
    api.advance_dispatch(dispatch["id"], "Dispatched")
    assert api.put(alloc_url, "coordinator", {"status": "Completed"}).status_code == 409
    api.advance_dispatch(dispatch["id"], "Delivered")
    assert api.put(alloc_url, "coordinator", {"status": "Completed"}).status_code == 200
    # the 200 units never dispatched return to available stock
    supply = api.get(f"/api/supplies/{supply_alloc['supply']['id']}")
    assert supply["reserved_quantity"] == 0 and supply["quantity"] == 900 and supply["available_quantity"] == 900


def test_prepared_dispatch_can_be_deleted(api, client, headers, supply_alloc):
    dispatch = api.dispatch(supply_alloc["alloc"]["id"])
    assert client.delete(f"/api/dispatch/{dispatch['id']}", headers=headers("coordinator")).status_code == 200
    dispatch = api.dispatch(supply_alloc["alloc"]["id"])
    api.advance_dispatch(dispatch["id"], "Dispatched")
    assert client.delete(f"/api/dispatch/{dispatch['id']}", headers=headers("coordinator")).status_code == 409


def test_team_dispatch_and_team_lead_updates(api, client, headers):
    incident = api.incident()
    team = api.team()
    alloc = api.approved_allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"])
    dispatch = api.dispatch(alloc["id"], vehicle_details="Rescue boat x2")
    assert dispatch["team_id"] == team["id"]

    # team leads may not mark a dispatch as Dispatched
    assert api.put(f"/api/dispatch/{dispatch['id']}", "lead", {"status": "Dispatched"}).status_code == 403
    api.advance_dispatch(dispatch["id"], "Dispatched")
    assert api.get(f"/api/teams/{team['id']}")["availability"] == "Busy"

    assert api.put(f"/api/dispatch/{dispatch['id']}", "lead2", {"status": "In Transit"}).status_code == 403
    api.advance_dispatch(dispatch["id"], "In Transit", "Delivered", "Completed", role="lead")
    assert [d["id"] for d in api.get("/api/dispatch", "lead")["items"]] == [dispatch["id"]]
    assert client.get(f"/api/dispatch/{dispatch['id']}", headers=headers("lead2")).status_code == 403

    api.put(f"/api/allocations/{alloc['id']}", "lead", {"status": "Completed"})
    assert api.get(f"/api/teams/{team['id']}")["availability"] == "Available"


def test_unavailable_team_cannot_carry_dispatch(api, client, headers, supply_alloc):
    team = api.team(name="Off Duty")
    api.put(f"/api/teams/{team['id']}", "lead", {"availability": "Unavailable"})
    resp = client.post("/api/dispatch", headers=headers("coordinator"),
                       json={"allocation_id": supply_alloc["alloc"]["id"], "team_id": team["id"]})
    assert resp.status_code == 409


def test_operator_cannot_create_dispatch(client, headers, supply_alloc):
    resp = client.post("/api/dispatch", headers=headers("operator"),
                       json={"allocation_id": supply_alloc["alloc"]["id"]})
    assert resp.status_code == 403


def test_list_dispatch_filters(api, supply_alloc):
    d1 = api.dispatch(supply_alloc["alloc"]["id"], quantity=10)
    api.dispatch(supply_alloc["alloc"]["id"], quantity=10)
    api.advance_dispatch(d1["id"], "Dispatched")
    items = api.get("/api/dispatch?status=Dispatched")["items"]
    assert [d["id"] for d in items] == [d1["id"]]
    assert api.get(f"/api/dispatch?incident_id={supply_alloc['incident']['id']}")["pagination"]["total"] == 2
