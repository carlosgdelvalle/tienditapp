"""Owner console: static page, PIN login and protected endpoints."""

from __future__ import annotations

from server.tests.conftest import create_cash_sale, create_customer


def test_console_page_is_static_and_auto_refreshes(client):
    response = client.get("/console")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Consola de la dueña" in response.text
    assert "X-Owner-Pin" in response.text
    assert "setInterval" in response.text
    assert "REFRESH_MS = 3000" in response.text
    assert "Modo demo" in response.text

    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code in (307, 308)
    assert redirect.headers["location"] == "/console"


def test_console_login_pin(client):
    assert client.post("/api/console/login", json={"pin": "0000"}).status_code == 401
    ok = client.post("/api/console/login", json={"pin": "1234"})
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}


def test_console_endpoints_require_owner_pin(client):
    for path in (
        "/api/console/summary",
        "/api/console/sales",
        "/api/console/inventory",
        "/api/console/fiado",
        "/api/console/webhooks",
    ):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Owner-Pin": "0000"}).status_code == 401

    headers = {"X-Owner-Pin": "1234"}
    create_cash_sale(client)

    summary = client.get("/api/console/summary", headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert set(body) == {
        "store",
        "today",
        "employees",
        "recentSales",
        "lowStock",
        "fiadoOutstandingCents",
    }
    assert body["store"]["id"] == "tiendita-esquina"
    assert body["today"]["salesCount"] == 1
    assert body["recentSales"][0]["status"] == "paid_cash"
    assert len(body["employees"]) == 3

    sales = client.get("/api/console/sales?limit=1", headers=headers)
    assert sales.status_code == 200
    assert len(sales.json()["items"]) == 1
    assert sales.json()["items"][0]["items"]

    inventory = client.get("/api/console/inventory", headers=headers)
    assert inventory.status_code == 200
    assert len(inventory.json()["items"]) == 12

    webhooks = client.get("/api/console/webhooks?limit=5", headers=headers)
    assert webhooks.status_code == 200
    assert "items" in webhooks.json()

    create_customer(client, "Cliente Consola", "555-0101")
    fiado = client.get("/api/console/fiado", headers=headers)
    assert fiado.status_code == 200
    assert "customers" in fiado.json()
    assert "totalOutstandingCents" in fiado.json()


def test_console_header_is_case_insensitive(client):
    response = client.get("/api/console/inventory", headers={"x-owner-pin": "1234"})
    assert response.status_code == 200
