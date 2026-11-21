"""Durable, event-sourced metrics and Control revenue (M6 · Analytics and Control).

Everything here reads durable sources only -- sales, sale_items, payments,
receipts/receipt_lines and inventory_movements -- and writes its own append-only
tables (per-line cost snapshots, a versioned event log, and the Control
subscription ledger). Aggregates are never derived from transient client or
screen state.

Invariants implemented (docs/produccion/contracts/metrics.md):

1. Weighted-average cost is snapshotted at sale time in integer cents. The
   snapshot for a sale line only reads receipts approved before the sale, so a
   later purchase can never change a closed margin.
2. Gross merchandise margin = net sales (collected) minus attributable cost, on
   the same quantity/currency basis (integer cents).
3. Never impute a zero cost: a line with unknown or missing cost is reported
   separately with its coverage, never treated as 100% margin.
4. Unknown-cost and offline-conflict lines are segregated and reported with
   explicit coverage; they never pollute the aggregate margin.
5. Only collected sales count: FINAL_PAID_STATUSES (the statuses apply_payment
   or the cash/fiado flows mark paid). pending / por_conciliar / failed never
   count as revenue.
6. Tenant scoping: every query filters by store_id and never mixes tenants.

Access separation roles: analytics, finance, support (+ the staff super-role).

Cost snapshot classification for one sale line (product qty Q sold at time T):

* known            -- there is a known-cost receipt basis approved before T and
                      the cumulative sold quantity through T does not exceed it.
                      line cost = round(total_known_cost * Q / total_known_qty).
* unknown          -- no known-cost receipt basis exists before T (no receipts,
                      or every receipt has a NULL unit cost). Never a zero.
* offline_conflict -- a known-cost basis exists but the cumulative sold quantity
                      through T exceeds it (the till sold offline beyond the
                      synced cost basis). Segregated, not costed.

Callers: read/report functions call ensure_analytics_schema() themselves; write
functions (bill_control_subscription, refund_subscription_charge, record_event)
assume the schema already exists (the router dependency creates it before the
BEGIN IMMEDIATE transaction, and tests ensure it in their fixture).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

BUSINESS_TIMEZONE = "America/Mexico_City"
CURRENCY = "MXN"

CONTROL_PLAN = "control"
CONTROL_PRICE_CENTS = 14900  # MXN 149 per store per month, billed manually

ROLE_ANALYTICS = "analytics"
ROLE_FINANCE = "finance"
ROLE_SUPPORT = "support"
SUPER_ROLES = frozenset({"staff"})
ALL_ROLES = (ROLE_ANALYTICS, ROLE_FINANCE, ROLE_SUPPORT)

# The statuses that count a sale as collected. Mirrors the set used by
# server/payments.apply_payment and the cash/fiado sale flows; kept local so
# this module stays independent of the router wiring.
FINAL_PAID_STATUSES = frozenset({"paid_cash", "paid_pey", "credit"})

COST_KNOWN = "known"
COST_UNKNOWN = "unknown"
COST_OFFLINE_CONFLICT = "offline_conflict"
COST_STATUSES = (COST_KNOWN, COST_UNKNOWN, COST_OFFLINE_CONFLICT)

# SIMULADO 28-day snapshot (docs/produccion/d3-comercial.md), integer MXN cents.
SIMULADO_28D = {
    "recorded_cents": 10_000_000,  # MXN 100,000 recorded by stores (all channels)
    "codi_cents": 2_000_000,        # MXN 20,000 tagged CoDi (subset of recorded)
    "confirmed_cents": 1_800_000,   # MXN 18,000 confirmed by pey (subset of CoDi)
}

# ---------------------------------------------------------------------------
# Schema (owned by this module; created idempotently)
# ---------------------------------------------------------------------------

ANALYTICS_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS analytics_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    store_id TEXT NOT NULL,
    occurred_at REAL NOT NULL,
    received_at REAL NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    origin TEXT NOT NULL CHECK(origin IN ('server','ui')) DEFAULT 'server',
    environment TEXT NOT NULL CHECK(environment IN ('demo','production')) DEFAULT 'production',
    campaign TEXT,
    owner TEXT,
    subject TEXT,
    payload TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_store_type
    ON analytics_events(store_id, event_type, occurred_at);

CREATE TABLE IF NOT EXISTS sale_cost_snapshots (
    sale_item_id INTEGER PRIMARY KEY,
    sale_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    product_id INTEGER NOT NULL,
    qty_milli INTEGER NOT NULL,
    cost_status TEXT NOT NULL CHECK(cost_status IN ('known','unknown','offline_conflict')),
    unit_cost_cents INTEGER,
    line_cost_cents INTEGER,
    known_qty_milli INTEGER NOT NULL DEFAULT 0,
    known_cost_cents INTEGER NOT NULL DEFAULT 0,
    snapshotted_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sale_cost_snapshots_sale
    ON sale_cost_snapshots(sale_id);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    plan TEXT NOT NULL CHECK(plan IN ('control')),
    status TEXT NOT NULL CHECK(status IN ('active','suspended','canceled')),
    campaign TEXT,
    owner TEXT,
    period_start REAL,
    period_end REAL,
    created_at REAL NOT NULL,
    canceled_at REAL
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_store
    ON subscriptions(store_id, status);

CREATE TABLE IF NOT EXISTS subscription_charges (
    id INTEGER PRIMARY KEY,
    subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
    kind TEXT NOT NULL CHECK(kind IN ('charge','refund')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'MXN',
    campaign TEXT,
    owner TEXT,
    charged_at REAL NOT NULL,
    receipt_ref TEXT,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_subscription_charges_sub
    ON subscription_charges(subscription_id);
"""


class AnalyticsError(Exception):
    """A business rejection for one analytics operation (mapped to HTTP 4xx)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class CrossComparisonError(AnalyticsError):
    """Raised when a query mixes the three CoDi series (recorded / tagged /
    confirmed). The confirmation rate is only ever computed over the CoDi-tagged
    amount; the pending amount is only ever CoDi-tagged minus confirmed."""

    def __init__(self, detail: str) -> None:
        super().__init__("cross_comparison", detail)


def ensure_analytics_schema(conn: sqlite3.Connection) -> None:
    """Create the analytics tables if missing (idempotent, safe on every start)."""

    conn.executescript(ANALYTICS_TABLES_SQL)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _round_half_up(numer: int, denom: int) -> int:
    """round(numer / denom) half-up, ties away from zero, in integer arithmetic."""

    numer = int(numer)
    denom = int(denom)
    if denom == 0:
        return 0
    if numer >= 0:
        return (numer + denom // 2) // denom
    return -((-numer + denom // 2) // denom)


def _ratio(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return round(part / whole, 6)


def _percent(part: int, whole: int) -> float | None:
    if not whole:
        return None
    return round(part * 100.0 / whole, 4)


# ---------------------------------------------------------------------------
# Versioned domain events (durable facts)
# ---------------------------------------------------------------------------


def record_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    store_id: str,
    occurred_at: float | None = None,
    received_at: float | None = None,
    version: int = 1,
    origin: str = "server",
    environment: str = "production",
    campaign: str | None = None,
    owner: str | None = None,
    subject: str | None = None,
    payload: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> str:
    """Append one versioned domain event, deduplicated by its stable event id.

    The id is caller-provided where the fact has a natural key (e.g.
    control_paid:<subscription>:<charge>) so re-recording is idempotent; absent a
    key a fresh uuid is used. No PII -- phone, CLABE, email, debtor names, or
    free-form text -- belongs in the payload (docs/produccion/d3-comercial.md).
    """

    occurred = time.time() if occurred_at is None else occurred_at
    received = time.time() if received_at is None else received_at
    eid = event_id or uuid.uuid4().hex
    conn.execute(
        """INSERT OR IGNORE INTO analytics_events
               (event_id, event_type, store_id, occurred_at, received_at,
                version, origin, environment, campaign, owner, subject, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            eid,
            event_type,
            store_id,
            occurred,
            received,
            int(version),
            origin,
            environment,
            campaign,
            owner,
            subject,
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )
    return eid


# ---------------------------------------------------------------------------
# Weighted-average cost snapshot and gross merchandise margin
# ---------------------------------------------------------------------------


def _receipt_basis(
    conn: sqlite3.Connection, store_id: str, product_id: int, as_of: float
) -> tuple[int, int]:
    """(known_qty_milli, known_cost_cents) from receipts approved up to as_of.

    Only receipts with a known (non-NULL) unit cost contribute to the basis;
    NULL-cost receipts are ignored so the weighted average is never polluted by
    a synthetic zero.
    """

    row = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN rl.unit_cost_cents IS NOT NULL
                               THEN rl.qty_milli ELSE 0 END), 0) AS known_qty,
             COALESCE(SUM(CASE WHEN rl.unit_cost_cents IS NOT NULL
                               THEN rl.purchase_cost_cents ELSE 0 END), 0) AS known_cost
           FROM receipt_lines rl
           JOIN receipts r ON r.id = rl.receipt_id
           WHERE r.store_id = ? AND rl.product_id = ?
             AND r.status = 'approved' AND r.approved_at <= ?""",
        (store_id, product_id, as_of),
    ).fetchone()
    return int(row["known_qty"] or 0), int(row["known_cost"] or 0)


def _cumulative_sold(
    conn: sqlite3.Connection, store_id: str, product_id: int, as_of: float
) -> int:
    row = conn.execute(
        """SELECT COALESCE(SUM(si.qty_milli), 0) AS sold
           FROM sale_items si
           JOIN sales s ON s.id = si.sale_id
           WHERE s.store_id = ? AND si.product_id = ? AND s.created_at <= ?""",
        (store_id, product_id, as_of),
    ).fetchone()
    return int(row["sold"] or 0)


def classify_sale_line(
    conn: sqlite3.Connection,
    store_id: str,
    product_id: int,
    qty_milli: int,
    sale_ts: float,
) -> tuple[str, int | None, int | None, int, int]:
    """Classify one sale line and return (status, line_cost, unit_cost, basis_qty,
    basis_cost). Unknown and offline-conflict lines return a None cost: they are
    never given a synthetic zero and never counted as margin."""

    known_qty, known_cost = _receipt_basis(conn, store_id, product_id, sale_ts)
    if known_qty == 0:
        return COST_UNKNOWN, None, None, 0, 0

    sold = _cumulative_sold(conn, store_id, product_id, sale_ts)
    if sold > known_qty:
        # Sold beyond the synced, known-cost basis at this moment: the offline
        # oversell signature. The line cannot be honestly costed.
        return COST_OFFLINE_CONFLICT, None, None, known_qty, known_cost

    # Weighted-average cost: line cost = round(total_known_cost * Q / total_known_qty).
    line_cost = _round_half_up(known_cost * qty_milli, known_qty)
    unit_cost = _round_half_up(known_cost * 1000, known_qty)  # cents per whole unit
    return COST_KNOWN, line_cost, unit_cost, known_qty, known_cost


def snapshot_sale_costs(conn: sqlite3.Connection, store_id: str) -> None:
    """Snapshot the weighted-average cost for every not-yet-snapshotted sale line.

    Idempotent: snapshots are keyed by sale_item_id and never recomputed, so a
    later receipt cannot change a closed margin.
    """

    rows = conn.execute(
        """SELECT si.id AS item_id, si.sale_id, si.product_id, si.qty_milli,
                  s.created_at AS sale_ts
           FROM sale_items si
           JOIN sales s ON s.id = si.sale_id
           WHERE s.store_id = ?
             AND si.id NOT IN (SELECT sale_item_id FROM sale_cost_snapshots)
           ORDER BY s.created_at, si.id""",
        (store_id,),
    ).fetchall()

    now = time.time()
    for row in rows:
        status, line_cost, unit_cost, basis_qty, basis_cost = classify_sale_line(
            conn,
            store_id,
            int(row["product_id"]),
            int(row["qty_milli"]),
            row["sale_ts"],
        )
        conn.execute(
            """INSERT OR IGNORE INTO sale_cost_snapshots
                   (sale_item_id, sale_id, store_id, product_id, qty_milli,
                    cost_status, unit_cost_cents, line_cost_cents,
                    known_qty_milli, known_cost_cents, snapshotted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                int(row["item_id"]),
                row["sale_id"],
                store_id,
                int(row["product_id"]),
                int(row["qty_milli"]),
                status,
                unit_cost,
                line_cost,
                basis_qty,
                basis_cost,
                now,
            ),
        )


def gross_margin_report(
    conn: sqlite3.Connection,
    store_id: str,
    *,
    from_ts: float | None = None,
    to_ts: float | None = None,
) -> dict[str, Any]:
    """Gross merchandise margin over collected sales, with coverage.

    Net sales come from collected sale lines (sale_items of sales in
    FINAL_PAID_STATUSES). Attributable cost is the snapshotted cost of known
    lines. Unknown-cost and offline-conflict lines are segregated and never
    contribute to the margin; when no line is costable the margin is None
    rather than a synthetic 100%.
    """

    ensure_analytics_schema(conn)
    snapshot_sale_costs(conn, store_id)

    rows = conn.execute(
        """SELECT si.line_total_cents AS line_total,
                  sc.cost_status AS cost_status,
                  sc.line_cost_cents AS line_cost
           FROM sale_items si
           JOIN sales s ON s.id = si.sale_id
           LEFT JOIN sale_cost_snapshots sc ON sc.sale_item_id = si.id
           WHERE s.store_id = ?
             AND s.status IN ('paid_cash','paid_pey','credit')
             AND (? IS NULL OR s.created_at >= ?)
             AND (? IS NULL OR s.created_at <= ?)
           ORDER BY s.created_at, si.id""",
        (store_id, from_ts, from_ts, to_ts, to_ts),
    ).fetchall()

    buckets = {
        status: {"lines": 0, "salesCents": 0, "costCents": 0}
        for status in COST_STATUSES
    }
    total_lines = 0
    net_sales = 0
    for row in rows:
        status = row["cost_status"] or COST_UNKNOWN
        line_total = int(row["line_total"] or 0)
        buckets[status]["lines"] += 1
        buckets[status]["salesCents"] += line_total
        if status == COST_KNOWN:
            buckets[status]["costCents"] += int(row["line_cost"] or 0)
        total_lines += 1
        net_sales += line_total

    known = buckets[COST_KNOWN]
    attributable = known["costCents"]
    costed_net = known["salesCents"]
    margin = (costed_net - attributable) if known["lines"] > 0 else None

    def lines(status: str) -> int:
        return buckets[status]["lines"]

    def sales(status: str) -> int:
        return buckets[status]["salesCents"]

    return {
        "simulado": False,
        "tenant": store_id,
        "timezone": BUSINESS_TIMEZONE,
        "currency": CURRENCY,
        "amountBasis": "cents",
        "computedAt": time.time(),
        "window": {"from": from_ts, "to": to_ts},
        "netSalesCents": net_sales,
        "costedNetSalesCents": costed_net,
        "attributableCostCents": attributable,
        "grossMarginCents": margin,
        "coverage": {
            "lines": {
                "known": lines(COST_KNOWN),
                "unknown": lines(COST_UNKNOWN),
                "offlineConflict": lines(COST_OFFLINE_CONFLICT),
                "total": total_lines,
            },
            "salesCents": {
                "known": sales(COST_KNOWN),
                "unknown": sales(COST_UNKNOWN),
                "offlineConflict": sales(COST_OFFLINE_CONFLICT),
            },
            "byLines": _ratio(lines(COST_KNOWN), total_lines),
            "byAmount": _ratio(costed_net, net_sales),
        },
        "segregated": {
            "unknownCost": {"lines": lines(COST_UNKNOWN), "salesCents": sales(COST_UNKNOWN)},
            "offlineConflict": {
                "lines": lines(COST_OFFLINE_CONFLICT),
                "salesCents": sales(COST_OFFLINE_CONFLICT),
            },
        },
    }


# ---------------------------------------------------------------------------
# Control pilot subscription (manual billing, campaign + owner attribution)
# ---------------------------------------------------------------------------


def _charge_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "subscriptionId": row["subscription_id"],
        "kind": row["kind"],
        "amountCents": row["amount_cents"],
        "currency": row["currency"],
        "campaign": row["campaign"],
        "owner": row["owner"],
        "chargedAt": row["charged_at"],
        "receiptRef": row["receipt_ref"],
        "note": row["note"],
    }


def _subscription_payload(conn: sqlite3.Connection, subscription_id: str) -> dict[str, Any]:
    sub = conn.execute(
        "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
    ).fetchone()
    charges = conn.execute(
        "SELECT * FROM subscription_charges WHERE subscription_id = ? ORDER BY id",
        (subscription_id,),
    ).fetchall()
    return {
        "id": sub["id"],
        "storeId": sub["store_id"],
        "plan": sub["plan"],
        "status": sub["status"],
        "campaign": sub["campaign"],
        "owner": sub["owner"],
        "periodStart": sub["period_start"],
        "periodEnd": sub["period_end"],
        "createdAt": sub["created_at"],
        "canceledAt": sub["canceled_at"],
        "charges": [_charge_payload(c) for c in charges],
    }


def _require_subscription(
    conn: sqlite3.Connection, store_id: str, subscription_id: str
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE id = ? AND store_id = ?",
        (subscription_id, store_id),
    ).fetchone()
    if row is None:
        raise AnalyticsError("subscription_not_found", "Suscripción no encontrada")
    return row


def bill_control_subscription(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    campaign: str | None = None,
    owner: str | None = None,
    amount_cents: int = CONTROL_PRICE_CENTS,
    period_start: float | None = None,
    period_end: float | None = None,
    receipt_ref: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Bill a Control pilot manually (MXN 149) with campaign + owner attribution.

    Creates the subscription (active) and records its first manual charge plus a
    durable control_paid event. Billing is manual by design: there is no
    automatic charge and no automatic renewal (docs/produccion/d3-comercial.md).
    """

    now = time.time() if now is None else now
    sub_id = uuid.uuid4().hex
    conn.execute(
        """INSERT INTO subscriptions
               (id, store_id, plan, status, campaign, owner, period_start,
                period_end, created_at)
           VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
        (sub_id, store_id, CONTROL_PLAN, campaign, owner, period_start, period_end, now),
    )
    cursor = conn.execute(
        """INSERT INTO subscription_charges
               (subscription_id, kind, amount_cents, currency, campaign, owner,
                charged_at, receipt_ref)
           VALUES (?, 'charge', ?, ?, ?, ?, ?, ?)""",
        (sub_id, int(amount_cents), CURRENCY, campaign, owner, now, receipt_ref),
    )
    charge_id = int(cursor.lastrowid)
    record_event(
        conn,
        event_type="control_paid",
        store_id=store_id,
        occurred_at=now,
        campaign=campaign,
        owner=owner,
        subject=store_id,
        payload={
            "plan": CONTROL_PLAN,
            "amountCents": int(amount_cents),
            "subscriptionId": sub_id,
            "chargeId": charge_id,
        },
        event_id=f"control_paid:{sub_id}:{charge_id}",
    )
    sub = _subscription_payload(conn, sub_id)
    charge = next(c for c in sub["charges"] if c["id"] == charge_id)
    return {"subscription": sub, "charge": charge}


def refund_subscription_charge(
    conn: sqlite3.Connection,
    *,
    subscription_id: str,
    charge_id: int,
    amount_cents: int,
    store_id: str,
    reason: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Record a settled refund against a manual charge (a refund does not cancel)."""

    now = time.time() if now is None else now
    _require_subscription(conn, store_id, subscription_id)
    charge = conn.execute(
        "SELECT * FROM subscription_charges WHERE id = ? AND subscription_id = ? AND kind = 'charge'",
        (charge_id, subscription_id),
    ).fetchone()
    if charge is None:
        raise AnalyticsError("charge_not_found", "Cargo no encontrado")
    cursor = conn.execute(
        """INSERT INTO subscription_charges
               (subscription_id, kind, amount_cents, currency, campaign, owner,
                charged_at, receipt_ref, note)
           VALUES (?, 'refund', ?, ?, ?, ?, ?, ?, ?)""",
        (
            subscription_id,
            int(amount_cents),
            CURRENCY,
            charge["campaign"],
            charge["owner"],
            now,
            charge["receipt_ref"],
            reason,
        ),
    )
    refund_id = int(cursor.lastrowid)
    record_event(
        conn,
        event_type="refund",
        store_id=store_id,
        occurred_at=now,
        campaign=charge["campaign"],
        owner=charge["owner"],
        subject=store_id,
        payload={
            "plan": CONTROL_PLAN,
            "amountCents": int(amount_cents),
            "subscriptionId": subscription_id,
            "chargeId": charge_id,
            "refundId": refund_id,
        },
        event_id=f"refund:{subscription_id}:{charge_id}:{refund_id}",
    )
    row = conn.execute(
        "SELECT * FROM subscription_charges WHERE id = ?", (refund_id,)
    ).fetchone()
    return {"refund": _charge_payload(row)}


def control_revenue(conn: sqlite3.Connection, store_id: str) -> dict[str, Any]:
    """Charged and settled refunds in MXN cents for the Control pilot."""

    ensure_analytics_schema(conn)
    row = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN sc.kind = 'charge' THEN sc.amount_cents ELSE 0 END), 0) AS gross,
             COALESCE(SUM(CASE WHEN sc.kind = 'refund' THEN sc.amount_cents ELSE 0 END), 0) AS refunds,
             COUNT(CASE WHEN sc.kind = 'charge' THEN 1 END) AS charges,
             COUNT(CASE WHEN sc.kind = 'refund' THEN 1 END) AS refund_count
           FROM subscription_charges sc
           JOIN subscriptions sub ON sub.id = sc.subscription_id
           WHERE sub.store_id = ?""",
        (store_id,),
    ).fetchone()
    gross = int(row["gross"] or 0)
    refunds = int(row["refunds"] or 0)
    return {
        "grossCents": gross,
        "refundsCents": refunds,
        "netCents": gross - refunds,
        "chargeCount": int(row["charges"] or 0),
        "refundCount": int(row["refund_count"] or 0),
    }


def list_subscriptions(conn: sqlite3.Connection, store_id: str) -> list[dict[str, Any]]:
    ensure_analytics_schema(conn)
    rows = conn.execute(
        "SELECT id FROM subscriptions WHERE store_id = ? ORDER BY created_at, id",
        (store_id,),
    ).fetchall()
    return [_subscription_payload(conn, row["id"]) for row in rows]


# ---------------------------------------------------------------------------
# CoDi reconciliation (recorded / tagged / confirmed are separate series)
# ---------------------------------------------------------------------------


def _validate_codi_series(recorded_cents: int, codi_cents: int, confirmed_cents: int) -> None:
    if recorded_cents < 0 or codi_cents < 0 or confirmed_cents < 0:
        raise AnalyticsError("invalid_amount", "Los montos no pueden ser negativos")
    if confirmed_cents > codi_cents:
        raise CrossComparisonError(
            "El monto confirmado no puede exceder el monto CoDi etiquetado"
        )
    if codi_cents > recorded_cents:
        raise CrossComparisonError(
            "El monto CoDi etiquetado no puede exceder el monto registrado total"
        )


def reconcile_codi(
    *, recorded_cents: int, codi_cents: int, confirmed_cents: int
) -> dict[str, Any]:
    """Reconcile the three CoDi series WITHOUT cross-comparison.

    recorded, codi and confirmed are three distinct series with three distinct
    denominators. The pending amount is codi - confirmed (inside the CoDi
    subset) and the confirmation rate is confirmed / codi (by CoDi amount), never
    confirmed / recorded and never recorded - confirmed.
    """

    _validate_codi_series(recorded_cents, codi_cents, confirmed_cents)
    return {
        "recordedCents": recorded_cents,
        "codiCents": codi_cents,
        "confirmedCents": confirmed_cents,
        "pendingCodiCents": codi_cents - confirmed_cents,
        "confirmedPercentCodiAmount": _percent(confirmed_cents, codi_cents),
        "basis": "codiAmount",
    }


def codis_confirmation_rate(
    confirmed_cents: int, basis_cents: int, *, basis: str
) -> float | None:
    """Fraction of CoDi confirmed over a basis that MUST be the CoDi-tagged amount.

    Passing basis='recorded' (e.g. 18,000 / 100,000) is the forbidden
    cross-comparison and raises CrossComparisonError.
    """

    if basis != "codi":
        raise CrossComparisonError(
            "Comparación cruzada: la tasa de confirmación CoDi se calcula sobre "
            f"el monto CoDi etiquetado, no sobre '{basis}'."
        )
    if basis_cents <= 0:
        return None
    return confirmed_cents / basis_cents


def codis_pending_cents(codi_cents: int, confirmed_cents: int) -> int:
    """Pending CoDi = tagged CoDi minus confirmed (inside the CoDi subset only)."""

    return codi_cents - confirmed_cents


def simulado_reconciliation() -> dict[str, Any]:
    """The corrected 28-day SIMULADO reconciliation (2,000 pending, 90% by CoDi amount)."""

    result = reconcile_codi(**SIMULADO_28D)
    result["simulado"] = True
    return result


def sales_reconciliation(conn: sqlite3.Connection, store_id: str) -> dict[str, Any]:
    """Live reconciliation derived from durable sales (recorded = all channels,
    codi = payment_method 'pey', confirmed = status 'paid_pey')."""

    row = conn.execute(
        """SELECT
             COALESCE(SUM(s.total_cents), 0) AS recorded,
             COALESCE(SUM(CASE WHEN s.payment_method = 'pey' THEN s.total_cents ELSE 0 END), 0) AS codi,
             COALESCE(SUM(CASE WHEN s.payment_method = 'pey' AND s.status = 'paid_pey'
                               THEN s.total_cents ELSE 0 END), 0) AS confirmed
           FROM sales s
           WHERE s.store_id = ?""",
        (store_id,),
    ).fetchone()
    return reconcile_codi(
        recorded_cents=int(row["recorded"] or 0),
        codi_cents=int(row["codi"] or 0),
        confirmed_cents=int(row["confirmed"] or 0),
    )
