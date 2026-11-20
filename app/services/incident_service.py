"""Incident management rules."""
from sqlalchemy import func, select

from ..constants import ACTIVE_ALLOCATION_STATUSES, CLOSED_INCIDENT_STATUSES
from ..extensions import db
from ..models import Incident, ResourceAllocation
from ..utils.errors import ConflictError
from ..utils.time import utcnow
from .activity_service import log_activity
from .common import apply_changes, atomic


def count_active_allocations(incident_id):
    return db.session.execute(
        select(func.count(ResourceAllocation.id)).where(
            ResourceAllocation.incident_id == incident_id,
            ResourceAllocation.status.in_(ACTIVE_ALLOCATION_STATUSES),
        )
    ).scalar_one()


def create_incident(data, actor):
    with atomic():
        incident = Incident(**data, reported_by=actor.id)
        db.session.add(incident)
        db.session.flush()
        log_activity(
            actor,
            "INCIDENT_CREATED",
            "incident",
            incident.id,
            f"{incident.severity} {incident.incident_type} incident registered: {incident.title}",
            {"severity": incident.severity, "type": incident.incident_type, "location": incident.location},
        )
    return incident


def update_incident(incident, data, actor):
    old_status = incident.status
    new_status = data.get("status", old_status)
    closing = new_status in CLOSED_INCIDENT_STATUSES and old_status not in CLOSED_INCIDENT_STATUSES
    reopening = old_status in CLOSED_INCIDENT_STATUSES and new_status not in CLOSED_INCIDENT_STATUSES

    if closing:
        active = count_active_allocations(incident.id)
        if active:
            raise ConflictError(
                "Incident still has active resource allocations",
                {"status": f"Complete or cancel the {active} active allocation(s) before marking it {new_status}."},
            )

    with atomic():
        changes = apply_changes(incident, data)
        if closing:
            incident.resolved_at = utcnow()
        elif reopening:
            incident.resolved_at = None

        if reopening:
            action = "INCIDENT_REOPENED"
        elif "status" in changes:
            action = "INCIDENT_STATUS_CHANGED"
        elif "severity" in changes:
            action = "INCIDENT_SEVERITY_CHANGED"
        else:
            action = "INCIDENT_UPDATED"
        log_activity(actor, action, "incident", incident.id, f"Incident '{incident.title}' updated", {"changes": changes})
    return incident


def delete_incident(incident, actor):
    allocation_count = db.session.execute(
        select(func.count(ResourceAllocation.id)).where(ResourceAllocation.incident_id == incident.id)
    ).scalar_one()
    if allocation_count:
        raise ConflictError(
            "Incident cannot be deleted because resources have been allocated to it",
            {"incident": "Close the incident instead to preserve the allocation history."},
        )
    with atomic():
        log_activity(
            actor, "INCIDENT_DELETED", "incident", incident.id, f"Incident '{incident.title}' deleted",
            {"title": incident.title, "type": incident.incident_type},
        )
        db.session.delete(incident)
