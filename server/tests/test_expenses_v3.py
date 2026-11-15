"""v3 simple expenses: register, list, voice parsing (SIMULADO) and today report."""

from __future__ import annotations

import time

import pytest

from server.parser import parse_expense
from server.tests.conftest import employee_headers

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)
LUPITA = employee_headers(2)
CONSOLE = {"X-Owner-Pin": "1234"}


def expenses(client, headers=None, limit: int = 50) -> dict:
    response = client.get("/api/expenses", params={"limit": limit}, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def voice(client, text: str) -> dict:
    response = client.post("/api/expenses/voice", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_create_list_expense_and_report(client, db):
    first = client.post("/api/expenses", json={"amountCents": 2000, "note": "  gas  "})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["amountCents"] == 2000
    assert body["note"] == "gas"
    assert body["employeeId"] is None
    assert isinstance(body["createdAt"], float)

    second = client.post(
        "/api/expenses",
        headers=LUPITA,
        json={"amountCents": 1500, "note": "luz"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["employeeId"] == 2
    assert second.json()["employeeName"] == "Lupita"

    listed = expenses(client, OWNER)
    assert listed["totalTodayCents"] == 3500
    assert [item["amountCents"] for item in listed["items"]] == [1500, 2000]
    assert listed["items"][0]["employeeName"] == "Lupita"
    assert listed["items"][1]["note"] == "gas"
    assert len(expenses(client, limit=1)["items"]) == 1

    # The open v1 behavior keeps the console working without a header.
    assert expenses(client)["totalTodayCents"] == 3500
    # Only the owner lists expenses; an employee is rejected.
    assert client.get("/api/expenses", headers=LUPITA).status_code == 403

    # Today's report (and the console summary) include expenses.
    report = client.get("/api/reports/today").json()
    assert report["totalExpensesCents"] == 3500
    summary = client.get("/api/console/summary", headers=CONSOLE).json()
    assert summary["today"]["totalExpensesCents"] == 3500

    # An expense registered later, with an explicit note, is not trimmed away.
    third = client.post(
        "/api/expenses", json={"amountCents": 999, "note": "  "}
    ).json()
    assert third["note"] is None


def test_expense_validation_and_employee_gate(client):
    assert client.post("/api/expenses", json={"amountCents": 0}).status_code == 400
    assert client.post("/api/expenses", json={"amountCents": -100}).status_code == 400
    assert client.post("/api/expenses", json={}).status_code == 422
    assert client.post(
        "/api/expenses", headers=employee_headers(999), json={"amountCents": 100}
    ).status_code == 403


def test_expense_today_total_ignores_other_days(client, db):
    db.execute(
        """INSERT INTO expenses (store_id, employee_id, amount_cents, note, created_at)
           VALUES ('tiendita-esquina', NULL, 9000, 'ayer', ?)""",
        (time.time() - 2 * 24 * 60 * 60,),
    )
    db.commit()
    client.post("/api/expenses", json={"amountCents": 2500, "note": "hoy"})
    assert expenses(client, OWNER)["totalTodayCents"] == 2500
    assert client.get("/api/reports/today").json()["totalExpensesCents"] == 2500


@pytest.mark.parametrize(
    "text,amount_cents,note",
    [
        ("veinte pesos de gas", 2000, "gas"),
        ("gasté 250 pesos en tortillas", 25000, "tortillas"),
        ("pagué doscientos cincuenta pesos de gasolina", 25000, "gasolina"),
        ("35.50 pesos de refrescos", 3550, "refrescos"),
        ("mil pesos de renta", 100000, "renta"),
        ("cien pesos de luz", 10000, "luz"),
        ("veinte pesos con cincuenta de jabón", 2050, "jabón"),
        ("un gasto de veinte pesos de gas", 2000, "gas"),
        ("500 pesos", 50000, None),
        ("cincuenta centavos de chicles", 50, "chicles"),
    ],
)
def test_expense_voice_parses_words_and_digits(client, db, text, amount_cents, note):
    assert voice(client, text) == {"amountCents": amount_cents, "note": note}
    # Nothing is saved by the voice endpoint: the app confirms first.
    assert expenses(client, OWNER)["items"] == []


def test_expense_voice_without_amount(client):
    body = voice(client, "solo gas")
    assert body["amountCents"] is None
    assert body["note"] == "solo gas"
    assert parse_expense("") == {"amountCents": None, "note": None}
    assert parse_expense("   ") == {"amountCents": None, "note": None}
