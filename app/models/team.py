from sqlalchemy import CheckConstraint

from ..constants import TEAM_AVAILABILITY, TEAM_TYPES
from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, in_check


class ResponseTeam(TimestampMixin, db.Model):
    __tablename__ = "response_teams"
    __table_args__ = (
        in_check("team_type", TEAM_TYPES, "valid_type"),
        in_check("availability", TEAM_AVAILABILITY, "valid_availability"),
        CheckConstraint("member_count >= 1", name="positive_members"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    team_type = db.Column(db.String(40), nullable=False, index=True)
    member_count = db.Column(db.Integer, nullable=False, default=1)
    contact_phone = db.Column(db.String(30))
    base_location = db.Column(db.String(255))
    equipment = db.Column(db.Text)
    availability = db.Column(db.String(20), nullable=False, default="Available", index=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    current_incident_id = db.Column(db.Integer, db.ForeignKey("incidents.id", ondelete="SET NULL"))

    lead = db.relationship("User", foreign_keys=[lead_id])
    current_incident = db.relationship("Incident", foreign_keys=[current_incident_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "team_type": self.team_type,
            "member_count": self.member_count,
            "contact_phone": self.contact_phone,
            "base_location": self.base_location,
            "equipment": self.equipment,
            "availability": self.availability,
            "lead_id": self.lead_id,
            "lead": self.lead.to_summary() if self.lead else None,
            "current_incident_id": self.current_incident_id,
            "current_incident_title": self.current_incident.title if self.current_incident else None,
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }
