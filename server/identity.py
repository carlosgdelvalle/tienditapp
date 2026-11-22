"""Identity domain core for Abarpay: devices, challenges, sessions, invites.

This module owns the business rules behind the OIDC identity layer:

- device linking (Android Keystore public-key registration),
- browser QR challenges (create / approve / exchange) with one-time redemption
  and a 120-second expiry,
- server-side session rotation (the tenant is resolved from the session, never
  from a client-supplied tenant header),
- membership resolution (tenant_id + role from verified identity),
- invitations (32 random bytes, shown once, persisted only as SHA-256), with
  role non-elevation and last-owner protection.

Persistence is behind the IdentityStore protocol. The production adapter is a
thin PostgreSQL mapping over the schema in docs/produccion/02-contratos-y-tenencia.md
(tenants, stores, users, memberships, invites). MemoryIdentityStore is the
reference/test implementation; it stores exactly the contract fields plus a few
in-memory-only bookkeeping columns (noted inline) and never touches the network.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Any, Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

# ---------------------------------------------------------------------------
# Time-to-live constants (aligned with the specs)
# ---------------------------------------------------------------------------

CHALLENGE_TTL_SECONDS = 120
INVITE_TTL_SECONDS = 7 * 24 * 60 * 60
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
DEVICE_RECENT_AUTH_SECONDS = 300

SESSION_COOKIE_NAME = "abarpay_session"
CHALLENGE_COOKIE_NAME = "abarpay_challenge"
SESSION_HEADER_NAME = "X-Abarpay-Session"
CSRF_HEADER_NAME = "X-CSRF-Token"

VALID_INTENTS = {"browser_login", "device_link"}
VALID_ROLES = {"owner", "employee"}


# ---------------------------------------------------------------------------
# Domain errors (mapped to HTTP by auth_routes)
# ---------------------------------------------------------------------------


class IdentityError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(IdentityError):
    status_code = 404


class ConflictError(IdentityError):
    status_code = 409


class ForbiddenError(IdentityError):
    status_code = 403


class UnauthorizedError(IdentityError):
    status_code = 401


# ---------------------------------------------------------------------------
# Domain records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    idp: str
    external_sub: str


@dataclass(frozen=True)
class Membership:
    user_id: str
    tenant_id: str
    role: str  # 'owner' | 'employee'
    can_sell: bool
    can_fiado: bool
    can_inventory: bool
    active: bool


@dataclass(frozen=True)
class TenantRecord:
    id: str
    slug: str
    name: str
    legal_name: str
    rfc: str | None
    timezone: str
    status: str


@dataclass(frozen=True)
class StoreRecord:
    id: str
    tenant_id: str
    name: str


@dataclass(frozen=True)
class Device:
    device_id: str
    user_id: str
    public_key: str  # PEM SubjectPublicKeyInfo
    label: str
    created_at: float
    last_seen_at: float | None


@dataclass(frozen=True)
class Challenge:
    id: str
    code: str
    intent: str
    nonce: str
    created_at: float
    expires_at: float
    status: str  # 'pending' | 'approved' | 'consumed'
    browser_token_hash: str
    approver_user_id: str | None
    approver_device_id: str | None
    selected_tenant_id: str | None
    approved_at: float | None
    redeemed_at: float | None


@dataclass(frozen=True)
class SessionRecord:
    token: str
    user_id: str
    tenant_id: str | None
    csrf_token: str
    created_at: float
    expires_at: float
    revoked_at: float | None


@dataclass(frozen=True)
class Invite:
    token_hash: str
    tenant_id: str
    email: str | None
    role: str
    can_sell: bool
    can_fiado: bool
    can_inventory: bool
    created_at: float
    expires_at: float
    accepted_at: float | None
    revoked_at: float | None
    accepted_by: str | None
    phone: str | None = None  # E.164; phone-bound invites only


@dataclass(frozen=True)
class MemberRow:
    user_id: str
    email: str
    name: str
    role: str
    can_sell: bool
    can_fiado: bool
    can_inventory: bool
    active: bool


# ---------------------------------------------------------------------------
# Crypto helpers
# ---------------------------------------------------------------------------


def sha256_hex(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def new_invite_token() -> str:
    """32 random bytes shown once; only its SHA-256 is persisted."""

    return secrets.token_urlsafe(32)


def hash_invite_token(token: str) -> str:
    return sha256_hex(token)


def new_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def new_challenge_code() -> str:
    """Short human-readable matching code shown on browser and phone."""

    return f"{secrets.randbelow(1_000_000):06d}"


def challenge_signature_payload(challenge: Challenge, chosen_store: str) -> str:
    """Canonical message the device signs (and the server re-verifies)."""

    return "\n".join(
        [
            challenge.id,
            challenge.nonce,
            str(int(challenge.expires_at)),
            challenge.intent,
            chosen_store or "",
        ]
    )


def load_public_key(pem: str) -> Any | None:
    try:
        return serialization.load_pem_public_key(pem.encode("utf-8"))
    except (ValueError, TypeError, UnicodeEncodeError):
        return None


def verify_device_signature(public_key_pem: str, message: str, signature_b64: str) -> bool:
    """Verify an Android Keystore signature over the challenge payload.

    Supports RSA (PKCS#1 v1.5 / SHA-256), EC P-256/384/521 (ECDSA SHA-256) and
    Ed25519. The signature is base64-decoded before verification.
    """

    public_key = load_public_key(public_key_pem)
    if public_key is None:
        return False
    try:
        signature = base64.b64decode(signature_b64 or "", validate=True)
    except (ValueError, TypeError):
        return False
    payload = message.encode("utf-8")

    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
            return True
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
            return True
        if isinstance(public_key, ed25519.Ed25519PublicKey):
            public_key.verify(signature, payload)
            return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Store protocol
# ---------------------------------------------------------------------------


class IdentityStore(ABC):
    """Persistence for the identity domain, shaped after the frozen schema."""

    # users ----------------------------------------------------------------
    @abstractmethod
    def find_user(self, idp: str, external_sub: str) -> User | None: ...

    @abstractmethod
    def create_user(self, idp: str, external_sub: str, email: str | None, name: str | None) -> User: ...

    @abstractmethod
    def get_user(self, user_id: str) -> User | None: ...

    # tenants / stores -----------------------------------------------------
    @abstractmethod
    def get_tenant(self, tenant_id: str) -> TenantRecord | None: ...

    @abstractmethod
    def get_store(self, tenant_id: str) -> StoreRecord | None: ...

    # memberships ----------------------------------------------------------
    @abstractmethod
    def list_memberships(self, user_id: str) -> list[Membership]: ...

    @abstractmethod
    def get_membership(self, user_id: str, tenant_id: str) -> Membership | None: ...

    @abstractmethod
    def list_tenant_members(self, tenant_id: str) -> list[MemberRow]: ...

    @abstractmethod
    def count_active_owners(self, tenant_id: str) -> int: ...

    @abstractmethod
    def upsert_membership(
        self,
        user_id: str,
        tenant_id: str,
        role: str,
        can_sell: bool,
        can_fiado: bool,
        can_inventory: bool,
        active: bool,
    ) -> Membership: ...

    @abstractmethod
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
    ) -> Membership | None: ...

    # devices --------------------------------------------------------------
    @abstractmethod
    def save_device(self, device: Device) -> None: ...

    @abstractmethod
    def get_device(self, user_id: str, device_id: str) -> Device | None: ...

    @abstractmethod
    def list_devices(self, user_id: str) -> list[Device]: ...

    @abstractmethod
    def delete_device(self, user_id: str, device_id: str) -> bool: ...

    # challenges -----------------------------------------------------------
    @abstractmethod
    def save_challenge(self, challenge: Challenge) -> None: ...

    @abstractmethod
    def get_challenge(self, challenge_id: str) -> Challenge | None: ...

    @abstractmethod
    def transition_challenge(
        self, challenge_id: str, from_status: str, to_status: str, **fields: Any
    ) -> Challenge | None: ...

    # sessions -------------------------------------------------------------
    @abstractmethod
    def save_session(self, session: SessionRecord) -> None: ...

    @abstractmethod
    def get_session(self, token: str) -> SessionRecord | None: ...

    @abstractmethod
    def revoke_session(self, token: str) -> None: ...

    @abstractmethod
    def revoke_sessions_for_user(self, user_id: str) -> None: ...

    # invites --------------------------------------------------------------
    @abstractmethod
    def save_invite(self, invite: Invite) -> None: ...

    @abstractmethod
    def get_invite(self, token_hash: str) -> Invite | None: ...

    @abstractmethod
    def lookup_invite(self, token_hash: str) -> Invite | None: ...

    @abstractmethod
    def claim_invite(self, token_hash: str, user_id: str, accepted_at: float) -> str | None: ...

    @abstractmethod
    def accept_invite(self, token_hash: str, user_id: str, tenant_id: str, name: str | None, phone: str | None) -> Membership | None: ...


# ---------------------------------------------------------------------------
# In-memory reference store (SIMULADO / test)
# ---------------------------------------------------------------------------


class MemoryIdentityStore(IdentityStore):
    """SIMULADO in-memory store used by tests; the production PostgreSQL adapter
    implements the same IdentityStore protocol over the frozen schema."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.users: dict[str, User] = {}  # key: idp + ":" + external_sub
        self.tenants: dict[str, TenantRecord] = {}
        self.stores: dict[str, StoreRecord] = {}  # key: tenant_id
        self.memberships: dict[tuple[str, str], Membership] = {}  # (user_id, tenant_id)
        self.devices: dict[tuple[str, str], Device] = {}  # (user_id, device_id)
        self.challenges: dict[str, Challenge] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.invites: dict[str, Invite] = {}  # key: token_hash
        self._user_counter = 0

    # -- users -------------------------------------------------------------
    def _key(self, idp: str, external_sub: str) -> str:
        return f"{idp}:{external_sub}"

    def find_user(self, idp: str, external_sub: str) -> User | None:
        with self._lock:
            return self.users.get(self._key(idp, external_sub))

    def create_user(self, idp: str, external_sub: str, email: str | None, name: str | None) -> User:
        with self._lock:
            key = self._key(idp, external_sub)
            existing = self.users.get(key)
            if existing is not None:
                return existing
            self._user_counter += 1
            user = User(
                id=f"usr_{self._user_counter}",
                email=email or "",
                name=name or "",
                idp=idp,
                external_sub=external_sub,
            )
            self.users[key] = user
            return user

    def get_user(self, user_id: str) -> User | None:
        with self._lock:
            return self._user_by_id(user_id)

    # -- tenants / stores --------------------------------------------------
    def seed_tenant(
        self,
        *,
        tenant_id: str,
        slug: str,
        name: str,
        store_id: str | None = None,
        store_name: str | None = None,
    ) -> None:
        with self._lock:
            self.tenants[tenant_id] = TenantRecord(
                id=tenant_id,
                slug=slug,
                name=name,
                legal_name="",
                rfc=None,
                timezone="America/Mexico_City",
                status="active",
            )
            if store_id is not None:
                self.stores[tenant_id] = StoreRecord(
                    id=store_id, tenant_id=tenant_id, name=store_name or name
                )

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        with self._lock:
            return self.tenants.get(tenant_id)

    def get_store(self, tenant_id: str) -> StoreRecord | None:
        with self._lock:
            return self.stores.get(tenant_id)

    # -- memberships -------------------------------------------------------
    def list_memberships(self, user_id: str) -> list[Membership]:
        with self._lock:
            return [
                m for (uid, _tid), m in self.memberships.items() if uid == user_id
            ]

    def get_membership(self, user_id: str, tenant_id: str) -> Membership | None:
        with self._lock:
            return self.memberships.get((user_id, tenant_id))

    def list_tenant_members(self, tenant_id: str) -> list[MemberRow]:
        with self._lock:
            rows: list[MemberRow] = []
            for (uid, tid), m in self.memberships.items():
                if tid != tenant_id:
                    continue
                user = self._user_by_id(uid)
                rows.append(
                    MemberRow(
                        user_id=uid,
                        email=user.email if user else "",
                        name=user.name if user else "",
                        role=m.role,
                        can_sell=m.can_sell,
                        can_fiado=m.can_fiado,
                        can_inventory=m.can_inventory,
                        active=m.active,
                    )
                )
            return rows

    def count_active_owners(self, tenant_id: str) -> int:
        with self._lock:
            return sum(
                1
                for (_uid, tid), m in self.memberships.items()
                if tid == tenant_id and m.role == "owner" and m.active
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
        with self._lock:
            membership = Membership(
                user_id=user_id,
                tenant_id=tenant_id,
                role=role,
                can_sell=can_sell,
                can_fiado=can_fiado,
                can_inventory=can_inventory,
                active=active,
            )
            self.memberships[(user_id, tenant_id)] = membership
            return membership

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
        with self._lock:
            current = self.memberships.get((user_id, tenant_id))
            if current is None:
                return None
            updated = Membership(
                user_id=current.user_id,
                tenant_id=current.tenant_id,
                role=current.role if role is None else role,
                can_sell=current.can_sell if can_sell is None else can_sell,
                can_fiado=current.can_fiado if can_fiado is None else can_fiado,
                can_inventory=current.can_inventory if can_inventory is None else can_inventory,
                active=current.active if active is None else active,
            )
            self.memberships[(user_id, tenant_id)] = updated
            return updated

    def _user_by_id(self, user_id: str) -> User | None:
        for user in self.users.values():
            if user.id == user_id:
                return user
        return None

    # -- devices -----------------------------------------------------------
    def save_device(self, device: Device) -> None:
        with self._lock:
            self.devices[(device.user_id, device.device_id)] = device

    def get_device(self, user_id: str, device_id: str) -> Device | None:
        with self._lock:
            return self.devices.get((user_id, device_id))

    def list_devices(self, user_id: str) -> list[Device]:
        with self._lock:
            return [
                d for (uid, _did), d in self.devices.items() if uid == user_id
            ]

    def delete_device(self, user_id: str, device_id: str) -> bool:
        with self._lock:
            key = (user_id, device_id)
            if key in self.devices:
                del self.devices[key]
                return True
            return False

    # -- challenges --------------------------------------------------------
    def save_challenge(self, challenge: Challenge) -> None:
        with self._lock:
            self.challenges[challenge.id] = challenge

    def get_challenge(self, challenge_id: str) -> Challenge | None:
        with self._lock:
            return self.challenges.get(challenge_id)

    def transition_challenge(
        self, challenge_id: str, from_status: str, to_status: str, **fields: Any
    ) -> Challenge | None:
        with self._lock:
            current = self.challenges.get(challenge_id)
            if current is None or current.status != from_status:
                return None
            updated = replace(current, status=to_status, **fields)
            self.challenges[challenge_id] = updated
            return updated

    # -- sessions ----------------------------------------------------------
    def save_session(self, session: SessionRecord) -> None:
        with self._lock:
            self.sessions[session.token] = session

    def get_session(self, token: str) -> SessionRecord | None:
        with self._lock:
            return self.sessions.get(token)

    def revoke_session(self, token: str) -> None:
        with self._lock:
            session = self.sessions.get(token)
            if session is not None:
                self.sessions[token] = replace(session, revoked_at=time.time())

    def revoke_sessions_for_user(self, user_id: str) -> None:
        with self._lock:
            for token, session in list(self.sessions.items()):
                if session.user_id == user_id and session.revoked_at is None:
                    self.sessions[token] = replace(session, revoked_at=time.time())

    # -- invites -----------------------------------------------------------
    def save_invite(self, invite: Invite) -> None:
        with self._lock:
            if invite.phone:
                for key, existing in list(self.invites.items()):
                    if (
                        existing.tenant_id == invite.tenant_id
                        and existing.phone == invite.phone
                        and existing.accepted_at is None
                        and existing.revoked_at is None
                        and key != invite.token_hash
                    ):
                        self.invites[key] = replace(existing, revoked_at=time.time())
            self.invites[invite.token_hash] = invite

    def get_invite(self, token_hash: str) -> Invite | None:
        with self._lock:
            return self.invites.get(token_hash)

    def lookup_invite(self, token_hash: str) -> Invite | None:
        with self._lock:
            return self.invites.get(token_hash)

    def claim_invite(self, token_hash: str, user_id: str, accepted_at: float) -> str | None:
        with self._lock:
            invite = self.invites.get(token_hash)
            if invite is None:
                return None
            if invite.accepted_by is not None:
                return invite.accepted_by
            updated = replace(
                invite, accepted_at=accepted_at, accepted_by=user_id
            )
            self.invites[token_hash] = updated
            return user_id

    def accept_invite(self, token_hash: str, user_id: str, tenant_id: str, name: str | None, phone: str | None) -> Membership | None:
        with self._lock:
            invite = self.invites.get(token_hash)
            if invite is None or invite.revoked_at is not None or invite.tenant_id != tenant_id or invite.phone != phone:
                return None
            existing = self.memberships.get((user_id, tenant_id))
            if invite.accepted_at is not None:
                return existing if invite.accepted_by == user_id else None
            self.invites[token_hash] = replace(
                invite, accepted_at=time.time(), accepted_by=user_id
            )
            if name:
                user = self._user_by_id(user_id)
                if user is not None and not user.name:
                    self.users[self._key(user.idp, user.external_sub)] = replace(user, name=name)
            if existing is None:
                membership = Membership(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    role=invite.role,
                    can_sell=invite.can_sell,
                    can_fiado=invite.can_fiado,
                    can_inventory=invite.can_inventory,
                    active=True,
                )
                self.memberships[(user_id, tenant_id)] = membership
                return membership
            return existing


# ---------------------------------------------------------------------------
# Service (business rules)
# ---------------------------------------------------------------------------


class IdentityService:
    """Applies the identity rules over an IdentityStore with an injectable clock."""

    def __init__(
        self,
        store: IdentityStore,
        *,
        now: Callable[[], float] | None = None,
        challenge_ttl: int = CHALLENGE_TTL_SECONDS,
        invite_ttl: int = INVITE_TTL_SECONDS,
        session_ttl: int = SESSION_TTL_SECONDS,
        device_recent_auth_seconds: int = DEVICE_RECENT_AUTH_SECONDS,
    ) -> None:
        self._store = store
        self._now = now or time.time
        self._challenge_ttl = challenge_ttl
        self._invite_ttl = invite_ttl
        self._session_ttl = session_ttl
        self._device_recent_auth_seconds = device_recent_auth_seconds

    # -- identity ----------------------------------------------------------
    def resolve_user(self, idp: str, external_sub: str, email: str | None, name: str | None) -> User:
        user = self._store.find_user(idp, external_sub)
        if user is None:
            user = self._store.create_user(idp, external_sub, email, name)
        return user

    def get_user(self, user_id: str) -> User | None:
        return self._store.get_user(user_id)

    def active_memberships(self, user_id: str) -> list[Membership]:
        return [m for m in self._store.list_memberships(user_id) if m.active]

    def select_tenant(self, user_id: str, tenant_id: str) -> Membership:
        membership = self._store.get_membership(user_id, tenant_id)
        if membership is None or not membership.active:
            raise ForbiddenError("No tienes acceso a esa tienda")
        return membership

    def _require_owner(self, user_id: str, tenant_id: str) -> Membership:
        membership = self._store.get_membership(user_id, tenant_id)
        if membership is None or not membership.active or membership.role != "owner":
            raise ForbiddenError("Solo el dueño puede hacer esto")
        return membership

    def _guard_last_owner(
        self,
        tenant_id: str,
        membership: Membership,
        *,
        new_role: str | None = None,
        new_active: bool | None = None,
    ) -> None:
        was_owner = membership.role == "owner" and membership.active
        still_owner = (new_role if new_role is not None else membership.role) == "owner"
        still_active = new_active if new_active is not None else membership.active
        if was_owner and not (still_owner and still_active):
            if self._store.count_active_owners(tenant_id) <= 1:
                raise ForbiddenError("No puedes quitar al último dueño de la tienda")

    def now(self) -> float:
        return self._now()

    # -- devices -----------------------------------------------------------
    def list_devices(self, user_id: str) -> list[Device]:
        return self._store.list_devices(user_id)

    def register_device(self, user_id: str, device_id: str, public_key: str, label: str) -> Device:
        device_id = (device_id or "").strip()
        label = (label or "").strip()
        if not device_id:
            raise IdentityError("El identificador del dispositivo es obligatorio")
        if not public_key or load_public_key(public_key) is None:
            raise IdentityError("La clave pública del dispositivo no es válida")
        now = self._now()
        device = Device(
            device_id=device_id,
            user_id=user_id,
            public_key=public_key,
            label=label or device_id,
            created_at=now,
            last_seen_at=now,
        )
        self._store.save_device(device)
        return device

    def revoke_device(self, user_id: str, device_id: str) -> None:
        if not self._store.delete_device(user_id, device_id):
            raise NotFoundError("Dispositivo no encontrado")
        # Replacing a phone invalidates the owner's browser sessions too.
        self._store.revoke_sessions_for_user(user_id)

    # -- challenges --------------------------------------------------------
    def create_challenge(self, intent: str) -> tuple[Challenge, str]:
        if intent not in VALID_INTENTS:
            raise IdentityError("Propósito de reto no válido")
        challenge_id = new_opaque_token()
        browser_token = new_opaque_token()
        now = self._now()
        challenge = Challenge(
            id=challenge_id,
            code=new_challenge_code(),
            intent=intent,
            nonce=new_opaque_token(),
            created_at=now,
            expires_at=now + self._challenge_ttl,
            status="pending",
            browser_token_hash=sha256_hex(browser_token),
            approver_user_id=None,
            approver_device_id=None,
            selected_tenant_id=None,
            approved_at=None,
            redeemed_at=None,
        )
        self._store.save_challenge(challenge)
        return challenge, browser_token

    def get_challenge(self, challenge_id: str) -> Challenge:
        challenge = self._store.get_challenge(challenge_id)
        if challenge is None:
            raise NotFoundError("Reto no encontrado")
        return challenge

    def approve_challenge(
        self,
        *,
        user_id: str,
        device_id: str,
        challenge_id: str,
        signature_b64: str,
        code: str,
        tenant_id: str | None,
        token_issued_at: int | None,
    ) -> Challenge:
        challenge = self._store.get_challenge(challenge_id)
        if challenge is None:
            raise NotFoundError("Reto no encontrado")
        now = self._now()
        if now > challenge.expires_at:
            raise ConflictError("El reto expiró")
        if challenge.status != "pending":
            raise ConflictError("El reto ya no está pendiente")

        # A device without recent authentication cannot approve.
        if token_issued_at is None or (now - token_issued_at) > self._device_recent_auth_seconds:
            raise ForbiddenError("Vuelve a iniciar sesión para aprobar")

        if not hmac.compare_digest((code or "").encode("utf-8"), challenge.code.encode("utf-8")):
            raise ForbiddenError("El código no coincide")

        device = self._store.get_device(user_id, device_id)
        if device is None:
            raise ForbiddenError("Este dispositivo no está registrado")

        memberships = self.active_memberships(user_id)
        selected = tenant_id
        if challenge.intent == "browser_login":
            owners = [m for m in memberships if m.role == "owner"]
            if not owners:
                raise ForbiddenError("Solo el dueño puede abrir la consola")
            if selected is None:
                if len(owners) == 1:
                    selected = owners[0].tenant_id
                else:
                    raise ForbiddenError("Elige la tienda que quieres abrir")
            if not any(m.tenant_id == selected for m in owners):
                raise ForbiddenError("No tienes acceso a esa tienda")
        else:
            # device_link: the chosen store must be an active membership.
            if selected is not None and not any(
                m.tenant_id == selected for m in memberships
            ):
                raise ForbiddenError("No tienes acceso a esa tienda")

        payload = challenge_signature_payload(challenge, selected or "")
        if not verify_device_signature(device.public_key, payload, signature_b64):
            raise ForbiddenError("La firma del dispositivo no es válida")

        updated = self._store.transition_challenge(
            challenge_id,
            "pending",
            "approved",
            approver_user_id=user_id,
            approver_device_id=device_id,
            selected_tenant_id=selected,
            approved_at=now,
        )
        if updated is None:
            raise ConflictError("El reto ya fue aprobado")
        return updated

    def exchange_challenge(self, challenge_id: str, browser_token: str | None) -> SessionRecord:
        challenge = self._store.get_challenge(challenge_id)
        if challenge is None:
            raise NotFoundError("Reto no encontrado")
        now = self._now()
        if now > challenge.expires_at:
            raise ConflictError("El reto expiró")

        # Bind the redemption to the browser cookie that started the challenge.
        if not browser_token or not hmac.compare_digest(
            sha256_hex(browser_token).encode("utf-8"), challenge.browser_token_hash.encode("utf-8")
        ):
            raise ForbiddenError("Esta sesión no inició el reto")

        if challenge.status != "approved":
            raise ConflictError("El reto aún no ha sido aprobado")

        # One-time redemption: approve -> consumed is a compare-and-set.
        updated = self._store.transition_challenge(
            challenge_id, "approved", "consumed", redeemed_at=now
        )
        if updated is None:
            raise ConflictError("El reto ya fue usado")

        user_id = challenge.approver_user_id
        tenant_id = challenge.selected_tenant_id
        device_id = challenge.approver_device_id
        if not user_id or not tenant_id:
            raise ForbiddenError("El reto no seleccionó una tienda")
        if not device_id or self._store.get_device(user_id, device_id) is None:
            raise ForbiddenError("Este dispositivo ya no está vinculado")
        membership = self._store.get_membership(user_id, tenant_id)
        if membership is None or not membership.active:
            raise ForbiddenError("La membresía ya no está activa")
        if membership.role != "owner":
            raise ForbiddenError("Solo el dueño puede abrir la consola")

        return self._issue_session(user_id, tenant_id)

    # -- sessions ----------------------------------------------------------
    def _issue_session(self, user_id: str, tenant_id: str | None) -> SessionRecord:
        session = SessionRecord(
            token=new_opaque_token(),
            user_id=user_id,
            tenant_id=tenant_id,
            csrf_token=new_opaque_token(),
            created_at=self._now(),
            expires_at=self._now() + self._session_ttl,
            revoked_at=None,
        )
        self._store.save_session(session)
        return session

    def create_session(
        self, user_id: str, tenant_id: str, *, rotate_from: str | None = None
    ) -> SessionRecord:
        self.select_tenant(user_id, tenant_id)
        if rotate_from:
            self._store.revoke_session(rotate_from)
        return self._issue_session(user_id, tenant_id)

    def rotate_session(self, token: str) -> SessionRecord:
        session = self.verify_session(token)
        if session is None:
            raise UnauthorizedError("Sesión inválida o vencida")
        self._store.revoke_session(token)
        return self._issue_session(session.user_id, session.tenant_id)

    def verify_session(self, token: str | None) -> SessionRecord | None:
        if not token:
            return None
        session = self._store.get_session(token)
        if session is None or session.revoked_at is not None:
            return None
        if self._now() > session.expires_at:
            return None
        return session

    def end_session(self, token: str) -> None:
        self._store.revoke_session(token)

    # -- invites -----------------------------------------------------------
    def create_invite(
        self,
        *,
        actor_user_id: str,
        tenant_id: str,
        email: str | None,
        phone: str | None = None,
        role: str,
        can_sell: bool,
        can_fiado: bool,
        can_inventory: bool,
    ) -> tuple[str, Invite]:
        self._require_owner(actor_user_id, tenant_id)
        if role != "employee":
            # Issue invites only to employees; acceptance can never elevate.
            raise ForbiddenError("Las invitaciones solo crean empleados")
        token = new_invite_token()
        token_hash = hash_invite_token(token)
        now = self._now()
        invite = Invite(
            token_hash=token_hash,
            tenant_id=tenant_id,
            email=(email or "").strip() or None,
            phone=(phone or "").strip() or None,
            role="employee",
            can_sell=bool(can_sell),
            can_fiado=bool(can_fiado),
            can_inventory=bool(can_inventory),
            created_at=now,
            expires_at=now + self._invite_ttl,
            accepted_at=None,
            revoked_at=None,
            accepted_by=None,
        )
        self._store.save_invite(invite)
        return token, invite

    def get_invite(self, token: str) -> Invite:
        invite = self._store.get_invite(hash_invite_token(token))
        if invite is None or invite.revoked_at is not None:
            raise NotFoundError("Invitación no encontrada")
        if self._now() > invite.expires_at:
            raise NotFoundError("La invitación expiró")
        return invite

    def accept_invite(
        self,
        token: str,
        user_id: str,
        *,
        name: str | None = None,
        verified_phone: str | None = None,
    ) -> tuple[Membership, TenantRecord]:
        invite = self.get_invite(token)
        if invite.phone is not None and invite.phone != verified_phone:
            raise ForbiddenError("La invitación no corresponde a este número.")
        membership = self._store.accept_invite(
            invite.token_hash, user_id, invite.tenant_id, (name or "").strip() or None,
            invite.phone,
        )
        if membership is None:
            raise ConflictError("La invitación ya fue aceptada")
        tenant = self._store.get_tenant(invite.tenant_id)
        if tenant is None:
            raise NotFoundError("La tienda de la invitación no existe")
        return membership, tenant

    # -- tenant management -------------------------------------------------
    def list_tenant_members(self, actor_user_id: str, tenant_id: str) -> list[MemberRow]:
        self._require_owner(actor_user_id, tenant_id)
        return self._store.list_tenant_members(tenant_id)

    def patch_member(
        self,
        actor_user_id: str,
        tenant_id: str,
        member_user_id: str,
        *,
        role: str | None = None,
        can_sell: bool | None = None,
        can_fiado: bool | None = None,
        can_inventory: bool | None = None,
        active: bool | None = None,
    ) -> Membership:
        self._require_owner(actor_user_id, tenant_id)
        membership = self._store.get_membership(member_user_id, tenant_id)
        if membership is None:
            raise NotFoundError("Miembro no encontrado")
        if role is not None and role not in VALID_ROLES:
            raise IdentityError("Rol no válido")
        self._guard_last_owner(tenant_id, membership, new_role=role, new_active=active)
        updated = self._store.update_membership(
            member_user_id,
            tenant_id,
            role=role,
            can_sell=can_sell,
            can_fiado=can_fiado,
            can_inventory=can_inventory,
            active=active,
        )
        if updated is None:
            raise NotFoundError("Miembro no encontrado")
        return updated

    def deactivate_member(self, actor_user_id: str, tenant_id: str, member_user_id: str) -> Membership:
        return self.patch_member(actor_user_id, tenant_id, member_user_id, active=False)

    # -- payload helpers --------------------------------------------------
    def memberships_payload(self, user_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for membership in self.active_memberships(user_id):
            tenant = self._store.get_tenant(membership.tenant_id)
            store = self._store.get_store(membership.tenant_id)
            items.append(
                {
                    "tenantId": membership.tenant_id,
                    "tenantName": tenant.name if tenant else "",
                    "storeId": store.id if store else None,
                    "storeName": store.name if store else "",
                    "role": membership.role,
                    "canSell": membership.can_sell,
                    "canFiado": membership.can_fiado,
                    "canInventory": membership.can_inventory,
                    "active": membership.active,
                }
            )
        return items

    def invite_payload(self, invite: Invite) -> dict[str, Any]:
        tenant = self._store.get_tenant(invite.tenant_id)
        store = self._store.get_store(invite.tenant_id)
        return {
            "email": invite.email,
            "role": invite.role,
            "canSell": invite.can_sell,
            "canFiado": invite.can_fiado,
            "canInventory": invite.can_inventory,
            "tenantId": invite.tenant_id,
            "tenantName": tenant.name if tenant else "",
            "storeName": store.name if store else "",
            "expiresAt": invite.expires_at,
        }

    # -- tenant resolution -------------------------------------------------
    def tenant_payload(self, tenant_id: str) -> dict[str, Any]:
        tenant = self._store.get_tenant(tenant_id)
        if tenant is None:
            raise NotFoundError("Tienda no encontrada")
        store = self._store.get_store(tenant_id)
        return {
            "id": tenant.id,
            "slug": tenant.slug,
            "name": tenant.name,
            "legalName": tenant.legal_name,
            "rfc": tenant.rfc,
            "timezone": tenant.timezone,
            "status": tenant.status,
            "store": {"id": store.id, "name": store.name} if store else None,
        }
