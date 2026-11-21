"""Onboarding and CLABE / bank-account core tests (SIMULADO).

Covers the M1 banking core:

- atomic signup (tenant + store + owner + membership; a new store has ZERO
  demo data),
- first cash sale with NO banking info (the cash path never touches
  bank_accounts),
- bank-account registration with an async status (PENDING -> ACTIVE) and an
  email notification path, labeled SIMULADO,
- collection routing: create_qr sends the tenant's ACTIVE bankAccountId.

No test registers a real account or calls api.pey.mx. The PostgreSQL adapter
test (atomic signup through the signup_tenant SECURITY DEFINER function) is
skipped automatically when the local dev cluster is not reachable, so the
SQLite-only CI stays green.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.onboarding import (  # noqa: E402
    OnboardingService,
    MemoryBankAccountNotifier,
    MemoryOnboardingStore,
    STATUS_ACTIVE,
    STATUS_PENDING,
    validate_clabe,
)
from server.pey import PeyClient  # noqa: E402
from server.routes_onboarding import register as register_onboarding  # noqa: E402

def _make_valid_clabe(first17: str) -> str:
    weights = (3, 7, 1)
    total = sum(int(d) * weights[i % 3] for i, d in enumerate(first17))
    check = (10 - (total % 10)) % 10
    return first17 + str(check)


# Synthetic SIMULADO CLABE (not a real account): only the local 3-7-1 check
# digit is meaningful here; the "CoDi-enabled bank" check belongs to pey. It is
# only ever used against the SIMULADO store - never api.pey.mx.
VALID_CLABE = _make_valid_clabe("01234567890123456")
INVALID_CLABE = VALID_CLABE[:-1] + ("0" if VALID_CLABE[-1] != "0" else "1")


# ---------------------------------------------------------------------------
# CLABE validation
# ---------------------------------------------------------------------------


def test_clabe_validation():
    assert validate_clabe(VALID_CLABE) is True
    # A corrupted check digit is rejected.
    assert validate_clabe(VALID_CLABE[:-1] + ("0" if VALID_CLABE[-1] != "0" else "1")) is False
    assert validate_clabe(INVALID_CLABE) is False  # wrong check digit
    assert validate_clabe("123") is False
    assert validate_clabe(VALID_CLABE[:-1] + "A") is False  # non-digit
    assert validate_clabe("") is False
    assert validate_clabe(None) is False
    # Round-trip: a generated CLABE validates.
    assert validate_clabe(_make_valid_clabe("01234567890123456")) is True


# ---------------------------------------------------------------------------
# Atomic signup (SIMULADO memory store)
# ---------------------------------------------------------------------------


def test_atomic_signup_creates_tenant_store_owner_membership():
    store = MemoryOnboardingStore()
    service = OnboardingService(store)
    result = service.signup(
        email="rosa@abarpay.test", owner_name="Doña Rosa", store_name="Tienda Rosa"
    )

    assert result.tenant_id
    assert result.store_id
    assert result.user_id

    membership = store.get_membership(result.user_id, result.tenant_id)
    assert membership is not None
    assert membership.role == "owner"
    assert membership.active is True
    assert membership.can_sell and membership.can_fiado and membership.can_inventory

    tenant = store.get_tenant(result.tenant_id)
    assert tenant is not None
    assert tenant.name == "Tienda Rosa"
    assert tenant.status == "active"

    store_rec = store.get_store(result.tenant_id)
    assert store_rec is not None
    assert store_rec.tenant_id == result.tenant_id
    assert store_rec.name == "Tienda Rosa"


def test_new_store_has_zero_demo_data():
    store = MemoryOnboardingStore()
    service = OnboardingService(store)
    result = service.signup(
        email="beta@abarpay.test", owner_name="Beta", store_name="Tienda Beta"
    )

    # A brand-new store is seeded clean: no catalog, no foreign staff - only
    # the single owner membership created by the signup.
    assert store.count_products(result.tenant_id) == 0
    assert store.count_members(result.tenant_id) == 1


def test_signup_requires_email_name_and_store():
    service = OnboardingService(MemoryOnboardingStore())
    with pytest.raises(Exception) as exc:
        service.signup(email="", owner_name="Rosa", store_name="Tienda")
    assert "correo" in str(exc.value)
    with pytest.raises(Exception):
        service.signup(email="r@x.test", owner_name="", store_name="Tienda")
    with pytest.raises(Exception):
        service.signup(email="r@x.test", owner_name="Rosa", store_name="")


# ---------------------------------------------------------------------------
# Bank-account async status + notification (SIMULADO)
# ---------------------------------------------------------------------------


def test_bank_account_async_status_and_notification():
    store = MemoryOnboardingStore()
    notifier = MemoryBankAccountNotifier()
    service = OnboardingService(store, notifier=notifier)
    result = service.signup(
        email="rosa@abarpay.test", owner_name="Rosa", store_name="Tienda Rosa"
    )

    account = service.register_bank_account(
        actor_user_id=result.user_id,
        tenant_id=result.tenant_id,
        alias="Ventas",
        name="Tienda Rosa S.A. de C.V.",
        clabe=VALID_CLABE,
        entity="BUSINESS",
    )
    # Async: a freshly created account is NOT active yet.
    assert account.status == STATUS_PENDING
    assert account.simulated is True
    assert account.last4 == VALID_CLABE[-4:]
    assert account.pey_account_id is None

    # A pending account is not the collection target.
    assert service.resolve_active_bank_account(result.tenant_id) is None

    # Creation triggered a notification (SIMULADO email path).
    assert notifier.sent[-1] == ("rosa@abarpay.test", account.id, STATUS_PENDING)

    activated = service.activate_bank_account(
        actor_user_id=result.user_id,
        tenant_id=result.tenant_id,
        bank_account_id=account.id,
    )
    assert activated.status == STATUS_ACTIVE
    assert activated.activated_at is not None
    assert notifier.sent[-1] == ("rosa@abarpay.test", account.id, STATUS_ACTIVE)

    # Now the active account is the collection target.
    active = service.resolve_active_bank_account(result.tenant_id)
    assert active is not None
    assert active.id == account.id


def test_bank_account_activation_is_idempotent_and_scoped():
    store = MemoryOnboardingStore()
    service = OnboardingService(store)
    result = service.signup(
        email="a@abarpay.test", owner_name="A", store_name="Tienda A"
    )
    account = service.register_bank_account(
        actor_user_id=result.user_id,
        tenant_id=result.tenant_id,
        alias="V",
        name="A SA",
        clabe=VALID_CLABE,
    )
    service.activate_bank_account(
        actor_user_id=result.user_id,
        tenant_id=result.tenant_id,
        bank_account_id=account.id,
    )
    # Idempotent re-activation.
    again = service.activate_bank_account(
        actor_user_id=result.user_id,
        tenant_id=result.tenant_id,
        bank_account_id=account.id,
    )
    assert again.status == STATUS_ACTIVE

    # Another tenant's owner cannot activate this account.
    other = service.signup(email="b@abarpay.test", owner_name="B", store_name="Tienda B")
    from server.onboarding import ForbiddenError

    with pytest.raises(ForbiddenError):
        service.activate_bank_account(
            actor_user_id=other.user_id,
            tenant_id=result.tenant_id,
            bank_account_id=account.id,
        )


def test_bank_account_rejects_invalid_clabe():
    store = MemoryOnboardingStore()
    service = OnboardingService(store)
    result = service.signup(email="r@x.test", owner_name="R", store_name="Tienda R")
    with pytest.raises(Exception) as exc:
        service.register_bank_account(
            actor_user_id=result.user_id,
            tenant_id=result.tenant_id,
            alias="V",
            name="R",
            clabe=INVALID_CLABE,
        )
    assert "CLABE" in str(exc.value)


# ---------------------------------------------------------------------------
# First cash sale needs NO banking info (cash path never touches bank_accounts)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("staff")
def test_cash_sale_works_with_zero_bank_accounts(client):
    # The SQLite demo app has no bank-account state at all. A cash sale must
    # complete without any banking info; only PEY/CoDi charges resolve the
    # tenant's active bank account.
    response = client.post(
        "/api/sales",
        json={
            "employeeId": 2,
            "items": [{"productId": 1, "qtyMilli": 1000}],
            "paymentMethod": "cash",
            "cashReceivedCents": 5000,
        },
    )
    assert response.status_code == 200, response.text
    sale = response.json()
    assert sale["status"] == "paid_cash"
    assert sale["paymentMethod"] == "cash"


# ---------------------------------------------------------------------------
# Collection routing: create_qr sends the ACTIVE bankAccountId
# ---------------------------------------------------------------------------


def test_create_qr_sends_bank_account_id():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": "qr_1", "image": "data:image/png;base64,U0lNVUxBRE8="})

    client = PeyClient("test-pey-key", base_url="https://pey.invalid",
                       transport=httpx.MockTransport(handler))
    try:
        client.create_qr(
            amount_cents=1,
            concept="Abarpay",
            expiration_sec=900,
            sale_id="sale_1",
            bank_account_id="ba_active_1",
        )
    finally:
        client.close()

    assert captured["body"]["bankAccountId"] == "ba_active_1"


def test_create_qr_omits_bank_account_id_for_legacy_call():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": "qr_1", "image": "data:image/png;base64,U0lNVUxBRE8="})

    client = PeyClient("test-pey-key", base_url="https://pey.invalid",
                       transport=httpx.MockTransport(handler))
    try:
        client.create_qr(amount_cents=1, concept="Abarpay", expiration_sec=900, sale_id="sale_1")
    finally:
        client.close()

    assert "bankAccountId" not in captured["body"]


# ---------------------------------------------------------------------------
# Router (signup + bank-account create/list/status)
# ---------------------------------------------------------------------------


@pytest.fixture
def onboarding_client():
    store = MemoryOnboardingStore()
    notifier = MemoryBankAccountNotifier()
    app = FastAPI()
    register_onboarding(app, store=store, notifier=notifier)
    with TestClient(app) as test_client:
        yield test_client, store, notifier


def _signup(client: TestClient) -> tuple[str, str]:
    response = client.post(
        "/api/signup",
        json={
            "email": "rosa@abarpay.test",
            "name": "Doña Rosa",
            "storeName": "Tienda Rosa",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["membership"]["role"] == "owner"
    return body["user"]["id"], body["tenant"]["id"]


def test_signup_endpoint_returns_owner_and_clean_store(onboarding_client):
    client, store, _notifier = onboarding_client
    response = client.post(
        "/api/signup",
        json={"email": "rosa@abarpay.test", "name": "Rosa", "storeName": "Tienda Rosa"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant"]["name"] == "Tienda Rosa"
    assert body["store"]["name"] == "Tienda Rosa"
    assert body["membership"]["role"] == "owner"

    # Clean seed: no products, only the owner membership.
    assert store.count_products(body["tenant"]["id"]) == 0
    assert store.count_members(body["tenant"]["id"]) == 1


def test_bank_account_endpoints_create_list_status_activate(onboarding_client):
    client, store, notifier = onboarding_client
    user_id, tenant_id = _signup(client)
    headers = {"X-Owner-Id": user_id, "X-Tenant-Id": tenant_id}

    # create
    response = client.post(
        "/api/tenant/bank-account",
        json={
            "alias": "Ventas",
            "name": "Tienda Rosa S.A. de C.V.",
            "clabe": VALID_CLABE,
            "entity": "BUSINESS",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    account = response.json()
    assert account["codiStatus"] == "PENDING"
    assert account["simulated"] is True
    assert account["last4"] == VALID_CLABE[-4:]
    assert "clabe" not in account  # the full CLABE never appears in responses
    bank_account_id = account["bankAccountId"]

    # list
    response = client.get("/api/tenant/bank-accounts", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [a["bankAccountId"] for a in items] == [bank_account_id]

    # status
    response = client.get(f"/api/tenant/bank-account/{bank_account_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["codiStatus"] == "PENDING"

    # activate (SIMULADO)
    response = client.post(
        f"/api/tenant/bank-account/{bank_account_id}/activate", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["codiStatus"] == "ACTIVE"

    # email notification path was exercised
    assert notifier.sent[-1] == ("rosa@abarpay.test", bank_account_id, "ACTIVE")
    assert store.get_active_bank_account(tenant_id).id == bank_account_id


def test_bank_account_endpoints_reject_invalid_clabe(onboarding_client):
    client, _store, _notifier = onboarding_client
    user_id, tenant_id = _signup(client)
    headers = {"X-Owner-Id": user_id, "X-Tenant-Id": tenant_id}
    response = client.post(
        "/api/tenant/bank-account",
        json={"alias": "V", "name": "R", "clabe": INVALID_CLABE, "entity": "BUSINESS"},
        headers=headers,
    )
    assert response.status_code == 400


def test_bank_account_endpoints_require_owner(onboarding_client):
    client, _store, _notifier = onboarding_client
    # No simulated owner headers -> 401.
    assert client.get("/api/tenant/bank-accounts").status_code == 401


# ---------------------------------------------------------------------------
# PostgreSQL adapter: atomic signup through the signup_tenant SECURITY DEFINER
# function (skipped when the local dev cluster is not reachable).
# ---------------------------------------------------------------------------

PG_DSN = os.environ.get("ABARPAY_PG_DSN") or (
    "host=127.0.0.1 port=5432 dbname=abarpay_dev user=" + getpass.getuser()
)

try:
    import psycopg  # noqa: F401

    from server import db_pg  # noqa: F401
    from server.onboarding import (  # noqa: F401
        PostgresOnboardingStore,
        ensure_onboarding_schema,
    )

    _PG_OK = True
except Exception:  # pragma: no cover - psycopg optional at collection time
    psycopg = None
    db_pg = None
    PostgresOnboardingStore = None
    ensure_onboarding_schema = None
    _PG_OK = False


def _pg_reachable() -> bool:
    if psycopg is None:
        return False
    try:
        with psycopg.connect(PG_DSN, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


PG_AVAILABLE = _pg_reachable()


@pytest.fixture(scope="session")
def pg_onboarding_admin():
    conn = psycopg.connect(PG_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute((REPO_ROOT / "migrations" / "001_schema.sql").read_text())
        cur.execute((REPO_ROOT / "migrations" / "002_seed.sql").read_text())
    ensure_onboarding_schema(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pg_onboarding_pool(pg_onboarding_admin):
    p = db_pg.create_pool(PG_DSN, min_size=1, max_size=4)
    yield p
    p.close()


def _pg_drop_tenant(admin, tenant_id: str, user_id: str) -> None:
    with admin.cursor() as cur:
        cur.execute("DELETE FROM bank_accounts WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM memberships WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM stores WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


@pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL abarpay_dev not reachable")
def test_pg_atomic_signup_and_bank_account(pg_onboarding_admin, pg_onboarding_pool):
    store = PostgresOnboardingStore(pg_onboarding_pool)
    suffix = uuid.uuid4().hex[:12]
    result = None
    try:
        result = store.signup(
            idp="auth0",
            external_sub=f"auth0|onb-{suffix}",
            email=f"onb-{suffix}@abarpay.test",
            owner_name="Owner Onboarding",
            slug=f"onb-{suffix}",
            tenant_name="Tienda Onboarding",
            store_name="Tienda Onboarding",
            timezone="America/Mexico_City",
        )

        # The SECURITY DEFINER function created tenant + store + owner
        # membership atomically, with a clean seed.
        assert store.count_products(result.tenant_id) == 0
        assert store.count_members(result.tenant_id) == 1

        membership = store.get_membership(result.user_id, result.tenant_id)
        assert membership is not None and membership.role == "owner"

        # Bank account via RLS-guarded writes.
        account = store.create_bank_account(
            tenant_id=result.tenant_id,
            alias="Ventas",
            name="Tienda Onboarding",
            entity="BUSINESS",
            clabe=VALID_CLABE,
        )
        assert account.status == STATUS_PENDING
        assert account.last4 == VALID_CLABE[-4:]

        activated = store.set_bank_account_status(
            result.tenant_id,
            account.id,
            from_status=STATUS_PENDING,
            to_status=STATUS_ACTIVE,
        )
        assert activated is not None and activated.status == STATUS_ACTIVE
        assert store.get_active_bank_account(result.tenant_id).id == account.id
    finally:
        store.close()
        if result is not None:
            _pg_drop_tenant(pg_onboarding_admin, result.tenant_id, result.user_id)
