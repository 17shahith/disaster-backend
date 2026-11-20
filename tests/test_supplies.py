import pytest


def test_create_supply_records_history(api):
    supply = api.supply(quantity=500)
    assert supply["available_quantity"] == 500 and supply["reserved_quantity"] == 0
    history = api.get(f"/api/supplies/{supply['id']}/history", "coordinator")["items"]
    assert history[0]["transaction_type"] == "Initial Stock"
    assert history[0]["quantity_change"] == 500


@pytest.mark.parametrize("payload, field", [
    ({"quantity": -1}, "quantity"),
    ({"category": "Snacks"}, "category"),
    ({"low_stock_threshold": -3}, "low_stock_threshold"),
    ({"quantity": "lots"}, "quantity"),
    ({"quantity": True}, "quantity"),
])
def test_invalid_supply(client, headers, payload, field):
    body = {"name": "Item", "category": "Food", "quantity": 10, **payload}
    resp = client.post("/api/supplies", headers=headers("coordinator"), json=body)
    assert resp.status_code == 400
    assert field in resp.get_json()["errors"]


def test_only_coordinators_manage_supplies(client, headers):
    for role in ("operator", "lead"):
        resp = client.post("/api/supplies", headers=headers(role), json={
            "name": "X", "category": "Food", "quantity": 1})
        assert resp.status_code == 403


def test_restock_and_adjust(api):
    supply = api.supply(quantity=100)
    data = api.put(f"/api/supplies/{supply['id']}", "coordinator", {"restock_quantity": 50}).get_json()["data"]
    assert data["quantity"] == 150
    data = api.put(f"/api/supplies/{supply['id']}", "coordinator",
                   {"quantity": 120, "adjustment_note": "Damaged stock"}).get_json()["data"]
    assert data["quantity"] == 120
    types = [t["transaction_type"] for t in api.get(f"/api/supplies/{supply['id']}/history", "coordinator")["items"]]
    assert types == ["Adjustment", "Restock", "Initial Stock"]


def test_negative_inventory_rejected(api):
    supply = api.supply()
    assert api.put(f"/api/supplies/{supply['id']}", "coordinator", {"quantity": -10}).status_code == 400
    assert api.put(f"/api/supplies/{supply['id']}", "coordinator", {"restock_quantity": 0}).status_code == 400


def test_cannot_reduce_stock_below_reserved(api):
    supply = api.supply(quantity=100)
    api.allocation(incident_id=api.incident()["id"], resource_type="Supply", supply_id=supply["id"], quantity=80)
    resp = api.put(f"/api/supplies/{supply['id']}", "coordinator", {"quantity": 50})
    assert resp.status_code == 409
    assert api.get(f"/api/supplies/{supply['id']}")["quantity"] == 100


def test_low_stock_warning(api):
    supply = api.supply(quantity=100, low_stock_threshold=30)
    api.allocation(incident_id=api.incident()["id"], resource_type="Supply", supply_id=supply["id"], quantity=75)
    data = api.get(f"/api/supplies/{supply['id']}")
    assert data["is_low_stock"] is True
    assert data["low_stock_warning"].startswith("Low stock: only 25")
    items = api.get("/api/supplies/low-stock", "operator")["items"]
    assert [s["id"] for s in items] == [supply["id"]]


def test_filter_by_category(api):
    api.supply(name="Rice", category="Food")
    api.supply(name="Water")
    items = api.get("/api/supplies?category=Food")["items"]
    assert [s["name"] for s in items] == ["Rice"]


def test_delete_supply_rules(api, client, headers):
    unused = api.supply(name="Unused")
    used = api.supply(name="Used")
    api.allocation(incident_id=api.incident()["id"], resource_type="Supply", supply_id=used["id"], quantity=1)
    assert client.delete(f"/api/supplies/{unused['id']}", headers=headers("coordinator")).status_code == 200
    assert client.delete(f"/api/supplies/{used['id']}", headers=headers("coordinator")).status_code == 409
