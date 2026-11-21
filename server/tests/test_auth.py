"""Identity suite: token validation, challenges, invites and isolation.

All tokens are signed with a locally generated RSA test key (no network); every
challenge/device is SIMULADO and lives in an in-memory store. No real OIDC
provider, no real credentials, no real money.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.parse

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import (
    AuthConfig,
    InvalidAudienceError,
    InvalidIssuerError,
    Issuer,
    StaticJwksProvider,
    TokenExpiredError,
    TokenValidator,
    UnsupportedAlgorithmError,
    entra_external_sub,
)
from server.auth_routes import register
from server.identity import (
    MemoryIdentityStore,
    challenge_signature_payload,
    hash_invite_token,
    sha256_hex,
)

ISSUER = "https://test.auth0.example/"
AUDIENCE = "abarpay-api"
KID = "token-kid"

ENTRA_ISSUER = "https://login.microsoftonline.com/test-tenant/v2.0"
ENTRA_AUDIENCE = "abarpay-staff-api"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_rsa_key(kid: str) -> tuple[str, str, dict]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    pub = key.public_key()
    pub_pem = pub.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    numbers = pub.public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
    }
    return priv_pem, pub_pem, jwk


TOKEN_PRIV, _TOKEN_PUB, TOKEN_JWK = _make_rsa_key(KID)
DEVICE_PRIV, DEVICE_PUB, _ = _make_rsa_key("device-kid")


def make_token(claims: dict, *, priv: str = TOKEN_PRIV, kid: str = KID) -> str:
    return jwt.encode(claims, priv, algorithm="RS256", headers={"kid": kid})


def make_none_token(claims: dict) -> str:
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8"))
    payload = _b64url(json.dumps(claims).encode("utf-8"))
    return f"{header}.{payload}."


def sign_device(private_pem: str, message: str) -> str:
    key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    signature = key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


class Clock:
    def __init__(self) -> None:
        self.t = time.time()

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def build_validator(
    *,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    kid: str = KID,
    jwk: dict = TOKEN_JWK,
    clock_skew: float = 0.0,
) -> TokenValidator:
    return TokenValidator(
        [Issuer(issuer=issuer, audience=audience, kind="auth0")],
        providers={issuer: StaticJwksProvider({kid: jwk})},
        clock_skew_seconds=clock_skew,
    )


def build_entra_validator() -> TokenValidator:
    return TokenValidator(
        [Issuer(issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE, kind="entra")],
        providers={ENTRA_ISSUER: StaticJwksProvider({KID: TOKEN_JWK})},
        clock_skew_seconds=0.0,
    )


def make_app(
    *,
    store: MemoryIdentityStore | None = None,
    clock: Clock | None = None,
    validator: TokenValidator | None = None,
) -> tuple[TestClient, MemoryIdentityStore, Clock]:
    store = store or MemoryIdentityStore()
    clock = clock or Clock()
    validator = validator or build_validator()
    config = AuthConfig(
        issuers=(Issuer(issuer=ISSUER, audience=AUDIENCE, kind="auth0"),),
        clock_skew_seconds=0.0,
        secure_cookies=False,
        cookie_samesite="lax",
    )
    app = FastAPI()
    register(app, store=store, validator=validator, auth_config=config, now=clock)
    return TestClient(app), store, clock


def auth0_claims(sub: str, clock: Clock, **extra: object) -> dict:
    claims = {
        "sub": sub,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(clock.t),
        "exp": int(clock.t) + 3600,
    }
    claims.update(extra)
    return claims


def seed_owner(
    store: MemoryIdentityStore, user_id: str, tenant_id: str, *, name: str | None = None
) -> None:
    store.seed_tenant(
        tenant_id=tenant_id,
        slug=f"slug-{tenant_id}",
        name=name or f"Tienda {tenant_id}",
        store_id=f"store-{tenant_id}",
        store_name=name or f"Tienda {tenant_id}",
    )
    store.upsert_membership(user_id, tenant_id, "owner", True, True, True, True)


def owner_bearer(client: TestClient, store: MemoryIdentityStore, clock: Clock, sub: str, tenant_id: str):
    """Resolve the user, seed an owner membership, and return a bearer token."""
    token = make_token(auth0_claims(sub, clock, email=f"{sub}@example.com"))
    user = store.find_user("auth0", sub)
    if user is None:
        client.get("/api/me/memberships", headers={"Authorization": f"Bearer {token}"})
        user = store.find_user("auth0", sub)
        assert user is not None
    seed_owner(store, user.id, tenant_id)
    return token, user.id


def cookie_value(response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(name + "="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


def select_store(client: TestClient, token: str, tenant_id: str) -> str:
    response = client.post(
        "/api/session/store",
        json={"tenantId": tenant_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrfToken"]


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


def test_alg_none_rejected():
    validator = build_validator()
    token = make_none_token(
        {"sub": "s", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 3600}
    )
    with pytest.raises(UnsupportedAlgorithmError):
        validator.validate_access_token(token)


def test_expired_token_rejected():
    validator = build_validator(clock_skew=0.0)
    token = make_token(
        {
            "sub": "s",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": int(time.time()) - 3600,
            "exp": int(time.time()) - 100,
        }
    )
    with pytest.raises(TokenExpiredError):
        validator.validate_access_token(token)


def test_wrong_audience_rejected():
    validator = build_validator()
    token = make_token(
        {
            "sub": "s",
            "iss": ISSUER,
            "aud": "some-other-api",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )
    with pytest.raises(InvalidAudienceError):
        validator.validate_access_token(token)


def test_wrong_issuer_rejected():
    validator = build_validator()
    token = make_token(
        {
            "sub": "s",
            "iss": "https://evil.example/",
            "aud": AUDIENCE,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )
    with pytest.raises(InvalidIssuerError):
        validator.validate_access_token(token)


def test_valid_token_maps_auth0_sub():
    validator = build_validator()
    token = make_token(
        {
            "sub": "auth0|owner-1",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "email": "owner@example.com",
        }
    )
    validated = validator.validate_access_token(token)
    assert validated.idp == "auth0"
    assert validated.external_sub == "auth0|owner-1"
    assert validated.email == "owner@example.com"


def test_entra_token_maps_oid_tid():
    validator = build_entra_validator()
    token = make_token(
        {
            "oid": "1111-2222",
            "tid": "tenant-guid",
            "iss": ENTRA_ISSUER,
            "aud": ENTRA_AUDIENCE,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
    )
    validated = validator.validate_access_token(token)
    assert validated.idp == "entra"
    assert validated.external_sub == entra_external_sub("1111-2222", "tenant-guid")


# ---------------------------------------------------------------------------
# Entra staff has no business membership
# ---------------------------------------------------------------------------


def test_entra_staff_gets_no_membership_and_cannot_select_tenant():
    store = MemoryIdentityStore()
    clock = Clock()
    client, store, clock = make_app(store=store, clock=clock, validator=build_entra_validator())
    store.seed_tenant(tenant_id="t_A", slug="a", name="Tienda Aurora", store_id="s_A")

    token = make_token(
        {
            "oid": "staff-oid",
            "tid": "tenant-guid",
            "iss": ENTRA_ISSUER,
            "aud": ENTRA_AUDIENCE,
            "iat": int(clock.t),
            "exp": int(clock.t) + 3600,
        }
    )

    memberships = client.get(
        "/api/me/memberships", headers={"Authorization": f"Bearer {token}"}
    )
    assert memberships.status_code == 200
    assert memberships.json()["items"] == []

    # Knowing the tenant id is not enough: selection is rejected.
    selected = client.post(
        "/api/session/store",
        json={"tenantId": "t_A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert selected.status_code == 403


# ---------------------------------------------------------------------------
# Challenge: one-time redemption and expiry
# ---------------------------------------------------------------------------


def test_challenge_one_time_redemption():
    client, store, clock = make_app()
    token, user_id = owner_bearer(client, store, clock, "owner-1", "t_A")
    device_id = "device-1"

    registered = client.post(
        "/api/auth/device/register",
        json={"deviceId": device_id, "publicKey": DEVICE_PUB, "label": "Pixel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert registered.status_code == 200, registered.text

    created = client.post("/api/auth/challenge", json={"intent": "browser_login"})
    assert created.status_code == 200, created.text
    body = created.json()
    challenge_id = body["challengeId"]
    code = body["code"]
    browser_cookie = cookie_value(created, "abarpay_challenge")
    assert browser_cookie

    challenge = store.get_challenge(challenge_id)
    assert challenge is not None
    payload = challenge_signature_payload(challenge, "t_A")
    signature = sign_device(DEVICE_PRIV, payload)

    approved = client.post(
        f"/api/auth/challenge/{challenge_id}/approve",
        json={"deviceSignature": signature, "code": code, "deviceId": device_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approved.status_code == 200, approved.text

    state = client.get(f"/api/auth/challenge/{challenge_id}")
    assert state.json()["status"] == "approved"

    exchanged = client.post(f"/api/auth/challenge/{challenge_id}/exchange")
    assert exchanged.status_code == 200, exchanged.text
    assert exchanged.json()["tenant"]["id"] == "t_A"
    assert exchanged.json()["user"]["id"] == user_id
    assert exchanged.json()["user"]["email"] == "owner-1@example.com"

    # The redemption code is consumed exactly once: replaying the original
    # cookie against an already-consumed challenge is rejected.
    client.cookies.set("abarpay_challenge", browser_cookie)
    second = client.post(f"/api/auth/challenge/{challenge_id}/exchange")
    assert second.status_code == 409


def test_challenge_expires_after_120_seconds():
    client, store, clock = make_app()
    token, user_id = owner_bearer(client, store, clock, "owner-1", "t_A")

    client.post(
        "/api/auth/device/register",
        json={"deviceId": "device-1", "publicKey": DEVICE_PUB, "label": "Pixel"},
        headers={"Authorization": f"Bearer {token}"},
    )

    created = client.post("/api/auth/challenge", json={"intent": "browser_login"})
    body = created.json()
    challenge_id = body["challengeId"]
    code = body["code"]

    clock.advance(121)

    challenge = store.get_challenge(challenge_id)
    payload = challenge_signature_payload(challenge, "t_A")
    signature = sign_device(DEVICE_PRIV, payload)

    approved = client.post(
        f"/api/auth/challenge/{challenge_id}/approve",
        json={"deviceSignature": signature, "code": code, "deviceId": "device-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approved.status_code == 409


def test_challenge_rejects_wrong_code():
    client, store, clock = make_app()
    token, user_id = owner_bearer(client, store, clock, "owner-1", "t_A")

    client.post(
        "/api/auth/device/register",
        json={"deviceId": "device-1", "publicKey": DEVICE_PUB, "label": "Pixel"},
        headers={"Authorization": f"Bearer {token}"},
    )

    created = client.post("/api/auth/challenge", json={"intent": "browser_login"})
    challenge_id = created.json()["challengeId"]
    challenge = store.get_challenge(challenge_id)
    signature = sign_device(DEVICE_PRIV, challenge_signature_payload(challenge, "t_A"))

    approved = client.post(
        f"/api/auth/challenge/{challenge_id}/approve",
        json={"deviceSignature": signature, "code": "000000", "deviceId": "device-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approved.status_code == 403


def test_device_register_and_revoke():
    client, store, clock = make_app()
    token, user_id = owner_bearer(client, store, clock, "owner-1", "t_A")

    registered = client.post(
        "/api/auth/device/register",
        json={"deviceId": "device-1", "publicKey": DEVICE_PUB, "label": "Pixel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert registered.status_code == 200
    assert store.get_device(user_id, "device-1") is not None

    revoked = client.delete(
        "/api/auth/devices/device-1", headers={"Authorization": f"Bearer {token}"}
    )
    assert revoked.status_code == 200
    assert store.get_device(user_id, "device-1") is None


# ---------------------------------------------------------------------------
# Invites: hash-only storage, role non-elevation, last owner
# ---------------------------------------------------------------------------


def test_invite_stored_hash_only():
    client, store, clock = make_app()
    token, user_id = owner_bearer(client, store, clock, "owner-1", "t_A")
    csrf = select_store(client, token, "t_A")

    created = client.post(
        "/api/tenant/members/invite",
        json={"email": "emp@example.com", "role": "employee", "canSell": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200, created.text
    token_value = created.json()["token"]

    # The plaintext token is never persisted; only its SHA-256.
    assert token_value not in store.invites
    assert hash_invite_token(token_value) in store.invites
    assert sha256_hex(token_value) in store.invites
    assert store.invites[hash_invite_token(token_value)].role == "employee"


def test_acceptance_cannot_elevate_role():
    client, store, clock = make_app()
    token, owner_id = owner_bearer(client, store, clock, "owner-1", "t_A")
    csrf = select_store(client, token, "t_A")

    created = client.post(
        "/api/tenant/members/invite",
        json={"email": "emp@example.com", "role": "employee", "canSell": True},
        headers={"X-CSRF-Token": csrf},
    )
    invite_token = created.json()["token"]

    # Employee authenticates and accepts; the role comes from the invite.
    employee_clock = clock
    emp_token = make_token(auth0_claims("employee-1", employee_clock, email="emp@example.com"))
    accepted = client.post(
        f"/api/tenant/members/invites/{invite_token}/accept",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["role"] == "employee"

    emp_user = store.find_user("auth0", "employee-1")
    assert emp_user is not None
    membership = store.get_membership(emp_user.id, "t_A")
    assert membership is not None
    assert membership.role == "employee"

    # Acceptance is one-time: a second user cannot accept the same token.
    other_token = make_token(auth0_claims("employee-2", employee_clock))
    second = client.post(
        f"/api/tenant/members/invites/{invite_token}/accept",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert second.status_code == 409


def test_invite_owner_role_rejected():
    client, store, clock = make_app()
    token, user_id = owner_bearer(client, store, clock, "owner-1", "t_A")
    csrf = select_store(client, token, "t_A")

    created = client.post(
        "/api/tenant/members/invite",
        json={"email": "x@example.com", "role": "owner", "canSell": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 403


# ---------------------------------------------------------------------------
# Membership isolation and last-owner protection
# ---------------------------------------------------------------------------


def test_membership_isolation_cannot_select_foreign_tenant():
    client, store, clock = make_app()
    token_a, user_a = owner_bearer(client, store, clock, "owner-a", "t_A")
    token_b, user_b = owner_bearer(client, store, clock, "owner-b", "t_B")

    # A selects its own store and reads its own tenant.
    csrf_a = select_store(client, token_a, "t_A")
    tenant_a = client.get("/api/tenant")
    assert tenant_a.status_code == 200
    assert tenant_a.json()["id"] == "t_A"

    # B knows A's tenant id but has no membership there: rejected.
    foreign = client.post(
        "/api/session/store",
        json={"tenantId": "t_A"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert foreign.status_code == 403

    # B's own tenant is B, never A.
    csrf_b = select_store(client, token_b, "t_B")
    tenant_b = client.get("/api/tenant")
    assert tenant_b.json()["id"] == "t_B"


def test_last_owner_protected():
    client, store, clock = make_app()
    token, user_id = owner_bearer(client, store, clock, "owner-1", "t_A")
    csrf = select_store(client, token, "t_A")

    # The only owner cannot deactivate themselves.
    deleted = client.delete(
        f"/api/tenant/members/{user_id}", headers={"X-CSRF-Token": csrf}
    )
    assert deleted.status_code == 403

    # Nor demote themselves.
    patched = client.patch(
        f"/api/tenant/members/{user_id}",
        json={"role": "employee"},
        headers={"X-CSRF-Token": csrf},
    )
    assert patched.status_code == 403
