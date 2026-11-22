"""Checkout and till-close core: last-unit conflict, offline cash, handover.

SIMULADO fixtures: no real money, no real data. The last-unit conflict is
driven through the offline outbox (two devices = two tills); the till
closeout drives the cash handover, acceptance, audited variance and the
idempotent retry.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.db import STORE_ID

pytestmark = pytest.mark.usefixtures("staff")


@pytest.fixture
def till_client(app):
    # create_app already wires register_till_routes; the fixture only wraps it.
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Offline cash + last-unit conflict (outbox; sync routes ship with create_app)
# ---------------------------------------------------------------------------


def get_lease(client: TestClient, device_id: str) -> dict:
    response = client.post(
        "/api/sync/lease",
        json={
            "deviceId": device_id,
            "storeId": STORE_ID,
            "tenantId": STORE_ID,
            "membershipId": "mem-" + device_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["lease"]


def sale_event(
    device_id: str,
    sequence: int,
    event_id: str,
    occurred_at: int,
    *,
    product_id: int = 1,
    qty_milli: int = 1000,
) -> dict:
    return {
        "v": 1,
        "eventId": event_id,
        "deviceId": device_id,
        "sequence": sequence,
        "type": "sale.created",
        "tenantId": STORE_ID,
        "storeId": STORE_ID,
        "catalogVersion": 1,
        "occurredAt": occurred_at,
        "payload": {
            "employeeId": 1,
            "items": [{"productId": product_id, "qtyMilli": qty_milli}],
            "paymentMethod": "cash",
        },
    }


def sync(client: TestClient, lease: dict, events: list[dict]) -> dict:
    response = client.post(
        "/api/sync/events", json={"lease": lease, "events": events}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_last_unit_conflict_between_two_tills(client, db):
    # Both tills already accepted cash. The stock shortage must stay auditable.
    db.execute("UPDATE products SET stock_milli = 1000 WHERE id = 1")
    db.commit()

    lease_a = get_lease(client, "till-a")
    lease_b = get_lease(client, "till-b")
    base = lease_a["issuedAt"] + 1

    first_event = sale_event("till-a", 1, "01HXTILLA00000000000000001", base)
    first = sync(client, lease_a, [first_event])
    assert first["acks"][0]["applied"] is True
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == 0

    second_event = sale_event("till-b", 1, "01HXTILLB00000000000000001", base + 1)
    ack = sync(client, lease_b, [second_event])["acks"][0]
    assert ack["applied"] is True
    first_sale = first["acks"][0]["receipt"]["saleId"]
    second_sale = ack["receipt"]["saleId"]
    assert second_sale != first_sale
    stock_after_sales = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    movements_after_sales = db.execute(
        "SELECT id, sale_id, delta_milli, reason FROM inventory_movements WHERE product_id = 1 ORDER BY id",
    ).fetchall()
    assert any(row["sale_id"] == first_sale and row["delta_milli"] == -1000 for row in movements_after_sales)

    for lease, event, original in (
        (lease_a, first_event, first["acks"][0]),
        (lease_b, second_event, ack),
    ):
        replay = sync(client, lease, [event])["acks"][0]
        assert replay["duplicate"] is True
        assert replay["receipt"] == original["receipt"]
    assert db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0] == stock_after_sales
    assert db.execute(
        "SELECT id, sale_id, delta_milli, reason FROM inventory_movements WHERE product_id = 1 ORDER BY id",
    ).fetchall() == movements_after_sales

    sales = db.execute(
        "SELECT id, status, total_cents FROM sales WHERE store_id = ?", (STORE_ID,),
    ).fetchall()
    assert {tuple(row) for row in sales} == {
        (first_sale, "paid_cash", 1800),
        (second_sale, "paid_cash", 1800),
    }
    payments = db.execute(
        "SELECT sale_id, amount_cents FROM payments WHERE source = 'offline_outbox'",
    ).fetchall()
    assert sorted(map(tuple, payments)) == sorted([(first_sale, 1800), (second_sale, 1800)])


# ---------------------------------------------------------------------------
# Online last-unit conflict (POST /api/sales, cash path)
# ---------------------------------------------------------------------------


def test_online_last_unit_oversell_returns_409(client, db):
    # One unit of product 1 remains; the first online sale honors it, the
    # second (a second till selling the last piece via POST /api/sales) is
    # rejected with 409 stock_conflict instead of a 500.
    db.execute("UPDATE products SET stock_milli = 1000 WHERE id = 1")
    db.commit()

    first = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "cash",
            "cashReceivedCents": 2000,
        },
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "cash",
            "cashReceivedCents": 2000,
        },
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["code"] == "stock_conflict"
    assert body.get("message")

    # Exactly one sale and one payment survive; stock never goes negative.
    assert db.execute(
        "SELECT stock_milli FROM products WHERE id = 1"
    ).fetchone()[0] == 0
    assert db.execute(
        "SELECT COUNT(*) FROM sales WHERE store_id = ?", (STORE_ID,)
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM payments WHERE source = 'pos'"
    ).fetchone()[0] == 1


def test_offline_cash_resend_adds_no_money_nor_stock(client, db):
    db.execute("UPDATE products SET stock_milli = 5000 WHERE id = 1")
    db.commit()

    lease = get_lease(client, "till-a")
    event = sale_event(
        "till-a", 1, "01HXOFFLINE0000000000000001", lease["issuedAt"] + 1
    )

    first = sync(client, lease, [event])
    assert first["acks"][0]["applied"] is True

    again = sync(client, lease, [event])
    ack = again["acks"][0]
    assert ack["applied"] is False
    assert ack["duplicate"] is True

    assert db.execute(
        "SELECT stock_milli FROM products WHERE id = 1"
    ).fetchone()[0] == 4000
    assert db.execute(
        "SELECT COUNT(*) FROM sales WHERE store_id = ?", (STORE_ID,)
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM payments WHERE source = 'offline_outbox'"
    ).fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Till close: handover, acceptance, audited variance, idempotent retry
# ---------------------------------------------------------------------------


def test_till_routes_registered_by_create_app(client):
    # create_app wires register_till_routes(app); /api/till/current resolves to
    # the till router (404 "No hay caja abierta") instead of FastAPI's default
    # 404 "Not Found".
    response = client.get("/api/till/current")
    assert response.status_code == 404
    assert response.json()["detail"] == "No hay caja abierta"


def _cash_sale(client: TestClient) -> None:
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "cash",
            "cashReceivedCents": 2000,
        },
    )
    assert response.status_code == 200, response.text


def test_till_handover_and_acceptance(till_client, db):
    opened = till_client.post(
        "/api/till/open", json={"openingFloatCents": 50000, "employeeId": 2}
    )
    assert opened.status_code == 200, opened.text
    shift = opened.json()
    assert shift["status"] == "open"
    shift_id = shift["id"]

    current = till_client.get("/api/till/current")
    assert current.status_code == 200
    assert current.json()["id"] == shift_id

    _cash_sale(till_client)

    # expected = 50000 float + 1800 cash sale = 51800, counted exactly.
    closed = till_client.post(
        "/api/till/close", json={"countedCents": 51800, "employeeId": 2}
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == "delivered"
    assert body["expectedCents"] == 51800
    assert body["countedCents"] == 51800
    assert body["varianceCents"] == 0

    accepted = till_client.post(
        f"/api/till/{shift_id}/accept", json={"employeeId": 1}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["acceptedBy"] == 1


def test_till_audited_variance(till_client, db):
    till_client.post(
        "/api/till/open", json={"openingFloatCents": 50000, "employeeId": 2}
    )
    _cash_sale(till_client)

    # counted short by 1000: 50800 vs expected 51800.
    closed = till_client.post(
        "/api/till/close", json={"countedCents": 50800, "employeeId": 2}
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["expectedCents"] == 51800
    assert body["varianceCents"] == -1000
    assert body["status"] == "delivered"

    # One count movement persisted.
    count_movements = db.execute(
        "SELECT kind FROM till_movements WHERE shift_id = ? AND kind = 'count'",
        (body["id"],),
    ).fetchall()
    assert len(count_movements) == 1

    # The owner records the discrepancy (observed), not silently corrected.
    accepted = till_client.post(
        f"/api/till/{body['id']}/accept",
        json={"employeeId": 1, "reason": "falta por aclarar"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "observed"
    assert accepted.json()["acceptReason"] == "falta por aclarar"

    # Inventory audit variance leaves an inventory_movements row; stock itself
    # is not changed (the correction is a separate justified adjustment).
    before = db.execute(
        "SELECT stock_milli FROM products WHERE id = 2"
    ).fetchone()[0]  # Sabritas: 18000
    audit = till_client.post(
        "/api/till/audit-variance",
        json={"productId": 2, "countedMilli": 17000, "employeeId": 3},
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["deltaMilli"] == -1000
    movement = db.execute(
        "SELECT delta_milli, reason FROM inventory_movements "
        "WHERE product_id = 2 AND reason = 'audit_variance' ORDER BY id DESC LIMIT 1",
    ).fetchone()
    assert movement["delta_milli"] == -1000
    assert db.execute(
        "SELECT stock_milli FROM products WHERE id = 2"
    ).fetchone()[0] == before


def test_till_close_idempotent_retry(till_client, db):
    till_client.post(
        "/api/till/open", json={"openingFloatCents": 50000, "employeeId": 2}
    )
    _cash_sale(till_client)

    first = till_client.post(
        "/api/till/close", json={"countedCents": 51800, "employeeId": 2}
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    shift_id = first_body["id"]

    # The ACK was lost: the device re-sends the same close with the shift id.
    retry = till_client.post(
        "/api/till/close",
        json={"countedCents": 51800, "employeeId": 2, "shiftId": shift_id},
    )
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["duplicate"] is True
    assert retry_body["varianceCents"] == first_body["varianceCents"]

    # The count movement was written exactly once.
    count = db.execute(
        "SELECT COUNT(*) FROM till_movements WHERE shift_id = ? AND kind = 'count'",
        (shift_id,),
    ).fetchone()[0]
    assert count == 1
