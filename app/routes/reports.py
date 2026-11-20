"""Dashboard and situation report endpoints."""
from flask import Blueprint

from ..constants import Role
from ..middleware import authenticated, role_required
from ..services import report_service
from ..utils.responses import success_response

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

REPORT_VIEWERS = (Role.OPERATOR, Role.COORDINATOR, Role.TEAM_LEAD)


@bp.get("/dashboard")
@authenticated
def dashboard():
    return success_response(report_service.dashboard(), "Dashboard summary generated successfully")


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
