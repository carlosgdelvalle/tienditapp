"""v3 migrations: the products table is rebuilt additively and stays idempotent."""

from __future__ import annotations

import sqlite3

import pytest

from server.db import PRODUCTS_TABLE_BODY, PRODUCT_KINDS, PRODUCT_UNITS, initialize_db

# v3.1: a real image URL shape (not fetched by any test, only stored/returned).
IMAGE_URL = (
    "https://images.openfoodfacts.org/images/products/"
    "750/105/532/0639/front_es.17.200.jpg"
)

# The v3 table as it was created before v3.1 (same body without image_url).
V3_WITHOUT_IMAGE_URL_BODY = PRODUCTS_TABLE_BODY.replace(",\n    image_url TEXT", "")

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


def test_legacy_rebuild_adds_the_v31_image_url_column(tmp_path):
    """A v1/v2 database is rebuilt once and gets image_url with NULL values."""

    path = tmp_path / "legacy-v31.db"
    build_legacy_v2_db(path)

    initialize_db(path, seed_catalog=True)
    initialize_db(path, seed_catalog=True)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(products)")]
        assert columns.count("image_url") == 1
        old = conn.execute(
            "SELECT name, price_cents, image_url FROM products WHERE id = 42"
        ).fetchone()
        assert (old["name"], old["price_cents"], old["image_url"]) == (
            "Producto viejo",
            123,
            None,
        )
        # The column is nullable and accepts a value without another migration.
        conn.execute("UPDATE products SET image_url = ? WHERE id = 42", (IMAGE_URL,))
        conn.commit()

    # Further starts are idempotent: no duplicate column, no row loss.
    initialize_db(path, seed_catalog=True)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(products)")]
        assert columns.count("image_url") == 1
        assert conn.execute(
            "SELECT image_url FROM products WHERE id = 42"
        ).fetchone()["image_url"] == IMAGE_URL
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 3
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_v3_database_without_image_url_gets_an_additive_column(tmp_path):
    """A database already rebuilt by v3 only needs ALTER TABLE, not a rebuild."""

    assert "image_url" not in V3_WITHOUT_IMAGE_URL_BODY
    path = tmp_path / "v3-sin-imagen.db"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            f"""
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
            CREATE TABLE products ({V3_WITHOUT_IMAGE_URL_BODY});
            """
        )
        conn.execute(
            "INSERT INTO stores (id, name) VALUES ('tiendita-esquina', 'Mi negocio')"
        )
        conn.execute(
            """INSERT INTO employees (id, store_id, name, role, active)
               VALUES (1, 'tiendita-esquina', 'Doña Rosa', 'owner', 1)"""
        )
        conn.execute(
            """INSERT INTO products
                   (id, store_id, name, aliases, unit, price_cents, stock_milli,
                    kind, category, duration_minutes)
               VALUES (7, 'tiendita-esquina', 'Servicio viejo', '[]', 'servicio',
                       5000, 0, 'servicio', 'Servicios', 30)"""
        )
        conn.commit()
    finally:
        conn.close()

    initialize_db(path, seed_catalog=False)
    initialize_db(path, seed_catalog=False)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(products)")]
        assert columns.count("image_url") == 1
        row = conn.execute(
            """SELECT name, kind, category, duration_minutes, image_url
               FROM products WHERE id = 7"""
        ).fetchone()
        assert tuple(row) == ("Servicio viejo", "servicio", "Servicios", 30, None)
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        # The column was added in place: no half-built table left behind.
        assert "products" in tables
        assert "products_new" not in tables
        conn.execute("UPDATE products SET image_url = ? WHERE id = 7", (IMAGE_URL,))
        conn.commit()
