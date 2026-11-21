"""PostgreSQL IdentityStore adapter for Abarpay (available, not default).

Implements the IdentityStore protocol from server/identity.py against the
frozen PostgreSQL schema in migrations/001_schema.sql, using the tenancy-aware
pool and set_tenant_context from server/db_pg.py. Membership and invite
*writes* are routed through the SECURITY DEFINER functions
(manage_membership, create_invite, accept_invite), which are the only escape
from pure RLS for those tables. Devices, challenges and sessions are likewise
reached only through their SECURITY DEFINER functions because their domain keys
are user- or token-scoped rather than tenant-scoped.

The SQLite demo (server/db.py) stays the default runtime; this adapter is
opted in explicitly:

    from server.db_pg import create_pool
    from server.identity_pg import PostgresIdentityStore
    from server.main import create_app

    pool = create_pool()  # or set ABARPAY_PG_DSN
    app = create_app(identity_store=PostgresIdentityStore(pool))

Actor context
-------------
manage_membership, create_invite and list_tenant_members validate that
current_setting('app.user_id') is an active owner of the tenant. The
IdentityStore protocol methods do not receive an actor, so the acting owner is
threaded through a context variable; the request wiring must wrap owner
mutations in actor_context():

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
    Challenge,
    Device,
    IdentityStore,
    Invite,
    MemberRow,
    Membership,
    SessionRecord,
    StoreRecord,
    TenantRecord,
    User,
    sha256_hex,
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


def _user_from_row(row: dict) -> User:
    return User(
        id=str(row["id"]),
        email=row["email"] or "",
        name=row["name"] or "",
        idp=row["idp"],
        external_sub=row["external_sub"],
    )


def _device_from_row(row: dict) -> Device:
    return Device(
        device_id=row["device_id"],
        user_id=str(row["user_id"]),
        public_key=row["public_key"],
        label=row["label"],
        created_at=_to_epoch(row["created_at"]),
        last_seen_at=_to_epoch(row["last_seen_at"]),
    )


def _challenge_from_row(row: dict) -> Challenge:
    return Challenge(
        id=row["challenge_id"],
        code=row["code"],
        intent=row["intent"],
        nonce=row["nonce"],
        created_at=_to_epoch(row["created_at"]),
        expires_at=_to_epoch(row["expires_at"]),
        status=row["status"],
        browser_token_hash=row["browser_token_hash"],
        approver_user_id=str(row["approver_user_id"]) if row["approver_user_id"] else None,
        approver_device_id=row["approver_device_id"],
        selected_tenant_id=str(row["tenant_id"]) if row["tenant_id"] else None,
        approved_at=_to_epoch(row["approved_at"]),
        redeemed_at=_to_epoch(row["redeemed_at"]),
    )


def _session_from_row(row: dict, token: str) -> SessionRecord:
    return SessionRecord(
        token=token,
        user_id=str(row["user_id"]),
        tenant_id=str(row["tenant_id"]) if row["tenant_id"] else None,
        csrf_token=row["csrf_token"],
        created_at=_to_epoch(row["created_at"]),
        expires_at=_to_epoch(row["expires_at"]),
        revoked_at=_to_epoch(row["revoked_at"]),
    )


def _invite_from_row(row: dict) -> Invite:
    return Invite(
        token_hash=row["token_hash"],
        tenant_id=str(row["tenant_id"]),
        email=row["email"],
        role=row["role"],
        can_sell=bool(row["can_sell"]),
        can_fiado=bool(row["can_fiado"]),
        can_inventory=bool(row["can_inventory"]),
        created_at=_to_epoch(row["created_at"]),
        expires_at=_to_epoch(row["expires_at"]),
        accepted_at=_to_epoch(row["accepted_at"]),
        revoked_at=_to_epoch(row["revoked_at"]),
        accepted_by=None,  # in-memory bookkeeping; not part of the frozen schema
    )


def _member_row_from_row(row: dict) -> MemberRow:
    return MemberRow(
        user_id=str(row["user_id"]),
        email=row["email"] or "",
        name=row["name"] or "",
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
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, email, name, idp, external_sub "
                    "FROM public.resolve_user(%s, %s)",
                    (idp, external_sub),
                )
                row = cur.fetchone()
        return _user_from_row(row) if row else None

    def create_user(self, idp: str, external_sub: str, email: str | None, name: str | None) -> User:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id, email, name, idp, external_sub "
                    "FROM public.create_user(%s, %s, %s, %s)",
                    (idp, external_sub, email or "", name or ""),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("create_user returned no row")
        return _user_from_row(row)

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
        return _user_from_row(row) if row else None

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
        return _membership_from_row(row) if row else None

    def list_tenant_members(self, tenant_id: str) -> list[MemberRow]:
        actor = self._require_actor()
        with self._conn() as conn:
            db_pg.set_tenant_context(conn, tenant_id=tenant_id, user_id=actor)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT user_id, email, name, role, can_sell, can_fiado, "
                    "can_inventory, active FROM public.list_tenant_members(%s::uuid)",
                    (tenant_id,),
                )
                rows = cur.fetchall()
        return [_member_row_from_row(r) for r in rows]

    def count_active_owners(self, tenant_id: str) -> int:
        members = self.list_tenant_members(tenant_id)
        return sum(1 for m in members if m.role == "owner" and m.active)

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
    def save_device(self, device: Device) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT public.save_device("
                    "%s::uuid, %s, %s, %s, %s::timestamptz, %s::timestamptz)",
                    (
                        device.user_id,
                        device.device_id,
                        device.public_key,
                        device.label,
                        _from_epoch(device.created_at),
                        _from_epoch(device.last_seen_at) if device.last_seen_at is not None else None,
                    ),
                )
            conn.commit()

    def get_device(self, user_id: str, device_id: str) -> Device | None:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT device_id, user_id, public_key, label, created_at, last_seen_at "
                    "FROM public.get_device(%s::uuid, %s)",
                    (user_id, device_id),
                )
                row = cur.fetchone()
        return _device_from_row(row) if row else None

    def list_devices(self, user_id: str) -> list[Device]:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT device_id, user_id, public_key, label, created_at, last_seen_at "
                    "FROM public.list_devices(%s::uuid)",
                    (user_id,),
                )
                rows = cur.fetchall()
        return [_device_from_row(r) for r in rows]

    def delete_device(self, user_id: str, device_id: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT public.delete_device(%s::uuid, %s)", (user_id, device_id))
                deleted = cur.fetchone()[0]
            conn.commit()
        return bool(deleted)

    # ------------------------------------------------------------- challenges
    def save_challenge(self, challenge: Challenge) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT public.save_challenge("
                    "%s, %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz)",
                    (
                        challenge.id,
                        challenge.code,
                        challenge.intent,
                        challenge.nonce,
                        challenge.status,
                        challenge.browser_token_hash,
                        _from_epoch(challenge.created_at),
                        _from_epoch(challenge.expires_at),
                    ),
                )
            conn.commit()

    def get_challenge(self, challenge_id: str) -> Challenge | None:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT challenge_id, tenant_id, code, intent, nonce, status, "
                    "browser_token_hash, approver_user_id, approver_device_id, "
                    "created_at, expires_at, approved_at, redeemed_at "
                    "FROM public.get_challenge(%s)",
                    (challenge_id,),
                )
                row = cur.fetchone()
        return _challenge_from_row(row) if row else None

    def transition_challenge(
        self, challenge_id: str, from_status: str, to_status: str, **fields: object
    ) -> Challenge | None:
        approver_user_id = fields.get("approver_user_id")
        approver_device_id = fields.get("approver_device_id")
        selected_tenant_id = fields.get("selected_tenant_id")
        approved_at = fields.get("approved_at")
        redeemed_at = fields.get("redeemed_at")
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT challenge_id, tenant_id, code, intent, nonce, status, "
                    "browser_token_hash, approver_user_id, approver_device_id, "
                    "created_at, expires_at, approved_at, redeemed_at "
                    "FROM public.transition_challenge("
                    "%s, %s, %s, %s::uuid, %s, %s::uuid, %s::timestamptz, %s::timestamptz)",
                    (
                        challenge_id,
                        from_status,
                        to_status,
                        approver_user_id,
                        approver_device_id,
                        selected_tenant_id,
                        _from_epoch(approved_at) if approved_at is not None else None,
                        _from_epoch(redeemed_at) if redeemed_at is not None else None,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return _challenge_from_row(row) if row else None

    # ---------------------------------------------------------------- sessions
    def save_session(self, session: SessionRecord) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT public.save_session("
                    "%s, %s::uuid, %s::uuid, %s, %s::timestamptz, %s::timestamptz)",
                    (
                        sha256_hex(session.token),
                        session.user_id,
                        session.tenant_id,
                        session.csrf_token,
                        _from_epoch(session.created_at),
                        _from_epoch(session.expires_at),
                    ),
                )
            conn.commit()

    def get_session(self, token: str) -> SessionRecord | None:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT tenant_id, user_id, csrf_token, created_at, expires_at, revoked_at "
                    "FROM public.get_session(%s)",
                    (sha256_hex(token),),
                )
                row = cur.fetchone()
        return _session_from_row(row, token) if row else None

    def revoke_session(self, token: str) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT public.revoke_session(%s)", (sha256_hex(token),))
            conn.commit()

    def revoke_sessions_for_user(self, user_id: str) -> None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT public.revoke_sessions_for_user(%s::uuid)", (user_id,))
            conn.commit()

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
        return self._invite_by_hash(token_hash)

    def lookup_invite(self, token_hash: str) -> Invite | None:
        return self._invite_by_hash(token_hash)

    def claim_invite(self, token_hash: str, user_id: str, accepted_at: float) -> str | None:
        invite = self.lookup_invite(token_hash)
        if invite is None:
            return None
        if invite.revoked_at is not None or invite.accepted_at is not None:
            # Already accepted/revoked: any value that is not user_id signals a
            # conflict to the caller.
            return ""
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT public.accept_invite(%s, %s::uuid, %s::uuid)",
                        (token_hash, invite.tenant_id, user_id),
                    )
                conn.commit()
            return user_id
        except psycopg.errors.InvalidParameterValue:
            # 'invite not found / no longer valid / expired': lost the race or
            # the invite is gone; report a conflict rather than crashing.
            return ""

    def _invite_by_hash(self, token_hash: str) -> Invite | None:
        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT token_hash, tenant_id, email, role, can_sell, can_fiado, "
                    "can_inventory, created_at, expires_at, accepted_at, revoked_at "
                    "FROM public.get_invite_by_hash(%s)",
                    (token_hash,),
                )
                row = cur.fetchone()
        return _invite_from_row(row) if row else None

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
