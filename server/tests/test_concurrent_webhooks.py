"""Concurrent webhooks must serialize, apply once and never return a 500."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from server.tests.conftest import create_pey_sale, event_payload, sign_webhook


def test_concurrent_cash_sales_do_not_lose_stock(client, db):
    payload = {
        "employeeId": 2,
        "items": [{"productId": 1, "qtyMilli": 1000}],
        "paymentMethod": "cash",
        "cashReceivedCents": 1800,
    }

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(
            pool.map(lambda _: client.post("/api/sales", json=payload), range(10))
        )

    assert all(response.status_code == 200 for response in responses)
    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 14000
    assert client.get("/api/reports/today").json()["salesCount"] == 10


def test_concurrent_webhooks_apply_exactly_once(client, fake_pey, db):
    sale = create_pey_sale(client)
    payload = event_payload(sale["qrId"], "tx_concurrent", 0.01)
    total_requests = 12
    barrier = threading.Barrier(total_requests)

    def fire(index: int):
        webhook_id = "wh_concurrent_" + str(index)
        body, headers = sign_webhook(payload, webhook_id)
        barrier.wait(timeout=10)
        return client.post("/webhooks/pey", content=body, headers=headers)

    with ThreadPoolExecutor(max_workers=total_requests) as pool:
        futures = [pool.submit(fire, index) for index in range(total_requests)]
        responses = [future.result(timeout=30) for future in futures]

    assert all(response.status_code == 200 for response in responses)
    outcomes = [response.json()["outcome"] for response in responses]
    assert outcomes.count("applied") == 1
    assert outcomes.count("duplicate_transaction") == total_requests - 1

    assert db.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE sale_id = ?", (sale["id"],)
    ).fetchone()[0] == 1
    assert client.get(f"/api/sales/{sale['id']}").json()["status"] == "paid_pey"
