"""Response team management and availability rules."""
from sqlalchemy import func, select, update

from ..constants import ACTIVE_ALLOCATION_STATUSES, Role
from ..extensions import db
from ..models import ActivityLog, DispatchRecord, ResourceAllocation, ResponseTeam, User
from ..utils.errors import ConflictError, ForbiddenError, ValidationError
from .activity_service import log_activity
from .common import apply_changes, atomic, get_or_404


def active_allocation_for(team_id):
    return db.session.execute(
        select(ResourceAllocation).where(
            ResourceAllocation.team_id == team_id,
            ResourceAllocation.status.in_(ACTIVE_ALLOCATION_STATUSES),
        )
    ).scalar_one_or_none()


def ensure_can_manage(team, actor):
    if actor.role == Role.TEAM_LEAD and team.lead_id != actor.id:
        raise ForbiddenError("Response team leads can only manage their own teams")


def _validate_lead(lead_id):
    if lead_id is None:
        return
    lead = get_or_404(User, lead_id, "User")
    if not lead.is_active or lead.role not in (Role.TEAM_LEAD, Role.ADMIN):
        raise ValidationError(
            "Invalid team lead", {"lead_id": "Team lead must be an active response team lead account."}
        )


def _ensure_unique_name(name, exclude_id=None):
    stmt = select(ResponseTeam.id).where(func.lower(ResponseTeam.name) == name.lower())
    if exclude_id:
        stmt = stmt.where(ResponseTeam.id != exclude_id)
    if db.session.execute(stmt).first():
        raise ConflictError("A response team with this name already exists", {"name": "Must be unique."})


def create_team(data, actor):
    if actor.role == Role.TEAM_LEAD:
        if data.get("lead_id") not in (None, actor.id):
            raise ForbiddenError("Response team leads can only register teams they lead")
        data["lead_id"] = actor.id
    _validate_lead(data.get("lead_id"))
    _ensure_unique_name(data["name"])
    with atomic():
        team = ResponseTeam(**data)
        db.session.add(team)
        db.session.flush()
        log_activity(actor, "TEAM_CREATED", "team", team.id, f"Response team '{team.name}' registered",
                     {"team_type": team.team_type, "members": team.member_count})
    return team


def update_team(team, data, actor):
    ensure_can_manage(team, actor)
    if actor.role == Role.TEAM_LEAD and "lead_id" in data and data["lead_id"] != team.lead_id:
        raise ForbiddenError("Only administrators can reassign a team's lead")
    if "lead_id" in data:
        _validate_lead(data["lead_id"])
    if "name" in data:
        _ensure_unique_name(data["name"], exclude_id=team.id)

    new_availability = data.get("availability")
    if new_availability and new_availability != team.availability:
        active = active_allocation_for(team.id)
        if active is not None and new_availability in ("Available", "Unavailable"):
            raise ConflictError(
                "Team has an active assignment",
                {"availability": f"Complete or cancel allocation #{active.id} before setting the team {new_availability}."},
            )
        if active is None and new_availability == "Assigned":
            raise ValidationError(
                "Invalid availability change",
                {"availability": "Teams become 'Assigned' only through resource allocation."},
            )

    with atomic():
        changes = apply_changes(team, data)
        action = "TEAM_AVAILABILITY_CHANGED" if "availability" in changes else "TEAM_UPDATED"
        log_activity(actor, action, "team", team.id, f"Response team '{team.name}' updated", {"changes": changes})
    return team


def delete_team(team, actor):
    used = db.session.execute(
        select(func.count(ResourceAllocation.id)).where(ResourceAllocation.team_id == team.id)
    ).scalar_one() + db.session.execute(
        select(func.count(DispatchRecord.id)).where(DispatchRecord.team_id == team.id)
    ).scalar_one()
    if used:
        raise ConflictError(
            "Team has allocation or dispatch history and cannot be deleted",
            {"team": "Set its availability to 'Unavailable' instead."},
        )
    with atomic():
        log_activity(actor, "TEAM_DELETED", "team", team.id, f"Response team '{team.name}' deleted")
        db.session.delete(team)


def record_activity(team, data, actor):
    ensure_can_manage(team, actor)
    with atomic():
        entry = log_activity(
            actor, "TEAM_ACTIVITY", "team", team.id, data["activity"],
            {"incident_id": data.get("incident_id"), "notes": data.get("notes"), "team_name": team.name},
        )
    return entry


def team_activity_query(team_id):
    return (
        select(ActivityLog)
        .where(ActivityLog.entity_type == "team", ActivityLog.entity_id == team_id)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    )


# --- availability transitions used by allocation/dispatch services -------------

def assign_team(team, incident_id):
    """Atomically move an Available team to Assigned. Raises Conflict if it is not available."""
    result = db.session.execute(
        update(ResponseTeam)
        .where(ResponseTeam.id == team.id, ResponseTeam.availability == "Available")
        .values(availability="Assigned", current_incident_id=incident_id)
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(team)
    if result.rowcount != 1:
        raise ConflictError(
            f"Response team '{team.name}' is not available",
            {"team_id": f"Current availability is {team.availability}."},
        )


def mark_busy(team):
    if team.availability in ("Assigned", "Available"):
        team.availability = "Busy"


def release_team(team):
    team.current_incident_id = None
    if team.availability != "Unavailable":
        team.availability = "Available"
