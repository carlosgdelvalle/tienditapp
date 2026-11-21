"""Till (cash register) shift lifecycle: open, close/handover, acceptance.

The till closeout is a cash reconciliation, independent of the 12-hour offline
lease: a shift opens with a float, closes with a blind count plus a handover,
and the owner accepts it or records a discrepancy. Every transition keeps who
and when. The variance is audited: it is stored durably and never corrected
silently.

Two kinds of "variance" live here:

* cash variance (till_shifts.variance_cents = counted - expected), recorded in
  till_shifts and a till_movements count row;
* inventory audit variance (inventory_movements.reason = "audit_variance"), a
  physical count that differs from the system stock, recorded as a durable
  movement WITHOUT mutating stock (the correction is a separate, justified
  adjustment).

All writes run inside db.write_transaction (BEGIN IMMEDIATE). Retries are
idempotent: re-closing or re-accepting a shift returns the stored result and
writes nothing twice.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any


# Shift states. "counted" from the contract is folded into "delivered" because
# the close endpoint performs the blind count and the handover atomically.
SHIFT_OPEN = "open"
SHIFT_DELIVERED = "delivered"
SHIFT_ACCEPTED = "accepted"
SHIFT_OBSERVED = "observed"

FINAL_SHIFT_STATUSES = {SHIFT_DELIVERED, SHIFT_ACCEPTED, SHIFT_OBSERVED}


TILL_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS till_shifts (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    opened_by INTEGER NOT NULL REFERENCES employees(id),
    opened_at REAL NOT NULL,
    closed_by INTEGER REFERENCES employees(id),
    closed_at REAL,
    opening_float_cents INTEGER NOT NULL,
    expected_cents INTEGER,
    counted_cents INTEGER,
    variance_cents INTEGER,
    status TEXT NOT NULL,
    accept_reason TEXT,
    accepted_by INTEGER REFERENCES employees(id),
    accepted_at REAL
);

CREATE TABLE IF NOT EXISTS till_movements (
    id INTEGER PRIMARY KEY,
    shift_id INTEGER NOT NULL REFERENCES till_shifts(id),
    kind TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    sale_id TEXT REFERENCES sales(id),
    note TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_till_shifts_store_status
    ON till_shifts(store_id, status);
CREATE INDEX IF NOT EXISTS idx_till_movements_shift
    ON till_movements(shift_id, created_at);
"""


class TillError(Exception):
    """A business rejection for one till operation (mapped to HTTP 4xx)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def ensure_till_schema(conn: sqlite3.Connection) -> None:
    """Create the till tables if missing (idempotent, safe on every start)."""

    conn.executescript(TILL_TABLES_SQL)


def open_shift(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    opened_by: int,
    opening_float_cents: int,
    now: float | None = None,
) -> dict[str, Any]:
    """Open a shift with its opening float.

    A new shift is not opened while another is still open.
    """

    now = time.time() if now is None else now
    if opening_float_cents < 0:
        raise TillError("invalid_float", "La base inicial no puede ser negativa")
    open_row = conn.execute(
        "SELECT id FROM till_shifts WHERE store_id = ? AND status = ? LIMIT 1",
        (store_id, SHIFT_OPEN),
    ).fetchone()
    if open_row is not None:
        raise TillError(
            "shift_open", "Ya hay una caja abierta: ciérrala antes de abrir otra"
        )
    cursor = conn.execute(
        """INSERT INTO till_shifts
               (store_id, opened_by, opened_at, opening_float_cents, status)
           VALUES (?, ?, ?, ?, ?)""",
        (store_id, opened_by, now, opening_float_cents, SHIFT_OPEN),
    )
    shift_id = int(cursor.lastrowid)
    conn.execute(
        """INSERT INTO till_movements
               (shift_id, kind, amount_cents, sale_id, note, created_at)
           VALUES (?, 'opening', ?, NULL, NULL, ?)""",
        (shift_id, opening_float_cents, now),
    )
    return _shift_payload(conn, store_id, shift_id)


def close_shift(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    shift_id: int,
    counted_cents: int,
    closed_by: int,
    now: float | None = None,
) -> dict[str, Any]:
    """Record the blind count + handover and compute the audited variance.

    expected = opening float + cash sales + inflows - outflows. The variance is
    counted - expected. Retrying an already-closed shift is idempotent: the
    stored result is returned and nothing is written twice.
    """

    now = time.time() if now is None else now
    if counted_cents < 0:
        raise TillError("invalid_count", "El conteo no puede ser negativo")
    shift = _require_shift(conn, store_id, shift_id)
    if shift["status"] != SHIFT_OPEN:
        return {"shift": _shift_payload(conn, store_id, shift_id), "duplicate": True}

    expected = _expected_cents(conn, shift, now)
    variance = counted_cents - expected
    conn.execute(
        """UPDATE till_shifts
           SET closed_by = ?, closed_at = ?, expected_cents = ?,
               counted_cents = ?, variance_cents = ?, status = ?
           WHERE id = ?""",
        (closed_by, now, expected, counted_cents, variance, SHIFT_DELIVERED, shift_id),
    )
    conn.execute(
        """INSERT INTO till_movements
               (shift_id, kind, amount_cents, sale_id, note, created_at)
           VALUES (?, 'count', ?, NULL, NULL, ?)""",
        (shift_id, counted_cents, now),
    )
    return {"shift": _shift_payload(conn, store_id, shift_id), "duplicate": False}


def accept_shift(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    shift_id: int,
    accepted_by: int,
    reason: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Owner accepts the handover or records the discrepancy.

    A zero variance accepts cleanly; a non-zero variance is marked observed
    with its cause, never silently corrected. Retrying is idempotent.
    """

    now = time.time() if now is None else now
    shift = _require_shift(conn, store_id, shift_id)
    if shift["status"] in (SHIFT_ACCEPTED, SHIFT_OBSERVED):
        return {"shift": _shift_payload(conn, store_id, shift_id), "duplicate": True}
    if shift["status"] != SHIFT_DELIVERED:
        raise TillError("shift_not_closed", "Cierra la caja antes de aceptarla")

    variance = int(shift["variance_cents"] or 0)
    new_status = SHIFT_ACCEPTED if variance == 0 else SHIFT_OBSERVED
    conn.execute(
        """UPDATE till_shifts
           SET status = ?, accepted_by = ?, accepted_at = ?, accept_reason = ?
           WHERE id = ?""",
        (new_status, accepted_by, now, reason, shift_id),
    )
    return {"shift": _shift_payload(conn, store_id, shift_id), "duplicate": False}


def record_audit_variance(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    product_id: int,
    counted_milli: int,
    employee_id: int,
    now: float | None = None,
) -> dict[str, Any]:
    """Record an inventory audit variance WITHOUT correcting stock silently.

    A physical count that differs from the system stock writes an
    inventory_movements row with reason = "audit_variance" and
    delta_milli = counted - system. The stock itself is not changed here; the
    correction is a separate, justified adjustment.
    """

    now = time.time() if now is None else now
    product = conn.execute(
        "SELECT stock_milli, unlimited_stock FROM products WHERE id = ? AND store_id = ?",
        (product_id, store_id),
    ).fetchone()
    if product is None:
        raise TillError("product_not_found", "Producto no encontrado")
    if product["unlimited_stock"]:
        raise TillError("unlimited_stock", "Este producto tiene inventario sin límite")
    system = int(product["stock_milli"])
    delta = counted_milli - system
    if delta != 0:
        conn.execute(
            """INSERT INTO inventory_movements
                   (product_id, delta_milli, reason, sale_id, employee_id, created_at)
               VALUES (?, ?, 'audit_variance', NULL, ?, ?)""",
            (product_id, delta, employee_id, now),
        )
    return {
        "productId": product_id,
        "countedMilli": counted_milli,
        "systemMilli": system,
        "deltaMilli": delta,
    }


def current_shift(
    conn: sqlite3.Connection, store_id: str
) -> sqlite3.Row | None:
    """The open shift, if any."""

    return conn.execute(
        "SELECT * FROM till_shifts WHERE store_id = ? AND status = ? ORDER BY id DESC LIMIT 1",
        (store_id, SHIFT_OPEN),
    ).fetchone()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_shift(
    conn: sqlite3.Connection, store_id: str, shift_id: int
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM till_shifts WHERE id = ? AND store_id = ?",
        (shift_id, store_id),
    ).fetchone()
    if row is None:
        raise TillError("shift_not_found", "Caja no encontrada")
    return row


def _cash_sales_cents(
    conn: sqlite3.Connection, store_id: str, opened_at: float, up_to: float
) -> int:
    """Cash sales finalized within the shift window (no credit, no CoDi)."""

    row = conn.execute(
        """SELECT COALESCE(SUM(total_cents), 0) AS total
           FROM sales
           WHERE store_id = ? AND payment_method = 'cash' AND status = 'paid_cash'
             AND created_at >= ? AND created_at <= ?""",
        (store_id, opened_at, up_to),
    ).fetchone()
    return int(row["total"])


def _expected_cents(
    conn: sqlite3.Connection, shift: sqlite3.Row, up_to: float
) -> int:
    """expected = float + cash sales + inflows - outflows."""

    sales = _cash_sales_cents(conn, shift["store_id"], shift["opened_at"], up_to)
    inflow = 0
    outflow = 0
    rows = conn.execute(
        "SELECT kind, COALESCE(SUM(amount_cents), 0) AS total FROM till_movements "
        "WHERE shift_id = ? AND kind IN ('cash_in', 'cash_out') GROUP BY kind",
        (shift["id"],),
    ).fetchall()
    for row in rows:
        if row["kind"] == "cash_in":
            inflow = int(row["total"])
        elif row["kind"] == "cash_out":
            outflow = int(row["total"])
    return int(shift["opening_float_cents"]) + sales + inflow - outflow


def _shift_payload(
    conn: sqlite3.Connection, store_id: str, shift_id: int
) -> dict[str, Any]:
    shift = conn.execute(
        "SELECT * FROM till_shifts WHERE id = ? AND store_id = ?",
        (shift_id, store_id),
    ).fetchone()
    if shift is None:
        raise TillError("shift_not_found", "Caja no encontrada")
    expected = shift["expected_cents"]
    if expected is None and shift["status"] == SHIFT_OPEN:
        expected = _expected_cents(conn, shift, time.time())
    movements = conn.execute(
        "SELECT id, kind, amount_cents, sale_id, note, created_at "
        "FROM till_movements WHERE shift_id = ? ORDER BY id",
        (shift_id,),
    ).fetchall()
    return {
        "id": shift["id"],
        "storeId": shift["store_id"],
        "openedBy": shift["opened_by"],
        "openedAt": shift["opened_at"],
        "closedBy": shift["closed_by"],
        "closedAt": shift["closed_at"],
        "openingFloatCents": shift["opening_float_cents"],
        "expectedCents": expected,
        "countedCents": shift["counted_cents"],
        "varianceCents": shift["variance_cents"],
        "status": shift["status"],
        "acceptReason": shift["accept_reason"],
        "acceptedBy": shift["accepted_by"],
        "acceptedAt": shift["accepted_at"],
        "movements": [
            {
                "id": movement["id"],
                "kind": movement["kind"],
                "amountCents": movement["amount_cents"],
                "saleId": movement["sale_id"],
                "note": movement["note"],
                "createdAt": movement["created_at"],
            }
            for movement in movements
        ],
    }