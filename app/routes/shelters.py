"""Shelter endpoints."""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import select

from ..constants import SHELTER_STATUSES, Role
from ..middleware import authenticated, role_required
from ..models import Shelter
from ..services import shelter_service
from ..services.common import get_or_404
from ..utils.pagination import filter_choice_arg, int_arg, paginate
from ..utils.responses import success_response
from ..utils.validators import PHONE_RE, Field, get_json_body, validate

bp = Blueprint("shelters", __name__, url_prefix="/api/shelters")

SHELTER_SCHEMA = {
    "name": Field(str, required=True, min_length=2, max_length=150),
    "location": Field(str, required=True, max_length=255),
    "capacity": Field(int, required=True, min_value=1, max_value=1_000_000),
    "current_occupancy": Field(int, min_value=0, default=0),
    "status": Field(str, choices=SHELTER_STATUSES, default="Open"),
    "contact_person": Field(str, nullable=True, max_length=120),
    "contact_phone": Field(str, nullable=True, pattern=PHONE_RE, pattern_message="Invalid phone number."),
    "facilities": Field(str, nullable=True, max_length=2000),
}


def _list(stmt):
    status = filter_choice_arg("status", SHELTER_STATUSES)
    if status:
        stmt = stmt.where(Shelter.status == status)
    min_beds = int_arg("min_available_beds")
    if min_beds is not None:
        stmt = stmt.where(Shelter.capacity - Shelter.current_occupancy >= min_beds)
    return paginate(stmt.order_by(Shelter.name))


@bp.post("")
@role_required(Role.COORDINATOR)
def create_shelter():
    data = validate(get_json_body(), SHELTER_SCHEMA, message="Invalid shelter information")
    shelter = shelter_service.create_shelter(data, current_user)
    return success_response(shelter.to_dict(), "Shelter registered successfully", 201)


@bp.get("")
@authenticated
def list_shelters():
    return success_response(_list(select(Shelter)), "Shelters retrieved successfully")


@bp.get("/available")
@authenticated
def list_available_shelters():
    stmt = select(Shelter).where(Shelter.status == "Open", Shelter.current_occupancy < Shelter.capacity)
    return success_response(_list(stmt), "Available shelters retrieved successfully")


@bp.get("/<int:shelter_id>")
@authenticated
def get_shelter(shelter_id):
    return success_response(get_or_404(Shelter, shelter_id, "Shelter").to_dict(), "Shelter retrieved successfully")


@bp.put("/<int:shelter_id>")
@role_required(Role.COORDINATOR)
def update_shelter(shelter_id):
    shelter = get_or_404(Shelter, shelter_id, "Shelter")
    data = validate(get_json_body(), SHELTER_SCHEMA, partial=True, message="Invalid shelter information")
    shelter = shelter_service.update_shelter(shelter, data, current_user)
    return success_response(shelter.to_dict(), "Shelter updated successfully")


@bp.delete("/<int:shelter_id>")
@role_required(Role.COORDINATOR)
def delete_shelter(shelter_id):
    shelter = get_or_404(Shelter, shelter_id, "Shelter")
    shelter_service.delete_shelter(shelter, current_user)
    return success_response({"id": shelter_id}, "Shelter deleted successfully")
