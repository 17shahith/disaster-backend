"""Simulated emergency scenarios for development, demos and testing.

Each scenario drives the real service layer (the same code the REST API uses),
so every business rule, transaction and activity log entry is exercised.
No external alerting systems are involved; everything is simulated internally.
Requires the base seed data (``app.seed.seed_base_data``).
"""
from sqlalchemy import select

from .extensions import db
from .models import Incident, ReliefSupply, ResponseTeam, Shelter, User
from .services import (
    allocation_service,
    dispatch_service,
    incident_service,
    request_service,
)


class _Ctx:
    """Name-based lookups and role actors for scenario scripts."""

    def __init__(self):
        self.operator = self._user("operator")
        self.coordinator = self._user("coordinator")
        self.leads = {"teamlead": self._user("teamlead"), "teamlead2": self._user("teamlead2")}

    @staticmethod
    def _user(username):
        user = db.session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None:
            raise RuntimeError("Base seed data missing: run `flask seed` first")
        return user

    @staticmethod
    def _by_name(model, name):
        obj = db.session.execute(select(model).where(model.name == name)).scalar_one_or_none()
        if obj is None:
            raise RuntimeError(f"Seed record '{name}' not found: run `flask seed` first")
        return obj

    def team(self, name):
        return self._by_name(ResponseTeam, name)

    def supply(self, name):
        return self._by_name(ReliefSupply, name)

    def shelter(self, name):
        return self._by_name(Shelter, name)

    def lead_of(self, team):
        return db.session.get(User, team.lead_id)

    # --- step helpers ------------------------------------------------------
    def incident(self, **data):
        data.setdefault("status", "Active")
        return incident_service.create_incident(data, self.operator)

    def request(self, incident, category, description, priority="High", people=0, quantity=None):
        return request_service.create_request(
            {"incident_id": incident.id, "category": category, "description": description, "priority": priority,
             "people_affected": people, "quantity_requested": quantity},
            self.operator,
        )

    def assign_team(self, incident, team_name, request=None, approve=True):
        allocation = allocation_service.create_allocation(
            {"incident_id": incident.id, "resource_type": "Team", "team_id": self.team(team_name).id,
             "request_id": request.id if request else None},
            self.operator,
        )
        if approve:
            allocation_service.update_allocation(allocation, {"status": "Approved"}, self.coordinator)
        return allocation

    def allocate_supply(self, incident, supply_name, quantity, request=None):
        allocation = allocation_service.create_allocation(
            {"incident_id": incident.id, "resource_type": "Supply", "supply_id": self.supply(supply_name).id,
             "quantity": quantity, "request_id": request.id if request else None},
            self.coordinator,
        )
        allocation_service.update_allocation(allocation, {"status": "Approved"}, self.coordinator)
        return allocation

    def allocate_shelter(self, incident, shelter_name, people, request=None):
        allocation = allocation_service.create_allocation(
            {"incident_id": incident.id, "resource_type": "Shelter", "shelter_id": self.shelter(shelter_name).id,
             "quantity": people, "request_id": request.id if request else None},
            self.coordinator,
        )
        allocation_service.update_allocation(allocation, {"status": "Approved"}, self.coordinator)
        return allocation

    def dispatch(self, allocation, through="Completed", quantity=None, team_name=None, vehicle=None):
        record = dispatch_service.create_dispatch(
            {"allocation_id": allocation.id, "quantity": quantity,
             "team_id": self.team(team_name).id if team_name else None, "vehicle_details": vehicle},
            self.coordinator,
        )
        for status in ("Dispatched", "In Transit", "Delivered", "Completed"):
            dispatch_service.update_dispatch(record, {"status": status}, self.coordinator)
            if status == through:
                break
        return record

    def complete_team(self, allocation, notes):
        lead = self.lead_of(allocation.team)
        allocation_service.update_allocation(allocation, {"progress_notes": notes, "status": "Completed"}, lead)

    def complete_request(self, request, notes):
        request_service.update_request(request, {"status": "Completed", "completion_notes": notes}, self.operator)


def flood(ctx):
    incident = ctx.incident(
        title="Riverbank Flooding - Ward 4", incident_type="Flood", severity="Critical", location="Ward 4, Riverside",
        latitude=13.0827, longitude=80.2707, affected_people=850,
        description="River overflowed after 36 hours of continuous rainfall. Low-lying homes submerged.",
    )
    rescue = ctx.request(incident, "Rescue", "Families stranded on rooftops near the river bridge", "Critical", 60)
    ctx.request(incident, "Rescue", "Elderly residents trapped in a care home ground floor", "High", 25)
    water = ctx.request(incident, "Drinking Water", "Clean drinking water for displaced families", "High", 400, 2000)
    food = ctx.request(incident, "Food", "Dry rations for relief camp", "Medium", 400, 1000)
    shelter_req = ctx.request(incident, "Shelter", "Temporary shelter for evacuated families", "High", 120)

    team_alloc = ctx.assign_team(incident, "Alpha Rescue Squad", rescue)
    ctx.dispatch(team_alloc, through="In Transit", vehicle="Rescue boats x4")
    water_alloc = ctx.allocate_supply(incident, "Bottled Drinking Water", 2000, water)
    ctx.dispatch(water_alloc, through="Completed", team_name="Echo Logistics Team", vehicle="Truck TN-01-4521")
    rice_alloc = ctx.allocate_supply(incident, "Rice Bags", 1000, food)
    ctx.dispatch(rice_alloc, through="In Transit", quantity=600, team_name="Echo Logistics Team",
                 vehicle="Truck TN-01-7788")
    ctx.allocate_shelter(incident, "City Community Hall", 120, shelter_req)
    incident_service.update_incident(incident, {"status": "In Progress"}, ctx.operator)
    return incident


def earthquake(ctx):
    incident = ctx.incident(
        title="Magnitude 6.1 Earthquake - Hill District", incident_type="Earthquake", severity="Critical",
        location="Hill District, Sector 2", latitude=30.7333, longitude=79.0667, affected_people=1200,
        description="Strong tremors damaged multiple residential buildings; injuries reported.",
    )
    medical = ctx.request(incident, "Medical Assistance", "Treatment for injured residents at relief point",
                          "Critical", 150, 200)
    ctx.request(incident, "Rescue", "Search collapsed houses in Sector 2", "Critical", 40)
    ctx.assign_team(incident, "Delta Search and Rescue")
    med_team = ctx.assign_team(incident, "Bravo Medical Unit", medical)
    ctx.dispatch(med_team, through="Delivered", vehicle="Ambulances x3")
    kits = ctx.allocate_supply(incident, "First Aid Kits", 200, medical)
    ctx.dispatch(kits, through="Completed")
    meds = ctx.allocate_supply(incident, "Antibiotics", 150, medical)
    ctx.dispatch(meds, through="Dispatched", quantity=100)
    incident_service.update_incident(incident, {"status": "In Progress"}, ctx.operator)
    return incident


def fire(ctx):
    incident = ctx.incident(
        title="Warehouse Fire - Industrial Estate", incident_type="Fire", severity="High",
        location="Plot 17, Industrial Estate", affected_people=30,
        description="Fire broke out in a chemical storage warehouse; workers evacuated, two missing.",
    )
    rescue = ctx.request(incident, "Rescue", "Locate two missing workers inside warehouse", "Critical", 2)
    team_alloc = ctx.assign_team(incident, "Charlie Fire Brigade", rescue)
    ctx.dispatch(team_alloc, through="Completed", vehicle="Fire tenders x3")
    ctx.complete_team(team_alloc, "Fire extinguished; both workers rescued with minor injuries.")
    ctx.complete_request(rescue, "Both missing workers rescued and handed over to paramedics.")
    incident_service.update_incident(incident, {"status": "Completed"}, ctx.operator)
    return incident


def cyclone(ctx):
    incident = ctx.incident(
        title="Cyclone Vardah Landfall - Coastal Belt", incident_type="Cyclone", severity="High",
        location="Coastal Belt, Fishermen Colony", latitude=13.05, longitude=80.29, affected_people=2000,
        description="Cyclone made landfall with 120 km/h winds; coastal villages evacuated.",
    )
    shelter_req = ctx.request(incident, "Shelter", "Evacuees from fishermen colony need shelter", "Critical", 850)
    food = ctx.request(incident, "Food", "Cooked food / meal packs for evacuees", "High", 850, 1700)
    water = ctx.request(incident, "Drinking Water", "Water purification for camp", "High", 850, 500)
    ctx.allocate_shelter(incident, "Stadium Relief Camp", 600, shelter_req)
    ctx.allocate_shelter(incident, "Hilltop College Shelter", 250, shelter_req)
    meals = ctx.allocate_supply(incident, "Ready-to-eat Meal Packs", 1700, food)
    ctx.dispatch(meals, through="Delivered", team_name="Echo Logistics Team")
    ctx.allocate_supply(incident, "Water Purification Tablets", 500, water)
    ctx.allocate_supply(incident, "Blankets", 850, shelter_req)
    return incident


def building_collapse(ctx):
    incident = ctx.incident(
        title="Residential Building Collapse - MG Road", incident_type="Building Collapse", severity="Critical",
        location="MG Road, Block C", affected_people=45,
        description="Four-storey residential building collapsed; residents trapped under debris.",
    )
    rescue = ctx.request(incident, "Rescue", "Extract residents trapped under debris", "Critical", 18)
    medical = ctx.request(incident, "Medical Assistance", "Trauma care for rescued residents", "High", 18)
    rescue_team = ctx.assign_team(incident, "Foxtrot Rescue Unit", rescue)
    ctx.dispatch(rescue_team, through="Completed", vehicle="Rescue truck")
    ctx.assign_team(incident, "Golf Medical Response", medical)
    cutters = ctx.allocate_supply(incident, "Hydraulic Rescue Cutters", 4, rescue)
    ctx.dispatch(cutters, through="Completed", team_name="Foxtrot Rescue Unit")
    ctx.complete_team(rescue_team, "All 18 trapped residents extracted; search operation concluded.")
    ctx.complete_request(rescue, "All trapped residents rescued.")
    incident_service.update_incident(incident, {"status": "In Progress"}, ctx.operator)
    return incident


SCENARIOS = {
    "flood": flood,
    "earthquake": earthquake,
    "fire": fire,
    "cyclone": cyclone,
    "building_collapse": building_collapse,
}

_TITLES = {
    "flood": "Riverbank Flooding - Ward 4",
    "earthquake": "Magnitude 6.1 Earthquake - Hill District",
    "fire": "Warehouse Fire - Industrial Estate",
    "cyclone": "Cyclone Vardah Landfall - Coastal Belt",
    "building_collapse": "Residential Building Collapse - MG Road",
}


def run_scenarios(names=None, log=print):
    ctx = _Ctx()
    results = {}
    for name in names or SCENARIOS:
        exists = db.session.execute(select(Incident.id).where(Incident.title == _TITLES[name])).first()
        if exists:
            log(f"  scenario    {name:<18} skipped (already simulated)")
            continue
        incident = SCENARIOS[name](ctx)
        results[name] = incident.id
        log(f"  scenario    {name:<18} -> incident #{incident.id}")
    return results
