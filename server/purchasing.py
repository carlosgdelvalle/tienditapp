"""Purchasing and replenishment: suppliers, purchase orders, goods receipts.

Server-side domain for M3. Everything here is SIMULADO where a real supplier
or invoice would otherwise be involved: no real money, no real data, and no
network calls. The core follows the same shape as server/till.py — domain
functions raise PurchasingError (mapped to HTTP 4xx by the router) and every
write runs inside db.write_transaction (BEGIN IMMEDIATE).

Flow (offline goods receipt):

    create_receipt  -> receipt "awaiting_approval" + lines + a "discrepancy"
                       case when received != ordered;
    approve_receipt -> snapshot purchase cost in cents + quantity received,
                       increase stock with inventory_movements.reason='receipt',
                       and advance the order to partial/received.

Two receipts for the SAME shipment never double inventory:

* an exact retry (same clientReceiptId) returns the stored receipt with
  duplicate=True, idempotent=True (S-08: retries add neither money nor stock);
* a different receipt for the same shipment (same shipmentRef on the same
  order) opens a traceable receipt_cases row (kind 'duplicate_shipment') and
  returns the original receipt — no second row, no stock change.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

# Purchase order states.
PO_DRAFT = "draft"
PO_ISSUED = "issued"
PO_PARTIAL = "partial"
PO_RECEIVED = "received"
PO_CANCELED = "canceled"

RECEIPT_AWAITING = "awaiting_approval"
RECEIPT_APPROVED = "approved"

CASE_DUPLICATE_SHIPMENT = "duplicate_shipment"
CASE_DISCREPANCY = "discrepancy"


PURCHASING_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    contact TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    status TEXT NOT NULL CHECK(status IN ('draft','issued','partial','received','canceled')),
    employee_id INTEGER REFERENCES employees(id),
    note TEXT,
    created_at REAL NOT NULL,
    issued_at REAL
);

CREATE TABLE IF NOT EXISTS po_lines (
    id INTEGER PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty_milli INTEGER NOT NULL,
    unit_cost_cents INTEGER,
    received_milli INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
    client_receipt_id TEXT,
    shipment_ref TEXT,
    status TEXT NOT NULL CHECK(status IN ('awaiting_approval','approved')),
    employee_id INTEGER REFERENCES employees(id),
    note TEXT,
    created_at REAL NOT NULL,
    approved_at REAL,
    approved_by INTEGER REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS receipt_lines (
    id INTEGER PRIMARY KEY,
    receipt_id INTEGER NOT NULL REFERENCES receipts(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    ordered_milli INTEGER NOT NULL,
    qty_milli INTEGER NOT NULL,
    discrepancy_milli INTEGER NOT NULL DEFAULT 0,
    unit_cost_cents INTEGER,
    purchase_cost_cents INTEGER
);

CREATE TABLE IF NOT EXISTS receipt_cases (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    receipt_id INTEGER REFERENCES receipts(id),
    kind TEXT NOT NULL,
    detail TEXT,
    status TEXT NOT NULL CHECK(status IN ('open','resolved')) DEFAULT 'open',
    created_at REAL NOT NULL,
    resolved_at REAL
);

CREATE INDEX IF NOT EXISTS idx_suppliers_store ON suppliers(store_id);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_store ON purchase_orders(store_id, status);
CREATE INDEX IF NOT EXISTS idx_po_lines_po ON po_lines(purchase_order_id);
CREATE INDEX IF NOT EXISTS idx_receipts_store ON receipts(store_id, status);
CREATE INDEX IF NOT EXISTS idx_receipts_po ON receipts(purchase_order_id);
CREATE INDEX IF NOT EXISTS idx_receipt_lines_receipt ON receipt_lines(receipt_id);
CREATE INDEX IF NOT EXISTS idx_receipt_cases_receipt ON receipt_cases(receipt_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_client_id
    ON receipts(client_receipt_id) WHERE client_receipt_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_shipment_ref
    ON receipts(purchase_order_id, shipment_ref) WHERE shipment_ref IS NOT NULL;
"""


class PurchasingError(Exception):
    """A business rejection for one purchasing operation (mapped to HTTP 4xx)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def ensure_purchasing_schema(conn: sqlite3.Connection) -> None:
    """Create the purchasing tables if missing (idempotent, safe on every start)."""

    conn.executescript(PURCHASING_TABLES_SQL)


def _line_cost_cents(unit_cost_cents: int | None, qty_milli: int) -> int | None:
    """round(unit_cost_cents * qty_milli / 1000), half up, in integer cents.

    Unknown cost (NULL unit cost) stays NULL: the metrics contract forbids
    imputing a synthetic zero.
    """

    if unit_cost_cents is None:
        return None
    product = int(unit_cost_cents) * int(qty_milli)
    if product >= 0:
        return (product + 500) // 1000
    return -((-product + 500) // 1000)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


def create_supplier(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    name: str,
    contact: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    clean_name = (name or "").strip()
    if not clean_name:
        raise PurchasingError("invalid_name", "El nombre del proveedor es obligatorio")
    clean_contact = (contact or "").strip() or None
    cursor = conn.execute(
        """INSERT INTO suppliers (store_id, name, contact, active, created_at)
           VALUES (?, ?, ?, 1, ?)""",
        (store_id, clean_name, clean_contact, now),
    )
    return _supplier_payload(conn, store_id, int(cursor.lastrowid))


def update_supplier(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    supplier_id: int,
    name: str | None = None,
    contact: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    supplier = _require_supplier(conn, store_id, supplier_id)
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise PurchasingError("invalid_name", "El nombre del proveedor es obligatorio")
        conn.execute(
            "UPDATE suppliers SET name = ? WHERE id = ? AND store_id = ?",
            (clean_name, supplier_id, store_id),
        )
    if contact is not None:
        conn.execute(
            "UPDATE suppliers SET contact = ? WHERE id = ? AND store_id = ?",
            ((contact or "").strip() or None, supplier_id, store_id),
        )
    if active is not None:
        conn.execute(
            "UPDATE suppliers SET active = ? WHERE id = ? AND store_id = ?",
            (1 if active else 0, supplier_id, store_id),
        )
    return _supplier_payload(conn, store_id, supplier_id)


def delete_supplier(
    conn: sqlite3.Connection, *, store_id: str, supplier_id: int
) -> dict[str, Any]:
    """Soft delete: history (orders, receipts) survives, the supplier is inactive."""

    supplier = _require_supplier(conn, store_id, supplier_id)
    conn.execute(
        "UPDATE suppliers SET active = 0 WHERE id = ? AND store_id = ?",
        (supplier_id, store_id),
    )
    return {"ok": True, "id": supplier["id"], "active": False}


def list_suppliers(conn: sqlite3.Connection, store_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM suppliers WHERE store_id = ? ORDER BY id", (store_id,)
    ).fetchall()
    return [_supplier_payload_from_row(row) for row in rows]


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------


def create_purchase_order(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    supplier_id: int,
    lines: list[dict[str, Any]],
    employee_id: int | None = None,
    note: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    supplier = _require_supplier(conn, store_id, supplier_id)
    if not supplier["active"]:
        raise PurchasingError(
            "supplier_inactive", "El proveedor está inactivo"
        )
    if not lines:
        raise PurchasingError("invalid_lines", "La orden necesita al menos una línea")
    seen: set[int] = set()
    for line in lines:
        product_id = int(line["productId"])
        qty = int(line["qtyMilli"])
        unit_cost = line.get("unitCostCents")
        if qty <= 0:
            raise PurchasingError("invalid_qty", "La cantidad ordenada debe ser mayor que cero")
        if unit_cost is not None and int(unit_cost) < 0:
            raise PurchasingError("invalid_cost", "El costo unitario no puede ser negativo")
        if product_id in seen:
            raise PurchasingError("duplicate_line", "Línea duplicada en la orden")
        seen.add(product_id)
        product = conn.execute(
            "SELECT 1 FROM products WHERE id = ? AND store_id = ?",
            (product_id, store_id),
        ).fetchone()
        if product is None:
            raise PurchasingError("product_not_found", "Producto no encontrado")

    cursor = conn.execute(
        """INSERT INTO purchase_orders
               (store_id, supplier_id, status, employee_id, note, created_at)
           VALUES (?, ?, 'draft', ?, ?, ?)""",
        (store_id, supplier_id, employee_id, (note or "").strip() or None, now),
    )
    po_id = int(cursor.lastrowid)
    for line in lines:
        conn.execute(
            """INSERT INTO po_lines
                   (purchase_order_id, product_id, qty_milli, unit_cost_cents,
                    received_milli)
               VALUES (?, ?, ?, ?, 0)""",
            (
                po_id,
                int(line["productId"]),
                int(line["qtyMilli"]),
                line.get("unitCostCents"),
            ),
        )
    return _purchase_order_payload(conn, store_id, po_id)


def issue_purchase_order(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    po_id: int,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    po = _require_purchase_order(conn, store_id, po_id)
    if po["status"] == PO_ISSUED:
        return {"purchaseOrder": _purchase_order_payload(conn, store_id, po_id), "duplicate": True}
    if po["status"] != PO_DRAFT:
        raise PurchasingError(
            "purchase_order_not_draft", "Solo una orden en borrador se puede emitir"
        )
    conn.execute(
        "UPDATE purchase_orders SET status = ?, issued_at = ? WHERE id = ?",
        (PO_ISSUED, now, po_id),
    )
    return {"purchaseOrder": _purchase_order_payload(conn, store_id, po_id), "duplicate": False}


def cancel_purchase_order(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    po_id: int,
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    po = _require_purchase_order(conn, store_id, po_id)
    if po["status"] == PO_CANCELED:
        return {"purchaseOrder": _purchase_order_payload(conn, store_id, po_id), "duplicate": True}
    if po["status"] in (PO_RECEIVED, PO_PARTIAL):
        raise PurchasingError(
            "purchase_order_not_cancelable",
            "No se puede cancelar una orden con mercancía ya recibida",
        )
    conn.execute(
        "UPDATE purchase_orders SET status = ? WHERE id = ?", (PO_CANCELED, po_id)
    )
    return {"purchaseOrder": _purchase_order_payload(conn, store_id, po_id), "duplicate": False}


def get_purchase_order(
    conn: sqlite3.Connection, store_id: str, po_id: int
) -> dict[str, Any]:
    return _purchase_order_payload(conn, store_id, po_id)


def list_purchase_orders(conn: sqlite3.Connection, store_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id FROM purchase_orders WHERE store_id = ? ORDER BY id", (store_id,)
    ).fetchall()
    return [_purchase_order_payload(conn, store_id, int(row["id"])) for row in rows]


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


def create_receipt(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    purchase_order_id: int,
    lines: list[dict[str, Any]],
    employee_id: int | None = None,
    client_receipt_id: str | None = None,
    shipment_ref: str | None = None,
    note: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Record an offline goods receipt as awaiting_approval (no stock change).

    Returns {"receipt", "duplicate", "idempotent", "case"}. A duplicate never
    creates a second stock effect: it either replays the stored receipt (same
    clientReceiptId) or opens a traceable duplicate_shipment case (same
    shipmentRef), leaving the original receipt as the single source of stock.
    """

    now = time.time() if now is None else now
    po = _require_purchase_order(conn, store_id, purchase_order_id)
    if po["status"] not in (PO_ISSUED, PO_PARTIAL):
        raise PurchasingError(
            "purchase_order_not_receivable",
            "La orden no está emitida o ya fue recibida/cancelada",
        )
    if not lines:
        raise PurchasingError("invalid_lines", "La recepción necesita al menos una línea")

    client_id = (client_receipt_id or "").strip() or None
    shipment = (shipment_ref or "").strip() or None

    # 1. Exact retry (lost ACK): same client receipt id -> same receipt, no case.
    if client_id is not None:
        existing = conn.execute(
            "SELECT * FROM receipts WHERE client_receipt_id = ? AND store_id = ?",
            (client_id, store_id),
        ).fetchone()
        if existing is not None:
            return {
                "receipt": _receipt_payload(conn, store_id, int(existing["id"])),
                "duplicate": True,
                "idempotent": True,
                "case": None,
            }

    # 2. Two receipts for the same shipment: open a traceable case, keep one row.
    if shipment is not None:
        existing = conn.execute(
            """SELECT * FROM receipts
               WHERE purchase_order_id = ? AND shipment_ref = ? AND store_id = ?""",
            (purchase_order_id, shipment, store_id),
        ).fetchone()
        if existing is not None:
            case = _open_case(
                conn,
                store_id,
                int(existing["id"]),
                CASE_DUPLICATE_SHIPMENT,
                f"Mercancía recibida dos veces para el embarque {shipment!r} "
                f"(orden {purchase_order_id}). Se conserva una sola recepción; "
                "el inventario no se duplica.",
                now,
            )
            return {
                "receipt": _receipt_payload(conn, store_id, int(existing["id"])),
                "duplicate": True,
                "idempotent": False,
                "case": case,
            }

    # 3. New receipt: validate lines against the order, capture discrepancies.
    po_lines = {
        int(row["product_id"]): row
        for row in conn.execute(
            "SELECT * FROM po_lines WHERE purchase_order_id = ?",
            (purchase_order_id,),
        ).fetchall()
    }
    seen: set[int] = set()
    discrepancies: list[tuple[sqlite3.Row, int, int]] = []
    for line in lines:
        product_id = int(line["productId"])
        qty = int(line["qtyMilli"])
        if qty <= 0:
            raise PurchasingError("invalid_qty", "La cantidad recibida debe ser mayor que cero")
        if product_id in seen:
            raise PurchasingError("duplicate_line", "Línea duplicada en la recepción")
        seen.add(product_id)
        po_line = po_lines.get(product_id)
        if po_line is None:
            raise PurchasingError(
                "product_not_ordered", "El producto no está en la orden de compra"
            )
        discrepancy = qty - int(po_line["qty_milli"])
        if discrepancy != 0:
            discrepancies.append((po_line, qty, discrepancy))

    cursor = conn.execute(
        """INSERT INTO receipts
               (store_id, purchase_order_id, client_receipt_id, shipment_ref,
                status, employee_id, note, created_at)
           VALUES (?, ?, ?, ?, 'awaiting_approval', ?, ?, ?)""",
        (
            store_id,
            purchase_order_id,
            client_id,
            shipment,
            employee_id,
            (note or "").strip() or None,
            now,
        ),
    )
    receipt_id = int(cursor.lastrowid)
    for line in lines:
        po_line = po_lines[int(line["productId"])]
        qty = int(line["qtyMilli"])
        discrepancy = qty - int(po_line["qty_milli"])
        conn.execute(
            """INSERT INTO receipt_lines
                   (receipt_id, product_id, ordered_milli, qty_milli,
                    discrepancy_milli)
               VALUES (?, ?, ?, ?, ?)""",
            (receipt_id, int(line["productId"]), int(po_line["qty_milli"]), qty, discrepancy),
        )

    case = None
    if discrepancies:
        case = _open_case(
            conn,
            store_id,
            receipt_id,
            CASE_DISCREPANCY,
            _discrepancy_detail(conn, discrepancies),
            now,
        )
    return {
        "receipt": _receipt_payload(conn, store_id, receipt_id),
        "duplicate": False,
        "idempotent": False,
        "case": case,
    }


def approve_receipt(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    receipt_id: int,
    approved_by: int | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Owner approves the receipt: snapshot cost, increase stock, advance the order.

    Idempotent: re-approving an approved receipt returns the stored result and
    writes no movement twice (S-08). Cost is snapshotted in cents per line from
    the purchase order at approval time; a later cost change cannot alter a
    closed receipt. Unknown cost stays NULL (never a synthetic zero).
    """

    now = time.time() if now is None else now
    receipt = _require_receipt(conn, store_id, receipt_id)
    if receipt["status"] == RECEIPT_APPROVED:
        return {"receipt": _receipt_payload(conn, store_id, receipt_id), "duplicate": True}
    if receipt["status"] != RECEIPT_AWAITING:
        raise PurchasingError("receipt_not_approvable", "La recepción no puede aprobarse")

    lines = conn.execute(
        "SELECT * FROM receipt_lines WHERE receipt_id = ? ORDER BY id", (receipt_id,)
    ).fetchall()
    for line in lines:
        po_line = conn.execute(
            "SELECT * FROM po_lines WHERE purchase_order_id = ? AND product_id = ?",
            (receipt["purchase_order_id"], line["product_id"]),
        ).fetchone()
        unit_cost = po_line["unit_cost_cents"] if po_line is not None else None
        cost = _line_cost_cents(unit_cost, int(line["qty_milli"]))
        conn.execute(
            """UPDATE receipt_lines
               SET unit_cost_cents = ?, purchase_cost_cents = ?
               WHERE id = ?""",
            (unit_cost, cost, line["id"]),
        )

        product = conn.execute(
            "SELECT unlimited_stock FROM products WHERE id = ? AND store_id = ?",
            (line["product_id"], store_id),
        ).fetchone()
        if product is None:
            continue
        if not product["unlimited_stock"]:
            conn.execute(
                "UPDATE products SET stock_milli = stock_milli + ? "
                "WHERE id = ? AND unlimited_stock = 0",
                (line["qty_milli"], line["product_id"]),
            )
        conn.execute(
            """INSERT INTO inventory_movements
                   (product_id, delta_milli, reason, sale_id, employee_id, created_at)
               VALUES (?, ?, 'receipt', NULL, ?, ?)""",
            (line["product_id"], line["qty_milli"], approved_by, now),
        )
        conn.execute(
            "UPDATE po_lines SET received_milli = received_milli + ? "
            "WHERE purchase_order_id = ? AND product_id = ?",
            (line["qty_milli"], receipt["purchase_order_id"], line["product_id"]),
        )

    conn.execute(
        "UPDATE receipts SET status = ?, approved_at = ?, approved_by = ? WHERE id = ?",
        (RECEIPT_APPROVED, now, approved_by, receipt_id),
    )
    _advance_purchase_order_status(conn, store_id, int(receipt["purchase_order_id"]))
    return {"receipt": _receipt_payload(conn, store_id, receipt_id), "duplicate": False}


def get_receipt(conn: sqlite3.Connection, store_id: str, receipt_id: int) -> dict[str, Any]:
    return _receipt_payload(conn, store_id, receipt_id)


def list_receipts(conn: sqlite3.Connection, store_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id FROM receipts WHERE store_id = ? ORDER BY id", (store_id,)
    ).fetchall()
    return [_receipt_payload(conn, store_id, int(row["id"])) for row in rows]


def list_receipt_cases(conn: sqlite3.Connection, store_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM receipt_cases WHERE store_id = ? ORDER BY id", (store_id,)
    ).fetchall()
    return [_case_payload(row) for row in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _advance_purchase_order_status(
    conn: sqlite3.Connection, store_id: str, po_id: int
) -> None:
    po = conn.execute(
        "SELECT * FROM purchase_orders WHERE id = ? AND store_id = ?",
        (po_id, store_id),
    ).fetchone()
    if po is None or po["status"] == PO_CANCELED:
        return
    lines = conn.execute(
        "SELECT qty_milli, received_milli FROM po_lines WHERE purchase_order_id = ?",
        (po_id,),
    ).fetchall()
    if not lines:
        return
    complete = all(int(line["received_milli"]) >= int(line["qty_milli"]) for line in lines)
    conn.execute(
        "UPDATE purchase_orders SET status = ? WHERE id = ?",
        (PO_RECEIVED if complete else PO_PARTIAL, po_id),
    )


def _open_case(
    conn: sqlite3.Connection,
    store_id: str,
    receipt_id: int,
    kind: str,
    detail: str,
    now: float,
) -> dict[str, Any]:
    cursor = conn.execute(
        """INSERT INTO receipt_cases (store_id, receipt_id, kind, detail, status, created_at)
           VALUES (?, ?, ?, ?, 'open', ?)""",
        (store_id, receipt_id, kind, detail, now),
    )
    row = conn.execute(
        "SELECT * FROM receipt_cases WHERE id = ?", (int(cursor.lastrowid),)
    ).fetchone()
    return _case_payload(row)


def _discrepancy_detail(
    conn: sqlite3.Connection, discrepancies: list[tuple[sqlite3.Row, int, int]]
) -> str:
    parts: list[str] = []
    for po_line, qty, discrepancy in discrepancies:
        product = conn.execute(
            "SELECT name FROM products WHERE id = ?", (po_line["product_id"],)
        ).fetchone()
        name = product["name"] if product is not None else f"producto {po_line['product_id']}"
        parts.append(
            f"{name}: recibidas {qty}, ordenadas {po_line['qty_milli']} "
            f"({'+' if discrepancy > 0 else ''}{discrepancy})"
        )
    return "Diferencias contra la orden: " + "; ".join(parts) + "."


def _require_supplier(
    conn: sqlite3.Connection, store_id: str, supplier_id: int
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM suppliers WHERE id = ? AND store_id = ?",
        (supplier_id, store_id),
    ).fetchone()
    if row is None:
        raise PurchasingError("supplier_not_found", "Proveedor no encontrado")
    return row


def _require_purchase_order(
    conn: sqlite3.Connection, store_id: str, po_id: int
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM purchase_orders WHERE id = ? AND store_id = ?",
        (po_id, store_id),
    ).fetchone()
    if row is None:
        raise PurchasingError("purchase_order_not_found", "Orden de compra no encontrada")
    return row


def _require_receipt(
    conn: sqlite3.Connection, store_id: str, receipt_id: int
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM receipts WHERE id = ? AND store_id = ?",
        (receipt_id, store_id),
    ).fetchone()
    if row is None:
        raise PurchasingError("receipt_not_found", "Recepción no encontrada")
    return row


def _supplier_payload_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "storeId": row["store_id"],
        "name": row["name"],
        "contact": row["contact"],
        "active": bool(row["active"]),
        "createdAt": row["created_at"],
    }


def _supplier_payload(conn: sqlite3.Connection, store_id: str, supplier_id: int) -> dict[str, Any]:
    return _supplier_payload_from_row(_require_supplier(conn, store_id, supplier_id))


def _purchase_order_payload(conn: sqlite3.Connection, store_id: str, po_id: int) -> dict[str, Any]:
    po = conn.execute(
        """SELECT po.*, s.name AS supplier_name
           FROM purchase_orders po
           JOIN suppliers s ON s.id = po.supplier_id
           WHERE po.id = ? AND po.store_id = ?""",
        (po_id, store_id),
    ).fetchone()
    if po is None:
        raise PurchasingError("purchase_order_not_found", "Orden de compra no encontrada")
    lines = conn.execute(
        """SELECT l.*, p.name AS product_name, p.unit AS unit
           FROM po_lines l JOIN products p ON p.id = l.product_id
           WHERE l.purchase_order_id = ? ORDER BY l.id""",
        (po_id,),
    ).fetchall()
    return {
        "id": po["id"],
        "storeId": po["store_id"],
        "supplierId": po["supplier_id"],
        "supplierName": po["supplier_name"],
        "status": po["status"],
        "employeeId": po["employee_id"],
        "note": po["note"],
        "createdAt": po["created_at"],
        "issuedAt": po["issued_at"],
        "lines": [
            {
                "id": line["id"],
                "productId": line["product_id"],
                "productName": line["product_name"],
                "unit": line["unit"],
                "qtyMilli": line["qty_milli"],
                "unitCostCents": line["unit_cost_cents"],
                "receivedMilli": line["received_milli"],
            }
            for line in lines
        ],
    }


def _receipt_payload(conn: sqlite3.Connection, store_id: str, receipt_id: int) -> dict[str, Any]:
    receipt = _require_receipt(conn, store_id, receipt_id)
    lines = conn.execute(
        """SELECT l.*, p.name AS product_name, p.unit AS unit
           FROM receipt_lines l JOIN products p ON p.id = l.product_id
           WHERE l.receipt_id = ? ORDER BY l.id""",
        (receipt_id,),
    ).fetchall()
    cases = conn.execute(
        "SELECT * FROM receipt_cases WHERE receipt_id = ? ORDER BY id", (receipt_id,)
    ).fetchall()
    return {
        "id": receipt["id"],
        "storeId": receipt["store_id"],
        "purchaseOrderId": receipt["purchase_order_id"],
        "clientReceiptId": receipt["client_receipt_id"],
        "shipmentRef": receipt["shipment_ref"],
        "status": receipt["status"],
        "employeeId": receipt["employee_id"],
        "note": receipt["note"],
        "createdAt": receipt["created_at"],
        "approvedAt": receipt["approved_at"],
        "approvedBy": receipt["approved_by"],
        "lines": [
            {
                "id": line["id"],
                "productId": line["product_id"],
                "productName": line["product_name"],
                "unit": line["unit"],
                "orderedMilli": line["ordered_milli"],
                "qtyMilli": line["qty_milli"],
                "discrepancyMilli": line["discrepancy_milli"],
                "unitCostCents": line["unit_cost_cents"],
                "purchaseCostCents": line["purchase_cost_cents"],
            }
            for line in lines
        ],
        "cases": [_case_payload(case) for case in cases],
    }


def _case_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "storeId": row["store_id"],
        "receiptId": row["receipt_id"],
        "kind": row["kind"],
        "detail": row["detail"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "resolvedAt": row["resolved_at"],
    }
