"""Integration tests for the PostgreSQL IdentityStore adapter.

These run against the local development PostgreSQL (database 'abarpay_dev',
trust auth) and are skipped automatically when the server is not reachable, so
the SQLite-only CI stays green. They exercise the end-to-end identity path
through the SECURITY DEFINER functions added by migrations/001_schema.sql:
users (resolve/create), devices, challenges, sessions and invites.

Every test creates its own tenant/user via a superuser connection and cleans up
after itself (children first, then parents).
"""

from __future__ import annotations

import getpass
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PG_DSN = os.environ.get("ABARPAY_PG_DSN") or (
    "host=127.0.0.1 port=5432 dbname=abarpay_dev user=" + getpass.getuser()
)

try:
    import psycopg

    from server import db_pg
    from server.identity import Challenge, Device, Invite, SessionRecord
    from server.identity_pg import PostgresIdentityStore, actor_context

    _PSYCOPG_OK = True
except Exception:  # pragma: no cover - psycopg optional at collection time
    psycopg = None
    db_pg = None
    PostgresIdentityStore = None
    actor_context = None
    _PSYCOPG_OK = False


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
pytestmark = pytest.mark.skipif(
    not PG_AVAILABLE, reason="PostgreSQL abarpay_dev not reachable"
)


# --- fixtures ---------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_admin():
    """A superuser connection used for schema setup and per-test cleanup."""

    conn = psycopg.connect(PG_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute((REPO_ROOT / "migrations" / "001_schema.sql").read_text())
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pool(pg_admin):
    """A service-role connection pool (SET ROLE abarpay_app)."""

    p = db_pg.create_pool(PG_DSN, min_size=1, max_size=4)
    yield p
    p.close()


@pytest.fixture
def store(pool):
    s = PostgresIdentityStore(pool)
    yield s
    s.close()


# --- helpers ----------------------------------------------------------------

def _create_owner_tenant(admin, email: str) -> dict:
    tid = uuid.uuid4()
    sid = uuid.uuid4()
    uid = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (id, slug, name, status) VALUES (%s, %s, %s, 'active')",
            (tid, "id-" + uuid.uuid4().hex[:8], "Identity Test"),
        )
        cur.execute(
            "INSERT INTO stores (id, tenant_id, name) VALUES (%s, %s, %s)",
            (sid, tid, "Identity Test"),
        )
        cur.execute(
            "INSERT INTO users (id, email, name, idp, external_sub) "
            "VALUES (%s, %s, %s, 'auth0', %s)",
            (uid, email, email, "auth0|" + str(uuid.uuid4())),
        )
        cur.execute(
            "INSERT INTO memberships "
            "(id, user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active) "
            "VALUES (%s, %s, %s, 'owner', true, true, true, true)",
            (uuid.uuid4(), uid, tid),
        )
    return {"tenant": tid, "store": sid, "user": uid}


def _cleanup(admin, tenant: dict, extra_users: list[uuid.UUID] | None = None) -> None:
    uid = tenant["user"]
    users = [uid] + (extra_users or [])
    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM sessions WHERE user_id = ANY(%s)",
            ([str(u) for u in users],),
        )
        cur.execute(
            "DELETE FROM devices WHERE user_id = ANY(%s)",
            ([str(u) for u in users],),
        )
        cur.execute(
            "DELETE FROM challenges WHERE tenant_id = %s OR approver_user_id = ANY(%s)",
            (tenant["tenant"], [str(u) for u in users]),
        )
        cur.execute("DELETE FROM invites WHERE tenant_id = %s", (tenant["tenant"],))
        cur.execute("DELETE FROM memberships WHERE tenant_id = %s", (tenant["tenant"],))
        cur.execute("DELETE FROM stores WHERE tenant_id = %s", (tenant["tenant"],))
        for u in users:
            cur.execute("DELETE FROM users WHERE id = %s", (u,))
        cur.execute("DELETE FROM tenants WHERE id = %s", (tenant["tenant"],))


def _future(days: float = 7.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


# --- tests ------------------------------------------------------------------

def test_find_and_create_user_roundtrip(pg_admin, store):
    t = _create_owner_tenant(pg_admin, "id-owner@abarpay.test")
    try:
        assert store.find_user("auth0", "auth0|missing") is None

        created = store.create_user("auth0", "auth0|new-sub", "new@abarpay.test", "Nuevo")
        assert created.idp == "auth0"
        assert created.external_sub == "auth0|new-sub"

        # Idempotent: the same idp/external_sub resolves to the same row.
        again = store.create_user("auth0", "auth0|new-sub", "", "")
        assert again.id == created.id

        found = store.find_user("auth0", "auth0|new-sub")
        assert found is not None and found.id == created.id
    finally:
        _cleanup(pg_admin, t, [created.id])


def test_device_roundtrip_and_revoke(pg_admin, store):
    t = _create_owner_tenant(pg_admin, "id-device@abarpay.test")
    uid = str(t["user"])
    try:
        device = Device(
            device_id="device-1",
            user_id=uid,
            public_key="-----BEGIN PUBLIC KEY-----SIMULADO-----END PUBLIC KEY-----",
            label="Pixel",
            created_at=datetime.now(timezone.utc).timestamp(),
            last_seen_at=datetime.now(timezone.utc).timestamp(),
        )
        store.save_device(device)

        got = store.get_device(uid, "device-1")
        assert got is not None and got.device_id == "device-1" and got.label == "Pixel"

        listed = store.list_devices(uid)
        assert [d.device_id for d in listed] == ["device-1"]

        assert store.delete_device(uid, "device-1") is True
        assert store.get_device(uid, "device-1") is None
        assert store.delete_device(uid, "device-1") is False
    finally:
        _cleanup(pg_admin, t)


def test_challenge_transition_one_time(pg_admin, store):
    t = _create_owner_tenant(pg_admin, "id-challenge@abarpay.test")
    uid = str(t["user"])
    tid = str(t["tenant"])
    challenge_id = "challenge-" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    try:
        store.save_challenge(
            Challenge(
                id=challenge_id,
                code="000000",
                intent="browser_login",
                nonce="nonce",
                created_at=now.timestamp(),
                expires_at=(now + timedelta(seconds=120)).timestamp(),
                status="pending",
                browser_token_hash="browser-hash",
                approver_user_id=None,
                approver_device_id=None,
                selected_tenant_id=None,
                approved_at=None,
                redeemed_at=None,
            )
        )

        pending = store.get_challenge(challenge_id)
        assert pending is not None and pending.status == "pending"

        approved = store.transition_challenge(
            challenge_id,
            "pending",
            "approved",
            approver_user_id=uid,
            approver_device_id="device-1",
            selected_tenant_id=tid,
            approved_at=now.timestamp(),
        )
        assert approved is not None
        assert approved.status == "approved"
        assert approved.approver_user_id == uid
        assert approved.selected_tenant_id == tid

        consumed = store.transition_challenge(
            challenge_id, "approved", "consumed", redeemed_at=now.timestamp()
        )
        assert consumed is not None and consumed.status == "consumed"

        # The CAS transition fails once the status is no longer 'approved'.
        assert (
            store.transition_challenge(
                challenge_id, "approved", "consumed", redeemed_at=now.timestamp()
            )
            is None
        )
    finally:
        _cleanup(pg_admin, t)


def test_session_roundtrip_and_revoke(pg_admin, store):
    t = _create_owner_tenant(pg_admin, "id-session@abarpay.test")
    uid = str(t["user"])
    tid = str(t["tenant"])
    token = "session-token-" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    try:
        store.save_session(
            SessionRecord(
                token=token,
                user_id=uid,
                tenant_id=tid,
                csrf_token="csrf",
                created_at=now.timestamp(),
                expires_at=(now + timedelta(days=30)).timestamp(),
                revoked_at=None,
            )
        )

        session = store.get_session(token)
        assert session is not None
        assert session.user_id == uid
        assert session.tenant_id == tid
        assert session.revoked_at is None

        store.revoke_session(token)
        assert store.get_session(token).revoked_at is not None
    finally:
        _cleanup(pg_admin, t)


def test_invite_lookup_and_claim(pg_admin, store):
    t = _create_owner_tenant(pg_admin, "id-invite@abarpay.test")
    owner_id = str(t["user"])
    tid = str(t["tenant"])
    employee = store.create_user("auth0", "auth0|employee", "emp@abarpay.test", "Emp")
    rival = store.create_user("auth0", "auth0|rival", "rival@abarpay.test", "Rival")
    try:
        token_hash = uuid.uuid4().hex
        invite = Invite(
            token_hash=token_hash,
            tenant_id=tid,
            email="emp@abarpay.test",
            role="employee",
            can_sell=True,
            can_fiado=False,
            can_inventory=False,
            created_at=datetime.now(timezone.utc).timestamp(),
            expires_at=_future().timestamp(),
            accepted_at=None,
            revoked_at=None,
            accepted_by=None,
        )
        with actor_context(owner_id):
            store.save_invite(invite)

        looked = store.lookup_invite(token_hash)
        assert looked is not None and looked.tenant_id == tid

        assert store.get_invite(token_hash) is not None

        # First claimant wins.
        assert store.claim_invite(token_hash, employee.id, _future().timestamp()) == employee.id

        # The invite is now accepted; a second claimant sees a conflict.
        assert store.claim_invite(token_hash, rival.id, _future().timestamp()) != rival.id

        after = store.get_invite(token_hash)
        assert after.accepted_at is not None
    finally:
        _cleanup(pg_admin, t, [employee.id, rival.id])


def test_list_tenant_members_and_count_owners(pg_admin, store):
    t = _create_owner_tenant(pg_admin, "id-members@abarpay.test")
    owner_id = str(t["user"])
    tid = str(t["tenant"])
    emp_uid = uuid.uuid4()
    with pg_admin.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email, name, idp, external_sub) "
            "VALUES (%s, %s, %s, 'auth0', %s)",
            (emp_uid, "member@abarpay.test", "Miembro", "auth0|" + str(uuid.uuid4())),
        )
        cur.execute(
            "INSERT INTO memberships "
            "(id, user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active) "
            "VALUES (%s, %s, %s, 'employee', true, false, false, true)",
            (uuid.uuid4(), emp_uid, tid),
        )
    try:
        with actor_context(owner_id):
            members = store.list_tenant_members(tid)
            assert store.count_active_owners(tid) == 1

        user_ids = {m.user_id for m in members}
        assert str(emp_uid) in user_ids
        assert owner_id in user_ids
        roles = {m.user_id: m.role for m in members}
        assert roles[owner_id] == "owner"
        assert roles[str(emp_uid)] == "employee"
    finally:
        _cleanup(pg_admin, t, [emp_uid])
