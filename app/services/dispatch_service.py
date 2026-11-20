"""Dispatch operations: moving allocated resources to the field.

Inventory is deducted when a dispatch moves to ``Dispatched`` (stock leaves the
warehouse). Supply/shelter allocations complete automatically once their full
quantity has been delivered and the dispatches are completed.
"""
from ..constants import CLOSED_INCIDENT_STATUSES, DISPATCH_STATUSES, DISPATCH_TRANSITIONS, Role
from ..extensions import db
from ..models import DispatchRecord, ResourceAllocation, ResponseTeam
from ..utils.errors import ConflictError, ForbiddenError, ValidationError
from ..utils.time import utcnow
from . import supply_service, team_service
from .activity_service import log_activity
from .common import apply_changes, atomic, get_or_404

DISPATCHABLE_ALLOCATION_STATUSES = ("Approved", "Allocated")
PREPARED_ONLY_FIELDS = ("quantity", "team_id")
TEAM_LEAD_FIELDS = {"status", "completion_notes", "notes"}


def _validate_team(team_id, allocation):
    if allocation.resource_type == "Team":
        if team_id is not None and team_id != allocation.team_id:
            raise ValidationError("Invalid team", {"team_id": "Must match the team in the allocation."})
        return allocation.team
    if team_id is None:
        return None
    team = get_or_404(ResponseTeam, team_id, "Response team")
    if team.availability == "Unavailable":
        raise ConflictError(f"Response team '{team.name}' is unavailable", {"team_id": "Team is unavailable."})
    return team


def create_dispatch(data, actor):
    allocation = get_or_404(ResourceAllocation, data["allocation_id"], "Allocation")
    if allocation.status not in DISPATCHABLE_ALLOCATION_STATUSES:
        raise ConflictError(
            "Dispatch records can only be created for approved or allocated allocations",
            {"allocation_id": f"Allocation status is {allocation.status}."},
        )
    if allocation.incident.status in CLOSED_INCIDENT_STATUSES:
        raise ConflictError("Incident is completed or closed", {"allocation_id": "Reopen the incident first."})

    remaining = allocation.quantity - allocation.dispatched_total
    if remaining <= 0:
        raise ConflictError("The full allocated quantity has already been dispatched",
                            {"allocation_id": "Nothing left to dispatch."})
    quantity = data.get("quantity") or remaining
    if quantity > remaining:
        raise ValidationError("Dispatch quantity exceeds the remaining allocated quantity",
                              {"quantity": f"Maximum dispatchable quantity is {remaining}."})
    team = _validate_team(data.get("team_id"), allocation)

    default_origin = {
        "Supply": allocation.supply.warehouse_location if allocation.supply else None,
        "Team": allocation.team.base_location if allocation.team else None,
        "Shelter": None,
    }[allocation.resource_type]

    with atomic():
        dispatch = DispatchRecord(
            allocation_id=allocation.id,
            team_id=team.id if team else None,
            quantity=quantity,
            status="Prepared",
            origin=data.get("origin") or default_origin,
            destination=data.get("destination") or (
                allocation.shelter.location if allocation.resource_type == "Shelter" else allocation.incident.location
            ),
            vehicle_details=data.get("vehicle_details"),
            notes=data.get("notes"),
            created_by=actor.id,
        )
        db.session.add(dispatch)
        db.session.flush()
        log_activity(
            actor, "DISPATCH_CREATED", "dispatch", dispatch.id,
            f"Dispatch prepared: {quantity} x {allocation.resource_name} for incident #{allocation.incident_id}",
            {"allocation_id": allocation.id, "quantity": quantity, "team_id": dispatch.team_id},
        )
    return dispatch


def _check_permissions(dispatch, data, actor):
    if actor.role != Role.TEAM_LEAD:
        return
    team = dispatch.team or dispatch.allocation.team
    if team is None or team.lead_id != actor.id:
        raise ForbiddenError("Response team leads can only update dispatches assigned to their teams")
    disallowed = set(data) - TEAM_LEAD_FIELDS
    if disallowed:
        raise ForbiddenError("Response team leads may only update status and notes",
                             {field: "Not permitted for your role." for field in disallowed})
    if data.get("status") in ("Prepared", "Dispatched"):
        raise ForbiddenError("Response team leads may only record transit, delivery and completion")


def _apply_status(dispatch, new_status, actor):
    allowed = DISPATCH_TRANSITIONS[dispatch.status]
    if new_status not in allowed:
        raise ConflictError(
            f"Invalid dispatch status change from {dispatch.status} to {new_status}",
            {"status": "Allowed next statuses: " + (", ".join(allowed) if allowed else "none (final state)")},
        )
    allocation = dispatch.allocation
    now = utcnow()

    if new_status == "Dispatched":
        if allocation.status not in DISPATCHABLE_ALLOCATION_STATUSES:
            raise ConflictError("Allocation is no longer active", {"status": f"Allocation status is {allocation.status}."})
        if allocation.resource_type == "Supply":
            supply_service.deduct_for_dispatch(allocation.supply, dispatch.quantity, actor, allocation.id, dispatch.id)
        elif allocation.resource_type == "Team":
            team_service.mark_busy(allocation.team)
        if allocation.status == "Approved":
            allocation.status = "Allocated"
            allocation.allocated_at = now
        dispatch.dispatched_at = now
    elif new_status == "In Transit":
        dispatch.in_transit_at = now
    elif new_status == "Delivered":
        dispatch.delivered_at = now
    elif new_status == "Completed":
        dispatch.completed_at = now

    dispatch.status = new_status

    if new_status == "Completed" and allocation.resource_type in ("Supply", "Shelter"):
        completed_total = sum(d.quantity for d in allocation.dispatches if d.status == "Completed")
        if completed_total >= allocation.quantity and allocation.status == "Allocated":
            allocation.status = "Completed"
            allocation.completed_at = now
            log_activity(actor, "ALLOCATION_COMPLETED", "allocation", allocation.id,
                         f"Allocation #{allocation.id} completed after full delivery")


def update_dispatch(dispatch, data, actor):
    _check_permissions(dispatch, data, actor)
    for field in PREPARED_ONLY_FIELDS:
        if field in data and dispatch.status != "Prepared":
            raise ConflictError(f"'{field}' can only be changed while the dispatch is Prepared",
                                {field: f"Dispatch status is {dispatch.status}."})
    allocation = dispatch.allocation
    if "quantity" in data:
        remaining = allocation.quantity - allocation.dispatched_total + dispatch.quantity
        if data["quantity"] > remaining:
            raise ValidationError("Dispatch quantity exceeds the remaining allocated quantity",
                                  {"quantity": f"Maximum dispatchable quantity is {remaining}."})
    if "team_id" in data:
        _validate_team(data["team_id"], allocation)

    new_status = data.pop("status", None)
    with atomic():
        changes = apply_changes(dispatch, data)
        if new_status and new_status != dispatch.status:
            changes["status"] = {"from": dispatch.status, "to": new_status}
            _apply_status(dispatch, new_status, actor)
        action = "DISPATCH_STATUS_CHANGED" if "status" in changes else "DISPATCH_UPDATED"
        log_activity(actor, action, "dispatch", dispatch.id, f"Dispatch #{dispatch.id} updated", {"changes": changes})
    return dispatch


def delete_dispatch(dispatch, actor):
    if dispatch.status != "Prepared":
        raise ConflictError("Only dispatches in 'Prepared' status can be deleted",
                            {"status": f"Dispatch status is {dispatch.status}."})
    with atomic():
        log_activity(actor, "DISPATCH_DELETED", "dispatch", dispatch.id, f"Prepared dispatch #{dispatch.id} deleted",
                     {"allocation_id": dispatch.allocation_id})
        db.session.delete(dispatch)


__all__ = ["DISPATCH_STATUSES", "create_dispatch", "update_dispatch", "delete_dispatch"]
