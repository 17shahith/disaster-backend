"""Dispatch management endpoints."""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import or_, select

from ..constants import DISPATCH_STATUSES, Role
from ..middleware import authenticated, role_required
from ..models import DispatchRecord, ResourceAllocation, ResponseTeam
from ..services import dispatch_service
from ..services.access import is_scoped_to_assignments
from ..services.common import get_or_404
from ..utils.errors import ForbiddenError
from ..utils.pagination import filter_choice_arg, int_arg, paginate
from ..utils.responses import success_response
from ..utils.validators import Field, get_json_body, validate

bp = Blueprint("dispatch", __name__, url_prefix="/api/dispatch")

CREATE_SCHEMA = {
    "allocation_id": Field(int, required=True, min_value=1),
    "quantity": Field(int, nullable=True, min_value=1, max_value=100_000_000),
    "team_id": Field(int, nullable=True, min_value=1),
    "origin": Field(str, nullable=True, max_length=255),
    "destination": Field(str, nullable=True, max_length=255),
    "vehicle_details": Field(str, nullable=True, max_length=255),
    "notes": Field(str, nullable=True, max_length=2000),
}
UPDATE_SCHEMA = {
    "status": Field(str, choices=DISPATCH_STATUSES),
    "quantity": Field(int, min_value=1, max_value=100_000_000),
    "team_id": Field(int, nullable=True, min_value=1),
    "origin": Field(str, nullable=True, max_length=255),
    "destination": Field(str, max_length=255),
    "vehicle_details": Field(str, nullable=True, max_length=255),
    "notes": Field(str, nullable=True, max_length=2000),
    "completion_notes": Field(str, nullable=True, max_length=5000),
}


def _lead_team_ids():
    return select(ResponseTeam.id).where(ResponseTeam.lead_id == current_user.id)


def _ensure_visible(dispatch):
    if not is_scoped_to_assignments(current_user):
        return
    team = dispatch.team or dispatch.allocation.team
    if team is None or team.lead_id != current_user.id:
        raise ForbiddenError("You can only view dispatches assigned to your teams")


@bp.post("")
@role_required(Role.COORDINATOR)
def create_dispatch():
    data = validate(get_json_body(), CREATE_SCHEMA, message="Invalid dispatch information")
    dispatch = dispatch_service.create_dispatch(data, current_user)
    return success_response(dispatch.to_dict(), "Dispatch record created successfully", 201)


@bp.get("")
@authenticated
def list_dispatches():
    stmt = select(DispatchRecord).join(ResourceAllocation, DispatchRecord.allocation_id == ResourceAllocation.id)
    if is_scoped_to_assignments(current_user):
        team_ids = _lead_team_ids()
        stmt = stmt.where(or_(DispatchRecord.team_id.in_(team_ids), ResourceAllocation.team_id.in_(team_ids)))
    status = filter_choice_arg("status", DISPATCH_STATUSES)
    if status:
        stmt = stmt.where(DispatchRecord.status == status)
    for arg, column in (
        ("allocation_id", DispatchRecord.allocation_id),
        ("team_id", DispatchRecord.team_id),
        ("incident_id", ResourceAllocation.incident_id),
    ):
        value = int_arg(arg)
        if value is not None:
            stmt = stmt.where(column == value)
    stmt = stmt.order_by(DispatchRecord.created_at.desc(), DispatchRecord.id.desc())
    return success_response(paginate(stmt), "Dispatch records retrieved successfully")


@bp.get("/<int:dispatch_id>")
@authenticated
def get_dispatch(dispatch_id):
    dispatch = get_or_404(DispatchRecord, dispatch_id, "Dispatch record")
    _ensure_visible(dispatch)
    return success_response(dispatch.to_dict(), "Dispatch record retrieved successfully")


@bp.put("/<int:dispatch_id>")
@role_required(Role.COORDINATOR, Role.TEAM_LEAD)
def update_dispatch(dispatch_id):
    dispatch = get_or_404(DispatchRecord, dispatch_id, "Dispatch record")
    data = validate(get_json_body(), UPDATE_SCHEMA, partial=True, message="Invalid dispatch information")
    dispatch = dispatch_service.update_dispatch(dispatch, data, current_user)
    return success_response(dispatch.to_dict(), "Dispatch record updated successfully")


@bp.delete("/<int:dispatch_id>")
@role_required(Role.COORDINATOR)
def delete_dispatch(dispatch_id):
    dispatch = get_or_404(DispatchRecord, dispatch_id, "Dispatch record")
    dispatch_service.delete_dispatch(dispatch, current_user)
    return success_response({"id": dispatch_id}, "Dispatch record deleted successfully")
