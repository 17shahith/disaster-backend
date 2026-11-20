"""End-to-end simulated emergency scenarios (flood, earthquake, fire, cyclone, building collapse)."""
from app.extensions import db
from app.models import ActivityLog, Incident, ReliefSupply, ResourceAllocation, ResponseTeam, Shelter
from app.scenarios import run_scenarios
from app.seed import seed_base_data
from app.services import report_service


def _seed(app):
    seed_base_data(log=lambda *_: None)
    return run_scenarios(log=lambda *_: None)


def _by_name(model, name):
    return db.session.execute(db.select(model).where(model.name == name)).scalar_one()


def test_all_scenarios_run(app):
    results = _seed(app)
    assert set(results) == {"flood", "earthquake", "fire", "cyclone", "building_collapse"}
    assert Incident.query.count() == 5


def test_scenarios_are_idempotent(app):
    _seed(app)
    assert run_scenarios(log=lambda *_: None) == {}
    seed_base_data(log=lambda *_: None)
    assert Incident.query.count() == 5
    assert ResponseTeam.query.count() == 8


def test_flood_scenario_state(app):
    results = _seed(app)
    flood = db.session.get(Incident, results["flood"])
    assert flood.status == "In Progress"
    water = _by_name(ReliefSupply, "Bottled Drinking Water")
    assert water.quantity == 8000 and water.dispatched_quantity == 2000 and water.reserved_quantity == 0
    rice = _by_name(ReliefSupply, "Rice Bags")
    assert rice.quantity == 4400 and rice.reserved_quantity == 400
    assert _by_name(Shelter, "City Community Hall").current_occupancy == 120
    assert _by_name(ResponseTeam, "Alpha Rescue Squad").availability == "Busy"


def test_fire_scenario_completes(app):
    results = _seed(app)
    fire = db.session.get(Incident, results["fire"])
    assert fire.status == "Completed" and fire.resolved_at is not None
    assert _by_name(ResponseTeam, "Charlie Fire Brigade").availability == "Available"
    assert all(r.status == "Completed" for r in fire.requests)


def test_cyclone_shelter_occupancy(app):
    _seed(app)
    assert _by_name(Shelter, "Stadium Relief Camp").current_occupancy == 600
    assert _by_name(Shelter, "Hilltop College Shelter").current_occupancy == 250
    report = report_service.shelter_report()
    assert report["total_occupancy"] == 970


def test_building_collapse_rescue_completion(app):
    results = _seed(app)
    allocations = ResourceAllocation.query.filter_by(incident_id=results["building_collapse"]).all()
    statuses = {a.resource_name: a.status for a in allocations}
    assert statuses["Foxtrot Rescue Unit"] == "Completed"
    assert statuses["Hydraulic Rescue Cutters"] == "Completed"
    assert statuses["Golf Medical Response"] == "Approved"


def test_scenarios_are_logged(app):
    _seed(app)
    actions = {a for (a,) in db.session.execute(db.select(ActivityLog.action).distinct())}
    assert {"INCIDENT_CREATED", "REQUEST_CREATED", "ALLOCATION_CREATED", "DISPATCH_CREATED",
            "DISPATCH_STATUS_CHANGED", "ALLOCATION_COMPLETED"} <= actions


def test_dashboard_after_scenarios(app):
    _seed(app)
    data = report_service.dashboard()
    assert data["total_incidents"] == 5
    assert data["active_incidents"] == 4
    assert data["critical_incidents"] == 3
    assert data["completed_operations"]["incidents"] == 1
