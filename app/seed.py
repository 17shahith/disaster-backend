"""Demonstration seed data (users, teams, shelters, supplies).

Seeding goes through the service layer so every record is validated and
logged exactly as if it had been created through the API. Re-running is safe:
existing records (matched by unique name) are skipped.
"""
from flask import current_app
from sqlalchemy import func, select

from .constants import Role
from .extensions import db
from .models import ReliefSupply, ResponseTeam, Shelter, User
from .services import shelter_service, supply_service, team_service, user_service

USERS = [
    {"username": "admin", "email": "admin@drrc.local", "full_name": "System Administrator", "role": Role.ADMIN},
    {"username": "operator", "email": "operator@drrc.local", "full_name": "Priya Control Room",
     "role": Role.OPERATOR},
    {"username": "teamlead", "email": "teamlead@drrc.local", "full_name": "Arjun Team Lead",
     "role": Role.TEAM_LEAD},
    {"username": "teamlead2", "email": "teamlead2@drrc.local", "full_name": "Meera Team Lead",
     "role": Role.TEAM_LEAD},
    {"username": "coordinator", "email": "coordinator@drrc.local", "full_name": "Ravi Relief Coordinator",
     "role": Role.COORDINATOR},
]

TEAMS = [
    ("Alpha Rescue Squad", "Rescue", 12, "teamlead", "North Fire Station", "Inflatable boats, ropes, life jackets"),
    ("Bravo Medical Unit", "Medical", 8, "teamlead", "District Hospital", "Ambulances, trauma kits"),
    ("Charlie Fire Brigade", "Fire", 15, "teamlead2", "Central Fire Station", "Fire tenders, breathing apparatus"),
    ("Delta Search and Rescue", "Search and Rescue", 10, "teamlead2", "Civil Defence HQ",
     "Thermal cameras, search dogs"),
    ("Echo Logistics Team", "Logistics", 6, "teamlead", "Central Warehouse", "Trucks, forklifts"),
    ("Foxtrot Rescue Unit", "Rescue", 9, "teamlead2", "East Fire Station", "Hydraulic tools, stretchers"),
    ("Golf Medical Response", "Medical", 7, "teamlead", "City Medical College", "Mobile clinic"),
    ("Hotel Search Team", "Search and Rescue", 8, "teamlead2", "Civil Defence Sub-station", "Drones, radios"),
]

SHELTERS = [
    ("City Community Hall", "Ward 4, Main Road", 300, "Anita Sharma", "+91 98400 11111", "Kitchen, toilets, power backup"),
    ("Government School Shelter", "School Lane, Ward 7", 200, "K. Ramesh", "+91 98400 22222", "Classrooms, water tank"),
    ("Stadium Relief Camp", "Municipal Stadium", 1000, "Sunil Varma", "+91 98400 33333", "Open ground, medical tent"),
    ("Riverside Temple Hall", "Riverside Road", 150, "Lakshmi Iyer", "+91 98400 44444", "Kitchen"),
    ("Hilltop College Shelter", "College Road, Hill Area", 400, "Dr. Farhan Ali", "+91 98400 55555",
     "Dormitories, generator"),
]

SUPPLIES = [
    ("Rice Bags", "Food", "kg", 5000, 500, "Central Warehouse"),
    ("Ready-to-eat Meal Packs", "Food", "packs", 3000, 300, "Central Warehouse"),
    ("Bottled Drinking Water", "Drinking Water", "litres", 10000, 1000, "Central Warehouse"),
    ("Water Purification Tablets", "Drinking Water", "strips", 4000, 400, "North Depot"),
    ("First Aid Kits", "Medicine", "kits", 600, 60, "Medical Store"),
    ("Antibiotics", "Medicine", "boxes", 800, 80, "Medical Store"),
    ("Blankets", "Clothing", "pieces", 1500, 150, "North Depot"),
    ("Life Jackets", "Rescue Equipment", "pieces", 300, 30, "North Depot"),
    ("Hydraulic Rescue Cutters", "Rescue Equipment", "sets", 12, 2, "Civil Defence HQ"),
    ("Tarpaulin Sheets", "Other", "sheets", 700, 70, "Central Warehouse"),
]


def _exists(model, name):
    return db.session.execute(
        select(model.id).where(func.lower(model.name) == name.lower())
    ).first() is not None


def _user(username):
    return db.session.execute(select(User).where(User.username == username)).scalar_one_or_none()


def seed_base_data(log=print):
    password = current_app.config["SEED_DEFAULT_PASSWORD"]
    admin = _user("admin")
    for spec in USERS:
        if _user(spec["username"]):
            continue
        user = user_service.create_user({**spec, "password": password}, actor=admin or user_service.SYSTEM)
        admin = admin or user
        log(f"  user        {user.username:<12} ({user.role})")

    for name, team_type, members, lead, base, equipment in TEAMS:
        if _exists(ResponseTeam, name):
            continue
        team_service.create_team(
            {"name": name, "team_type": team_type, "member_count": members, "lead_id": _user(lead).id,
             "base_location": base, "equipment": equipment, "contact_phone": "+91 100 200 300",
             "availability": "Available"},
            admin,
        )
        log(f"  team        {name}")

    for name, location, capacity, contact, phone, facilities in SHELTERS:
        if _exists(Shelter, name):
            continue
        shelter_service.create_shelter(
            {"name": name, "location": location, "capacity": capacity, "current_occupancy": 0, "status": "Open",
             "contact_person": contact, "contact_phone": phone, "facilities": facilities},
            admin,
        )
        log(f"  shelter     {name}")

    for name, category, unit, quantity, threshold, warehouse in SUPPLIES:
        if _exists(ReliefSupply, name):
            continue
        supply_service.create_supply(
            {"name": name, "category": category, "unit": unit, "quantity": quantity,
             "low_stock_threshold": threshold, "warehouse_location": warehouse},
            admin,
        )
        log(f"  supply      {name} ({quantity} {unit})")
