"""Store credit (fiado) domain: limits, due dates, override, repayment, reminders.

Server-side domain for M4 ("Store credit (fiado)" from docs/produccion/
09-paquetes-y-aceptacion.md). Everything that would touch a real SMS/push is
SIMULADO: the notification hook only logs and writes a durable trace row, so
no real message is sent and no real data leaves the server.

This module extends the v1/v3.2 fiado ledger (fiado_customers /
fiado_entries) additively, without touching server/db.py or server/main.py:

  fiado_customers += credit_limit_cents, due_days, active, reminders_consent
  fiado_entries   += due_at, reminded_at (charges)
  fiado_overrides    owner-authorized charge beyond the limit (audit trace)
  fiado_reminders    SIMULADO notification trace (proof of consent + send)

Domain functions raise :class:`FiadoError` (mapped to HTTP 4xx by
routes_fiado.py) and every write runs inside db.write_transaction
(BEGIN IMMEDIATE), so two concurrent charges/repayments serialize.

Flow (mirrors F-04 "Online credit" and doc 05 "Extended fiado"):

    patch_customer   -> set credit limit / due days / consent / active
    create_charge    -> validate limit, compute due date, insert charge
    create_override  -> owner authorizes a charge beyond the limit (trace)
    create_repayment -> partial installment or full settlement (balance)
    send_reminders   -> SIMULADO notification for consenting customers only
    export_csv       -> Gratis-plan CSV without PII (no phone / contact)
"""

from __future__ import annotations

import csv
import io
import logging
import sqlite3
import time
from typing import Any, Callable

from .db import STORE_ID
from .serializers import customer_balance_cents

logger = logging.getLogger("abarpay")

# Reminder classification.
REMINDER_OVERDUE = "overdue"
REMINDER_UPCOMING = "upcoming"

# Sentinel so patch_customer can tell "field absent" from "field = None".
_UNSET = object()


class FiadoError(Exception):
    """A business rejection for one fiado operation (mapped to HTTP 4xx)."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.payload = payload or {}


# ---------------------------------------------------------------------------
# Schema (additive, idempotent, safe on every request/start)
# ---------------------------------------------------------------------------

# New tables for M4. The existing fiado_customers / fiado_entries tables stay
# in db.py; only their new columns are added here via ALTER TABLE.
FIADO_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS fiado_overrides (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    customer_id INTEGER NOT NULL REFERENCES fiado_customers(id),
    amount_cents INTEGER NOT NULL,
    reason TEXT NOT NULL,
    employee_id INTEGER REFERENCES employees(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fiado_reminders (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    customer_id INTEGER NOT NULL REFERENCES fiado_customers(id),
    entry_id INTEGER REFERENCES fiado_entries(id),
    kind TEXT NOT NULL CHECK(kind IN ('overdue','upcoming')),
    detail TEXT,
    sent_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fiado_overrides_store
    ON fiado_overrides(store_id, customer_id);
CREATE INDEX IF NOT EXISTS idx_fiado_reminders_store
    ON fiado_reminders(store_id, customer_id, sent_at);
"""

# (table, column, ddl) for the additive columns on existing tables.
_FIADO_COLUMN_MIGRATIONS = (
    ("fiado_customers", "credit_limit_cents", "INTEGER"),
    ("fiado_customers", "due_days", "INTEGER"),
    ("fiado_customers", "active", "INTEGER NOT NULL DEFAULT 1"),
    ("fiado_customers", "reminders_consent", "INTEGER NOT NULL DEFAULT 0"),
    ("fiado_entries", "due_at", "REAL"),
    ("fiado_entries", "reminded_at", "REAL"),
)


def ensure_fiado_schema(conn: sqlite3.Connection) -> None:
    """Create the M4 fiado tables/columns if missing (idempotent)."""

    conn.executescript(FIADO_TABLES_SQL)
    for table, column, ddl in _FIADO_COLUMN_MIGRATIONS:
        existing = {
            row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
        }
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ---------------------------------------------------------------------------
# SIMULADO notification hook
# ---------------------------------------------------------------------------


def _log_notification_hook(
    customer_name: str,
    entry: sqlite3.Row,
    kind: str,
    now: float,
) -> None:
    logger.info(
        "SIMULADO recordatorio fiado: cliente=%r entrada=%s tipo=%s montoCents=%s",
        customer_name,
        entry["id"],
        kind,
        entry["amount_cents"],
    )


# Injectable for tests and future real providers (SMS/push). The default only
# logs; the durable proof of delivery is the fiado_reminders trace row.
notification_hook: Callable[[str, sqlite3.Row, str, float], None] = (
    _log_notification_hook
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> float:
    return time.time()


def require_customer(conn: sqlite3.Connection, customer_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM fiado_customers WHERE id = ? AND store_id = ?",
        (customer_id, STORE_ID),
    ).fetchone()
    if row is None:
        raise FiadoError("customer_not_found", "Cliente de fiado no encontrado")
    return row


def customer_payload(conn: sqlite3.Connection, customer_id: int) -> dict[str, Any]:
    row = require_customer(conn, customer_id)
    balance = customer_balance_cents(conn, customer_id)
    limit = row["credit_limit_cents"]
    available = None if limit is None else max(0, int(limit) - balance)
    return {
        "id": customer_id,
        "name": row["name"],
        "phone": row["phone"],
        "active": bool(row["active"]),
        "creditLimitCents": limit,
        "dueDays": row["due_days"],
        "remindersConsent": bool(row["reminders_consent"]),
        "balanceCents": balance,
        "availableCreditCents": available,
    }


def entry_payload(conn: sqlite3.Connection, entry_id: int) -> dict[str, Any]:
    row = conn.execute(
        """SELECT e.id, e.customer_id, e.kind, e.amount_cents, e.note,
                  e.employee_id, e.created_at, e.due_at, e.reminded_at,
                  emp.name AS employee_name
           FROM fiado_entries e
           LEFT JOIN employees emp ON emp.id = e.employee_id
           WHERE e.id = ?""",
        (entry_id,),
    ).fetchone()
    if row is None:
        raise FiadoError("entry_not_found", "Movimiento de fiado no encontrado")
    return {
        "id": row["id"],
        "customerId": row["customer_id"],
        "kind": row["kind"],
        "amountCents": row["amount_cents"],
        "note": row["note"],
        "employeeId": row["employee_id"],
        "employeeName": row["employee_name"],
        "dueAt": row["due_at"],
        "remindedAt": row["reminded_at"],
        "createdAt": row["created_at"],
    }


def _resolve_due_at(
    customer: sqlite3.Row,
    due_at: float | None,
    now: float,
) -> float | None:
    if due_at is not None:
        if due_at <= 0:
            raise FiadoError("invalid_due_at", "La fecha de vencimiento no es válida")
        return float(due_at)
    due_days = customer["due_days"]
    if due_days is not None:
        return now + float(due_days) * 86400.0
    return None


def _require_active(customer: sqlite3.Row) -> None:
    if not customer["active"]:
        raise FiadoError("customer_inactive", "El cliente de fiado está inactivo")


# ---------------------------------------------------------------------------
# Customer limits / due days / consent / active
# ---------------------------------------------------------------------------


def patch_customer(
    conn: sqlite3.Connection,
    *,
    customer_id: int,
    credit_limit_cents: Any = _UNSET,
    due_days: Any = _UNSET,
    active: Any = _UNSET,
    reminders_consent: Any = _UNSET,
) -> dict[str, Any]:
    require_customer(conn, customer_id)
    if credit_limit_cents is not _UNSET:
        if credit_limit_cents is not None and int(credit_limit_cents) < 0:
            raise FiadoError(
                "invalid_credit_limit", "El límite de crédito no puede ser negativo"
            )
        conn.execute(
            "UPDATE fiado_customers SET credit_limit_cents = ? WHERE id = ?",
            (credit_limit_cents, customer_id),
        )
    if due_days is not _UNSET:
        if due_days is not None and int(due_days) < 0:
            raise FiadoError(
                "invalid_due_days", "Los días de plazo no pueden ser negativos"
            )
        conn.execute(
            "UPDATE fiado_customers SET due_days = ? WHERE id = ?",
            (due_days, customer_id),
        )
    if active is not _UNSET:
        conn.execute(
            "UPDATE fiado_customers SET active = ? WHERE id = ?",
            (1 if active else 0, customer_id),
        )
    if reminders_consent is not _UNSET:
        conn.execute(
            "UPDATE fiado_customers SET reminders_consent = ? WHERE id = ?",
            (1 if reminders_consent else 0, customer_id),
        )
    return customer_payload(conn, customer_id)


# ---------------------------------------------------------------------------
# Charges and the credit-limit check
# ---------------------------------------------------------------------------


def create_charge(
    conn: sqlite3.Connection,
    *,
    customer_id: int,
    amount_cents: int,
    due_at: float | None = None,
    note: str | None = None,
    employee_id: int | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    now = _now() if now is None else now
    if amount_cents <= 0:
        raise FiadoError("invalid_amount", "El monto debe ser mayor que cero")
    customer = require_customer(conn, customer_id)
    _require_active(customer)

    balance = customer_balance_cents(conn, customer_id)
    limit = customer["credit_limit_cents"]
    if limit is not None and balance + amount_cents > int(limit):
        raise FiadoError(
            "credit_limit_exceeded",
            "El cargo supera el límite de crédito del cliente",
            payload={
                "availableCreditCents": max(0, int(limit) - balance),
                "requestedCents": amount_cents,
                "balanceCents": balance,
                "creditLimitCents": int(limit),
            },
        )

    resolved_due = _resolve_due_at(customer, due_at, now)
    cursor = conn.execute(
        """INSERT INTO fiado_entries
               (customer_id, sale_id, kind, amount_cents, note,
                employee_id, created_at, due_at)
           VALUES (?, NULL, 'charge', ?, ?, ?, ?, ?)""",
        (
            customer_id,
            amount_cents,
            (note or "").strip() or None,
            employee_id,
            now,
            resolved_due,
        ),
    )
    return {
        "entry": entry_payload(conn, int(cursor.lastrowid)),
        "customer": customer_payload(conn, customer_id),
    }


def create_override(
    conn: sqlite3.Connection,
    *,
    customer_id: int,
    amount_cents: int,
    reason: str,
    due_at: float | None = None,
    note: str | None = None,
    employee_id: int | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Owner authorizes a charge beyond the limit, leaving an audit trace."""

    now = _now() if now is None else now
    if amount_cents <= 0:
        raise FiadoError("invalid_amount", "El monto debe ser mayor que cero")
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise FiadoError(
            "override_requires_reason", "La autorización requiere un motivo"
        )
    customer = require_customer(conn, customer_id)
    _require_active(customer)

    resolved_due = _resolve_due_at(customer, due_at, now)
    cursor = conn.execute(
        """INSERT INTO fiado_overrides
               (store_id, customer_id, amount_cents, reason, employee_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (STORE_ID, customer_id, amount_cents, reason_clean, employee_id, now),
    )
    override_id = int(cursor.lastrowid)
    cursor = conn.execute(
        """INSERT INTO fiado_entries
               (customer_id, sale_id, kind, amount_cents, note,
                employee_id, created_at, due_at)
           VALUES (?, NULL, 'charge', ?, ?, ?, ?, ?)""",
        (
            customer_id,
            amount_cents,
            (note or "").strip() or None,
            employee_id,
            now,
            resolved_due,
        ),
    )
    return {
        "override": override_payload(conn, override_id),
        "entry": entry_payload(conn, int(cursor.lastrowid)),
        "customer": customer_payload(conn, customer_id),
    }


def override_payload(conn: sqlite3.Connection, override_id: int) -> dict[str, Any]:
    row = conn.execute(
        """SELECT o.*, emp.name AS employee_name
           FROM fiado_overrides o
           LEFT JOIN employees emp ON emp.id = o.employee_id
           WHERE o.id = ?""",
        (override_id,),
    ).fetchone()
    if row is None:
        raise FiadoError("override_not_found", "Autorización no encontrada")
    return {
        "id": row["id"],
        "customerId": row["customer_id"],
        "amountCents": row["amount_cents"],
        "reason": row["reason"],
        "employeeId": row["employee_id"],
        "employeeName": row["employee_name"],
        "createdAt": row["created_at"],
    }


# ---------------------------------------------------------------------------
# Repayment (partial installment or full settlement)
# ---------------------------------------------------------------------------


def create_repayment(
    conn: sqlite3.Connection,
    *,
    customer_id: int,
    amount_cents: int,
    note: str | None = None,
    employee_id: int | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    now = _now() if now is None else now
    if amount_cents <= 0:
        raise FiadoError("invalid_amount", "El abono debe ser mayor que cero")
    require_customer(conn, customer_id)

    balance = customer_balance_cents(conn, customer_id)
    if amount_cents > balance:
        raise FiadoError(
            "overpayment",
            "El abono supera el saldo pendiente",
            payload={"balanceCents": balance, "requestedCents": amount_cents},
        )

    cursor = conn.execute(
        """INSERT INTO fiado_entries
               (customer_id, sale_id, kind, amount_cents, note,
                employee_id, created_at)
           VALUES (?, NULL, 'payment', ?, ?, ?, ?)""",
        (
            customer_id,
            amount_cents,
            (note or "").strip() or None,
            employee_id,
            now,
        ),
    )
    new_balance = customer_balance_cents(conn, customer_id)
    return {
        "entry": entry_payload(conn, int(cursor.lastrowid)),
        "customerId": customer_id,
        "balanceCents": new_balance,
        "settled": new_balance == 0,
    }


# ---------------------------------------------------------------------------
# Reminders (opt-in, SIMULADO notification hook)
# ---------------------------------------------------------------------------


def _reminder_rows(
    conn: sqlite3.Connection,
    *,
    due_within_days: int,
    now: float,
) -> list[sqlite3.Row]:
    """Charges due or upcoming for consenting, active, still-owing customers."""

    end = now + float(due_within_days) * 86400.0
    rows = conn.execute(
        """SELECT e.id AS entry_id, e.customer_id, e.amount_cents, e.due_at,
                  e.reminded_at, c.name AS customer_name
           FROM fiado_entries e
           JOIN fiado_customers c ON c.id = e.customer_id
           WHERE c.store_id = ?
             AND e.kind = 'charge'
             AND e.due_at IS NOT NULL
             AND c.active = 1
             AND c.reminders_consent = 1
             AND e.due_at <= ?
           ORDER BY e.due_at ASC, e.id ASC""",
        (STORE_ID, end),
    ).fetchall()

    # A fully settled customer is not reminded (their balance is zero).
    balances: dict[int, int] = {}
    result: list[sqlite3.Row] = []
    for row in rows:
        customer_id = int(row["customer_id"])
        if customer_id not in balances:
            balances[customer_id] = customer_balance_cents(conn, customer_id)
        if balances[customer_id] > 0:
            result.append(row)
    return result


def _classify(row: sqlite3.Row, now: float) -> str:
    return REMINDER_OVERDUE if float(row["due_at"]) < now else REMINDER_UPCOMING


def _reminder_payload(row: sqlite3.Row, now: float) -> dict[str, Any]:
    due_at = float(row["due_at"])
    return {
        "entryId": row["entry_id"],
        "customerId": row["customer_id"],
        "customerName": row["customer_name"],
        "amountCents": row["amount_cents"],
        "dueAt": due_at,
        "kind": _classify(row, now),
        "daysDue": int((now - due_at) // 86400.0),
        "remindedAt": row["reminded_at"],
    }


def list_reminders(
    conn: sqlite3.Connection,
    *,
    due_within_days: int = 7,
    now: float | None = None,
) -> dict[str, Any]:
    now = _now() if now is None else now
    overdue: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    for row in _reminder_rows(conn, due_within_days=due_within_days, now=now):
        payload = _reminder_payload(row, now)
        if payload["kind"] == REMINDER_OVERDUE:
            overdue.append(payload)
        else:
            upcoming.append(payload)
    return {"overdue": overdue, "upcoming": upcoming, "simulado": True}


def send_reminders(
    conn: sqlite3.Connection,
    *,
    due_within_days: int = 7,
    now: float | None = None,
    hook: Callable[[str, sqlite3.Row, str, float], None] | None = None,
) -> dict[str, Any]:
    """Send SIMULADO reminders for consenting customers and record the trace.

    Customers without reminders_consent are never sent anything (the query only
    selects consenting rows). Each send records a fiado_reminders row and marks
    the charge reminded_at as the durable SIMULADO proof.
    """

    now = _now() if now is None else now
    hook = hook or notification_hook
    sent: list[dict[str, Any]] = []
    for row in _reminder_rows(conn, due_within_days=due_within_days, now=now):
        kind = _classify(row, now)
        hook(row["customer_name"], row, kind, now)
        cursor = conn.execute(
            """INSERT INTO fiado_reminders
                   (store_id, customer_id, entry_id, kind, detail, sent_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                STORE_ID,
                row["customer_id"],
                row["entry_id"],
                kind,
                f"SIMULADO recordatorio {kind}",
                now,
            ),
        )
        conn.execute(
            "UPDATE fiado_entries SET reminded_at = ? WHERE id = ?",
            (now, row["entry_id"]),
        )
        payload = _reminder_payload(row, now)
        payload["remindedAt"] = now
        sent.append(payload)
    return {"sent": sent, "simulado": True}


# ---------------------------------------------------------------------------
# CSV export (Gratis plan, no PII leak)
# ---------------------------------------------------------------------------

# Columns intentionally exclude phone and any contact data (no PII leak).
CSV_COLUMNS = (
    "customerId",
    "customerName",
    "entryId",
    "kind",
    "amountCents",
    "note",
    "employeeName",
    "dueAt",
    "remindedAt",
    "createdAt",
)


def export_csv(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """SELECT e.id AS entry_id, e.customer_id, e.kind, e.amount_cents,
                  e.note, e.employee_id, e.created_at, e.due_at, e.reminded_at,
                  c.name AS customer_name, emp.name AS employee_name
           FROM fiado_entries e
           JOIN fiado_customers c ON c.id = e.customer_id
           LEFT JOIN employees emp ON emp.id = e.employee_id
           WHERE c.store_id = ?
           ORDER BY e.created_at ASC, e.id ASC""",
        (STORE_ID,),
    ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row["customer_id"],
                row["customer_name"],
                row["entry_id"],
                row["kind"],
                row["amount_cents"],
                row["note"],
                row["employee_name"],
                row["due_at"],
                row["reminded_at"],
                row["created_at"],
            ]
        )
    return buffer.getvalue()
