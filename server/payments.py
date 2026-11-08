"""Payment application and inventory movement rules.

apply_payment is the only function that marks a PEY sale as paid. Callers
must wrap it in a BEGIN IMMEDIATE transaction (see db.write_transaction).
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

FINAL_PAID_STATUSES = {"paid_cash", "paid_pey", "credit"}


def append_note(current: str | None, addition: str | None) -> str | None:
    if not addition:
        return current
    if not current:
        return addition
    if addition in current:
        return current
    return f"{current} | {addition}"


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(int(cents))
    return sign + "$" + str(value // 100) + "." + str(value % 100).zfill(2)


def decrement_inventory(
    conn: sqlite3.Connection,
    sale_id: str,
    employee_id: int,
    *,
    now: float | None = None,
) -> None:
    now = time.time() if now is None else now
    items = conn.execute(
        "SELECT product_id, qty_milli FROM sale_items WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
    for item in items:
        conn.execute(
            "UPDATE products SET stock_milli = stock_milli - ? WHERE id = ?",
            (item["qty_milli"], item["product_id"]),
        )
        conn.execute(
            """INSERT INTO inventory_movements
               (product_id, delta_milli, reason, sale_id, employee_id, created_at)
               VALUES (?, ?, 'sale', ?, ?, ?)""",
            (item["product_id"], -item["qty_milli"], sale_id, employee_id, now),
        )


def restore_inventory(
    conn: sqlite3.Connection,
    sale_id: str,
    employee_id: int,
    *,
    now: float | None = None,
) -> None:
    now = time.time() if now is None else now
    items = conn.execute(
        "SELECT product_id, qty_milli FROM sale_items WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
    for item in items:
        conn.execute(
            "UPDATE products SET stock_milli = stock_milli + ? WHERE id = ?",
            (item["qty_milli"], item["product_id"]),
        )
        conn.execute(
            """INSERT INTO inventory_movements
               (product_id, delta_milli, reason, sale_id, employee_id, created_at)
               VALUES (?, ?, 'cancel', ?, ?, ?)""",
            (item["product_id"], item["qty_milli"], sale_id, employee_id, now),
        )


def record_payment(
    conn: sqlite3.Connection,
    *,
    tx_id: str,
    sale_id: str,
    amount_cents: int,
    source: str,
    applied: bool,
    received_at: float,
) -> None:
    conn.execute(
        """INSERT INTO payments
           (tx_id, sale_id, amount_cents, method, source, applied, received_at)
           VALUES (?, ?, ?, 'pey', ?, ?, ?)""",
        (tx_id, sale_id, amount_cents, source, 1 if applied else 0, received_at),
    )


def apply_payment(
    conn: sqlite3.Connection,
    *,
    sale_id: str,
    transaction_id: str,
    amount_cents: int,
    source: str,
    received_at: float | None = None,
) -> dict[str, Any]:
    """Apply one verified PEY transaction exactly once.

    Returns an outcome plus the current sale row. An extra payment on an
    already paid sale, or a payment on a canceled sale, is still written to
    the payments table with applied=0 instead of being dropped.
    """

    now = time.time() if received_at is None else received_at
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale is None:
        return {"outcome": "unknown_sale", "sale": None, "applied": False}

    duplicate = conn.execute(
        "SELECT 1 FROM payments WHERE tx_id = ?", (transaction_id,)
    ).fetchone()
    if duplicate is not None:
        return {"outcome": "duplicate_transaction", "sale": sale, "applied": False}

    status = sale["status"]

    if status == "canceled":
        record_payment(
            conn,
            tx_id=transaction_id,
            sale_id=sale_id,
            amount_cents=amount_cents,
            source=source,
            applied=False,
            received_at=now,
        )
        note = append_note(
            sale["note"],
            f"Pago tardío PEY {_money(amount_cents)} (tx {transaction_id}) "
            "registrado sin aplicar: la venta está cancelada.",
        )
        conn.execute("UPDATE sales SET note = ? WHERE id = ?", (note, sale_id))
        return {
            "outcome": "late_payment",
            "sale": conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone(),
            "applied": False,
        }

    if status in FINAL_PAID_STATUSES:
        record_payment(
            conn,
            tx_id=transaction_id,
            sale_id=sale_id,
            amount_cents=amount_cents,
            source=source,
            applied=False,
            received_at=now,
        )
        note = append_note(
            sale["note"],
            f"Pago extra PEY {_money(amount_cents)} (tx {transaction_id}) "
            "registrado sin aplicar: la venta ya estaba pagada.",
        )
        conn.execute("UPDATE sales SET note = ? WHERE id = ?", (note, sale_id))
        return {
            "outcome": "extra_payment",
            "sale": conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone(),
            "applied": False,
        }

    if amount_cents != sale["charged_cents"]:
        record_payment(
            conn,
            tx_id=transaction_id,
            sale_id=sale_id,
            amount_cents=amount_cents,
            source=source,
            applied=False,
            received_at=now,
        )
        note = append_note(
            sale["note"],
            f"Pago PEY {_money(amount_cents)} (tx {transaction_id}) no coincide "
            f"con el cobro de {_money(sale['charged_cents'])}; por conciliar.",
        )
        conn.execute(
            "UPDATE sales SET status = 'por_conciliar', note = ? WHERE id = ?",
            (note, sale_id),
        )
        return {
            "outcome": "amount_mismatch",
            "sale": conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone(),
            "applied": False,
        }

    record_payment(
        conn,
        tx_id=transaction_id,
        sale_id=sale_id,
        amount_cents=amount_cents,
        source=source,
        applied=True,
        received_at=now,
    )

    note = sale["note"]
    if status == "por_conciliar":
        note = append_note(
            note,
            f"Conciliada con pago PEY {_money(amount_cents)} (tx {transaction_id}).",
        )
    elif status == "expired":
        note = append_note(
            note,
            f"Pago PEY recibido después de expirar el QR (tx {transaction_id}).",
        )

    conn.execute(
        """UPDATE sales
           SET status = 'paid_pey', pey_tx_id = ?, paid_at = ?, note = ?
           WHERE id = ?""",
        (transaction_id, now, note, sale_id),
    )
    decrement_inventory(conn, sale_id, sale["employee_id"], now=now)

    return {
        "outcome": "applied",
        "sale": conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone(),
        "applied": True,
    }
