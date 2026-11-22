"""First-party staff authentication for the Abarpay platform console.

The SaaS team signs in with email and password. Passwords are hashed with
scrypt from the standard library, sessions are opaque random tokens stored as
SHA-256 hashes, and the browser cookie is HttpOnly and SameSite=Lax.

Storage lives in the same SQLite database as the application (`platform_*`
tables), so the console works on the current Render service without an external
identity provider. The tables are portable to PostgreSQL when the merchant
runtime moves there.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .db import connect, write_transaction

logger = logging.getLogger("abarpay.platform_auth")

COOKIE_NAME = "abarpay_platform"
SESSION_TTL_SECONDS = 12 * 60 * 60
INVITE_TTL_SECONDS = 7 * 24 * 60 * 60

ROLES = ("owner", "admin", "operations", "marketing", "finance", "analyst")
SUPER_ROLES = frozenset({"owner", "admin"})
ROLE_LABELS = {
    "owner": "Propietario",
    "admin": "Administrador",
    "operations": "Operaciones y soporte",
    "marketing": "Crecimiento y marketing",
    "finance": "Ingresos y finanzas",
    "analyst": "Datos y analista",
}

MIN_PASSWORD_LENGTH = 10
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS platform_staff (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS platform_invites (
    token_hash TEXT PRIMARY KEY,
    staff_id TEXT NOT NULL REFERENCES platform_staff(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS platform_sessions (
    token_hash TEXT PRIMARY KEY,
    staff_id TEXT NOT NULL REFERENCES platform_staff(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS platform_sessions_staff
    ON platform_sessions(staff_id);
CREATE INDEX IF NOT EXISTS platform_invites_staff
    ON platform_invites(staff_id);
"""


class PlatformAuthError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Staff:
    id: str
    email: str
    name: str
    role: str
    active: bool
    must_change_password: bool

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "roleLabel": ROLE_LABELS.get(self.role, self.role),
            "active": self.active,
            "mustChangePassword": self.must_change_password,
        }


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    return "scrypt$16384$8$1$" + _b64encode(salt) + "$" + _b64encode(digest)


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        calculated = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(calculated, _b64decode(digest))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def normalize_email(email: str) -> str:
    return email.strip().lower()


class PlatformAuth:
    """Persisted staff accounts, sessions and one-time invitations."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._schema_ready = False
        self._failures: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    # -- schema ---------------------------------------------------------
    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        conn = connect(self.db_path)
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()
        self._schema_ready = True

    def bootstrap(self, env: Mapping[str, str]) -> None:
        """Create the first owner account from the environment, once."""

        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            existing = conn.execute("SELECT COUNT(*) FROM platform_staff").fetchone()[0]
        finally:
            conn.close()
        if existing:
            return

        email = normalize_email(env.get("ABARPAY_PLATFORM_ADMIN_EMAIL", ""))
        password = env.get("ABARPAY_PLATFORM_ADMIN_PASSWORD", "")
        name = env.get("ABARPAY_PLATFORM_ADMIN_NAME", "").strip() or "Equipo Abarpay"
        if not email or len(password) < MIN_PASSWORD_LENGTH:
            logger.info(
                "platform console has no staff accounts yet; set "
                "ABARPAY_PLATFORM_ADMIN_EMAIL and ABARPAY_PLATFORM_ADMIN_PASSWORD"
            )
            return

        staff_id = secrets.token_hex(16)
        conn = connect(self.db_path)
        try:
            with write_transaction(conn):
                conn.execute(
                    "INSERT INTO platform_staff "
                    "(id, email, name, role, password_hash, active, "
                    " must_change_password, created_at) "
                    "VALUES (?, ?, ?, 'owner', ?, 1, 1, ?)",
                    (staff_id, email, name, hash_password(password), _iso(_now())),
                )
        finally:
            conn.close()
        logger.info("platform owner account created for %s", email)

    # -- reads ----------------------------------------------------------
    def _row_to_staff(self, row: sqlite3.Row) -> Staff:
        return Staff(
            id=row["id"],
            email=row["email"],
            name=row["name"],
            role=row["role"],
            active=bool(row["active"]),
            must_change_password=bool(row["must_change_password"]),
        )

    def count_staff(self) -> int:
        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM platform_staff").fetchone()[0])
        finally:
            conn.close()

    def get_staff(self, staff_id: str) -> Staff | None:
        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM platform_staff WHERE id = ?", (staff_id,)
            ).fetchone()
            return self._row_to_staff(row) if row else None
        finally:
            conn.close()

    def create_owner(self, *, email: str, name: str, password: str) -> Staff:
        """Create the very first owner account from the setup screen."""

        normalized = normalize_email(email)
        display_name = name.strip() or "Propietario"
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise PlatformAuthError("Escribe un correo válido.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PlatformAuthError(
                "La contraseña debe tener al menos "
                f"{MIN_PASSWORD_LENGTH} caracteres."
            )
        self.ensure_schema()
        staff_id = secrets.token_hex(16)
        conn = connect(self.db_path)
        try:
            with write_transaction(conn):
                existing = conn.execute(
                    "SELECT COUNT(*) FROM platform_staff"
                ).fetchone()[0]
                if existing:
                    raise PlatformAuthError(
                        "La cuenta inicial ya existe. Inicia sesión.", status_code=409
                    )
                conn.execute(
                    "INSERT INTO platform_staff "
                    "(id, email, name, role, password_hash, active, "
                    " must_change_password, created_at) "
                    "VALUES (?, ?, ?, 'owner', ?, 1, 0, ?)",
                    (staff_id, normalized, display_name, hash_password(password), _iso(_now())),
                )
        finally:
            conn.close()
        created = self.get_staff(staff_id)
        assert created is not None
        return created

    def list_staff(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM platform_staff ORDER BY created_at"
            ).fetchall()
            pending = {
                row["staff_id"]
                for row in conn.execute(
                    "SELECT staff_id FROM platform_invites "
                    "WHERE used_at IS NULL AND expires_at > ?",
                    (_iso(_now()),),
                ).fetchall()
            }
        finally:
            conn.close()
        items = []
        for row in rows:
            staff = self._row_to_staff(row)
            item = staff.payload()
            item["createdAt"] = row["created_at"]
            item["lastLoginAt"] = row["last_login_at"]
            item["pendingInvite"] = staff.id in pending
            items.append(item)
        return items

    # -- login ----------------------------------------------------------
    def _throttle(self, key: tuple[str, str]) -> None:
        cutoff = time.monotonic() - FAILURE_WINDOW_SECONDS
        with self._lock:
            recent = [t for t in self._failures.get(key, []) if t > cutoff]
            if len(recent) >= MAX_FAILURES:
                raise PlatformAuthError(
                    "Demasiados intentos. Espera unos minutos antes de volver a intentar.",
                    status_code=429,
                )
            self._failures[key] = recent

    def _record_failure(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(time.monotonic())

    def authenticate(
        self, email: str, password: str, *, client_ip: str = ""
    ) -> Staff | None:
        self.ensure_schema()
        normalized = normalize_email(email)
        key = (normalized, client_ip)
        self._throttle(key)
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM platform_staff WHERE email = ? COLLATE NOCASE",
                (normalized,),
            ).fetchone()
            if row is None or not row["active"] or not verify_password(
                password, row["password_hash"]
            ):
                self._record_failure(key)
                return None
            with write_transaction(conn):
                conn.execute(
                    "UPDATE platform_staff SET last_login_at = ? WHERE id = ?",
                    (_iso(_now()), row["id"]),
                )
            with self._lock:
                self._failures.pop(key, None)
            return self._row_to_staff(row)
        finally:
            conn.close()

    # -- sessions -------------------------------------------------------
    def create_session(self, staff_id: str) -> str:
        self.ensure_schema()
        token = secrets.token_urlsafe(32)
        now = _now()
        conn = connect(self.db_path)
        try:
            with write_transaction(conn):
                conn.execute(
                    "INSERT INTO platform_sessions "
                    "(token_hash, staff_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (
                        _hash_token(token),
                        staff_id,
                        _iso(now),
                        _iso(now + timedelta(seconds=SESSION_TTL_SECONDS)),
                    ),
                )
        finally:
            conn.close()
        return token

    def session_staff(self, token: str | None) -> Staff | None:
        if not token:
            return None
        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT s.*, u.active AS staff_active, u.id AS staff_id "
                "FROM platform_sessions s JOIN platform_staff u ON u.id = s.staff_id "
                "WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ?",
                (_hash_token(token), _iso(_now())),
            ).fetchone()
            if row is None or not row["staff_active"]:
                return None
            staff_row = conn.execute(
                "SELECT * FROM platform_staff WHERE id = ?", (row["staff_id"],)
            ).fetchone()
            return self._row_to_staff(staff_row) if staff_row else None
        finally:
            conn.close()

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            with write_transaction(conn):
                conn.execute(
                    "UPDATE platform_sessions SET revoked_at = ? "
                    "WHERE token_hash = ? AND revoked_at IS NULL",
                    (_iso(_now()), _hash_token(token)),
                )
        finally:
            conn.close()

    def revoke_all_sessions(self, staff_id: str, *, keep: str | None = None) -> None:
        self.ensure_schema()
        keep_hash = _hash_token(keep) if keep else ""
        conn = connect(self.db_path)
        try:
            with write_transaction(conn):
                conn.execute(
                    "UPDATE platform_sessions SET revoked_at = ? "
                    "WHERE staff_id = ? AND revoked_at IS NULL AND token_hash <> ?",
                    (_iso(_now()), staff_id, keep_hash),
                )
        finally:
            conn.close()

    # -- password -------------------------------------------------------
    def change_password(
        self, staff_id: str, current: str, new: str, *, keep_token: str | None = None
    ) -> None:
        if len(new) < MIN_PASSWORD_LENGTH:
            raise PlatformAuthError(
                "La contraseña nueva debe tener al menos "
                f"{MIN_PASSWORD_LENGTH} caracteres."
            )
        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT password_hash FROM platform_staff WHERE id = ?", (staff_id,)
            ).fetchone()
            if row is None or not verify_password(current, row["password_hash"]):
                raise PlatformAuthError("La contraseña actual no coincide.", status_code=403)
            with write_transaction(conn):
                conn.execute(
                    "UPDATE platform_staff SET password_hash = ?, "
                    "must_change_password = 0 WHERE id = ?",
                    (hash_password(new), staff_id),
                )
        finally:
            conn.close()
        self.revoke_all_sessions(staff_id, keep=keep_token)

    # -- team -----------------------------------------------------------
    def invite(
        self, *, email: str, name: str, role: str, actor: Staff
    ) -> tuple[str, datetime]:
        normalized = normalize_email(email)
        name = name.strip()
        role = role.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise PlatformAuthError("Escribe un correo válido.")
        if not name:
            raise PlatformAuthError("Escribe el nombre de la persona.")
        if role not in ROLES:
            raise PlatformAuthError("Rol no válido.")
        if role in {"owner", "admin"} and actor.role != "owner":
            raise PlatformAuthError(
                "Solo el propietario puede invitar administradores.", status_code=403
            )

        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            existing = conn.execute(
                "SELECT * FROM platform_staff WHERE email = ? COLLATE NOCASE",
                (normalized,),
            ).fetchone()
            if existing and existing["active"]:
                raise PlatformAuthError(
                    "Ese correo ya tiene acceso activo.", status_code=409
                )
            token = secrets.token_urlsafe(32)
            expires = _now() + timedelta(seconds=INVITE_TTL_SECONDS)
            with write_transaction(conn):
                if existing:
                    staff_id = existing["id"]
                    conn.execute(
                        "UPDATE platform_staff SET name = ?, role = ?, active = 0, "
                        "password_hash = NULL, must_change_password = 1 WHERE id = ?",
                        (name, role, staff_id),
                    )
                else:
                    staff_id = secrets.token_hex(16)
                    conn.execute(
                        "INSERT INTO platform_staff "
                        "(id, email, name, role, active, must_change_password, created_at) "
                        "VALUES (?, ?, ?, ?, 0, 1, ?)",
                        (staff_id, normalized, name, role, _iso(_now())),
                    )
                conn.execute(
                    "UPDATE platform_invites SET used_at = ? "
                    "WHERE staff_id = ? AND used_at IS NULL",
                    (_iso(_now()), staff_id),
                )
                conn.execute(
                    "INSERT INTO platform_invites (token_hash, staff_id, expires_at) "
                    "VALUES (?, ?, ?)",
                    (_hash_token(token), staff_id, _iso(expires)),
                )
        finally:
            conn.close()
        return token, expires

    def invite_preview(self, token: str) -> dict[str, Any]:
        self.ensure_schema()
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT i.*, u.email, u.name, u.role FROM platform_invites i "
                "JOIN platform_staff u ON u.id = i.staff_id "
                "WHERE i.token_hash = ? AND i.used_at IS NULL AND i.expires_at > ?",
                (_hash_token(token), _iso(_now())),
            ).fetchone()
            if row is None:
                raise PlatformAuthError(
                    "La invitación venció o ya se usó. Pide una nueva.", status_code=410
                )
            return {
                "email": row["email"],
                "name": row["name"],
                "role": row["role"],
                "roleLabel": ROLE_LABELS.get(row["role"], row["role"]),
            }
        finally:
            conn.close()

    def accept_invite(self, token: str, *, name: str, password: str) -> Staff:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PlatformAuthError(
                "La contraseña debe tener al menos "
                f"{MIN_PASSWORD_LENGTH} caracteres."
            )
        preview = self.invite_preview(token)
        display_name = name.strip() or preview["name"]
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT staff_id FROM platform_invites WHERE token_hash = ?",
                (_hash_token(token),),
            ).fetchone()
            if row is None:
                raise PlatformAuthError("La invitación ya no es válida.", status_code=410)
            staff_id = row["staff_id"]
            with write_transaction(conn):
                conn.execute(
                    "UPDATE platform_staff SET password_hash = ?, name = ?, "
                    "active = 1, must_change_password = 0 WHERE id = ?",
                    (hash_password(password), display_name, staff_id),
                )
                conn.execute(
                    "UPDATE platform_invites SET used_at = ? WHERE token_hash = ?",
                    (_iso(_now()), _hash_token(token)),
                )
            staff_row = conn.execute(
                "SELECT * FROM platform_staff WHERE id = ?", (staff_id,)
            ).fetchone()
        finally:
            conn.close()
        return self._row_to_staff(staff_row)

    def patch_staff(
        self,
        staff_id: str,
        *,
        actor: Staff,
        role: str | None = None,
        active: bool | None = None,
    ) -> Staff:
        self.ensure_schema()
        target = self.get_staff(staff_id)
        if target is None:
            raise PlatformAuthError("No encontramos a esa persona.", status_code=404)
        if target.id == actor.id and active is False:
            raise PlatformAuthError("No puedes quitarte el acceso a ti mismo.")
        if target.role == "owner" and actor.role != "owner":
            raise PlatformAuthError(
                "Solo el propietario puede modificar a otro propietario.",
                status_code=403,
            )
        if role is not None:
            role = role.strip().lower()
            if role not in ROLES:
                raise PlatformAuthError("Rol no válido.")
            if role in {"owner", "admin"} and actor.role != "owner":
                raise PlatformAuthError(
                    "Solo el propietario puede asignar administradores.", status_code=403
                )

        conn = connect(self.db_path)
        try:
            with write_transaction(conn):
                if role is not None:
                    conn.execute(
                        "UPDATE platform_staff SET role = ? WHERE id = ?",
                        (role, staff_id),
                    )
                if active is not None:
                    conn.execute(
                        "UPDATE platform_staff SET active = ? WHERE id = ?",
                        (1 if active else 0, staff_id),
                    )
                owners = conn.execute(
                    "SELECT COUNT(*) FROM platform_staff WHERE role = 'owner' AND active = 1"
                ).fetchone()[0]
                if not owners:
                    raise PlatformAuthError("Debe quedar al menos un propietario activo.")
        finally:
            conn.close()

        if active is False:
            self.revoke_all_sessions(staff_id)
        updated = self.get_staff(staff_id)
        assert updated is not None
        return updated

