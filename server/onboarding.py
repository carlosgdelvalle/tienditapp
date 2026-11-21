"""Onboarding and CLABE / bank-account domain core for Abarpay.

Owns the business rules behind business onboarding and the CoDi collection
account:

- atomic signup: tenant + store + owner + owner membership in ONE transaction,
  so a new store can never exist half-created. A fresh store is seeded with
  ZERO demo data (no catalog, no employees, no foreign staff).
- CLABE validation (18 digits, 3-7-1 weights, modulo 10) and bank-account
  registration with an ASYNC status (PENDING -> ACTIVE) plus an email
  notification path. The account is labeled SIMULADO until a real pey merchant
  account exists (there is no real pey call in this module).
- the routing helper resolve_active_bank_account(), which returns the tenant's
  ACTIVE bank account id so a CoDi charge is routed to the right account.

Persistence is behind the OnboardingStore protocol. The production adapter is a
thin PostgreSQL mapping: the atomic signup runs through the SECURITY DEFINER
function signup_tenant() (the only escape from pure RLS for the FIRST owner
membership - manage_membership refuses the owner role), and bank_accounts are
reached through their tenant-scoped RLS policy. MemoryOnboardingStore is the
SIMULADO reference/test implementation and never touches the network.

The production DDL is shipped here (ONBOARDING_DDL) so migrations/ stays
untouched; the integrator runs ensure_onboarding_schema() once with a
migrator/superuser connection (the service role has no DDL).
"""

from __future__ import annotations

import re
import secrets
import threading
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import db_pg
from .identity import (
    Membership,
    MemoryIdentityStore,
    StoreRecord,
    TenantRecord,
    User,
)
from .identity_pg import PostgresIdentityStore

# ---------------------------------------------------------------------------
# Async bank-account status (matches the pey codiStatus vocabulary).
# ---------------------------------------------------------------------------

STATUS_PENDING = "PENDING"
STATUS_PROCESSING = "PROCESSING"
STATUS_ACTIVE = "ACTIVE"
STATUS_ERROR = "ERROR"

VALID_BANK_STATUSES = {STATUS_PENDING, STATUS_PROCESSING, STATUS_ACTIVE, STATUS_ERROR}
ACTIVATABLE_STATUSES = {STATUS_PENDING, STATUS_PROCESSING}

VALID_ENTITIES = {"BUSINESS", "PERSON"}
DEFAULT_TIMEZONE = "America/Mexico_City"

# 3-7-1 weights repeated left-to-right over the first 17 digits.
_CLABE_WEIGHTS = (3, 7, 1)


# ---------------------------------------------------------------------------
# Domain errors (mapped to HTTP by routes_onboarding).
# ---------------------------------------------------------------------------


class OnboardingError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(OnboardingError):
    status_code = 404


class ConflictError(OnboardingError):
    status_code = 409


class ForbiddenError(OnboardingError):
    status_code = 403


class InvalidClabeError(OnboardingError):
    status_code = 400


# ---------------------------------------------------------------------------
# Domain records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignupResult:
    tenant_id: str
    store_id: str
    user_id: str


@dataclass(frozen=True)
class BankAccount:
    id: str  # bankAccountId (local id; pey_account_id is pey's own id)
    tenant_id: str
    alias: str
    name: str
    entity: str  # 'BUSINESS' | 'PERSON'
    status: str  # 'PENDING' | 'PROCESSING' | 'ACTIVE' | 'ERROR'
    last4: str
    pey_account_id: str | None
    simulated: bool
    error_message: str | None
    created_at: float
    updated_at: float
    activated_at: float | None


# ---------------------------------------------------------------------------
# CLABE validation
# ---------------------------------------------------------------------------


def _clabe_check_digit(first17: str) -> int:
    total = 0
    for index, digit in enumerate(first17):
        total += int(digit) * _CLABE_WEIGHTS[index % 3]
    return (10 - (total % 10)) % 10


def validate_clabe(clabe: str | None) -> bool:
    """Local CLABE check: 18 digits and a valid 3-7-1 check digit.

    Local validation rejects before any pey call and never replaces pey's own
    validation. The full CLABE never leaves this function's argument.
    """

    if not isinstance(clabe, str) or not re.fullmatch(r"\d{18}", clabe):
        return False
    return int(clabe[17]) == _clabe_check_digit(clabe[:17])


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "tienda"


def _epoch(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# ---------------------------------------------------------------------------
# Email notification path (SIMULADO: no real mail is ever sent).
# ---------------------------------------------------------------------------


class BankAccountNotifier(ABC):
    """Notification path for bank-account status changes (SIMULADO)."""

    @abstractmethod
    def notify_status(self, *, email: str, account: BankAccount) -> None: ...


class MemoryBankAccountNotifier(BankAccountNotifier):
    """SIMULADO in-memory notifier that records what it would have sent."""

    simulated = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []  # (email, bankAccountId, status)

    def notify_status(self, *, email: str, account: BankAccount) -> None:
        self.sent.append((email, account.id, account.status))


# ---------------------------------------------------------------------------
# Store protocol
# ---------------------------------------------------------------------------


class OnboardingStore(ABC):
    """Persistence for onboarding + bank accounts, shaped after the schema."""

    # -- atomic signup ------------------------------------------------------
    @abstractmethod
    def signup(
        self,
        *,
        idp: str,
        external_sub: str,
        email: str,
        owner_name: str,
        slug: str,
        tenant_name: str,
        store_name: str,
        timezone: str,
    ) -> SignupResult: ...

    # -- ownership reads ----------------------------------------------------
    @abstractmethod
    def get_membership(self, user_id: str, tenant_id: str) -> Membership | None: ...

    @abstractmethod
    def get_user(self, user_id: str) -> User | None: ...

    @abstractmethod
    def get_tenant(self, tenant_id: str) -> TenantRecord | None: ...

    @abstractmethod
    def get_store(self, tenant_id: str) -> StoreRecord | None: ...

    # -- clean-seed introspection (used by tests / acceptance) --------------
    @abstractmethod
    def count_products(self, tenant_id: str) -> int: ...

    @abstractmethod
    def count_members(self, tenant_id: str) -> int: ...

    # -- bank accounts ------------------------------------------------------
    @abstractmethod
    def create_bank_account(
        self, *, tenant_id: str, alias: str, name: str, entity: str, clabe: str
    ) -> BankAccount: ...

    @abstractmethod
    def get_bank_account(self, tenant_id: str, bank_account_id: str) -> BankAccount | None: ...

    @abstractmethod
    def list_bank_accounts(self, tenant_id: str) -> list[BankAccount]: ...

    @abstractmethod
    def set_bank_account_status(
        self,
        tenant_id: str,
        bank_account_id: str,
        *,
        from_status: str,
        to_status: str,
        error_message: str | None = None,
    ) -> BankAccount | None: ...

    @abstractmethod
    def get_active_bank_account(self, tenant_id: str) -> BankAccount | None: ...


# ---------------------------------------------------------------------------
# In-memory reference store (SIMULADO / test)
# ---------------------------------------------------------------------------


class MemoryOnboardingStore(OnboardingStore):
    """SIMULADO in-memory store. signup seeds ZERO demo data."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._identity = MemoryIdentityStore()
        self.bank_accounts: dict[str, BankAccount] = {}  # key: bankAccountId
        self._bank_by_tenant: dict[str, list[str]] = {}
        self._products: dict[str, list[object]] = {}
        self._counter = 0

    # -- signup ------------------------------------------------------------
    def signup(
        self,
        *,
        idp: str,
        external_sub: str,
        email: str,
        owner_name: str,
        slug: str,
        tenant_name: str,
        store_name: str,
        timezone: str,
    ) -> SignupResult:
        with self._lock:
            user = self._identity.create_user(idp, external_sub, email, owner_name)
            tenant_id = str(uuid.uuid4())
            store_id = str(uuid.uuid4())
            self._identity.seed_tenant(
                tenant_id=tenant_id,
                slug=slug,
                name=tenant_name,
                store_id=store_id,
                store_name=store_name,
            )
            self._identity.upsert_membership(
                user.id, tenant_id, "owner", True, True, True, True
            )
            # Clean seed: a brand-new store has an empty catalog.
            self._products[tenant_id] = []
        return SignupResult(tenant_id=tenant_id, store_id=store_id, user_id=user.id)

    # -- ownership reads ----------------------------------------------------
    def get_membership(self, user_id: str, tenant_id: str) -> Membership | None:
        return self._identity.get_membership(user_id, tenant_id)

    def get_user(self, user_id: str) -> User | None:
        return self._identity.get_user(user_id)

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        return self._identity.get_tenant(tenant_id)

    def get_store(self, tenant_id: str) -> StoreRecord | None:
        return self._identity.get_store(tenant_id)

    # -- clean-seed introspection ------------------------------------------
    def count_products(self, tenant_id: str) -> int:
        with self._lock:
            return len(self._products.get(tenant_id, []))

    def count_members(self, tenant_id: str) -> int:
        with self._lock:
            return len(self._identity.list_tenant_members(tenant_id))

    # -- bank accounts ------------------------------------------------------
    def create_bank_account(
        self, *, tenant_id: str, alias: str, name: str, entity: str, clabe: str
    ) -> BankAccount:
        now = time.time()
        with self._lock:
            self._counter += 1
            account = BankAccount(
                id=f"ba_sim_{self._counter}",
                tenant_id=tenant_id,
                alias=alias,
                name=name,
                entity=entity,
                status=STATUS_PENDING,
                last4=clabe[-4:],
                pey_account_id=None,
                simulated=True,
                error_message=None,
                created_at=now,
                updated_at=now,
                activated_at=None,
            )
            self.bank_accounts[account.id] = account
            self._bank_by_tenant.setdefault(tenant_id, []).append(account.id)
            return account

    def get_bank_account(self, tenant_id: str, bank_account_id: str) -> BankAccount | None:
        with self._lock:
            account = self.bank_accounts.get(bank_account_id)
            if account is None or account.tenant_id != tenant_id:
                return None
            return account

    def list_bank_accounts(self, tenant_id: str) -> list[BankAccount]:
        with self._lock:
            ids = self._bank_by_tenant.get(tenant_id, [])
            return [self.bank_accounts[i] for i in ids if i in self.bank_accounts]

    def set_bank_account_status(
        self,
        tenant_id: str,
        bank_account_id: str,
        *,
        from_status: str,
        to_status: str,
        error_message: str | None = None,
    ) -> BankAccount | None:
        now = time.time()
        with self._lock:
            account = self.bank_accounts.get(bank_account_id)
            if account is None or account.tenant_id != tenant_id:
                return None
            if account.status != from_status:
                return None
            updated = replace(
                account,
                status=to_status,
                error_message=error_message,
                updated_at=now,
                activated_at=(now if to_status == STATUS_ACTIVE else account.activated_at),
            )
            self.bank_accounts[bank_account_id] = updated
            return updated

    def get_active_bank_account(self, tenant_id: str) -> BankAccount | None:
        with self._lock:
            active = [
                a
                for a in self.bank_accounts.values()
                if a.tenant_id == tenant_id and a.status == STATUS_ACTIVE
            ]
            if not active:
                return None
            return max(active, key=lambda a: (a.activated_at or 0.0, a.created_at))


# ---------------------------------------------------------------------------
# Service (business rules)
# ---------------------------------------------------------------------------


class OnboardingService:
    """Applies the onboarding + bank-account rules over an OnboardingStore."""

    def __init__(
        self,
        store: OnboardingStore,
        *,
        notifier: BankAccountNotifier | None = None,
    ) -> None:
        self._store = store
        self._notifier = notifier

    # -- signup ------------------------------------------------------------
    def signup(
        self,
        *,
        email: str,
        owner_name: str,
        store_name: str,
        idp: str = "auth0",
        external_sub: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> SignupResult:
        email = (email or "").strip()
        owner_name = (owner_name or "").strip()
        store_name = (store_name or "").strip()
        if not email:
            raise OnboardingError("El correo es obligatorio")
        if not owner_name:
            raise OnboardingError("El nombre del dueño es obligatorio")
        if not store_name:
            raise OnboardingError("El nombre de la tienda es obligatorio")
        external = external_sub or f"signup|{uuid.uuid4().hex}"
        slug = f"{_slugify(store_name)}-{secrets.token_hex(4)}"
        return self._store.signup(
            idp=idp,
            external_sub=external,
            email=email,
            owner_name=owner_name,
            slug=slug,
            tenant_name=store_name,
            store_name=store_name,
            timezone=timezone or DEFAULT_TIMEZONE,
        )

    # -- ownership ---------------------------------------------------------
    def require_owner(self, user_id: str, tenant_id: str) -> Membership:
        membership = self._store.get_membership(user_id, tenant_id)
        if membership is None or not membership.active or membership.role != "owner":
            raise ForbiddenError("Solo el dueño puede hacer esto")
        return membership

    def get_user(self, user_id: str) -> User | None:
        return self._store.get_user(user_id)

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        return self._store.get_tenant(tenant_id)

    def get_store(self, tenant_id: str) -> StoreRecord | None:
        return self._store.get_store(tenant_id)

    # -- bank accounts -----------------------------------------------------
    def register_bank_account(
        self,
        *,
        actor_user_id: str,
        tenant_id: str,
        alias: str,
        name: str,
        clabe: str,
        entity: str = "BUSINESS",
    ) -> BankAccount:
        self.require_owner(actor_user_id, tenant_id)
        alias = (alias or "").strip()
        name = (name or "").strip()
        clabe = (clabe or "").strip()
        if not alias:
            raise OnboardingError("El alias es obligatorio")
        if not name:
            raise OnboardingError("El nombre del titular es obligatorio")
        if not validate_clabe(clabe):
            raise InvalidClabeError("La CLABE no es válida")
        if entity not in VALID_ENTITIES:
            raise OnboardingError("La entidad debe ser BUSINESS o PERSON")
        account = self._store.create_bank_account(
            tenant_id=tenant_id, alias=alias, name=name, entity=entity, clabe=clabe
        )
        self._notify(actor_user_id, account)
        return account

    def activate_bank_account(
        self, *, actor_user_id: str, tenant_id: str, bank_account_id: str
    ) -> BankAccount:
        self.require_owner(actor_user_id, tenant_id)
        account = self._store.get_bank_account(tenant_id, bank_account_id)
        if account is None:
            raise NotFoundError("Cuenta bancaria no encontrada")
        if account.status == STATUS_ACTIVE:
            return account  # idempotent
        if account.status not in ACTIVATABLE_STATUSES:
            raise ConflictError("La cuenta no se puede activar desde su estado")
        updated = self._store.set_bank_account_status(
            tenant_id,
            bank_account_id,
            from_status=account.status,
            to_status=STATUS_ACTIVE,
        )
        if updated is None:
            raise ConflictError("La cuenta cambió de estado; reintenta")
        self._notify(actor_user_id, updated)
        return updated

    def list_bank_accounts(self, *, actor_user_id: str, tenant_id: str) -> list[BankAccount]:
        self.require_owner(actor_user_id, tenant_id)
        return self._store.list_bank_accounts(tenant_id)

    def get_bank_account(
        self, *, actor_user_id: str, tenant_id: str, bank_account_id: str
    ) -> BankAccount:
        self.require_owner(actor_user_id, tenant_id)
        account = self._store.get_bank_account(tenant_id, bank_account_id)
        if account is None:
            raise NotFoundError("Cuenta bancaria no encontrada")
        return account

    def resolve_active_bank_account(self, tenant_id: str) -> BankAccount | None:
        """Routing helper: the tenant's ACTIVE account (or None if none yet).

        A CoDi charge must send this account's id as bankAccountId. When there
        is no ACTIVE account the caller (server/pey.py call site) must refuse
        the charge with NO_ACTIVE_BANK_ACCOUNT rather than omit the field.
        """

        return self._store.get_active_bank_account(tenant_id)

    # -- notification ------------------------------------------------------
    def _notify(self, actor_user_id: str, account: BankAccount) -> None:
        if self._notifier is None:
            return
        user = self._store.get_user(actor_user_id)
        email = user.email if user else ""
        if email:
            self._notifier.notify_status(email=email, account=account)


# ---------------------------------------------------------------------------
# Payload helper (shared with routes_onboarding)
# ---------------------------------------------------------------------------


def bank_account_payload(account: BankAccount) -> dict:
    """Owner-facing bank-account view. The full CLABE never appears here."""

    return {
        "bankAccountId": account.id,
        "alias": account.alias,
        "name": account.name,
        "entity": account.entity,
        "codiStatus": account.status,
        "last4": account.last4,
        "simulated": account.simulated,
        "errorMessage": account.error_message,
    }


# ---------------------------------------------------------------------------
# PostgreSQL adapter + production DDL (SECURITY DEFINER signup).
# ---------------------------------------------------------------------------

ONBOARDING_DDL = """
-- Bank-account columns for the async production contract (additive; the
-- frozen demo columns clabe/bank_name/account_holder/active stay intact).
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS alias text NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS account_name text NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS entity text NOT NULL DEFAULT 'BUSINESS';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'PENDING';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS last4 text NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS pey_account_id text;
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS simulated boolean NOT NULL DEFAULT true;
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS error_message text;
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS activated_at timestamptz;

-- Atomic signup: the ONLY way the first owner membership is created. The
-- service role cannot write tenants/stores/users/memberships directly
-- (membership writes are owner-only and manage_membership refuses the owner
-- role), so this SECURITY DEFINER function is the escape hatch that creates
-- tenant + store + owner + owner membership in ONE transaction.
CREATE OR REPLACE FUNCTION signup_tenant(
    p_idp text,
    p_external_sub text,
    p_email text,
    p_owner_name text,
    p_slug text,
    p_tenant_name text,
    p_store_name text,
    p_timezone text
)
RETURNS TABLE (tenant_id uuid, store_id uuid, user_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user uuid;
    v_tenant uuid;
    v_store uuid;
BEGIN
    INSERT INTO public.users (email, name, idp, external_sub)
    VALUES (coalesce(p_email, ''), coalesce(p_owner_name, ''), p_idp, p_external_sub)
    ON CONFLICT (idp, external_sub) DO NOTHING;

    SELECT u.id INTO v_user
    FROM public.users u
    WHERE u.idp = p_idp AND u.external_sub = p_external_sub;

    IF v_user IS NULL THEN
        RAISE EXCEPTION 'user not found after create' USING ERRCODE = '23505';
    END IF;

    v_tenant := gen_random_uuid();
    INSERT INTO public.tenants (id, slug, name, timezone, status)
    VALUES (v_tenant, p_slug, p_tenant_name,
            coalesce(p_timezone, 'America/Mexico_City'), 'active');

    v_store := gen_random_uuid();
    INSERT INTO public.stores (id, tenant_id, name)
    VALUES (v_store, v_tenant, coalesce(p_store_name, p_tenant_name));

    INSERT INTO public.memberships
        (user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active)
    VALUES
        (v_user, v_tenant, 'owner', true, true, true, true);

    RETURN QUERY SELECT v_tenant, v_store, v_user;
END;
$$;

-- Clean-seed introspection (memberships use a self-read policy, so a plain
-- tenant-scoped count would always see zero; this count is internal-only).
CREATE OR REPLACE FUNCTION count_tenant_members(p_tenant_id uuid)
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT count(*) FROM public.memberships WHERE tenant_id = p_tenant_id;
$$;

REVOKE ALL ON FUNCTION signup_tenant(text, text, text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION count_tenant_members(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION signup_tenant(text, text, text, text, text, text, text, text) TO abarpay_app;
GRANT EXECUTE ON FUNCTION count_tenant_members(uuid) TO abarpay_app;
"""


def ensure_onboarding_schema(admin_conn: psycopg.Connection) -> None:
    """Apply the onboarding DDL (idempotent).

    Run ONCE by the migrator with a superuser/table-owner connection; the
    service role (abarpay_app) has no DDL privileges. The connection is used
    as-is (autocommit or an explicit commit by the caller both work).
    """

    with admin_conn.cursor() as cur:
        cur.execute(ONBOARDING_DDL)


def _bank_account_from_row(row: dict) -> BankAccount:
    return BankAccount(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        alias=row["alias"] or "",
        name=row["account_name"] or "",
        entity=row["entity"] or "BUSINESS",
        status=row["status"] or STATUS_PENDING,
        last4=row["last4"] or "",
        pey_account_id=row["pey_account_id"],
        simulated=bool(row["simulated"]),
        error_message=row["error_message"],
        created_at=_epoch(row["created_at"]) or 0.0,
        updated_at=_epoch(row["updated_at"]) or 0.0,
        activated_at=_epoch(row["activated_at"]),
    )


_BANK_ACCOUNT_SELECT = """
    SELECT id, tenant_id, alias, account_name, entity, status, last4,
           pey_account_id, simulated, error_message, created_at, updated_at,
           activated_at
    FROM bank_accounts
"""


class PostgresOnboardingStore(OnboardingStore):
    """OnboardingStore over PostgreSQL: SECURITY DEFINER signup + RLS bank
    accounts. Reuses PostgresIdentityStore for the ownership reads."""

    def __init__(self, pool: ConnectionPool | None = None, *, dsn: str | None = None) -> None:
        self._pool = pool or db_pg.create_pool(dsn or db_pg.DEFAULT_DSN)
        self._owns_pool = pool is None
        self._identity = PostgresIdentityStore(self._pool)

    def close(self) -> None:
        if self._owns_pool:
            self._pool.close()

    @contextmanager
    def _conn(self) -> Iterator[psycopg.Connection]:
        with self._pool.connection() as conn:
            yield conn

    # -- signup ------------------------------------------------------------
    def signup(
        self,
        *,
        idp: str,
        external_sub: str,
        email: str,
        owner_name: str,
        slug: str,
        tenant_name: str,
        store_name: str,
        timezone: str,
    ) -> SignupResult:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT tenant_id, store_id, user_id "
                    "FROM public.signup_tenant(%s, %s, %s, %s, %s, %s, %s, %s)",
                    (idp, external_sub, email, owner_name, slug, tenant_name,
                     store_name, timezone),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("signup_tenant returned no row")
        return SignupResult(
            tenant_id=str(row["tenant_id"]),
            store_id=str(row["store_id"]),
            user_id=str(row["user_id"]),
        )

    # -- ownership reads ----------------------------------------------------
    def get_membership(self, user_id: str, tenant_id: str) -> Membership | None:
        return self._identity.get_membership(user_id, tenant_id)

    def get_user(self, user_id: str) -> User | None:
        return self._identity.get_user(user_id)

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        return self._identity.get_tenant(tenant_id)

    def get_store(self, tenant_id: str) -> StoreRecord | None:
        return self._identity.get_store(tenant_id)

    # -- clean-seed introspection ------------------------------------------
    def count_products(self, tenant_id: str) -> int:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM products")
                return int(cur.fetchone()[0])

    def count_members(self, tenant_id: str) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT public.count_tenant_members(%s::uuid)", (tenant_id,)
                )
                return int(cur.fetchone()[0])

    # -- bank accounts ------------------------------------------------------
    def create_bank_account(
        self, *, tenant_id: str, alias: str, name: str, entity: str, clabe: str
    ) -> BankAccount:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """INSERT INTO bank_accounts
                       (tenant_id, clabe, alias, account_name, entity, status,
                        last4, simulated, active)
                       VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, true, false)
                       RETURNING id, tenant_id, alias, account_name, entity,
                                 status, last4, pey_account_id, simulated,
                                 error_message, created_at, updated_at, activated_at""",
                    (tenant_id, clabe, alias, name, entity, STATUS_PENDING, clabe[-4:]),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("bank account insert returned no row")
        return _bank_account_from_row(row)

    def get_bank_account(self, tenant_id: str, bank_account_id: str) -> BankAccount | None:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _BANK_ACCOUNT_SELECT
                    + " WHERE tenant_id = %s::uuid AND id = %s::uuid",
                    (tenant_id, bank_account_id),
                )
                row = cur.fetchone()
        return _bank_account_from_row(row) if row else None

    def list_bank_accounts(self, tenant_id: str) -> list[BankAccount]:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _BANK_ACCOUNT_SELECT
                    + " WHERE tenant_id = %s::uuid ORDER BY created_at ASC",
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return [_bank_account_from_row(r) for r in rows]

    def set_bank_account_status(
        self,
        tenant_id: str,
        bank_account_id: str,
        *,
        from_status: str,
        to_status: str,
        error_message: str | None = None,
    ) -> BankAccount | None:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """UPDATE bank_accounts
                       SET status = %s,
                           error_message = %s,
                           updated_at = now(),
                           activated_at = CASE WHEN %s = 'ACTIVE' THEN now()
                                               ELSE activated_at END,
                           active = (%s = 'ACTIVE')
                       WHERE tenant_id = %s::uuid AND id = %s::uuid AND status = %s
                       RETURNING id, tenant_id, alias, account_name, entity,
                                 status, last4, pey_account_id, simulated,
                                 error_message, created_at, updated_at, activated_at""",
                    (
                        to_status,
                        error_message,
                        to_status,
                        to_status,
                        tenant_id,
                        bank_account_id,
                        from_status,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return _bank_account_from_row(row) if row else None

    def get_active_bank_account(self, tenant_id: str) -> BankAccount | None:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _BANK_ACCOUNT_SELECT
                    + """ WHERE tenant_id = %s::uuid AND status = 'ACTIVE'
                          ORDER BY activated_at DESC NULLS LAST, created_at DESC
                          LIMIT 1""",
                    (tenant_id,),
                )
                row = cur.fetchone()
        return _bank_account_from_row(row) if row else None
