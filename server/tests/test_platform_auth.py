"""Platform console: first-party staff login, roles and team invitations."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import create_app

OWNER_EMAIL = "carlos@abarpay.app"
OWNER_PASSWORD = "ClaveSegura123"


@pytest.fixture
def platform(settings, fake_pey, monkeypatch):
    monkeypatch.setenv("ABARPAY_PLATFORM_ADMIN_EMAIL", OWNER_EMAIL)
    monkeypatch.setenv("ABARPAY_PLATFORM_ADMIN_PASSWORD", OWNER_PASSWORD)
    monkeypatch.setenv("ABARPAY_PLATFORM_ADMIN_NAME", "Carlos")
    app = create_app(settings=settings, pey_client=fake_pey)
    with TestClient(app) as owner:
        yield app, owner


def login(client: TestClient, email: str = OWNER_EMAIL, password: str = OWNER_PASSWORD):
    return client.post(
        "/api/platform/auth/login",
        json={"email": email, "password": password},
    )


def invite(client: TestClient, email: str, role: str, name: str = "Persona"):
    response = client.post(
        "/api/platform/team/invites",
        json={"email": email, "name": name, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()["inviteUrl"].rsplit("/", 1)[-1]


def accept(app, token: str, password: str = "OtraClave456", name: str = "Persona"):
    client = TestClient(app)
    response = client.post(
        "/api/platform/team/invites/" + token,
        json={"name": name, "password": password},
    )
    return client, response


def test_owner_login_sees_every_section_and_team(platform):
    app, owner = platform
    assert owner.get("/api/platform/ingresos").status_code == 401

    response = login(owner)
    assert response.status_code == 200, response.text
    staff = response.json()["staff"]
    assert staff["role"] == "owner"
    assert staff["mustChangePassword"] is True

    for section in ("salud", "crecimiento", "ingresos", "datos"):
        assert owner.get("/api/platform/" + section).status_code == 200
    team = owner.get("/api/platform/team")
    assert team.status_code == 200
    assert team.json()["items"][0]["email"] == OWNER_EMAIL

    assert owner.post("/api/platform/auth/logout").status_code == 204
    assert owner.get("/api/platform/ingresos").status_code == 401
    assert app.state.platform_auth.session_staff(None) is None


def test_wrong_password_is_throttled(platform):
    _, client = platform
    for _ in range(5):
        assert login(client, password="incorrecta").status_code == 401
    assert login(client, password="incorrecta").status_code == 429


def test_invitation_grants_only_its_section(platform):
    app, owner = platform
    assert login(owner).status_code == 200
    token = invite(owner, "maria@abarpay.app", "marketing", "María")

    preview = TestClient(app).get("/api/platform/team/invites/" + token)
    assert preview.status_code == 200
    assert preview.json()["email"] == "maria@abarpay.app"

    maria, accepted = accept(app, token, name="María")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["staff"]["role"] == "marketing"
    assert maria.get("/api/platform/crecimiento").status_code == 200
    assert maria.get("/api/platform/ingresos").status_code == 403
    assert maria.get("/api/platform/team").status_code == 403

    again = maria.post(
        "/api/platform/team/invites/" + token,
        json={"name": "María", "password": "OtraClave789"},
    )
    assert again.status_code == 410


def test_deactivating_staff_revokes_the_session(platform):
    app, owner = platform
    assert login(owner).status_code == 200
    token = invite(owner, "operaciones@abarpay.app", "operations")
    operations, accepted = accept(app, token)
    assert accepted.status_code == 200
    assert operations.get("/api/platform/salud").status_code == 200

    items = owner.get("/api/platform/team").json()["items"]
    person = next(item for item in items if item["email"] == "operaciones@abarpay.app")
    patched = owner.patch(
        "/api/platform/team/" + person["id"], json={"active": False}
    )
    assert patched.status_code == 200, patched.text
    assert operations.get("/api/platform/salud").status_code == 401


def test_password_change_clears_the_temporary_password(platform):
    _, owner = platform
    assert login(owner).status_code == 200
    changed = owner.post(
        "/api/platform/auth/password",
        json={"currentPassword": OWNER_PASSWORD, "newPassword": "ClaveDefinitiva789"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["staff"]["mustChangePassword"] is False

    assert owner.post("/api/platform/auth/logout").status_code == 204
    assert login(owner).status_code == 401
    assert login(owner, password="ClaveDefinitiva789").status_code == 200


def test_only_the_owner_can_grant_admin(platform):
    app, owner = platform
    assert login(owner).status_code == 200
    assert (
        owner.post(
            "/api/platform/team/invites",
            json={"email": "x@abarpay.app", "name": "X", "role": "superuser"},
        ).status_code
        == 400
    )
    token = invite(owner, "admin@abarpay.app", "admin", "Admin")
    admin, accepted = accept(app, token, name="Admin")
    assert accepted.status_code == 200
    assert (
        admin.post(
            "/api/platform/team/invites",
            json={"email": "otro@abarpay.app", "name": "Otro", "role": "admin"},
        ).status_code
        == 403
    )


def test_first_owner_setup_requires_the_open_window(settings, fake_pey, monkeypatch):
    monkeypatch.delenv("ABARPAY_PLATFORM_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ABARPAY_PLATFORM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ABARPAY_PLATFORM_SETUP_OPEN", raising=False)
    app = create_app(settings=settings, pey_client=fake_pey)
    body = {
        "name": "Carlos",
        "email": OWNER_EMAIL,
        "password": OWNER_PASSWORD,
    }
    with TestClient(app) as client:
        me = client.get("/api/platform/auth/me").json()
        assert me["configured"] is False
        assert me["setupOpen"] is False
        assert client.post("/api/platform/auth/setup", json=body).status_code == 403

        monkeypatch.setenv("ABARPAY_PLATFORM_SETUP_OPEN", "1")
        me = client.get("/api/platform/auth/me").json()
        assert me["setupOpen"] is True

        created = client.post("/api/platform/auth/setup", json=body)
        assert created.status_code == 201, created.text
        assert created.json()["staff"]["role"] == "owner"
        assert created.json()["staff"]["mustChangePassword"] is False
        assert client.get("/api/platform/team").status_code == 200

        again = client.post("/api/platform/auth/setup", json=body)
        assert again.status_code == 409
        assert client.get("/api/platform/auth/me").json()["setupOpen"] is False

