"""v2 support tickets: cobros no confirmados reported from the store.

The ticket row keeps only the report (sale, note, status, timestamps). The sale
context (status, totals, PEY tx id) is read live from sales, which is what the
owner console shows as the trace of a charge that was not confirmed.
"""

from __future__ import annotations

import re
import sqlite3
import time

import pytest

from server.db import initialize_db
from server.tests.conftest import (
    create_cash_sale,
    create_pey_sale,
    employee_headers,
)

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)
LUPITA = employee_headers(2)
TONO = employee_headers(3)

TICKET_ID_RE = re.compile(r"tkt_[0-9a-f]{16}")

# Contract shapes: POST adds alreadyOpen, list/PATCH add resolvedAt.
TICKET_KEYS = {
    "id",
    "saleId",
    "saleStatus",
    "saleTotalCents",
    "chargedCents",
    "peyTxId",
    "note",
    "status",
    "createdAt",
    "reportedByName",
}
GET_KEYS = TICKET_KEYS | {"resolvedAt"}
POST_KEYS = TICKET_KEYS | {"alreadyOpen"}


def create_ticket(client, *, headers=None, **body):
    response = client.post("/api/support/tickets", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_support_tickets_migration_is_additive_and_idempotent(tmp_path):
    path = tmp_path / "tickets-migration.db"
    initialize_db(path)

    # Simulate a database created before the tickets section existed: the
    # additive migration must create the table again without touching data.
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE support_tickets")

    initialize_db(path)
    initialize_db(path)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(support_tickets)")
        ]
        assert columns == [
            "id",
            "store_id",
            "sale_id",
            "note",
            "status",
            "created_at",
            "resolved_at",
        ]
        indexes = {
            row["name"]
            for row in conn.execute("PRAGMA index_list(support_tickets)")
        }
        assert "idx_support_tickets_sale" in indexes
        foreign_keys = {
            (row["from"], row["table"])
            for row in conn.execute("PRAGMA foreign_key_list(support_tickets)")
        }
        assert {("store_id", "stores"), ("sale_id", "sales")} <= foreign_keys

        conn.execute(
            """INSERT INTO support_tickets
                   (id, store_id, sale_id, note, status, created_at, resolved_at)
               VALUES ('tkt_keep', 'tiendita-esquina', NULL, 'nota', 'open', 1.0, NULL)"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO support_tickets
                       (id, store_id, note, status, created_at, resolved_at)
                   VALUES ('tkt_malo', 'tiendita-esquina', 'nota', 'closed', 2.0, NULL)"""
            )

    # A later start keeps the existing ticket.
    initialize_db(path)
    with sqlite3.connect(path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM support_tickets WHERE id = 'tkt_keep'"
            ).fetchone()[0]
            == 1
        )


def test_create_ticket_with_sale_has_full_context(client, fake_pey, db):
    sale = create_pey_sale(client)
    assert sale["status"] == "pending"

    ticket = create_ticket(
        client,
        headers=LUPITA,
        saleId=sale["id"],
        note="El cliente dice que ya pagó",
    )
    assert TICKET_ID_RE.fullmatch(ticket["id"])
    assert set(ticket) == POST_KEYS
    assert ticket["saleId"] == sale["id"]
    assert ticket["saleStatus"] == "pending"
    assert ticket["saleTotalCents"] == 1800
    assert ticket["chargedCents"] == 1
    assert ticket["peyTxId"] is None
    assert ticket["note"] == "El cliente dice que ya pagó"
    assert ticket["status"] == "open"
    assert isinstance(ticket["createdAt"], float)
    assert ticket["createdAt"] > 0
    assert ticket["reportedByName"] == "Lupita"
    assert ticket["alreadyOpen"] is False

    row = db.execute(
        """SELECT store_id, sale_id, note, status, created_at, resolved_at
           FROM support_tickets WHERE id = ?""",
        (ticket["id"],),
    ).fetchone()
    assert tuple(row) == (
        "tiendita-esquina",
        sale["id"],
        "El cliente dice que ya pagó",
        "open",
        ticket["createdAt"],
        None,
    )

    # The context follows the sale: a paid PEY sale exposes its tx id.
    paid_sale = create_pey_sale(client)
    fake_pey.add_transaction(paid_sale["qrId"], "tx_ticket_1", 0.01)
    updated = client.get(f"/api/sales/{paid_sale['id']}")
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "paid_pey"

    paid_ticket = create_ticket(client, headers=TONO, saleId=paid_sale["id"])
    assert paid_ticket["saleStatus"] == "paid_pey"
    assert paid_ticket["saleTotalCents"] == 1800
    assert paid_ticket["chargedCents"] == 1
    assert paid_ticket["peyTxId"] == "tx_ticket_1"
    assert paid_ticket["reportedByName"] == "Toño"
    assert paid_ticket["note"] is None


def test_general_ticket_requires_note(client):
    missing = client.post("/api/support/tickets", headers=LUPITA, json={})
    assert missing.status_code == 400
    assert "nota" in missing.json()["detail"].lower()

    blank = client.post(
        "/api/support/tickets", headers=LUPITA, json={"note": "   "}
    )
    assert blank.status_code == 400

    ticket = create_ticket(client, headers=LUPITA, note="Cobro doble en la caja")
    assert set(ticket) == POST_KEYS
    assert ticket["saleId"] is None
    assert ticket["saleStatus"] is None
    assert ticket["saleTotalCents"] is None
    assert ticket["chargedCents"] is None
    assert ticket["peyTxId"] is None
    assert ticket["note"] == "Cobro doble en la caja"
    assert ticket["status"] == "open"
    assert ticket["reportedByName"] == "Lupita"

    # Without the simulated identity the v1 behavior stays open and there is
    # no employee name to report.
    anonymous = create_ticket(client, note="Ticket sin identidad")
    assert anonymous["reportedByName"] is None


def test_duplicate_open_ticket_returns_the_same_one(client, db):
    sale = create_cash_sale(client)

    first = create_ticket(
        client, headers=LUPITA, saleId=sale["id"], note="Primer reporte"
    )
    again = create_ticket(
        client, headers=LUPITA, saleId=sale["id"], note="Segundo reporte"
    )
    assert again["id"] == first["id"]
    assert again["alreadyOpen"] is True
    assert again["note"] == "Primer reporte"
    assert again["reportedByName"] == "Lupita"
    assert (
        db.execute(
            "SELECT COUNT(*) FROM support_tickets WHERE sale_id = ?",
            (sale["id"],),
        ).fetchone()[0]
        == 1
    )

    resolved = client.patch(
        f"/api/support/tickets/{first['id']}",
        headers=OWNER,
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text

    # A resolved ticket no longer blocks a new report for the same sale.
    reopened = create_ticket(
        client, headers=LUPITA, saleId=sale["id"], note="Sigue el problema"
    )
    assert reopened["id"] != first["id"]
    assert reopened["alreadyOpen"] is False
    assert reopened["status"] == "open"
    assert (
        db.execute(
            "SELECT COUNT(*) FROM support_tickets WHERE sale_id = ?",
            (sale["id"],),
        ).fetchone()[0]
        == 2
    )


def test_list_tickets_owner_view_and_status_filter(client):
    sale_a = create_cash_sale(client)
    ticket_a = create_ticket(
        client, headers=LUPITA, saleId=sale_a["id"], note="Ticket A"
    )
    ticket_b = create_ticket(client, headers=LUPITA, note="Ticket B")
    sale_c = create_cash_sale(client)
    ticket_c = create_ticket(
        client, headers=LUPITA, saleId=sale_c["id"], note="Ticket C"
    )
    resolved_c = client.patch(
        f"/api/support/tickets/{ticket_c['id']}",
        headers=OWNER,
        json={"status": "resolved"},
    )
    assert resolved_c.status_code == 200, resolved_c.text
    assert isinstance(resolved_c.json()["resolvedAt"], float)

    # No header keeps the v1 open behavior: the owner/console view works.
    every = client.get("/api/support/tickets")
    assert every.status_code == 200, every.text
    items = every.json()["items"]
    assert {item["id"] for item in items} == {
        ticket_a["id"],
        ticket_b["id"],
        ticket_c["id"],
    }
    created = [item["createdAt"] for item in items]
    assert created == sorted(created, reverse=True)
    for item in items:
        assert set(item) == GET_KEYS

    by_id = {item["id"]: item for item in items}
    assert by_id[ticket_a["id"]]["saleId"] == sale_a["id"]
    assert by_id[ticket_a["id"]]["saleStatus"] == "paid_cash"
    assert by_id[ticket_a["id"]]["saleTotalCents"] == 1800
    assert by_id[ticket_a["id"]]["chargedCents"] == 1800
    assert by_id[ticket_a["id"]]["reportedByName"] == "Lupita"
    assert by_id[ticket_a["id"]]["resolvedAt"] is None
    assert by_id[ticket_b["id"]]["saleId"] is None
    assert by_id[ticket_b["id"]]["saleStatus"] is None
    assert by_id[ticket_b["id"]]["reportedByName"] is None
    assert by_id[ticket_c["id"]]["status"] == "resolved"
    assert by_id[ticket_c["id"]]["resolvedAt"] is not None

    open_items = client.get(
        "/api/support/tickets", params={"status": "open"}, headers=OWNER
    ).json()["items"]
    assert {item["id"] for item in open_items} == {
        ticket_a["id"],
        ticket_b["id"],
    }
    assert all(item["status"] == "open" for item in open_items)

    resolved_items = client.get(
        "/api/support/tickets", params={"status": "resolved"}, headers=OWNER
    ).json()["items"]
    assert [item["id"] for item in resolved_items] == [ticket_c["id"]]
    assert all(item["status"] == "resolved" for item in resolved_items)

    all_items = client.get(
        "/api/support/tickets", params={"status": "all"}, headers=OWNER
    ).json()["items"]
    assert {item["id"] for item in all_items} == {
        ticket_a["id"],
        ticket_b["id"],
        ticket_c["id"],
    }

    assert (
        client.get(
            "/api/support/tickets", params={"status": "closed"}, headers=OWNER
        ).status_code
        == 422
    )


def test_patch_resolves_and_reopens_tickets(client):
    ticket = create_ticket(client, headers=LUPITA, note="Revisar cobro")

    before = time.time()
    resolved = client.patch(
        f"/api/support/tickets/{ticket['id']}",
        headers=OWNER,
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert set(body) == GET_KEYS
    assert body["status"] == "resolved"
    assert isinstance(body["resolvedAt"], float)
    assert body["resolvedAt"] >= before - 1
    assert body["note"] == "Revisar cobro"

    reopened = client.patch(
        f"/api/support/tickets/{ticket['id']}",
        headers=OWNER,
        json={"status": "open"},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "open"
    assert reopened.json()["resolvedAt"] is None

    noted = client.patch(
        f"/api/support/tickets/{ticket['id']}",
        headers=OWNER,
        json={"note": "   Ya se revisó   "},
    )
    assert noted.status_code == 200, noted.text
    assert noted.json()["note"] == "Ya se revisó"
    assert noted.json()["status"] == "open"

    missing = client.patch(
        "/api/support/tickets/tkt_inexistente",
        headers=OWNER,
        json={"status": "resolved"},
    )
    assert missing.status_code == 404

    invalid = client.patch(
        f"/api/support/tickets/{ticket['id']}",
        headers=OWNER,
        json={"status": "closed"},
    )
    assert invalid.status_code == 422


def test_tickets_are_owner_only_but_any_employee_can_report(client):
    ticket = create_ticket(client, headers=LUPITA, note="Nota de Lupita")

    assert client.get("/api/support/tickets", headers=LUPITA).status_code == 403
    assert (
        client.get(
            "/api/support/tickets", headers=employee_headers(999)
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/support/tickets/{ticket['id']}",
            headers=LUPITA,
            json={"status": "resolved"},
        ).status_code
        == 403
    )

    # Reporting is not owner-only: any active employee can create a ticket.
    reported = create_ticket(client, headers=TONO, note="Reporte de Toño")
    assert reported["reportedByName"] == "Toño"
    assert (
        client.post(
            "/api/support/tickets",
            headers=employee_headers(999),
            json={"note": "x"},
        ).status_code
        == 403
    )

    client.patch("/api/employees/2", headers=OWNER, json={"active": False})
    inactive = client.post(
        "/api/support/tickets", headers=LUPITA, json={"note": "x"}
    )
    assert inactive.status_code == 403


def test_ticket_for_unknown_sale_fails(client, db):
    missing = client.post(
        "/api/support/tickets",
        headers=LUPITA,
        json={"saleId": "sale_no_existe", "note": "x"},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Venta no encontrada"}
    assert db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0] == 0

    blank = client.post(
        "/api/support/tickets",
        headers=LUPITA,
        json={"saleId": "   ", "note": "x"},
    )
    assert blank.status_code == 400

    wrong_type = client.post(
        "/api/support/tickets",
        headers=LUPITA,
        json={"saleId": 123, "note": "x"},
    )
    assert wrong_type.status_code == 422
