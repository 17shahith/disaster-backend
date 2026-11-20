from sqlalchemy import CheckConstraint

from ..constants import SHELTER_STATUSES
from ..extensions import db
from ..utils.time import isoformat
from .base import TimestampMixin, in_check


class Shelter(TimestampMixin, db.Model):
    __tablename__ = "shelters"
    __table_args__ = (
        in_check("status", SHELTER_STATUSES, "valid_status"),
        CheckConstraint("capacity > 0", name="positive_capacity"),
        CheckConstraint("current_occupancy >= 0", name="non_negative_occupancy"),
        CheckConstraint("current_occupancy <= capacity", name="occupancy_within_capacity"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    location = db.Column(db.String(255), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    current_occupancy = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default="Open", index=True)
    contact_person = db.Column(db.String(120))
    contact_phone = db.Column(db.String(30))
    facilities = db.Column(db.Text)

    @property
    def available_beds(self):
        return max(self.capacity - self.current_occupancy, 0)

    @property
    def occupancy_rate(self):
        return round(self.current_occupancy * 100.0 / self.capacity, 2) if self.capacity else 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "capacity": self.capacity,
            "current_occupancy": self.current_occupancy,
            "available_beds": self.available_beds,
            "occupancy_rate": self.occupancy_rate,
            "status": self.status,
            "contact_person": self.contact_person,
            "contact_phone": self.contact_phone,
            "facilities": self.facilities,
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }
