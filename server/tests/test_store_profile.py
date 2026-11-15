"""v2 store profile, business photo and the owner gate."""

from __future__ import annotations

import pytest

import base64
from pathlib import Path

from server.tests.conftest import employee_headers

pytestmark = pytest.mark.usefixtures("staff")

JPEG_BYTES = b"SIMULADO-foto-jpeg"


def data_url(payload: bytes = JPEG_BYTES) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")


def test_profile_defaults_and_update(client, db):
    default = client.get("/api/store/profile")
    assert default.status_code == 200
    assert default.json() == {
        "storeId": "tiendita-esquina",
        "name": "Tiendita de la Esquina",
        "businessType": "",
        "ownerName": "Doña Rosa",
    }

    updated = client.put(
        "/api/store/profile",
        headers=employee_headers(1),
        json={
            "name": "Abarrotes Doña Rosa",
            "businessType": "Abarrotes",
            "ownerName": "Rosa",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json() == {
        "storeId": "tiendita-esquina",
        "name": "Abarrotes Doña Rosa",
        "businessType": "Abarrotes",
        "ownerName": "Rosa",
    }
    assert client.get("/api/store/profile").json() == updated.json()
    bootstrap_store = client.get("/api/bootstrap").json()["store"]
    assert bootstrap_store == {
        "id": "tiendita-esquina",
        "name": "Abarrotes Doña Rosa",
        "businessType": "Abarrotes",
        "ownerName": "Rosa",
    }
    settings_row = db.execute(
        "SELECT business_type, owner_name FROM store_settings WHERE store_id = ?",
        ("tiendita-esquina",),
    ).fetchone()
    assert (settings_row["business_type"], settings_row["owner_name"]) == (
        "Abarrotes",
        "Rosa",
    )


def test_profile_partial_update_keeps_other_fields(client):
    client.put(
        "/api/store/profile",
        headers=employee_headers(1),
        json={"businessType": "Fondita"},
    )
    body = client.get("/api/store/profile").json()
    assert body["businessType"] == "Fondita"
    assert body["name"] == "Tiendita de la Esquina"
    assert body["ownerName"] == "Doña Rosa"


def test_profile_requires_owner_and_validates_names(client):
    employee = client.put(
        "/api/store/profile",
        headers=employee_headers(2),
        json={"name": "No permitido"},
    )
    assert employee.status_code == 403

    unknown = client.put(
        "/api/store/profile",
        headers=employee_headers(999),
        json={"name": "No permitido"},
    )
    assert unknown.status_code == 403

    empty_name = client.put(
        "/api/store/profile",
        headers=employee_headers(1),
        json={"name": "   "},
    )
    assert empty_name.status_code == 400

    empty_owner = client.put(
        "/api/store/profile",
        headers=employee_headers(1),
        json={"ownerName": ""},
    )
    assert empty_owner.status_code == 400

    # No header keeps the open v1 behavior (scripts and console).
    open_update = client.put("/api/store/profile", json={"businessType": "Tiendita"})
    assert open_update.status_code == 200
    assert open_update.json()["businessType"] == "Tiendita"


def test_photo_upload_and_fetch(client, settings):
    assert client.get("/api/store/photo").status_code == 404

    uploaded = client.post(
        "/api/store/photo",
        headers=employee_headers(1),
        json={"dataUrl": data_url()},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json() == {"ok": True}

    photo_path = Path(settings.db_path).parent / "store-photo.jpg"
    assert photo_path.is_file()
    assert photo_path.read_bytes() == JPEG_BYTES

    fetched = client.get("/api/store/photo")
    assert fetched.status_code == 200
    assert fetched.content == JPEG_BYTES
    assert fetched.headers["content-type"].startswith("image/jpeg")


def test_photo_upload_is_owner_only(client, settings):
    response = client.post(
        "/api/store/photo",
        headers=employee_headers(2),
        json={"dataUrl": data_url()},
    )
    assert response.status_code == 403
    assert not (Path(settings.db_path).parent / "store-photo.jpg").exists()


def test_photo_rejects_bad_prefix_base64_and_size(client, settings):
    bad_prefix = client.post(
        "/api/store/photo",
        headers=employee_headers(1),
        json={"dataUrl": "data:image/png;base64,AAAA"},
    )
    assert bad_prefix.status_code == 400

    bad_base64 = client.post(
        "/api/store/photo",
        headers=employee_headers(1),
        json={"dataUrl": "data:image/jpeg;base64,%%%no-es-base64%%%"},
    )
    assert bad_base64.status_code == 400

    empty = client.post(
        "/api/store/photo",
        headers=employee_headers(1),
        json={"dataUrl": "data:image/jpeg;base64,"},
    )
    assert empty.status_code == 400

    too_big = client.post(
        "/api/store/photo",
        headers=employee_headers(1),
        json={"dataUrl": data_url(b"x" * (5 * 1024 * 1024 + 1))},
    )
    assert too_big.status_code == 400
    assert not (Path(settings.db_path).parent / "store-photo.jpg").exists()
