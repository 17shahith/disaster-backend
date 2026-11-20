"""Incident management endpoints."""
from flask import Blueprint, request
from flask_jwt_extended import current_user
from sqlalchemy import or_, select

from ..constants import ACTIVE_INCIDENT_STATUSES, INCIDENT_STATUSES, INCIDENT_TYPES, SEVERITIES, Role
from ..middleware import authenticated, role_required
from ..models import Incident
from ..services import incident_service
from ..services.access import assigned_incident_ids_query, can_view_incident, is_scoped_to_assignments
from ..services.common import get_or_404
from ..utils.errors import ForbiddenError
from ..utils.pagination import filter_choice_arg, paginate
from ..utils.responses import success_response
from ..utils.validators import Field, get_json_body, validate

bp = Blueprint("incidents", __name__, url_prefix="/api/incidents")

INCIDENT_SCHEMA = {
    "title": Field(str, required=True, min_length=3, max_length=200),
    "incident_type": Field(str, required=True, choices=INCIDENT_TYPES),
    "description": Field(str, required=True, max_length=5000),
    "location": Field(str, required=True, max_length=255),
    "latitude": Field(float, nullable=True, min_value=-90, max_value=90),
    "longitude": Field(float, nullable=True, min_value=-180, max_value=180),
    "severity": Field(str, choices=SEVERITIES, default="Medium"),
    "status": Field(str, choices=ACTIVE_INCIDENT_STATUSES, default="Reported"),
    "affected_people": Field(int, min_value=0, default=0),
}
UPDATE_SCHEMA = {**INCIDENT_SCHEMA, "status": Field(str, choices=INCIDENT_STATUSES)}

MANAGERS = (Role.OPERATOR,)


def _get_visible(incident_id):
    incident = get_or_404(Incident, incident_id, "Incident")
    if not can_view_incident(current_user, incident.id):
        raise ForbiddenError("You can only view incidents assigned to your teams")
    return incident


@bp.post("")
@role_required(*MANAGERS)
def create_incident():
    data = validate(get_json_body(), INCIDENT_SCHEMA, message="Invalid incident information")
    incident = incident_service.create_incident(data, current_user)
    return success_response(incident.to_dict(), "Incident created successfully", 201)


@bp.get("")
@authenticated
def list_incidents():
    stmt = select(Incident).order_by(Incident.created_at.desc(), Incident.id.desc())
    if is_scoped_to_assignments(current_user) or request.args.get("assigned") == "true":
        stmt = stmt.where(Incident.id.in_(assigned_incident_ids_query(current_user)))
    for arg, column, choices in (
        ("status", Incident.status, INCIDENT_STATUSES),
        ("severity", Incident.severity, SEVERITIES),
        ("incident_type", Incident.incident_type, INCIDENT_TYPES),
    ):
        value = filter_choice_arg(arg, choices)
        if value:
            stmt = stmt.where(column == value)
    if request.args.get("active") == "true":
        stmt = stmt.where(Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
    search = request.args.get("search")
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Incident.title.ilike(like), Incident.location.ilike(like)))
    return success_response(paginate(stmt), "Incidents retrieved successfully")


@bp.get("/<int:incident_id>")
@authenticated
def get_incident(incident_id):
    incident = _get_visible(incident_id)
    data = incident.to_dict()
    data["requests"] = [r.to_dict() for r in incident.requests]
    data["allocations"] = [a.to_dict() for a in incident.allocations]
    return success_response(data, "Incident retrieved successfully")


@bp.put("/<int:incident_id>")
@role_required(*MANAGERS)
def update_incident(incident_id):
    incident = get_or_404(Incident, incident_id, "Incident")
    data = validate(get_json_body(), UPDATE_SCHEMA, partial=True, message="Invalid incident information")
    incident = incident_service.update_incident(incident, data, current_user)
    return success_response(incident.to_dict(), "Incident updated successfully")


@bp.delete("/<int:incident_id>")
@role_required(Role.ADMIN)
def delete_incident(incident_id):
    incident = get_or_404(Incident, incident_id, "Incident")
    incident_service.delete_incident(incident, current_user)
    return success_response({"id": incident_id}, "Incident deleted successfully")
