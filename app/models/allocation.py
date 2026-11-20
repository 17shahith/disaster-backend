from sqlalchemy import CheckConstraint, Index, text

from ..constants import ALLOCATION_STATUSES, RESOURCE_TYPES
from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, in_check

_ACTIVE = "status IN ('Pending', 'Approved', 'Allocated')"


class ResourceAllocation(TimestampMixin, db.Model):
    """Allocation of one resource (team, supply or shelter) to an incident."""

    __tablename__ = "resource_allocations"
    __table_args__ = (
        in_check("resource_type", RESOURCE_TYPES, "valid_resource_type"),
        in_check("status", ALLOCATION_STATUSES, "valid_status"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint(
            "(resource_type = 'Team' AND team_id IS NOT NULL AND supply_id IS NULL AND shelter_id IS NULL)"
            " OR (resource_type = 'Supply' AND supply_id IS NOT NULL AND team_id IS NULL AND shelter_id IS NULL)"
            " OR (resource_type = 'Shelter' AND shelter_id IS NOT NULL AND team_id IS NULL AND supply_id IS NULL)",
            name="resource_matches_type",
        ),
        # A team can only hold one active assignment at a time.
        Index(
            "uq_active_team_allocation",
            "team_id",
            unique=True,
            sqlite_where=text(f"team_id IS NOT NULL AND {_ACTIVE}"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(
        db.Integer, db.ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id = db.Column(db.Integer, db.ForeignKey("emergency_requests.id", ondelete="SET NULL"))
    resource_type = db.Column(db.String(20), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("response_teams.id", ondelete="RESTRICT"))
    supply_id = db.Column(db.Integer, db.ForeignKey("relief_supplies.id", ondelete="RESTRICT"))
    shelter_id = db.Column(db.Integer, db.ForeignKey("shelters.id", ondelete="RESTRICT"))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    notes = db.Column(db.Text)
    progress_notes = db.Column(db.Text)
    allocated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = db.Column(db.DateTime)
    allocated_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancellation_reason = db.Column(db.String(255))

    incident = db.relationship("Incident", back_populates="allocations")
    request = db.relationship("EmergencyRequest")
    team = db.relationship("ResponseTeam")
    supply = db.relationship("ReliefSupply")
    shelter = db.relationship("Shelter")
    allocator = db.relationship("User", foreign_keys=[allocated_by])
    approver = db.relationship("User", foreign_keys=[approved_by])
    dispatches = db.relationship("DispatchRecord", back_populates="allocation", order_by="DispatchRecord.id")

    @property
    def resource(self):
        return {"Team": self.team, "Supply": self.supply, "Shelter": self.shelter}[self.resource_type]

    @property
    def resource_name(self):
        resource = self.resource
        return resource.name if resource is not None else None

    @property
    def dispatched_total(self):
        return sum(d.quantity for d in self.dispatches)

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "incident_title": self.incident.title if self.incident else None,
            "request_id": self.request_id,
            "resource_type": self.resource_type,
            "team_id": self.team_id,
            "supply_id": self.supply_id,
            "shelter_id": self.shelter_id,
            "resource_name": self.resource_name,
            "quantity": self.quantity,
            "dispatched_quantity": self.dispatched_total,
            "remaining_quantity": max(self.quantity - self.dispatched_total, 0),
            "status": self.status,
            "notes": self.notes,
            "progress_notes": self.progress_notes,
            "allocated_by": self.allocator.to_summary() if self.allocator else None,
            "approved_by": self.approver.to_summary() if self.approver else None,
            "approved_at": isoformat(self.approved_at),
            "allocated_at": isoformat(self.allocated_at),
            "completed_at": isoformat(self.completed_at),
            "cancelled_at": isoformat(self.cancelled_at),
            "cancellation_reason": self.cancellation_reason,
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }
