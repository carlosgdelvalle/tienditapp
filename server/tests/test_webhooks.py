"""Standard Webhooks verification, dedupe, mismatch and unknown QR."""

from __future__ import annotations

import time

from server.tests.conftest import (
    TEST_SECRET,
    create_pey_sale,
    event_payload,
    post_webhook,
    sign_webhook,
)


def test_invalid_signature_rejected(client, fake_pey, db):
    sale = create_pey_sale(client)
    payload = event_payload(sale["qrId"], "tx_bad_sig", 0.01)
    body, headers = sign_webhook(payload, "wh_bad_sig", secret=TEST_SECRET)
    headers["webhook-signature"] = "v1,AAAA"
    response = client.post("/webhooks/pey", content=body, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_signature"
    assert db.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0


def test_valid_webhook_applies_once_and_dedupes(client, fake_pey, db):
    sale = create_pey_sale(client)
    payload = event_payload(sale["qrId"], "tx_once", 0.01)

    first = post_webhook(client, payload, "wh_once")
    assert first.status_code == 200
    assert first.json()["outcome"] == "applied"
    assert first.json()["status"] == "paid_pey"

    duplicate = post_webhook(client, payload, "wh_once")
    assert duplicate.status_code == 200
    assert duplicate.json()["outcome"] == "duplicate"

    same_tx = post_webhook(client, payload, "wh_once_other_id")
    assert same_tx.status_code == 200
    assert same_tx.json()["outcome"] == "duplicate_transaction"

    assert db.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
    stock = db.execute("SELECT stock_milli FROM products WHERE id = 1").fetchone()[0]
    assert stock == 23000


def test_unknown_qr_is_acknowledged(client, db):
    payload = event_payload("qr_que_no_existe", "tx_unknown", 0.01)
    response = post_webhook(client, payload, "wh_unknown_qr")
    assert response.status_code == 200
    assert response.json()["outcome"] == "unknown_qr"
    event = db.execute(
        "SELECT outcome FROM webhook_events WHERE webhook_id = 'wh_unknown_qr'"
    ).fetchone()
    assert event["outcome"] == "unknown_qr"


def test_amount_mismatch_sets_por_conciliar(client, fake_pey, db):
    sale = create_pey_sale(client)
    response = post_webhook(
        client,
        event_payload(sale["qrId"], "tx_wrong", 1.00),
        "wh_wrong_amount",
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "amount_mismatch"
    assert client.get(f"/api/sales/{sale['id']}").json()["status"] == "por_conciliar"
    payment = db.execute(
        "SELECT amount_cents, applied FROM payments WHERE tx_id = 'tx_wrong'"
    ).fetchone()
    assert payment["amount_cents"] == 100
    assert payment["applied"] == 0


def test_old_timestamp_rejected(client, fake_pey):
    sale = create_pey_sale(client)
    payload = event_payload(sale["qrId"], "tx_old", 0.01)
    response = post_webhook(
        client,
        payload,
        "wh_old",
        timestamp=int(time.time()) - 400,
    )
    assert response.status_code == 401


def test_missing_webhook_secret_rejects(client, fake_pey, tmp_path):
    from fastapi.testclient import TestClient

    from server.config import Settings
    from server.main import create_app

    settings = Settings(
        db_path=tmp_path / "no-secret.db",
        pey_api_key="test-key",
        pey_webhook_secret="",
    )
    with TestClient(create_app(settings=settings, pey_client=fake_pey)) as local_client:
        response = local_client.post(
            "/webhooks/pey",
            content=b"{}",
            headers={},
        )
        assert response.status_code == 503
        assert response.json()["error"] == "webhook_not_configured"
