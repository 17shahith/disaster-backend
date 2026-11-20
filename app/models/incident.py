from sqlalchemy import CheckConstraint

from ..constants import INCIDENT_STATUSES, INCIDENT_TYPES, SEVERITIES
from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, in_check


class Incident(TimestampMixin, db.Model):
    __tablename__ = "incidents"
    __table_args__ = (
        in_check("incident_type", INCIDENT_TYPES, "valid_type"),
        in_check("severity", SEVERITIES, "valid_severity"),
        in_check("status", INCIDENT_STATUSES, "valid_status"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="valid_latitude"),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="valid_longitude"
        ),
        CheckConstraint("affected_people >= 0", name="non_negative_affected"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    incident_type = db.Column(db.String(40), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    severity = db.Column(db.String(20), nullable=False, default="Medium", index=True)
    status = db.Column(db.String(20), nullable=False, default="Reported", index=True)
    affected_people = db.Column(db.Integer, nullable=False, default=0)
    reported_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    # Who raised the alarm (agency / caller) and when; distinct from the operator who registered it.
    reported_source = db.Column(db.String(120))
    reported_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)

    reporter = db.relationship("User", foreign_keys=[reported_by])
    requests = db.relationship(
        "EmergencyRequest",
        back_populates="incident",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    allocations = db.relationship("ResourceAllocation", back_populates="incident")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "incident_type": self.incident_type,
            "description": self.description,
            "location": self.location,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "severity": self.severity,
            "status": self.status,
            "affected_people": self.affected_people,
            "reported_by": self.reported_by,
            "reporter": self.reporter.to_summary() if self.reporter else None,
            "reported_source": self.reported_source,
            "reported_at": isoformat(self.reported_at or self.created_at),
            "resolved_at": isoformat(self.resolved_at),
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }
