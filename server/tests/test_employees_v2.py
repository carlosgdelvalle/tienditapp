"""v2 employees, permissions and multi-device invitations."""

from __future__ import annotations

import re
import time

import pytest

from server.tests.conftest import employee_headers

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)


def create_invite(client, **body):
    payload = {"name": "Beto"}
    payload.update(body)
    response = client.post("/api/employees/invites", headers=OWNER, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.fresh_seed
def test_new_database_seeds_only_the_owner(client):
    body = client.get("/api/employees", headers=OWNER).json()
    assert body["items"] == [
        {
            "id": 1,
            "name": "Doña Rosa",
            "nickname": None,
            "role": "owner",
            "active": True,
            "canSell": True,
            "canFiado": True,
            "canInventory": False,
        }
    ]


def test_employees_owner_gate(client):
    open_list = client.get("/api/employees")
    assert open_list.status_code == 200
    ids = [employee["id"] for employee in open_list.json()["items"]]
    assert ids == [1, 2, 3]

    assert (
        client.get("/api/employees", headers=employee_headers(2)).status_code == 403
    )
    assert (
        client.get("/api/employees", headers=employee_headers(999)).status_code == 403
    )


def test_patch_employee_permissions_and_nickname(client, db):
    patched = client.patch(
        "/api/employees/2",
        headers=OWNER,
        json={
            "nickname": "Lupis",
            "canSell": False,
            "canFiado": False,
            "canInventory": True,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json() == {
        "id": 2,
        "name": "Lupita",
        "nickname": "Lupis",
        "role": "employee",
        "active": True,
        "canSell": False,
        "canFiado": False,
        "canInventory": True,
    }
    row = db.execute(
        "SELECT nickname, can_sell, can_fiado, can_inventory FROM employees WHERE id = 2"
    ).fetchone()
    assert (row["nickname"], row["can_sell"], row["can_fiado"], row["can_inventory"]) == (
        "Lupis",
        0,
        0,
        1,
    )

    deactivated = client.patch(
        "/api/employees/2", headers=OWNER, json={"active": False}
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    # An inactive employee header is no longer valid.
    assert (
        client.get("/api/reports/today", headers=employee_headers(2)).status_code
        == 403
    )


def test_patch_employee_validation(client):
    assert (
        client.patch(
            "/api/employees/2", headers=employee_headers(2), json={"nickname": "x"}
        ).status_code
        == 403
    )
    assert (
        client.patch("/api/employees/999", headers=OWNER, json={"nickname": "x"}).status_code
        == 404
    )
    assert (
        client.patch("/api/employees/2", headers=OWNER, json={"name": "  "}).status_code
        == 400
    )


def test_invite_create_lookup_accept_flow(client, db):
    created = create_invite(
        client, name="Beto", canSell=True, canFiado=False, canInventory=True
    )
    token = created["token"]
    assert re.fullmatch(r"[0-9a-f]{32}", token)
    assert created["url"] == "https://abarpay-api.onrender.com/invite/" + token
    employee_id = created["employeeId"]

    pending = db.execute(
        "SELECT name, role, active, can_fiado, can_inventory FROM employees WHERE id = ?",
        (employee_id,),
    ).fetchone()
    assert (pending["name"], pending["role"], pending["active"]) == (
        "Beto",
        "employee",
        0,
    )
    assert (pending["can_fiado"], pending["can_inventory"]) == (0, 1)
    invite_row = db.execute(
        "SELECT employee_id, accepted FROM invites WHERE token = ?", (token,)
    ).fetchone()
    assert (invite_row["employee_id"], invite_row["accepted"]) == (employee_id, 0)

    lookup = client.get(f"/api/employees/invites/{token}")
    assert lookup.status_code == 200, lookup.text
    body = lookup.json()
    assert body["token"] == token
    assert body["employeeId"] == employee_id
    assert body["name"] == "Beto"
    assert body["role"] == "employee"
    assert body["storeName"] == "Mi negocio"
    assert body["businessType"] == ""
    assert body["canSell"] is True
    assert body["canFiado"] is False
    assert body["canInventory"] is True

    accepted = client.post(
        f"/api/employees/invites/{token}/accept", json={"nickname": "Beto"}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {
        "id": employee_id,
        "name": "Beto",
        "nickname": "Beto",
        "role": "employee",
        "active": True,
        "canSell": True,
        "canFiado": False,
        "canInventory": True,
    }

    # A used token is gone.
    assert client.get(f"/api/employees/invites/{token}").status_code == 410
    assert (
        client.post(
            f"/api/employees/invites/{token}/accept", json={"nickname": "Otra vez"}
        ).status_code
        == 410
    )

    listed = client.get("/api/employees", headers=OWNER).json()["items"]
    beto = next(item for item in listed if item["id"] == employee_id)
    assert beto["active"] is True
    assert beto["nickname"] == "Beto"

    # The new employee can use inventory because can_inventory is on, and is
    # still rejected from owner-only reports.
    set_stock = client.post(
        "/api/inventory/set",
        headers=employee_headers(employee_id),
        json={"productId": 1, "qtyMilli": 12000},
    )
    assert set_stock.status_code == 200, set_stock.text
    reports = client.get(
        "/api/reports/today", headers=employee_headers(employee_id)
    )
    assert reports.status_code == 403
    assert reports.json() == {"detail": "Solo el dueño ve reportes"}


def test_invite_expired_returns_404(client, db):
    created = create_invite(client, name="Beto")
    token = created["token"]
    db.execute(
        "UPDATE invites SET expires_at = ? WHERE token = ?",
        (time.time() - 1, token),
    )
    db.commit()

    assert client.get(f"/api/employees/invites/{token}").status_code == 404
    assert (
        client.post(
            f"/api/employees/invites/{token}/accept", json={"nickname": "Beto"}
        ).status_code
        == 404
    )


def test_invite_unknown_token_returns_404(client):
    token = "0" * 32
    assert client.get(f"/api/employees/invites/{token}").status_code == 404
    assert client.delete(f"/api/employees/invites/{token}", headers=OWNER).status_code == 404
    assert (
        client.post(
            f"/api/employees/invites/{token}/accept", json={"nickname": "Beto"}
        ).status_code
        == 404
    )


def test_invite_delete_pending_employee(client, db):
    created = create_invite(client, name="Beto")
    token = created["token"]
    employee_id = created["employeeId"]

    deleted = client.delete(f"/api/employees/invites/{token}", headers=OWNER)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"ok": True}
    assert client.get(f"/api/employees/invites/{token}").status_code == 404
    assert (
        db.execute("SELECT COUNT(*) FROM employees WHERE id = ?", (employee_id,)).fetchone()[0]
        == 0
    )
    # Deleting twice is a 404, not a crash.
    assert client.delete(f"/api/employees/invites/{token}", headers=OWNER).status_code == 404


def test_invite_delete_requires_owner_and_ignores_accepted(client, db):
    created = create_invite(client, name="Beto")
    token = created["token"]
    assert (
        client.delete(
            f"/api/employees/invites/{token}", headers=employee_headers(2)
        ).status_code
        == 403
    )

    assert (
        client.post(
            f"/api/employees/invites/{token}/accept", json={"nickname": "Beto"}
        ).status_code
        == 200
    )
    conflict = client.delete(f"/api/employees/invites/{token}", headers=OWNER)
    assert conflict.status_code == 409
    assert (
        db.execute(
            "SELECT active FROM employees WHERE id = ?", (created["employeeId"],)
        ).fetchone()["active"]
        == 1
    )


def test_invite_create_validation(client):
    assert (
        client.post(
            "/api/employees/invites",
            headers=employee_headers(2),
            json={"name": "Beto"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/employees/invites", headers=OWNER, json={"name": "   "}
        ).status_code
        == 400
    )
