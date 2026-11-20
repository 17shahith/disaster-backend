"""Shelter management and capacity rules."""
from sqlalchemy import case, func, select, update

from ..extensions import db
from ..models import ResourceAllocation, Shelter
from ..utils.errors import ConflictError, ValidationError
from .activity_service import log_activity
from .common import apply_changes, atomic


def _sync_status(shelter):
    """Open/Full follow occupancy automatically; Closed/Under Maintenance are left alone."""
    if shelter.status in ("Open", "Full"):
        shelter.status = "Full" if shelter.current_occupancy >= shelter.capacity else "Open"


def _validate_capacity(capacity, occupancy):
    if occupancy > capacity:
        raise ValidationError(
            "Shelter occupancy cannot exceed its maximum capacity",
            {"current_occupancy": f"Occupancy ({occupancy}) exceeds capacity ({capacity})."},
        )


def _ensure_unique_name(name, exclude_id=None):
    stmt = select(Shelter.id).where(func.lower(Shelter.name) == name.lower())
    if exclude_id:
        stmt = stmt.where(Shelter.id != exclude_id)
    if db.session.execute(stmt).first():
        raise ConflictError("A shelter with this name already exists", {"name": "Must be unique."})


def create_shelter(data, actor):
    _validate_capacity(data["capacity"], data.get("current_occupancy", 0))
    _ensure_unique_name(data["name"])
    with atomic():
        shelter = Shelter(**data)
        _sync_status(shelter)
        db.session.add(shelter)
        db.session.flush()
        log_activity(actor, "SHELTER_CREATED", "shelter", shelter.id, f"Shelter '{shelter.name}' registered",
                     {"capacity": shelter.capacity})
    return shelter


def update_shelter(shelter, data, actor):
    _validate_capacity(data.get("capacity", shelter.capacity), data.get("current_occupancy", shelter.current_occupancy))
    if "name" in data:
        _ensure_unique_name(data["name"], exclude_id=shelter.id)
    with atomic():
        changes = apply_changes(shelter, data)
        if "status" not in data:
            _sync_status(shelter)
        elif shelter.status == "Open" and shelter.current_occupancy >= shelter.capacity:
            shelter.status = "Full"
        action = "SHELTER_OCCUPANCY_UPDATED" if "current_occupancy" in changes else "SHELTER_UPDATED"
        log_activity(actor, action, "shelter", shelter.id, f"Shelter '{shelter.name}' updated", {"changes": changes})
    return shelter


def delete_shelter(shelter, actor):
    if shelter.current_occupancy > 0:
        raise ConflictError("Shelter is currently occupied and cannot be deleted",
                            {"current_occupancy": shelter.current_occupancy})
    used = db.session.execute(
        select(func.count(ResourceAllocation.id)).where(ResourceAllocation.shelter_id == shelter.id)
    ).scalar_one()
    if used:
        raise ConflictError("Shelter has allocation history and cannot be deleted",
                            {"shelter": "Set its status to 'Closed' instead."})
    with atomic():
        log_activity(actor, "SHELTER_DELETED", "shelter", shelter.id, f"Shelter '{shelter.name}' deleted")
        db.session.delete(shelter)


# --- occupancy changes used by the allocation service ------------------------

def occupy(shelter, people):
    """Atomically add ``people`` to an Open shelter without exceeding capacity."""
    result = db.session.execute(
        update(Shelter)
        .where(
            Shelter.id == shelter.id,
            Shelter.status == "Open",
            Shelter.current_occupancy + people <= Shelter.capacity,
        )
        .values(current_occupancy=Shelter.current_occupancy + people)
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(shelter)
    if result.rowcount != 1:
        if shelter.status != "Open":
            detail = f"Shelter status is {shelter.status}."
        else:
            detail = f"Only {shelter.available_beds} bed(s) available; {people} requested."
        raise ConflictError("Shelter cannot accommodate the requested number of people", {"shelter_id": detail})
    _sync_status(shelter)


def vacate(shelter, people):
    db.session.execute(
        update(Shelter)
        .where(Shelter.id == shelter.id)
        .values(
            current_occupancy=case(
                (Shelter.current_occupancy >= people, Shelter.current_occupancy - people), else_=0
            )
        )
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(shelter)
    _sync_status(shelter)
