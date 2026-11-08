"""Small JSON serializers shared by the public and console endpoints."""

from __future__ import annotations

import sqlite3
from typing import Any


def store_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"]}


def employee_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "role": row["role"],
    }


def product_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "unit": row["unit"],
        "priceCents": row["price_cents"],
        "stockMilli": row["stock_milli"],
        "lowStockMilli": row["low_stock_milli"],
        "quick": bool(row["quick"]),
    }


def sale_item_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "productId": row["product_id"],
        "name": row["name"],
        "unit": row["unit"],
        "qtyMilli": row["qty_milli"],
        "unitPriceCents": row["unit_price_cents"],
        "lineTotalCents": row["line_total_cents"],
    }


def customer_balance_cents(conn: sqlite3.Connection, customer_id: int) -> int:
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN e.kind = 'charge' THEN e.amount_cents
                                    ELSE -e.amount_cents END), 0) AS balance
           FROM fiado_entries e
           LEFT JOIN sales s ON s.id = e.sale_id
           WHERE e.customer_id = ?
             AND (e.sale_id IS NULL OR e.kind = 'payment'
                  OR s.status IS NULL OR s.status != 'canceled')""",
        (customer_id,),
    ).fetchone()
    return int(row["balance"] or 0)


def customer_to_dict(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    include_entries: bool = False,
) -> dict[str, Any]:
    customer_id = int(row["id"])
    data: dict[str, Any] = {
        "id": customer_id,
        "name": row["name"],
        "phone": row["phone"],
        "balanceCents": customer_balance_cents(conn, customer_id),
    }
    if include_entries:
        entries = conn.execute(
            """SELECT id, customer_id, sale_id, kind, amount_cents, note,
                      employee_id, created_at
               FROM fiado_entries WHERE customer_id = ?
               ORDER BY created_at ASC, id ASC""",
            (customer_id,),
        ).fetchall()
        data["entries"] = [
            {
                "id": entry["id"],
                "saleId": entry["sale_id"],
                "kind": entry["kind"],
                "amountCents": entry["amount_cents"],
                "note": entry["note"],
                "employeeId": entry["employee_id"],
                "createdAt": entry["created_at"],
            }
            for entry in entries
        ]
    return data


def sale_to_dict(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    include_items: bool = True,
) -> dict[str, Any]:
    sale_id = row["id"]
    customer = None
    if row["customer_id"] is not None:
        customer_row = conn.execute(
            "SELECT id, name, phone FROM fiado_customers WHERE id = ?",
            (row["customer_id"],),
        ).fetchone()
        if customer_row is not None:
            customer = {
                "id": customer_row["id"],
                "name": customer_row["name"],
                "phone": customer_row["phone"],
            }

    data: dict[str, Any] = {
        "id": sale_id,
        "saleId": sale_id,
        "storeId": row["store_id"],
        "employeeId": row["employee_id"],
        "createdAt": row["created_at"],
        "status": row["status"],
        "paymentMethod": row["payment_method"],
        "totalCents": row["total_cents"],
        "chargedCents": row["charged_cents"],
        "cashReceivedCents": row["cash_received_cents"],
        "changeCents": row["change_cents"],
        "customerId": row["customer_id"],
        "customer": customer,
        "qrId": row["pey_qr_id"],
        "peyQrId": row["pey_qr_id"],
        "txId": row["pey_tx_id"],
        "peyTxId": row["pey_tx_id"],
        "paidAt": row["paid_at"],
        "expiresAt": row["expires_at"],
        "note": row["note"],
    }
    if include_items:
        items = conn.execute(
            """SELECT product_id, name, unit, qty_milli, unit_price_cents,
                      line_total_cents
               FROM sale_items WHERE sale_id = ? ORDER BY id ASC""",
            (sale_id,),
        ).fetchall()
        data["items"] = [sale_item_to_dict(item) for item in items]
    return data
