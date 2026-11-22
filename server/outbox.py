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
            receipt = _apply_sale_created(
                conn,
                store_id=store_id,
                event_id=event_id,
                payload=payload,
                occurred_at=occurred_at,
                now=now,
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

    total_cents = 0
    lines: list[tuple[sqlite3.Row, int, int]] = []
    for product_id, qty_milli in merged.items():
        product = _require_product(conn, store_id, product_id)
        line_total = line_total_cents(int(product["price_cents"]), qty_milli)
        total_cents += line_total
        lines.append((product, qty_milli, line_total))

    cash_received = total_cents
    if payload.get("cashReceivedCents") is not None:
        cash_received = _int_field(payload, "cashReceivedCents")
    if cash_received < total_cents:
        raise SyncError(
            "cash_received", "El efectivo recibido no cubre el total"
        )
    change_cents = cash_received - total_cents

    sale_id = _sale_id_from_event(event_id)
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
    for product, qty_milli, line_total in lines:
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
                product["price_cents"],
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


def _sale_id_from_event(event_id: str) -> str:
    """Stable central folio derived from the idempotency key.

    Deriving it deterministically means the folio is never reused and stays
    identical across retries even if the receipt itself were ever lost.
    """

    slug = "".join(ch for ch in str(event_id) if ch.isalnum()).lower()
    return "sale_" + (slug or uuid.uuid4().hex[:20])


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
