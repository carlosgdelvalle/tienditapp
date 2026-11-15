"""v2 schema migrations are additive, idempotent and never delete employees."""

from __future__ import annotations

import sqlite3

from server.db import initialize_db

LEGACY_SCHEMA = """
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
"""


def build_legacy_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO stores (id, name) VALUES ('tiendita-esquina', 'Tiendita vieja')"
        )
        conn.execute(
            "INSERT INTO employees (id, store_id, name, role, active) VALUES (1, 'tiendita-esquina', 'Doña Rosa', 'owner', 1)"
        )
        conn.execute(
            "INSERT INTO employees (id, store_id, name, role, active) VALUES (2, 'tiendita-esquina', 'Lupita', 'employee', 1)"
        )
        conn.execute(
            """INSERT INTO products
                   (id, store_id, name, unit, price_cents, stock_milli)
               VALUES (42, 'tiendita-esquina', 'Producto viejo', 'pieza', 123, 7000)"""
        )
        conn.commit()
    finally:
        conn.close()


def test_legacy_database_keeps_employees_and_gets_new_columns(tmp_path):
    path = tmp_path / "legacy-v2.db"
    build_legacy_db(path)

    initialize_db(path)
    initialize_db(path)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(employees)")}
        assert {"nickname", "can_sell", "can_fiado", "can_inventory"} <= columns

        employees = conn.execute(
            "SELECT id, name, role, active, nickname, can_sell, can_fiado, can_inventory "
            "FROM employees ORDER BY id"
        ).fetchall()
        # Existing employees with history are never deleted nor reseeded.
        assert [(row["id"], row["name"], row["role"]) for row in employees] == [
            (1, "Doña Rosa", "owner"),
            (2, "Lupita", "employee"),
        ]
        assert employees[1]["active"] == 1
        assert employees[1]["nickname"] is None
        assert (employees[1]["can_sell"], employees[1]["can_fiado"]) == (1, 1)
        assert employees[1]["can_inventory"] == 0

        settings = conn.execute(
            "SELECT business_type, owner_name FROM store_settings WHERE store_id = 'tiendita-esquina'"
        ).fetchone()
        assert tuple(settings) == ("", "Doña Rosa")

        # The new tables are usable after the migration.
        token = "a" * 32
        conn.execute(
            "INSERT INTO invites (token, employee_id, created_at, expires_at, accepted) "
            "VALUES (?, 2, 1.0, 2.0, 0)",
            (token,),
        )
        assert conn.execute(
            "SELECT employee_id FROM invites WHERE token = ?", (token,)
        ).fetchone()[0] == 2

        # The store name is preserved; only new products are appended once.
        assert conn.execute(
            "SELECT name FROM stores WHERE id = 'tiendita-esquina'"
        ).fetchone()[0] == "Tiendita vieja"
        assert conn.execute(
            "SELECT COUNT(*) FROM products WHERE name = 'Tacos de pastor'"
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 2


def test_new_database_seed_is_idempotent(tmp_path):
    path = tmp_path / "nueva-v2.db"
    initialize_db(path)
    initialize_db(path)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0] == 1
        employees = conn.execute("SELECT id, name, role FROM employees ORDER BY id").fetchall()
        assert [(row["id"], row["name"], row["role"]) for row in employees] == [
            (1, "Doña Rosa", "owner")
        ]
        assert conn.execute("SELECT COUNT(*) FROM store_settings").fetchone()[0] == 1
