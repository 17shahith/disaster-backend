from sqlalchemy import CheckConstraint

from ..constants import PRIORITIES, REQUEST_CATEGORIES, REQUEST_STATUSES
from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, in_check


class EmergencyRequest(TimestampMixin, db.Model):
    __tablename__ = "emergency_requests"
    __table_args__ = (
        in_check("category", REQUEST_CATEGORIES, "valid_category"),
        in_check("priority", PRIORITIES, "valid_priority"),
        in_check("status", REQUEST_STATUSES, "valid_status"),
        CheckConstraint("people_affected >= 0", name="non_negative_people"),
        CheckConstraint("quantity_requested IS NULL OR quantity_requested > 0", name="positive_quantity"),
    )

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(
        db.Integer, db.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category = db.Column(db.String(40), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255))
    priority = db.Column(db.String(20), nullable=False, default="Medium", index=True)
    status = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    people_affected = db.Column(db.Integer, nullable=False, default=0)
    quantity_requested = db.Column(db.Integer)
    contact_name = db.Column(db.String(120))
    contact_phone = db.Column(db.String(30))
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    completed_at = db.Column(db.DateTime)
    completion_notes = db.Column(db.Text)

    incident = db.relationship("Incident", back_populates="requests")
    requester = db.relationship("User", foreign_keys=[requested_by])

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "incident_title": self.incident.title if self.incident else None,
            "category": self.category,
            "description": self.description,
            "location": self.location,
            "priority": self.priority,
            "status": self.status,
            "people_affected": self.people_affected,
            "quantity_requested": self.quantity_requested,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "requested_by": self.requested_by,
            "requester": self.requester.to_summary() if self.requester else None,
            "completed_at": isoformat(self.completed_at),
            "completion_notes": self.completion_notes,
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }
