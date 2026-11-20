"""Emergency request rules."""
from sqlalchemy import func, select

from ..constants import ACTIVE_ALLOCATION_STATUSES, CLOSED_INCIDENT_STATUSES
from ..extensions import db
from ..models import EmergencyRequest, Incident, ResourceAllocation
from ..utils.errors import ConflictError
from ..utils.time import utcnow
from .activity_service import log_activity
from .common import apply_changes, atomic, get_or_404


def _open_incident(incident_id):
    incident = get_or_404(Incident, incident_id, "Incident")
    if incident.status in CLOSED_INCIDENT_STATUSES:
        raise ConflictError(
            "Emergency requests cannot be linked to a completed or closed incident",
            {"incident_id": f"Incident status is {incident.status}. Reopen it first."},
        )
    return incident


def create_request(data, actor):
    incident = _open_incident(data["incident_id"])
    with atomic():
        fields = {**data, "location": data.get("location") or incident.location}
        req = EmergencyRequest(**fields, requested_by=actor.id)
        db.session.add(req)
        db.session.flush()
        log_activity(
            actor, "REQUEST_CREATED", "emergency_request", req.id,
            f"{req.priority} priority {req.category} request created for incident #{incident.id}",
            {"incident_id": incident.id, "category": req.category, "priority": req.priority},
        )
    return req


def update_request(req, data, actor):
    if "incident_id" in data and data["incident_id"] != req.incident_id:
        _open_incident(data["incident_id"])
    with atomic():
        changes = apply_changes(req, data)
        if "status" in changes:
            if req.status == "Completed":
                req.completed_at = utcnow()
            else:
                req.completed_at = None
        action = "REQUEST_COMPLETED" if changes.get("status", {}).get("to") == "Completed" else "REQUEST_UPDATED"
        log_activity(actor, action, "emergency_request", req.id, f"Emergency request #{req.id} updated", {"changes": changes})
    return req


def delete_request(req, actor):
    active = db.session.execute(
        select(func.count(ResourceAllocation.id)).where(
            ResourceAllocation.request_id == req.id,
            ResourceAllocation.status.in_(ACTIVE_ALLOCATION_STATUSES),
        )
    ).scalar_one()
    if active:
        raise ConflictError(
            "Emergency request has active allocations and cannot be deleted",
            {"request": "Cancel the request or complete its allocations first."},
        )
    with atomic():
        log_activity(
            actor, "REQUEST_DELETED", "emergency_request", req.id, f"Emergency request #{req.id} deleted",
            {"incident_id": req.incident_id, "category": req.category},
        )
        db.session.delete(req)


def mark_in_progress(req):
    """Called when resources are allocated against a pending request."""
    if req is not None and req.status == "Pending":
        req.status = "In Progress"
