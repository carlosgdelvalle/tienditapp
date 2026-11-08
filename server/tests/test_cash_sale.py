"""Cash is final immediately, decrements stock and records a movement."""

from __future__ import annotations


def test_cash_sale_paid_and_stock_decremented(client, db):
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 2000}],
            "paymentMethod": "cash",
            "cashReceivedCents": 5000,
        },
    )
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["status"] == "paid_cash"
    assert sale["paymentMethod"] == "cash"
    assert sale["totalCents"] == 3600
    assert sale["chargedCents"] == 3600
    assert sale["cashReceivedCents"] == 5000
    assert sale["changeCents"] == 1400
    assert sale["paidAt"] is not None
    assert sale["items"][0]["qtyMilli"] == 2000
    assert sale["items"][0]["lineTotalCents"] == 3600

    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 22000

    movement = db.execute(
        """SELECT delta_milli, reason, sale_id, employee_id
           FROM inventory_movements WHERE sale_id = ?""",
        (sale["id"],),
    ).fetchone()
    assert movement["delta_milli"] == -2000
    assert movement["reason"] == "sale"
    assert movement["employee_id"] == 2

    payment = db.execute(
        "SELECT amount_cents, method, applied FROM payments WHERE sale_id = ?",
        (sale["id"],),
    ).fetchone()
    assert payment["amount_cents"] == 3600
    assert payment["method"] == "cash"
    assert payment["applied"] == 1

    fetched = client.get(f"/api/sales/{sale['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "paid_cash"
    assert fetched.json()["changeCents"] == 1400


def test_cash_sale_with_two_products(client):
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 1,
            "items": [
                {"productId": 9, "qtyMilli": 500},
                {"productId": 1, "qtyMilli": 2000},
            ],
            "paymentMethod": "cash",
            "cashReceivedCents": 5000,
        },
    )
    assert response.status_code == 200
    assert response.json()["totalCents"] == 4900
    assert response.json()["changeCents"] == 100


def test_cash_requires_enough_money(client):
    before = client.get("/api/console/inventory", headers={"X-Owner-Pin": "1234"})
    assert before.status_code == 200
    stock_before = {item["id"]: item["stockMilli"] for item in before.json()["items"]}

    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 2000}],
            "paymentMethod": "cash",
            "cashReceivedCents": 100,
        },
    )
    assert response.status_code == 400
    stock_after = {
        item["id"]: item["stockMilli"]
        for item in client.get(
            "/api/console/inventory", headers={"X-Owner-Pin": "1234"}
        ).json()["items"]
    }
    assert stock_after == stock_before
