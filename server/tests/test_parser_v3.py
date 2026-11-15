"""v3 parser: service units keep working with catalog aliases; v2 stays intact."""

from __future__ import annotations

import pytest

from server.tests.conftest import employee_headers

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)


def add_item(client, **payload) -> dict:
    response = client.post("/api/catalog", headers=OWNER, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def parse(client, text: str) -> dict:
    response = client.post("/api/cart/parse", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def first_item(client, text: str) -> dict:
    body = parse(client, text)
    assert body["unmatched"] == [], (text, body)
    assert len(body["items"]) == 1, (text, body)
    return body["items"][0]


def test_v2_cart_parser_contract_example_still_matches(client):
    body = parse(client, "medio kilo de tortillas y dos cocas")
    assert body["engine"] == "local"
    assert body["unmatched"] == []
    assert body["items"] == [
        {
            "productId": 9,
            "name": "Tortillas (kg)",
            "qtyMilli": 500,
            "unit": "kg",
            "unitPriceCents": 2600,
            "lineTotalCents": 1300,
        },
        {
            "productId": 1,
            "name": "Coca-Cola 600 ml",
            "qtyMilli": 2000,
            "unit": "pieza",
            "unitPriceCents": 1800,
            "lineTotalCents": 3600,
        },
    ]


def test_v2_count_parser_contract_example_still_matches(client):
    response = client.post(
        "/api/inventory/voice",
        json={"text": "coca colas de 600… 4, 5, 6, 7, 8, 9, 10, 11, 12 piezas"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {
            "productId": 1,
            "name": "Coca-Cola 600 ml",
            "qtyMilli": 12000,
            "unit": "pieza",
        }
    ]
    assert body["note"] is None


def test_service_units_are_counted_like_pieces(client):
    corte = add_item(
        client,
        name="Corte de cabello",
        unit="servicio",
        kind="servicio",
        priceCents=15000,
        aliases=["corte", "cortes", "corte de pelo"],
        durationMinutes=30,
    )
    manicure = add_item(
        client,
        name="Manicure",
        unit="servicio",
        kind="servicio",
        priceCents=12000,
        aliases=["manicure", "manicures", "sesion de manicure"],
        durationMinutes=45,
    )
    combo = add_item(
        client,
        name="Corte y barba",
        unit="combo",
        kind="servicio",
        priceCents=20000,
        aliases=["combo"],
        durationMinutes=45,
    )

    for text, expected_id, expected_qty in [
        ("dos cortes", corte["id"], 2000),
        ("un corte de pelo", corte["id"], 1000),
        ("tres manicures", manicure["id"], 3000),
        ("un manicure", manicure["id"], 1000),
        ("una sesión de manicure", manicure["id"], 1000),
        ("cuatro turnos de corte", corte["id"], 4000),
        ("un combo", combo["id"], 1000),
    ]:
        line = first_item(client, text)
        assert line["productId"] == expected_id, text
        assert line["qtyMilli"] == expected_qty, text
        assert line["unit"] in {"servicio", "combo"}
        assert line["unitPriceCents"] == next(
            item["priceCents"]
            for item in (corte, manicure, combo)
            if item["id"] == expected_id
        )


def test_service_quantities_merge_and_keep_catalog_prices(client):
    corte = add_item(
        client,
        name="Corte express",
        unit="servicio",
        kind="servicio",
        priceCents=9900,
        aliases=["express"],
    )
    body = parse(client, "un corte express y dos cortes express")
    assert [(item["productId"], item["qtyMilli"]) for item in body["items"]] == [
        (corte["id"], 3000)
    ]
    assert body["items"][0]["lineTotalCents"] == 29700


def test_weight_and_piece_units_are_untouched(client):
    for text, product_id, qty_milli in [
        ("1/2 kg de huevo", 4, 500),
        ("250 gramos de huevo", 4, 250),
        ("1.5 kg de tortillas", 9, 1500),
        ("un cuarto de kilo de tortillas", 9, 250),
        ("tres coches", 1, 3000),
        ("2 piezas de pan", 3, 2000),
    ]:
        line = first_item(client, text)
        assert line["productId"] == product_id, text
        assert line["qtyMilli"] == qty_milli, text
