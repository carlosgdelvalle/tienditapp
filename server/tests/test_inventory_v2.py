"""v2 inventory: value, lastUpdated, absolute set, permissions and voice."""

from __future__ import annotations

import pytest

from server.tests.conftest import employee_headers

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)


def inventory(client):
    response = client.get("/api/inventory")
    assert response.status_code == 200, response.text
    return response.json()


def expected_total(products):
    total = 0
    for product in products:
        if product["unlimitedStock"]:
            continue
        total += (product["priceCents"] * product["stockMilli"] + 500) // 1000
    return total


def test_inventory_value_and_last_updated(client):
    body = inventory(client)
    products = client.get("/api/bootstrap").json()["products"]
    assert len(body["items"]) == 13
    assert body["totalValueCents"] == expected_total(products)

    coca = next(item for item in body["items"] if item["productId"] == 1)
    assert coca == {
        "productId": 1,
        "name": "Coca-Cola 600 ml",
        "unit": "pieza",
        "priceCents": 1800,
        "stockMilli": 24000,
        "unlimitedStock": False,
        "valueCents": 43200,
        "lastUpdatedAt": None,
        "lastUpdatedById": None,
        "lastUpdatedByName": None,
        "lastUpdatedByNickname": None,
    }
    tacos = next(item for item in body["items"] if item["name"] == "Tacos de pastor")
    assert tacos["unlimitedStock"] is True
    assert tacos["valueCents"] == 0

    client.patch("/api/employees/1", headers=OWNER, json={"nickname": "Rosy"})
    moved = client.post(
        "/api/inventory/set",
        headers=OWNER,
        json={"productId": 1, "qtyMilli": 10000, "note": "conteo del lunes"},
    )
    assert moved.status_code == 200, moved.text
    coca = next(item for item in inventory(client)["items"] if item["productId"] == 1)
    assert coca["stockMilli"] == 10000
    assert coca["valueCents"] == 18000
    assert isinstance(coca["lastUpdatedAt"], float)
    assert coca["lastUpdatedById"] == 1
    assert coca["lastUpdatedByName"] == "Doña Rosa"
    assert coca["lastUpdatedByNickname"] == "Rosy"


def test_last_updated_comes_from_the_newest_movement(client):
    sale = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "cash",
            "cashReceivedCents": 5000,
        },
    )
    assert sale.status_code == 200, sale.text
    coca = next(item for item in inventory(client)["items"] if item["productId"] == 1)
    assert coca["stockMilli"] == 23000
    assert coca["valueCents"] == 41400
    assert coca["lastUpdatedById"] == 2
    assert coca["lastUpdatedByName"] == "Lupita"
    assert coca["lastUpdatedByNickname"] == "Lupis"
    assert isinstance(coca["lastUpdatedAt"], float)


def test_set_absolute_writes_movement_and_permissions(client, db):
    response = client.post(
        "/api/inventory/set",
        headers=OWNER,
        json={"productId": 1, "qtyMilli": 9000},
    )
    assert response.status_code == 200, response.text
    assert response.json()["stockMilli"] == 9000
    movement = db.execute(
        """SELECT delta_milli, reason, employee_id FROM inventory_movements
           WHERE product_id = 1 ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert movement["delta_milli"] == -15000
    assert movement["reason"] == "set"
    assert movement["employee_id"] == 1

    # Employee 3 has can_inventory; employee 2 does not.
    allowed = client.post(
        "/api/inventory/set",
        headers=employee_headers(3),
        json={"productId": 2, "qtyMilli": 5000, "note": "conteo"},
    )
    assert allowed.status_code == 200, allowed.text
    movement = db.execute(
        "SELECT reason, employee_id FROM inventory_movements WHERE product_id = 2 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (movement["reason"], movement["employee_id"]) == ("conteo", 3)

    forbidden = client.post(
        "/api/inventory/set",
        headers=employee_headers(2),
        json={"productId": 1, "qtyMilli": 1},
    )
    assert forbidden.status_code == 403
    assert (
        db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 9000
    )

    # No header keeps the v1 open behavior.
    open_set = client.post("/api/inventory/set", json={"productId": 3, "qtyMilli": 3000})
    assert open_set.status_code == 200
    movement = db.execute(
        "SELECT employee_id FROM inventory_movements WHERE product_id = 3 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert movement["employee_id"] is None


def test_set_validates_unlimited_and_unknown_products(client):
    products = client.get("/api/bootstrap").json()["products"]
    unlimited = next(product for product in products if product["unlimitedStock"])
    response = client.post(
        "/api/inventory/set",
        headers=OWNER,
        json={"productId": unlimited["id"], "qtyMilli": 1000},
    )
    assert response.status_code == 400

    missing = client.post(
        "/api/inventory/set",
        headers=OWNER,
        json={"productId": 999, "qtyMilli": 1000},
    )
    assert missing.status_code == 404


def test_adjust_requires_inventory_permission_when_header_is_sent(client):
    forbidden = client.post(
        "/api/inventory/adjust",
        headers=employee_headers(2),
        json={"employeeId": 2, "productId": 1, "deltaMilli": -1000, "reason": "conteo"},
    )
    assert forbidden.status_code == 403

    allowed = client.post(
        "/api/inventory/adjust",
        headers=employee_headers(3),
        json={"employeeId": 3, "productId": 1, "deltaMilli": -1000, "reason": "conteo"},
    )
    assert allowed.status_code == 200, allowed.text

    open_adjust = client.post(
        "/api/inventory/adjust",
        json={"employeeId": 2, "productId": 1, "deltaMilli": -1000, "reason": "conteo"},
    )
    assert open_adjust.status_code == 200


def test_voice_only_parses_and_does_not_touch_stock(client, db):
    response = client.post(
        "/api/inventory/voice",
        json={"text": "coca colas de 600… 4, 5, 6… 12 piezas"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "productId": 1,
            "name": "Coca-Cola 600 ml",
            "qtyMilli": 12000,
            "unit": "pieza",
        }
    ]
    assert response.json()["note"] is None
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 24000
    assert db.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0

    missing = client.post("/api/inventory/voice", json={"text": "coca cola"})
    assert missing.status_code == 200
    assert missing.json()["items"][0]["qtyMilli"] is None
    assert "Confirma" in missing.json()["note"]
    assert db.execute("SELECT COUNT(*) FROM inventory_movements").fetchone()[0] == 0
