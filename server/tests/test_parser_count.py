"""v2 parse_count: last number wins, pieces/kg, null quantity, several products."""

from __future__ import annotations

import pytest


def voice(client, text):
    response = client.post("/api/inventory/voice", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_contract_example_last_number_wins(client):
    body = voice(client, "coca colas de 600… 4, 5, 6, 7, 8, 9, 10, 11, 12 piezas")
    assert body["items"] == [
        {
            "productId": 1,
            "name": "Coca-Cola 600 ml",
            "qtyMilli": 12000,
            "unit": "pieza",
        }
    ]
    assert body["note"] is None


@pytest.mark.parametrize(
    "text,product_id,qty_milli",
    [
        ("coca cola 4 5 6 12", 1, 12000),
        ("doce piezas de coca cola", 1, 12000),
        ("docena de cocas", 1, 12000),
        ("3 cocas", 1, 3000),
        ("una coca", 1, 1000),
        ("medio kilo de huevo", 4, 500),
        ("2 kilos de tortillas", 9, 2000),
        ("1.5 kg de tortillas", 9, 1500),
        ("250 gramos de huevo", 4, 250),
        ("tres cuartos de kilo de tortillas", 9, 750),
        ("2 piezas de pan", 3, 2000),
    ],
)
def test_count_quantities_and_units(client, text, product_id, qty_milli):
    items = voice(client, text)["items"]
    assert items, text
    first = items[0]
    assert first["productId"] == product_id, text
    assert first["qtyMilli"] == qty_milli, text
    assert first["unit"] in {"pieza", "kg"}


def test_multiple_products_get_their_own_number(client):
    body = voice(client, "3 cocas y 2 sabritas")
    assert [(item["productId"], item["qtyMilli"]) for item in body["items"]] == [
        (1, 3000),
        (2, 2000),
    ]


def test_product_without_quantity_returns_null_and_note(client):
    body = voice(client, "coca cola")
    assert body["items"] == [
        {"productId": 1, "name": "Coca-Cola 600 ml", "qtyMilli": None, "unit": "pieza"}
    ]
    assert body["note"] == "Falta la cantidad de Coca-Cola 600 ml. Confirma la cantidad."


def test_unknown_phrase_returns_empty_items_with_note(client):
    body = voice(client, "una pizza")
    assert body["items"] == []
    assert body["note"] == "No reconocí ningún producto. Intenta de nuevo."
