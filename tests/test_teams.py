def test_team_lead_registers_own_team(api, users):
    team = api.team(name="Rescue One")
    assert team["lead_id"] == users["lead"].id
    assert team["availability"] == "Available"


def test_team_lead_cannot_register_team_for_other_lead(client, headers, users):
    resp = client.post("/api/teams", headers=headers("lead"), json={
        "name": "Other Team", "team_type": "Rescue", "member_count": 3, "lead_id": users["lead2"].id})
    assert resp.status_code == 403


def test_admin_assigns_lead(client, headers, users):
    resp = client.post("/api/teams", headers=headers("admin"), json={
        "name": "Medics", "team_type": "Medical", "member_count": 4, "lead_id": users["lead2"].id})
    assert resp.status_code == 201
    resp = client.post("/api/teams", headers=headers("admin"), json={
        "name": "Bad Lead", "team_type": "Medical", "member_count": 4, "lead_id": users["coordinator"].id})
    assert resp.status_code == 400


def test_coordinator_cannot_register_team(client, headers):
    resp = client.post("/api/teams", headers=headers("coordinator"), json={
        "name": "X", "team_type": "Rescue", "member_count": 3})
    assert resp.status_code == 403


def test_team_validation(client, headers):
    resp = client.post("/api/teams", headers=headers("lead"), json={
        "name": "X", "team_type": "Navy", "member_count": 0, "availability": "Assigned"})
    assert resp.status_code == 400
    assert set(resp.get_json()["errors"]) >= {"team_type", "member_count", "availability"}


def test_duplicate_team_name(api, client, headers):
    api.team(name="Unique")
    resp = client.post("/api/teams", headers=headers("lead"), json={
        "name": "unique", "team_type": "Rescue", "member_count": 3})
    assert resp.status_code == 409


def test_update_own_team_availability(api):
    team = api.team()
    resp = api.put(f"/api/teams/{team['id']}", "lead", {"availability": "Unavailable", "member_count": 7})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["availability"] == "Unavailable"


def test_cannot_update_other_leads_team(api):
    team = api.team()
    assert api.put(f"/api/teams/{team['id']}", "lead2", {"member_count": 2}).status_code == 403


def test_cannot_manually_set_assigned(api):
    team = api.team()
    assert api.put(f"/api/teams/{team['id']}", "lead", {"availability": "Assigned"}).status_code == 400


def test_available_teams_endpoint(api):
    a = api.team(name="Team A")
    b = api.team(name="Team B")
    api.put(f"/api/teams/{b['id']}", "lead", {"availability": "Unavailable"})
    items = api.get("/api/teams/available", "operator")["items"]
    assert [t["id"] for t in items] == [a["id"]]


def test_assignment_updates_availability_and_completion_releases(api):
    incident = api.incident()
    team = api.team()
    alloc = api.approved_allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"])
    data = api.get(f"/api/teams/{team['id']}")
    assert data["availability"] == "Assigned"
    assert data["current_incident_id"] == incident["id"]
    assert data["active_allocation"]["id"] == alloc["id"]

    # cannot free the team while it has an active assignment
    assert api.put(f"/api/teams/{team['id']}", "lead", {"availability": "Available"}).status_code == 409

    api.put(f"/api/allocations/{alloc['id']}", "coordinator", {"status": "Allocated"})
    resp = api.put(f"/api/allocations/{alloc['id']}", "lead",
                   {"status": "Completed", "progress_notes": "All rescued"})
    assert resp.status_code == 200
    data = api.get(f"/api/teams/{team['id']}")
    assert data["availability"] == "Available"
    assert data["current_incident_id"] is None
    assert data["assignment_history"][0]["status"] == "Completed"


def test_unavailable_team_cannot_be_assigned(api, client, headers):
    incident = api.incident()
    team = api.team()
    api.put(f"/api/teams/{team['id']}", "lead", {"availability": "Unavailable"})
    resp = client.post("/api/allocations", headers=headers("coordinator"), json={
        "incident_id": incident["id"], "resource_type": "Team", "team_id": team["id"]})
    assert resp.status_code == 409
    assert "not available" in resp.get_json()["message"]


def test_team_cannot_be_double_assigned(api, client, headers):
    team = api.team()
    api.allocation(incident_id=api.incident()["id"], resource_type="Team", team_id=team["id"])
    resp = client.post("/api/allocations", headers=headers("operator"), json={
        "incident_id": api.incident(title="Second")["id"], "resource_type": "Team", "team_id": team["id"]})
    assert resp.status_code == 409


def test_record_and_list_team_activity(api, client, headers):
    team = api.team()
    resp = client.post(f"/api/teams/{team['id']}/activities", headers=headers("lead"),
                       json={"activity": "Completed sweep of sector 3", "notes": "No casualties"})
    assert resp.status_code == 201
    items = api.get(f"/api/teams/{team['id']}/activities", "operator")["items"]
    assert items[0]["description"] == "Completed sweep of sector 3"
    resp = client.post(f"/api/teams/{team['id']}/activities", headers=headers("lead2"),
                       json={"activity": "Not my team"})
    assert resp.status_code == 403


def test_delete_team_rules(api, client, headers):
    unused = api.team(name="Unused")
    used = api.team(name="Used")
    api.allocation(incident_id=api.incident()["id"], resource_type="Team", team_id=used["id"])
    assert client.delete(f"/api/teams/{unused['id']}", headers=headers("lead")).status_code == 403
    assert client.delete(f"/api/teams/{unused['id']}", headers=headers("admin")).status_code == 200
    assert client.delete(f"/api/teams/{used['id']}", headers=headers("admin")).status_code == 409
