import pytest


class TestCreateIncident:
    def test_operator_creates_incident(self, client, headers):
        resp = client.post("/api/incidents", headers=headers("operator"), json={
            "title": "Flash Flood", "incident_type": "Flood", "description": "Rapid water rise",
            "location": "Ward 9", "severity": "Critical", "latitude": 13.08, "longitude": 80.27,
            "affected_people": 300})
        body = resp.get_json()
        assert resp.status_code == 201
        assert body["message"] == "Incident created successfully"
        data = body["data"]
        assert data["status"] == "Reported"
        assert data["reporter"]["username"] == "operator"
        assert data["created_at"].endswith("Z")

    def test_admin_can_create(self, api):
        assert api.incident()["id"]

    @pytest.mark.parametrize("role", ["lead", "coordinator"])
    def test_other_roles_forbidden(self, client, headers, role):
        resp = client.post("/api/incidents", headers=headers(role), json={
            "title": "X Fire", "incident_type": "Fire", "description": "d", "location": "l"})
        assert resp.status_code == 403

    def test_unauthenticated(self, client):
        assert client.post("/api/incidents", json={}).status_code == 401

    def test_validation_errors(self, client, headers):
        resp = client.post("/api/incidents", headers=headers("operator"), json={
            "title": "", "incident_type": "Tsunami", "severity": "Extreme", "latitude": 200,
            "affected_people": -5})
        errors = resp.get_json()["errors"]
        assert resp.status_code == 400
        assert set(errors) >= {"title", "incident_type", "severity", "latitude", "description", "location",
                               "affected_people"}

    def test_cannot_create_already_closed(self, client, headers):
        resp = client.post("/api/incidents", headers=headers("operator"), json={
            "title": "Old", "incident_type": "Fire", "description": "d", "location": "l", "status": "Closed"})
        assert resp.status_code == 400


class TestReadIncidents:
    def test_list_and_filter(self, api, client, headers):
        api.incident(title="Flood A", severity="Critical")
        api.incident(title="Fire B", incident_type="Fire", severity="Low")
        data = api.get("/api/incidents?severity=Critical", "coordinator")
        assert [i["title"] for i in data["items"]] == ["Flood A"]
        assert api.get("/api/incidents?search=fire")["pagination"]["total"] == 1
        assert client.get("/api/incidents?severity=Huge", headers=headers("admin")).status_code == 400

    def test_get_detail_includes_requests(self, api):
        incident = api.incident()
        api.request(incident["id"])
        data = api.get(f"/api/incidents/{incident['id']}", "operator")
        assert len(data["requests"]) == 1
        assert data["allocations"] == []

    def test_not_found(self, client, headers):
        resp = client.get("/api/incidents/999", headers=headers("operator"))
        assert resp.status_code == 404

    def test_team_lead_sees_only_assigned_incidents(self, api, client, headers):
        assigned = api.incident(title="Assigned Incident")
        other = api.incident(title="Other Incident")
        team = api.team()
        api.allocation(incident_id=assigned["id"], resource_type="Team", team_id=team["id"])

        items = api.get("/api/incidents", "lead")["items"]
        assert [i["id"] for i in items] == [assigned["id"]]
        assert client.get(f"/api/incidents/{other['id']}", headers=headers("lead")).status_code == 403
        assert client.get(f"/api/incidents/{assigned['id']}", headers=headers("lead")).status_code == 200
        assert api.get("/api/incidents", "lead2")["items"] == []


class TestUpdateIncident:
    def test_update_status_and_severity(self, api):
        incident = api.incident()
        resp = api.put(f"/api/incidents/{incident['id']}", "operator", {"status": "Active", "severity": "Critical"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["severity"] == "Critical"

    def test_complete_sets_resolved_and_reopen_clears(self, api):
        incident = api.incident()
        data = api.put(f"/api/incidents/{incident['id']}", "operator", {"status": "Completed"}).get_json()["data"]
        assert data["resolved_at"] is not None
        data = api.put(f"/api/incidents/{incident['id']}", "operator", {"status": "Active"}).get_json()["data"]
        assert data["resolved_at"] is None

    def test_cannot_complete_with_active_allocations(self, api):
        incident = api.incident()
        team = api.team()
        api.allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"])
        resp = api.put(f"/api/incidents/{incident['id']}", "operator", {"status": "Completed"})
        assert resp.status_code == 409

    def test_invalid_status(self, api):
        incident = api.incident()
        resp = api.put(f"/api/incidents/{incident['id']}", "operator", {"status": "Done"})
        assert resp.status_code == 400

    def test_empty_update(self, api):
        incident = api.incident()
        assert api.put(f"/api/incidents/{incident['id']}", "operator", {}).status_code == 400

    def test_team_lead_cannot_update(self, api):
        incident = api.incident()
        assert api.put(f"/api/incidents/{incident['id']}", "lead", {"status": "Active"}).status_code == 403


class TestDeleteIncident:
    def test_admin_deletes_incident_and_requests(self, api, client, headers):
        incident = api.incident()
        req = api.request(incident["id"])
        resp = client.delete(f"/api/incidents/{incident['id']}", headers=headers("admin"))
        assert resp.status_code == 200
        assert client.get(f"/api/requests/{req['id']}", headers=headers("admin")).status_code == 404

    def test_operator_cannot_delete(self, api, client, headers):
        incident = api.incident()
        assert client.delete(f"/api/incidents/{incident['id']}", headers=headers("operator")).status_code == 403

    def test_cannot_delete_with_allocations(self, api, client, headers):
        incident = api.incident()
        team = api.team()
        api.allocation(incident_id=incident["id"], resource_type="Team", team_id=team["id"])
        assert client.delete(f"/api/incidents/{incident['id']}", headers=headers("admin")).status_code == 409
