"""PEY HTTP client boundary test with httpx MockTransport (no network)."""

from __future__ import annotations

import json

import httpx

from server.pey import PeyClient


def test_create_qr_sends_pesos_and_metadata_without_network():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"id": "qr_sim_client", "image": "data:image/png;base64,U0lNVUxBRE8="},
        )

    client = PeyClient(
        "test-pey-key",
        base_url="https://pey.invalid",
        transport=httpx.MockTransport(handler),
    )
    try:
        response = client.create_qr(
            amount_cents=1,
            concept="Abarpay sale_test",
            expiration_sec=900,
            sale_id="sale_test",
        )
    finally:
        client.close()

    assert response["id"] == "qr_sim_client"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://pey.invalid/codi/qr"
    assert captured["authorization"] == "Bearer test-pey-key"
    assert captured["body"] == {
        "amount": 0.01,
        "concept": "Abarpay sale_test",
        "expiration": 900,
        "generateImage": True,
        "metadata": {"saleId": "sale_test"},
    }


def test_qr_transactions_reads_items_without_network():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transaction/codi/qr/qr_1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "transactionId": "tx_1",
                        "amount": 0.01,
                        "status": "completed",
                    }
                ]
            },
        )

    client = PeyClient(
        "test-pey-key",
        base_url="https://pey.invalid",
        transport=httpx.MockTransport(handler),
    )
    try:
        items = client.qr_transactions("qr_1")
    finally:
        client.close()

    assert items[0]["transactionId"] == "tx_1"
