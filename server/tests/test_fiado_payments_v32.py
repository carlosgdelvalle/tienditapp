"""v3.2 fiado payments: history, abono permissions, settlement and report.

Covers the v3.2 contract section "Pagos de fiado (abonos y liquidación)":
the entries history endpoint, the canFiado gate on abonos (owner always
allowed), the note on an abono, partial/full settlement, the console detail
with PIN and fiadoCollectedCents in the today report.
"""

from __future__ import annotations

import pytest

from server.reports import today_bounds
from server.tests.conftest import (
    create_customer,
    create_test_employee,
    employee_headers,
)

pytestmark = pytest.mark.usefixtures("staff")

OWNER_HEADERS = employee_headers(1)
PIN_HEADERS = {"X-Owner-Pin": "1234"}
ENTRY_KEYS = {"id", "kind", "amountCents", "note", "employeeName", "createdAt"}


def create_fiado_sale(client, customer_id: int, *, employee_id: int = 2) -> dict:
    """One charge of $18.00 (product 1 costs 1800 cents) on the customer."""

    response = client.post(
        "/api/sales",
        json={
            "employeeId": employee_id,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "fiado",
            "customerId": customer_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def register_abono(
    client,
    customer_id: int,
    amount_cents: int,
    *,
    employee_id: int = 2,
    note: str | None = None,
    headers: dict[str, str] | None = None,
):
    body: dict = {"amountCents": amount_cents, "employeeId": employee_id}
    if note is not None:
        body["note"] = note
    return client.post(
        f"/api/fiado/customers/{customer_id}/abono", json=body, headers=headers or {}
    )


def list_entries(client, customer_id: int, headers: dict[str, str] | None = None):
    return client.get(
        f"/api/fiado/customers/{customer_id}/entries", headers=headers or {}
    )


def test_entries_history_with_charges_and_payments(client):
    customer = create_customer(client, "Doña Mari", "555-0100")
    charge = create_fiado_sale(client, customer["id"], employee_id=2)

    first = register_abono(
        client, customer["id"], 500, employee_id=3, note="abono parcial"
    )
    assert first.status_code == 200, first.text
    second = register_abono(client, customer["id"], 200, employee_id=2)
    assert second.status_code == 200, second.text

    response = list_entries(client, customer["id"])
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 3

    # Newest first: the two abonos, then the original charge.
    assert [item["kind"] for item in items] == ["payment", "payment", "charge"]
    assert [item["amountCents"] for item in items] == [200, 500, charge["totalCents"]]

    assert [item["employeeName"] for item in items] == ["Lupita", "Toño", "Lupita"]
    assert items[0]["note"] is None
    assert items[1]["note"] == "abono parcial"
    assert items[2]["note"] is None

    for item in items:
        assert set(item) == ENTRY_KEYS
        assert isinstance(item["id"], int)
        assert isinstance(item["createdAt"], (int, float))
    timestamps = [item["createdAt"] for item in items]
    assert timestamps == sorted(timestamps, reverse=True)

    # The same history is readable by an employee with canFiado and by owner.
    assert list_entries(client, customer["id"], employee_headers(2)).status_code == 200
    assert list_entries(client, customer["id"], OWNER_HEADERS).status_code == 200
    # No header keeps the open v1 behavior (console and scripts).
    assert list_entries(client, customer["id"]).status_code == 200


def test_entries_unknown_customer_is_404(client):
    response = list_entries(client, 99999)
    assert response.status_code == 404
    assert response.json()["detail"] == "Cliente de fiado no encontrado"


def test_abono_requires_can_fiado_for_employee(client, db):
    create_test_employee(db, 4, "Beto", can_fiado=0)
    customer = create_customer(client)
    create_fiado_sale(client, customer["id"])

    denied_history = list_entries(client, customer["id"], employee_headers(4))
    assert denied_history.status_code == 403
    assert (
        denied_history.json()["detail"] == "Tu perfil no puede registrar abonos"
    )

    denied_abono = register_abono(
        client, customer["id"], 500, employee_id=4, headers=employee_headers(4)
    )
    assert denied_abono.status_code == 403
    assert denied_abono.json()["detail"] == "Tu perfil no puede registrar abonos"
    # The rejected abono was not recorded.
    assert client.get(f"/api/fiado/customers/{customer['id']}").json()[
        "balanceCents"
    ] == 1800

    # Unknown/inactive identities are rejected too, for reads and writes.
    assert list_entries(client, customer["id"], employee_headers(999)).status_code == 403
    assert (
        register_abono(
            client, customer["id"], 500, employee_id=2, headers=employee_headers(999)
        ).status_code
        == 403
    )

    # The owner always can, even with the simulated console identity (1).
    owner_abono = register_abono(
        client, customer["id"], 100, employee_id=1, headers=OWNER_HEADERS
    )
    assert owner_abono.status_code == 200, owner_abono.text
    assert owner_abono.json() == {"customerId": customer["id"], "balanceCents": 1700}

    # And an employee with canFiado still registers abonos normally.
    allowed = register_abono(
        client, customer["id"], 200, employee_id=2, headers=employee_headers(2)
    )
    assert allowed.status_code == 200
    assert allowed.json()["balanceCents"] == 1500


def test_abono_with_note_and_partial_settlement(client):
    customer = create_customer(client, "Don Pepe")
    create_fiado_sale(client, customer["id"])

    partial = register_abono(
        client,
        customer["id"],
        800,
        employee_id=2,
        note="pago quincena",
        headers=employee_headers(2),
    )
    assert partial.status_code == 200, partial.text
    assert partial.json() == {"customerId": customer["id"], "balanceCents": 1000}

    detail = client.get(f"/api/fiado/customers/{customer['id']}").json()
    assert detail["balanceCents"] == 1000

    history = list_entries(client, customer["id"]).json()["items"]
    assert history[0]["kind"] == "payment"
    assert history[0]["amountCents"] == 800
    assert history[0]["note"] == "pago quincena"
    assert history[0]["employeeName"] == "Lupita"

    # Liquidar saldo: an abono equal to the remaining balance leaves 0.
    settlement = register_abono(
        client, customer["id"], 1000, employee_id=2, note="liquidado"
    )
    assert settlement.status_code == 200, settlement.text
    assert settlement.json() == {"customerId": customer["id"], "balanceCents": 0}

    detail = client.get(f"/api/fiado/customers/{customer['id']}").json()
    assert detail["balanceCents"] == 0
    history = list_entries(client, customer["id"]).json()["items"]
    assert [item["kind"] for item in history] == ["payment", "payment", "charge"]
    assert history[0]["amountCents"] == 1000
    assert history[0]["note"] == "liquidado"

    customers = client.get("/api/fiado/customers").json()["customers"]
    assert customers[0]["balanceCents"] == 0

    # Nothing left to collect: a new report shows no outstanding balance.
    assert client.get("/api/reports/today").json()["fiadoOutstandingCents"] == 0


def test_console_fiado_detail_requires_owner_pin(client):
    customer = create_customer(client, "Cliente Consola", "555-0101")
    create_fiado_sale(client, customer["id"])
    register_abono(client, customer["id"], 300, employee_id=2, note="abono consola")

    path = f"/api/console/fiado/{customer['id']}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Owner-Pin": "0000"}).status_code == 401

    response = client.get(path, headers=PIN_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"customer", "entries"}
    # The customer keeps the console/fiado list shape.
    assert body["customer"] == {
        "id": customer["id"],
        "name": "Cliente Consola",
        "phone": "555-0101",
        "balanceCents": 1500,
    }
    assert [entry["kind"] for entry in body["entries"]] == ["payment", "charge"]
    assert body["entries"][0]["amountCents"] == 300
    assert body["entries"][0]["note"] == "abono consola"
    assert body["entries"][0]["employeeName"] == "Lupita"
    assert set(body["entries"][0]) == ENTRY_KEYS

    # Same customer as the console list payload (customer shape is reused).
    listed = client.get("/api/console/fiado", headers=PIN_HEADERS).json()
    assert listed["customers"][0] == body["customer"]

    assert (
        client.get("/api/console/fiado/99999", headers=PIN_HEADERS).status_code == 404
    )


def test_report_fiado_collected_cents_only_today(client, db, settings):
    start, _end = today_bounds(settings)
    customer = create_customer(client)
    create_fiado_sale(client, customer["id"])

    # A payment from yesterday: it reduces the balance but must not count as
    # fiado collected today.
    db.execute(
        """INSERT INTO fiado_entries
               (customer_id, sale_id, kind, amount_cents, note,
                employee_id, created_at)
           VALUES (?, NULL, 'payment', ?, ?, ?, ?)""",
        (customer["id"], 300, "abono de ayer", 2, start - 60),
    )
    db.commit()

    assert client.get("/api/reports/today").json()["fiadoCollectedCents"] == 0

    today_abono = register_abono(
        client, customer["id"], 500, employee_id=2, note="abono de hoy"
    )
    assert today_abono.status_code == 200

    report = client.get("/api/reports/today").json()
    assert report["fiadoCollectedCents"] == 500
    assert report["fiadoCents"] == 1800
    # The old payment still reduces what the customer owes (1800 - 800).
    assert report["fiadoOutstandingCents"] == 1000

    summary = client.get("/api/console/summary", headers=PIN_HEADERS).json()
    assert summary["fiadoCollectedCents"] == 500
    assert summary["today"]["fiadoCollectedCents"] == 500
