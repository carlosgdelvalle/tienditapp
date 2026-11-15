"""SQLite schema, per-request connections and the v1 seed.

The database uses one connection per request, WAL, a 5 second busy timeout and
foreign keys. Writes that must serialize (sales, payments, webhooks, stock
adjustments) open `BEGIN IMMEDIATE` transactions through
`write_transaction`.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

STORE_ID = "tiendita-esquina"
# v3: the demo is generic; existing databases keep the name the owner saved.
STORE_NAME = "Mi negocio"

# v2 defaults for store_settings. The visible store name lives in stores.name;
# business_type and owner_name are the onboarding answers.
DEFAULT_BUSINESS_TYPE = ""
DEFAULT_OWNER_NAME = "Doña Rosa"

# v2: a brand new database starts with the owner only. Existing databases keep
# every employee with history; the additive migrations below never delete rows.
SEED_EMPLOYEES = [
    (1, "Doña Rosa", "owner"),
]

# v3 catalog: units and kinds accepted by products. The unit list only grows,
# so every v1/v2 database is rebuilt once (copy rows, drop, rename, indexes).
PRODUCT_UNITS = (
    "pieza",
    "kg",
    "g",
    "litro",
    "servicio",
    "sesion",
    "turno",
    "minuto",
    "hora",
    "paquete",
    "combo",
)
PRODUCT_KINDS = ("producto", "servicio", "platillo")

# Columns added to employees by v2. Each one is added only when missing.
EMPLOYEE_MIGRATIONS = (
    ("nickname", "TEXT"),
    ("can_sell", "INTEGER NOT NULL DEFAULT 1"),
    ("can_fiado", "INTEGER NOT NULL DEFAULT 1"),
    ("can_inventory", "INTEGER NOT NULL DEFAULT 0"),
)

# id, name, unit, price_cents, stock_milli, low_stock_milli, quick, aliases
SEED_PRODUCTS = [
    (
        1,
        "Coca-Cola 600 ml",
        "pieza",
        1800,
        24000,
        5000,
        1,
        ["coca", "cocas", "coca cola", "coca-cola", "coche", "coches", "refresco", "refrescos"],
    ),
    (
        2,
        "Sabritas sal 45 g",
        "pieza",
        2200,
        18000,
        5000,
        1,
        ["sabritas", "sabrita", "papas", "papas sabritas", "sabritas sal"],
    ),
    (
        3,
        "Pan Bimbo grande",
        "pieza",
        4800,
        6000,
        5000,
        1,
        ["pan", "bimbo", "pan bimbo", "pan grande", "panes"],
    ),
    (
        4,
        "Huevo (kg)",
        "kg",
        4500,
        10000,
        5000,
        1,
        ["huevo", "huevos", "blanquillos"],
    ),
    (
        5,
        "Leche Lala 1 L",
        "pieza",
        3100,
        12000,
        5000,
        1,
        ["leche", "lala", "leche lala"],
    ),
    (
        6,
        "Agua Bonafont 1 L",
        "pieza",
        1500,
        20000,
        5000,
        1,
        ["agua", "bonafont", "agua bonafont"],
    ),
    (
        7,
        "Maruchan camarón",
        "pieza",
        1600,
        30000,
        5000,
        1,
        ["maruchan", "maruchan camaron", "ramen", "sopa"],
    ),
    (
        8,
        "Gansito",
        "pieza",
        1700,
        15000,
        5000,
        1,
        ["gansito", "gansitos"],
    ),
    (
        9,
        "Tortillas (kg)",
        "kg",
        2600,
        8000,
        5000,
        0,
        ["tortilla", "tortillas"],
    ),
    (
        10,
        "Jabón Zote",
        "pieza",
        2300,
        9000,
        5000,
        0,
        ["jabon", "jabón", "zote", "jabon zote"],
    ),
    (
        11,
        "Galletas Marías",
        "pieza",
        1900,
        14000,
        5000,
        0,
        ["galletas", "galleta", "marias", "galletas marias"],
    ),
    (
        12,
        "Fanta 600 ml",
        "pieza",
        1700,
        12000,
        5000,
        0,
        ["fanta", "fanta 600", "naranja"],
    ),
]

SEED_BARCODES = [
    ("7500000000001", 1),
    ("7500000000002", 2),
    ("7500000000003", 3),
    ("7500000000004", 4),
    ("7500000000005", 5),
]

# v3 products body: one source of truth for new databases and for the table
# rebuild that widens the unit CHECK. The unit list is generated from
# PRODUCT_UNITS so both paths can never drift apart.
_PRODUCT_UNITS_SQL = ",".join(f"'{unit}'" for unit in PRODUCT_UNITS)
_PRODUCT_KINDS_SQL = ",".join(f"'{kind}'" for kind in PRODUCT_KINDS)
PRODUCTS_TABLE_BODY = f"""
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    unit TEXT NOT NULL CHECK(unit IN ({_PRODUCT_UNITS_SQL})),
    price_cents INTEGER NOT NULL,
    stock_milli INTEGER NOT NULL,
    low_stock_milli INTEGER NOT NULL DEFAULT 5000,
    quick INTEGER NOT NULL DEFAULT 0,
    unlimited_stock INTEGER NOT NULL DEFAULT 0 CHECK(unlimited_stock IN (0,1)),
    kind TEXT NOT NULL DEFAULT 'producto' CHECK(kind IN ({_PRODUCT_KINDS_SQL})),
    category TEXT,
    duration_minutes INTEGER
"""

# Tables only. Indexes live in INDEXES_SQL and run *after* the products table
# migration, because a legacy table does not have the v3 columns yet.
TABLES_SQL = f"""
CREATE TABLE IF NOT EXISTS stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    nickname TEXT,
    role TEXT NOT NULL CHECK(role IN ('owner','employee')),
    active INTEGER NOT NULL DEFAULT 1,
    can_sell INTEGER NOT NULL DEFAULT 1,
    can_fiado INTEGER NOT NULL DEFAULT 1,
    can_inventory INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invites (
    token TEXT PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS store_settings (
    store_id TEXT PRIMARY KEY REFERENCES stores(id),
    business_type TEXT NOT NULL DEFAULT '',
    owner_name TEXT NOT NULL DEFAULT 'Doña Rosa'
);

CREATE TABLE IF NOT EXISTS products ({PRODUCTS_TABLE_BODY});

CREATE TABLE IF NOT EXISTS barcodes (
    code TEXT PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS fiado_customers (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    phone TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    created_at REAL NOT NULL,
    status TEXT NOT NULL,
    payment_method TEXT NOT NULL CHECK(payment_method IN ('cash','pey','fiado')),
    total_cents INTEGER NOT NULL,
    charged_cents INTEGER NOT NULL,
    cash_received_cents INTEGER,
    change_cents INTEGER,
    customer_id INTEGER REFERENCES fiado_customers(id),
    pey_qr_id TEXT UNIQUE,
    pey_tx_id TEXT,
    paid_at REAL,
    expires_at REAL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY,
    sale_id TEXT NOT NULL REFERENCES sales(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    qty_milli INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    line_total_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    tx_id TEXT PRIMARY KEY,
    sale_id TEXT NOT NULL REFERENCES sales(id),
    amount_cents INTEGER NOT NULL,
    method TEXT NOT NULL,
    source TEXT NOT NULL,
    applied INTEGER NOT NULL DEFAULT 1,
    received_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    delta_milli INTEGER NOT NULL,
    reason TEXT NOT NULL,
    sale_id TEXT REFERENCES sales(id),
    employee_id INTEGER REFERENCES employees(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fiado_entries (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES fiado_customers(id),
    sale_id TEXT REFERENCES sales(id),
    kind TEXT NOT NULL CHECK(kind IN ('charge','payment')),
    amount_cents INTEGER NOT NULL,
    note TEXT,
    employee_id INTEGER REFERENCES employees(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_events (
    webhook_id TEXT PRIMARY KEY,
    received_at REAL NOT NULL,
    outcome TEXT NOT NULL
);

-- v2 support tickets: the person in the store reports a charge that was not
-- confirmed. The sale context (status, totals, PEY tx id) is read live from
-- sales when the ticket is serialized; a ticket without a sale only has a note.
CREATE TABLE IF NOT EXISTS support_tickets (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    sale_id TEXT REFERENCES sales(id),
    note TEXT,
    status TEXT NOT NULL CHECK(status IN ('open','resolved')),
    created_at REAL NOT NULL,
    resolved_at REAL
);

-- v3 fixed day tasks per business type. A template creates them unassigned;
-- an employee only lists the tasks assigned to them and active.
CREATE TABLE IF NOT EXISTS day_tasks (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    key TEXT NOT NULL,
    title TEXT NOT NULL,
    assigned_employee_id INTEGER REFERENCES employees(id),
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(store_id, key)
);

-- v3 simple expenses: amount in cents, optional note, who registered it.
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    employee_id INTEGER REFERENCES employees(id),
    amount_cents INTEGER NOT NULL,
    note TEXT,
    created_at REAL NOT NULL
);
"""

# Re-running this script is safe (IF NOT EXISTS) and it is what puts the
# indexes back after the products table is rebuilt.
INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_sales_store_created ON sales(store_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sales_qr ON sales(pey_qr_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_payments_sale ON payments(sale_id);
CREATE INDEX IF NOT EXISTS idx_movements_product ON inventory_movements(product_id, created_at);
CREATE INDEX IF NOT EXISTS idx_fiado_entries_customer ON fiado_entries(customer_id, created_at);
CREATE INDEX IF NOT EXISTS idx_support_tickets_sale ON support_tickets(sale_id);
CREATE INDEX IF NOT EXISTS idx_products_store ON products(store_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(store_id, category);
CREATE INDEX IF NOT EXISTS idx_products_kind ON products(store_id, kind);
CREATE INDEX IF NOT EXISTS idx_day_tasks_store ON day_tasks(store_id, active);
CREATE INDEX IF NOT EXISTS idx_expenses_store_created ON expenses(store_id, created_at);
"""

# Backwards-compatible alias: tests and scripts that build a database from
# scratch keep importing SCHEMA. Production initialization runs the two parts
# separately (tables, migration, then indexes).
SCHEMA = TABLES_SQL + INDEXES_SQL


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a fresh connection with the required pragmas.

    Every request gets its own connection; nothing is shared globally.
    """

    conn = sqlite3.connect(
        str(db_path),
        timeout=5.0,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a serialized write transaction.

    `BEGIN IMMEDIATE` takes the write lock up front, so two concurrent cash
    sales or webhooks cannot read-modify-write the same row on stale data.
    A short retry loop covers the rare case where SQLite reports a busy/locked
    database after the busy_timeout has already elapsed.
    """

    deadline = time.monotonic() + 5.0
    while True:
        try:
            conn.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and time.monotonic() < deadline:
                time.sleep(0.02)
                continue
            raise
    try:
        yield conn
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    else:
        conn.execute("COMMIT")


def initialize_db(db_path: str | Path, *, seed_catalog: bool = False) -> None:
    """Create the schema, migrate additively and seed the demo store once.

    seed_catalog=False leaves the catalog empty for a new store: the Android
    onboarding applies the template of the chosen business type once. Tests
    pass seed_catalog=True to keep the historical demo catalog.
    """

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.executescript(TABLES_SQL)
        _migrate_products(conn)
        with write_transaction(conn):
            # v2 additive migration for employees: never drops existing rows.
            employee_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(employees)")
            }
            for column, ddl in EMPLOYEE_MIGRATIONS:
                if column not in employee_columns:
                    conn.execute(f"ALTER TABLE employees ADD COLUMN {column} {ddl}")
            existing = conn.execute("SELECT COUNT(*) AS n FROM stores").fetchone()["n"]
            if not existing:
                _seed(conn, seed_catalog=seed_catalog)
            # One settings row per store; keeps onboarding answers and never
            # overwrites what the owner already saved.
            conn.execute(
                """INSERT OR IGNORE INTO store_settings
                       (store_id, business_type, owner_name)
                   SELECT id, ?, ? FROM stores WHERE id = ?""",
                (DEFAULT_BUSINESS_TYPE, DEFAULT_OWNER_NAME, STORE_ID),
            )
            # Add the requested demo product once, preserving existing prices,
            # stock balances and sale history on subsequent starts. A brand-new
            # store with seed_catalog=False keeps an empty catalog so the v3
            # business template applies exactly once.
            product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            if seed_catalog or product_count > 0:
                conn.execute(
                    """INSERT INTO products
                       (store_id,name,aliases,unit,price_cents,stock_milli,
                        low_stock_milli,quick,unlimited_stock)
                       SELECT ?, ?, ?, 'pieza', 2000, 0, 0, 1, 1
                       WHERE EXISTS (SELECT 1 FROM stores WHERE id = ?)
                         AND NOT EXISTS (SELECT 1 FROM products
                                         WHERE store_id = ? AND name = ? COLLATE NOCASE)""",
                    (STORE_ID, "Tacos de pastor", json.dumps([
                        "de pastor", "al pastor", "taco de pastor", "tacos al pastor", "taco al pastor",
                    ]), STORE_ID, STORE_ID, "Tacos de pastor"),
                )
        # Indexes run last: the v3 products rebuild drops the ones that lived
        # on the old table, and this script puts every index back. Idempotent.
        conn.executescript(INDEXES_SQL)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# v3 migration: widen products.unit CHECK by rebuilding the table
# ---------------------------------------------------------------------------

def _products_columns(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(products)")}


def _products_table_sql(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'products'"
    ).fetchone()
    return None if row is None else str(row["sql"] or "")


def _products_need_rebuild(conn: sqlite3.Connection) -> bool:
    """True when the products table still has the v1/v2 unit CHECK.

    The table must be recreated to widen a CHECK constraint in SQLite. The
    v3 columns kind/category/duration_minutes ride along in the same rebuild,
    which keeps the migration a single copy of the data.
    """

    table_sql = _products_table_sql(conn)
    if table_sql is None:
        return False
    columns = _products_columns(conn)
    if "unlimited_stock" not in columns:
        return True
    if not {"kind", "category", "duration_minutes"} <= columns:
        return True
    return any(f"'{unit}'" not in table_sql for unit in PRODUCT_UNITS)


def _migrate_products(conn: sqlite3.Connection) -> None:
    """Additive, idempotent migration of the products table.

    Foreign keys are disabled only around the rebuild: dropping the old table
    while barcodes/sale_items/inventory_movements point at it would otherwise
    fail. The data is copied row by row, ids and history are preserved, and
    the caller re-creates the indexes afterwards.
    """

    if not _products_need_rebuild(conn):
        return
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        with write_transaction(conn):
            _rebuild_products_table(conn)
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def _rebuild_products_table(conn: sqlite3.Connection) -> None:
    columns = _products_columns(conn)
    copied = (
        "id",
        "store_id",
        "name",
        "aliases",
        "unit",
        "price_cents",
        "stock_milli",
        "low_stock_milli",
        "quick",
        "unlimited_stock",
        "kind",
        "category",
        "duration_minutes",
    )
    defaults = {
        "aliases": "'[]'",
        "low_stock_milli": "5000",
        "quick": "0",
        "unlimited_stock": "0",
        "kind": "'producto'",
        "category": "NULL",
        "duration_minutes": "NULL",
    }
    targets: list[str] = []
    sources: list[str] = []
    for column in copied:
        if column in columns:
            targets.append(column)
            sources.append(column)
        elif column in defaults:
            targets.append(column)
            sources.append(defaults[column])
        else:
            raise RuntimeError(f"products sin columna obligatoria: {column}")
    # A crashed migration must not leave a half table behind.
    conn.execute("DROP TABLE IF EXISTS products_new")
    conn.execute(f"CREATE TABLE products_new ({PRODUCTS_TABLE_BODY})")
    conn.execute(
        f"INSERT INTO products_new ({', '.join(targets)}) "
        f"SELECT {', '.join(sources)} FROM products"
    )
    conn.execute("DROP TABLE products")
    conn.execute("ALTER TABLE products_new RENAME TO products")



def _seed(conn: sqlite3.Connection, *, seed_catalog: bool = False) -> None:
    conn.execute(
        "INSERT INTO stores (id, name) VALUES (?, ?)",
        (STORE_ID, STORE_NAME),
    )
    for employee_id, name, role in SEED_EMPLOYEES:
        conn.execute(
            "INSERT INTO employees (id, store_id, name, role, active) VALUES (?, ?, ?, ?, 1)",
            (employee_id, STORE_ID, name, role),
        )
    if not seed_catalog:
        return
    for (
        product_id,
        name,
        unit,
        price_cents,
        stock_milli,
        low_stock_milli,
        quick,
        aliases,
    ) in SEED_PRODUCTS:
        conn.execute(
            """INSERT INTO products
               (id, store_id, name, aliases, unit, price_cents, stock_milli,
                low_stock_milli, quick)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product_id,
                STORE_ID,
                name,
                json.dumps(aliases, ensure_ascii=False),
                unit,
                price_cents,
                stock_milli,
                low_stock_milli,
                quick,
            ),
        )
    for code, product_id in SEED_BARCODES:
        conn.execute(
            "INSERT INTO barcodes (code, product_id) VALUES (?, ?)",
            (code, product_id),
        )


def store_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, name FROM stores WHERE id = ?", (STORE_ID,)
    ).fetchone()


def store_settings_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT store_id, business_type, owner_name FROM store_settings WHERE store_id = ?",
        (STORE_ID,),
    ).fetchone()
