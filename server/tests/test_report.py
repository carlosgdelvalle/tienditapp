"""Today report totals and split by payment method."""

from __future__ import annotations

from server.tests.conftest import (
    create_cash_sale,
    create_customer,
    create_pey_sale,
    event_payload,
    post_webhook,
)


def test_today_report_totals_by_method_employee_and_product(client, fake_pey):
    cash = create_cash_sale(client, employee_id=2, product_id=1, qty_milli=2000)

    pey = create_pey_sale(client, employee_id=3, product_id=2, qty_milli=1000)
    fake_pey.add_transaction(pey["qrId"], "tx_report", 0.01)
    assert client.get(f"/api/sales/{pey['id']}").json()["status"] == "paid_pey"

    customer = create_customer(client, "Cliente Reporte")
    fiado = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 5, "qtyMilli": 1000}],
            "paymentMethod": "fiado",
            "customerId": customer["id"],
        },
    )
    assert fiado.status_code == 200

    adjust = client.post(
        "/api/inventory/adjust",
        json={
            "employeeId": 2,
            "productId": 3,
            "deltaMilli": -2000,
            "reason": "conteo",
        },
    )
    assert adjust.status_code == 200

    report = client.get("/api/reports/today")
    assert report.status_code == 200
    body = report.json()

    assert body["totalCents"] == 3600 + 2200 + 3100
    assert body["collectedCents"] == 3600 + 2200
    assert body["cashCents"] == 3600
    assert body["peyCents"] == 2200
    assert body["fiadoCents"] == 3100
    assert body["salesCount"] == 3
    assert body["pending"] == 0
    assert body["fiadoOutstandingCents"] == 3100
    assert body["demoMode"] is True
    assert body["cashCents"] + body["peyCents"] + body["fiadoCents"] == body["totalCents"]

    by_employee = {row["employeeId"]: row for row in body["byEmployee"]}
    assert by_employee[2]["salesCount"] == 2
    assert by_employee[2]["totalCents"] == 3600 + 3100
    assert by_employee[3]["totalCents"] == 2200

    top = {row["productId"]: row for row in body["topProducts"]}
    assert top[1]["totalCents"] == 3600
    assert top[2]["totalCents"] == 2200
    assert top[5]["totalCents"] == 3100

    low_stock_ids = {product["id"] for product in body["lowStock"]}
    assert 3 in low_stock_ids
    pan = next(product for product in body["lowStock"] if product["id"] == 3)
    assert pan["stockMilli"] == 4000


def test_abono_reduces_outstanding_and_pending_pey_is_counted(client, fake_pey):
    customer = create_customer(client)
    client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "fiado",
            "customerId": customer["id"],
        },
    )
    client.post(
        f"/api/fiado/customers/{customer['id']}/abono",
        json={"amountCents": 800, "employeeId": 2},
    )
    assert client.get("/api/reports/today").json()["fiadoOutstandingCents"] == 1000

    pending = create_pey_sale(client, product_id=12, qty_milli=1000)
    assert pending["status"] == "pending"

    report = client.get("/api/reports/today").json()
    assert report["pending"] == 1
    assert report["pendingCents"] == 1700
    assert report["salesCount"] == 2
    assert report["collectedCents"] == 0
    assert report["fiadoOutstandingCents"] == 1000
