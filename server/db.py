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
STORE_NAME = "Tiendita de la Esquina"

SEED_EMPLOYEES = [
    (1, "Doña Rosa", "owner"),
    (2, "Lupita", "employee"),
    (3, "Toño", "employee"),
]

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('owner','employee')),
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    unit TEXT NOT NULL CHECK(unit IN ('pieza','kg')),
    price_cents INTEGER NOT NULL,
    stock_milli INTEGER NOT NULL,
    low_stock_milli INTEGER NOT NULL DEFAULT 5000,
    quick INTEGER NOT NULL DEFAULT 0
);

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

CREATE INDEX IF NOT EXISTS idx_sales_store_created ON sales(store_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sales_qr ON sales(pey_qr_id);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_payments_sale ON payments(sale_id);
CREATE INDEX IF NOT EXISTS idx_movements_product ON inventory_movements(product_id, created_at);
CREATE INDEX IF NOT EXISTS idx_fiado_entries_customer ON fiado_entries(customer_id, created_at);
"""


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


def initialize_db(db_path: str | Path) -> None:
    """Create the schema and seed the demo store exactly once."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        with write_transaction(conn):
            existing = conn.execute("SELECT COUNT(*) AS n FROM stores").fetchone()["n"]
            if existing:
                return
            _seed(conn)
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO stores (id, name) VALUES (?, ?)",
        (STORE_ID, STORE_NAME),
    )
    for employee_id, name, role in SEED_EMPLOYEES:
        conn.execute(
            "INSERT INTO employees (id, store_id, name, role, active) VALUES (?, ?, ?, ?, 1)",
            (employee_id, STORE_ID, name, role),
        )
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
