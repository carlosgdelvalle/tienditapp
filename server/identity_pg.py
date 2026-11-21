"""PostgreSQL IdentityStore adapter for Abarpay (available, not default).

Implements the IdentityStore protocol from server/identity.py against the
frozen PostgreSQL schema in migrations/001_schema.sql, using the tenancy-aware
pool and set_tenant_context from server/db_pg.py. Membership and invite
*writes* are routed through the SECURITY DEFINER functions
(manage_membership, create_invite, accept_invite), which are the only escape
from pure RLS for those tables.

The SQLite demo (server/db.py) stays the default runtime; this adapter is
opted in explicitly:

    from server.db_pg import create_pool
    from server.identity_pg import PostgresIdentityStore
    from server.main import create_app

    pool = create_pool()  # or set ABARPAY_PG_DSN
    app = create_app(identity_store=PostgresIdentityStore(pool))

Scope and current gaps
----------------------
001_schema.sql only carries the identity core (tenants, stores, users,
memberships, invites) plus three SECURITY DEFINER functions, and RLS is
deny-by-default: the service role may only SELECT its own users row and its own
memberships, and memberships/invites are writable only through the three
functions. This adapter therefore implements exactly what the schema supports
and raises NotImplementedError (with a precise reason) for the rest:

Supported (PostgreSQL):
  * get_tenant, get_store
  * get_user, list_memberships, get_membership   (self-read under RLS)
  * upsert_membership, update_membership          (manage_membership)
  * save_invite                                   (create_invite)

Requires schema additions (not yet in 001_schema.sql):
  * find_user / create_user: users is self-read only; needs a SECURITY DEFINER
    resolve/create function (or a write policy) for OIDC sign-in.
  * list_tenant_members / count_active_owners: memberships is self-read only;
    needs an owner-wide read policy or a SECURITY DEFINER function.
  * get_invite: invites is FORCE RLS with no read policy; needs a read function.
  * claim_invite: the accept_invite function requires the invite's tenant_id,
    which the IdentityStore.claim_invite signature does not carry.
  * devices / challenges / sessions: no tables exist in the frozen schema.

Actor context
-------------
manage_membership and create_invite validate that current_setting('app.user_id')
is an active owner of the tenant. The IdentityStore protocol methods do not
receive an actor, so the acting owner is threaded through a context variable;
the future request wiring must wrap owner mutations in actor_context():

    from server.identity_pg import actor_context
    with actor_context(owner_user_id):
        store.save_invite(invite)

accept_invite is self-service (it validates the token, not the caller) and does
not need an actor.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import db_pg
from .identity import (
    IdentityStore,
    Invite,
    MemberRow,
    Membership,
    StoreRecord,
    TenantRecord,
    User,
)

# Acting owner for SECURITY DEFINER writes (see module docstring).
_ACTOR: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "abarpay_identity_actor", default=None
)


@contextmanager
def actor_context(user_id: str) -> Iterator[None]:
    """Scope the acting owner for manage_membership / create_invite writes."""

    token = _ACTOR.set(user_id)
    try:
        yield
    finally:
        _ACTOR.reset(token)


def _to_epoch(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _from_epoch(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _membership_from_row(row: dict) -> Membership:
    return Membership(
        user_id=str(row["user_id"]),
        tenant_id=str(row["tenant_id"]),
        role=row["role"],
        can_sell=bool(row["can_sell"]),
        can_fiado=bool(row["can_fiado"]),
        can_inventory=bool(row["can_inventory"]),
        active=bool(row["active"]),
    )


class PostgresIdentityStore(IdentityStore):
    """IdentityStore over PostgreSQL, writes through SECURITY DEFINER fns."""

    def __init__(self, pool: ConnectionPool | None = None, *, dsn: str | None = None) -> None:
        self._pool = pool or db_pg.create_pool(dsn or db_pg.DEFAULT_DSN)
        self._owns_pool = pool is None

    def close(self) -> None:
        if self._owns_pool:
            self._pool.close()

    # ------------------------------------------------------------------ users
    def find_user(self, idp: str, external_sub: str) -> User | None:
        raise self._unsupported(
            "find_user",
            "users is self-read only (user_self_read) with no resolve/create "
            "SECURITY DEFINER function; OIDC sign-in cannot claim a user yet.",
        )

    def create_user(self, idp: str, external_sub: str, email: str | None, name: str | None) -> User:
        raise self._unsupported(
            "create_user",
            "users has no INSERT policy and no SECURITY DEFINER create function.",
        )

    def get_user(self, user_id: str) -> User | None:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id="", user_id=user_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, email, name, idp, external_sub "
                    "FROM users WHERE id = %s::uuid",
                    (user_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return User(
            id=str(row["id"]),
            email=row["email"] or "",
            name=row["name"] or "",
            idp=row["idp"],
            external_sub=row["external_sub"],
        )

    # ------------------------------------------------------ tenants / stores
    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, slug, name, legal_name, rfc, timezone, status "
                    "FROM tenants WHERE id = %s::uuid",
                    (tenant_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return TenantRecord(
            id=str(row["id"]),
            slug=row["slug"],
            name=row["name"],
            legal_name=row["legal_name"] or "",
            rfc=row["rfc"],
            timezone=row["timezone"],
            status=row["status"],
        )

    def get_store(self, tenant_id: str) -> StoreRecord | None:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, tenant_id, name FROM stores "
                    "WHERE tenant_id = %s::uuid",
                    (tenant_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return StoreRecord(id=str(row["id"]), tenant_id=str(row["tenant_id"]), name=row["name"])

    # ------------------------------------------------------------- memberships
    def list_memberships(self, user_id: str) -> list[Membership]:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id="", user_id=user_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT user_id, tenant_id, role, can_sell, can_fiado, "
                    "can_inventory, active FROM memberships WHERE user_id = %s::uuid",
                    (user_id,),
                )
                rows = cur.fetchall()
        return [_membership_from_row(r) for r in rows]

    def get_membership(self, user_id: str, tenant_id: str) -> Membership | None:
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id="", user_id=user_id)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT user_id, tenant_id, role, can_sell, can_fiado, "
                    "can_inventory, active FROM memberships "
                    "WHERE user_id = %s::uuid AND tenant_id = %s::uuid",
                    (user_id, tenant_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return _membership_from_row(row)

    def list_tenant_members(self, tenant_id: str) -> list[MemberRow]:
        raise self._unsupported(
            "list_tenant_members",
            "memberships is self-read only; an owner cannot list other members "
            "without an owner-wide read policy or SECURITY DEFINER function.",
        )

    def count_active_owners(self, tenant_id: str) -> int:
        raise self._unsupported(
            "count_active_owners",
            "memberships is self-read only; last-owner protection needs an "
            "owner-wide read policy or SECURITY DEFINER function.",
        )

    def upsert_membership(
        self,
        user_id: str,
        tenant_id: str,
        role: str,
        can_sell: bool,
        can_fiado: bool,
        can_inventory: bool,
        active: bool,
    ) -> Membership:
        actor = self._require_actor()
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id=actor)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT public.manage_membership("
                    "%s::uuid, %s::uuid, %s, %s, %s, %s, %s)",
                    (tenant_id, user_id, role, can_sell, can_fiado, can_inventory, active),
                )
            conn.commit()
        return Membership(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            can_sell=bool(can_sell),
            can_fiado=bool(can_fiado),
            can_inventory=bool(can_inventory),
            active=bool(active),
        )

    def update_membership(
        self,
        user_id: str,
        tenant_id: str,
        *,
        role: str | None = None,
        can_sell: bool | None = None,
        can_fiado: bool | None = None,
        can_inventory: bool | None = None,
        active: bool | None = None,
    ) -> Membership | None:
        actor = self._require_actor()
        with self._conn() as conn:
            # Read the current row as the target user (self-read), then write
            # the merged row as the acting owner through manage_membership.
            db_pg.set_tenant_context(conn, tenant_id="", user_id=user_id)
            current = None
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT user_id, tenant_id, role, can_sell, can_fiado, "
                    "can_inventory, active FROM memberships "
                    "WHERE user_id = %s::uuid AND tenant_id = %s::uuid",
                    (user_id, tenant_id),
                )
                row = cur.fetchone()
            if row is None:
                return None
            current = _membership_from_row(row)

            merged_role = current.role if role is None else role
            merged_can_sell = current.can_sell if can_sell is None else can_sell
            merged_can_fiado = current.can_fiado if can_fiado is None else can_fiado
            merged_can_inventory = current.can_inventory if can_inventory is None else can_inventory
            merged_active = current.active if active is None else active

            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id=actor)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT public.manage_membership("
                    "%s::uuid, %s::uuid, %s, %s, %s, %s, %s)",
                    (
                        tenant_id,
                        user_id,
                        merged_role,
                        merged_can_sell,
                        merged_can_fiado,
                        merged_can_inventory,
                        merged_active,
                    ),
                )
            conn.commit()
        return Membership(
            user_id=user_id,
            tenant_id=tenant_id,
            role=merged_role,
            can_sell=bool(merged_can_sell),
            can_fiado=bool(merged_can_fiado),
            can_inventory=bool(merged_can_inventory),
            active=bool(merged_active),
        )

    # ---------------------------------------------------------------- devices
    def save_device(self, device) -> None:
        raise self._unsupported("save_device", "no devices table in the frozen schema.")

    def get_device(self, user_id: str, device_id: str):
        raise self._unsupported("get_device", "no devices table in the frozen schema.")

    def list_devices(self, user_id: str):
        raise self._unsupported("list_devices", "no devices table in the frozen schema.")

    def delete_device(self, user_id: str, device_id: str) -> bool:
        raise self._unsupported("delete_device", "no devices table in the frozen schema.")

    # ------------------------------------------------------------- challenges
    def save_challenge(self, challenge) -> None:
        raise self._unsupported("save_challenge", "no challenges table in the frozen schema.")

    def get_challenge(self, challenge_id: str):
        raise self._unsupported("get_challenge", "no challenges table in the frozen schema.")

    def transition_challenge(self, challenge_id: str, from_status: str, to_status: str, **fields):
        raise self._unsupported(
            "transition_challenge", "no challenges table in the frozen schema."
        )

    # ---------------------------------------------------------------- sessions
    def save_session(self, session) -> None:
        raise self._unsupported("save_session", "no sessions table in the frozen schema.")

    def get_session(self, token: str):
        raise self._unsupported("get_session", "no sessions table in the frozen schema.")

    def revoke_session(self, token: str) -> None:
        raise self._unsupported("revoke_session", "no sessions table in the frozen schema.")

    def revoke_sessions_for_user(self, user_id: str) -> None:
        raise self._unsupported(
            "revoke_sessions_for_user", "no sessions table in the frozen schema."
        )

    # ----------------------------------------------------------------- invites
    def save_invite(self, invite: Invite) -> None:
        actor = self._require_actor()
        expires = _from_epoch(invite.expires_at)
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=invite.tenant_id, user_id=actor)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT public.create_invite("
                    "%s::uuid, %s, %s, %s, %s, %s, %s, %s::timestamptz)",
                    (
                        invite.tenant_id,
                        invite.email,
                        invite.role,
                        invite.can_sell,
                        invite.can_fiado,
                        invite.can_inventory,
                        invite.token_hash,
                        expires,
                    ),
                )
            conn.commit()

    def get_invite(self, token_hash: str) -> Invite | None:
        raise self._unsupported(
            "get_invite",
            "invites is FORCE RLS with no read policy; needs a SECURITY DEFINER "
            "read function (e.g. lookup_invite).",
        )

    def claim_invite(self, token_hash: str, user_id: str, accepted_at: float) -> str | None:
        raise self._unsupported(
            "claim_invite",
            "accept_invite needs the invite's tenant_id, which claim_invite's "
            "signature does not carry; add tenant_id to claim_invite or a "
            "lookup_invite SECURITY DEFINER read function.",
        )

    # --------------------------------------------------------------- helpers
    @contextmanager
    def _conn(self) -> Iterator[psycopg.Connection]:
        with self._pool.connection() as conn:
            yield conn

    def _require_actor(self) -> str:
        actor = _ACTOR.get()
        if not actor:
            raise RuntimeError(
                "PostgresIdentityStore: no acting owner; wrap the mutation in "
                "identity_pg.actor_context(owner_user_id)."
            )
        return actor

    @staticmethod
    def _unsupported(method: str, reason: str) -> NotImplementedError:
        return NotImplementedError(
            f"PostgresIdentityStore.{method} is not supported by the current "
            f"migrations/001_schema.sql: {reason}"
        )
