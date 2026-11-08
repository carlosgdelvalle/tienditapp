"""Inventory adjustments always write a movement; negative stock is allowed."""

from __future__ import annotations


def test_inventory_adjustment_creates_movement(client, db):
    response = client.post(
        "/api/inventory/adjust",
        json={
            "employeeId": 2,
            "productId": 1,
            "deltaMilli": -1000,
            "reason": "conteo",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["stockMilli"] == 23000

    movement = db.execute(
        """SELECT delta_milli, reason, employee_id, sale_id
           FROM inventory_movements WHERE product_id = 1
           ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert movement["delta_milli"] == -1000
    assert movement["reason"] == "conteo"
    assert movement["employee_id"] == 2
    assert movement["sale_id"] is None


def test_negative_stock_is_allowed(client, db):
    response = client.post(
        "/api/inventory/adjust",
        json={
            "employeeId": 3,
            "productId": 11,
            "deltaMilli": -999999,
            "reason": "merma",
        },
    )
    assert response.status_code == 200
    assert response.json()["stockMilli"] == -985999
    assert db.execute("SELECT stock_milli FROM products WHERE id = 11").fetchone()[0] == -985999


def test_inventory_adjustment_validates_product_and_employee(client):
    assert (
        client.post(
            "/api/inventory/adjust",
            json={
                "employeeId": 2,
                "productId": 999,
                "deltaMilli": -1000,
                "reason": "conteo",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/inventory/adjust",
            json={
                "employeeId": 999,
                "productId": 1,
                "deltaMilli": -1000,
                "reason": "conteo",
            },
        ).status_code
        == 404
    )
