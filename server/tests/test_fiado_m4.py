"""M4 extended fiado tests: limits, override, repayment, payoff, reminder, export.

These tests build an app with the M4 router registered on top of the normal
create_app (the integrator wires register_fiado_routes(app) into main.py; here
the test registers it directly so the suite is self-contained). Identity is
SIMULADO via X-Employee-Id, exactly like the v3.2 fiado payment tests.
"""

from __future__ import annotations

import csv
import io
import time

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.routes_fiado import register as register_fiado_routes
from server.tests.conftest import (
    create_customer,
    create_test_employee,
    employee_headers,
)

OWNER_HEADERS = employee_headers(1)

EXPECTED_CSV_HEADER = (
    "customerId,customerName,entryId,kind,amountCents,note,employeeName,"
    "dueAt,remindedAt,createdAt"
)


@pytest.fixture
def fiado_client(settings, fake_pey, staff, db):
    """App + TestClient with the M4 fiado router registered."""

    app = create_app(settings=settings, pey_client=fake_pey)
    register_fiado_routes(app)
    with TestClient(app) as test_client:
        yield test_client


# --- helpers ---------------------------------------------------------------


def set_limit(client, customer_id: int, limit_cents: int) -> dict:
    response = client.patch(
        f"/api/fiado/customers/{customer_id}",
        json={"creditLimitCents": limit_cents},
        headers=OWNER_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def charge(
    client,
    customer_id: int,
    amount_cents: int,
    *,
    headers: dict[str, str] | None = None,
    due_at: float | None = None,
    note: str | None = None,
):
    body: dict = {"amountCents": amount_cents}
    if due_at is not None:
        body["dueAt"] = due_at
    if note is not None:
        body["note"] = note
    return client.post(
        f"/api/fiado/customers/{customer_id}/charges",
        json=body,
        headers=headers or {},
    )


def repay(
    client,
    customer_id: int,
    amount_cents: int,
    *,
    headers: dict[str, str] | None = None,
    note: str | None = None,
):
    body: dict = {"amountCents": amount_cents}
    if note is not None:
        body["note"] = note
    return client.post(
        f"/api/fiado/customers/{customer_id}/repayments",
        json=body,
        headers=headers or {},
    )


# --- tests -----------------------------------------------------------------


def test_credit_limit_rejection(fiado_client):
    customer = create_customer(fiado_client, "Cliente Límite", "555-1111")
    set_limit(fiado_client, customer["id"], 5000)

    first = charge(fiado_client, customer["id"], 3000, headers=employee_headers(2))
    assert first.status_code == 200, first.text
    assert first.json()["customer"]["balanceCents"] == 3000
    assert first.json()["customer"]["availableCreditCents"] == 2000
    assert first.json()["entry"]["kind"] == "charge"

    # 3000 outstanding + 3000 requested exceeds the 5000 limit.
    over = charge(fiado_client, customer["id"], 3000, headers=employee_headers(2))
    assert over.status_code == 409, over.text
    detail = over.json()["detail"]
    assert detail["code"] == "CREDIT_LIMIT_EXCEEDED"
    assert detail["availableCreditCents"] == 2000
    assert detail["requestedCents"] == 3000

    # The rejected charge left the ledger untouched.
    assert (
        fiado_client.get(f"/api/fiado/customers/{customer['id']}").json()[
            "balanceCents"
        ]
        == 3000
    )


def test_owner_override_beyond_limit(fiado_client):
    customer = create_customer(fiado_client, "Cliente Override", "555-2222")
    set_limit(fiado_client, customer["id"], 2000)

    denied = charge(fiado_client, customer["id"], 3000, headers=employee_headers(2))
    assert denied.status_code == 409

    # A can_fiado employee cannot authorize the exception; only the owner can.
    denied_override = fiado_client.post(
        "/api/fiado/overrides",
        json={"customerId": customer["id"], "amountCents": 3000, "reason": "x"},
        headers=employee_headers(2),
    )
    assert denied_override.status_code == 403

    override = fiado_client.post(
        "/api/fiado/overrides",
        json={
            "customerId": customer["id"],
            "amountCents": 3000,
            "reason": "cliente de confianza",
        },
        headers=OWNER_HEADERS,
    )
    assert override.status_code == 200, override.text
    body = override.json()
    assert body["override"]["reason"] == "cliente de confianza"
    assert body["override"]["amountCents"] == 3000
    assert body["override"]["employeeName"] == "Doña Rosa"
    assert body["entry"]["kind"] == "charge"
    assert body["entry"]["amountCents"] == 3000
    assert body["customer"]["balanceCents"] == 3000

    # The owner reason is kept as an audit trace, not only the charge.
    assert (
        fiado_client.get(f"/api/fiado/customers/{customer['id']}").json()[
            "balanceCents"
        ]
        == 3000
    )


def test_partial_repayment(fiado_client):
    customer = create_customer(fiado_client, "Cliente Abono", "555-3333")
    charge(fiado_client, customer["id"], 4000, headers=employee_headers(2))

    response = repay(
        fiado_client,
        customer["id"],
        1500,
        headers=employee_headers(2),
        note="pago quincena",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["balanceCents"] == 2500
    assert body["settled"] is False
    assert body["entry"]["kind"] == "payment"
    assert body["entry"]["amountCents"] == 1500
    assert body["entry"]["note"] == "pago quincena"
    assert body["entry"]["employeeName"] == "Lupita"


def test_full_payoff(fiado_client):
    customer = create_customer(fiado_client, "Cliente Liquidado", "555-4444")
    charge(fiado_client, customer["id"], 4000)

    response = repay(fiado_client, customer["id"], 4000, note="liquidado")
    assert response.status_code == 200, response.text
    assert response.json()["balanceCents"] == 0
    assert response.json()["settled"] is True

    # Nothing left to collect: a further repayment is an overpayment.
    over = repay(fiado_client, customer["id"], 100)
    assert over.status_code == 409
    assert over.json()["detail"]["code"] == "OVERPAYMENT"


def test_opt_in_reminder(fiado_client, db, monkeypatch):
    now = time.time()

    # Consenting customer with one overdue and one upcoming charge.
    c1 = create_customer(fiado_client, "Con Consentimiento", "555-5555")
    assert (
        fiado_client.patch(
            f"/api/fiado/customers/{c1['id']}",
            json={"remindersConsent": True},
            headers=OWNER_HEADERS,
        ).status_code
        == 200
    )
    charge(fiado_client, c1["id"], 1000, due_at=now - 86400)  # overdue
    charge(fiado_client, c1["id"], 2000, due_at=now + 3 * 86400)  # upcoming

    # Non-consenting customer with an overdue charge (default consent = 0).
    c2 = create_customer(fiado_client, "Sin Consentimiento", "555-6666")
    charge(fiado_client, c2["id"], 1500, due_at=now - 86400)

    # Only the consenting customer appears, split by overdue / upcoming.
    reminders = fiado_client.get("/api/fiado/reminders", headers=OWNER_HEADERS).json()
    assert reminders["simulado"] is True
    assert [r["customerId"] for r in reminders["overdue"]] == [c1["id"]]
    assert [r["kind"] for r in reminders["overdue"]] == ["overdue"]
    assert [r["customerId"] for r in reminders["upcoming"]] == [c1["id"]]
    assert [r["kind"] for r in reminders["upcoming"]] == ["upcoming"]
    assert all(r["customerId"] != c2["id"] for r in reminders["overdue"])
    assert all(r["customerId"] != c2["id"] for r in reminders["upcoming"])

    # SIMULADO send: only the consenting customer is notified, once per charge.
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "server.fiado.notification_hook",
        lambda name, entry, kind, _now: calls.append((name, kind)),
    )
    sent = fiado_client.post(
        "/api/fiado/reminders/send", headers=OWNER_HEADERS
    ).json()
    assert sent["simulado"] is True
    assert [s["kind"] for s in sent["sent"]] == ["overdue", "upcoming"]
    assert calls == [
        ("Con Consentimiento", "overdue"),
        ("Con Consentimiento", "upcoming"),
    ]

    # Durable SIMULADO trace + reminded_at were written only for the consenting
    # customer's two charges.
    trace = db.execute(
        "SELECT customer_id FROM fiado_reminders ORDER BY id"
    ).fetchall()
    assert [row["customer_id"] for row in trace] == [c1["id"], c1["id"]]
    reminded = db.execute(
        """SELECT customer_id FROM fiado_entries
           WHERE reminded_at IS NOT NULL ORDER BY id"""
    ).fetchall()
    assert [row["customer_id"] for row in reminded] == [c1["id"], c1["id"]]


def test_export_csv_no_pii(fiado_client):
    customer = create_customer(fiado_client, "Cliente Export", "555-7777")
    charge(fiado_client, customer["id"], 1800, note="fiado export")

    # A can_fiado employee cannot export; the owner can.
    assert (
        fiado_client.get("/api/fiado/export", headers=employee_headers(2)).status_code
        == 403
    )

    response = fiado_client.get("/api/fiado/export", headers=OWNER_HEADERS)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")

    text = response.text
    assert text.splitlines()[0] == EXPECTED_CSV_HEADER

    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 1
    assert rows[0]["customerName"] == "Cliente Export"
    assert rows[0]["kind"] == "charge"
    assert rows[0]["amountCents"] == "1800"
    assert rows[0]["note"] == "fiado export"

    # No PII leak: the phone/contact never appears in the CSV.
    assert "555-7777" not in text
    assert "phone" not in text.lower()
    assert "phone" not in rows[0]


def test_repayment_requires_can_fiado(fiado_client, db):
    create_test_employee(db, 4, "Beto", can_fiado=0)
    customer = create_customer(fiado_client, "Cliente Permiso", "555-8888")
    charge(fiado_client, customer["id"], 2000)

    denied = repay(
        fiado_client, customer["id"], 500, headers=employee_headers(4)
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Tu perfil no puede registrar abonos"

    # The rejected repayment did not change the balance.
    assert (
        fiado_client.get(f"/api/fiado/customers/{customer['id']}").json()[
            "balanceCents"
        ]
        == 2000
    )

    # The owner always can.
    allowed = repay(fiado_client, customer["id"], 500, headers=OWNER_HEADERS)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["balanceCents"] == 1500
