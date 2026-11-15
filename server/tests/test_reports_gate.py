"""v2 reports are owner-only when the simulated identity header is present."""

from __future__ import annotations

import pytest

from server.tests.conftest import employee_headers

pytestmark = pytest.mark.usefixtures("staff")


def test_reports_today_owner_only(client):
    # No header is still compatible with v1 (console and scripts).
    assert client.get("/api/reports/today").status_code == 200
    owner = client.get("/api/reports/today", headers=employee_headers(1))
    assert owner.status_code == 200
    assert owner.json()["demoMode"] is True

    employee = client.get("/api/reports/today", headers=employee_headers(2))
    assert employee.status_code == 403
    assert employee.json() == {"detail": "Solo el dueño ve reportes"}

    unknown = client.get("/api/reports/today", headers=employee_headers(999))
    assert unknown.status_code == 403


def test_reports_gate_rejects_inactive_employee(client):
    client.patch("/api/employees/2", headers=employee_headers(1), json={"active": False})
    response = client.get("/api/reports/today", headers=employee_headers(2))
    assert response.status_code == 403
    # An inactive header is invalid; the request never reaches the report.
    assert response.json()["detail"]
