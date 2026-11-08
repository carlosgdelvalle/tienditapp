"""PEY pending/reconcile, timeout, rejection and applied=0 extras."""

from __future__ import annotations

import time

from server.pey import PeyError
from server.tests.conftest import (
    TEST_SECRET,
    create_pey_sale,
    event_payload,
    post_webhook,
)


def test_pey_pending_then_reconcile_with_fake(client, fake_pey, db):
    sale = create_pey_sale(client, qty_milli=2000)
    assert sale["status"] == "pending"
    assert sale["paymentMethod"] == "pey"
    assert sale["totalCents"] == 3600
    assert sale["chargedCents"] == 1
    assert sale["qrId"]
    assert sale["qrImage"].startswith("data:image/png;base64,")
    assert sale["expiresAt"] > time.time()

    qr_id = sale["qrId"]
    assert fake_pey.qrs[qr_id]["amountCents"] == 1
    assert fake_pey.qrs[qr_id]["saleId"] == sale["id"]

    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 24000

    pending = client.get(f"/api/sales/{sale['id']}")
    assert pending.json()["status"] == "pending"

    fake_pey.add_transaction(qr_id, "tx_sim_1", 0.01)
    paid = client.get(f"/api/sales/{sale['id']}")
    assert paid.status_code == 200
    body = paid.json()
    assert body["status"] == "paid_pey"
    assert body["txId"] == "tx_sim_1"
    assert body["paidAt"] is not None

    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 22000
    payment = db.execute(
        "SELECT amount_cents, applied, source FROM payments WHERE sale_id = ?",
        (sale["id"],),
    ).fetchone()
    assert payment["amount_cents"] == 1
    assert payment["applied"] == 1
    assert payment["source"] == "reconcile"
    movements = db.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE sale_id = ?",
        (sale["id"],),
    ).fetchone()[0]
    assert movements == 1


def test_raw_base64_qr_image_is_normalized_to_data_url(client, fake_pey):
    fake_pey.create_image = "U0lNVUxBRE8="
    sale = create_pey_sale(client)
    assert sale["qrImage"] == "data:image/png;base64,U0lNVUxBRE8="


def test_pey_timeout_returns_202_with_sale_id(client, fake_pey, db):
    fake_pey.create_timeout = True
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 2, "qtyMilli": 1000}],
            "paymentMethod": "pey",
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "por_conciliar"
    assert body["saleId"].startswith("sale_")
    assert body["totalCents"] == 2200
    assert body["chargedCents"] == 1

    fetched = client.get(f"/api/sales/{body['saleId']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "por_conciliar"
    stock = db.execute("SELECT stock_milli FROM products WHERE id = 2").fetchone()[0]
    assert stock == 18000


def test_amount_mismatch_then_correct_transaction_resolves(client, fake_pey, db):
    sale = create_pey_sale(client, product_id=2)
    qr_id = sale["qrId"]

    mismatch = post_webhook(
        client,
        event_payload(qr_id, "tx_bad", 0.02),
        "wh_bad_amount",
    )
    assert mismatch.status_code == 200
    assert mismatch.json()["outcome"] == "amount_mismatch"
    assert client.get(f"/api/sales/{sale['id']}").json()["status"] == "por_conciliar"

    bad_payment = db.execute(
        "SELECT amount_cents, applied FROM payments WHERE tx_id = 'tx_bad'"
    ).fetchone()
    assert bad_payment["amount_cents"] == 2
    assert bad_payment["applied"] == 0

    # A later, correct payment for the same QR is the reconciliation path.
    fake_pey.add_transaction(qr_id, "tx_good", 0.01)
    resolved = client.get(f"/api/sales/{sale['id']}")
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "paid_pey"
    assert resolved.json()["txId"] == "tx_good"

    applied = db.execute(
        "SELECT applied FROM payments WHERE sale_id = ? ORDER BY received_at, tx_id",
        (sale["id"],),
    ).fetchall()
    assert sorted(row["applied"] for row in applied) == [0, 1]
    stock = db.execute("SELECT stock_milli FROM products WHERE id = 2").fetchone()[0]
    assert stock == 17000


def test_extra_payment_on_paid_sale_is_recorded_with_applied_zero(client, fake_pey, db):
    sale = create_pey_sale(client)
    fake_pey.add_transaction(sale["qrId"], "tx_first", 0.01)
    assert client.get(f"/api/sales/{sale['id']}").json()["status"] == "paid_pey"

    extra = post_webhook(
        client,
        event_payload(sale["qrId"], "tx_extra", 0.01),
        "wh_extra",
    )
    assert extra.status_code == 200
    assert extra.json()["outcome"] == "extra_payment"
    assert client.get(f"/api/sales/{sale['id']}").json()["status"] == "paid_pey"

    rows = db.execute(
        "SELECT tx_id, applied FROM payments WHERE sale_id = ? ORDER BY tx_id",
        (sale["id"],),
    ).fetchall()
    assert [(row["tx_id"], row["applied"]) for row in rows] == [
        ("tx_extra", 0),
        ("tx_first", 1),
    ]
    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 23000


def test_pey_rejection_returns_502_failed(client, fake_pey, db):
    fake_pey.create_error = PeyError("rejected", "SIMULADO: rechazado")
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "pey",
        },
    )
    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "failed"
    assert body["saleId"].startswith("sale_")
    row = db.execute("SELECT status FROM sales WHERE id = ?", (body["saleId"],)).fetchone()
    assert row["status"] == "failed"
    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 24000


def test_live_mode_charges_commercial_total(tmp_path):
    from fastapi.testclient import TestClient

    from server.config import Settings
    from server.main import create_app
    from server.tests.fakes import FakePey

    settings = Settings(
        db_path=tmp_path / "live.db",
        owner_pin="1234",
        modo_demo=False,
        pey_api_key="test-pey-key",
        pey_webhook_secret=TEST_SECRET,
    )
    fake = FakePey()
    with TestClient(create_app(settings=settings, pey_client=fake)) as local_client:
        response = local_client.post(
            "/api/sales",
            json={
                "employeeId": 2,
                "items": [{"productId": 1, "qtyMilli": 1000}],
                "paymentMethod": "pey",
            },
        )
        assert response.status_code == 200
        sale = response.json()
        assert sale["totalCents"] == 1800
        assert sale["chargedCents"] == 1800
        assert fake.qrs[sale["qrId"]]["amountCents"] == 1800

        webhook = post_webhook(
            local_client,
            event_payload(sale["qrId"], "tx_live", 18.00),
            "wh_live",
        )
        assert webhook.status_code == 200
        assert webhook.json()["outcome"] == "applied"
        assert local_client.get(f"/api/sales/{sale['id']}").json()["status"] == "paid_pey"


def test_pey_without_configuration_returns_sale_id(client, tmp_path):
    from fastapi.testclient import TestClient

    from server.config import Settings
    from server.main import create_app

    settings = Settings(
        db_path=tmp_path / "no-pey.db",
        owner_pin="1234",
        pey_api_key="",
        pey_webhook_secret=TEST_SECRET,
    )
    with TestClient(create_app(settings=settings)) as local_client:
        response = local_client.post(
            "/api/sales",
            json={
                "employeeId": 2,
                "items": [{"productId": 1, "qtyMilli": 1000}],
                "paymentMethod": "pey",
            },
        )
        assert response.status_code == 502
        body = response.json()
        assert body["saleId"]
        assert body["status"] == "failed"
        assert body["error"] == "pey_not_configured"
