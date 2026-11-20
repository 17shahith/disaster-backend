"""Resource allocation: assigning teams, supplies and shelter space to incidents.

Every operation runs in a single transaction; resource side effects
(team availability, inventory reservation, shelter occupancy) are applied
atomically with the allocation record, or not at all.
"""
from sqlalchemy import select

from ..constants import (
    ACTIVE_ALLOCATION_STATUSES,
    ALLOCATION_TRANSITIONS,
    CLOSED_INCIDENT_STATUSES,
    OPEN_REQUEST_STATUSES,
    Role,
)
from ..extensions import db
from ..models import EmergencyRequest, Incident, ReliefSupply, ResourceAllocation, ResponseTeam, Shelter
from ..utils.errors import ConflictError, ForbiddenError, ValidationError
from ..utils.time import utcnow
from . import request_service, shelter_service, supply_service, team_service
from .activity_service import log_activity
from .common import atomic, get_or_404

RESOURCE_FIELDS = {"Team": "team_id", "Supply": "supply_id", "Shelter": "shelter_id"}


def _validate_request_link(request_id, incident):
    if request_id is None:
        return None
    req = get_or_404(EmergencyRequest, request_id, "Emergency request")
    if req.incident_id != incident.id:
        raise ValidationError("Invalid emergency request", {"request_id": "Request does not belong to this incident."})
    if req.status not in OPEN_REQUEST_STATUSES:
        raise ConflictError("Emergency request is no longer open", {"request_id": f"Request status is {req.status}."})
    return req


def _find_active_duplicate(incident_id, field, resource_id):
    return db.session.execute(
        select(ResourceAllocation).where(
            ResourceAllocation.incident_id == incident_id,
            getattr(ResourceAllocation, field) == resource_id,
            ResourceAllocation.status.in_(ACTIVE_ALLOCATION_STATUSES),
        )
    ).scalars().first()


def create_allocation(data, actor):
    resource_type = data["resource_type"]
    if actor.role == Role.OPERATOR and resource_type != "Team":
        raise ForbiddenError("Control room operators can only assign response teams")

    field = RESOURCE_FIELDS[resource_type]
    errors = {}
    if data.get(field) is None:
        errors[field] = f"Required when resource_type is {resource_type}."
    for other in RESOURCE_FIELDS.values():
        if other != field and data.get(other) is not None:
            errors[other] = f"Must not be set when resource_type is {resource_type}."
    if resource_type in ("Supply", "Shelter") and data.get("quantity") is None:
        errors["quantity"] = f"Required when resource_type is {resource_type}."
    if errors:
        raise ValidationError("Invalid allocation data", errors)

    incident = get_or_404(Incident, data["incident_id"], "Incident")
    if incident.status in CLOSED_INCIDENT_STATUSES:
        raise ConflictError(
            "Cannot allocate resources to a completed or closed incident",
            {"incident_id": f"Incident status is {incident.status}. Reopen the incident first."},
        )
    req = _validate_request_link(data.get("request_id"), incident)

    model, label = {
        "Team": (ResponseTeam, "Response team"),
        "Supply": (ReliefSupply, "Relief supply"),
        "Shelter": (Shelter, "Shelter"),
    }[resource_type]
    resource = get_or_404(model, data[field], label)

    duplicate = _find_active_duplicate(incident.id, field, resource.id)
    if duplicate is not None:
        raise ConflictError(
            f"{label} already has an active allocation for this incident",
            {field: f"See allocation #{duplicate.id} (status {duplicate.status}); update it instead."},
        )

    with atomic():
        allocation = ResourceAllocation(
            incident_id=incident.id,
            request_id=req.id if req else None,
            resource_type=resource_type,
            notes=data.get("notes"),
            status="Pending",
            allocated_by=actor.id,
            quantity=data.get("quantity") or 1,
        )
        setattr(allocation, field, resource.id)

        if resource_type == "Team":
            active = team_service.active_allocation_for(resource.id)
            if active is not None:
                raise ConflictError(
                    f"Response team '{resource.name}' is already assigned",
                    {"team_id": f"Active allocation #{active.id} for incident #{active.incident_id}."},
                )
            allocation.quantity = resource.member_count
            db.session.add(allocation)
            db.session.flush()
            team_service.assign_team(resource, incident.id)
        elif resource_type == "Supply":
            db.session.add(allocation)
            db.session.flush()
            supply_service.reserve(resource, allocation.quantity, actor, allocation.id)
        else:
            db.session.add(allocation)
            db.session.flush()
            shelter_service.occupy(resource, allocation.quantity)

        request_service.mark_in_progress(req)
        log_activity(
            actor, "ALLOCATION_CREATED", "allocation", allocation.id,
            f"{resource_type} '{resource.name}' allocated to incident #{incident.id}",
            {"incident_id": incident.id, "resource_type": resource_type, "resource_id": resource.id,
             "quantity": allocation.quantity},
        )
    return allocation


def _check_update_permissions(allocation, data, actor):
    if actor.role == Role.TEAM_LEAD:
        if allocation.resource_type != "Team" or allocation.team is None or allocation.team.lead_id != actor.id:
            raise ForbiddenError("Response team leads can only update their own team's assignments")
        disallowed = set(data) - {"status", "progress_notes"}
        if disallowed:
            raise ForbiddenError("Response team leads may only update status and progress notes",
                                 {field: "Not permitted for your role." for field in disallowed})
        if "status" in data and data["status"] not in (allocation.status, "Completed"):
            raise ForbiddenError("Response team leads may only mark assignments as Completed")
    elif actor.role == Role.OPERATOR and allocation.resource_type != "Team":
        raise ForbiddenError("Control room operators can only manage response team assignments")


def _change_quantity(allocation, new_quantity, actor):
    if allocation.status not in ("Pending", "Approved"):
        raise ConflictError("Quantity can only be changed while the allocation is Pending or Approved",
                            {"quantity": f"Allocation status is {allocation.status}."})
    if allocation.resource_type == "Team":
        raise ValidationError("Team allocation quantity is the team size and cannot be changed",
                              {"quantity": "Not editable for team allocations."})
    if new_quantity < allocation.dispatched_total:
        raise ConflictError("Quantity cannot be lower than the amount already dispatched",
                            {"quantity": f"{allocation.dispatched_total} already in dispatch records."})
    delta = new_quantity - allocation.quantity
    if allocation.resource_type == "Supply":
        if delta > 0:
            supply_service.reserve(allocation.supply, delta, actor, allocation.id)
        elif delta < 0:
            supply_service.release(allocation.supply, -delta, actor, allocation.id, "Allocation quantity reduced")
    else:
        if delta > 0:
            shelter_service.occupy(allocation.shelter, delta)
        elif delta < 0:
            shelter_service.vacate(allocation.shelter, -delta)
    allocation.quantity = new_quantity


def _release_resources(allocation, actor, reason):
    """Return everything still held by an allocation (cancellation or completion)."""
    if allocation.resource_type == "Team":
        team_service.release_team(allocation.team)
    elif allocation.resource_type == "Supply":
        undispatched = allocation.quantity - allocation.dispatched_total
        supply_service.release(allocation.supply, undispatched, actor, allocation.id, reason)
    elif allocation.resource_type == "Shelter" and allocation.status != "Completed":
        shelter_service.vacate(allocation.shelter, allocation.quantity)


def transition(allocation, new_status, actor, reason=None):
    old_status = allocation.status
    if new_status == old_status:
        return
    allowed = ALLOCATION_TRANSITIONS[old_status]
    if new_status not in allowed:
        raise ConflictError(
            f"Invalid allocation status change from {old_status} to {new_status}",
            {"status": "Allowed next statuses: " + (", ".join(allowed) if allowed else "none (final state)")},
        )
    now = utcnow()
    if new_status == "Approved":
        allocation.approved_by = actor.id
        allocation.approved_at = now
    elif new_status == "Allocated":
        allocation.allocated_at = now
        if allocation.approved_at is None:
            allocation.approved_at, allocation.approved_by = now, actor.id
    elif new_status == "Completed":
        open_dispatches = [d.id for d in allocation.dispatches if d.status in ("Prepared", "Dispatched", "In Transit")]
        if open_dispatches:
            raise ConflictError(
                "Allocation has dispatches that are not yet delivered",
                {"dispatches": f"Dispatch record(s) {open_dispatches} must be delivered first."},
            )
        if allocation.resource_type == "Team":
            team_service.release_team(allocation.team)
        elif allocation.resource_type == "Supply":
            undispatched = allocation.quantity - allocation.dispatched_total
            supply_service.release(allocation.supply, undispatched, actor, allocation.id,
                                   "Unused reservation released on completion")
        allocation.completed_at = now
    elif new_status == "Cancelled":
        if allocation.dispatches:
            started = [d.id for d in allocation.dispatches if d.status != "Prepared"]
            raise ConflictError(
                "Allocation cannot be cancelled because dispatch records exist",
                {"dispatches": (
                    f"Resources already dispatched in record(s) {started}." if started
                    else "Delete the prepared dispatch records first."
                )},
            )
        _release_resources(allocation, actor, reason or "Allocation cancelled")
        allocation.cancelled_at = now
        allocation.cancellation_reason = reason
    allocation.status = new_status


def update_allocation(allocation, data, actor):
    _check_update_permissions(allocation, data, actor)
    changes = {}
    with atomic():
        if "request_id" in data and data["request_id"] != allocation.request_id:
            req = _validate_request_link(data["request_id"], allocation.incident)
            changes["request_id"] = {"from": allocation.request_id, "to": data["request_id"]}
            allocation.request_id = data["request_id"]
            request_service.mark_in_progress(req)
        if "quantity" in data and data["quantity"] != allocation.quantity:
            changes["quantity"] = {"from": allocation.quantity, "to": data["quantity"]}
            _change_quantity(allocation, data["quantity"], actor)
        for field in ("notes", "progress_notes"):
            if field in data and data[field] != getattr(allocation, field):
                changes[field] = {"from": getattr(allocation, field), "to": data[field]}
                setattr(allocation, field, data[field])
        if "status" in data and data["status"] != allocation.status:
            changes["status"] = {"from": allocation.status, "to": data["status"]}
            transition(allocation, data["status"], actor, data.get("cancellation_reason"))

        action = "ALLOCATION_STATUS_CHANGED" if "status" in changes else "ALLOCATION_UPDATED"
        if "progress_notes" in changes and len(changes) == 1:
            action = "ALLOCATION_PROGRESS_RECORDED"
        log_activity(actor, action, "allocation", allocation.id,
                     f"Allocation #{allocation.id} ({allocation.resource_type}) updated", {"changes": changes})
    return allocation
