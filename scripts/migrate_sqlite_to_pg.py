#!/usr/bin/env python3
"""One-time, idempotent SQLite -> PostgreSQL migration for Abarpay tenancy.

Reads a single-store SQLite database (server/db.py schema) and writes the
multi-tenant PostgreSQL schema from docs/produccion/02-contratos-y-tenencia.md:

1. Create the schema and apply RLS (migrations/001_schema.sql, idempotent).
2. Inventory the stores and assign the explicitly identified demo store to its
   own tenant (1-to-1). For that store, create the tenant + store and propagate
   tenant_id to every business row.
3. Create historical users with idp='legacy' for ALL employees (active and
   inactive) plus v2-equivalent memberships. These rows are never auto-linked
   to a real sign-in (a real sign-in creates its own users row).
4. Reassign employee_id and every foreign-key reference to the new UUIDs.
5. Emit a per-table count difference report (SQLite vs PostgreSQL).

Idempotency: tenant/store/users/memberships use natural unique keys and every
business row gets a deterministic UUID (UUIDv5 of the source primary key), so
re-running never duplicates rows. The migrator runs as the superuser principal;
the service role abarpay_app is never used here.

Usage:
    python scripts/migrate_sqlite_to_pg.py --dry-run
    python scripts/migrate_sqlite_to_pg.py --apply
"""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "server" / "data" / "abarpay.db"
DEFAULT_SCHEMA = REPO_ROOT / "migrations" / "001_schema.sql"
DEFAULT_STORE_ID = "tiendita-esquina"
DEFAULT_DSN = "host=127.0.0.1 port=5432 dbname=abarpay_dev user=" + getpass.getuser()

# Fixed namespace so the generated UUIDs are stable across runs (idempotency).
NAMESPACE = uuid.UUID("9f0b5e4d-3a2b-4c1d-8e7f-6a5b4c3d2e1f")


def did(*parts: str) -> uuid.UUID:
    """Deterministic UUID for one migrated row, keyed on its source identity."""

    return uuid.uuid5(NAMESPACE, "/".join(str(p) for p in parts))


def ts(value: object) -> datetime | None:
    """Convert a SQLite REAL unix epoch (seconds) to an aware timestamp."""

    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="SQLite source database (default: %(default)s)")
    parser.add_argument("--dsn", default=os_dsn(),
                        help="PostgreSQL connection string (default: %(default)s)")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA,
                        help="001_schema.sql path (default: %(default)s)")
    parser.add_argument("--store-id", default=DEFAULT_STORE_ID,
                        help="SQLite store id to migrate (default: %(default)s)")
    parser.add_argument("--tenant-slug", default=None,
                        help="Demo tenant slug (default: the SQLite store id)")
    parser.add_argument("--tenant-name", default=None,
                        help="Demo tenant name (default: the SQLite store name)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="Report only; write nothing to PostgreSQL")
    mode.add_argument("--apply", action="store_true",
                      help="Create schema and migrate data (idempotent)")
    return parser.parse_args(argv)


def os_dsn() -> str:
    import os
    return os.environ.get("ABARPAY_PG_DSN") or DEFAULT_DSN


# --- SQLite ----------------------------------------------------------------

def open_sqlite(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise SystemExit(f"SQLite source not found: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_has(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def sqlite_count(conn: sqlite3.Connection, table: str,
                 store_id: str | None = None) -> int:
    if not sqlite_has(conn, table):
        return 0
    if store_id is not None:
        row = conn.execute(
            f"SELECT count(*) FROM {table} WHERE store_id = ?", (store_id,)
        ).fetchone()
    else:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    return int(row[0])


# --- PostgreSQL ------------------------------------------------------------

def connect_pg(dsn: str):
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "psycopg is not installed. Run: pip install 'psycopg[binary]' psycopg-pool"
        ) from exc
    return psycopg.connect(dsn)


def apply_sql_file(conn, path: Path) -> None:
    """Run a .sql file (multiple statements, no parameters)."""

    text = path.read_text()
    with conn.cursor() as cur:
        cur.execute(text)
    conn.commit()


def ensure_tenant(conn, slug: str, name: str) -> uuid.UUID:
    tid = did("tenant", slug)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (id, slug, name, status) VALUES (%s, %s, %s, 'active') "
            "ON CONFLICT (slug) DO NOTHING",
            (tid, slug, name),
        )
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
        row = cur.fetchone()
    return row[0]


def ensure_store(conn, tenant_id: uuid.UUID, slug: str, name: str) -> uuid.UUID:
    sid = did("store", slug)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO stores (id, tenant_id, name) VALUES (%s, %s, %s) "
            "ON CONFLICT (tenant_id) DO NOTHING",
            (sid, tenant_id, name),
        )
        cur.execute("SELECT id FROM stores WHERE tenant_id = %s", (tenant_id,))
        row = cur.fetchone()
    return row[0]


def pg_tenant_id(conn, slug: str) -> uuid.UUID | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
        row = cur.fetchone()
    return row[0] if row else None


def pg_count(conn, table: str, tenant_id: uuid.UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {table} WHERE tenant_id = %s", (tenant_id,)
        )
        return int(cur.fetchone()[0])


# --- Migration -------------------------------------------------------------

def migrate(conn, *, source: Path, schema: Path, store_id: str,
            tenant_slug: str, tenant_name: str) -> dict[str, int]:
    """Apply schema + seed the demo tenant + migrate all rows. Returns SQLite counts."""

    apply_sql_file(conn, schema)

    db = open_sqlite(source)

    # Identify the demo store.
    store_row = db.execute("SELECT id, name FROM stores WHERE id = ?",
                           (store_id,)).fetchone()
    if store_row is None:
        store_row = db.execute("SELECT id, name FROM stores LIMIT 1").fetchone()
    if store_row is None:
        raise SystemExit("SQLite source has no stores row to migrate")
    store_name = store_row["name"] or "Mi negocio"

    slug = tenant_slug or store_row["id"] or "tiendita-esquina"
    name = tenant_name or store_name

    tenant_id = ensure_tenant(conn, slug, name)
    store_uuid = ensure_store(conn, tenant_id, slug, name)
    conn.commit()

    counts: dict[str, int] = {}
    counts["stores"] = 1

    # -- employees -> users (legacy) + memberships ---------------------------
    employees = db.execute(
        "SELECT id, name, role, active, can_sell, can_fiado, can_inventory "
        "FROM employees WHERE store_id = ? ORDER BY id",
        (store_row["id"],),
    ).fetchall()
    counts["employees"] = len(employees)

    user_ids: dict[int, uuid.UUID] = {}
    if employees:
        with conn.cursor() as cur:
            for emp in employees:
                uid = did("user", slug, str(emp["id"]))
                user_ids[int(emp["id"])] = uid
                cur.execute(
                    "INSERT INTO users (id, email, name, idp, external_sub) "
                    "VALUES (%s, %s, %s, 'legacy', %s) "
                    "ON CONFLICT (idp, external_sub) DO NOTHING",
                    (uid, f"legacy-{slug}-{emp['id']}@abarpay.local", emp["name"],
                     f"legacy-{slug}-{emp['id']}"),
                )
                cur.execute(
                    "INSERT INTO memberships "
                    "(id, user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, user_id) DO NOTHING",
                    (did("membership", slug, str(emp["id"])), uid, tenant_id,
                     emp["role"], bool(emp["can_sell"]), bool(emp["can_fiado"]),
                     bool(emp["can_inventory"]), bool(emp["active"])),
                )
        conn.commit()

    # -- products -----------------------------------------------------------
    products = db.execute(
        "SELECT * FROM products WHERE store_id = ? ORDER BY id",
        (store_row["id"],),
    ).fetchall()
    counts["products"] = len(products)
    product_ids: dict[int, uuid.UUID] = {}
    if products:
        with conn.cursor() as cur:
            for p in products:
                pid = did("product", slug, str(p["id"]))
                product_ids[int(p["id"])] = pid
                cur.execute(
                    "INSERT INTO products "
                    "(id, tenant_id, name, aliases, unit, price_cents, stock_milli, "
                    " low_stock_milli, quick, unlimited_stock, kind, category, "
                    " duration_minutes, image_url) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (pid, tenant_id, p["name"], p["aliases"], p["unit"],
                     p["price_cents"], p["stock_milli"], p["low_stock_milli"],
                     bool(p["quick"]), bool(p["unlimited_stock"]), p["kind"],
                     p["category"], p["duration_minutes"], p["image_url"]),
                )
        conn.commit()

    # -- fiado_customers -----------------------------------------------------
    customers = db.execute(
        "SELECT * FROM fiado_customers WHERE store_id = ? ORDER BY id",
        (store_row["id"],),
    ).fetchall()
    counts["fiado_customers"] = len(customers)
    customer_ids: dict[int, uuid.UUID] = {}
    if customers:
        with conn.cursor() as cur:
            for c in customers:
                cid = did("fiado_customer", slug, str(c["id"]))
                customer_ids[int(c["id"])] = cid
                cur.execute(
                    "INSERT INTO fiado_customers "
                    "(id, tenant_id, name, phone, active, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (cid, tenant_id, c["name"], c["phone"], True,
                     ts(c["created_at"])),
                )
        conn.commit()

    # -- sales ---------------------------------------------------------------
    sales = db.execute(
        "SELECT * FROM sales WHERE store_id = ? ORDER BY id",
        (store_row["id"],),
    ).fetchall()
    counts["sales"] = len(sales)
    sale_ids: dict[str, uuid.UUID] = {}
    if sales:
        with conn.cursor() as cur:
            for s in sales:
                sid = did("sale", slug, str(s["id"]))
                sale_ids[str(s["id"])] = sid
                cur.execute(
                    "INSERT INTO sales "
                    "(id, tenant_id, store_id, employee_id, status, payment_method, "
                    " total_cents, charged_cents, cash_received_cents, change_cents, "
                    " customer_id, pey_qr_id, pey_tx_id, paid_at, expires_at, note, "
                    " created_at, occurred_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "        %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (sid, tenant_id, store_uuid,
                     user_ids.get(int(s["employee_id"])), s["status"],
                     s["payment_method"], s["total_cents"], s["charged_cents"],
                     s["cash_received_cents"], s["change_cents"],
                     customer_ids.get(int(s["customer_id"])) if s["customer_id"] is not None else None,
                     s["pey_qr_id"], s["pey_tx_id"], ts(s["paid_at"]),
                     ts(s["expires_at"]), s["note"], ts(s["created_at"]),
                     ts(s["created_at"])),
                )
        conn.commit()

    # -- sale_items ----------------------------------------------------------
    items = db.execute("SELECT * FROM sale_items ORDER BY id").fetchall()
    counts["sale_items"] = len(items)
    if items:
        with conn.cursor() as cur:
            for it in items:
                cur.execute(
                    "INSERT INTO sale_items "
                    "(id, tenant_id, sale_id, product_id, name, unit, qty_milli, "
                    " unit_price_cents, line_total_cents) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (did("sale_item", slug, str(it["id"])), tenant_id,
                     sale_ids.get(str(it["sale_id"])),
                     product_ids.get(int(it["product_id"])),
                     it["name"], it["unit"], it["qty_milli"],
                     it["unit_price_cents"], it["line_total_cents"]),
                )
        conn.commit()

    # -- payments ------------------------------------------------------------
    pays = db.execute("SELECT * FROM payments ORDER BY tx_id").fetchall()
    counts["payments"] = len(pays)
    if pays:
        with conn.cursor() as cur:
            for p in pays:
                cur.execute(
                    "INSERT INTO payments "
                    "(id, tenant_id, tx_id, sale_id, amount_cents, method, source, "
                    " applied, received_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tx_id) DO NOTHING",
                    (did("payment", slug, str(p["tx_id"])), tenant_id,
                     p["tx_id"], sale_ids.get(str(p["sale_id"])),
                     p["amount_cents"], p["method"], p["source"],
                     bool(p["applied"]), ts(p["received_at"])),
                )
        conn.commit()

    # -- inventory_movements -------------------------------------------------
    moves = db.execute("SELECT * FROM inventory_movements ORDER BY id").fetchall()
    counts["inventory_movements"] = len(moves)
    if moves:
        with conn.cursor() as cur:
            for m in moves:
                cur.execute(
                    "INSERT INTO inventory_movements "
                    "(id, tenant_id, product_id, delta_milli, reason, sale_id, "
                    " employee_id, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (did("inventory_movement", slug, str(m["id"])), tenant_id,
                     product_ids.get(int(m["product_id"])), m["delta_milli"],
                     m["reason"],
                     sale_ids.get(str(m["sale_id"])) if m["sale_id"] is not None else None,
                     user_ids.get(int(m["employee_id"])) if m["employee_id"] is not None else None,
                     ts(m["created_at"])),
                )
        conn.commit()

    # -- fiado_entries -------------------------------------------------------
    entries = db.execute("SELECT * FROM fiado_entries ORDER BY id").fetchall()
    counts["fiado_entries"] = len(entries)
    if entries:
        with conn.cursor() as cur:
            for e in entries:
                cur.execute(
                    "INSERT INTO fiado_entries "
                    "(id, tenant_id, customer_id, sale_id, kind, amount_cents, note, "
                    " employee_id, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (did("fiado_entry", slug, str(e["id"])), tenant_id,
                     customer_ids.get(int(e["customer_id"])),
                     sale_ids.get(str(e["sale_id"])) if e["sale_id"] is not None else None,
                     e["kind"], e["amount_cents"], e["note"],
                     user_ids.get(int(e["employee_id"])) if e["employee_id"] is not None else None,
                     ts(e["created_at"])),
                )
        conn.commit()

    # -- expenses ------------------------------------------------------------
    exps = db.execute(
        "SELECT * FROM expenses WHERE store_id = ? ORDER BY id",
        (store_row["id"],),
    ).fetchall()
    counts["expenses"] = len(exps)
    if exps:
        with conn.cursor() as cur:
            for x in exps:
                cur.execute(
                    "INSERT INTO expenses (id, tenant_id, employee_id, amount_cents, note, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (did("expense", slug, str(x["id"])), tenant_id,
                     user_ids.get(int(x["employee_id"])) if x["employee_id"] is not None else None,
                     x["amount_cents"], x["note"], ts(x["created_at"])),
                )
        conn.commit()

    # -- day_tasks -----------------------------------------------------------
    tasks = db.execute(
        "SELECT * FROM day_tasks WHERE store_id = ? ORDER BY id",
        (store_row["id"],),
    ).fetchall()
    counts["day_tasks"] = len(tasks)
    if tasks:
        with conn.cursor() as cur:
            for t in tasks:
                cur.execute(
                    "INSERT INTO day_tasks "
                    "(id, tenant_id, key, title, assigned_employee_id, active) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, key) DO NOTHING",
                    (did("day_task", slug, str(t["id"])), tenant_id,
                     t["key"], t["title"],
                     user_ids.get(int(t["assigned_employee_id"])) if t["assigned_employee_id"] is not None else None,
                     bool(t["active"])),
                )
        conn.commit()

    # -- store_settings (onboarding answers) ---------------------------------
    settings = db.execute(
        "SELECT * FROM store_settings WHERE store_id = ?", (store_row["id"],)
    ).fetchall()
    counts["store_settings"] = len(settings)
    if settings:
        with conn.cursor() as cur:
            for st in settings:
                cur.execute(
                    "INSERT INTO store_settings "
                    "(id, tenant_id, store_id, business_type, owner_name) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id) DO NOTHING",
                    (did("store_settings", slug), tenant_id, store_uuid,
                     st["business_type"], st["owner_name"]),
                )
        conn.commit()

    # -- barcodes ------------------------------------------------------------
    barcodes = db.execute("SELECT * FROM barcodes ORDER BY code").fetchall()
    counts["barcodes"] = len(barcodes)
    if barcodes:
        with conn.cursor() as cur:
            for bc in barcodes:
                cur.execute(
                    "INSERT INTO barcodes (id, tenant_id, code, product_id) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, code) DO NOTHING",
                    (did("barcode", slug, str(bc["code"])), tenant_id,
                     bc["code"], product_ids.get(int(bc["product_id"]))),
                )
        conn.commit()

    # -- webhook_events (PEY webhook dedup) ----------------------------------
    webhooks = db.execute("SELECT * FROM webhook_events ORDER BY webhook_id").fetchall()
    counts["webhook_events"] = len(webhooks)
    if webhooks:
        with conn.cursor() as cur:
            for w in webhooks:
                cur.execute(
                    "INSERT INTO webhook_events "
                    "(id, tenant_id, webhook_id, received_at, outcome) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (webhook_id) DO NOTHING",
                    (did("webhook_event", slug, str(w["webhook_id"])), tenant_id,
                     w["webhook_id"], ts(w["received_at"]), w["outcome"]),
                )
        conn.commit()

    # -- support_tickets -----------------------------------------------------
    tickets = db.execute(
        "SELECT * FROM support_tickets WHERE store_id = ? ORDER BY id",
        (store_row["id"],),
    ).fetchall()
    counts["support_tickets"] = len(tickets)
    if tickets:
        with conn.cursor() as cur:
            for tk in tickets:
                cur.execute(
                    "INSERT INTO support_tickets "
                    "(id, tenant_id, sale_id, note, status, created_at, resolved_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    (did("support_ticket", slug, str(tk["id"])), tenant_id,
                     sale_ids.get(str(tk["sale_id"])) if tk["sale_id"] is not None else None,
                     tk["note"], tk["status"], ts(tk["created_at"]),
                     ts(tk["resolved_at"])),
                )
        conn.commit()

    db.close()
    return counts, slug, tenant_id, store_row["id"]


# --- Reporting -------------------------------------------------------------

STORE_FILTERED = (
    "products", "sales", "fiado_customers", "expenses", "day_tasks",
    "store_settings", "support_tickets",
)

BUSINESS_PG_TABLES = [
    "products", "sales", "sale_items", "payments", "inventory_movements",
    "fiado_customers", "fiado_entries", "fiado_drafts", "expenses",
    "day_tasks", "bank_accounts", "purchase_orders", "receipts",
    "till_shifts", "outbox_applied",
    "webhook_events", "barcodes", "store_settings", "support_tickets",
]

# v2 tables superseded by the tenancy schema; intentionally not migrated.
DROPPED_TABLES = ["invites"]


def report(conn, *, source: Path, store_id: str, slug: str,
           tenant_id: uuid.UUID | None) -> int:
    """Print the SQLite vs PostgreSQL per-table count reconciliation."""

    db = open_sqlite(source)
    store_row = db.execute("SELECT id FROM stores WHERE id = ?",
                           (store_id,)).fetchone()
    if store_row is None:
        store_row = db.execute("SELECT id FROM stores LIMIT 1").fetchone()
    sstore = store_row["id"] if store_row else store_id

    rows: list[tuple[str, str, str, str]] = []
    rows.append(("stores", str(sqlite_count(db, "stores")), "-", "-"))

    emp_n = sqlite_count(db, "employees", sstore)
    rows.append(("users (legacy)", str(emp_n), "-", "-"))
    rows.append(("memberships", str(emp_n), "-", "-"))

    for t in BUSINESS_PG_TABLES:
        sql_n = sqlite_count(db, t, sstore if t in STORE_FILTERED else None)
        rows.append((t, str(sql_n), "-", "-"))

    for t in DROPPED_TABLES:
        rows.append((f"{t} (dropped, superseded)", str(sqlite_count(db, t)), "-", "-"))

    db.close()

    if tenant_id is not None:
        resolved = []
        for label, sql_n, _, _ in rows:
            if label == "users (legacy)":
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM users u JOIN memberships m ON m.user_id = u.id "
                        "WHERE m.tenant_id = %s AND u.idp = 'legacy'", (tenant_id,))
                    pg_n = int(cur.fetchone()[0])
            elif label == "memberships":
                pg_n = pg_count(conn, "memberships", tenant_id)
            elif label in ("stores",):
                pg_n = pg_count(conn, "stores", tenant_id)
            elif label in BUSINESS_PG_TABLES:
                pg_n = pg_count(conn, label, tenant_id)
            else:
                pg_n = None
            diff = "-" if pg_n is None else str(int(sql_n) - int(pg_n)) if sql_n.isdigit() else "-"
            resolved.append((label, sql_n, str(pg_n) if pg_n is not None else "-", diff))
        rows = resolved

    # Print table.
    print(f"{'Table':<30} {'SQLite':>10} {'Postgres':>10} {'Diff':>8}")
    print("-" * 62)
    ok = True
    for label, sql_n, pg_n, diff in rows:
        print(f"{label:<30} {sql_n:>10} {pg_n:>10} {diff:>8}")
        if diff not in ("-", "0"):
            ok = False
    print("-" * 62)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.apply and not args.dry_run:
        args.dry_run = True

    # Resolve the demo tenant slug (must match what --apply would use).
    db = open_sqlite(args.source)
    store_row = db.execute("SELECT id, name FROM stores WHERE id = ?",
                           (args.store_id,)).fetchone()
    if store_row is None:
        store_row = db.execute("SELECT id, name FROM stores LIMIT 1").fetchone()
    if store_row is None:
        db.close()
        raise SystemExit("SQLite source has no stores row to migrate")
    slug = args.tenant_slug or store_row["id"] or "tiendita-esquina"
    db.close()

    if args.apply:
        conn = connect_pg(args.dsn)
        try:
            counts, slug, tenant_id, _ = migrate(
                conn, source=args.source, schema=args.schema,
                store_id=args.store_id, tenant_slug=slug,
                tenant_name=args.tenant_name,
            )
        finally:
            conn.close()
        conn = connect_pg(args.dsn)
        try:
            rc = report(conn, source=args.source, store_id=args.store_id,
                        slug=slug, tenant_id=tenant_id)
        finally:
            conn.close()
        return rc

    # --dry-run (read-only)
    conn = None
    tenant_id = None
    try:
        conn = connect_pg(args.dsn)
        tenant_id = pg_tenant_id(conn, slug)
    except Exception as exc:  # PG unavailable: still report SQLite side.
        print(f"[dry-run] PostgreSQL not reachable, showing SQLite counts only: {exc}",
              file=sys.stderr)
    try:
        return report(conn, source=args.source, store_id=args.store_id,
                      slug=slug, tenant_id=tenant_id)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
