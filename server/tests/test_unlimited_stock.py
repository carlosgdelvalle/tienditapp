"""Unlimited products retain stock and stay out of restock alerts; PEY is SIMULADO."""

import sqlite3

import pytest

from server.db import SCHEMA, initialize_db
from server.tests.conftest import create_customer, event_payload, post_webhook

pytestmark = pytest.mark.usefixtures("staff")


@pytest.mark.parametrize("method", ["cash", "fiado", "pey"])
def test_unlimited_sale_and_cancel_preserve_stock_and_audit(client, db, method):
    db.execute("UPDATE products SET stock_milli=0, unlimited_stock=1 WHERE id=1")
    db.commit()
    body = {
        "employeeId": 2,
        "items": [{"productId": 1, "qtyMilli": 50000}, {"productId": 2, "qtyMilli": 1000}],
        "paymentMethod": method,
    }
    if method == "cash":
        body["cashReceivedCents"] = 100000
    if method == "fiado":
        body["customerId"] = create_customer(client)["id"]
    response = client.post("/api/sales", json=body)
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["totalCents"] == 92200
    if method == "pey":
        payload = event_payload(sale["qrId"], "tx_sim_unlimited")
        assert post_webhook(client, payload, "evt_sim_unlimited").status_code == 200
        assert post_webhook(client, payload, "evt_sim_unlimited").status_code == 200
    assert db.execute("SELECT stock_milli FROM products WHERE id=1").fetchone()[0] == 0
    assert db.execute("SELECT stock_milli FROM products WHERE id=2").fetchone()[0] == 17000
    sale_movements = db.execute(
        "SELECT delta_milli FROM inventory_movements WHERE sale_id=? AND product_id=1",
        (sale["id"],),
    ).fetchall()
    assert [r[0] for r in sale_movements] == [-50000]
    canceled = client.post(f"/api/sales/{sale['id']}/cancel", json={"employeeId": 2})
    assert canceled.status_code == 200, canceled.text
    assert db.execute("SELECT stock_milli FROM products WHERE id=1").fetchone()[0] == 0
    assert db.execute("SELECT stock_milli FROM products WHERE id=2").fetchone()[0] == 18000
    movements = db.execute(
        "SELECT delta_milli FROM inventory_movements WHERE sale_id=? AND product_id=1 ORDER BY id",
        (sale["id"],),
    ).fetchall()
    assert [r[0] for r in movements] == [-50000, 50000]


def test_unlimited_is_visible_excluded_from_alerts_and_cannot_be_adjusted(client, db):
    db.execute("UPDATE products SET stock_milli=0, unlimited_stock=1 WHERE id=1")
    db.commit()
    products = client.get("/api/bootstrap").json()["products"]
    assert next(p for p in products if p["id"] == 1)["unlimitedStock"] is True
    low_stock = client.get("/api/reports/today").json()["lowStock"]
    assert all(p["id"] != 1 for p in low_stock)
    response = client.post("/api/inventory/adjust", json={
        "employeeId": 2, "productId": 1, "deltaMilli": -1000, "reason": "conteo",
    })
    assert response.status_code == 400
    assert db.execute("SELECT COUNT(*) FROM inventory_movements WHERE product_id=1").fetchone()[0] == 0


def test_legacy_database_migration_preserves_catalog(tmp_path):
    path = tmp_path / "legacy.db"
    column = ",\n    unlimited_stock INTEGER NOT NULL DEFAULT 0 CHECK(unlimited_stock IN (0,1))"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA.replace(column, ""))
        conn.execute("INSERT INTO stores VALUES ('tiendita-esquina', 'Existente')")
        conn.execute("INSERT INTO products (id,store_id,name,unit,price_cents,stock_milli) "
                     "VALUES (42,'tiendita-esquina','Existente','pieza',123,7000)")
    initialize_db(path)
    initialize_db(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id,price_cents,stock_milli,unlimited_stock FROM products WHERE id=42").fetchall() == [(42, 123, 7000, 0)]
        assert conn.execute("SELECT COUNT(*) FROM products WHERE name='Tacos de pastor'").fetchone()[0] == 1


@pytest.mark.parametrize("text", ["dos de pastor", "2 tacos de pastor", "dos al pastor"])
def test_pastor_aliases_use_catalog_price_and_unlimited_inventory(client, text):
    product = next(p for p in client.get('/api/bootstrap').json()['products'] if p['name'] == 'Tacos de pastor')
    assert product['priceCents'] == 2000
    assert product['unlimitedStock'] is True
    parsed = client.post('/api/cart/parse', json={'text': text})
    assert parsed.status_code == 200
    assert parsed.json()['unmatched'] == []
    line = parsed.json()['items'][0]
    assert line['productId'] == product['id']
    assert line['qtyMilli'] == 2000
    assert line['lineTotalCents'] == 4000
