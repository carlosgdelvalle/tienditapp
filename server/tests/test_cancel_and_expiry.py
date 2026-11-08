"""Cancellation, late payment notes and expiry reconciliation."""

from __future__ import annotations

import time

from server.tests.conftest import (
    create_cash_sale,
    create_customer,
    create_pey_sale,
    event_payload,
    post_webhook,
)


def test_cancel_pending_pey_then_late_payment_is_recorded_with_note(client, db):
    sale = create_pey_sale(client)
    response = client.post(f"/api/sales/{sale['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "canceled"

    late = post_webhook(
        client,
        event_payload(sale["qrId"], "tx_late", 0.01),
        "wh_late",
    )
    assert late.status_code == 200
    assert late.json()["outcome"] == "late_payment"

    detail = client.get(f"/api/sales/{sale['id']}").json()
    assert detail["status"] == "canceled"
    assert "tardío" in detail["note"]
    payment = db.execute(
        "SELECT applied, amount_cents FROM payments WHERE tx_id = 'tx_late'"
    ).fetchone()
    assert payment["applied"] == 0
    assert payment["amount_cents"] == 1
    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 24000


def test_cancel_cash_restores_inventory_with_movement(client, db):
    sale = create_cash_sale(client)
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 23000

    canceled = client.post(f"/api/sales/{sale['id']}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 24000
    reasons = [
        row["reason"]
        for row in db.execute(
            "SELECT reason FROM inventory_movements WHERE sale_id = ? ORDER BY id",
            (sale["id"],),
        ).fetchall()
    ]
    assert reasons == ["sale", "cancel"]


def test_cancel_credit_restores_stock_and_clears_balance(client, db):
    customer = create_customer(client)
    sale = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "fiado",
            "customerId": customer["id"],
        },
    ).json()
    assert sale["status"] == "credit"
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 23000
    assert client.get(f"/api/fiado/customers/{customer['id']}").json()["balanceCents"] == 1800

    canceled = client.post(f"/api/sales/{sale['id']}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 24000
    assert client.get(f"/api/fiado/customers/{customer['id']}").json()["balanceCents"] == 0
    assert client.get("/api/reports/today").json()["fiadoOutstandingCents"] == 0


def test_expired_pey_sale_can_still_be_reconciled(client, fake_pey, db):
    sale = create_pey_sale(client)
    db.execute(
        "UPDATE sales SET expires_at = ? WHERE id = ?",
        (time.time() - 10, sale["id"]),
    )
    db.commit()

    expired = client.get(f"/api/sales/{sale['id']}")
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"

    fake_pey.add_transaction(sale["qrId"], "tx_after_expiry", 0.01)
    late = client.get(f"/api/sales/{sale['id']}")
    assert late.status_code == 200
    assert late.json()["status"] == "paid_pey"
    assert late.json()["txId"] == "tx_after_expiry"
