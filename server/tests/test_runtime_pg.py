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
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from server.auth import AuthConfig, Issuer, StaticJwksProvider, TokenValidator
from server.identity import SESSION_HEADER_NAME
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
            for name in ("001_schema.sql", "002_seed.sql", "003_onboarding.sql"):
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
