"""v3 migrations: the products table is rebuilt additively and stays idempotent."""

from __future__ import annotations

import sqlite3

import pytest

from server.db import PRODUCT_KINDS, PRODUCT_UNITS, initialize_db

LEGACY_V2_SCHEMA = """
CREATE TABLE stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('owner','employee')),
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    store_id TEXT NOT NULL REFERENCES stores(id),
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    unit TEXT NOT NULL CHECK(unit IN ('pieza','kg')),
    price_cents INTEGER NOT NULL,
    stock_milli INTEGER NOT NULL,
    low_stock_milli INTEGER NOT NULL DEFAULT 5000,
    quick INTEGER NOT NULL DEFAULT 0,
    unlimited_stock INTEGER NOT NULL DEFAULT 0 CHECK(unlimited_stock IN (0,1))
);
CREATE TABLE barcodes (
    code TEXT PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id)
);
CREATE TABLE sales (
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
    customer_id INTEGER,
    pey_qr_id TEXT UNIQUE,
    pey_tx_id TEXT,
    paid_at REAL,
    expires_at REAL,
    note TEXT
);
CREATE TABLE sale_items (
    id INTEGER PRIMARY KEY,
    sale_id TEXT NOT NULL REFERENCES sales(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    qty_milli INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    line_total_cents INTEGER NOT NULL
);
CREATE TABLE inventory_movements (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id),
    delta_milli INTEGER NOT NULL,
    reason TEXT NOT NULL,
    sale_id TEXT REFERENCES sales(id),
    employee_id INTEGER,
    created_at REAL NOT NULL
);
"""


def build_legacy_v2_db(path) -> None:
    """A v2 database with catalog, barcode, sale and inventory history."""

    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_V2_SCHEMA)
        conn.execute(
            "INSERT INTO stores (id, name) VALUES ('tiendita-esquina', 'Tiendita vieja')"
        )
        conn.execute(
            "INSERT INTO employees (id, store_id, name, role, active) "
            "VALUES (1, 'tiendita-esquina', 'Doña Rosa', 'owner', 1)"
        )
        conn.execute(
            "INSERT INTO employees (id, store_id, name, role, active) "
            "VALUES (2, 'tiendita-esquina', 'Lupita', 'employee', 1)"
        )
        conn.execute(
            """INSERT INTO products
                   (id, store_id, name, aliases, unit, price_cents, stock_milli,
                    low_stock_milli, quick, unlimited_stock)
               VALUES (42, 'tiendita-esquina', 'Producto viejo', '["viejo"]',
                       'pieza', 123, 7000, 5000, 0, 0)"""
        )
        conn.execute(
            """INSERT INTO products
                   (id, store_id, name, unit, price_cents, stock_milli)
               VALUES (43, 'tiendita-esquina', 'Tortilla vieja', 'kg', 2500, 9000)"""
        )
        conn.execute(
            "INSERT INTO barcodes (code, product_id) VALUES ('7500000000099', 42)"
        )
        conn.execute(
            """INSERT INTO sales
                   (id, store_id, employee_id, created_at, status, payment_method,
                    total_cents, charged_cents)
               VALUES ('sale_legacy', 'tiendita-esquina', 2, 1000.0,
                       'paid_cash', 'cash', 123, 123)"""
        )
        conn.execute(
            """INSERT INTO sale_items
                   (sale_id, product_id, name, unit, qty_milli,
                    unit_price_cents, line_total_cents)
               VALUES ('sale_legacy', 42, 'Producto viejo', 'pieza',
                       1000, 123, 123)"""
        )
        conn.execute(
            """INSERT INTO inventory_movements
                   (product_id, delta_milli, reason, sale_id, employee_id, created_at)
               VALUES (42, -1000, 'sale', 'sale_legacy', 2, 1000.0)"""
        )
        conn.commit()
    finally:
        conn.close()


def test_legacy_products_are_rebuilt_preserving_data(tmp_path):
    path = tmp_path / "legacy-v3.db"
    build_legacy_v2_db(path)

    initialize_db(path, seed_catalog=True)
    initialize_db(path, seed_catalog=True)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
        assert {"kind", "category", "duration_minutes"} <= columns
        assert {"unlimited_stock"} <= columns

        # Existing rows keep ids, prices, stock and history.
        old = conn.execute(
            "SELECT * FROM products WHERE id = 42"
        ).fetchone()
        assert (old["name"], old["unit"], old["price_cents"], old["stock_milli"]) == (
            "Producto viejo",
            "pieza",
            123,
            7000,
        )
        assert old["unlimited_stock"] == 0
        assert old["kind"] == "producto"
        assert old["category"] is None
        assert old["duration_minutes"] is None

        assert conn.execute(
            "SELECT COUNT(*) FROM barcodes WHERE code = '7500000000099' "
            "AND product_id = 42"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sale_items WHERE sale_id = 'sale_legacy'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM inventory_movements WHERE sale_id = 'sale_legacy'"
        ).fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        # The widened unit CHECK accepts the v3 units and the kind CHECK works.
        for unit in PRODUCT_UNITS:
            conn.execute(
                """INSERT INTO products
                       (store_id, name, unit, price_cents, stock_milli, kind)
                   VALUES ('tiendita-esquina', ?, ?, 100, 0, 'producto')""",
                (f"Unidad {unit}", unit),
            )
        for kind in PRODUCT_KINDS:
            conn.execute(
                """INSERT INTO products
                       (store_id, name, unit, price_cents, stock_milli, kind)
                   VALUES ('tiendita-esquina', ?, 'pieza', 100, 0, ?)""",
                (f"Tipo {kind}", kind),
            )
        inserted = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        assert inserted == 2 + 1 + len(PRODUCT_UNITS) + len(PRODUCT_KINDS)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO products
                       (store_id, name, unit, price_cents, stock_milli)
                   VALUES ('tiendita-esquina', 'Unidad mala', 'botella', 100, 0)"""
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO products
                       (store_id, name, unit, price_cents, stock_milli, kind)
                   VALUES ('tiendita-esquina', 'Tipo malo', 'pieza', 100, 0, 'otro')"""
            )

        # Indexes were re-created after the rebuild and there is only one table.
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "idx_products_store",
            "idx_products_category",
            "idx_products_kind",
            "idx_day_tasks_store",
            "idx_expenses_store_created",
        } <= indexes
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "products" in tables
        assert "products_new" not in tables
        assert {"day_tasks", "expenses"} <= tables

        # Existing stores keep their name; the default only applies to new ones.
        assert conn.execute(
            "SELECT name FROM stores WHERE id = 'tiendita-esquina'"
        ).fetchone()[0] == "Tiendita vieja"
        assert conn.execute(
            "SELECT COUNT(*) FROM products WHERE name = 'Tacos de pastor'"
        ).fetchone()[0] == 1

        # A third run is still idempotent (no rows added or lost). Commit first
        # so the migration does not fight this connection for the write lock.
        before = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        conn.commit()
        initialize_db(path, seed_catalog=True)
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == before

        conn.execute(
            """INSERT INTO day_tasks (store_id, key, title)
               VALUES ('tiendita-esquina', 'contar-inventario', 'Contar inventario')"""
        )
        conn.execute(
            """INSERT INTO expenses (store_id, employee_id, amount_cents, note, created_at)
               VALUES ('tiendita-esquina', NULL, 2000, 'gas', 1000.0)"""
        )


def test_new_database_uses_generic_name_and_keeps_seed_idempotent(tmp_path):
    path = tmp_path / "nueva-v3.db"
    initialize_db(path, seed_catalog=True)
    initialize_db(path, seed_catalog=True)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT name FROM stores").fetchone()["name"] == "Mi negocio"
        assert conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0] == 1
        products = conn.execute(
            "SELECT id, name, kind FROM products ORDER BY id"
        ).fetchall()
        assert len(products) == 13
        assert [row["id"] for row in products] == list(range(1, 14))
        assert {row["kind"] for row in products} == {"producto"}
        # Nothing is seeded twice and a new id is allocated on top of the seed.
        assert conn.execute(
            "SELECT COUNT(*) FROM products WHERE name = 'Tacos de pastor'"
        ).fetchone()[0] == 1
        conn.execute(
            """INSERT INTO products
                   (store_id, name, unit, price_cents, stock_milli, kind)
               VALUES ('tiendita-esquina', 'Servicio nuevo', 'servicio', 5000, 0, 'servicio')"""
        )
        assert conn.execute(
            "SELECT id FROM products WHERE name = 'Servicio nuevo'"
        ).fetchone()["id"] == 14
        assert conn.execute("SELECT COUNT(*) FROM day_tasks").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
