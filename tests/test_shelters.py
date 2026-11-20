import pytest


def test_create_shelter_with_available_beds(api):
    shelter = api.shelter(capacity=100, current_occupancy=40)
    assert shelter["available_beds"] == 60
    assert shelter["occupancy_rate"] == 40.0
    assert shelter["status"] == "Open"


def test_full_shelter_status_is_automatic(api):
    shelter = api.shelter(capacity=10, current_occupancy=10)
    assert shelter["status"] == "Full"
    data = api.put(f"/api/shelters/{shelter['id']}", "coordinator", {"current_occupancy": 5}).get_json()["data"]
    assert data["status"] == "Open" and data["available_beds"] == 5


def test_occupancy_cannot_exceed_capacity_on_create(client, headers):
    resp = client.post("/api/shelters", headers=headers("coordinator"), json={
        "name": "Over", "location": "x", "capacity": 10, "current_occupancy": 11})
    assert resp.status_code == 400
    assert "current_occupancy" in resp.get_json()["errors"]


def test_occupancy_cannot_exceed_capacity_on_update(api):
    shelter = api.shelter(capacity=50, current_occupancy=20)
    assert api.put(f"/api/shelters/{shelter['id']}", "coordinator", {"current_occupancy": 51}).status_code == 400
    # shrinking capacity below current occupancy is also rejected
    assert api.put(f"/api/shelters/{shelter['id']}", "coordinator", {"capacity": 10}).status_code == 400


@pytest.mark.parametrize("payload", [{"capacity": 0}, {"capacity": -5}, {"current_occupancy": -1},
                                     {"status": "Flooded"}])
def test_invalid_values(api, payload):
    shelter = api.shelter()
    assert api.put(f"/api/shelters/{shelter['id']}", "coordinator", payload).status_code == 400


def test_operator_cannot_manage_shelters(client, headers):
    resp = client.post("/api/shelters", headers=headers("operator"), json={
        "name": "X", "location": "x", "capacity": 10})
    assert resp.status_code == 403


def test_available_shelters(api):
    open_ = api.shelter(name="Open", capacity=10)
    api.shelter(name="Full", capacity=10, current_occupancy=10)
    api.shelter(name="Closed", capacity=10, status="Closed")
    items = api.get("/api/shelters/available", "operator")["items"]
    assert [s["id"] for s in items] == [open_["id"]]


def test_shelter_allocation_tracks_occupancy(api):
    incident = api.incident()
    shelter = api.shelter(capacity=100)
    alloc = api.allocation(incident_id=incident["id"], resource_type="Shelter", shelter_id=shelter["id"], quantity=70)
    assert api.get(f"/api/shelters/{shelter['id']}")["current_occupancy"] == 70

    api.put(f"/api/allocations/{alloc['id']}", "coordinator", {"status": "Cancelled", "cancellation_reason": "Moved"})
    assert api.get(f"/api/shelters/{shelter['id']}")["current_occupancy"] == 0


def test_shelter_allocation_over_capacity_rejected(api, client, headers):
    incident = api.incident()
    shelter = api.shelter(capacity=50, current_occupancy=30)
    resp = client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": incident["id"], "resource_type": "Shelter", "shelter_id": shelter["id"], "quantity": 21})
    assert resp.status_code == 409
    assert "20 bed(s) available" in resp.get_json()["errors"]["shelter_id"]
    assert api.get(f"/api/shelters/{shelter['id']}")["current_occupancy"] == 30  # rolled back


def test_closed_shelter_cannot_be_allocated(api, client, headers):
    shelter = api.shelter(status="Closed")
    resp = client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": api.incident()["id"], "resource_type": "Shelter", "shelter_id": shelter["id"],
        "quantity": 1})
    assert resp.status_code == 409


def test_delete_shelter_rules(api, client, headers):
    empty = api.shelter(name="Empty")
    occupied = api.shelter(name="Occupied", current_occupancy=3)
    assert client.delete(f"/api/shelters/{empty['id']}", headers=headers("coordinator")).status_code == 200
    assert client.delete(f"/api/shelters/{occupied['id']}", headers=headers("coordinator")).status_code == 409
