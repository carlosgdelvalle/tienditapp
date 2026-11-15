"""v3 business templates: one-shot catalog + fixed day tasks per business type."""

from __future__ import annotations

import pytest

from server.db import PRODUCT_KINDS, PRODUCT_UNITS
from server.tests.conftest import TEST_SECRET, employee_headers
from server.tests.fakes import FakePey

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)
EMPLOYEE = employee_headers(2)

TEMPLATE_SIZES = {
    "tiendita": (24, 32),
    "tortilleria": (6, 12),
    "taqueria": (6, 12),
    "comida-corrida": (6, 12),
    "peluqueria": (6, 12),
    "estetica": (6, 12),
    "fondita": (6, 12),
    "otro": (6, 12),
}


def empty_catalog(db) -> None:
    """Leave the store with no products (the template only applies then)."""

    db.execute("DELETE FROM barcodes")
    db.execute("DELETE FROM products")
    db.commit()


def test_brand_new_store_without_seed_catalog_starts_empty(tmp_path):
    from fastapi.testclient import TestClient

    from server.config import Settings
    from server.main import create_app

    fresh = Settings(
        db_path=tmp_path / "fresh-empty.db",
        seed_catalog=False,
        owner_pin="1234",
        modo_demo=True,
        pey_api_key="test-pey-key",
        pey_webhook_secret=TEST_SECRET,
        pey_expiration_seconds=900,
        timezone="America/Mexico_City",
    )
    with TestClient(create_app(settings=fresh, pey_client=FakePey())) as client:
        catalog = client.get("/api/catalog", params={"limit": 500}).json()
        assert catalog["total"] == 0
        response = client.post(
            "/api/catalog/templates/apply",
            headers=employee_headers(1),
            json={"businessType": "tiendita"},
        )
        assert response.status_code == 200, response.text
        items = client.get("/api/catalog", params={"limit": 500}).json()["items"]
        assert 24 <= len(items) <= 32
        second = client.post(
            "/api/catalog/templates/apply",
            headers=employee_headers(1),
            json={"businessType": "taqueria"},
        )
        assert second.status_code == 409


def apply_template(client, business_type: str):
    return client.post(
        "/api/catalog/templates/apply",
        headers=OWNER,
        json={"businessType": business_type},
    )


def catalog_items(client) -> list[dict]:
    response = client.get("/api/catalog", params={"limit": 200})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def tasks(client, headers=None) -> list[dict]:
    response = client.get("/api/tasks", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()["items"]


@pytest.mark.parametrize("business_type", list(TEMPLATE_SIZES))
def test_apply_template_creates_catalog_and_day_tasks(client, db, business_type):
    empty_catalog(db)
    low, high = TEMPLATE_SIZES[business_type]
    response = apply_template(client, business_type)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] is True
    assert body["businessType"] == business_type
    assert low <= body["itemsCreated"] <= high
    assert 3 <= body["tasksCreated"] <= 5
    assert body["itemsCreated"] == len(catalog_items(client))

    items = catalog_items(client)
    for item in items:
        assert item["kind"] in PRODUCT_KINDS
        assert item["unit"] in PRODUCT_UNITS
        assert item["priceCents"] > 0
        assert item["category"], item
        if item["kind"] != "producto":
            # Services and dishes never carry inventory.
            assert item["unlimitedStock"] is True
            assert item["stockMilli"] == 0
    if business_type == "tortilleria":
        assert any(item["unit"] == "kg" for item in items)
    if business_type in {"peluqueria", "estetica"}:
        assert all(item["kind"] == "servicio" for item in items)
        assert all(item["durationMinutes"] for item in items)

    day_tasks = tasks(client)
    assert len(day_tasks) == body["tasksCreated"]
    keys = [task["key"] for task in day_tasks]
    assert len(keys) == len(set(keys))
    for task in day_tasks:
        assert task["active"] is True
        assert task["assignedEmployeeId"] is None
        assert task["title"].strip()


def test_apply_template_only_once(client, db):
    empty_catalog(db)
    first = apply_template(client, "taqueria")
    assert first.status_code == 200
    items_after_first = len(catalog_items(client))
    tasks_after_first = len(tasks(client))

    second = apply_template(client, "taqueria")
    assert second.status_code == 409
    assert "ya tiene catálogo" in second.json()["detail"]
    other = apply_template(client, "peluqueria")
    assert other.status_code == 409
    assert len(catalog_items(client)) == items_after_first
    assert len(tasks(client)) == tasks_after_first


def test_apply_with_existing_catalog_returns_409(client):
    # The v2 seed already has a catalog, so this is the normal onboarding state.
    response = apply_template(client, "tiendita")
    assert response.status_code == 409
    assert len(catalog_items(client)) == 13


def test_apply_rejects_unknown_business_type(client, db):
    empty_catalog(db)
    response = apply_template(client, "ferreteria")
    assert response.status_code == 400
    assert "Tipo de negocio" in response.json()["detail"]
    assert catalog_items(client) == []
    assert tasks(client) == []


def test_apply_requires_owner(client, db):
    empty_catalog(db)
    response = client.post(
        "/api/catalog/templates/apply",
        headers=EMPLOYEE,
        json={"businessType": "tiendita"},
    )
    assert response.status_code == 403
    assert catalog_items(client) == []


def test_apply_accepts_onboarding_aliases(client, db):
    aliases = {
        "Miscelánea": "tiendita",
        "Tiendita/Abarrotes": "tiendita",
        "Tortillería": "tortilleria",
        "Taquería": "taqueria",
        "Comida corrida": "comida-corrida",
        "Peluquería/Barbería": "peluqueria",
        "Estética de uñas": "estetica",
        "Otro": "otro",
    }
    for raw, canonical in aliases.items():
        empty_catalog(db)
        response = apply_template(client, raw)
        assert response.status_code == 200, (raw, response.text)
        assert response.json()["businessType"] == canonical


def test_tiendita_uses_the_curated_resource_catalog(client, db):
    empty_catalog(db)
    response = apply_template(client, "tiendita")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["itemsCreated"] == 28
    source = body["source"]
    assert source["curatedItems"] == 28
    assert source["catalogFile"] == "catalogo-incluir.csv"
    # The full CSV is never embedded: only the curated subset is matched.
    if source["filesAvailable"]:
        assert source["matchedItems"] == 28
        assert source["observedPrices"] >= 10
        assert source["incluirTotal"] == 9421

    items = catalog_items(client)
    assert len(items) == 28
    names = {item["name"] for item in items}
    categories = {item["category"] for item in items}
    assert "Coca-Cola 600 ml (sin azúcar)" in names
    assert {"Bebidas", "Lácteos", "Pan", "Abarrotes"} <= categories
    assert all(item["kind"] == "producto" for item in items)
    assert all(item["unit"] in {"pieza", "kg"} for item in items)
    assert all(item["unlimitedStock"] is False for item in items)
    assert all(item["stockMilli"] > 0 for item in items)
    # The observed price from the resource (18.00 MXN) wins for Coca-Cola.
    coca = next(item for item in items if item["name"].startswith("Coca-Cola"))
    assert coca["priceCents"] == 1800
    # Fiado catalog aliases keep working with the curated items.
    parsed = client.post("/api/cart/parse", json={"text": "dos cocas y un jabon"})
    assert parsed.status_code == 200
    names = [line["name"] for line in parsed.json()["items"]]
    assert "Coca-Cola 600 ml (sin azúcar)" in names
    assert any("Jabón" in name for name in names)

    task_titles = [task["title"] for task in tasks(client)]
    assert "Contar inventario" in task_titles
    assert "Limpiar" in task_titles
