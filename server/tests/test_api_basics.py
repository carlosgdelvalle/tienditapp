"""Health, bootstrap, barcode and server-side price checks."""

from __future__ import annotations


def test_health_and_bootstrap(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {
        "ok": True,
        "mode": "demo",
        "db": "ok",
        "peyConfigured": True,
    }

    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["store"] == {"id": "tiendita-esquina", "name": "Tiendita de la Esquina"}
    assert body["demoMode"] is True
    assert body["ai"] == "local"
    assert [employee["name"] for employee in body["employees"]] == [
        "Doña Rosa",
        "Lupita",
        "Toño",
    ]
    assert [employee["role"] for employee in body["employees"]] == [
        "owner",
        "employee",
        "employee",
    ]

    products = body["products"]
    assert len(products) == 12
    assert products[0] == {
        "id": 1,
        "name": "Coca-Cola 600 ml",
        "unit": "pieza",
        "priceCents": 1800,
        "stockMilli": 24000,
        "lowStockMilli": 5000,
        "quick": True,
    }
    assert products[8]["name"] == "Tortillas (kg)"
    assert products[8]["unit"] == "kg"
    assert products[8]["priceCents"] == 2600
    assert products[8]["stockMilli"] == 8000
    assert products[8]["quick"] is False


def test_barcode_lookup_and_link(client):
    response = client.post("/api/barcode/lookup", json={"code": "7500000000001"})
    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["name"] == "Coca-Cola 600 ml"

    missing = client.post("/api/barcode/lookup", json={"code": "9999999999999"})
    assert missing.status_code == 404

    linked = client.post(
        "/api/barcode/link",
        json={"code": "9999999999999", "productId": 9},
    )
    assert linked.status_code == 200
    assert linked.json()["id"] == 9

    lookup = client.post("/api/barcode/lookup", json={"code": "9999999999999"})
    assert lookup.status_code == 200
    assert lookup.json()["id"] == 9

    bad_product = client.post(
        "/api/barcode/link",
        json={"code": "123", "productId": 999},
    )
    assert bad_product.status_code == 404


def test_server_ignores_client_prices(client):
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [
                {
                    "productId": 1,
                    "qtyMilli": 2000,
                    "unitPriceCents": 1,
                    "lineTotalCents": 1,
                }
            ],
            "paymentMethod": "cash",
            "cashReceivedCents": 5000,
            "totalCents": 1,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["totalCents"] == 3600
    assert body["changeCents"] == 1400
    assert body["items"][0]["unitPriceCents"] == 1800
    assert body["items"][0]["lineTotalCents"] == 3600
