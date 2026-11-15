"""Shared fixtures. All PEY calls use FakePey (SIMULADO)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Never let the test process pick up the real credentials file, even if the
# surrounding shell exported something.
os.environ["ABARPAY_LOAD_DOTENV"] = "0"
os.environ.pop("PEY_API_KEY", None)
os.environ.pop("PEY_WEBHOOK_SECRET", None)

from fastapi.testclient import TestClient  # noqa: E402

from server.config import Settings  # noqa: E402
from server.db import STORE_ID, initialize_db  # noqa: E402
from server.main import create_app  # noqa: E402
from server.tests.fakes import FakePey  # noqa: E402

TEST_SECRET = "whsec_" + base64.b64encode(b"abarpay-test-secret").decode("ascii")

# v2: a brand new database only seeds the owner (id 1). Most v1 tests use the
# historical demo employees 2 and 3, so the suite seeds them explicitly here.
TEST_STAFF = (
    {
        "id": 2,
        "name": "Lupita",
        "nickname": "Lupis",
        "role": "employee",
        "can_sell": 1,
        "can_fiado": 1,
        "can_inventory": 0,
    },
    {
        "id": 3,
        "name": "Toño",
        "nickname": "Toñito",
        "role": "employee",
        "can_sell": 1,
        "can_fiado": 1,
        "can_inventory": 1,
    },
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "fresh_seed: usa la base nueva de v2 (solo el dueño), sin sembrar empleados de prueba",
    )


def employee_headers(employee_id: int) -> dict[str, str]:
    """Simulated identity header used by the Android app after onboarding."""

    return {"X-Employee-Id": str(employee_id)}


def create_test_employee(
    db: sqlite3.Connection,
    employee_id: int,
    name: str,
    *,
    nickname: str | None = None,
    role: str = "employee",
    active: int = 1,
    can_sell: int = 1,
    can_fiado: int = 1,
    can_inventory: int = 0,
) -> None:
    """Insert an employee directly for tests that need a specific id."""

    db.execute(
        """INSERT OR REPLACE INTO employees
               (id, store_id, name, nickname, role, active,
                can_sell, can_fiado, can_inventory)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            employee_id,
            STORE_ID,
            name,
            nickname,
            role,
            active,
            can_sell,
            can_fiado,
            can_inventory,
        ),
    )
    db.commit()


@pytest.fixture
def staff(request: pytest.FixtureRequest, settings: Settings, db):
    """Seed the v1 demo employees 2 and 3 when a test needs them.

    v2 seeds a new database with the owner only; the v1 suite and the new
    permission tests ask for this fixture explicitly. Tests marked with
    fresh_seed keep the owner-only state to verify the seed itself.
    """

    initialize_db(settings.db_path)
    if request.node.get_closest_marker("fresh_seed"):
        yield
        return
    for employee in TEST_STAFF:
        db.execute(
            """INSERT OR IGNORE INTO employees
                   (id, store_id, name, nickname, role, active,
                    can_sell, can_fiado, can_inventory)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                employee["id"],
                STORE_ID,
                employee["name"],
                employee["nickname"],
                employee["role"],
                employee["can_sell"],
                employee["can_fiado"],
                employee["can_inventory"],
            ),
        )
    db.commit()
    yield


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "abar-test.db",
        owner_pin="1234",
        modo_demo=True,
        pey_api_key="test-pey-key",
        pey_webhook_secret=TEST_SECRET,
        pey_expiration_seconds=900,
        timezone="America/Mexico_City",
    )


@pytest.fixture
def fake_pey() -> FakePey:
    return FakePey()


@pytest.fixture
def app(settings: Settings, fake_pey: FakePey):
    return create_app(settings=settings, pey_client=fake_pey)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(settings: Settings):
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_cash_sale(
    client: TestClient,
    *,
    employee_id: int = 2,
    product_id: int = 1,
    qty_milli: int = 1000,
    cash_received_cents: int = 5000,
) -> dict:
    response = client.post(
        "/api/sales",
        json={
            "employeeId": employee_id,
            "items": [{"productId": product_id, "qtyMilli": qty_milli}],
            "paymentMethod": "cash",
            "cashReceivedCents": cash_received_cents,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_pey_sale(
    client: TestClient,
    *,
    employee_id: int = 2,
    product_id: int = 1,
    qty_milli: int = 1000,
) -> dict:
    response = client.post(
        "/api/sales",
        json={
            "employeeId": employee_id,
            "items": [{"productId": product_id, "qtyMilli": qty_milli}],
            "paymentMethod": "pey",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_customer(client: TestClient, name: str = "Doña Mari", phone: str = "555-0100") -> dict:
    response = client.post("/api/fiado/customers", json={"name": name, "phone": phone})
    assert response.status_code == 200, response.text
    return response.json()


def event_payload(qr_id: str, transaction_id: str, amount: float | str = 0.01) -> dict:
    return {
        "type": "codi.qr.payment_received",
        "data": {
            "codiQrId": qr_id,
            "transactionId": transaction_id,
            "amount": amount,
        },
    }


def sign_webhook(
    payload: dict,
    webhook_id: str,
    *,
    timestamp: int | None = None,
    secret: str = TEST_SECRET,
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts = int(time.time()) if timestamp is None else int(timestamp)
    signed = f"{webhook_id}.{ts}.".encode("utf-8") + body
    key = base64.b64decode(secret.split("_", 1)[1])
    signature = base64.b64encode(
        hmac.new(key, signed, hashlib.sha256).digest()
    ).decode("ascii")
    headers = {
        "webhook-id": webhook_id,
        "webhook-timestamp": str(ts),
        "webhook-signature": "v1," + signature,
        "content-type": "application/json",
    }
    return body, headers


def post_webhook(
    client: TestClient,
    payload: dict,
    webhook_id: str,
    *,
    timestamp: int | None = None,
    secret: str = TEST_SECRET,
):
    body, headers = sign_webhook(
        payload, webhook_id, timestamp=timestamp, secret=secret
    )
    return client.post("/webhooks/pey", content=body, headers=headers)
