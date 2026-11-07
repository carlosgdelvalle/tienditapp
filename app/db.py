"""Base de datos SQLite: esquema y catálogo de la Tiendita de la Esquina (comercio ficticio)."""
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("TIENDITA_DB", str(Path(__file__).parent / "data" / "tiendita.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  aliases TEXT NOT NULL DEFAULT '[]',
  price_cents INTEGER NOT NULL,
  stock INTEGER NOT NULL DEFAULT 0,
  low_stock_at INTEGER NOT NULL DEFAULT 5,
  quick INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS employees (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner','employee'))
);
CREATE TABLE IF NOT EXISTS sales (
  id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  items TEXT NOT NULL,
  total_cents INTEGER NOT NULL,
  charged_cents INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','paid','expired','por_conciliar')),
  pey_qr_id TEXT UNIQUE,
  pey_tx_id TEXT,
  paid_at REAL,
  expires_at REAL NOT NULL,
  note TEXT
);
CREATE TABLE IF NOT EXISTS payments (
  tx_id TEXT PRIMARY KEY,
  sale_id TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  source TEXT NOT NULL,
  received_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS barcodes (
  code TEXT PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id)
);
CREATE TABLE IF NOT EXISTS webhook_events (
  webhook_id TEXT PRIMARY KEY,
  received_at REAL NOT NULL,
  outcome TEXT NOT NULL
);
"""

# (nombre, alias, precio en centavos, stock, botón rápido)
CATALOG = [
    ("Coca-Cola 600 ml", ["coca", "cocas", "coca cola", "coca-cola", "refresco de cola"], 1800, 24, 1),
    ("Sabritas sal 45 g", ["sabritas", "papas", "papitas", "sabrita"], 2200, 18, 1),
    ("Pan Bimbo grande", ["bimbo", "pan", "pan bimbo", "pan de caja"], 4800, 6, 1),
    ("Huevo (kg)", ["huevo", "huevos", "kilo de huevo"], 4500, 10, 1),
    ("Leche Lala 1 L", ["leche", "lala", "litro de leche"], 3100, 12, 1),
    ("Agua Bonafont 1 L", ["agua", "bonafont", "botella de agua"], 1500, 20, 1),
    ("Maruchan camarón", ["maruchan", "sopa", "sopa instantánea", "maruchanes"], 1600, 30, 1),
    ("Gansito", ["gansito", "gansitos"], 1700, 15, 1),
    ("Tortillas (kg)", ["tortillas", "tortilla", "kilo de tortillas"], 2600, 8, 0),
    ("Jabón Zote", ["zote", "jabón", "jabon"], 2300, 9, 0),
    ("Galletas Marías", ["marías", "marias", "galletas"], 1900, 14, 0),
    ("Fanta 600 ml", ["fanta", "refresco de naranja"], 1700, 12, 0),
]

EMPLOYEES = [(1, "Doña Rosa", "owner"), (2, "Lupita", "employee"), (3, "Toño", "employee")]


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO products(name, aliases, price_cents, stock, quick) VALUES (?,?,?,?,?)",
            [(n, json.dumps(a, ensure_ascii=False), p, s, q) for n, a, p, s, q in CATALOG],
        )
    if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
        conn.executemany("INSERT INTO employees(id, name, role) VALUES (?,?,?)", EMPLOYEES)
