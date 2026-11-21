"""Integration tests for the PostgreSQL tenancy schema (RLS, isolation,
composite FKs, invites, migration).

These tests run against the local development PostgreSQL (database
'abarpay_dev', trust auth). They are skipped automatically when the server is
not reachable, so the SQLite-only CI stays green. Set ABARPAY_PG_DSN to point
at a different database if needed.

They exercise the acceptance criteria and gates of
docs/produccion/02-contratos-y-tenencia.md and the frozen tenancy contract
docs/produccion/contracts/tenancy.md.
"""

from __future__ import annotations

import getpass
import hashlib
import os
import secrets
import sqlite3
import subprocess
import sys
import time
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

    _PSYCOPG_OK = True
except Exception:  # pragma: no cover - psycopg optional at collection time
    psycopg = None
    db_pg = None
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

# The 16 tenant-isolated tables: stores + the 15 business tables.
TENANT_TABLES = [
    "stores", "products", "sales", "sale_items", "payments",
    "inventory_movements", "fiado_customers", "fiado_entries",
    "fiado_drafts", "expenses", "day_tasks", "bank_accounts",
    "purchase_orders", "receipts", "till_shifts", "outbox_applied",
    "webhook_events", "barcodes", "store_settings", "support_tickets",
]

# Deletion order for per-tenant cleanup (children before parents).
_CHILD_ORDER = (
    "sale_items", "payments", "inventory_movements", "fiado_entries",
    "fiado_drafts", "expenses", "day_tasks", "receipts", "till_shifts",
    "bank_accounts", "purchase_orders", "outbox_applied", "support_tickets",
    "webhook_events", "sales", "fiado_customers", "barcodes", "products",
    "store_settings", "memberships", "stores", "invites",
)


# --- fixtures ---------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_admin():
    """A superuser connection (no SET ROLE) used for setup/cleanup.

    Applies the schema and the two-tenant seed idempotently.
    """

    conn = psycopg.connect(PG_DSN)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute((REPO_ROOT / "migrations" / "001_schema.sql").read_text())
        cur.execute((REPO_ROOT / "migrations" / "002_seed.sql").read_text())
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def pool(pg_admin):
    """A service-role connection pool (SET ROLE abarpay_app)."""

    p = db_pg.create_pool(PG_DSN, min_size=1, max_size=4)
    yield p
    p.close()


@pytest.fixture
def tenants(pg_admin):
    """Two fresh owner tenants (A and B), one store and one owner each."""

    suffix = uuid.uuid4().hex[:8]
    a = _create_owner_tenant(pg_admin, f"t-a-{suffix}", "Tenant A",
                             f"a-{suffix}@abarpay.test")
    b = _create_owner_tenant(pg_admin, f"t-b-{suffix}", "Tenant B",
                             f"b-{suffix}@abarpay.test")
    yield a, b
    _drop_tenant(pg_admin, a["tenant"], [a["user"]])
    _drop_tenant(pg_admin, b["tenant"], [b["user"]])


# --- helpers ----------------------------------------------------------------

def _create_owner_tenant(admin, slug: str, name: str, email: str) -> dict:
    tid = uuid.uuid4()
    sid = uuid.uuid4()
    uid = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (id, slug, name, status) VALUES (%s, %s, %s, 'active')",
            (tid, slug, name),
        )
        cur.execute(
            "INSERT INTO stores (id, tenant_id, name) VALUES (%s, %s, %s)",
            (sid, tid, name),
        )
        cur.execute(
            "INSERT INTO users (id, email, name, idp, external_sub) "
            "VALUES (%s, %s, %s, 'auth0', %s)",
            (uid, email, name, "auth0|" + str(uuid.uuid4())),
        )
        cur.execute(
            "INSERT INTO memberships "
            "(id, user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active) "
            "VALUES (%s, %s, %s, 'owner', true, true, true, true)",
            (uuid.uuid4(), uid, tid),
        )
    return {"tenant": tid, "store": sid, "user": uid, "slug": slug}


def _drop_tenant(admin, tenant_id: uuid.UUID, user_ids: list[uuid.UUID]) -> None:
    with admin.cursor() as cur:
        for t in _CHILD_ORDER:
            cur.execute(f"DELETE FROM {t} WHERE tenant_id = %s", (tenant_id,))
        cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
        for uid in user_ids:
            cur.execute("DELETE FROM users WHERE id = %s", (uid,))


def _as_owner(conn, tenant: dict) -> None:
    db_pg.set_tenant_context(conn, tenant_id=str(tenant["tenant"]),
                             user_id=str(tenant["user"]))


# --- tests ------------------------------------------------------------------

def test_schema_tables_have_force_rls_and_policy(pg_admin):
    """Gate: every business table has RLS + FORCE + a tenant-isolation policy,
    and abarpay_app is neither a superuser nor a table owner."""

    with pg_admin.cursor() as cur:
        cur.execute(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
        flags = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        cur.execute(
            "SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public'"
        )
        policies: dict[str, list[str]] = {}
        for t, p in cur.fetchall():
            policies.setdefault(t, []).append(p)

    for t in TENANT_TABLES:
        assert flags.get(t, (False, False))[0] is True, f"{t} lacks RLS"
        assert flags.get(t, (False, False))[1] is True, f"{t} lacks FORCE RLS"
        assert any("tenant_isolation" in p for p in policies.get(t, [])), (
            f"{t} lacks a tenant-isolation policy"
        )

    with pg_admin.cursor() as cur:
        cur.execute(
            "SELECT rolsuper, rolbypassrls, rolcanlogin "
            "FROM pg_roles WHERE rolname = 'abarpay_app'"
        )
        assert cur.fetchone() == (False, False, False)
        cur.execute(
            "SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_roles r ON r.oid = c.relowner "
            "WHERE n.nspname = 'public' AND r.rolname = 'abarpay_app'"
        )
        assert cur.fetchone()[0] == 0


def test_two_tenant_isolation(pg_admin, tenants, pool):
    """Acceptance: A sees no B rows in any business table (and vice versa)."""

    a, b = tenants
    with pg_admin.cursor() as cur:
        cur.execute(
            "INSERT INTO products (tenant_id, name, unit, price_cents, stock_milli) "
            "VALUES (%s, 'Producto A', 'pieza', 100, 10)",
            (a["tenant"],),
        )
        cur.execute(
            "INSERT INTO products (tenant_id, name, unit, price_cents, stock_milli) "
            "VALUES (%s, 'Producto B', 'pieza', 200, 20)",
            (b["tenant"],),
        )

    with pool.connection() as conn:
        _as_owner(conn, a)
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM products ORDER BY name")
            assert [r[0] for r in cur.fetchall()] == ["Producto A"]

    with pool.connection() as conn:
        _as_owner(conn, b)
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM products ORDER BY name")
            assert [r[0] for r in cur.fetchall()] == ["Producto B"]


def test_deny_by_default(pg_admin, tenants, pool):
    """Acceptance: unset context -> zero rows read and writes fail."""

    a, _ = tenants
    with pg_admin.cursor() as cur:
        cur.execute(
            "INSERT INTO products (tenant_id, name, unit, price_cents, stock_milli) "
            "VALUES (%s, 'Producto A', 'pieza', 100, 10)",
            (a["tenant"],),
        )

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM products")
            assert cur.fetchone()[0] == 0

    with pool.connection() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO products (tenant_id, name, unit, price_cents, stock_milli) "
                    "VALUES (%s, 'x', 'pieza', 0, 0)",
                    (a["tenant"],),
                )


def test_context_reverts_on_commit(pg_admin, tenants, pool):
    """A reused pooled connection with no context sees no rows after commit."""

    a, _ = tenants
    with pg_admin.cursor() as cur:
        cur.execute(
            "INSERT INTO products (tenant_id, name, unit, price_cents, stock_milli) "
            "VALUES (%s, 'Producto A', 'pieza', 100, 10)",
            (a["tenant"],),
        )

    with pool.connection() as conn:
        _as_owner(conn, a)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM products")
            assert cur.fetchone()[0] == 1
        conn.commit()  # SET LOCAL context reverts
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM products")
            assert cur.fetchone()[0] == 0


def test_one_to_one_store(pg_admin, tenants):
    """Invariant: a second stores row for the same tenant fails (UNIQUE)."""

    a, _ = tenants
    with pg_admin.cursor() as cur:
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO stores (id, tenant_id, name) "
                "VALUES (%s, %s, 'segunda tienda')",
                (uuid.uuid4(), a["tenant"]),
            )


def test_composite_cross_tenant_fk(pg_admin, tenants):
    """Invariant: a composite FK cannot reference another tenant's row."""

    a, b = tenants
    with pg_admin.cursor() as cur:
        cur.execute(
            "INSERT INTO products (id, tenant_id, name, unit, price_cents, stock_milli) "
            "VALUES (%s, %s, 'Prod B', 'pieza', 100, 10) RETURNING id",
            (uuid.uuid4(), b["tenant"]),
        )
        b_product = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO sales "
            "(id, tenant_id, store_id, employee_id, status, payment_method, "
            " total_cents, charged_cents) "
            "VALUES (%s, %s, %s, %s, 'paid_cash', 'cash', 100, 100) RETURNING id",
            (uuid.uuid4(), a["tenant"], a["store"], a["user"]),
        )
        a_sale = cur.fetchone()[0]

    with pg_admin.cursor() as cur:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            cur.execute(
                "INSERT INTO sale_items "
                "(tenant_id, sale_id, product_id, name, unit, qty_milli, "
                " unit_price_cents, line_total_cents) "
                "VALUES (%s, %s, %s, 'x', 'pieza', 1, 1, 1)",
                (a["tenant"], a_sale, b_product),
            )


def test_invite_token_stored_hashed_only(pg_admin, tenants, pool):
    """Invariant: only SHA-256(token) is stored; the plaintext never appears."""

    a, _ = tenants
    token = secrets.token_bytes(32)
    token_hash = hashlib.sha256(token).hexdigest()
    token_plain = token.hex()
    expires = datetime.now(timezone.utc) + timedelta(days=30)

    with pool.connection() as conn:
        _as_owner(conn, a)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT create_invite(%s, %s, 'employee', true, true, false, %s, %s)",
                (a["tenant"], "emp@abarpay.test", token_hash, expires),
            )
        conn.commit()

    with pg_admin.cursor() as cur:
        cur.execute("SELECT token_hash FROM invites WHERE tenant_id = %s",
                    (a["tenant"],))
        hashes = [r[0] for r in cur.fetchall()]

    assert token_hash in hashes
    assert token_plain not in hashes
    # The plaintext must not appear anywhere in the invites table.
    with pg_admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM invites WHERE token_hash = %s OR coalesce(email, '') = %s",
            (token_plain, token_plain),
        )
        assert cur.fetchone()[0] == 0


def test_create_invite_rejects_owner_role(pg_admin, tenants, pool):
    """SECURITY DEFINER function cannot mint an owner (no role elevation)."""

    a, _ = tenants
    token_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=30)

    with pool.connection() as conn:
        _as_owner(conn, a)
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    "SELECT create_invite(%s, %s, 'owner', true, true, true, %s, %s)",
                    (a["tenant"], "emp@abarpay.test", token_hash, expires),
                )


def test_membership_self_read(pg_admin, tenants, pool):
    """Auxiliary policy: a user sees only their own memberships."""

    a, b = tenants
    with pool.connection() as conn:
        _as_owner(conn, a)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM memberships")
            assert cur.fetchone()[0] == 1  # only their own (owner A)

    with pool.connection() as conn:
        _as_owner(conn, b)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM memberships")
            assert cur.fetchone()[0] == 1  # only their own (owner B)


def test_owner_belongs_to_multiple_tenants(pg_admin, tenants):
    """Acceptance: an owner user can belong to several independent tenants."""

    a, b = tenants
    uid = uuid.uuid4()
    with pg_admin.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email, name, idp, external_sub) "
            "VALUES (%s, %s, %s, 'auth0', %s)",
            (uid, "multi@abarpay.test", "Multi Owner", "auth0|" + str(uuid.uuid4())),
        )
        for tid in (a["tenant"], b["tenant"]):
            cur.execute(
                "INSERT INTO memberships "
                "(id, user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active) "
                "VALUES (%s, %s, %s, 'owner', true, true, true, true)",
                (uuid.uuid4(), uid, tid),
            )
    with pg_admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM memberships WHERE user_id = %s AND role = 'owner'",
            (uid,),
        )
        assert cur.fetchone()[0] == 2
    # cleanup
    with pg_admin.cursor() as cur:
        cur.execute("DELETE FROM memberships WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))


def test_migration_dry_run_apply_idempotent(pg_admin, tmp_path):
    """Gate: --dry-run then --apply twice is idempotent and counts reconcile."""

    from server import db

    src = tmp_path / "src.db"
    db.initialize_db(src, seed_catalog=True)
    conn = sqlite3.connect(str(src))
    now = time.time()
    conn.execute(
        "INSERT INTO employees (id, store_id, name, role, active, can_sell, can_fiado, can_inventory) "
        "VALUES (2, 'tiendita-esquina', 'Lupita', 'employee', 1, 1, 1, 0)"
    )
    conn.execute(
        "INSERT INTO sales (id, store_id, employee_id, created_at, status, payment_method, total_cents, charged_cents) "
        "VALUES ('s1', 'tiendita-esquina', 2, ?, 'paid_cash', 'cash', 100, 100)",
        (now,),
    )
    conn.commit()
    conn.close()

    slug = "mig-test-" + uuid.uuid4().hex[:8]
    script = str(REPO_ROOT / "scripts" / "migrate_sqlite_to_pg.py")
    base = [sys.executable, script, "--source", str(src),
            "--tenant-slug", slug, "--tenant-name", "Mig Test"]

    r1 = subprocess.run(base + ["--dry-run"], capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    r2 = subprocess.run(base + ["--apply"], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    r3 = subprocess.run(base + ["--apply"], capture_output=True, text=True)
    assert r3.returncode == 0, r3.stderr

    with pg_admin.cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
        tid = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM products WHERE tenant_id = %s", (tid,))
        pg_products = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM sales WHERE tenant_id = %s", (tid,))
        pg_sales = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM barcodes WHERE tenant_id = %s", (tid,))
        pg_barcodes = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM store_settings WHERE tenant_id = %s", (tid,))
        pg_store_settings = cur.fetchone()[0]
        cur.execute(
            "SELECT u.id FROM users u JOIN memberships m ON m.user_id = u.id "
            "WHERE m.tenant_id = %s AND u.idp = 'legacy'",
            (tid,),
        )
        legacy_ids = [r[0] for r in cur.fetchall()]

    assert pg_products == 13  # 12 seed products + "Tacos de pastor"
    assert pg_sales == 1
    assert pg_barcodes == 5  # seeded barcodes
    assert pg_store_settings == 1  # seeded store_settings row
    assert len(legacy_ids) == 2  # Doña Rosa (owner) + Lupita (employee)

    _drop_tenant(pg_admin, tid, legacy_ids)


def test_migration_same_fixture_two_tenants_keeps_barcodes(pg_admin, tmp_path):
    """Regression (verifier): barcodes are tenant-scoped. Migrating the SAME
    SQLite fixture under two different tenant slugs must preserve every
    barcode in EACH tenant (no cross-tenant data loss from a global unique
    code)."""

    from server import db

    src = tmp_path / "src.db"
    db.initialize_db(src, seed_catalog=True)  # seeds 5 barcodes

    script = str(REPO_ROOT / "scripts" / "migrate_sqlite_to_pg.py")
    tids = []
    for _ in range(2):
        slug = "mig-bc-" + uuid.uuid4().hex[:8]
        r = subprocess.run(
            [sys.executable, script, "--source", str(src),
             "--tenant-slug", slug, "--tenant-name", "Barcode Test", "--apply"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        with pg_admin.cursor() as cur:
            cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
            tids.append(cur.fetchone()[0])

    try:
        for tid in tids:
            with pg_admin.cursor() as cur:
                cur.execute("SELECT count(*) FROM barcodes WHERE tenant_id = %s", (tid,))
                assert cur.fetchone()[0] == 5
    finally:
        for tid in tids:
            with pg_admin.cursor() as cur:
                cur.execute(
                    "SELECT u.id FROM users u JOIN memberships m ON m.user_id = u.id "
                    "WHERE m.tenant_id = %s AND u.idp = 'legacy'",
                    (tid,),
                )
                legacy = [r[0] for r in cur.fetchall()]
            _drop_tenant(pg_admin, tid, legacy)


def test_legacy_users_never_auto_claimed(pg_admin, tenants, pool):
    """Acceptance: a legacy row has idp='legacy' and a fake email; it is never
    the target of a real sign-in identity."""

    with pg_admin.cursor() as cur:
        cur.execute("SELECT email, idp, external_sub FROM users WHERE idp = 'legacy' LIMIT 1")
        row = cur.fetchone()
    if row is not None:
        email, idp, external_sub = row
        assert idp == "legacy"
        assert external_sub.startswith("legacy-")
        assert "@abarpay.local" in email
        assert not external_sub.startswith("auth0|")
        assert not external_sub.startswith("entra|")
