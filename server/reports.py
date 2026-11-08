"""Today report used by /api/reports/today and the owner console."""

from __future__ import annotations

import sqlite3
import time as clock
from datetime import datetime, time as day_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .db import STORE_ID
from .serializers import product_to_dict


def _zone(settings: Settings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        return ZoneInfo("America/Mexico_City")


def today_bounds(settings: Settings, now: float | None = None) -> tuple[float, float]:
    current = clock.time() if now is None else now
    tz = _zone(settings)
    local = datetime.fromtimestamp(current, tz)
    start_local = datetime.combine(local.date(), day_time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.timestamp(), end_local.timestamp()


def fiado_outstanding_cents(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN e.kind = 'charge' THEN e.amount_cents
                                    ELSE -e.amount_cents END), 0) AS balance
           FROM fiado_entries e
           LEFT JOIN sales s ON s.id = e.sale_id
           WHERE e.sale_id IS NULL OR e.kind = 'payment'
                 OR s.status IS NULL OR s.status != 'canceled'"""
    ).fetchone()
    return int(row["balance"] or 0)


def build_today_report(
    conn: sqlite3.Connection,
    settings: Settings,
    now: float | None = None,
) -> dict[str, Any]:
    start, end = today_bounds(settings, now)
    rows = conn.execute(
        """SELECT * FROM sales
           WHERE store_id = ? AND created_at >= ? AND created_at < ?
             AND status != 'canceled'
           ORDER BY created_at ASC""",
        (STORE_ID, start, end),
    ).fetchall()

    total_cents = 0
    cash_cents = 0
    pey_cents = 0
    fiado_cents = 0
    pending = 0
    pending_cents = 0
    aggregates: dict[int, dict[str, Any]] = {}

    employee_ids = {row["employee_id"] for row in rows}
    employees: dict[int, str] = {}
    if employee_ids:
        placeholders = ",".join("?" for _ in employee_ids)
        for employee in conn.execute(
            f"SELECT id, name FROM employees WHERE id IN ({placeholders})",
            tuple(employee_ids),
        ):
            employees[employee["id"]] = employee["name"]

    for row in rows:
        total_cents += row["total_cents"]
        if row["status"] == "paid_cash":
            cash_cents += row["total_cents"]
        elif row["status"] == "paid_pey":
            pey_cents += row["total_cents"]
        elif row["status"] == "credit":
            fiado_cents += row["total_cents"]
        if row["status"] in {"pending", "por_conciliar"}:
            pending += 1
            pending_cents += row["total_cents"]
        employee_id = row["employee_id"]
        bucket = aggregates.setdefault(
            employee_id,
            {
                "employeeId": employee_id,
                "name": employees.get(employee_id, ""),
                "salesCount": 0,
                "totalCents": 0,
            },
        )
        bucket["salesCount"] += 1
        bucket["totalCents"] += row["total_cents"]

    top_rows = conn.execute(
        """SELECT si.product_id, si.name, SUM(si.qty_milli) AS qty_milli,
                  SUM(si.line_total_cents) AS total_cents
           FROM sale_items si
           JOIN sales s ON s.id = si.sale_id
           WHERE s.store_id = ? AND s.created_at >= ? AND s.created_at < ?
             AND s.status != 'canceled'
           GROUP BY si.product_id, si.name
           ORDER BY total_cents DESC, qty_milli DESC
           LIMIT 5""",
        (STORE_ID, start, end),
    ).fetchall()

    low_stock_rows = conn.execute(
        """SELECT * FROM products
           WHERE store_id = ? AND stock_milli <= low_stock_milli
           ORDER BY stock_milli ASC, id ASC""",
        (STORE_ID,),
    ).fetchall()

    by_employee = sorted(
        aggregates.values(),
        key=lambda item: (-item["totalCents"], item["employeeId"]),
    )
    top_products = [
        {
            "productId": row["product_id"],
            "name": row["name"],
            "qtyMilli": int(row["qty_milli"] or 0),
            "totalCents": int(row["total_cents"] or 0),
        }
        for row in top_rows
    ]

    return {
        "totalCents": total_cents,
        "collectedCents": cash_cents + pey_cents,
        "cashCents": cash_cents,
        "peyCents": pey_cents,
        "fiadoCents": fiado_cents,
        "salesCount": len(rows),
        "byEmployee": by_employee,
        "topProducts": top_products,
        "lowStock": [product_to_dict(row) for row in low_stock_rows],
        "pending": pending,
        "pendingCents": pending_cents,
        "fiadoOutstandingCents": fiado_outstanding_cents(conn),
        "demoMode": settings.modo_demo,
    }
