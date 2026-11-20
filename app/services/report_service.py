"""Dashboard metrics and situation reports (computed live from the database)."""
from sqlalchemy import func, select

from ..constants import (
    ACTIVE_ALLOCATION_STATUSES,
    ACTIVE_INCIDENT_STATUSES,
    ACTIVE_SHELTER_STATUSES,
    ALLOCATION_STATUSES,
    DISPATCH_STATUSES,
    IN_FLIGHT_DISPATCH_STATUSES,
    INCIDENT_STATUSES,
    INCIDENT_TYPES,
    REQUEST_CATEGORIES,
    REQUEST_STATUSES,
    RESOURCE_TYPES,
    SEVERITIES,
    SHELTER_STATUSES,
    SUPPLY_CATEGORIES,
    TEAM_AVAILABILITY,
    TEAM_TYPES,
)
from ..extensions import db
from ..models import (
    DispatchRecord,
    EmergencyRequest,
    Incident,
    ReliefSupply,
    ResourceAllocation,
    ResponseTeam,
    Shelter,
)
from ..utils.time import isoformat, utcnow
from .supply_service import low_stock_condition


def _scalar(stmt):
    return db.session.execute(stmt).scalar_one() or 0


def _count(model, *conditions):
    return _scalar(select(func.count(model.id)).where(*conditions))


def _grouped(column, keys, *conditions):
    """Count rows per value of ``column``, including zero buckets for every known key."""
    rows = db.session.execute(select(column, func.count()).where(*conditions).group_by(column)).all()
    counts = {key: 0 for key in keys}
    counts.update({value: count for value, count in rows})
    return counts


def _pct(part, whole):
    return round(part * 100.0 / whole, 2) if whole else 0.0


def dashboard():
    available_supplies = _scalar(select(func.sum(ReliefSupply.quantity - ReliefSupply.reserved_quantity)))
    return {
        "generated_at": isoformat(utcnow()),
        "total_incidents": _count(Incident),
        "active_incidents": _count(Incident, Incident.status.in_(ACTIVE_INCIDENT_STATUSES)),
        "critical_incidents": _count(
            Incident, Incident.severity == "Critical", Incident.status.in_(ACTIVE_INCIDENT_STATUSES)
        ),
        "pending_requests": _count(EmergencyRequest, EmergencyRequest.status == "Pending"),
        "open_requests": _count(EmergencyRequest, EmergencyRequest.status.in_(("Pending", "In Progress"))),
        "available_teams": _count(ResponseTeam, ResponseTeam.availability == "Available"),
        "total_teams": _count(ResponseTeam),
        "active_shelters": _count(Shelter, Shelter.status.in_(ACTIVE_SHELTER_STATUSES)),
        "available_shelter_beds": _scalar(
            select(func.sum(Shelter.capacity - Shelter.current_occupancy)).where(Shelter.status == "Open")
        ),
        "total_available_supplies": available_supplies,
        "supply_items": _count(ReliefSupply),
        "low_stock_items": _count(ReliefSupply, low_stock_condition()),
        "active_allocations": _count(ResourceAllocation, ResourceAllocation.status.in_(ACTIVE_ALLOCATION_STATUSES)),
        "dispatched_resources": _count(DispatchRecord, DispatchRecord.status.in_(IN_FLIGHT_DISPATCH_STATUSES)),
        "dispatched_quantity_total": _scalar(select(func.sum(ReliefSupply.dispatched_quantity))),
        "completed_operations": {
            "allocations": _count(ResourceAllocation, ResourceAllocation.status == "Completed"),
            "dispatches": _count(DispatchRecord, DispatchRecord.status == "Completed"),
            "requests": _count(EmergencyRequest, EmergencyRequest.status == "Completed"),
            "incidents": _count(Incident, Incident.status.in_(("Completed", "Closed"))),
        },
    }


def incident_report():
    recent = db.session.execute(
        select(Incident).order_by(Incident.created_at.desc(), Incident.id.desc()).limit(10)
    ).scalars().all()
    critical_active = db.session.execute(
        select(Incident)
        .where(Incident.severity == "Critical", Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
        .order_by(Incident.created_at.desc())
    ).scalars().all()
    return {
        "total": _count(Incident),
        "by_type": _grouped(Incident.incident_type, INCIDENT_TYPES),
        "by_severity": _grouped(Incident.severity, SEVERITIES),
        "by_status": _grouped(Incident.status, INCIDENT_STATUSES),
        "affected_people": _scalar(select(func.sum(Incident.affected_people))),
        "requests": {
            "total": _count(EmergencyRequest),
            "by_category": _grouped(EmergencyRequest.category, REQUEST_CATEGORIES),
            "by_status": _grouped(EmergencyRequest.status, REQUEST_STATUSES),
            "by_priority": _grouped(EmergencyRequest.priority, SEVERITIES),
        },
        "critical_active_incidents": [
            {"id": i.id, "title": i.title, "type": i.incident_type, "location": i.location, "status": i.status}
            for i in critical_active
        ],
        "recent_incidents": [
            {"id": i.id, "title": i.title, "type": i.incident_type, "severity": i.severity,
             "status": i.status, "created_at": isoformat(i.created_at)}
            for i in recent
        ],
    }


def resource_report():
    supplies = db.session.execute(select(ReliefSupply).order_by(ReliefSupply.category, ReliefSupply.name)).scalars().all()
    by_category = {
        category: {"items": 0, "quantity": 0, "reserved": 0, "available": 0, "dispatched": 0}
        for category in SUPPLY_CATEGORIES
    }
    for s in supplies:
        bucket = by_category[s.category]
        bucket["items"] += 1
        bucket["quantity"] += s.quantity
        bucket["reserved"] += s.reserved_quantity
        bucket["available"] += s.available_quantity
        bucket["dispatched"] += s.dispatched_quantity

    return {
        "supplies": [
            {
                "id": s.id,
                "name": s.name,
                "category": s.category,
                "unit": s.unit,
                "quantity": s.quantity,
                "reserved": s.reserved_quantity,
                "available": s.available_quantity,
                "dispatched": s.dispatched_quantity,
                # Share of all stock ever held that has been dispatched or is reserved.
                "utilization_rate": _pct(s.dispatched_quantity + s.reserved_quantity,
                                         s.quantity + s.dispatched_quantity),
                "is_low_stock": s.is_low_stock,
            }
            for s in supplies
        ],
        "by_category": by_category,
        "low_stock_items": [
            {"id": s.id, "name": s.name, "available": s.available_quantity, "threshold": s.low_stock_threshold,
             "unit": s.unit}
            for s in supplies if s.is_low_stock
        ],
        "allocations": {
            "total": _count(ResourceAllocation),
            "by_status": _grouped(ResourceAllocation.status, ALLOCATION_STATUSES),
            "by_resource_type": _grouped(ResourceAllocation.resource_type, RESOURCE_TYPES),
            "active_by_resource_type": _grouped(
                ResourceAllocation.resource_type, RESOURCE_TYPES,
                ResourceAllocation.status.in_(ACTIVE_ALLOCATION_STATUSES),
            ),
        },
        "dispatches": {
            "total": _count(DispatchRecord),
            "by_status": _grouped(DispatchRecord.status, DISPATCH_STATUSES),
        },
    }


def shelter_report():
    shelters = db.session.execute(select(Shelter).order_by(Shelter.name)).scalars().all()
    capacity = sum(s.capacity for s in shelters)
    occupancy = sum(s.current_occupancy for s in shelters)
    return {
        "total_shelters": len(shelters),
        "by_status": _grouped(Shelter.status, SHELTER_STATUSES),
        "total_capacity": capacity,
        "total_occupancy": occupancy,
        "total_available_beds": sum(s.available_beds for s in shelters if s.status == "Open"),
        "overall_occupancy_rate": _pct(occupancy, capacity),
        "shelters": [
            {
                "id": s.id,
                "name": s.name,
                "location": s.location,
                "status": s.status,
                "capacity": s.capacity,
                "current_occupancy": s.current_occupancy,
                "available_beds": s.available_beds,
                "occupancy_rate": s.occupancy_rate,
            }
            for s in shelters
        ],
    }


def team_report():
    teams = db.session.execute(select(ResponseTeam).order_by(ResponseTeam.name)).scalars().all()
    completed_counts = dict(
        db.session.execute(
            select(ResourceAllocation.team_id, func.count())
            .where(ResourceAllocation.team_id.is_not(None), ResourceAllocation.status == "Completed")
            .group_by(ResourceAllocation.team_id)
        ).all()
    )
    total = len(teams)
    by_availability = _grouped(ResponseTeam.availability, TEAM_AVAILABILITY)
    return {
        "total_teams": total,
        "total_personnel": sum(t.member_count for t in teams),
        "by_availability": by_availability,
        "by_type": _grouped(ResponseTeam.team_type, TEAM_TYPES),
        "availability_rate": _pct(by_availability.get("Available", 0), total),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "team_type": t.team_type,
                "availability": t.availability,
                "member_count": t.member_count,
                "lead": t.lead.to_summary() if t.lead else None,
                "current_incident_id": t.current_incident_id,
                "completed_assignments": completed_counts.get(t.id, 0),
            }
            for t in teams
        ],
    }
