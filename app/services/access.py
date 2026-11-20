"""Data-scoping rules for roles that may only see part of the data."""
from sqlalchemy import select, union

from ..constants import Role
from ..models import ResourceAllocation, ResponseTeam


def assigned_incident_ids_query(user):
    """Incident ids a response team lead is assigned to (through any of their teams)."""
    via_allocations = (
        select(ResourceAllocation.incident_id)
        .join(ResponseTeam, ResourceAllocation.team_id == ResponseTeam.id)
        .where(ResponseTeam.lead_id == user.id)
    )
    via_current = select(ResponseTeam.current_incident_id).where(
        ResponseTeam.lead_id == user.id, ResponseTeam.current_incident_id.is_not(None)
    )
    return union(via_allocations, via_current)


def is_scoped_to_assignments(user):
    return user.role == Role.TEAM_LEAD


def can_view_incident(user, incident_id):
    from ..extensions import db

    if not is_scoped_to_assignments(user):
        return True
    ids = db.session.execute(assigned_incident_ids_query(user)).scalars().all()
    return incident_id in ids
