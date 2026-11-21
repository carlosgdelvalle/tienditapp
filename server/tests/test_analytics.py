"""Analytics and Control revenue (M6): margin, reconciliation, access separation.

The router is registered manually on the shared app fixture because
server/main.py is intentionally left untouched (same pattern as
test_purchasing.py / test_sync.py). Core functions are exercised directly on a
connection built with server.db.connect (autocommit) so timestamp control for
the weighted-average-cost snapshot is exact.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import analytics as an
from server.db import STORE_ID, connect, initialize_db
from server.purchasing import (
    approve_receipt,
    create_purchase_order,
    create_receipt,
    create_supplier,
    ensure_purchasing_schema,
    issue_purchase_order,
)
from server.routes_analytics import register as register_analytics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aconn(settings):
    """A raw autocommit connection with db + purchasing + analytics schemas."""

    initialize_db(settings.db_path, seed_catalog=settings.seed_catalog)
    conn = connect(settings.db_path)
    ensure_purchasing_schema(conn)
    an.ensure_analytics_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def analytics_client(app):
    register_analytics(app)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approved_receipt(
    conn,
    *,
    store_id=STORE_ID,
    product_id=1,
    qty_milli=10000,
    unit_cost_cents=1000,
    approved_at=1000.0,
):
    supplier = create_supplier(conn, store_id=store_id, name="Proveedor " + store_id, now=900.0)
    po = create_purchase_order(
        conn,
        store_id=store_id,
        supplier_id=supplier["id"],
        lines=[{"productId": product_id, "qtyMilli": qty_milli, "unitCostCents": unit_cost_cents}],
        employee_id=1,
        now=910.0,
    )
    issue_purchase_order(conn, store_id=store_id, po_id=po["id"], now=920.0)
    rcpt = create_receipt(
        conn,
        store_id=store_id,
        purchase_order_id=po["id"],
        lines=[{"productId": product_id, "qtyMilli": qty_milli}],
        employee_id=1,
        now=930.0,
    )
    approve_receipt(
        conn, store_id=store_id, receipt_id=rcpt["receipt"]["id"], approved_by=1, now=approved_at
    )


def _sale(
    conn,
    *,
    sale_id,
    store_id=STORE_ID,
    product_id=1,
    qty_milli=1000,
    unit_price_cents=2000,
    status="paid_cash",
    payment_method="cash",
    created_at=2000.0,
    employee_id=1,
):
    line_total = unit_price_cents * qty_milli // 1000
    conn.execute(
        """INSERT INTO sales
               (id, store_id, employee_id, created_at, status, payment_method,
                total_cents, charged_cents)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (sale_id, store_id, employee_id, created_at, status, payment_method, line_total, line_total),
    )
    conn.execute(
        """INSERT INTO sale_items
               (sale_id, product_id, name, unit, qty_milli, unit_price_cents, line_total_cents)
           VALUES (?, ?, ?, 'pieza', ?, ?, ?)""",
        (sale_id, product_id, "Producto", qty_milli, unit_price_cents, line_total),
    )
    return line_total


def _role_hdr(role: str) -> dict[str, str]:
    return {"X-Platform-Role": role}


# ---------------------------------------------------------------------------
# Gross merchandise margin
# ---------------------------------------------------------------------------


def test_margin_unknown_cost_is_segregated(aconn):
    _sale(aconn, sale_id="s1", qty_milli=1000, unit_price_cents=2000)
    report = an.gross_margin_report(aconn, STORE_ID)
    assert report["netSalesCents"] == 2000
    assert report["attributableCostCents"] == 0
    # Never treated as 100% margin: with no costable line the margin is None.
    assert report["grossMarginCents"] is None
    assert report["coverage"]["lines"]["known"] == 0
    assert report["coverage"]["lines"]["unknown"] == 1
    assert report["coverage"]["lines"]["total"] == 1
    assert report["segregated"]["unknownCost"]["lines"] == 1
    assert report["segregated"]["unknownCost"]["salesCents"] == 2000


def test_margin_known_cost(aconn):
    _approved_receipt(aconn, product_id=1, qty_milli=10000, unit_cost_cents=1000, approved_at=1000.0)
    _sale(aconn, sale_id="s1", product_id=1, qty_milli=1000, unit_price_cents=2000, created_at=2000.0)
    report = an.gross_margin_report(aconn, STORE_ID)
    assert report["attributableCostCents"] == 1000
    assert report["grossMarginCents"] == 1000
    assert report["coverage"]["lines"]["known"] == 1


def test_margin_weighted_average_across_receipts(aconn):
    _approved_receipt(aconn, product_id=1, qty_milli=10000, unit_cost_cents=1000, approved_at=1000.0)
    _approved_receipt(aconn, product_id=1, qty_milli=10000, unit_cost_cents=2000, approved_at=1100.0)
    _sale(aconn, sale_id="s1", product_id=1, qty_milli=1000, unit_price_cents=3000, created_at=2000.0)
    # WAC = (10 * 1000 + 10 * 2000) / 20 = 1500 cents per unit.
    report = an.gross_margin_report(aconn, STORE_ID)
    assert report["attributableCostCents"] == 1500
    assert report["grossMarginCents"] == 1500


def test_later_receipt_does_not_change_closed_margin(aconn):
    _approved_receipt(aconn, product_id=1, qty_milli=10000, unit_cost_cents=1000, approved_at=1000.0)
    _sale(aconn, sale_id="s1", product_id=1, qty_milli=1000, unit_price_cents=3000, created_at=2000.0)
    first = an.gross_margin_report(aconn, STORE_ID)
    assert first["attributableCostCents"] == 1000

    # A later, more expensive purchase arrives after the sale.
    _approved_receipt(aconn, product_id=1, qty_milli=10000, unit_cost_cents=2000, approved_at=3000.0)
    second = an.gross_margin_report(aconn, STORE_ID)
    assert second["attributableCostCents"] == 1000  # unchanged
    assert second["grossMarginCents"] == 2000

    snap = aconn.execute(
        "SELECT cost_status, line_cost_cents FROM sale_cost_snapshots WHERE sale_id = 's1'"
    ).fetchone()
    assert snap["cost_status"] == "known"
    assert snap["line_cost_cents"] == 1000


def test_margin_offline_conflict_segregated(aconn):
    # 5 units with known cost, then sell 8 units: sold beyond the known basis.
    _approved_receipt(aconn, product_id=1, qty_milli=5000, unit_cost_cents=1000, approved_at=1000.0)
    _sale(aconn, sale_id="s1", product_id=1, qty_milli=8000, unit_price_cents=2000, created_at=2000.0)
    report = an.gross_margin_report(aconn, STORE_ID)
    assert report["coverage"]["lines"]["offlineConflict"] == 1
    assert report["coverage"]["lines"]["known"] == 0
    assert report["grossMarginCents"] is None
    assert report["segregated"]["offlineConflict"]["lines"] == 1


def test_margin_tenant_scoping(aconn):
    # Tenant A
    aconn.execute("INSERT INTO stores (id, name) VALUES ('tenant-a', 'Tienda A')")
    aconn.execute(
        "INSERT INTO employees (id, store_id, name, role) VALUES (101, 'tenant-a', 'Owner A', 'owner')"
    )
    aconn.execute(
        "INSERT INTO products (id, store_id, name, unit, price_cents, stock_milli, low_stock_milli) "
        "VALUES (101, 'tenant-a', 'P A', 'pieza', 2000, 0, 0)"
    )
    _approved_receipt(aconn, store_id="tenant-a", product_id=101, qty_milli=10000, unit_cost_cents=1000, approved_at=1000.0)
    _sale(aconn, sale_id="sa", store_id="tenant-a", product_id=101, qty_milli=1000, unit_price_cents=2000, created_at=2000.0, employee_id=101)

    # Tenant B (same product id space, different store)
    aconn.execute("INSERT INTO stores (id, name) VALUES ('tenant-b', 'Tienda B')")
    aconn.execute(
        "INSERT INTO employees (id, store_id, name, role) VALUES (102, 'tenant-b', 'Owner B', 'owner')"
    )
    aconn.execute(
        "INSERT INTO products (id, store_id, name, unit, price_cents, stock_milli, low_stock_milli) "
        "VALUES (102, 'tenant-b', 'P B', 'pieza', 5000, 0, 0)"
    )
    _approved_receipt(aconn, store_id="tenant-b", product_id=102, qty_milli=10000, unit_cost_cents=4000, approved_at=1000.0)
    _sale(aconn, sale_id="sb", store_id="tenant-b", product_id=102, qty_milli=1000, unit_price_cents=5000, created_at=2000.0, employee_id=102)

    a = an.gross_margin_report(aconn, "tenant-a")
    b = an.gross_margin_report(aconn, "tenant-b")
    assert a["netSalesCents"] == 2000
    assert a["attributableCostCents"] == 1000
    assert b["netSalesCents"] == 5000
    assert b["attributableCostCents"] == 4000


# ---------------------------------------------------------------------------
# Control pilot subscription (manual billing)
# ---------------------------------------------------------------------------


def test_bill_control_subscription_with_attribution(aconn):
    res = an.bill_control_subscription(
        aconn, store_id=STORE_ID, campaign="camp-001", owner="owner-maria", receipt_ref="rcpt-1", now=5000.0
    )
    assert res["subscription"]["plan"] == "control"
    assert res["subscription"]["status"] == "active"
    assert res["subscription"]["campaign"] == "camp-001"
    assert res["subscription"]["owner"] == "owner-maria"
    assert res["charge"]["amountCents"] == 14900

    rev = an.control_revenue(aconn, STORE_ID)
    assert rev["grossCents"] == 14900
    assert rev["refundsCents"] == 0
    assert rev["netCents"] == 14900

    ev = aconn.execute("SELECT * FROM analytics_events WHERE event_type = 'control_paid'").fetchone()
    assert ev["campaign"] == "camp-001"
    assert ev["owner"] == "owner-maria"


def test_control_revenue_matches_fixture(aconn):
    billed = []
    for i in range(7):
        billed.append(
            an.bill_control_subscription(aconn, store_id=STORE_ID, campaign=f"camp-{i}", owner="owner-maria", now=5000.0 + i)
        )
    for i in range(2):
        an.refund_subscription_charge(
            aconn,
            subscription_id=billed[i]["subscription"]["id"],
            charge_id=billed[i]["charge"]["id"],
            amount_cents=14900,
            store_id=STORE_ID,
            now=6000.0 + i,
        )
    rev = an.control_revenue(aconn, STORE_ID)
    assert rev["grossCents"] == 104300
    assert rev["refundsCents"] == 29800
    assert rev["netCents"] == 74500


def test_refund_does_not_cancel(aconn):
    res = an.bill_control_subscription(aconn, store_id=STORE_ID, now=5000.0)
    an.refund_subscription_charge(
        aconn,
        subscription_id=res["subscription"]["id"],
        charge_id=res["charge"]["id"],
        amount_cents=14900,
        store_id=STORE_ID,
        now=6000.0,
    )
    sub = aconn.execute("SELECT status FROM subscriptions WHERE id = ?", (res["subscription"]["id"],)).fetchone()
    assert sub["status"] == "active"


# ---------------------------------------------------------------------------
# CoDi reconciliation (recorded / tagged / confirmed are separate series)
# ---------------------------------------------------------------------------


def test_reconcile_codi_fixture():
    r = an.reconcile_codi(recorded_cents=10_000_000, codi_cents=2_000_000, confirmed_cents=1_800_000)
    assert r["pendingCodiCents"] == 200_000
    assert r["confirmedPercentCodiAmount"] == 90.0
    assert r["basis"] == "codiAmount"


def test_simulado_reconciliation():
    r = an.simulado_reconciliation()
    assert r["simulado"] is True
    assert r["pendingCodiCents"] == 200_000
    assert r["confirmedPercentCodiAmount"] == 90.0


def test_cross_comparison_is_rejected():
    # 18,000 / 100,000 = 18% is the forbidden cross-comparison.
    with pytest.raises(an.CrossComparisonError):
        an.codis_confirmation_rate(1_800_000, 10_000_000, basis="recorded")
    # The only valid basis is the CoDi-tagged amount (18,000 / 20,000).
    assert an.codis_confirmation_rate(1_800_000, 2_000_000, basis="codi") == 0.9


def test_reconcile_rejects_invalid_series():
    with pytest.raises(an.CrossComparisonError):
        # confirmed (30,000) > tagged CoDi (20,000) is impossible.
        an.reconcile_codi(recorded_cents=10_000_000, codi_cents=2_000_000, confirmed_cents=3_000_000)


def test_sales_reconciliation_from_durable_sources(aconn):
    _sale(aconn, sale_id="cash1", product_id=1, qty_milli=1000, unit_price_cents=80000, status="paid_cash", payment_method="cash", created_at=1000.0)
    _sale(aconn, sale_id="pey1", product_id=1, qty_milli=1000, unit_price_cents=18000, status="paid_pey", payment_method="pey", created_at=1000.0)
    _sale(aconn, sale_id="pey2", product_id=1, qty_milli=1000, unit_price_cents=2000, status="pending", payment_method="pey", created_at=1000.0)
    r = an.sales_reconciliation(aconn, STORE_ID)
    assert r["recordedCents"] == 100000
    assert r["codiCents"] == 20000
    assert r["confirmedCents"] == 18000
    assert r["pendingCodiCents"] == 2000
    assert r["confirmedPercentCodiAmount"] == 90.0


# ---------------------------------------------------------------------------
# Access separation (analytics / finance / support)
# ---------------------------------------------------------------------------


def test_meta_is_public(analytics_client):
    resp = analytics_client.get("/api/analytics/meta")
    assert resp.status_code == 200
    assert resp.json()["roles"] == ["staff", "analytics", "finance", "support"]


def test_access_separation_margin(analytics_client):
    c = analytics_client
    assert c.get("/api/analytics/margin", headers=_role_hdr("analytics")).status_code == 200
    assert c.get("/api/analytics/margin", headers=_role_hdr("staff")).status_code == 200
    assert c.get("/api/analytics/margin", headers=_role_hdr("finance")).status_code == 403
    assert c.get("/api/analytics/margin", headers=_role_hdr("support")).status_code == 403
    assert c.get("/api/analytics/margin").status_code == 401


def test_access_separation_reconciliation(analytics_client):
    c = analytics_client
    assert c.get("/api/analytics/reconciliation", headers=_role_hdr("support")).status_code == 200
    assert c.get("/api/analytics/reconciliation", headers=_role_hdr("staff")).status_code == 200
    assert c.get("/api/analytics/reconciliation", headers=_role_hdr("analytics")).status_code == 403
    assert c.get("/api/analytics/reconciliation", headers=_role_hdr("finance")).status_code == 403


def test_access_separation_subscriptions(analytics_client):
    c = analytics_client
    assert c.get("/api/analytics/subscriptions", headers=_role_hdr("finance")).status_code == 200
    assert c.get("/api/analytics/subscriptions", headers=_role_hdr("staff")).status_code == 200
    assert c.get("/api/analytics/subscriptions", headers=_role_hdr("analytics")).status_code == 403
    assert c.get("/api/analytics/subscriptions", headers=_role_hdr("support")).status_code == 403
    # Billing is finance-only too.
    denied = c.post("/api/analytics/subscriptions", json={"campaign": "c"}, headers=_role_hdr("analytics"))
    assert denied.status_code == 403


def test_finance_bill_via_http(analytics_client):
    c = analytics_client
    bill = c.post(
        "/api/analytics/subscriptions",
        json={"campaign": "camp-1", "owner": "owner-x"},
        headers=_role_hdr("finance"),
    )
    assert bill.status_code == 200, bill.text
    data = bill.json()
    assert data["charge"]["amountCents"] == 14900
    assert data["subscription"]["campaign"] == "camp-1"

    listing = c.get("/api/analytics/subscriptions", headers=_role_hdr("finance")).json()
    assert listing["revenue"]["grossCents"] == 14900


def test_reconciliation_endpoint_returns_fixture(analytics_client):
    r = analytics_client.get("/api/analytics/reconciliation", headers=_role_hdr("support")).json()
    assert r["simulado"] is True
    assert r["pendingCodiCents"] == 200000
    assert r["confirmedPercentCodiAmount"] == 90.0


def test_margin_endpoint_empty(analytics_client):
    r = analytics_client.get("/api/analytics/margin", headers=_role_hdr("analytics")).json()
    assert r["netSalesCents"] == 0
    assert r["grossMarginCents"] is None
    assert r["coverage"]["lines"]["total"] == 0
