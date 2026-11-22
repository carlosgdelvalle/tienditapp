"""B3/B4 release regressions, using only synthetic data and FakePey."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.db import STORE_ID
from server.main import create_app
from server.tests.conftest import create_cash_sale, create_pey_sale, event_payload, post_webhook
from server.tests.test_checkout_till import sale_event, sync

pytestmark = pytest.mark.usefixtures("staff")


def issued_catalog(client, device_id):
    response = client.post(
        "/api/sync/lease",
        json={
            "tenantId": STORE_ID,
            "storeId": STORE_ID,
            "deviceId": device_id,
            "membershipId": "mem-" + device_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("source", ["reconcile", "webhook"])
def test_verified_codi_settles_once_when_another_till_sells_the_last_unit(
    app, db, fake_pey, source,
):
    db.execute("UPDATE products SET stock_milli = 1000 WHERE id = 1")
    db.commit()

    with TestClient(app, raise_server_exceptions=False) as client:
        pending = create_pey_sale(client)
        assert pending["status"] == "pending"
        assert create_cash_sale(client)["status"] == "paid_cash"
        transaction_id = "simulado-last-unit"
        fake_pey.add_transaction(pending["qrId"], transaction_id, 0.01)
        webhook = event_payload(pending["qrId"], transaction_id, 0.01)
        sale_url = f"/api/sales/{pending['id']}"

        if source == "reconcile":
            response = client.get(sale_url)
        else:
            response = post_webhook(client, webhook, "simulado-last-unit-delivery")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "paid_pey"

        # A repeat delivery and provider readback must account for the same payment.
        for _ in range(2):
            response = post_webhook(client, webhook, "simulado-last-unit-delivery")
            assert response.status_code == 200, response.text
        assert client.get(sale_url).json()["status"] == "paid_pey"

    payment_rows = db.execute(
        "SELECT tx_id, amount_cents, applied, source FROM payments WHERE sale_id = ?",
        (pending["id"],),
    ).fetchall()
    assert [tuple(row) for row in payment_rows] == [(transaction_id, 1, 1, source)]
    sale_row = db.execute(
        "SELECT status, pey_tx_id FROM sales WHERE id = ?", (pending["id"],),
    ).fetchone()
    assert tuple(sale_row) == ("paid_pey", transaction_id)


def test_offline_cash_uses_issued_price_after_catalog_edit_and_lost_ack(client, db):
    device_id = "price-change-till"
    issued = issued_catalog(client, device_id)
    lease, snapshot = issued["lease"], issued["snapshot"]
    quoted_price = next(item["priceCents"] for item in snapshot["items"] if item["productId"] == 1)
    assert quoted_price == 1800
    event = sale_event(device_id, 1, "01HXPRICE00000000000000001", lease["issuedAt"])
    event["catalogVersion"] = snapshot["catalogVersion"]
    event["payload"]["cashReceivedCents"] = 2000

    db.execute("UPDATE products SET price_cents = 1900 WHERE id = 1")
    db.commit()

    first = sync(client, lease, [event])["acks"][0]
    assert first["applied"] is True
    receipt = first["receipt"]
    assert (receipt["totalCents"], receipt["cashReceivedCents"], receipt["changeCents"]) == (1800, 2000, 200)

    duplicate = sync(client, lease, [event])["acks"][0]
    assert duplicate["duplicate"] is True
    assert duplicate["receipt"] == receipt
    sale_id = receipt["saleId"]
    lines = db.execute(
        "SELECT unit_price_cents, line_total_cents FROM sale_items WHERE sale_id = ?",
        (sale_id,),
    ).fetchall()
    assert [tuple(row) for row in lines] == [(1800, 1800)]
    payments = db.execute("SELECT amount_cents FROM payments WHERE sale_id = ?", (sale_id,)).fetchall()
    assert [row[0] for row in payments] == [1800]
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 23000


def test_checkout_commit_survives_lost_response_and_offline_replay(settings, fake_pey, db):
    device_id = "lost-checkout-response"
    event_id = "01HXRETRY00000000000000001"
    checkout = {
        "employeeId": 1,
        "items": [{"productId": 1, "qtyMilli": 1000}],
        "paymentMethod": "cash",
        "cashReceivedCents": 2000,
    }

    with TestClient(create_app(settings=settings, pey_client=fake_pey)) as client:
        issued = issued_catalog(client, device_id)
        lease = issued["lease"]
        event = sale_event(device_id, 1, event_id, lease["issuedAt"])
        event["catalogVersion"] = issued["snapshot"]["catalogVersion"]
        event["payload"] = checkout
        # Model the loss boundary by discarding the response after the request commits.
        assert client.post("/api/sales", json=checkout, headers={"Idempotency-Key": event_id}).status_code == 200

    sale_id = db.execute("SELECT id FROM sales WHERE payment_method = 'cash'").fetchone()[0]
    with TestClient(create_app(settings=settings, pey_client=fake_pey)) as restarted:
        for _ in range(2):
            ack = sync(restarted, lease, [event])["acks"][0]
            assert ack["receipt"]["saleId"] == sale_id
            assert ack["receipt"]["totalCents"] == 1800

    assert db.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM inventory_movements WHERE product_id = 1").fetchone()[0] == 1
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 23000
