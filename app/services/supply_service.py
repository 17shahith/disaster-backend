"""Relief supply inventory rules.

Stock movements use conditional UPDATE statements so that concurrent requests
can never drive inventory negative or reserve more than is available.
"""
from sqlalchemy import func, select, update

from ..extensions import db
from ..models import InventoryTransaction, ReliefSupply, ResourceAllocation
from ..utils.errors import ConflictError, ValidationError
from .activity_service import log_activity
from .common import apply_changes, atomic


def _record(supply, tx_type, change, actor, note=None, allocation_id=None, dispatch_id=None):
    db.session.add(
        InventoryTransaction(
            supply_id=supply.id,
            transaction_type=tx_type,
            quantity_change=change,
            quantity_after=supply.quantity,
            reserved_after=supply.reserved_quantity,
            allocation_id=allocation_id,
            dispatch_id=dispatch_id,
            note=note,
            performed_by=getattr(actor, "id", None),
        )
    )


def _ensure_unique_name(name, exclude_id=None):
    stmt = select(ReliefSupply.id).where(func.lower(ReliefSupply.name) == name.lower())
    if exclude_id:
        stmt = stmt.where(ReliefSupply.id != exclude_id)
    if db.session.execute(stmt).first():
        raise ConflictError("A relief supply with this name already exists", {"name": "Must be unique."})


def low_stock_condition():
    return (ReliefSupply.quantity - ReliefSupply.reserved_quantity) <= ReliefSupply.low_stock_threshold


def create_supply(data, actor):
    _ensure_unique_name(data["name"])
    with atomic():
        supply = ReliefSupply(**data)
        db.session.add(supply)
        db.session.flush()
        _record(supply, "Initial Stock", supply.quantity, actor, "Initial stock registered")
        log_activity(actor, "SUPPLY_CREATED", "supply", supply.id, f"Relief supply '{supply.name}' added",
                     {"quantity": supply.quantity, "unit": supply.unit})
    return supply


def update_supply(supply, data, actor):
    """Update supply details. Stock can be changed with ``quantity`` (absolute) or ``restock_quantity`` (added)."""
    new_quantity = data.pop("quantity", None)
    restock = data.pop("restock_quantity", None)
    note = data.pop("adjustment_note", None)
    if new_quantity is not None and restock is not None:
        raise ValidationError("Provide either 'quantity' or 'restock_quantity', not both",
                              {"quantity": "Conflicts with restock_quantity."})
    if "name" in data:
        _ensure_unique_name(data["name"], exclude_id=supply.id)

    with atomic():
        changes = apply_changes(supply, data)
        if restock:
            db.session.execute(
                update(ReliefSupply)
                .where(ReliefSupply.id == supply.id)
                .values(quantity=ReliefSupply.quantity + restock)
                .execution_options(synchronize_session=False)
            )
            db.session.refresh(supply)
            _record(supply, "Restock", restock, actor, note or "Stock replenished")
            changes["quantity"] = {"restocked": restock, "to": supply.quantity}
        elif new_quantity is not None and new_quantity != supply.quantity:
            old = supply.quantity
            result = db.session.execute(
                update(ReliefSupply)
                .where(ReliefSupply.id == supply.id, ReliefSupply.reserved_quantity <= new_quantity)
                .values(quantity=new_quantity)
                .execution_options(synchronize_session=False)
            )
            db.session.refresh(supply)
            if result.rowcount != 1:
                raise ConflictError(
                    "Stock cannot be reduced below the quantity reserved for active allocations",
                    {"quantity": f"At least {supply.reserved_quantity} {supply.unit} are reserved."},
                )
            delta = new_quantity - old
            _record(supply, "Restock" if delta > 0 else "Adjustment", delta, actor, note or "Stock adjusted")
            changes["quantity"] = {"from": old, "to": new_quantity}
        action = "SUPPLY_INVENTORY_UPDATED" if "quantity" in changes else "SUPPLY_UPDATED"
        log_activity(actor, action, "supply", supply.id, f"Relief supply '{supply.name}' updated", {"changes": changes})
        if supply.is_low_stock:
            log_activity(actor, "LOW_STOCK_WARNING", "supply", supply.id,
                         f"Low stock: {supply.available_quantity} {supply.unit} of '{supply.name}' available")
    return supply


def delete_supply(supply, actor):
    used = db.session.execute(
        select(func.count(ResourceAllocation.id)).where(ResourceAllocation.supply_id == supply.id)
    ).scalar_one()
    if used:
        raise ConflictError("Supply has allocation history and cannot be deleted",
                            {"supply": "Set its quantity to 0 instead."})
    with atomic():
        log_activity(actor, "SUPPLY_DELETED", "supply", supply.id, f"Relief supply '{supply.name}' deleted")
        db.session.delete(supply)


def history_query(supply_id):
    return (
        select(InventoryTransaction)
        .where(InventoryTransaction.supply_id == supply_id)
        .order_by(InventoryTransaction.id.desc())
    )


# --- stock movements used by allocation/dispatch services --------------------

def reserve(supply, amount, actor, allocation_id):
    result = db.session.execute(
        update(ReliefSupply)
        .where(ReliefSupply.id == supply.id, ReliefSupply.quantity - ReliefSupply.reserved_quantity >= amount)
        .values(reserved_quantity=ReliefSupply.reserved_quantity + amount)
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(supply)
    if result.rowcount != 1:
        raise ConflictError(
            "Insufficient inventory for this allocation",
            {"quantity": f"Requested {amount} {supply.unit} of '{supply.name}', "
                         f"but only {supply.available_quantity} available."},
        )
    _record(supply, "Reserved", -amount, actor, f"Reserved for allocation #{allocation_id}", allocation_id)


def release(supply, amount, actor, allocation_id, note=None):
    if amount <= 0:
        return
    result = db.session.execute(
        update(ReliefSupply)
        .where(ReliefSupply.id == supply.id, ReliefSupply.reserved_quantity >= amount)
        .values(reserved_quantity=ReliefSupply.reserved_quantity - amount)
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(supply)
    if result.rowcount != 1:
        raise ConflictError("Inventory reservation is inconsistent", {"supply_id": "Reserved quantity too low."})
    _record(supply, "Released", amount, actor, note or f"Released from allocation #{allocation_id}", allocation_id)


def deduct_for_dispatch(supply, amount, actor, allocation_id, dispatch_id):
    """Reserved stock physically leaves the warehouse."""
    result = db.session.execute(
        update(ReliefSupply)
        .where(
            ReliefSupply.id == supply.id,
            ReliefSupply.reserved_quantity >= amount,
            ReliefSupply.quantity >= amount,
        )
        .values(
            quantity=ReliefSupply.quantity - amount,
            reserved_quantity=ReliefSupply.reserved_quantity - amount,
            dispatched_quantity=ReliefSupply.dispatched_quantity + amount,
        )
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(supply)
    if result.rowcount != 1:
        raise ConflictError("Insufficient reserved inventory for this dispatch",
                            {"quantity": f"Only {supply.reserved_quantity} {supply.unit} reserved."})
    _record(supply, "Dispatched", -amount, actor, f"Dispatched (dispatch #{dispatch_id})", allocation_id, dispatch_id)
    if supply.is_low_stock:
        log_activity(actor, "LOW_STOCK_WARNING", "supply", supply.id,
                     f"Low stock: {supply.available_quantity} {supply.unit} of '{supply.name}' available")
