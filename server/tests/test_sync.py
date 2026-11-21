"""Server-side offline journal: idempotency, ordered resumption, tenant isolation.

Fixture: two tenants — "Tienda Aurora" (tenant A) and "Tienda Beta" (tenant B)
— one store each, matching the frozen offline-journal contract. All events are
SIMULADO (no real money, no real data).

The three invariants enforced here:

1. Idempotency — resending an event after a lost ACK adds neither money nor
   stock (exactly one sale, one payment, one movement).
2. Ordered resumption — pending events replay in sequence order and the server
   returns a per-sequence receipt plus the next expected sequence; replaying
   the whole batch changes nothing.
3. Tenant isolation — a device is bound to one tenant forever, and an event
   can never be replayed into a different tenant's store.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server.sync_routes import register as register_sync_routes

pytestmark = pytest.mark.usefixtures("staff")

TENANT_A = "tenant-aurora"
TENANT_B = "tenant-beta"
STORE_A = "tienda-aurora"
STORE_B = "tienda-beta"
OWNER_A = 101
OWNER_B = 201
PRODUCT_A = 1001
PRODUCT_B = 2001


@pytest.fixture
def sync_client(app):
    """The FastAPI app with the offline sync router registered."""

    register_sync_routes(app)
    with TestClient(app) as test_client:
        yield test_client


def evtid(n: int) -> str:
    """A 26-character ULID-shaped idempotency key for test events."""

    return f"01HXEVT{n:019d}"


def seed_store(
    db,
    store_id: str,
    owner_id: int,
    owner_name: str,
    product_id: int,
    *,
    price_cents: int = 1800,
    stock_milli: int = 24000,
) -> None:
    db.execute("INSERT INTO stores (id, name) VALUES (?, ?)", (store_id, store_id))
    db.execute(
        """INSERT INTO employees
               (id, store_id, name, nickname, role, active,
                can_sell, can_fiado, can_inventory)
           VALUES (?, ?, ?, NULL, 'owner', 1, 1, 1, 1)""",
        (owner_id, store_id, owner_name),
    )
    db.execute(
        """INSERT INTO products
               (id, store_id, name, aliases, unit, price_cents, stock_milli,
                low_stock_milli, quick)
           VALUES (?, ?, ?, '[]', 'pieza', ?, ?, 5000, 1)""",
        (product_id, store_id, "Coca-Cola 600 ml", price_cents, stock_milli),
    )
    db.commit()


def get_lease(client, tenant_id: str, store_id: str, device_id: str) -> dict:
    response = client.post(
        "/api/sync/lease",
        json={
            "deviceId": device_id,
            "storeId": store_id,
            "tenantId": tenant_id,
            "membershipId": "mem-" + device_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["lease"]


def sync_events(client, lease: dict, events: list[dict]) -> dict:
    response = client.post(
        "/api/sync/events", json={"lease": lease, "events": events}
    )
    assert response.status_code == 200, response.text
    return response.json()


def sale_event(
    device_id: str,
    tenant_id: str,
    store_id: str,
    sequence: int,
    event_id: str,
    occurred_at: int,
    product_id: int,
    *,
    employee_id: int,
    qty_milli: int = 1000,
    cash_received_cents: int | None = None,
    catalog_version: int = 1,
) -> dict:
    payload: dict = {
        "employeeId": employee_id,
        "items": [{"productId": product_id, "qtyMilli": qty_milli}],
        "paymentMethod": "cash",
    }
    if cash_received_cents is not None:
        payload["cashReceivedCents"] = cash_received_cents
    return {
        "v": 1,
        "eventId": event_id,
        "deviceId": device_id,
        "sequence": sequence,
        "type": "sale.created",
        "tenantId": tenant_id,
        "storeId": store_id,
        "catalogVersion": catalog_version,
        "occurredAt": occurred_at,
        "payload": payload,
    }


def adjust_event(
    device_id: str,
    tenant_id: str,
    store_id: str,
    sequence: int,
    event_id: str,
    occurred_at: int,
    product_id: int,
    *,
    employee_id: int,
    delta_milli: int,
    reason: str = "conteo",
) -> dict:
    return {
        "v": 1,
        "eventId": event_id,
        "deviceId": device_id,
        "sequence": sequence,
        "type": "inventory.adjust",
        "tenantId": tenant_id,
        "storeId": store_id,
        "catalogVersion": 1,
        "occurredAt": occurred_at,
        "payload": {
            "employeeId": employee_id,
            "productId": product_id,
            "deltaMilli": delta_milli,
            "reason": reason,
        },
    }


def store_totals(db, store_id: str):
    """(sales_count, total_cents, stock_milli, movements_count, payments_count)."""

    sales = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(total_cents), 0) AS t "
        "FROM sales WHERE store_id = ?",
        (store_id,),
    ).fetchone()
    stock = db.execute(
        "SELECT stock_milli FROM products WHERE store_id = ?", (store_id,)
    ).fetchone()[0]
    movements = db.execute(
        """SELECT COUNT(*) AS n FROM inventory_movements
           WHERE product_id IN (SELECT id FROM products WHERE store_id = ?)""",
        (store_id,),
    ).fetchone()[0]
    payments = db.execute(
        "SELECT COUNT(*) AS n FROM payments WHERE source = 'offline_outbox'"
    ).fetchone()[0]
    return {
        "salesCount": sales["n"],
        "totalCents": sales["t"],
        "stockMilli": stock,
        "movements": movements,
        "payments": payments,
    }


# ---------------------------------------------------------------------------
# 1. Idempotency: a retry after a lost ACK adds neither money nor stock
# ---------------------------------------------------------------------------


def test_retry_after_lost_ack_adds_neither_money_nor_stock(sync_client, db):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    seed_store(db, STORE_B, OWNER_B, "Don Beto", PRODUCT_B)
    lease = get_lease(sync_client, TENANT_A, STORE_A, "device-a")

    event = sale_event(
        "device-a",
        TENANT_A,
        STORE_A,
        1,
        evtid(1),
        lease["issuedAt"] + 1,
        PRODUCT_A,
        employee_id=OWNER_A,
        qty_milli=1000,
        cash_received_cents=5000,
    )

    first = sync_events(sync_client, lease, [event])
    assert first["acks"][0]["applied"] is True
    assert first["acks"][0]["receipt"]["totalCents"] == 1800

    # The ACK was lost: the device resends the exact same batch.
    second = sync_events(sync_client, lease, [event])
    ack = second["acks"][0]
    assert ack["applied"] is False
    assert ack["duplicate"] is True
    assert ack["receipt"]["saleId"] == first["acks"][0]["receipt"]["saleId"]

    totals = store_totals(db, STORE_A)
    assert totals["salesCount"] == 1
    assert totals["totalCents"] == 1800
    assert totals["stockMilli"] == 23000  # 24000 - 1000, applied exactly once
    assert totals["movements"] == 1
    assert totals["payments"] == 1


def test_inventory_adjust_retry_moves_stock_once(sync_client, db):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    lease = get_lease(sync_client, TENANT_A, STORE_A, "device-a")

    event = adjust_event(
        "device-a",
        TENANT_A,
        STORE_A,
        1,
        evtid(1),
        lease["issuedAt"] + 1,
        PRODUCT_A,
        employee_id=OWNER_A,
        delta_milli=-1000,
    )

    sync_events(sync_client, lease, [event])
    assert db.execute(
        "SELECT stock_milli FROM products WHERE id = ?", (PRODUCT_A,)
    ).fetchone()[0] == 23000

    sync_events(sync_client, lease, [event])
    assert db.execute(
        "SELECT stock_milli FROM products WHERE id = ?", (PRODUCT_A,)
    ).fetchone()[0] == 23000
    assert (
        db.execute(
            "SELECT COUNT(*) FROM inventory_movements WHERE product_id = ?",
            (PRODUCT_A,),
        ).fetchone()[0]
        == 1
    )


def test_same_event_id_different_content_is_reviewed_not_mutated(sync_client, db):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    lease = get_lease(sync_client, TENANT_A, STORE_A, "device-a")

    event_id = evtid(1)
    first = sale_event(
        "device-a", TENANT_A, STORE_A, 1, event_id, lease["issuedAt"] + 1,
        PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000,
    )
    sync_events(sync_client, lease, [first])

    # Same id, different content: must be flagged for review, never mutated.
    altered = sale_event(
        "device-a", TENANT_A, STORE_A, 1, event_id, lease["issuedAt"] + 1,
        PRODUCT_A, employee_id=OWNER_A, qty_milli=2000, cash_received_cents=5000,
    )
    result = sync_events(sync_client, lease, [altered])
    ack = result["acks"][0]
    assert ack["applied"] is False
    assert ack["conflict"] is True
    assert ack["error"] == "idempotency_conflict"

    totals = store_totals(db, STORE_A)
    assert totals["salesCount"] == 1
    assert totals["totalCents"] == 1800
    assert totals["stockMilli"] == 23000


# ---------------------------------------------------------------------------
# 2. Ordered resumption
# ---------------------------------------------------------------------------


def test_ordered_resumption_replays_in_order_and_resend_changes_nothing(
    sync_client, db
):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    lease = get_lease(sync_client, TENANT_A, STORE_A, "device-a")
    base = lease["issuedAt"] + 1

    events = [
        sale_event("device-a", TENANT_A, STORE_A, 1, evtid(1), base,
                   PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000),
        sale_event("device-a", TENANT_A, STORE_A, 2, evtid(2), base + 1,
                   PRODUCT_A, employee_id=OWNER_A, qty_milli=2000, cash_received_cents=10000),
        sale_event("device-a", TENANT_A, STORE_A, 3, evtid(3), base + 2,
                   PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000),
    ]

    result = sync_events(sync_client, lease, events)
    assert [a["sequence"] for a in result["acks"]] == [1, 2, 3]
    assert all(a["applied"] for a in result["acks"])
    assert result["nextSequence"] == 4

    totals = store_totals(db, STORE_A)
    assert totals["salesCount"] == 3
    assert totals["totalCents"] == 7200  # 1800 + 3600 + 1800
    assert totals["stockMilli"] == 20000  # 24000 - 4000
    assert totals["movements"] == 3

    # Replay the entire pending batch (every ACK lost): nothing changes.
    again = sync_events(sync_client, lease, events)
    assert all(a["duplicate"] for a in again["acks"])
    assert store_totals(db, STORE_A) == totals


def test_out_of_order_replay_applies_each_event_exactly_once(sync_client, db):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    lease = get_lease(sync_client, TENANT_A, STORE_A, "device-a")
    base = lease["issuedAt"] + 1

    events = [
        sale_event("device-a", TENANT_A, STORE_A, 1, evtid(1), base,
                   PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000),
        sale_event("device-a", TENANT_A, STORE_A, 2, evtid(2), base + 1,
                   PRODUCT_A, employee_id=OWNER_A, qty_milli=2000, cash_received_cents=10000),
    ]

    # Sequence 2 arrives before sequence 1; the high-water mark is max+1.
    result = sync_events(sync_client, lease, [events[1], events[0]])
    assert all(a["applied"] for a in result["acks"])
    assert result["nextSequence"] == 3

    # The gap is filled later; neither event is applied twice.
    gap = sale_event("device-a", TENANT_A, STORE_A, 3, evtid(3), base + 2,
                     PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000)
    result = sync_events(sync_client, lease, [gap])
    assert result["acks"][0]["applied"] is True

    totals = store_totals(db, STORE_A)
    assert totals["salesCount"] == 3
    assert totals["totalCents"] == 7200
    assert totals["stockMilli"] == 20000


# ---------------------------------------------------------------------------
# 3. Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_blocks_cross_tenant_replay(sync_client, db):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    seed_store(db, STORE_B, OWNER_B, "Don Beto", PRODUCT_B)

    lease_a = get_lease(sync_client, TENANT_A, STORE_A, "device-a")
    event = sale_event(
        "device-a", TENANT_A, STORE_A, 1, evtid(1), lease_a["issuedAt"] + 1,
        PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000,
    )
    sync_events(sync_client, lease_a, [event])

    # The same device cannot be re-bound to another tenant.
    rebind = sync_client.post(
        "/api/sync/lease",
        json={
            "deviceId": "device-a",
            "storeId": STORE_B,
            "tenantId": TENANT_B,
            "membershipId": "mem-device-a",
        },
    )
    assert rebind.status_code == 409

    # A device bound to tenant B cannot replay tenant A's event.
    lease_b = get_lease(sync_client, TENANT_B, STORE_B, "device-b")
    result = sync_events(sync_client, lease_b, [event])
    ack = result["acks"][0]
    assert ack["applied"] is False
    assert ack["error"] in {"device_mismatch", "tenant_mismatch"}

    # Tenant B's store is untouched.
    totals_b = store_totals(db, STORE_B)
    assert totals_b["salesCount"] == 0
    assert totals_b["totalCents"] == 0
    assert totals_b["stockMilli"] == 24000
    assert totals_b["movements"] == 0


def test_event_claiming_another_tenant_is_rejected(sync_client, db):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    seed_store(db, STORE_B, OWNER_B, "Don Beto", PRODUCT_B)
    lease_a = get_lease(sync_client, TENANT_A, STORE_A, "device-a")

    # device-a presents a valid tenant-A lease but claims a tenant-B event.
    forged = sale_event(
        "device-a", TENANT_B, STORE_B, 1, evtid(1), lease_a["issuedAt"] + 1,
        PRODUCT_B, employee_id=OWNER_B, qty_milli=1000, cash_received_cents=5000,
    )
    result = sync_events(sync_client, lease_a, [forged])
    ack = result["acks"][0]
    assert ack["applied"] is False
    assert ack["error"] == "tenant_mismatch"
    assert store_totals(db, STORE_B)["salesCount"] == 0


# ---------------------------------------------------------------------------
# Lease expiry: a legitimate pre-expiry operation still syncs; a post-expiry
# record requires re-authorization and is never silently dropped.
# ---------------------------------------------------------------------------


def test_lease_expiry_keeps_pre_expiry_events_and_blocks_post_expiry(
    sync_client, db
):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    lease = get_lease(sync_client, TENANT_A, STORE_A, "device-a")

    pre_expiry = sale_event(
        "device-a", TENANT_A, STORE_A, 1, evtid(1), lease["expiresAt"] - 10,
        PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000,
    )
    post_expiry = sale_event(
        "device-a", TENANT_A, STORE_A, 2, evtid(2), lease["expiresAt"] + 10,
        PRODUCT_A, employee_id=OWNER_A, qty_milli=1000, cash_received_cents=5000,
    )

    result = sync_events(sync_client, lease, [pre_expiry, post_expiry])
    acks = {a["eventId"]: a for a in result["acks"]}
    assert acks[evtid(1)]["applied"] is True
    assert acks[evtid(2)]["applied"] is False
    assert acks[evtid(2)]["error"] == "lease_expired"

    # Only the pre-expiry sale took effect.
    totals = store_totals(db, STORE_A)
    assert totals["salesCount"] == 1
    assert totals["stockMilli"] == 23000


def test_lease_and_snapshot_are_signed(sync_client, db):
    seed_store(db, STORE_A, OWNER_A, "Doña Aurora", PRODUCT_A)
    response = sync_client.post(
        "/api/sync/lease",
        json={
            "deviceId": "device-a",
            "storeId": STORE_A,
            "tenantId": TENANT_A,
            "membershipId": "mem-a",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lease"]["signature"]
    assert body["snapshot"]["signature"]
    assert body["snapshot"]["items"][0]["priceCents"] == 1800
