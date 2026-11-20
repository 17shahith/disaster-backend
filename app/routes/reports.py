"""Dashboard and situation report endpoints (live reports from SQLite, saved snapshots in MongoDB)."""
from flask import Blueprint
from flask_jwt_extended import current_user

from ..constants import Role
from ..middleware import authenticated, role_required
from ..services import report_service, snapshot_service
from ..utils.pagination import page_args
from ..utils.responses import success_response
from ..utils.validators import Field, get_json_body, validate

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

REPORT_VIEWERS = (Role.OPERATOR, Role.COORDINATOR, Role.TEAM_LEAD)
SNAPSHOT_AUTHORS = (Role.OPERATOR, Role.COORDINATOR)

SNAPSHOT_SCHEMA = {
    "title": Field(str, required=True, min_length=3, max_length=150),
    "notes": Field(str, nullable=True, max_length=2000),
}


@bp.post("/snapshots")
@role_required(*SNAPSHOT_AUTHORS)
def create_snapshot():
    data = validate(get_json_body(), SNAPSHOT_SCHEMA, message="Invalid situation report information")
    snapshot = snapshot_service.create_snapshot(data, current_user)
    return success_response(snapshot, "Situation report saved successfully", 201)


@bp.get("/snapshots")
@role_required(*REPORT_VIEWERS)
def list_snapshots():
    page, per_page = page_args()
    return success_response(snapshot_service.list_snapshots(page, per_page), "Situation reports retrieved successfully")


@bp.get("/snapshots/<snapshot_id>")
@role_required(*REPORT_VIEWERS)
def get_snapshot(snapshot_id):
    return success_response(snapshot_service.get_snapshot(snapshot_id), "Situation report retrieved successfully")


@bp.delete("/snapshots/<snapshot_id>")
@role_required(Role.ADMIN)
def delete_snapshot(snapshot_id):
    snapshot_service.delete_snapshot(snapshot_id, current_user)
    return success_response({"id": snapshot_id}, "Situation report deleted successfully")


@bp.get("/dashboard")
@authenticated
def dashboard():
    return success_response(report_service.dashboard(), "Dashboard summary generated successfully")


@bp.get("/summary")
@role_required(*REPORT_VIEWERS)
def summary():
    return success_response(report_service.summary(), "Situation summary generated successfully")


@bp.get("/incidents")
@role_required(*REPORT_VIEWERS)
def incidents():
    return success_response(report_service.incident_report(), "Incident report generated successfully")


@bp.get("/resources")
@role_required(*REPORT_VIEWERS)
def resources():
    return success_response(report_service.resource_report(), "Resource utilization report generated successfully")


@bp.get("/shelters")
@role_required(*REPORT_VIEWERS)
def shelters():
    return success_response(report_service.shelter_report(), "Shelter occupancy report generated successfully")


@bp.get("/teams")
@role_required(*REPORT_VIEWERS)
def teams():
    return success_response(report_service.team_report(), "Team availability report generated successfully")
