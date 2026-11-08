"""Fiado charge and abono flow."""

from __future__ import annotations

from server.tests.conftest import create_cash_sale, create_customer


def test_fiado_charge_and_abono(client, db):
    customer = create_customer(client, "Doña Mari", "555-0100")
    assert customer["name"] == "Doña Mari"
    assert customer["balanceCents"] == 0

    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "fiado",
            "customerId": customer["id"],
        },
    )
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["status"] == "credit"
    assert sale["totalCents"] == 1800
    assert sale["customerId"] == customer["id"]
    assert sale["customer"]["name"] == "Doña Mari"
    assert sale["paidAt"] is None

    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 23000
    entry = db.execute(
        "SELECT kind, amount_cents, sale_id FROM fiado_entries WHERE customer_id = ?",
        (customer["id"],),
    ).fetchone()
    assert entry["kind"] == "charge"
    assert entry["amount_cents"] == 1800
    assert entry["sale_id"] == sale["id"]

    detail = client.get(f"/api/fiado/customers/{customer['id']}")
    assert detail.status_code == 200
    assert detail.json()["balanceCents"] == 1800
    assert len(detail.json()["entries"]) == 1
    assert detail.json()["entries"][0]["kind"] == "charge"

    abono = client.post(
        f"/api/fiado/customers/{customer['id']}/abono",
        json={"amountCents": 500, "employeeId": 2, "note": "abono parcial"},
    )
    assert abono.status_code == 200
    assert abono.json() == {"customerId": customer["id"], "balanceCents": 1300}

    detail = client.get(f"/api/fiado/customers/{customer['id']}").json()
    assert detail["balanceCents"] == 1300
    assert [entry["kind"] for entry in detail["entries"]] == ["charge", "payment"]

    customers = client.get("/api/fiado/customers").json()["customers"]
    assert len(customers) == 1
    assert customers[0]["balanceCents"] == 1300

    report = client.get("/api/reports/today").json()
    assert report["fiadoCents"] == 1800
    assert report["fiadoOutstandingCents"] == 1300


def test_fiado_requires_customer(client):
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "fiado",
        },
    )
    assert response.status_code == 400


def test_abono_validation_and_unknown_customer(client):
    customer = create_customer(client)
    bad = client.post(
        f"/api/fiado/customers/{customer['id']}/abono",
        json={"amountCents": 0, "employeeId": 2},
    )
    assert bad.status_code == 400

    missing = client.post(
        "/api/fiado/customers/99999/abono",
        json={"amountCents": 100, "employeeId": 2},
    )
    assert missing.status_code == 404

    missing_detail = client.get("/api/fiado/customers/99999")
    assert missing_detail.status_code == 404


def test_cash_sale_does_not_touch_fiado(client):
    create_cash_sale(client)
    assert client.get("/api/fiado/customers").json()["customers"] == []
