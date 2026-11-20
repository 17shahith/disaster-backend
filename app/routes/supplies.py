"""Relief supply / inventory endpoints."""
from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import select

from ..constants import SUPPLY_CATEGORIES, Role
from ..middleware import authenticated, role_required
from ..models import ReliefSupply
from ..services import supply_service
from ..services.common import get_or_404
from ..utils.pagination import filter_choice_arg, paginate
from ..utils.responses import success_response
from ..utils.validators import Field, get_json_body, validate

bp = Blueprint("supplies", __name__, url_prefix="/api/supplies")

SUPPLY_SCHEMA = {
    "name": Field(str, required=True, min_length=2, max_length=150),
    "category": Field(str, required=True, choices=SUPPLY_CATEGORIES),
    "unit": Field(str, max_length=30, default="units"),
    "quantity": Field(int, required=True, min_value=0, max_value=100_000_000),
    "low_stock_threshold": Field(int, min_value=0, default=10),
    "warehouse_location": Field(str, nullable=True, max_length=255),
    "description": Field(str, nullable=True, max_length=2000),
}
UPDATE_SCHEMA = {
    **SUPPLY_SCHEMA,
    "restock_quantity": Field(int, min_value=1, max_value=100_000_000),
    "adjustment_note": Field(str, max_length=255),
}


def _list(stmt):
    category = filter_choice_arg("category", SUPPLY_CATEGORIES)
    if category:
        stmt = stmt.where(ReliefSupply.category == category)
    return paginate(stmt.order_by(ReliefSupply.category, ReliefSupply.name))


@bp.post("")
@role_required(Role.COORDINATOR)
def create_supply():
    data = validate(get_json_body(), SUPPLY_SCHEMA, message="Invalid relief supply information")
    supply = supply_service.create_supply(data, current_user)
    return success_response(supply.to_dict(), "Relief supply added successfully", 201)


@bp.get("")
@authenticated
def list_supplies():
    return success_response(_list(select(ReliefSupply)), "Relief supplies retrieved successfully")


@bp.get("/low-stock")
@authenticated
def list_low_stock():
    stmt = select(ReliefSupply).where(supply_service.low_stock_condition())
    return success_response(_list(stmt), "Low-stock supplies retrieved successfully")


@bp.get("/<int:supply_id>")
@authenticated
def get_supply(supply_id):
    return success_response(get_or_404(ReliefSupply, supply_id, "Relief supply").to_dict(),
                            "Relief supply retrieved successfully")


@bp.get("/<int:supply_id>/history")
@role_required(Role.COORDINATOR)
def supply_history(supply_id):
    get_or_404(ReliefSupply, supply_id, "Relief supply")
    return success_response(paginate(supply_service.history_query(supply_id)),
                            "Inventory history retrieved successfully")


@bp.put("/<int:supply_id>")
@role_required(Role.COORDINATOR)
def update_supply(supply_id):
    supply = get_or_404(ReliefSupply, supply_id, "Relief supply")
    data = validate(get_json_body(), UPDATE_SCHEMA, partial=True, message="Invalid relief supply information")
    supply = supply_service.update_supply(supply, data, current_user)
    return success_response(supply.to_dict(), "Relief supply updated successfully")


@bp.delete("/<int:supply_id>")
@role_required(Role.COORDINATOR)
def delete_supply(supply_id):
    supply = get_or_404(ReliefSupply, supply_id, "Relief supply")
    supply_service.delete_supply(supply, current_user)
    return success_response({"id": supply_id}, "Relief supply deleted successfully")
