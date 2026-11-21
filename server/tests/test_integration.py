"""Integration smoke test: create_app boots with the I-phase routers wired.

Verifies the non-breaking wiring in server/main.py: the OIDC identity router
runs on a SIMULADO in-memory store (no real OIDC credentials) and the offline
sync router reuses the existing SQLite path. One auth route and one sync route
are exercised to prove both surfaces are reachable on the same app.
"""

from __future__ import annotations


def test_app_boots_with_identity_router(client):
    """POST /api/auth/challenge responds on the wired identity router."""

    response = client.post("/api/auth/challenge", json={"intent": "browser_login"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["challengeId"]
    assert body["code"]
    assert body["qr"].startswith("abarpay://challenge/")
    # The browser receives an HttpOnly cookie used to redeem the challenge.
    assert client.cookies.get("abarpay_challenge") is not None


def test_app_boots_with_sync_router(client):
    """POST /api/sync/lease issues a signed lease + snapshot via SQLite."""

    response = client.post(
        "/api/sync/lease",
        json={
            "deviceId": "device-smoke-1",
            "storeId": "tiendita-esquina",
            "tenantId": "tenant-smoke-1",
            "membershipId": "member-smoke-1",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lease"]["deviceId"] == "device-smoke-1"
    assert body["lease"]["signature"]
    assert body["snapshot"]["signature"]
    assert body["snapshot"]["items"]  # catalog snapshot from the seeded SQLite DB
