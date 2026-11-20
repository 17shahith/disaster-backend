"""Emergency request endpoints."""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import select

from ..constants import PRIORITIES, REQUEST_CATEGORIES, REQUEST_STATUSES, Role
from ..middleware import authenticated, role_required
from ..models import EmergencyRequest
from ..services import request_service
from ..services.access import assigned_incident_ids_query, can_view_incident, is_scoped_to_assignments
from ..services.common import get_or_404
from ..utils.errors import ForbiddenError
from ..utils.pagination import filter_choice_arg, int_arg, paginate
from ..utils.responses import success_response
from ..utils.validators import PHONE_RE, Field, get_json_body, validate

bp = Blueprint("requests", __name__, url_prefix="/api/requests")

REQUEST_SCHEMA = {
    "incident_id": Field(int, required=True, min_value=1),
    "category": Field(str, required=True, choices=REQUEST_CATEGORIES),
    "description": Field(str, required=True, max_length=5000),
    "location": Field(str, nullable=True, max_length=255),
    "priority": Field(str, choices=PRIORITIES, default="Medium"),
    "people_affected": Field(int, min_value=0, default=0),
    "quantity_requested": Field(int, nullable=True, min_value=1),
    "contact_name": Field(str, nullable=True, max_length=120),
    "contact_phone": Field(str, nullable=True, pattern=PHONE_RE, pattern_message="Invalid phone number."),
}
UPDATE_SCHEMA = {
    **REQUEST_SCHEMA,
    "status": Field(str, choices=REQUEST_STATUSES),
    "completion_notes": Field(str, nullable=True, max_length=5000),
}
TEAM_LEAD_FIELDS = {"status", "completion_notes"}


def _get_visible(request_id):
    req = get_or_404(EmergencyRequest, request_id, "Emergency request")
    if not can_view_incident(current_user, req.incident_id):
        raise ForbiddenError("You can only access requests for incidents assigned to your teams")
    return req


@bp.post("")
@role_required(Role.OPERATOR)
def create_request():
    data = validate(get_json_body(), REQUEST_SCHEMA, message="Invalid emergency request information")
    req = request_service.create_request(data, current_user)
    return success_response(req.to_dict(), "Emergency request created successfully", 201)


@bp.get("")
@authenticated
def list_requests():
    stmt = select(EmergencyRequest)
    if is_scoped_to_assignments(current_user):
        stmt = stmt.where(EmergencyRequest.incident_id.in_(assigned_incident_ids_query(current_user)))
    for arg, column, choices in (
        ("status", EmergencyRequest.status, REQUEST_STATUSES),
        ("priority", EmergencyRequest.priority, PRIORITIES),
        ("category", EmergencyRequest.category, REQUEST_CATEGORIES),
    ):
        value = filter_choice_arg(arg, choices)
        if value:
            stmt = stmt.where(column == value)
    incident_id = int_arg("incident_id")
    if incident_id is not None:
        stmt = stmt.where(EmergencyRequest.incident_id == incident_id)
    stmt = stmt.order_by(EmergencyRequest.created_at.desc(), EmergencyRequest.id.desc())
    return success_response(paginate(stmt), "Emergency requests retrieved successfully")


@bp.get("/<int:request_id>")
@authenticated
def get_request(request_id):
    return success_response(_get_visible(request_id).to_dict(), "Emergency request retrieved successfully")


@bp.put("/<int:request_id>")
@role_required(Role.OPERATOR, Role.COORDINATOR, Role.TEAM_LEAD)
def update_request(request_id):
    req = _get_visible(request_id)
    data = validate(get_json_body(), UPDATE_SCHEMA, partial=True, message="Invalid emergency request information")
    if current_user.role == Role.TEAM_LEAD:
        disallowed = set(data) - TEAM_LEAD_FIELDS
        if disallowed:
            raise ForbiddenError(
                "Response team leads may only update request status and completion notes",
                {field: "Not permitted for your role." for field in disallowed},
            )
    req = request_service.update_request(req, data, current_user)
    return success_response(req.to_dict(), "Emergency request updated successfully")


@bp.delete("/<int:request_id>")
@role_required(Role.OPERATOR)
def delete_request(request_id):
    req = get_or_404(EmergencyRequest, request_id, "Emergency request")
    request_service.delete_request(req, current_user)
    return success_response({"id": request_id}, "Emergency request deleted successfully")
