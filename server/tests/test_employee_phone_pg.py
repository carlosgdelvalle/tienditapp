"""PostgreSQL acceptance for phone-bound employee invitations and grants.

The module starts an isolated PostgreSQL cluster and drives the production app
through the same phone enrollment, QR session and bearer contracts used by the
owner console and mobile clients. SMS delivery is simulated in-process.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

import phonenumbers
import psycopg
import pytest
from fastapi.testclient import TestClient

from server.owner_phone import PhoneSettings
from server.runtime import create_production_app
from server.tests.test_runtime_pg import (
    INITDB,
    NL,
    PG_CTL,
    _make_device_key,
    _prod_env,
    _provision_service_role,
    _start_cluster,
    _stop_cluster,
    parse_qr,
    sign_device,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Runtime:
    app: object
    client: TestClient
    inbox: list[tuple[str, str]]
    admin_dsn: str


@dataclass(frozen=True)
class PhoneIdentity:
    phone: str
    e164: str
    auth: dict[str, str]
    device_id: str
    private_key: str
    public_key: str


@dataclass(frozen=True)
class PhoneSetup:
    phone: str
    e164: str
    device_id: str
    private_key: str
    public_key: str


@dataclass(frozen=True)
class OwnerWorkspace:
    client: TestClient
    identity: PhoneIdentity
    user_id: str
    tenant_id: str
    tenant_name: str
    csrf: str


def _apply_all_migrations(dsn: str) -> None:
    """Apply every migration present when the focused test starts."""

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cursor:
            for path in sorted((REPO_ROOT / "migrations").glob("*.sql")):
                cursor.execute(path.read_text(encoding="utf-8"))


def _new_mexican_mobile() -> str:
    for _ in range(100):
        national = "55" + f"{secrets.randbelow(90_000_000) + 10_000_000:08d}"
        number = phonenumbers.parse(national, "MX")
        if phonenumbers.is_valid_number_for_region(number, "MX"):
            return national
    raise AssertionError("No se pudo generar un celular mexicano válido")


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    if not INITDB or not PG_CTL:
        pytest.skip("initdb/pg_ctl not available")

    cluster = _start_cluster(tmp_path_factory.mktemp("employee-phone-pg"))
    try:
        _apply_all_migrations(cluster["superuser_dsn"])
        _provision_service_role(cluster["superuser_dsn"])
        inbox: list[tuple[str, str]] = []
        app = create_production_app(
            env={**_prod_env(cluster["service_dsn"]), "SECURE_COOKIES": "false"},
            phone_settings=PhoneSettings(
                secrets.token_bytes(32),
                lambda number, code: inbox.append((number, code)),
            ),
        )
        with TestClient(app) as client:
            yield Runtime(
                app=app,
                client=client,
                inbox=inbox,
                admin_dsn=cluster["superuser_dsn"],
            )
    finally:
        _stop_cluster(cluster)


def _new_phone_setup() -> PhoneSetup:
    phone = _new_mexican_mobile()
    e164 = phonenumbers.format_number(
        phonenumbers.parse(phone, "MX"),
        phonenumbers.PhoneNumberFormat.E164,
    )
    private_key, public_key = _make_device_key()
    return PhoneSetup(
        phone=phone,
        e164=e164,
        device_id=str(uuid.uuid4()),
        private_key=private_key,
        public_key=public_key,
    )


def _start_phone(
    runtime: Runtime,
    setup: PhoneSetup,
    *,
    invite_token: str | None = None,
):
    payload = {
        "phone": setup.phone,
        "deviceId": setup.device_id,
        "publicKey": setup.public_key,
    }
    if invite_token is not None:
        payload["inviteToken"] = invite_token
    return runtime.client.post("/api/auth/owner/phone/start", json=payload)


def _enroll_phone(
    runtime: Runtime,
    *,
    setup: PhoneSetup | None = None,
    invite_token: str | None = None,
) -> PhoneIdentity:
    setup = setup or _new_phone_setup()
    before = len(runtime.inbox)

    started = _start_phone(runtime, setup, invite_token=invite_token)
    assert started.status_code == 200, started.text
    assert len(runtime.inbox) == before + 1
    sent_to, code = runtime.inbox[-1]
    assert sent_to == setup.e164

    challenge = started.json()["challengeId"]
    verified = runtime.client.post(
        "/api/auth/owner/phone/verify",
        json={
            "challengeId": challenge,
            "signature": sign_device(
                setup.private_key, f"abarpay-owner-enroll:{challenge}"
            ),
            "code": code,
        },
    )
    assert verified.status_code == 200, verified.text
    return PhoneIdentity(
        phone=setup.phone,
        e164=setup.e164,
        auth={"Authorization": "Bearer " + verified.json()["accessToken"]},
        device_id=setup.device_id,
        private_key=setup.private_key,
        public_key=setup.public_key,
    )


def _signup_owner(runtime: Runtime, *, store_name: str) -> OwnerWorkspace:
    identity = _enroll_phone(runtime)
    client = TestClient(runtime.app)
    signed_up = client.post(
        "/api/signup",
        headers=identity.auth,
        json={"name": "Dueño " + store_name, "storeName": store_name},
    )
    assert signed_up.status_code == 200, signed_up.text
    body = signed_up.json()
    tenant_id = body["tenant"]["id"]

    challenge = client.post(
        "/api/auth/challenge", json={"intent": "browser_login"}
    )
    assert challenge.status_code == 200, challenge.text
    qr = parse_qr(challenge.json()["qr"])
    payload = NL.join(
        [
            qr["id"],
            qr["nonce"],
            str(qr["exp"]),
            qr["intent"],
            tenant_id,
        ]
    )
    approved = client.post(
        f"/api/auth/challenge/{qr['id']}/approve",
        headers=identity.auth,
        json={
            "deviceId": identity.device_id,
            "tenantId": tenant_id,
            "code": qr["code"],
            "deviceSignature": sign_device(identity.private_key, payload),
        },
    )
    assert approved.status_code == 200, approved.text
    exchanged = client.post(f"/api/auth/challenge/{qr['id']}/exchange")
    assert exchanged.status_code == 200, exchanged.text

    return OwnerWorkspace(
        client=client,
        identity=identity,
        user_id=body["user"]["id"],
        tenant_id=tenant_id,
        tenant_name=store_name,
        csrf=exchanged.json()["csrfToken"],
    )


def _owner_headers(owner: OwnerWorkspace) -> dict[str, str]:
    return {"X-CSRF-Token": owner.csrf}


def _create_invite(
    owner: OwnerWorkspace,
    phone: str,
    *,
    can_sell: bool,
    can_fiado: bool,
    can_inventory: bool,
) -> dict:
    response = owner.client.post(
        "/api/tenant/members/invite",
        headers=_owner_headers(owner),
        json={
            "phone": phone,
            "canSell": can_sell,
            "canFiado": can_fiado,
            "canInventory": can_inventory,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token"]
    assert f"/invite/{body['token']}" in body["url"]
    assert body["expiresAt"]
    return body


def _accept_invite(
    client: TestClient,
    token: str,
    identity: PhoneIdentity,
    *,
    name: str,
):
    return client.post(
        f"/api/tenant/members/invites/{token}/accept",
        headers=identity.auth,
        json={"name": name},
    )


def _membership_row(runtime: Runtime, tenant_id: str, user_id: str):
    with psycopg.connect(runtime.admin_dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT role, can_sell, can_fiado, can_inventory, active
                   FROM memberships
                   WHERE tenant_id = %s::uuid AND user_id = %s::uuid""",
                (tenant_id, user_id),
            )
            rows = cursor.fetchall()
    assert len(rows) == 1
    return rows[0]


def _create_product(owner: OwnerWorkspace, name: str, price_cents: int = 2500) -> dict:
    response = owner.client.post(
        "/api/catalog",
        headers=_owner_headers(owner),
        json={
            "name": name,
            "unit": "pieza",
            "priceCents": price_cents,
            "stockMilli": 5000,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_customer(owner: OwnerWorkspace, name: str) -> dict:
    response = owner.client.post(
        "/api/owner/fiado/customers",
        headers={
            **_owner_headers(owner),
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _patch_member(owner: OwnerWorkspace, user_id: str, body: dict) -> dict:
    response = owner.client.patch(
        f"/api/tenant/members/{user_id}",
        headers=_owner_headers(owner),
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _cash_catalog(client: TestClient, identity: PhoneIdentity, tenant_id: str):
    return client.get(
        f"/api/owner/pos/{tenant_id}/catalog", headers=identity.auth
    )


def _cash_sale(
    client: TestClient,
    identity: PhoneIdentity,
    tenant_id: str,
    product_id: str,
):
    return client.post(
        f"/api/owner/pos/{tenant_id}/sales",
        headers={**identity.auth, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "items": [{"productId": product_id, "qtyMilli": 1000}],
            "cashReceivedCents": 2500,
            "expectedTotalCents": 2500,
        },
    )


def _employee_inventory(client: TestClient, identity: PhoneIdentity, tenant_id: str):
    return client.get(f"/api/employee/{tenant_id}/inventory", headers=identity.auth)


def _employee_fiado(client: TestClient, identity: PhoneIdentity, tenant_id: str):
    return client.get(
        f"/api/employee/{tenant_id}/fiado/customers", headers=identity.auth
    )


def test_phone_invite_is_previewed_bound_and_retry_safe(runtime: Runtime):
    owner = _signup_owner(runtime, store_name="Tienda invitación " + uuid.uuid4().hex[:6])
    intended_employee = _new_phone_setup()
    wrong_phone = _enroll_phone(runtime)
    employee_client = TestClient(runtime.app)

    invite = _create_invite(
        owner,
        intended_employee.phone,
        can_sell=True,
        can_fiado=False,
        can_inventory=True,
    )
    replacement = _create_invite(
        owner,
        intended_employee.phone,
        can_sell=False,
        can_fiado=True,
        can_inventory=False,
    )
    assert employee_client.get(f"/api/tenant/members/invites/{invite['token']}").status_code == 404
    invite = replacement
    landing = employee_client.get(f"/invite/{invite['token']}")
    assert landing.status_code == 200
    assert landing.headers["Referrer-Policy"] == "no-referrer"
    assert f"abarpay://equipo/{invite['token']}" in landing.text

    inbox_before_mismatch = len(runtime.inbox)
    mismatched_start = _start_phone(
        runtime,
        _new_phone_setup(),
        invite_token=invite["token"],
    )
    assert mismatched_start.status_code == 403, mismatched_start.text
    assert len(runtime.inbox) == inbox_before_mismatch

    employee = _enroll_phone(
        runtime,
        setup=intended_employee,
        invite_token=invite["token"],
    )

    preview = owner.client.get(
        f"/api/tenant/members/invites/{invite['token']}"
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["tenantName"] == owner.tenant_name
    assert preview_body["canSell"] is False
    assert preview_body["canFiado"] is True
    assert preview_body["canInventory"] is False
    preview_text = json.dumps(preview_body, ensure_ascii=False)
    assert employee.e164 not in preview_text
    assert employee.phone not in preview_text

    # The owner's QR session cannot consume a phone-bound invitation.
    qr_accept = owner.client.post(
        f"/api/tenant/members/invites/{invite['token']}/accept",
        json={"name": "Dueño por QR"},
    )
    assert qr_accept.status_code in {401, 403}, qr_accept.text
    assert employee_client.get(
        "/api/me/memberships", headers=employee.auth
    ).json()["items"] == []

    wrong = _accept_invite(
        employee_client,
        invite["token"],
        wrong_phone,
        name="Persona equivocada",
    )
    assert wrong.status_code in {403, 409}, wrong.text
    assert employee_client.get(
        "/api/me/memberships", headers=wrong_phone.auth
    ).json()["items"] == []
    assert owner.client.get(
        f"/api/tenant/members/invites/{invite['token']}"
    ).status_code == 200

    accepted = _accept_invite(
        employee_client,
        invite["token"],
        employee,
        name="Empleada verificada",
    )
    assert accepted.status_code == 200, accepted.text
    membership = accepted.json()
    assert str(uuid.UUID(membership["userId"])) == membership["userId"]
    assert membership["tenantId"] == owner.tenant_id
    assert membership["role"] == "employee"
    assert membership["canSell"] is False
    assert membership["canFiado"] is True
    assert membership["canInventory"] is False
    assert membership["active"] is True
    assert membership["name"] == "Empleada verificada"
    employee_user_id = membership["userId"]

    retry = _accept_invite(
        employee_client,
        invite["token"],
        employee,
        name="Empleada verificada",
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["userId"] == employee_user_id
    assert retry.json()["canSell"] is False
    assert retry.json()["canFiado"] is True
    assert retry.json()["canInventory"] is False

    row = _membership_row(runtime, owner.tenant_id, employee_user_id)
    assert row == ("employee", False, True, False, True)

    memberships = employee_client.get(
        "/api/me/memberships", headers=employee.auth
    ).json()["items"]
    assert len(memberships) == 1
    assert memberships[0]["tenantId"] == owner.tenant_id
    assert memberships[0]["canSell"] is False
    assert memberships[0]["canFiado"] is True
    assert memberships[0]["canInventory"] is False

    still_wrong = _accept_invite(
        employee_client,
        invite["token"],
        wrong_phone,
        name="Persona equivocada",
    )
    assert still_wrong.status_code in {403, 409}, still_wrong.text


def test_live_employee_grants_cash_inventory_fiado_and_revocation(runtime: Runtime):
    suffix = uuid.uuid4().hex[:6]
    owner_a = _signup_owner(runtime, store_name="Tienda permisos " + suffix)
    owner_b = _signup_owner(runtime, store_name="Tienda ajena " + suffix)
    employee = _enroll_phone(runtime)
    employee_client = TestClient(runtime.app)

    invite = _create_invite(
        owner_a,
        employee.phone,
        can_sell=False,
        can_fiado=False,
        can_inventory=False,
    )
    accepted = _accept_invite(
        employee_client, invite["token"], employee, name="Empleado permisos"
    )
    assert accepted.status_code == 200, accepted.text
    employee_user_id = accepted.json()["userId"]

    product_a = _create_product(owner_a, "Producto permitido " + suffix)
    product_b = _create_product(owner_b, "Producto ajeno " + suffix)
    customer_a = _create_customer(owner_a, "Cliente permitido " + suffix)

    assert _cash_catalog(employee_client, employee, owner_a.tenant_id).status_code == 403
    assert _cash_sale(
        employee_client, employee, owner_a.tenant_id, product_a["id"]
    ).status_code == 403
    assert _employee_inventory(
        employee_client, employee, owner_a.tenant_id
    ).status_code == 403
    assert employee_client.post(
        f"/api/employee/{owner_a.tenant_id}/inventory/{product_a['id']}/adjust",
        headers={**employee.auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"stockMilli": 6000, "expectedStockMilli": 5000, "reason": "Conteo"},
    ).status_code == 403
    assert _employee_fiado(
        employee_client, employee, owner_a.tenant_id
    ).status_code == 403
    assert employee_client.get(
        f"/api/employee/{owner_a.tenant_id}/fiado/customers/{customer_a['id']}",
        headers=employee.auth,
    ).status_code == 403

    # Owner-only surfaces stay forbidden even when the employee gains flags.
    assert employee_client.get(
        "/api/owner/inventory", headers=employee.auth
    ).status_code in {401, 403}
    assert employee_client.get(
        "/api/owner/fiado/customers", headers=employee.auth
    ).status_code in {401, 403}
    assert employee_client.post(
        "/api/tenant/members/invite",
        headers=employee.auth,
        json={"phone": _new_mexican_mobile()},
    ).status_code in {401, 403}

    granted = _patch_member(
        owner_a,
        employee_user_id,
        {"canSell": True, "canFiado": True, "canInventory": True},
    )
    assert (granted["canSell"], granted["canFiado"], granted["canInventory"]) == (
        True,
        True,
        True,
    )

    browser = TestClient(runtime.app)
    for intent, approval_status, exchange_status in (
        ("browser_login", 403, 409),
        ("device_link", 200, 403),
    ):
        challenge = browser.post("/api/auth/challenge", json={"intent": intent})
        assert challenge.status_code == 200
        qr = parse_qr(challenge.json()["qr"])
        payload = NL.join([qr["id"], qr["nonce"], str(qr["exp"]), qr["intent"], owner_a.tenant_id])
        approved = browser.post(
            f"/api/auth/challenge/{qr['id']}/approve",
            headers=employee.auth,
            json={
                "deviceId": employee.device_id,
                "tenantId": owner_a.tenant_id,
                "code": qr["code"],
                "deviceSignature": sign_device(employee.private_key, payload),
            },
        )
        assert approved.status_code == approval_status
        exchanged = browser.post(f"/api/auth/challenge/{qr['id']}/exchange")
        assert exchanged.status_code == exchange_status
        assert browser.get("/api/tenant").status_code == 401

    # Replaying an accepted invitation returns the newer owner grants.
    replay = _accept_invite(
        employee_client, invite["token"], employee, name="Empleado permisos"
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["userId"] == employee_user_id
    assert (
        replay.json()["canSell"],
        replay.json()["canFiado"],
        replay.json()["canInventory"],
    ) == (True, True, True)
    assert _membership_row(runtime, owner_a.tenant_id, employee_user_id) == (
        "employee",
        True,
        True,
        True,
        True,
    )

    catalog = _cash_catalog(employee_client, employee, owner_a.tenant_id)
    assert catalog.status_code == 200, catalog.text
    assert product_a["id"] in {item["id"] for item in catalog.json()["items"]}
    sale = _cash_sale(
        employee_client, employee, owner_a.tenant_id, product_a["id"]
    )
    assert sale.status_code == 200, sale.text
    assert sale.json()["employeeId"] == employee_user_id
    assert sale.json()["totalCents"] == 2500

    inventory = _employee_inventory(employee_client, employee, owner_a.tenant_id)
    assert inventory.status_code == 200, inventory.text
    current = next(
        item for item in inventory.json()["items"] if item["id"] == product_a["id"]
    )
    assert current["stockMilli"] == 4000
    adjusted = employee_client.post(
        f"/api/employee/{owner_a.tenant_id}/inventory/{product_a['id']}/adjust",
        headers={**employee.auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"stockMilli": 6100, "expectedStockMilli": 4000, "reason": "Conteo"},
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["stockMilli"] == 6100

    customers = _employee_fiado(employee_client, employee, owner_a.tenant_id)
    assert customers.status_code == 200, customers.text
    assert customer_a["id"] in {item["id"] for item in customers.json()["items"]}
    detail = employee_client.get(
        f"/api/employee/{owner_a.tenant_id}/fiado/customers/{customer_a['id']}",
        headers=employee.auth,
    )
    assert detail.status_code == 200, detail.text
    entry = employee_client.post(
        f"/api/employee/{owner_a.tenant_id}/fiado/customers/{customer_a['id']}/entries",
        headers={**employee.auth, "Idempotency-Key": str(uuid.uuid4())},
        json={"kind": "charge", "amountCents": 1500, "note": "Venta fiada"},
    )
    assert entry.status_code == 200, entry.text

    # A valid membership in A cannot read or write B through tenant paths.
    assert _cash_catalog(
        employee_client, employee, owner_b.tenant_id
    ).status_code in {403, 404}
    assert _cash_sale(
        employee_client, employee, owner_b.tenant_id, product_b["id"]
    ).status_code in {403, 404}
    assert _employee_inventory(
        employee_client, employee, owner_b.tenant_id
    ).status_code in {403, 404}
    assert _employee_fiado(
        employee_client, employee, owner_b.tenant_id
    ).status_code in {403, 404}

    # Grant changes take effect on the next request without a new token.
    downgraded = _patch_member(owner_a, employee_user_id, {"canSell": False})
    assert downgraded["canSell"] is False
    assert downgraded["canFiado"] is True
    assert downgraded["canInventory"] is True
    assert _cash_catalog(employee_client, employee, owner_a.tenant_id).status_code == 403
    assert _cash_sale(
        employee_client, employee, owner_a.tenant_id, product_a["id"]
    ).status_code == 403
    assert _employee_inventory(
        employee_client, employee, owner_a.tenant_id
    ).status_code == 200
    assert _employee_fiado(
        employee_client, employee, owner_a.tenant_id
    ).status_code == 200

    revoked = _patch_member(owner_a, employee_user_id, {"active": False})
    assert revoked["active"] is False
    suspended_replay = _accept_invite(
        employee_client, invite["token"], employee, name="Empleado permisos"
    )
    assert suspended_replay.status_code == 200
    assert suspended_replay.json()["active"] is False
    assert employee_client.get(
        "/api/me/memberships", headers=employee.auth
    ).json()["items"] == []
    assert _cash_catalog(employee_client, employee, owner_a.tenant_id).status_code == 403
    assert _employee_inventory(
        employee_client, employee, owner_a.tenant_id
    ).status_code == 403
    assert _employee_fiado(
        employee_client, employee, owner_a.tenant_id
    ).status_code == 403
