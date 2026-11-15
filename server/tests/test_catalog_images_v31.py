"""v3.1 product images: https-only CRUD validation and template URLs.

The contract (docs/v2-contract.md, section v3.1) allows one optional image URL
per catalog item: https only, at most 500 characters. The tiendita template
fills it from the 'imagen' column of the curated resource CSV (Open Food Facts,
CC BY-SA); every other template leaves it null.
"""

from __future__ import annotations

import pytest

from server.catalog_templates import business_template
from server.tests.conftest import employee_headers
from server.tests.test_migrations_v3 import IMAGE_URL

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)

# Exactly 500 characters, the contract limit.
MAX_LENGTH_URL = "https://example.com/" + "a" * (500 - len("https://example.com/"))
TOO_LONG_URL = "https://example.com/" + "a" * (501 - len("https://example.com/"))

OTHER_TEMPLATES = (
    "tortilleria",
    "taqueria",
    "comida-corrida",
    "peluqueria",
    "estetica",
    "fondita",
    "otro",
)


def create_item(client, **overrides):
    payload = {
        "name": "Producto con imagen",
        "unit": "pieza",
        "priceCents": 2500,
        **overrides,
    }
    return client.post("/api/catalog", headers=OWNER, json=payload)


def catalog_item(client, product_id: int) -> dict:
    response = client.get("/api/catalog", params={"limit": 500})
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["id"] == product_id)


def catalog_total(client) -> int:
    response = client.get("/api/catalog", params={"limit": 500})
    assert response.status_code == 200, response.text
    return response.json()["total"]


def empty_catalog(db) -> None:
    db.execute("DELETE FROM barcodes")
    db.execute("DELETE FROM products")
    db.commit()


def apply_template(client, business_type: str):
    return client.post(
        "/api/catalog/templates/apply",
        headers=OWNER,
        json={"businessType": business_type},
    )


def test_create_and_patch_accept_https_image_url(client, db):
    created = create_item(client, imageUrl=IMAGE_URL)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["imageUrl"] == IMAGE_URL
    assert catalog_item(client, body["id"])["imageUrl"] == IMAGE_URL
    # The value lands in the nullable "image_url" column.
    stored = db.execute(
        "SELECT image_url FROM products WHERE id = ?", (body["id"],)
    ).fetchone()
    assert stored["image_url"] == IMAGE_URL

    # No image is also valid: the field is optional and defaults to null.
    plain = create_item(client, name="Producto sin imagen")
    assert plain.status_code == 200, plain.text
    assert plain.json()["imageUrl"] is None

    # PATCH replaces the URL and accepts the exact 500-character boundary.
    patched = client.patch(
        f"/api/catalog/{body['id']}", headers=OWNER, json={"imageUrl": MAX_LENGTH_URL}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["imageUrl"] == MAX_LENGTH_URL
    assert len(patched.json()["imageUrl"]) == 500

    # PATCH with null (or a blank string) clears the image again.
    for empty in (None, "   "):
        cleared = client.patch(
            f"/api/catalog/{body['id']}", headers=OWNER, json={"imageUrl": empty}
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["imageUrl"] is None
    assert catalog_item(client, body["id"])["imageUrl"] is None


def test_create_and_patch_reject_non_https_and_long_urls(client):
    invalid_urls = (
        "http://images.openfoodfacts.org/images/products/front.jpg",
        "http://example.com/producto.jpg",
        "ftp://example.com/producto.jpg",
        "data:image/png;base64,AAAA",
        "images/producto.jpg",
    )
    before = catalog_total(client)
    for url in invalid_urls:
        response = create_item(client, name=f"Imagen inválida {url[:12]}", imageUrl=url)
        assert response.status_code == 400, (url, response.text)
        detail = response.json()["detail"]
        assert "https://" in detail
        assert "URL de imagen" in detail
    assert catalog_total(client) == before

    too_long = create_item(client, name="Imagen larga", imageUrl=TOO_LONG_URL)
    assert too_long.status_code == 400, too_long.text
    assert "500" in too_long.json()["detail"]

    # PATCH validates the same way and keeps the previous value untouched.
    item = create_item(client, name="Producto editable", imageUrl=IMAGE_URL).json()
    for url in invalid_urls + (TOO_LONG_URL,):
        response = client.patch(
            f"/api/catalog/{item['id']}", headers=OWNER, json={"imageUrl": url}
        )
        assert response.status_code == 400, (url, response.text)
        assert "URL de imagen" in response.json()["detail"]
    assert catalog_item(client, item["id"])["imageUrl"] == IMAGE_URL


def test_tiendita_template_assigns_resource_image_urls(client, db):
    empty_catalog(db)
    response = apply_template(client, "tiendita")
    assert response.status_code == 200, response.text
    source = response.json()["source"]

    items = client.get("/api/catalog", params={"limit": 500}).json()["items"]
    assert len(items) == 28
    # Every item carries the v3.1 field.
    assert all("imageUrl" in item for item in items)

    with_image = [item for item in items if item["imageUrl"]]
    assert len(with_image) >= 3
    assert all(item["imageUrl"].startswith("https://") for item in with_image)
    assert all(len(item["imageUrl"]) <= 500 for item in with_image)

    coca = next(item for item in items if item["name"].startswith("Coca-Cola"))
    assert coca["imageUrl"] == IMAGE_URL
    # Two curated rows have no image in the CSV: they stay null (emoji fallback).
    mazapan = next(item for item in items if item["name"] == "Mazapán")
    zote = next(item for item in items if item["name"] == "Jabón Zote")
    assert mazapan["imageUrl"] is None
    assert zote["imageUrl"] is None

    if source["filesAvailable"]:
        # Only the curated rows are read from the (large) CSV header.
        assert source["matchedItems"] == 28
        assert source["imageUrls"] == len(with_image)


@pytest.mark.parametrize("business_type", OTHER_TEMPLATES)
def test_other_templates_leave_image_url_null(client, db, business_type):
    empty_catalog(db)
    response = apply_template(client, business_type)
    assert response.status_code == 200, response.text
    assert response.json()["source"]["imageUrls"] == 0
    items = client.get("/api/catalog", params={"limit": 500}).json()["items"]
    assert items
    assert all(item["imageUrl"] is None for item in items)


def test_tiendita_template_without_resources_degrades_to_no_images(tmp_path):
    template = business_template("tiendita", resources_dir=tmp_path)
    assert template is not None
    assert len(template["items"]) == 28
    assert all(item["imageUrl"] is None for item in template["items"])
    assert template["source"]["filesAvailable"] is False
    assert template["source"]["imageUrls"] == 0
    assert template["source"]["curatedItems"] == 28
