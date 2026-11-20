from sqlalchemy import CheckConstraint

from ..constants import DISPATCH_STATUSES
from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, in_check


class DispatchRecord(TimestampMixin, db.Model):
    __tablename__ = "dispatch_records"
    __table_args__ = (
        in_check("status", DISPATCH_STATUSES, "valid_status"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(
        db.Integer, db.ForeignKey("resource_allocations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    team_id = db.Column(db.Integer, db.ForeignKey("response_teams.id", ondelete="SET NULL"), index=True)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Prepared", index=True)
    origin = db.Column(db.String(255))
    destination = db.Column(db.String(255), nullable=False)
    vehicle_details = db.Column(db.String(255))
    notes = db.Column(db.Text)
    dispatched_at = db.Column(db.DateTime)
    in_transit_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    completion_notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    allocation = db.relationship("ResourceAllocation", back_populates="dispatches")
    team = db.relationship("ResponseTeam")
    creator = db.relationship("User")

    def to_dict(self):
        allocation = self.allocation
        return {
            "id": self.id,
            "allocation_id": self.allocation_id,
            "incident_id": allocation.incident_id if allocation else None,
            "resource_type": allocation.resource_type if allocation else None,
            "resource_name": allocation.resource_name if allocation else None,
            "team_id": self.team_id,
            "team_name": self.team.name if self.team else None,
            "quantity": self.quantity,
            "status": self.status,
            "origin": self.origin,
            "destination": self.destination,
            "vehicle_details": self.vehicle_details,
            "notes": self.notes,
            "dispatched_at": isoformat(self.dispatched_at),
            "in_transit_at": isoformat(self.in_transit_at),
            "delivered_at": isoformat(self.delivered_at),
            "completed_at": isoformat(self.completed_at),
            "completion_notes": self.completion_notes,
            "created_by": self.creator.to_summary() if self.creator else None,
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }
