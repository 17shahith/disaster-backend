"""Resource allocation endpoints."""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import select

from ..constants import ALLOCATION_STATUSES, RESOURCE_TYPES, Role
from ..middleware import authenticated, role_required
from ..models import ResourceAllocation, ResponseTeam
from ..services import allocation_service
from ..services.access import can_view_incident, is_scoped_to_assignments
from ..services.common import get_or_404
from ..utils.errors import ForbiddenError
from ..utils.pagination import filter_choice_arg, int_arg, paginate
from ..utils.responses import success_response
from ..utils.validators import Field, get_json_body, validate

bp = Blueprint("allocations", __name__, url_prefix="/api/allocations")

CREATE_SCHEMA = {
    "incident_id": Field(int, required=True, min_value=1),
    "resource_type": Field(str, required=True, choices=RESOURCE_TYPES),
    "team_id": Field(int, nullable=True, min_value=1),
    "supply_id": Field(int, nullable=True, min_value=1),
    "shelter_id": Field(int, nullable=True, min_value=1),
    "quantity": Field(int, nullable=True, min_value=1, max_value=100_000_000),
    "request_id": Field(int, nullable=True, min_value=1),
    "notes": Field(str, nullable=True, max_length=2000),
}
UPDATE_SCHEMA = {
    "status": Field(str, choices=ALLOCATION_STATUSES),
    "quantity": Field(int, min_value=1, max_value=100_000_000),
    "request_id": Field(int, min_value=1),
    "notes": Field(str, nullable=True, max_length=2000),
    "progress_notes": Field(str, nullable=True, max_length=5000),
    "cancellation_reason": Field(str, max_length=255),
}


@bp.post("")
@role_required(Role.COORDINATOR, Role.OPERATOR)
def create_allocation():
    data = validate(get_json_body(), CREATE_SCHEMA, message="Invalid allocation information")
    allocation = allocation_service.create_allocation(data, current_user)
    return success_response(allocation.to_dict(), "Resource allocated successfully", 201)


@bp.get("")
@authenticated
def list_allocations():
    stmt = select(ResourceAllocation)
    if is_scoped_to_assignments(current_user):
        stmt = stmt.join(ResponseTeam, ResourceAllocation.team_id == ResponseTeam.id).where(
            ResponseTeam.lead_id == current_user.id
        )
    for arg, column, choices in (
        ("status", ResourceAllocation.status, ALLOCATION_STATUSES),
        ("resource_type", ResourceAllocation.resource_type, RESOURCE_TYPES),
    ):
        value = filter_choice_arg(arg, choices)
        if value:
            stmt = stmt.where(column == value)
    for arg in ("incident_id", "team_id", "supply_id", "shelter_id", "request_id"):
        value = int_arg(arg)
        if value is not None:
            stmt = stmt.where(getattr(ResourceAllocation, arg) == value)
    stmt = stmt.order_by(ResourceAllocation.created_at.desc(), ResourceAllocation.id.desc())
    return success_response(paginate(stmt), "Allocations retrieved successfully")


@bp.get("/<int:allocation_id>")
@authenticated
def get_allocation(allocation_id):
    allocation = get_or_404(ResourceAllocation, allocation_id, "Allocation")
    if not can_view_incident(current_user, allocation.incident_id):
        raise ForbiddenError("You can only view allocations for incidents assigned to your teams")
    data = allocation.to_dict()
    data["dispatches"] = [d.to_dict() for d in allocation.dispatches]
    return success_response(data, "Allocation retrieved successfully")


@bp.put("/<int:allocation_id>")
@role_required(Role.COORDINATOR, Role.OPERATOR, Role.TEAM_LEAD)
def update_allocation(allocation_id):
    allocation = get_or_404(ResourceAllocation, allocation_id, "Allocation")
    data = validate(get_json_body(), UPDATE_SCHEMA, partial=True, message="Invalid allocation information")
    allocation = allocation_service.update_allocation(allocation, data, current_user)
    return success_response(allocation.to_dict(), "Allocation updated successfully")
