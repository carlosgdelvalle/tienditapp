"""Server-side offline journal outbox contract.

One durable operation on the device = one outbox row there = one
`outbox_applied` row here. Events are applied exactly once under a stable
idempotency key (`tenant_id`, `device_id`, `event_id`); every application
returns a receipt that gates client deletion, and the journal is tenant-scoped
so a device bound to one tenant can never replay into another.

This module owns only the server contract: schema, deduplication, content
fingerprint and the effect of each event type. The HTTP surface lives in
`server/sync_routes.py`. It talks SQLite (the database every server test and
the demo run against); the PostgreSQL counterpart of these tables belongs to
the schema migration owned by the coordinator — this file must not be edited by
that migration, and `ensure_outbox_schema` is idempotent by design.

Money and stock are never synthesized from the device: the server recomputes
line totals from its own catalog prices and applies each inventory movement
exactly once per applied sale.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from typing import Any

from .db import write_transaction
from .parser import line_total_cents
from .payments import decrement_inventory

# Event types the server knows how to apply. Adding a type requires a
# dispatcher branch plus a receipt shape; unknown types are rejected without
# mutation and stay pending on the device for review.
EVENT_SALE_CREATED = "sale.created"
EVENT_INVENTORY_ADJUST = "inventory.adjust"

SUPPORTED_EVENT_TYPES = {EVENT_SALE_CREATED, EVENT_INVENTORY_ADJUST}

# catalogVersion values that predate durable server snapshots. 0 means the
# device had no snapshot loaded; 1 is the historical demo/test placeholder.
# Those journals are priced from the live catalog under the documented legacy
# policy. Any other version must resolve to a persisted snapshot, otherwise the
# event is routed to review instead of being silently repriced.
LEGACY_CATALOG_VERSIONS = {0, 1}

OUTBOX_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS outbox_devices (
    device_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_applied (
    tenant_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    receipt TEXT,
    applied_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, device_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_outbox_applied_sequence
    ON outbox_applied(tenant_id, device_id, sequence);

CREATE TABLE IF NOT EXISTS catalog_snapshots (
    store_id TEXT NOT NULL,
    catalog_version INTEGER NOT NULL,
    as_of INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    PRIMARY KEY (store_id, catalog_version)
);

CREATE TABLE IF NOT EXISTS catalog_snapshot_items (
    store_id TEXT NOT NULL,
    catalog_version INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    price_cents INTEGER NOT NULL,
    unit TEXT NOT NULL,
    unlimited_stock INTEGER NOT NULL,
    PRIMARY KEY (store_id, catalog_version, product_id)
);
"""


class SyncError(Exception):
    """A business rejection for one event: no mutation and no applied row.

    The device keeps the event (it is never marked applied), so a later retry
    re-evaluates it. The code is surfaced as a per-event ack error.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def ensure_outbox_schema(conn: sqlite3.Connection) -> None:
    """Create the outbox tables if missing (idempotent, safe on every start)."""

    conn.executescript(OUTBOX_TABLES_SQL)


def canonical_fingerprint(
    event_type: str, payload: Any, catalog_version: Any = None
) -> str:
    """Stable content hash of one event.

    A duplicate event id with the same fingerprint returns the original
    receipt; the same id with a *different* fingerprint is a conflict and is
    routed to review without mutation.
    """

    canonical = json.dumps(
        {"type": event_type, "catalogVersion": catalog_version, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def last_applied_sequence(
    conn: sqlite3.Connection, tenant_id: str, device_id: str
) -> int:
    """Highest sequence applied for a device, used to detect resumption gaps."""

    row = conn.execute(
        "SELECT MAX(sequence) AS seq FROM outbox_applied "
        "WHERE tenant_id = ? AND device_id = ?",
        (tenant_id, device_id),
    ).fetchone()
    return int(row["seq"] or 0)


def apply_event(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    device_id: str,
    event_id: str,
    sequence: int,
    event_type: str,
    occurred_at: int,
    payload: dict[str, Any],
    store_id: str,
    catalog_version: Any = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Apply one device event exactly once, inside its own BEGIN IMMEDIATE.

    Safe to call repeatedly for the same (tenant, device, event): the stored
    receipt is returned and no money, stock or movement is synthesized. The
    caller must already have verified the lease and tenant/device scoping.
    """

    now = time.time() if now is None else now
    if event_type not in SUPPORTED_EVENT_TYPES:
        return {
            "applied": False,
            "duplicate": False,
            "conflict": False,
            "error": "unsupported_event_type",
            "receipt": None,
        }

    with write_transaction(conn):
        existing = conn.execute(
            "SELECT * FROM outbox_applied "
            "WHERE tenant_id = ? AND device_id = ? AND event_id = ?",
            (tenant_id, device_id, event_id),
        ).fetchone()
        if existing is not None:
            fingerprint = canonical_fingerprint(event_type, payload, catalog_version)
            if existing["fingerprint"] != fingerprint:
                # Same id, different content: review, never mutate.
                return {
                    "applied": False,
                    "duplicate": False,
                    "conflict": True,
                    "error": "idempotency_conflict",
                    "receipt": _decode_receipt(existing["receipt"]),
                }
            return {
                "applied": False,
                "duplicate": True,
                "conflict": False,
                "error": None,
                "receipt": _decode_receipt(existing["receipt"]),
            }

        fingerprint = canonical_fingerprint(event_type, payload, catalog_version)
        if event_type == EVENT_SALE_CREATED:
            # Cross-entrypoint idempotency: POST /api/sales with an
            # Idempotency-Key equal to this eventId derives the same sale id.
            # If that online commit already landed, return its sale unchanged.
            sale_id = sale_id_from_event(event_id)
            prior = conn.execute(
                "SELECT * FROM sales WHERE id = ?", (sale_id,)
            ).fetchone()
            if prior is not None:
                employee_id = _int_field(payload, "employeeId")
                payment_method = str(payload.get("paymentMethod") or "cash").strip()
                merged_items = _merge_items(_coerce_items(payload.get("items")))
                if prior["store_id"] != store_id or not cash_intent_matches(
                    conn,
                    prior,
                    employee_id=employee_id,
                    payment_method=payment_method,
                    merged_items=merged_items,
                    cash_received_cents=payload.get("cashReceivedCents"),
                ):
                    return {
                        "applied": False,
                        "duplicate": False,
                        "conflict": True,
                        "error": "idempotency_conflict",
                        "receipt": None,
                    }
                receipt = _receipt_from_sale(prior)
                conn.execute(
                    """INSERT INTO outbox_applied
                       (tenant_id, device_id, event_id, sequence, event_type,
                        fingerprint, receipt, applied_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        tenant_id,
                        device_id,
                        event_id,
                        sequence,
                        event_type,
                        fingerprint,
                        json.dumps(receipt, ensure_ascii=False, separators=(",", ":")),
                        now,
                    ),
                )
                return {
                    "applied": False,
                    "duplicate": True,
                    "conflict": False,
                    "error": None,
                    "receipt": receipt,
                }
            receipt = _apply_sale_created(
                conn,
                store_id=store_id,
                event_id=event_id,
                payload=payload,
                occurred_at=occurred_at,
                now=now,
                catalog_version=catalog_version,
            )
        elif event_type == EVENT_INVENTORY_ADJUST:
            receipt = _apply_inventory_adjust(
                conn, store_id=store_id, payload=payload, now=now
            )
        else:  # pragma: no cover - guarded by the supported-type check above
            raise SyncError("unsupported_event_type", "Tipo de evento desconocido")

        conn.execute(
            """INSERT INTO outbox_applied
               (tenant_id, device_id, event_id, sequence, event_type,
                fingerprint, receipt, applied_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tenant_id,
                device_id,
                event_id,
                sequence,
                event_type,
                fingerprint,
                json.dumps(receipt, ensure_ascii=False, separators=(",", ":")),
                now,
            ),
        )

    return {
        "applied": True,
        "duplicate": False,
        "conflict": False,
        "error": None,
        "receipt": receipt,
    }


# ---------------------------------------------------------------------------
# Event effects (server recomputes money and stock; never the device)
# ---------------------------------------------------------------------------


def _apply_sale_created(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    event_id: str,
    payload: dict[str, Any],
    occurred_at: int,
    now: float,
    catalog_version: Any = None,
) -> dict[str, Any]:
    """Finalize an offline cash sale as `paid_cash` with DB catalog prices.

    Offline only authorizes cash; fiado and PEY require the online flow, so any
    other payment method is rejected here. The physical sale keeps the device
    `occurredAt` as its business time and is never rewritten on sync.
    """

    payment_method = str(payload.get("paymentMethod") or "cash").strip()
    if payment_method != "cash":
        raise SyncError(
            "payment_method",
            "Solo una venta en efectivo se puede finalizar sin conexión",
        )

    merged = _merge_items(_coerce_items(payload.get("items")))
    employee = _require_employee(conn, store_id, _int_field(payload, "employeeId"))

    price_map = _price_map_for(conn, store_id, catalog_version)
    total_cents = 0
    lines: list[tuple[sqlite3.Row, int, int, int]] = []
    for product_id, qty_milli in merged.items():
        product = _require_product(conn, store_id, product_id)
        if price_map is not None:
            if product["id"] not in price_map:
                raise SyncError(
                    "catalog_version_unavailable",
                    "El producto no está en la versión del catálogo emitida",
                )
            unit_price = price_map[product["id"]]
        else:
            unit_price = int(product["price_cents"])
        line_total = line_total_cents(unit_price, qty_milli)
        total_cents += line_total
        lines.append((product, qty_milli, line_total, unit_price))

    cash_received = total_cents
    if payload.get("cashReceivedCents") is not None:
        cash_received = _int_field(payload, "cashReceivedCents")
    if cash_received < total_cents:
        raise SyncError(
            "cash_received", "El efectivo recibido no cubre el total"
        )
    change_cents = cash_received - total_cents

    sale_id = sale_id_from_event(event_id)
    note = payload.get("note")
    conn.execute(
        """INSERT INTO sales
           (id, store_id, employee_id, created_at, status, payment_method,
            total_cents, charged_cents, cash_received_cents, change_cents,
            customer_id, pey_qr_id, pey_tx_id, paid_at, expires_at, note)
           VALUES (?, ?, ?, ?, 'paid_cash', 'cash', ?, ?, ?, ?,
                   NULL, NULL, NULL, ?, NULL, ?)""",
        (
            sale_id,
            store_id,
            employee["id"],
            occurred_at,
            total_cents,
            total_cents,
            cash_received,
            change_cents,
            occurred_at,
            note,
        ),
    )
    for product, qty_milli, line_total, unit_price in lines:
        conn.execute(
            """INSERT INTO sale_items
               (sale_id, product_id, name, unit, qty_milli,
                unit_price_cents, line_total_cents)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                sale_id,
                product["id"],
                product["name"],
                product["unit"],
                qty_milli,
                unit_price,
                line_total,
            ),
        )
    decrement_inventory(conn, sale_id, employee["id"], now=float(occurred_at), allow_oversell=True)
    conn.execute(
        """INSERT INTO payments
           (tx_id, sale_id, amount_cents, method, source, applied, received_at)
           VALUES (?, ?, ?, 'cash', 'offline_outbox', 1, ?)""",
        (f"cash_{sale_id}", sale_id, total_cents, float(occurred_at)),
    )

    reference = str(payload.get("reference") or "").strip()
    return {
        "eventType": EVENT_SALE_CREATED,
        "saleId": sale_id,
        "reference": reference or sale_id,
        "status": "paid_cash",
        "paymentMethod": "cash",
        "totalCents": total_cents,
        "chargedCents": total_cents,
        "cashReceivedCents": cash_received,
        "changeCents": change_cents,
        "occurredAt": occurred_at,
        "appliedAt": now,
    }


def _apply_inventory_adjust(
    conn: sqlite3.Connection, *, store_id: str, payload: dict[str, Any], now: float
) -> dict[str, Any]:
    """Apply one inventory adjustment (count, variance, receipt) with a movement.

    The delta is applied exactly once; a retry of the same event returns the
    original receipt and does not move the stock again.
    """

    product_id = _int_field(payload, "productId")
    delta_milli = _int_field(payload, "deltaMilli")
    reason = str(payload.get("reason") or "ajuste").strip() or "ajuste"
    employee = _require_employee(conn, store_id, _int_field(payload, "employeeId"))
    product = _require_product(conn, store_id, product_id)
    if product["unlimited_stock"]:
        raise SyncError("unlimited_stock", "Este producto tiene inventario sin límite")

    conn.execute(
        "UPDATE products SET stock_milli = stock_milli + ? WHERE id = ?",
        (delta_milli, product_id),
    )
    conn.execute(
        """INSERT INTO inventory_movements
           (product_id, delta_milli, reason, sale_id, employee_id, created_at)
           VALUES (?, ?, ?, NULL, ?, ?)""",
        (product_id, delta_milli, reason, employee["id"], now),
    )
    new_stock = conn.execute(
        "SELECT stock_milli FROM products WHERE id = ?", (product_id,)
    ).fetchone()["stock_milli"]

    return {
        "eventType": EVENT_INVENTORY_ADJUST,
        "productId": product_id,
        "deltaMilli": delta_milli,
        "reason": reason,
        "stockMilli": new_stock,
        "appliedAt": now,
    }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _decode_receipt(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def sale_id_from_event(event_id: str) -> str:
    """Stable central folio derived from the idempotency key.

    Deriving it deterministically means the folio is never reused and stays
    identical across retries and across entrypoints (offline sync and
    POST /api/sales with an Idempotency-Key), even if the receipt were lost.
    """

    slug = "".join(ch for ch in str(event_id) if ch.isalnum()).lower()
    return "sale_" + (slug or uuid.uuid4().hex[:20])


def _price_map_for(
    conn: sqlite3.Connection, store_id: str, catalog_version: Any
) -> dict[int, int] | None:
    """Canonical unit prices for the event's catalog version.

    Returns None for legacy journals (no durable snapshot): those are priced
    from the live catalog under the documented legacy policy. A non-legacy
    version must resolve to a persisted snapshot; otherwise the event is routed
    to review (SyncError) instead of being silently repriced.
    """

    version = _catalog_version_int(catalog_version)
    if version is None or version in LEGACY_CATALOG_VERSIONS:
        return None
    header = conn.execute(
        "SELECT 1 FROM catalog_snapshots WHERE store_id = ? AND catalog_version = ?",
        (store_id, version),
    ).fetchone()
    if header is None:
        raise SyncError(
            "catalog_version_unavailable",
            "No se puede verificar el precio emitido: vuelve a autorizar en línea",
        )
    rows = conn.execute(
        "SELECT product_id, price_cents FROM catalog_snapshot_items "
        "WHERE store_id = ? AND catalog_version = ?",
        (store_id, version),
    ).fetchall()
    return {int(row["product_id"]): int(row["price_cents"]) for row in rows}


def _catalog_version_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise SyncError("catalog_version_invalid", "Versión del catálogo inválida")


def cash_intent_matches(
    conn: sqlite3.Connection,
    sale: sqlite3.Row,
    *,
    employee_id: int,
    payment_method: str,
    merged_items: dict[int, int],
    cash_received_cents: Any,
) -> bool:
    """True when an incoming cash intent equals the stored sale.

    The same idempotency key must map to the same logical operation. A
    different employee, payment method, item set or cash received is a content
    conflict, not a duplicate, so it is routed to review without mutation.
    """

    if int(sale["employee_id"]) != int(employee_id):
        return False
    if sale["payment_method"] != payment_method:
        return False
    stored = conn.execute(
        "SELECT product_id, qty_milli FROM sale_items "
        "WHERE sale_id = ? ORDER BY product_id, qty_milli",
        (sale["id"],),
    ).fetchall()
    if [(int(row["product_id"]), int(row["qty_milli"])) for row in stored] != sorted(
        merged_items.items()
    ):
        return False
    if cash_received_cents is None:
        # Exact change: the sale stored the total as the cash received.
        return int(sale["cash_received_cents"]) == int(sale["total_cents"])
    try:
        return int(sale["cash_received_cents"]) == int(cash_received_cents)
    except (TypeError, ValueError):
        return False


def _receipt_from_sale(sale: sqlite3.Row) -> dict[str, Any]:
    """Rebuild the sale.created receipt for a sale committed by another path."""

    return {
        "eventType": EVENT_SALE_CREATED,
        "saleId": sale["id"],
        "reference": sale["id"],
        "status": sale["status"],
        "paymentMethod": sale["payment_method"],
        "totalCents": int(sale["total_cents"]),
        "chargedCents": int(sale["charged_cents"]),
        "cashReceivedCents": sale["cash_received_cents"],
        "changeCents": sale["change_cents"],
        "occurredAt": sale["created_at"],
        "appliedAt": sale["created_at"],
    }


def _int_field(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise SyncError("invalid_field", f"Campo inválido: {key}")


def _coerce_items(raw: Any) -> list[tuple[int, int]]:
    if not isinstance(raw, list):
        raise SyncError("items", "La venta no tiene productos")
    items: list[tuple[int, int]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise SyncError("items", "Línea de venta inválida")
        try:
            items.append((int(entry.get("productId")), int(entry.get("qtyMilli"))))
        except (TypeError, ValueError):
            raise SyncError("items", "Línea de venta inválida")
    return items


def _merge_items(items: list[tuple[int, int]]) -> dict[int, int]:
    merged: dict[int, int] = {}
    for product_id, qty_milli in items:
        if qty_milli <= 0:
            raise SyncError("items", "qtyMilli debe ser mayor que cero")
        merged[product_id] = merged.get(product_id, 0) + qty_milli
    return merged


def _require_employee(
    conn: sqlite3.Connection, store_id: str, employee_id: int
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM employees WHERE id = ? AND store_id = ? AND active = 1",
        (employee_id, store_id),
    ).fetchone()
    if row is None:
        raise SyncError("employee_not_found", "Empleado no encontrado o inactivo")
    return row


def _require_product(
    conn: sqlite3.Connection, store_id: str, product_id: int
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM products WHERE id = ? AND store_id = ?",
        (product_id, store_id),
    ).fetchone()
    if row is None:
        raise SyncError("product_not_found", "Producto no encontrado")
    return row
