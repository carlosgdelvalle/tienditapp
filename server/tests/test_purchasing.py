"""Purchasing and replenishment: suppliers, purchase orders, goods receipts.

SIMULADO: no real supplier, no real money, no real data. The router is
registered manually because server/main.py is intentionally left untouched for
the coordinator to wire (the same pattern as server/tests/test_sync.py).

Covered here:
1. Two receipts for the SAME shipment -> exactly one stock increase + a
   traceable receipt_cases row (duplicate_shipment); inventory is never doubled.
2. An exact retry (same clientReceiptId) returns the stored receipt idempotently.
3. Discrepancy (received != ordered) -> approval -> stock; the order advances
   to partial/received and the difference is captured.
4. Purchase cost is snapshotted in cents + quantity received at approval.
5. Supplier and purchase-order lifecycle (draft -> issue -> cancel).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.db import STORE_ID
from server.purchasing import ensure_purchasing_schema
from server.routes_purchasing import register as register_purchasing

pytestmark = pytest.mark.usefixtures("staff")


def hdr(employee_id: int) -> dict[str, str]:
    """SIMULADO identity header, mirroring conftest.employee_headers."""

    return {"X-Employee-Id": str(employee_id)}


@pytest.fixture
def purchasing_client(app):
    """The FastAPI app with the purchasing router registered."""

    register_purchasing(app)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def purchasing_db(app, db):
    """A raw connection with the purchasing schema ensured for direct asserts."""

    ensure_purchasing_schema(db)
    return db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _supplier(client: TestClient, name: str = "Proveedor SIMULADO") -> dict:
    response = client.post(
        "/api/suppliers", json={"name": name, "contact": "55-0000-0000"}, headers=hdr(1)
    )
    assert response.status_code == 200, response.text
    return response.json()


def _issued_po(
    client: TestClient,
    supplier_id: int,
    *,
    product_id: int = 1,
    qty_milli: int = 10000,
    unit_cost_cents: int = 1200,
) -> dict:
    created = client.post(
        "/api/purchase-orders",
        json={
            "supplierId": supplier_id,
            "lines": [
                {"productId": product_id, "qtyMilli": qty_milli, "unitCostCents": unit_cost_cents}
            ],
        },
        headers=hdr(1),
    )
    assert created.status_code == 200, created.text
    po = created.json()
    assert po["status"] == "draft"
    issued = client.post(f"/api/purchase-orders/{po['id']}/issue", headers=hdr(1))
    assert issued.status_code == 200, issued.text
    assert issued.json()["purchaseOrder"]["status"] == "issued"
    return po


def _receipt(
    client: TestClient,
    po_id: int,
    *,
    product_id: int = 1,
    qty_milli: int = 5000,
    shipment_ref: str = "shipment-001",
    client_receipt_id: str | None = None,
) -> dict:
    response = client.post(
        "/api/receipts",
        json={
            "purchaseOrderId": po_id,
            "lines": [{"productId": product_id, "qtyMilli": qty_milli}],
            "shipmentRef": shipment_ref,
            **({"clientReceiptId": client_receipt_id} if client_receipt_id else {}),
        },
        headers=hdr(3),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Two receipts for the same shipment -> one stock increase + a traceable case
# ---------------------------------------------------------------------------


def test_two_receipts_same_shipment_do_not_double_inventory(
    purchasing_client, purchasing_db
):
    client = purchasing_client
    db = purchasing_db

    supplier = _supplier(client)
    po = _issued_po(client, supplier["id"], product_id=1, qty_milli=10000, unit_cost_cents=1200)
    before = db.execute(
        "SELECT stock_milli FROM products WHERE id = 1"
    ).fetchone()[0]

    first = _receipt(
        client,
        po["id"],
        qty_milli=5000,
        shipment_ref="shipment-001",
        client_receipt_id="rcpt-aaa",
    )
    assert first["duplicate"] is False
    assert first["receipt"]["status"] == "awaiting_approval"
    receipt_id = first["receipt"]["id"]

    # A second receipt for the SAME shipment (different client id) is flagged.
    second = _receipt(
        client,
        po["id"],
        qty_milli=5000,
        shipment_ref="shipment-001",
        client_receipt_id="rcpt-bbb",
    )
    assert second["duplicate"] is True
    assert second["idempotent"] is False
    assert second["receipt"]["id"] == receipt_id
    assert second["case"] is not None
    assert second["case"]["kind"] == "duplicate_shipment"

    # Approve the original once.
    approved = client.post(f"/api/receipts/{receipt_id}/approve", headers=hdr(1))
    assert approved.status_code == 200, approved.text
    assert approved.json()["receipt"]["status"] == "approved"

    # Stock increased exactly once (5000 milli, not 10000).
    after = db.execute(
        "SELECT stock_milli FROM products WHERE id = 1"
    ).fetchone()[0]
    assert after == before + 5000

    # Exactly one receipt row, one receipt movement and one traceable case.
    assert (
        db.execute(
            "SELECT COUNT(*) FROM receipts WHERE store_id = ?", (STORE_ID,)
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM inventory_movements "
            "WHERE product_id = 1 AND reason = 'receipt'"
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM receipt_cases WHERE kind = 'duplicate_shipment'"
        ).fetchone()[0]
        == 1
    )


def test_idempotent_retry_same_client_receipt_id(purchasing_client, purchasing_db):
    client = purchasing_client
    db = purchasing_db

    supplier = _supplier(client)
    po = _issued_po(client, supplier["id"])

    first = _receipt(
        client, po["id"], shipment_ref="shipment-retry", client_receipt_id="rcpt-same"
    )
    assert first["duplicate"] is False

    # The ACK was lost: the device re-sends the SAME receipt id.
    retry = _receipt(
        client, po["id"], shipment_ref="shipment-retry", client_receipt_id="rcpt-same"
    )
    assert retry["duplicate"] is True
    assert retry["idempotent"] is True
    assert retry["receipt"]["id"] == first["receipt"]["id"]
    assert retry["case"] is None

    # No second receipt row, and no duplicate_shipment case was opened.
    assert (
        db.execute(
            "SELECT COUNT(*) FROM receipts WHERE store_id = ?", (STORE_ID,)
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM receipt_cases WHERE kind = 'duplicate_shipment'"
        ).fetchone()[0]
        == 0
    )


# ---------------------------------------------------------------------------
# Discrepancy -> approval -> stock
# ---------------------------------------------------------------------------


def test_discrepancy_then_approval_applies_stock(purchasing_client, purchasing_db):
    client = purchasing_client
    db = purchasing_db

    supplier = _supplier(client)
    po = _issued_po(client, supplier["id"], product_id=2, qty_milli=10000, unit_cost_cents=800)
    before = db.execute(
        "SELECT stock_milli FROM products WHERE id = 2"
    ).fetchone()[0]

    # Receive 8 of 10 ordered -> a shortfall of 2 units.
    body = _receipt(
        client, po["id"], product_id=2, qty_milli=8000, shipment_ref="shipment-002"
    )
    assert body["duplicate"] is False
    receipt = body["receipt"]
    assert receipt["status"] == "awaiting_approval"
    line = receipt["lines"][0]
    assert line["orderedMilli"] == 10000
    assert line["qtyMilli"] == 8000
    assert line["discrepancyMilli"] == -2000
    # The difference is captured as a traceable discrepancy case.
    assert body["case"] is not None
    assert body["case"]["kind"] == "discrepancy"

    # Approval publishes stock exactly once, by the received quantity.
    approved = client.post(f"/api/receipts/{receipt['id']}/approve", headers=hdr(1))
    assert approved.status_code == 200, approved.text
    assert approved.json()["receipt"]["status"] == "approved"

    after = db.execute(
        "SELECT stock_milli FROM products WHERE id = 2"
    ).fetchone()[0]
    assert after == before + 8000

    movement = db.execute(
        "SELECT delta_milli, reason FROM inventory_movements "
        "WHERE product_id = 2 AND reason = 'receipt' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert movement["delta_milli"] == 8000

    # The order advances to partial (not received): 8 of 10 arrived.
    assert (
        db.execute(
            "SELECT status FROM purchase_orders WHERE id = ?", (po["id"],)
        ).fetchone()[0]
        == "partial"
    )


def test_surplus_requires_authorization_and_advances_order(purchasing_client, purchasing_db):
    client = purchasing_client
    db = purchasing_db

    supplier = _supplier(client)
    po = _issued_po(client, supplier["id"], product_id=1, qty_milli=10000, unit_cost_cents=1200)
    before = db.execute(
        "SELECT stock_milli FROM products WHERE id = 1"
    ).fetchone()[0]

    # Receive 12 of 10 ordered -> surplus; the discrepancy is captured and the
    # owner's approval is the authorization.
    body = _receipt(
        client, po["id"], qty_milli=12000, shipment_ref="shipment-surplus"
    )
    assert body["receipt"]["lines"][0]["discrepancyMilli"] == 2000
    assert body["case"]["kind"] == "discrepancy"

    approved = client.post(
        f"/api/receipts/{body['receipt']['id']}/approve", headers=hdr(1)
    )
    assert approved.status_code == 200, approved.text

    assert (
        db.execute(
            "SELECT stock_milli FROM products WHERE id = 1"
        ).fetchone()[0]
        == before + 12000
    )
    assert (
        db.execute(
            "SELECT status FROM purchase_orders WHERE id = ?", (po["id"],)
        ).fetchone()[0]
        == "received"
    )


# ---------------------------------------------------------------------------
# Purchase cost in cents + quantity received
# ---------------------------------------------------------------------------


def test_purchase_cost_recorded_in_cents(purchasing_client, purchasing_db):
    client = purchasing_client
    db = purchasing_db

    supplier = _supplier(client)
    po = _issued_po(client, supplier["id"], product_id=1, qty_milli=10000, unit_cost_cents=1200)

    body = _receipt(
        client, po["id"], qty_milli=5000, shipment_ref="shipment-cost"
    )
    receipt_id = body["receipt"]["id"]

    # Before approval there is no cost snapshot.
    line_before = body["receipt"]["lines"][0]
    assert line_before["unitCostCents"] is None
    assert line_before["purchaseCostCents"] is None

    approved = client.post(f"/api/receipts/{receipt_id}/approve", headers=hdr(1))
    assert approved.status_code == 200, approved.text

    line = approved.json()["receipt"]["lines"][0]
    assert line["unitCostCents"] == 1200
    # 1200 cents/unit * 5 units = 6000 cents, snapshotted at approval.
    assert line["purchaseCostCents"] == 6000
    assert line["qtyMilli"] == 5000

    # Durable: the snapshot lives in receipt_lines, not recomputed later.
    row = db.execute(
        "SELECT unit_cost_cents, purchase_cost_cents, qty_milli "
        "FROM receipt_lines WHERE receipt_id = ?",
        (receipt_id,),
    ).fetchone()
    assert row["unit_cost_cents"] == 1200
    assert row["purchase_cost_cents"] == 6000
    assert row["qty_milli"] == 5000


def test_unknown_cost_stays_null(purchasing_client):
    client = purchasing_client

    supplier = _supplier(client)
    po = _issued_po(
        client, supplier["id"], product_id=1, qty_milli=10000, unit_cost_cents=None
    )
    # A PO without a unit cost still receives and approves; cost is never a
    # synthetic zero (metrics contract: unknown cost is reported separately).
    body = _receipt(client, po["id"], qty_milli=5000, shipment_ref="shipment-nocost")
    approved = client.post(
        f"/api/receipts/{body['receipt']['id']}/approve", headers=hdr(1)
    )
    assert approved.status_code == 200, approved.text
    line = approved.json()["receipt"]["lines"][0]
    assert line["unitCostCents"] is None
    assert line["purchaseCostCents"] is None


# ---------------------------------------------------------------------------
# Approval idempotency + supplier/PO lifecycle
# ---------------------------------------------------------------------------


def test_approval_is_idempotent(purchasing_client, purchasing_db):
    client = purchasing_client
    db = purchasing_db

    supplier = _supplier(client)
    po = _issued_po(client, supplier["id"])
    body = _receipt(client, po["id"], shipment_ref="shipment-approve")
    receipt_id = body["receipt"]["id"]

    first = client.post(f"/api/receipts/{receipt_id}/approve", headers=hdr(1))
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False

    again = client.post(f"/api/receipts/{receipt_id}/approve", headers=hdr(1))
    assert again.status_code == 200, again.text
    assert again.json()["duplicate"] is True

    assert (
        db.execute(
            "SELECT COUNT(*) FROM inventory_movements "
            "WHERE product_id = 1 AND reason = 'receipt'"
        ).fetchone()[0]
        == 1
    )


def test_supplier_and_purchase_order_lifecycle(purchasing_client, purchasing_db):
    client = purchasing_client
    db = purchasing_db

    created = client.post(
        "/api/suppliers", json={"name": "Coca-Cola FEMSA", "contact": "ventas@femsa.mx"}, headers=hdr(1)
    )
    assert created.status_code == 200, created.text
    supplier = created.json()
    assert supplier["active"] is True

    patched = client.patch(
        f"/api/suppliers/{supplier['id']}",
        json={"contact": "nuevo@femsa.mx"},
        headers=hdr(1),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["contact"] == "nuevo@femsa.mx"

    listed = client.get("/api/suppliers")
    assert listed.status_code == 200
    assert any(item["id"] == supplier["id"] for item in listed.json()["items"])

    # A non-owner cannot create a supplier.
    denied = client.post(
        "/api/suppliers", json={"name": "No autorizado"}, headers=hdr(3)
    )
    assert denied.status_code == 403

    # Draft -> issue -> cancel on a purchase order.
    po = client.post(
        "/api/purchase-orders",
        json={
            "supplierId": supplier["id"],
            "lines": [{"productId": 1, "qtyMilli": 3000, "unitCostCents": 1000}],
        },
        headers=hdr(1),
    )
    assert po.status_code == 200, po.text
    assert po.json()["status"] == "draft"

    issued = client.post(f"/api/purchase-orders/{po.json()['id']}/issue", headers=hdr(1))
    assert issued.status_code == 200
    assert issued.json()["purchaseOrder"]["status"] == "issued"

    canceled = client.post(
        f"/api/purchase-orders/{po.json()['id']}/cancel", headers=hdr(1)
    )
    assert canceled.status_code == 200
    assert canceled.json()["purchaseOrder"]["status"] == "canceled"

    # A canceled order cannot be received against.
    blocked = client.post(
        "/api/receipts",
        json={
            "purchaseOrderId": po.json()["id"],
            "lines": [{"productId": 1, "qtyMilli": 1000}],
        },
        headers=hdr(3),
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]

    # Soft delete keeps history; the supplier becomes inactive.
    deleted = client.delete(f"/api/suppliers/{supplier['id']}", headers=hdr(1))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["active"] is False
    assert db.execute(
        "SELECT active FROM suppliers WHERE id = ?", (supplier["id"],)
    ).fetchone()[0] == 0
