"""Production runtime vertical slice: PG-backed init + verified identity.

Proves the first vertical slice through create_production_app against an
isolated, ephemeral PostgreSQL cluster (its own port and unix socket dir, never
the default 5432 dev cluster). Two tenants sign up with two synthetic RS256
tokens (StaticJwksProvider, no network), and tenant/role are derived only from
the verified identity. Fail-closed startup is asserted too.

The cluster is created with initdb/pg_ctl; when those binaries are absent the
positive tests skip. The config-level fail-closed tests still run because they
need no PostgreSQL.
"""

from __future__ import annotations

import base64
import getpass
import secrets
import shutil
import socket
import subprocess
import time
import urllib.parse
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from server.auth import AuthConfig, Issuer, StaticJwksProvider, TokenValidator
from server.identity import CHALLENGE_COOKIE_NAME, SESSION_HEADER_NAME
from server.db_pg import set_tenant_context
from server.runtime import create_production_app

REPO_ROOT = Path(__file__).resolve().parents[2]

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")

ISSUER = "https://test.auth0.example/"
AUDIENCE = "abarpay-api"
KID = "token-kid"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_rsa_key(kid: str) -> tuple[str, dict]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    numbers = key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
    }
    return priv, jwk


_PRIV, _JWK = _make_rsa_key(KID)


def make_token(sub: str) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "email": sub + "@abarpay.test",
        "name": "Dueño " + sub,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(claims, _PRIV, algorithm="RS256", headers={"kid": KID})


def build_validator() -> TokenValidator:
    return TokenValidator(
        [Issuer(issuer=ISSUER, audience=AUDIENCE, kind="auth0")],
        providers={ISSUER: StaticJwksProvider({KID: _JWK})},
        clock_skew_seconds=0.0,
    )


def prod_config() -> AuthConfig:
    return AuthConfig(
        issuers=(Issuer(issuer=ISSUER, audience=AUDIENCE, kind="auth0"),),
        secure_cookies=False,
        cookie_samesite="lax",
    )


def _prod_env(dsn: str) -> dict:
    return {
        "ABARPAY_RUNTIME": "production",
        "MODO_DEMO": "false",
        "ABARPAY_PG_DSN": dsn,
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_cluster(base: Path) -> dict:
    base.mkdir(parents=True, exist_ok=True)
    datadir = base / "data"
    datadir.mkdir()
    sockdir = Path("/tmp") / ("abarpay-pg-sock-" + uuid.uuid4().hex[:8])
    sockdir.mkdir()
    user = getpass.getuser()
    port = _free_port()
    subprocess.run(
        [INITDB, "-D", str(datadir), "-U", user, "-A", "trust",
         "--no-locale", "-E", "UTF8", "--no-sync"],
        check=True, capture_output=True, text=True,
    )
    logfile = base / "postgres.log"
    subprocess.run(
        [PG_CTL, "-D", str(datadir), "-l", str(logfile), "-o",
         f"-p {port} -k {sockdir} -h 127.0.0.1", "-w", "start"],
        check=True, capture_output=True, text=True,
    )
    superuser_dsn = f"host=127.0.0.1 port={port} dbname=postgres user={user}"
    service_dsn = f"host=127.0.0.1 port={port} dbname=postgres user=abarpay_service"
    return {
        "datadir": datadir,
        "sockdir": sockdir,
        "superuser_dsn": superuser_dsn,
        "service_dsn": service_dsn,
    }


def _stop_cluster(cluster: dict) -> None:
    subprocess.run(
        [PG_CTL, "-D", str(cluster["datadir"]), "-m", "fast", "-w", "stop"],
        capture_output=True, text=True,
    )
    shutil.rmtree(cluster["sockdir"], ignore_errors=True)


def _apply_migrations(dsn: str) -> None:
    import psycopg

    conn = psycopg.connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            for name in ("001_schema.sql", "002_seed.sql", "003_onboarding.sql", "004_owner_phone.sql"):
                cur.execute((REPO_ROOT / "migrations" / name).read_text(encoding="utf-8"))
    finally:
        conn.close()


def _provision_service_role(superuser_dsn: str) -> None:
    import psycopg

    conn = psycopg.connect(superuser_dsn, autocommit=True)
    try:
        conn.execute("CREATE ROLE abarpay_service LOGIN")
        conn.execute("GRANT abarpay_app TO abarpay_service")
    finally:
        conn.close()


@pytest.fixture(scope="session")
def pg_cluster(tmp_path_factory):
    if not INITDB or not PG_CTL:
        pytest.skip("initdb/pg_ctl not available")
    cluster = _start_cluster(tmp_path_factory.mktemp("pgcluster"))
    yield cluster
    _stop_cluster(cluster)


@pytest.fixture(scope="session")
def migrated_dsn(pg_cluster):
    _apply_migrations(pg_cluster["superuser_dsn"])
    _provision_service_role(pg_cluster["superuser_dsn"])
    return pg_cluster["service_dsn"]


def test_two_tenant_signup_and_verified_identity(migrated_dsn):
    app = create_production_app(
        env=_prod_env(migrated_dsn),
        auth_config=prod_config(),
        validator=build_validator(),
    )
    with TestClient(app) as client:
        token_a = make_token("owner-a")
        resp = client.post(
            "/api/signup",
            json={"name": "Dueño A", "storeName": "Tienda A"},
            headers={"Authorization": "Bearer " + token_a},
        )
        assert resp.status_code == 200, resp.text
        a = resp.json()
        assert a["tenant"]["name"] == "Tienda A"
        assert a["store"]["name"] == "Tienda A"
        assert a["membership"]["role"] == "owner"

        token_b = make_token("owner-b")
        resp = client.post(
            "/api/signup",
            json={"name": "Dueño B", "storeName": "Tienda B"},
            headers={"Authorization": "Bearer " + token_b},
        )
        assert resp.status_code == 200, resp.text
        b = resp.json()

        # Durable, isolated signup: distinct persisted tenants and owners.
        assert a["tenant"]["id"] != b["tenant"]["id"]
        assert a["user"]["id"] != b["user"]["id"]

        # Tenant/role are derived only from the verified identity.
        items_a = client.get(
            "/api/me/memberships", headers={"Authorization": "Bearer " + token_a}
        ).json()["items"]
        assert [m["tenantId"] for m in items_a] == [a["tenant"]["id"]]
        assert items_a[0]["role"] == "owner"

        items_b = client.get(
            "/api/me/memberships", headers={"Authorization": "Bearer " + token_b}
        ).json()["items"]
        assert [m["tenantId"] for m in items_b] == [b["tenant"]["id"]]
        assert items_b[0]["role"] == "owner"

        # Cross-tenant store selection is rejected; own selection succeeds.
        resp = client.post(
            "/api/session/store",
            json={"tenantId": b["tenant"]["id"]},
            headers={"Authorization": "Bearer " + token_a},
        )
        assert resp.status_code == 403

        resp = client.post(
            "/api/session/store",
            json={"tenantId": a["tenant"]["id"]},
            headers={"Authorization": "Bearer " + token_a},
        )
        assert resp.status_code == 200, resp.text
        session_token = resp.json()["sessionToken"]

        # The selected tenant is served back from the verified session.
        tenant = client.get(
            "/api/tenant", headers={SESSION_HEADER_NAME: session_token}
        ).json()
        assert tenant["id"] == a["tenant"]["id"]
        assert tenant["name"] == "Tienda A"


def test_health_reports_production_pg(migrated_dsn):
    app = create_production_app(
        env=_prod_env(migrated_dsn),
        auth_config=prod_config(),
        validator=build_validator(),
    )
    with TestClient(app) as client:
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["runtime"] == "production"
        assert body["pg"] == "ok"


def test_fail_closed_demo_mode():
    with pytest.raises(RuntimeError, match="MODO_DEMO"):
        create_production_app(
            env={"ABARPAY_RUNTIME": "production", "MODO_DEMO": "true",
                 "ABARPAY_PG_DSN": "host=127.0.0.1"},
            auth_config=prod_config(),
            validator=build_validator(),
        )


def test_fail_closed_missing_dsn():
    with pytest.raises(RuntimeError, match="ABARPAY_PG_DSN"):
        create_production_app(
            env={"ABARPAY_RUNTIME": "production", "MODO_DEMO": "false"},
            auth_config=prod_config(),
            validator=build_validator(),
        )


def test_fail_closed_no_oidc_issuer():
    with pytest.raises(RuntimeError, match="OIDC issuer"):
        create_production_app(
            env={"ABARPAY_RUNTIME": "production", "MODO_DEMO": "false",
                 "ABARPAY_PG_DSN": "host=127.0.0.1"},
        )


def test_fail_closed_unmigrated_schema(tmp_path):
    if not INITDB or not PG_CTL:
        pytest.skip("initdb/pg_ctl not available")
    cluster = _start_cluster(tmp_path / "fresh")
    try:
        with pytest.raises(RuntimeError):
            create_production_app(
                env=_prod_env(cluster["service_dsn"]),
                auth_config=prod_config(),
                validator=build_validator(),
            )
    finally:
        _stop_cluster(cluster)

def test_health_degraded_returns_503(migrated_dsn):
    app = create_production_app(
        env=_prod_env(migrated_dsn),
        auth_config=prod_config(),
        validator=build_validator(),
    )
    app.state.pool.close()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["pg"] == "error"


def test_fail_closed_superuser_login(tmp_path):
    if not INITDB or not PG_CTL:
        pytest.skip("initdb/pg_ctl not available")
    cluster = _start_cluster(tmp_path / "super")
    try:
        _apply_migrations(cluster["superuser_dsn"])
        with pytest.raises(RuntimeError, match="login principal"):
            create_production_app(
                env=_prod_env(cluster["superuser_dsn"]),
                auth_config=prod_config(),
                validator=build_validator(),
            )
    finally:
        _stop_cluster(cluster)


NL = chr(10)
EMAIL_CLAIM = "https://abarpay.app/email"
NAME_CLAIM = "https://abarpay.app/name"


def make_token_ns(sub: str) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "iss": ISSUER,
        "aud": AUDIENCE,
        EMAIL_CLAIM: sub + "@abarpay.test",
        NAME_CLAIM: "Dueño " + sub,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(claims, _PRIV, algorithm="RS256", headers={"kid": KID})


def build_validator_ns() -> TokenValidator:
    issuer = Issuer(
        issuer=ISSUER,
        audience=AUDIENCE,
        kind="auth0",
        email_claim=EMAIL_CLAIM,
        name_claim=NAME_CLAIM,
    )
    return TokenValidator(
        [issuer],
        providers={ISSUER: StaticJwksProvider({KID: _JWK})},
        clock_skew_seconds=0.0,
    )


def prod_config_ns() -> AuthConfig:
    return AuthConfig(
        issuers=(
            Issuer(
                issuer=ISSUER,
                audience=AUDIENCE,
                kind="auth0",
                email_claim=EMAIL_CLAIM,
                name_claim=NAME_CLAIM,
            ),
        ),
        secure_cookies=False,
        cookie_samesite="lax",
    )


def _make_device_key() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return priv, pub


def sign_device(private_pem: str, message: str) -> str:
    key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    signature = key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def parse_qr(qr: str) -> dict:
    parsed = urllib.parse.urlparse(qr)
    query = urllib.parse.parse_qs(parsed.query)
    return {
        "id": parsed.path.rstrip("/").split("/")[-1],
        "code": query["code"][0],
        "nonce": query["nonce"][0],
        "exp": int(query["exp"][0]),
        "intent": query["intent"][0],
    }


def cookie_value(response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(name + "="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


def _qr_login(client, token, device_id, device_priv, device_pub, tenant_id):
    registered = client.post(
        "/api/auth/device/register",
        json={"deviceId": device_id, "publicKey": device_pub, "label": "Pixel"},
        headers={"Authorization": "Bearer " + token},
    )
    assert registered.status_code == 200, registered.text

    created = client.post("/api/auth/challenge", json={"intent": "browser_login"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body.get("qrSvg"), "qrSvg debe estar presente en el reto"
    qr = parse_qr(body["qr"])
    assert qr["id"] == body["challengeId"]
    browser_cookie = cookie_value(created, CHALLENGE_COOKIE_NAME)
    assert browser_cookie

    payload = NL.join([qr["id"], qr["nonce"], str(qr["exp"]), qr["intent"], tenant_id])
    signature = sign_device(device_priv, payload)

    approved = client.post(
        "/api/auth/challenge/" + qr["id"] + "/approve",
        json={"deviceSignature": signature, "code": qr["code"], "deviceId": device_id},
        headers={"Authorization": "Bearer " + token},
    )
    assert approved.status_code == 200, approved.text

    exchanged = client.post("/api/auth/challenge/" + qr["id"] + "/exchange")
    assert exchanged.status_code == 200, exchanged.text
    data = exchanged.json()
    assert data["tenant"]["id"] == tenant_id
    return qr["id"], data["csrfToken"], browser_cookie


def test_namespaced_email_claim():
    validator = build_validator_ns()
    now = int(time.time())
    root = jwt.encode(
        {"sub": "u1", "iss": ISSUER, "aud": AUDIENCE, "email": "root@abarpay.test",
         "iat": now, "exp": now + 3600},
        _PRIV, algorithm="RS256", headers={"kid": KID},
    )
    assert validator.validate_access_token(root).email == "root@abarpay.test"

    namespaced = jwt.encode(
        {"sub": "u1", "iss": ISSUER, "aud": AUDIENCE, EMAIL_CLAIM: "ns@abarpay.test",
         "iat": now, "exp": now + 3600},
        _PRIV, algorithm="RS256", headers={"kid": KID},
    )
    assert validator.validate_access_token(namespaced).email == "ns@abarpay.test"


def test_owner_journey_two_tenants(migrated_dsn):
    app = create_production_app(
        env=_prod_env(migrated_dsn),
        auth_config=prod_config_ns(),
        validator=build_validator_ns(),
    )
    client_a = TestClient(app)
    client_b = TestClient(app)
    device_a_priv, device_a_pub = _make_device_key()
    device_b_priv, device_b_pub = _make_device_key()
    try:
        # ---- tenant A: signup via namespaced-email OIDC token ----
        token_a = make_token_ns("journey-a")
        resp = client_a.post(
            "/api/signup",
            json={"name": "Dueño A", "storeName": "Tienda A"},
            headers={"Authorization": "Bearer " + token_a},
        )
        assert resp.status_code == 200, resp.text
        a = resp.json()
        assert a["user"]["email"] == "journey-a@abarpay.test"
        assert a["membership"]["role"] == "owner"

        # ---- QR binding + one-time exchange -> owner session ----
        challenge_a, csrf_a, cookie_a = _qr_login(
            client_a, token_a, "device-a", device_a_priv, device_a_pub, a["tenant"]["id"]
        )

        # one-time redemption: replaying the original challenge cookie fails
        client_a.cookies.set(CHALLENGE_COOKIE_NAME, cookie_a)
        assert client_a.post("/api/auth/challenge/" + challenge_a + "/exchange").status_code == 409

        # trusted session derives tenant from verified identity
        tenant_a = client_a.get("/api/tenant").json()
        assert tenant_a["id"] == a["tenant"]["id"]
        assert tenant_a["name"] == "Tienda A"

        # CSRF is required for a cookie-session state change
        assert client_a.post(
            "/api/catalog", json={"name": "X", "unit": "pieza", "priceCents": 1}
        ).status_code == 403

        # ---- add a product + identical-SKU barcode ----
        resp = client_a.post(
            "/api/catalog",
            json={"name": "Refresco", "unit": "pieza", "priceCents": 1500, "stockMilli": 10000},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert resp.status_code == 200, resp.text
        product_a = resp.json()
        assert product_a["name"] == "Refresco"

        resp = client_a.post(
            "/api/barcode/link",
            json={"productId": product_a["id"], "code": "7501000000001"},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert resp.status_code == 200, resp.text

        # ---- first cash sale with Idempotency-Key ----
        idem_a = str(uuid.uuid4())
        resp = client_a.post(
            "/api/sales",
            json={"items": [{"productId": product_a["id"], "qtyMilli": 1000}], "cashReceivedCents": 1500},
            headers={"X-CSRF-Token": csrf_a, "Idempotency-Key": idem_a},
        )
        assert resp.status_code == 200, resp.text
        sale_a = resp.json()
        assert sale_a["status"] == "paid_cash"
        assert sale_a["totalCents"] == 1500
        assert sale_a["changeCents"] == 0

        # idempotent replay returns the prior receipt (same key, same saleId)
        replay = client_a.post(
            "/api/sales",
            json={"items": [{"productId": product_a["id"], "qtyMilli": 1000}], "cashReceivedCents": 1500},
            headers={"X-CSRF-Token": csrf_a, "Idempotency-Key": idem_a},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == sale_a["id"]

        # changed body with the same key is rejected
        changed = client_a.post(
            "/api/sales",
            json={"items": [{"productId": product_a["id"], "qtyMilli": 2000}], "cashReceivedCents": 3000},
            headers={"X-CSRF-Token": csrf_a, "Idempotency-Key": idem_a},
        )
        assert changed.status_code == 409

        # visible receipt
        receipt = client_a.get("/api/sales/" + sale_a["id"]).json()
        assert receipt["id"] == sale_a["id"]
        assert len(receipt["items"]) == 1
        assert receipt["items"][0]["name"] == "Refresco"

        # exactly one ledger payment and one inventory movement
        with app.state.pool.connection() as conn:
            set_tenant_context(conn, tenant_id=a["tenant"]["id"], user_id="")
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM payments WHERE sale_id = %s::uuid", (sale_a["id"],))
                assert cur.fetchone()[0] == 1
                cur.execute("SELECT count(*) FROM inventory_movements WHERE sale_id = %s::uuid", (sale_a["id"],))
                assert cur.fetchone()[0] == 1

        # ---- tenant B ----
        token_b = make_token_ns("journey-b")
        resp = client_b.post(
            "/api/signup",
            json={"name": "Dueño B", "storeName": "Tienda B"},
            headers={"Authorization": "Bearer " + token_b},
        )
        assert resp.status_code == 200, resp.text
        b = resp.json()
        _challenge_b, csrf_b, _cookie_b = _qr_login(
            client_b, token_b, "device-b", device_b_priv, device_b_pub, b["tenant"]["id"]
        )

        # identical SKU in two stores (per-tenant barcode uniqueness)
        resp = client_b.post(
            "/api/catalog",
            json={"name": "Refresco", "unit": "pieza", "priceCents": 2000, "stockMilli": 5000},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert resp.status_code == 200, resp.text
        product_b = resp.json()
        resp = client_b.post(
            "/api/barcode/link",
            json={"productId": product_b["id"], "code": "7501000000001"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert resp.status_code == 200, resp.text

        idem_b = str(uuid.uuid4())
        resp = client_b.post(
            "/api/sales",
            json={"items": [{"productId": product_b["id"], "qtyMilli": 1000}], "cashReceivedCents": 2000},
            headers={"X-CSRF-Token": csrf_b, "Idempotency-Key": idem_b},
        )
        assert resp.status_code == 200, resp.text
        sale_b = resp.json()
        assert sale_b["totalCents"] == 2000

        # ---- B1-style isolation ----
        catalog_a = client_a.get("/api/catalog").json()["items"]
        assert [p["id"] for p in catalog_a] == [product_a["id"]]
        catalog_b = client_b.get("/api/catalog").json()["items"]
        assert [p["id"] for p in catalog_b] == [product_b["id"]]

        assert client_a.get("/api/sales/" + sale_b["id"]).status_code == 404
        resp = client_a.post(
            "/api/sales",
            json={"items": [{"productId": product_b["id"], "qtyMilli": 1000}]},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert resp.status_code == 404
    finally:
        app.state.pool.close()


def test_owner_phone_enrollment_and_qr_without_oidc(migrated_dsn, pg_cluster):
    import psycopg
    from phonenumbers import PhoneNumberType, example_number_for_type

    from server.owner_phone import PhoneSettings

    inbox = []
    app = create_production_app(
        env={**_prod_env(migrated_dsn), "SECURE_COOKIES": "false"},
        phone_settings=PhoneSettings(secrets.token_bytes(32), lambda number, code: inbox.append((number, code))),
    )
    prefix = "/api/auth/owner/"
    phone = str(example_number_for_type("MX", PhoneNumberType.MOBILE).national_number)
    key, pub = _make_device_key()
    device = str(uuid.uuid4())

    def send(client, target, public_key):
        return client.post(
            prefix + "phone/start",
            json={"phone": phone, "deviceId": target, "publicKey": public_key},
        )

    with TestClient(app) as client, TestClient(app) as other:
        started = send(client, device, pub)
        assert started.status_code == 200
        assert inbox[0][0] == "+52" + phone
        assert set(started.json()) == {"challengeId", "retryAfterSeconds"}
        challenge = started.json()["challengeId"]
        otp_body = {
            "challengeId": challenge,
            "signature": sign_device(key, f"abarpay-owner-enroll:{challenge}"),
            "code": inbox[0][1],
        }
        assert send(client, device, pub).status_code == 429
        malformed = client.post(prefix + "phone/verify", json={**otp_body, "code": "entrada inválida"})
        assert malformed.status_code == 422
        assert "entrada inválida" not in malformed.text
        wrong_code = "000000" if otp_body["code"] != "000000" else "000001"
        assert client.post(prefix + "phone/verify", json={**otp_body, "code": wrong_code}).status_code == 401
        assert client.post(prefix + "phone/verify", json={**otp_body, "signature": "invalid"}).status_code == 401
        verified = client.post(prefix + "phone/verify", json=otp_body)
        assert verified.status_code == 200
        assert verified.headers["Cache-Control"] == "no-store"
        assert client.post(prefix + "phone/verify", json=otp_body).status_code == 401
        auth = {"Authorization": "Bearer " + verified.json()["accessToken"]}

        signup = {"name": "Dueña de prueba", "storeName": "Tienda simulada"}
        first = client.post("/api/signup", headers=auth, json=signup)
        assert first.status_code == 200
        tenant = first.json()["tenant"]
        assert first.json()["user"]["email"] == ""
        assert client.post("/api/signup", headers=auth, json=signup).json()["tenant"] == tenant
        assert client.post("/api/session/store", headers=auth, json={"tenantId": tenant["id"]}).status_code == 403
        assert client.post(
            "/api/auth/device/register", headers=auth, json={"deviceId": device, "publicKey": pub}
        ).status_code == 403

        challenge = client.post(prefix + "device/start", json={"deviceId": device}).json()["challengeId"]
        proof = {"challengeId": challenge, "signature": sign_device(key, f"abarpay-owner-signin:{challenge}")}
        reentry = client.post(prefix + "device/verify", json=proof)
        assert reentry.status_code == 200
        assert len(inbox) == 1
        assert client.post(prefix + "device/verify", json=proof).status_code == 401
        auth = {"Authorization": "Bearer " + reentry.json()["accessToken"]}

        # Simulate the cooldown without sleeping or changing the challenge TTL.
        with psycopg.connect(pg_cluster["superuser_dsn"]) as conn:
            conn.execute("UPDATE owner_auth.challenges SET created_at = created_at - interval '31 seconds'")
        other_key, other_pub = _make_device_key()
        other_device = str(uuid.uuid4())
        other_begin = send(other, other_device, other_pub)
        assert other_begin.status_code == 200
        other_challenge = other_begin.json()["challengeId"]
        assert other.post(prefix + "phone/verify", json={
            "challengeId": other_challenge,
            "signature": sign_device(other_key, f"abarpay-owner-enroll:{other_challenge}"),
            "code": inbox[1][1],
        }).status_code == 409

        created = client.post("/api/auth/challenge", json={"intent": "browser_login"})
        qr = parse_qr(created.json()["qr"])
        approved_path = f"/api/auth/challenge/{qr['id']}/approve"
        exchange_path = f"/api/auth/challenge/{qr['id']}/exchange"
        payload = NL.join([qr["id"], qr["nonce"], str(qr["exp"]), qr["intent"], tenant["id"]])
        approval = {
            "deviceId": device,
            "tenantId": tenant["id"],
            "code": qr["code"],
            "deviceSignature": sign_device(key, payload),
        }
        assert client.post(approved_path, headers=auth, json=approval).status_code == 200
        assert other.post(exchange_path).status_code == 403
        exchanged = client.post(exchange_path)
        assert exchanged.status_code == 200
        assert exchanged.json()["tenant"]["id"] == tenant["id"]
        assert client.get("/api/tenant").json()["id"] == tenant["id"]
        cookie = cookie_value(created, CHALLENGE_COOKIE_NAME)
        client.cookies.set(CHALLENGE_COOKIE_NAME, cookie)
        assert client.post(exchange_path).status_code == 409
