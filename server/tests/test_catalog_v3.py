"""v3 catalog: public listing with filters, owner CRUD and delete gates."""

from __future__ import annotations

import pytest

from server.tests.conftest import create_cash_sale, employee_headers

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)
EMPLOYEE = employee_headers(2)


def get_catalog(client, **params) -> dict:
    response = client.get("/api/catalog", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def new_item(client, **overrides) -> dict:
    payload = {
        "name": "Producto de prueba v3",
        "unit": "pieza",
        "priceCents": 2500,
        **overrides,
    }
    response = client.post("/api/catalog", json=payload, headers=OWNER)
    assert response.status_code == 200, response.text
    return response.json()


def test_catalog_is_public_and_exposes_v3_fields(client):
    body = get_catalog(client)
    # v2 seed: 12 products plus the demo Tacos de pastor.
    assert body["total"] == 13
    assert body["limit"] == 50
    assert body["offset"] == 0
    first = next(item for item in body["items"] if item["id"] == 1)
    assert set(first) == {
        "id",
        "name",
        "unit",
        "priceCents",
        "stockMilli",
        "lowStockMilli",
        "quick",
        "unlimitedStock",
        "kind",
        "category",
        "durationMinutes",
        "aliases",
    }
    assert first["name"] == "Coca-Cola 600 ml"
    assert first["kind"] == "producto"
    assert first["category"] is None
    assert first["durationMinutes"] is None
    assert isinstance(first["aliases"], list) and first["aliases"]


def test_catalog_search_category_kind_and_pagination(client):
    service = new_item(
        client,
        name="Corte de cabello v3",
        unit="servicio",
        kind="servicio",
        priceCents=15000,
        category="Servicios",
        durationMinutes=30,
        aliases=["corte", "corte de pelo"],
    )
    dish = new_item(
        client,
        name="Platillo del día v3",
        unit="servicio",
        kind="platillo",
        priceCents=8000,
        category="Comida",
    )
    assert service["unlimitedStock"] is True
    assert service["stockMilli"] == 0
    assert dish["unlimitedStock"] is True

    # Free text: name or alias, accent and hyphen insensitive.
    assert [item["id"] for item in get_catalog(client, q="coca")["items"]] == [1]
    assert [item["id"] for item in get_catalog(client, q="jabon")["items"]] == [10]
    assert get_catalog(client, q="Jabón")["total"] == 1
    assert get_catalog(client, q="coca-cola")["total"] == 1
    assert get_catalog(client, q="corte de pelo")["items"][0]["id"] == service["id"]

    # Exact category / kind filters.
    assert get_catalog(client, category="Servicios")["total"] == 1
    assert get_catalog(client, category="Comida")["total"] == 1
    assert get_catalog(client, kind="servicio")["total"] == 1
    assert get_catalog(client, kind="platillo")["total"] == 1
    assert get_catalog(client, kind="producto")["total"] == 13

    # Server-side pagination reports the filtered total, not the page size.
    page = get_catalog(client, limit=5, offset=0)
    assert len(page["items"]) == 5 and page["total"] == 15
    tail = get_catalog(client, limit=5, offset=10)
    assert len(tail["items"]) == 5 and tail["total"] == 15
    assert get_catalog(client, limit=200, offset=20)["items"] == []

    # Invalid filters and out-of-range pagination are rejected.
    assert client.get("/api/catalog", params={"kind": "otro"}).status_code == 400
    assert client.get("/api/catalog", params={"limit": 0}).status_code == 422
    assert client.get("/api/catalog", params={"limit": 501}).status_code == 422
    assert get_catalog(client, limit=500)["total"] == 15  # Android asks for 500
    assert client.get("/api/catalog", params={"offset": -1}).status_code == 422


def test_catalog_create_validates_units_kinds_and_numbers(client):
    created = client.post(
        "/api/catalog",
        headers=OWNER,
        json={
            "name": "  Servicio premium  ",
            "unit": "sesion",
            "priceCents": 45000,
            "kind": "servicio",
            "category": "Servicios",
            "durationMinutes": 90,
            "aliases": ["premium", " sesion premium ", ""],
            "quick": True,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Servicio premium"
    assert body["unit"] == "sesion"
    assert body["kind"] == "servicio"
    assert body["category"] == "Servicios"
    assert body["durationMinutes"] == 90
    assert body["aliases"] == ["premium", "sesion premium"]
    # Servicios do not carry inventory unless the owner says otherwise.
    assert body["unlimitedStock"] is True
    assert body["stockMilli"] == 0
    assert body["quick"] is True
    assert body["id"] > 13

    # A product with explicit stock stays finite.
    product = new_item(
        client,
        name="Producto con stock",
        stockMilli=8000,
        category="Abarrotes",
        unlimitedStock=False,
    )
    assert product["unlimitedStock"] is False
    assert product["stockMilli"] == 8000

    # Open v1 behavior for console/scripts: no employee header.
    open_create = client.post(
        "/api/catalog",
        json={"name": "Producto consola", "unit": "pieza", "priceCents": 1000},
    )
    assert open_create.status_code == 200

    # Only the owner can write.
    denied = client.post(
        "/api/catalog",
        headers=EMPLOYEE,
        json={"name": "No permitido", "unit": "pieza", "priceCents": 1000},
    )
    assert denied.status_code == 403

    invalid_cases = [
        {"name": "   ", "unit": "pieza", "priceCents": 1000},
        {"name": "Unidad mala", "unit": "botella", "priceCents": 1000},
        {"name": "Tipo malo", "unit": "pieza", "priceCents": 1000, "kind": "otro"},
        {"name": "Precio negativo", "unit": "pieza", "priceCents": -1},
        {"name": "Stock negativo", "unit": "pieza", "priceCents": 1000, "stockMilli": -5},
        {"name": "Duración negativa", "unit": "servicio", "priceCents": 1000, "durationMinutes": -5},
    ]
    for payload in invalid_cases:
        response = client.post("/api/catalog", headers=OWNER, json=payload)
        assert response.status_code == 400, (payload, response.text)
    missing = client.post("/api/catalog", headers=OWNER, json={"name": "Sin unidad"})
    assert missing.status_code == 422


def test_catalog_patch_updates_only_sent_fields(client):
    created = new_item(
        client,
        name="Producto editable",
        priceCents=3000,
        category="Abarrotes",
        stockMilli=5000,
        aliases=["editable"],
    )
    product_id = created["id"]

    patched = client.patch(
        f"/api/catalog/{product_id}",
        headers=OWNER,
        json={"name": "Producto editado", "priceCents": 3500, "quick": True},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["name"] == "Producto editado"
    assert body["priceCents"] == 3500
    assert body["quick"] is True
    # Untouched fields survive.
    assert body["category"] == "Abarrotes"
    assert body["stockMilli"] == 5000
    assert body["aliases"] == ["editable"]

    cleared = client.patch(
        f"/api/catalog/{product_id}", headers=OWNER, json={"category": None}
    )
    assert cleared.json()["category"] is None

    # Changing to a service disables inventory; setting stock makes it finite.
    service = client.patch(
        f"/api/catalog/{product_id}", headers=OWNER, json={"kind": "servicio"}
    ).json()
    assert service["unlimitedStock"] is True
    assert service["stockMilli"] == 0
    finite = client.patch(
        f"/api/catalog/{product_id}", headers=OWNER, json={"stockMilli": 4000}
    ).json()
    assert finite["unlimitedStock"] is False
    assert finite["stockMilli"] == 4000

    assert client.patch(
        f"/api/catalog/{product_id}", headers=OWNER, json={"unit": "botella"}
    ).status_code == 400
    assert client.patch(
        f"/api/catalog/{product_id}", headers=OWNER, json={"priceCents": -1}
    ).status_code == 400
    assert client.patch(
        f"/api/catalog/{product_id}", headers=OWNER, json={"kind": "otro"}
    ).status_code == 400
    assert client.patch(
        "/api/catalog/99999", headers=OWNER, json={"name": "Fantasma"}
    ).status_code == 404
    assert client.patch(
        f"/api/catalog/{product_id}", headers=EMPLOYEE, json={"name": "Nope"}
    ).status_code == 403


def test_catalog_delete_removes_item_and_barcode(client):
    created = new_item(client, name="Producto borrable")
    product_id = created["id"]
    assert client.post(
        "/api/barcode/link", json={"code": "9990001112223", "productId": product_id}
    ).status_code == 200

    deleted = client.delete(f"/api/catalog/{product_id}", headers=OWNER)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"ok": True, "id": product_id}
    assert client.post(
        "/api/barcode/lookup", json={"code": "9990001112223"}
    ).status_code == 404
    assert all(item["id"] != product_id for item in get_catalog(client, limit=200)["items"])

    assert client.delete(f"/api/catalog/{product_id}", headers=OWNER).status_code == 404
    other = new_item(client, name="Producto ajeno")
    assert client.delete(
        f"/api/catalog/{other['id']}", headers=EMPLOYEE
    ).status_code == 403


def test_catalog_delete_is_blocked_by_sales_or_movements(client):
    sold = new_item(client, name="Producto vendido", priceCents=3000)
    create_cash_sale(
        client,
        employee_id=2,
        product_id=sold["id"],
        qty_milli=1000,
        cash_received_cents=5000,
    )
    blocked_sale = client.delete(f"/api/catalog/{sold['id']}", headers=OWNER)
    assert blocked_sale.status_code == 409
    assert "ventas" in blocked_sale.json()["detail"]

    moved = new_item(client, name="Producto con movimiento", priceCents=3000, stockMilli=1000)
    adjusted = client.post(
        "/api/inventory/adjust",
        headers=employee_headers(3),
        json={
            "employeeId": 3,
            "productId": moved["id"],
            "deltaMilli": 500,
            "reason": "conteo",
        },
    )
    assert adjusted.status_code == 200, adjusted.text
    blocked_movement = client.delete(f"/api/catalog/{moved['id']}", headers=OWNER)
    assert blocked_movement.status_code == 409
    assert "movimientos" in blocked_movement.json()["detail"]


def test_service_sale_does_not_touch_inventory(client):
    service = new_item(
        client,
        name="Servicio cobrado",
        unit="servicio",
        kind="servicio",
        priceCents=12000,
    )
    sale = create_cash_sale(
        client,
        employee_id=2,
        product_id=service["id"],
        qty_milli=2000,
        cash_received_cents=30000,
    )
    assert sale["totalCents"] == 24000
    assert sale["items"][0]["unit"] == "servicio"
    inventory = client.get("/api/inventory").json()["items"]
    line = next(item for item in inventory if item["productId"] == service["id"])
    assert line["unlimitedStock"] is True
    assert line["stockMilli"] == 0
    assert line["valueCents"] == 0
