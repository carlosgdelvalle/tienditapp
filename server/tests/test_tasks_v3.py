"""v3 day tasks: owner sees all, an employee only their own active tasks."""

from __future__ import annotations

import pytest

from server.db import STORE_ID
from server.tests.conftest import create_test_employee, employee_headers

pytestmark = pytest.mark.usefixtures("staff")

OWNER = employee_headers(1)
LUPITA = employee_headers(2)
TONO = employee_headers(3)


def apply_template(client, db, business_type: str = "taqueria") -> list[dict]:
    db.execute("DELETE FROM barcodes")
    db.execute("DELETE FROM products")
    db.commit()
    response = client.post(
        "/api/catalog/templates/apply",
        headers=OWNER,
        json={"businessType": business_type},
    )
    assert response.status_code == 200, response.text
    tasks = client.get("/api/tasks").json()["items"]
    assert len(tasks) >= 3
    return tasks


def list_tasks(client, headers=None) -> list[dict]:
    response = client.get("/api/tasks", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_employee_only_sees_assigned_active_tasks(client, db):
    tasks = apply_template(client, db)
    assert len(tasks) == 4
    # Owner and the open v1 behavior see every task.
    assert len(list_tasks(client, OWNER)) == 4
    assert len(list_tasks(client)) == 4
    # Nothing is assigned right after applying the template.
    assert list_tasks(client, LUPITA) == []
    assert list_tasks(client, TONO) == []

    first, second, third = tasks[0], tasks[1], tasks[2]
    assert client.patch(
        f"/api/tasks/{first['id']}",
        headers=OWNER,
        json={"assignedEmployeeId": 2},
    ).status_code == 200
    assert client.patch(
        f"/api/tasks/{second['id']}",
        headers=OWNER,
        json={"assignedEmployeeId": 2, "active": False},
    ).status_code == 200
    assert client.patch(
        f"/api/tasks/{third['id']}",
        headers=OWNER,
        json={"assignedEmployeeId": 3},
    ).status_code == 200

    # Lupita: only her active task. Toño: his own. Unassigned never shows up.
    assert [task["id"] for task in list_tasks(client, LUPITA)] == [first["id"]]
    assert [task["id"] for task in list_tasks(client, TONO)] == [third["id"]]
    assert len(list_tasks(client, OWNER)) == 4
    inactive = next(task for task in list_tasks(client, OWNER) if task["id"] == second["id"])
    assert inactive["active"] is False

    # Reactivating the second task makes it visible again for Lupita.
    client.patch(f"/api/tasks/{second['id']}", headers=OWNER, json={"active": True})
    assert [task["id"] for task in list_tasks(client, LUPITA)] == [
        first["id"],
        second["id"],
    ]


def test_patch_task_assignment_title_and_validation(client, db):
    tasks = apply_template(client, db, "peluqueria")
    task = tasks[0]

    updated = client.patch(
        f"/api/tasks/{task['id']}",
        headers=OWNER,
        json={"assignedEmployeeId": 2, "title": "Preparar estación y café"},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["assignedEmployeeId"] == 2
    assert body["assignedEmployeeName"] == "Lupita"
    assert body["title"] == "Preparar estación y café"
    assert body["active"] is True

    unassigned = client.patch(
        f"/api/tasks/{task['id']}",
        headers=OWNER,
        json={"assignedEmployeeId": None},
    )
    assert unassigned.json()["assignedEmployeeId"] is None
    assert unassigned.json()["assignedEmployeeName"] is None
    assert list_tasks(client, LUPITA) == []

    # Unknown/inactive employees, empty titles and bad payloads are rejected.
    assert client.patch(
        f"/api/tasks/{task['id']}",
        headers=OWNER,
        json={"assignedEmployeeId": 999},
    ).status_code == 400
    create_test_employee(db, 4, "Empleado inactivo", active=0)
    assert client.patch(
        f"/api/tasks/{task['id']}",
        headers=OWNER,
        json={"assignedEmployeeId": 4},
    ).status_code == 400
    assert client.patch(
        f"/api/tasks/{task['id']}", headers=OWNER, json={"title": "   "}
    ).status_code == 400
    assert client.patch(
        f"/api/tasks/{task['id']}", headers=OWNER, json={"active": None}
    ).status_code == 400
    assert client.patch(
        "/api/tasks/99999", headers=OWNER, json={"title": "Fantasma"}
    ).status_code == 404

    # Only the owner may change tasks; an unknown employee is rejected.
    assert client.patch(
        f"/api/tasks/{task['id']}", headers=LUPITA, json={"title": "Nope"}
    ).status_code == 403
    assert client.get("/api/tasks", headers=employee_headers(999)).status_code == 403


def test_tasks_are_created_by_the_template_with_unique_keys(client, db):
    tasks = apply_template(client, db, "tortilleria")
    keys = [task["key"] for task in tasks]
    assert keys == [
        "revisar-maquina",
        "limpiar-comal",
        "contar-costales",
        "cuadrar-caja",
    ]
    assert tasks[0]["title"] == "Revisar la máquina"
    # Applying another template is blocked, so keys never duplicate.
    assert client.post(
        "/api/catalog/templates/apply",
        headers=OWNER,
        json={"businessType": "fondita"},
    ).status_code == 409
    assert len(list_tasks(client)) == 4
