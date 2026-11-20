from sqlalchemy import CheckConstraint

from ..constants import INVENTORY_TX_TYPES, SUPPLY_CATEGORIES
from ..extensions import db
from ..utils.time import isoformat, utcnow
from .base import TimestampMixin, in_check


class ReliefSupply(TimestampMixin, db.Model):
    """A stocked relief item.

    ``quantity`` is physical stock in the warehouse, ``reserved_quantity`` is the
    part of it promised to active allocations but not yet dispatched, and
    ``dispatched_quantity`` is the cumulative amount that has left the warehouse.
    """

    __tablename__ = "relief_supplies"
    __table_args__ = (
        in_check("category", SUPPLY_CATEGORIES, "valid_category"),
        CheckConstraint("quantity >= 0", name="non_negative_quantity"),
        CheckConstraint("reserved_quantity >= 0", name="non_negative_reserved"),
        CheckConstraint("reserved_quantity <= quantity", name="reserved_within_stock"),
        CheckConstraint("dispatched_quantity >= 0", name="non_negative_dispatched"),
        CheckConstraint("low_stock_threshold >= 0", name="non_negative_threshold"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    unit = db.Column(db.String(30), nullable=False, default="units")
    quantity = db.Column(db.Integer, nullable=False, default=0)
    reserved_quantity = db.Column(db.Integer, nullable=False, default=0)
    dispatched_quantity = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=10)
    warehouse_location = db.Column(db.String(255))
    description = db.Column(db.Text)

    transactions = db.relationship(
        "InventoryTransaction",
        back_populates="supply",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InventoryTransaction.id.desc()",
    )

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    @property
    def is_low_stock(self):
        return self.available_quantity <= self.low_stock_threshold

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "quantity": self.quantity,
            "reserved_quantity": self.reserved_quantity,
            "available_quantity": self.available_quantity,
            "dispatched_quantity": self.dispatched_quantity,
            "low_stock_threshold": self.low_stock_threshold,
            "is_low_stock": self.is_low_stock,
            "low_stock_warning": (
                f"Low stock: only {self.available_quantity} {self.unit} of {self.name} available"
                if self.is_low_stock
                else None
            ),
            "warehouse_location": self.warehouse_location,
            "description": self.description,
            "created_at": isoformat(self.created_at),
            "updated_at": isoformat(self.updated_at),
        }


class InventoryTransaction(db.Model):
    """Append-only inventory history for a supply."""

    __tablename__ = "inventory_transactions"
    __table_args__ = (in_check("transaction_type", INVENTORY_TX_TYPES, "valid_type"),)

    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(
        db.Integer, db.ForeignKey("relief_supplies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_type = db.Column(db.String(20), nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    reserved_after = db.Column(db.Integer, nullable=False)
    allocation_id = db.Column(db.Integer, db.ForeignKey("resource_allocations.id", ondelete="SET NULL"))
    dispatch_id = db.Column(db.Integer, db.ForeignKey("dispatch_records.id", ondelete="SET NULL"))
    note = db.Column(db.String(255))
    performed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    supply = db.relationship("ReliefSupply", back_populates="transactions")
    performer = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "supply_id": self.supply_id,
            "transaction_type": self.transaction_type,
            "quantity_change": self.quantity_change,
            "quantity_after": self.quantity_after,
            "reserved_after": self.reserved_after,
            "allocation_id": self.allocation_id,
            "dispatch_id": self.dispatch_id,
            "note": self.note,
            "performed_by": self.performer.to_summary() if self.performer else None,
            "created_at": isoformat(self.created_at),
        }
