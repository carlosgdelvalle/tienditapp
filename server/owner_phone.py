"""Abarpay-owned phone enrollment and device sign-in for merchant owners."""

from __future__ import annotations

import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
import phonenumbers
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from .identity import IdentityError, load_public_key, sha256_hex, verify_device_signature

TOKEN_PREFIX = "abarpay_owner_"
TOKEN_SECONDS = 300
Sender = Callable[[str, str], None]


def normalize_phone(phone: str) -> str:
    try:
        number = phonenumbers.parse(phone, "MX")
        if phonenumbers.is_valid_number_for_region(number, "MX") and not number.extension:
            return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    raise HTTPException(422, "Escribe un número celular de México de 10 dígitos.")


@dataclass(frozen=True)
class PhoneSettings:
    pepper: bytes
    send: Sender

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> PhoneSettings | None:
        raw = [env.get(name, "").strip() for name in (
            "ABARPAY_OWNER_CODE_KEY", "ABARPAY_OWNER_SMS_URL", "ABARPAY_OWNER_SMS_TOKEN",
        )]
        if not any(raw):
            return None
        pepper, url, token = raw
        target = urlsplit(url)
        if (len(pepper.encode()) < 32 or target.scheme != "https" or not target.hostname
                or target.username or target.password or target.query or target.fragment or not token):
            raise RuntimeError("owner phone sign-in requires a code key and an HTTPS SMS gateway")

        def send(phone: str, code: str) -> None:
            response = httpx.post(
                url,
                json={"to": phone, "message": f"Abarpay: tu código es {code}. No lo compartas."},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
                follow_redirects=False,
            )
            response.raise_for_status()

        return cls(pepper.encode(), send)


@dataclass(frozen=True)
class MobileIdentity:
    user_id: str
    device_id: str
    issued_at: int
    idp: str = "phone"


class PhoneAuth:
    def __init__(self, pool: ConnectionPool, settings: PhoneSettings):
        self.pool = pool
        self.settings = settings

    def _mac(self, challenge_id: UUID, code: str) -> str:
        return hmac.digest(self.settings.pepper, f"{challenge_id}:{code}".encode(), "sha256").hex()

    def start(self, device_id: UUID, phone: str | None = None, key: str | None = None) -> UUID:
        challenge_id = uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}" if phone else None
        with self.pool.connection() as conn, conn.cursor() as cur:
            # Across workers: both the global spend cap and per-number/device
            # quota must be checked under the same lock as inserting a request.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                        ("owner-sms-quota" if phone else "owner-device-quota",))
            cur.execute("DELETE FROM owner_auth.challenges WHERE created_at < now() - interval '1 hour'")
            if phone:
                cur.execute(
                    """SELECT count(*), count(*) FILTER (WHERE phone = %s),
                              count(*) FILTER (WHERE device_id = %s),
                              count(*) FILTER (WHERE phone = %s AND created_at > now() - interval '30 seconds')
                       FROM owner_auth.challenges WHERE phone IS NOT NULL""", (phone, device_id, phone),
                )
                total, number_count, device_count, recent = cur.fetchone()
                limited = total >= 120 or number_count >= 3 or device_count >= 6 or recent > 0
            else:
                cur.execute(
                    """SELECT count(*), count(*) FILTER (WHERE device_id = %s)
                       FROM owner_auth.challenges WHERE phone IS NULL
                         AND created_at > now() - interval '5 minutes'""", (device_id,),
                )
                total, device_count = cur.fetchone()
                limited = total >= 600 or device_count >= 12
            if limited:
                raise HTTPException(429, "Espera un momento antes de pedir otro código.")
            cur.execute(
                """INSERT INTO owner_auth.challenges (id, device_id, phone, public_key, code_mac, expires_at)
                   VALUES (%s, %s, %s, %s, %s, now() + (%s * interval '1 second'))""",
                (challenge_id, device_id, phone, key, self._mac(challenge_id, code) if code else None,
                 300 if phone else 60),
            )
        if code:
            try:
                self.settings.send(phone, code)
            except Exception:
                # Do not echo gateway diagnostics, numbers or OTPs.
                raise HTTPException(503, "No se pudo enviar el SMS. Intenta de nuevo en un momento.") from None
        return challenge_id

    def finish(self, challenge_id: UUID, signature: str, code: str | None = None) -> str:
        error = HTTPException(401, "El código o el acceso venció o no es válido. Intenta de nuevo.")
        token = None
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            if code is not None:
                cur.execute("SELECT phone FROM owner_auth.challenges WHERE id = %s", (challenge_id,))
                attempt = cur.fetchone()
                if not attempt or not attempt["phone"]:
                    raise error
                # Count failures across codes when the user requests another SMS.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s), hashtext('owner-enroll'))",
                            (attempt["phone"],))
                cur.execute(
                    """SELECT coalesce(sum(attempts - used::integer), 0) AS failures
                       FROM owner_auth.challenges WHERE phone = %s
                         AND created_at > now() - interval '10 minutes'""",
                    (attempt["phone"],),
                )
                if cur.fetchone()["failures"] >= 5:
                    raise HTTPException(429, "Hubo varios intentos. Vuelve a intentar en unos minutos.")
            cur.execute(
                """UPDATE owner_auth.challenges SET attempts = attempts + 1
                   WHERE id = %s AND NOT used AND expires_at > now() AND attempts < 5
                     AND (phone IS NOT NULL) = %s
                   RETURNING device_id, phone, public_key, code_mac""",
                (challenge_id, code is not None),
            )
            row = cur.fetchone()
            if row:
                device_id = row["device_id"]
                phone = row["phone"]
                if phone:
                    if hmac.compare_digest(row["code_mac"], self._mac(challenge_id, code)) and (
                        verify_device_signature(row["public_key"], f"abarpay-owner-enroll:{challenge_id}", signature)
                    ):
                        cur.execute("UPDATE owner_auth.challenges SET used = true WHERE id = %s", (challenge_id,))
                        token = self._enroll(cur, phone, device_id, row["public_key"])
                        if token is None:
                            error = HTTPException(409, "Esta cuenta está vinculada a otro celular. Usa el celular anterior o contacta a Abarpay.")
                else:
                    public_key = self._device_key(cur, device_id)
                    if public_key and verify_device_signature(public_key, f"abarpay-owner-signin:{challenge_id}", signature):
                        cur.execute("UPDATE owner_auth.challenges SET used = true WHERE id = %s", (challenge_id,))
                        token = self._issue(cur, device_id)
        if token is None:
            raise error
        return token

    def _enroll(self, cur, phone: str, device_id: UUID, key: str) -> str | None:
        # One first device for a verified number. An SMS on a different device
        # cannot replace a previously paired key even after a SIM swap.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s), hashtext('owner-device'))", (str(device_id),))
        cur.execute("SELECT device_id FROM owner_auth.credentials WHERE phone = %s", (phone,))
        assigned = cur.fetchone()
        if assigned is not None:
            if assigned["device_id"] == device_id and self._device_key(cur, device_id) == key:
                return self._issue(cur, device_id)
            return None
        cur.execute("SELECT 1 FROM owner_auth.credentials WHERE device_id = %s", (device_id,))
        if cur.fetchone() is not None:
            return None
        cur.execute("SELECT id FROM public.create_user('phone', %s, '', '')", (str(uuid4()),))
        user_id = cur.fetchone()["id"]
        cur.execute("SELECT public.save_device(%s, %s, %s, 'Abarpay', now(), now())",
                    (user_id, str(device_id), key))
        cur.execute("INSERT INTO owner_auth.credentials VALUES (%s, %s, %s)", (phone, user_id, device_id))
        return self._issue(cur, device_id)

    @staticmethod
    def _device_key(cur, device_id: UUID) -> str | None:
        cur.execute(
            """SELECT d.public_key FROM owner_auth.credentials c
               CROSS JOIN LATERAL public.get_device(c.user_id, c.device_id::text) d
               WHERE c.device_id = %s""", (device_id,),
        )
        row = cur.fetchone()
        return row["public_key"] if row else None

    @staticmethod
    def _issue(cur, device_id: UUID) -> str:
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        cur.execute("DELETE FROM owner_auth.mobile_sessions WHERE expires_at <= now()")
        cur.execute(
            """INSERT INTO owner_auth.mobile_sessions (token_hash, device_id, expires_at)
               VALUES (%s, %s, now() + (%s * interval '1 second'))""",
            (sha256_hex(token), device_id, TOKEN_SECONDS),
        )
        return token

    def identity(self, token: str) -> MobileIdentity | None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT c.user_id, c.device_id, floor(extract(epoch FROM s.issued_at))
                   FROM owner_auth.mobile_sessions s JOIN owner_auth.credentials c USING (device_id)
                   CROSS JOIN LATERAL public.get_device(c.user_id, c.device_id::text) d
                   WHERE s.token_hash = %s AND s.expires_at > now()""", (sha256_hex(token),),
            )
            row = cur.fetchone()
        return MobileIdentity(str(row[0]), str(row[1]), int(row[2])) if row else None

    def phone_for_user(self, user_id: str) -> str | None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT phone FROM owner_auth.credentials WHERE user_id = %s::uuid",
                (user_id,),
            )
            row = cur.fetchone()
        return row[0] if row else None


class DeviceStart(BaseModel):
    deviceId: UUID


class PhoneStart(DeviceStart):
    phone: str = Field(min_length=10, max_length=28)
    publicKey: str = Field(min_length=256, max_length=1000)
    inviteToken: str | None = Field(default=None, max_length=128)


class DeviceFinish(BaseModel):
    challengeId: UUID
    signature: str = Field(min_length=1, max_length=800)


class PhoneFinish(DeviceFinish):
    code: str = Field(pattern=r"^[0-9]{6}$")


class PrivateInputRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, "Revisa los datos e intenta de nuevo.") from None

        return handle


router = APIRouter(prefix="/api/auth/owner", route_class=PrivateInputRoute)


def _require_invite_matches_phone(
    request: Request, token: str, normalized_phone: str
) -> None:
    """Reject enrollment when the invite is not active for this exact phone.

    The message stays generic so it never reveals the intended number.
    """

    service = getattr(request.app.state, "identity_service", None)
    try:
        invite = service.get_invite(token) if service is not None else None
    except IdentityError:
        invite = None
    if invite is None or invite.accepted_at is not None or invite.phone != normalized_phone:
        raise HTTPException(403, "La invitación no es válida o no corresponde a este número.")


@router.post("/phone/start")
def start_phone(body: PhoneStart, request: Request):
    key = load_public_key(body.publicKey)
    if not isinstance(key, RSAPublicKey) or key.key_size not in (2048, 3072, 4096):
        raise HTTPException(422, "No se pudo verificar este celular.")
    if not re.fullmatch(r"[+0-9() .-]+", body.phone):
        raise HTTPException(422, "Escribe un número celular de México de 10 dígitos.")
    normalized = normalize_phone(body.phone)
    if body.inviteToken:
        _require_invite_matches_phone(request, body.inviteToken, normalized)
    pem = key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    challenge = request.app.state.owner_phone.start(body.deviceId, normalized, pem.decode())
    return {"challengeId": challenge, "retryAfterSeconds": 30}


@router.post("/device/start")
def start_device(body: DeviceStart, request: Request):
    return {"challengeId": request.app.state.owner_phone.start(body.deviceId)}


@router.post("/phone/verify")
def finish_phone(body: PhoneFinish, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    token = request.app.state.owner_phone.finish(body.challengeId, body.signature, body.code)
    return {"accessToken": token, "expiresIn": TOKEN_SECONDS}


@router.post("/device/verify")
def finish_device(body: DeviceFinish, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    token = request.app.state.owner_phone.finish(body.challengeId, body.signature)
    return {"accessToken": token, "expiresIn": TOKEN_SECONDS}


def register_phone(app: FastAPI, service: PhoneAuth) -> None:
    app.state.owner_phone = service
    app.include_router(router)
