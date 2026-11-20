"""Response team endpoints."""
from flask import Blueprint, request
from flask_jwt_extended import current_user
from sqlalchemy import select

from ..constants import TEAM_AVAILABILITY, TEAM_TYPES, Role
from ..extensions import db
from ..middleware import authenticated, role_required
from ..models import ResourceAllocation, ResponseTeam
from ..services import team_service
from ..services.common import get_or_404
from ..utils.pagination import filter_choice_arg, paginate
from ..utils.responses import success_response
from ..utils.time import isoformat
from ..utils.validators import PHONE_RE, Field, get_json_body, validate

bp = Blueprint("teams", __name__, url_prefix="/api/teams")

TEAM_SCHEMA = {
    "name": Field(str, required=True, min_length=2, max_length=120),
    "team_type": Field(str, required=True, choices=TEAM_TYPES),
    "member_count": Field(int, required=True, min_value=1, max_value=1000),
    "contact_phone": Field(str, nullable=True, pattern=PHONE_RE, pattern_message="Invalid phone number."),
    "base_location": Field(str, nullable=True, max_length=255),
    "equipment": Field(str, nullable=True, max_length=2000),
    "availability": Field(str, choices=("Available", "Unavailable"), default="Available"),
    "lead_id": Field(int, nullable=True, min_value=1),
}
UPDATE_SCHEMA = {**TEAM_SCHEMA, "availability": Field(str, choices=TEAM_AVAILABILITY)}
ACTIVITY_SCHEMA = {
    "activity": Field(str, required=True, min_length=3, max_length=500),
    "incident_id": Field(int, nullable=True, min_value=1),
    "notes": Field(str, nullable=True, max_length=2000),
}


def _list(stmt):
    for arg, column, choices in (
        ("availability", ResponseTeam.availability, TEAM_AVAILABILITY),
        ("team_type", ResponseTeam.team_type, TEAM_TYPES),
    ):
        value = filter_choice_arg(arg, choices)
        if value:
            stmt = stmt.where(column == value)
    if request.args.get("mine") == "true":
        stmt = stmt.where(ResponseTeam.lead_id == current_user.id)
    return paginate(stmt.order_by(ResponseTeam.name))


@bp.post("")
@role_required(Role.TEAM_LEAD)
def create_team():
    data = validate(get_json_body(), TEAM_SCHEMA, message="Invalid response team information")
    team = team_service.create_team(data, current_user)
    return success_response(team.to_dict(), "Response team registered successfully", 201)


@bp.get("")
@authenticated
def list_teams():
    return success_response(_list(select(ResponseTeam)), "Response teams retrieved successfully")


@bp.get("/available")
@authenticated
def list_available_teams():
    stmt = select(ResponseTeam).where(ResponseTeam.availability == "Available")
    return success_response(_list(stmt), "Available response teams retrieved successfully")


@bp.get("/<int:team_id>")
@authenticated
def get_team(team_id):
    team = get_or_404(ResponseTeam, team_id, "Response team")
    data = team.to_dict()
    active = team_service.active_allocation_for(team.id)
    data["active_allocation"] = active.to_dict() if active else None
    history = db.session.execute(
        select(ResourceAllocation).where(ResourceAllocation.team_id == team.id).order_by(ResourceAllocation.id.desc())
    ).scalars()
    data["assignment_history"] = [
        {"allocation_id": a.id, "incident_id": a.incident_id, "status": a.status,
         "created_at": isoformat(a.created_at), "completed_at": isoformat(a.completed_at)}
        for a in history
    ]
    return success_response(data, "Response team retrieved successfully")


@bp.put("/<int:team_id>")
@role_required(Role.TEAM_LEAD)
def update_team(team_id):
    team = get_or_404(ResponseTeam, team_id, "Response team")
    data = validate(get_json_body(), UPDATE_SCHEMA, partial=True, message="Invalid response team information")
    team = team_service.update_team(team, data, current_user)
    return success_response(team.to_dict(), "Response team updated successfully")


@bp.delete("/<int:team_id>")
@role_required(Role.ADMIN)
def delete_team(team_id):
    team = get_or_404(ResponseTeam, team_id, "Response team")
    team_service.delete_team(team, current_user)
    return success_response({"id": team_id}, "Response team deleted successfully")


@bp.get("/<int:team_id>/activities")
@authenticated
def list_team_activities(team_id):
    get_or_404(ResponseTeam, team_id, "Response team")
    return success_response(paginate(team_service.team_activity_query(team_id)), "Team activities retrieved successfully")


@bp.post("/<int:team_id>/activities")
@role_required(Role.TEAM_LEAD)
def record_team_activity(team_id):
    team = get_or_404(ResponseTeam, team_id, "Response team")
    data = validate(get_json_body(), ACTIVITY_SCHEMA, message="Invalid team activity")
    entry = team_service.record_activity(team, data, current_user)
    return success_response(entry.to_dict(), "Team activity recorded successfully", 201)
