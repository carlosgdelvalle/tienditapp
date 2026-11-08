"""Local parser: pieces, kg, grams, fractions, decimals, aliases, unmatched."""

from __future__ import annotations

import pytest


def parse(client, text: str) -> dict:
    response = client.post("/api/cart/parse", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_contract_example_half_kilo_and_two_cokes(client):
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


@pytest.mark.parametrize(
    "text,product_id,qty_milli",
    [
        ("1/2 kg de huevo", 4, 500),
        ("250 gramos de huevo", 4, 250),
        ("1.5 kg de tortillas", 9, 1500),
        ("un cuarto de kilo de tortillas", 9, 250),
        ("tres coches", 1, 3000),
        ("2 piezas de pan", 3, 2000),
        ("un kilo de huevo", 4, 1000),
        ("1,5 kg de huevo", 4, 1500),
        ("dos cocas, unas sabritas", 1, 2000),
    ],
)
def test_quantities_and_aliases(client, text, product_id, qty_milli):
    body = parse(client, text)
    assert body["items"], text
    first = body["items"][0]
    assert first["productId"] == product_id
    assert first["qtyMilli"] == qty_milli


def test_unmatched_words_are_reported(client):
    body = parse(client, "dos cocas y una pizza")
    assert [item["productId"] for item in body["items"]] == [1]
    assert body["unmatched"] == ["pizza"]


def test_duplicate_products_are_merged(client):
    body = parse(client, "una coca y dos cocas")
    assert len(body["items"]) == 1
    assert body["items"][0]["productId"] == 1
    assert body["items"][0]["qtyMilli"] == 3000
    assert body["items"][0]["lineTotalCents"] == 5400


def test_parser_never_calls_openai(client):
    body = parse(client, "medio kilo de tortillas")
    assert body["engine"] == "local"
