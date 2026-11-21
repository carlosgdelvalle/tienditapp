"""Transactional email: sender, outbox queue, and bounce handling for Abarpay.

SIMULADO: this module ships no real SMTP credentials and no durable store. The
SMTP transport is real code (SMTP2GO over mandatory STARTTLS) but only delivers
when the operator injects SMTP_USERNAME / SMTP_PASSWORD into the environment;
the reference queue is in-memory and the whole path is labeled SIMULADO until a
transactional outbox with a durable store replaces it.

Owns the delivery path for the three transactional emails the identity layer
needs:

- invitation   -> an access link /invite/{token} (expires; token shown once),
- verification -> a one-time code (OTP),
- recovery     -> an access link /recovery/{token} (expires).

Hard rules enforced here:

- STARTTLS is mandatory and there is NO plaintext fallback (mail.smtp2go.com:2525).
- OTPs and access links live ONLY in OutboxEmail.template_vars and the rendered
  MIME body. They are never logged, never part of repr, never placed in
  last_error, and never exposed through safe_summary() / telemetry.
- Every email is a transactional outbox row keyed by a stable unique id derived
  from (kind, event_id), so re-enqueueing the same event is idempotent.
- States recorded: queued, accepted (provider accepted), bounced, expired, and
  retryable-failure (plus a permanent failed). SMTP acceptance does not prove
  inbox delivery.

Environment variables consumed here (read directly, never from config.py):

- SMTP_HOST            default "mail.smtp2go.com"
- SMTP_PORT            default 2525
- SMTP_USERNAME        SMTP identity (SMTP2GO API key username)
- SMTP_PASSWORD        SMTP identity (SMTP2GO API key secret)
- SMTP_FROM            envelope From mailbox, default "mailer@abarpay.app"
- SMTP_FROM_NAME       display name, default "Abarpay" (separate from the identity)
- SMTP_TIMEOUT_SECONDS default 15
- EMAIL_BASE_URL       base for access links, default "https://abarpay.app"
"""

from __future__ import annotations

import hashlib
import logging
import os
import smtplib
import socket
import ssl
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger("abarpay.email")

# ---------------------------------------------------------------------------
# Email kinds (event -> template) and queue states
# ---------------------------------------------------------------------------

KIND_INVITATION = "invitation"
KIND_VERIFICATION = "verification"
KIND_RECOVERY = "recovery"

VALID_KINDS = {KIND_INVITATION, KIND_VERIFICATION, KIND_RECOVERY}

STATE_QUEUED = "queued"
STATE_ACCEPTED = "accepted"
STATE_BOUNCED = "bounced"
STATE_EXPIRED = "expired"
STATE_RETRYABLE_FAILURE = "retryable_failure"
STATE_FAILED = "failed"

# Default time-to-live per kind when the caller does not pass an expiry.
DEFAULT_TTL_SECONDS = {
    KIND_INVITATION: 7 * 24 * 60 * 60,
    KIND_VERIFICATION: 600,
    KIND_RECOVERY: 60 * 60,
}

SMTP_DEFAULT_HOST = "mail.smtp2go.com"
SMTP_DEFAULT_PORT = 2525
SMTP_DEFAULT_FROM = "mailer@abarpay.app"
SMTP_DEFAULT_FROM_NAME = "Abarpay"
DEFAULT_BASE_URL = "https://abarpay.app"

SUBJECTS = {
    KIND_INVITATION: "Invitación a tu tienda en Abarpay",
    KIND_VERIFICATION: "Tu código de verificación de Abarpay",
    KIND_RECOVERY: "Recupera el acceso a tu tienda en Abarpay",
}

BODY_TEMPLATES = {
    KIND_INVITATION: (
        "Hola,\n\n"
        "{store_name} te invita a unirte a su equipo en Abarpay.\n\n"
        "Para aceptar la invitación, abre este enlace:\n{link}\n\n"
        "Este enlace es personal y expira el {expires}."
    ),
    KIND_VERIFICATION: (
        "Hola,\n\n"
        "Tu código de verificación de Abarpay es:\n\n{otp}\n\n"
        "Este código expira en {minutes} minutos. Si no lo solicitaste, "
        "ignora este correo."
    ),
    KIND_RECOVERY: (
        "Hola,\n\n"
        "Recibimos una solicitud para recuperar el acceso a tu tienda.\n\n"
        "Abre este enlace para continuar:\n{link}\n\n"
        "Este enlace es de un solo uso y expira el {expires}. Si no lo "
        "solicitaste, ignora este correo."
    ),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EmailError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class SmtpDeliveryError(Exception):
    """A failed delivery attempt, classified by whether it is retryable.

    code is a short, human-safe token (never the recipient, OTP, or link) so it
    can be stored in last_error and logged without redaction risk.
    """

    def __init__(self, code: str, *, permanent: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.permanent = permanent


# ---------------------------------------------------------------------------
# Settings (read from the environment; config.py is intentionally untouched)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EmailSettings:
    host: str = SMTP_DEFAULT_HOST
    port: int = SMTP_DEFAULT_PORT
    username: str = ""
    password: str = field(default="", repr=False)
    sender: str = SMTP_DEFAULT_FROM
    sender_name: str = SMTP_DEFAULT_FROM_NAME
    timeout_seconds: float = 15.0
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(cls) -> "EmailSettings":
        def _env(name: str, default: str) -> str:
            raw = os.getenv(name)
            return raw.strip() if raw is not None and raw.strip() else default

        def _env_int(name: str, default: int) -> int:
            raw = os.getenv(name)
            try:
                return int(raw) if raw is not None and raw.strip() else default
            except (TypeError, ValueError):
                return default

        def _env_float(name: str, default: float) -> float:
            raw = os.getenv(name)
            try:
                value = float(raw) if raw is not None and raw.strip() else default
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default

        return cls(
            host=_env("SMTP_HOST", SMTP_DEFAULT_HOST),
            port=_env_int("SMTP_PORT", SMTP_DEFAULT_PORT),
            username=_env("SMTP_USERNAME", ""),
            password=os.getenv("SMTP_PASSWORD", "") or "",
            sender=_env("SMTP_FROM", SMTP_DEFAULT_FROM),
            sender_name=_env("SMTP_FROM_NAME", SMTP_DEFAULT_FROM_NAME),
            timeout_seconds=_env_float("SMTP_TIMEOUT_SECONDS", 15.0),
            base_url=_env("EMAIL_BASE_URL", DEFAULT_BASE_URL),
        )

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password)


# ---------------------------------------------------------------------------
# Redaction helpers (OTPs and access links must never reach logs/telemetry)
# ---------------------------------------------------------------------------


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every non-empty secret inside text with [REDACTED]."""

    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result


def mask_email(address: str) -> str:
    """Mask the local part of an address for logs; never the full mailbox."""

    if not address or "@" not in address:
        return "***"
    local, _, domain = address.partition("@")
    if len(local) <= 1:
        masked = "*"
    else:
        masked = local[:1] + "*" * (len(local) - 1)
    return f"{masked}@{domain}"


def safe_summary(email: "OutboxEmail") -> dict[str, Any]:
    """Telemetry-safe view of one outbox email (no OTP, link, or mailbox)."""

    return {
        "id": email.id,
        "kind": email.kind,
        "eventId": email.event_id,
        "recipient": mask_email(email.recipient),
        "state": email.state,
        "attempts": email.attempts,
    }


# ---------------------------------------------------------------------------
# Domain records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutboxEmail:
    id: str  # stable unique id derived from (kind, event_id)
    kind: str  # invitation | verification | recovery
    recipient: str
    event_id: str  # non-secret correlation (invite token hash, user id, ...)
    created_at: float
    expires_at: Optional[float]
    template_vars: dict[str, str] = field(repr=False, compare=False, default_factory=dict)
    attempts: int = 0
    state: str = STATE_QUEUED
    last_error: Optional[str] = field(repr=False, default=None)
    sent_at: Optional[float] = None

    def __repr__(self) -> str:
        # Never leak the mailbox, OTP, or access link through repr/logs.
        return (
            f"OutboxEmail(id={self.id!r}, kind={self.kind!r}, "
            f"recipient={mask_email(self.recipient)!r}, event_id={self.event_id!r}, "
            f"created_at={self.created_at!r}, expires_at={self.expires_at!r}, "
            f"attempts={self.attempts!r}, state={self.state!r}, "
            f"sent_at={self.sent_at!r})"
        )


@dataclass(frozen=True)
class Bounce:
    recipient: str
    reason: str
    message_id: Optional[str]
    bounced_at: float
    permanent: bool


@dataclass(frozen=True)
class DrainResult:
    sent: int = 0
    expired: int = 0
    failed: int = 0
    suppressed: int = 0


# ---------------------------------------------------------------------------
# Stable id and template rendering
# ---------------------------------------------------------------------------


def make_email_id(kind: str, event_id: str) -> str:
    """Stable, deterministic unique id so re-enqueueing the same event is a
    no-op (idempotent outbox)."""

    return hashlib.sha256(f"{kind}:{event_id}".encode("utf-8")).hexdigest()


def _expires_label(expires_at: Optional[float]) -> str:
    if expires_at is None:
        return ""
    dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    return dt.strftime("%d/%m/%Y %H:%M (UTC)")


def render_body(email: OutboxEmail) -> str:
    template = BODY_TEMPLATES.get(email.kind, "")
    if not template:
        return ""
    return template.format(**email.template_vars)


def render_message(email: OutboxEmail, *, sender: str, sender_name: str) -> EmailMessage:
    """Build the MIME message. The OTP/link appear here and are sent over TLS;
    this message object is never logged."""

    domain = sender.rsplit("@", 1)[-1] if "@" in sender else "abarpay.app"
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender))
    msg["To"] = email.recipient
    msg["Subject"] = SUBJECTS.get(email.kind, "Abarpay")
    msg["Message-ID"] = f"<{email.id}@{domain}>"
    msg["X-Abarpay-Kind"] = email.kind
    msg["X-Abarpay-Event-Id"] = email.event_id
    msg.set_content(render_body(email), subtype="plain", charset="utf-8")
    return msg


# ---------------------------------------------------------------------------
# Queue protocol + in-memory reference (SIMULADO)
# ---------------------------------------------------------------------------


class EmailQueue(ABC):
    """Transactional outbox for emails. The in-memory implementation is the
    SIMULADO reference; a durable (PostgreSQL) adapter must implement the same
    protocol."""

    @abstractmethod
    def enqueue(self, email: OutboxEmail) -> OutboxEmail: ...

    @abstractmethod
    def get(self, email_id: str) -> Optional[OutboxEmail]: ...

    @abstractmethod
    def pending(self) -> list[OutboxEmail]: ...

    @abstractmethod
    def mark_sent(self, email_id: str, *, sent_at: float) -> Optional[OutboxEmail]: ...

    @abstractmethod
    def mark_failed(
        self, email_id: str, *, error: str, permanent: bool
    ) -> Optional[OutboxEmail]: ...

    @abstractmethod
    def mark_bounced(self, email_id: str, *, reason: str) -> Optional[OutboxEmail]: ...

    @abstractmethod
    def mark_expired(self, email_id: str) -> Optional[OutboxEmail]: ...

    @abstractmethod
    def requeue(self, email_id: str) -> Optional[OutboxEmail]: ...

    @abstractmethod
    def record_bounce(self, bounce: Bounce) -> None: ...

    @abstractmethod
    def is_suppressed(self, recipient: str) -> bool: ...


class MemoryEmailQueue(EmailQueue):
    """SIMULADO in-memory outbox. Never touches the network."""

    simulated = True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._emails: dict[str, OutboxEmail] = {}
        self.bounces: list[Bounce] = []
        self._suppressed: set[str] = set()

    def enqueue(self, email: OutboxEmail) -> OutboxEmail:
        with self._lock:
            existing = self._emails.get(email.id)
            if existing is not None:
                return existing
            self._emails[email.id] = email
            return email

    def get(self, email_id: str) -> Optional[OutboxEmail]:
        with self._lock:
            return self._emails.get(email_id)

    def pending(self) -> list[OutboxEmail]:
        with self._lock:
            queued = [e for e in self._emails.values() if e.state == STATE_QUEUED]
            return sorted(queued, key=lambda e: e.created_at)

    def mark_sent(self, email_id: str, *, sent_at: float) -> Optional[OutboxEmail]:
        with self._lock:
            email = self._emails.get(email_id)
            if email is None:
                return None
            updated = replace(
                email,
                state=STATE_ACCEPTED,
                sent_at=sent_at,
                attempts=email.attempts + 1,
                last_error=None,
            )
            self._emails[email_id] = updated
            return updated

    def mark_failed(
        self, email_id: str, *, error: str, permanent: bool
    ) -> Optional[OutboxEmail]:
        with self._lock:
            email = self._emails.get(email_id)
            if email is None:
                return None
            updated = replace(
                email,
                state=(STATE_FAILED if permanent else STATE_RETRYABLE_FAILURE),
                attempts=email.attempts + 1,
                last_error=error,
            )
            self._emails[email_id] = updated
            return updated

    def mark_bounced(self, email_id: str, *, reason: str) -> Optional[OutboxEmail]:
        with self._lock:
            email = self._emails.get(email_id)
            if email is None:
                return None
            updated = replace(email, state=STATE_BOUNCED, last_error=reason)
            self._emails[email_id] = updated
            return updated

    def mark_expired(self, email_id: str) -> Optional[OutboxEmail]:
        with self._lock:
            email = self._emails.get(email_id)
            if email is None:
                return None
            updated = replace(email, state=STATE_EXPIRED)
            self._emails[email_id] = updated
            return updated

    def requeue(self, email_id: str) -> Optional[OutboxEmail]:
        with self._lock:
            email = self._emails.get(email_id)
            if email is None or email.state != STATE_RETRYABLE_FAILURE:
                return None
            updated = replace(email, state=STATE_QUEUED)
            self._emails[email_id] = updated
            return updated

    def record_bounce(self, bounce: Bounce) -> None:
        with self._lock:
            self.bounces.append(bounce)
            if bounce.permanent:
                self._suppressed.add(bounce.recipient.lower())

    def is_suppressed(self, recipient: str) -> bool:
        with self._lock:
            return (recipient or "").lower() in self._suppressed


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------


class SmtpSender(ABC):
    simulated: bool = False

    @abstractmethod
    def send(self, email: OutboxEmail) -> None: ...


def _classify(exc: Exception) -> tuple[str, bool]:
    """Map a transport exception to a safe code + retryability. The code never
    carries the recipient or message body."""

    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth_failed", True
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "recipient_refused", True
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "sender_refused", True
    if isinstance(exc, smtplib.SMTPDataError):
        return "data_rejected", False
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "starttls_not_supported", False
    if isinstance(exc, (socket.timeout, TimeoutError, ConnectionError, OSError, ssl.SSLError)):
        return "transport_error", False
    if isinstance(exc, smtplib.SMTPException):
        return "smtp_error", False
    return "unknown_error", False


class Smtp2GoSender(SmtpSender):
    """SMTP2GO delivery over mandatory STARTTLS (no plaintext fallback).

    ssl_context is injectable for tests that point at a loopback capture
    server; in production it stays None so smtplib uses the strict default
    context (certificate + hostname validation against the configured host).
    """

    def __init__(
        self,
        settings: EmailSettings,
        *,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> None:
        self._settings = settings
        self._ssl_context = ssl_context

    @property
    def configured(self) -> bool:
        return self._settings.configured

    def send(self, email: OutboxEmail) -> None:
        settings = self._settings
        if not settings.configured:
            raise SmtpDeliveryError("smtp_not_configured", permanent=False)

        message = render_message(
            email, sender=settings.sender, sender_name=settings.sender_name
        )
        smtp: Optional[smtplib.SMTP] = None
        try:
            smtp = smtplib.SMTP(
                settings.host, settings.port, timeout=settings.timeout_seconds
            )
            smtp.ehlo()
            try:
                smtp.starttls(context=self._ssl_context)
            except smtplib.SMTPNotSupportedError as exc:
                raise SmtpDeliveryError(
                    "starttls_not_supported", permanent=False
                ) from exc
            except smtplib.SMTPException as exc:
                raise SmtpDeliveryError("starttls_failed", permanent=False) from exc
            # Re-issue EHLO inside the TLS session and authenticate.
            smtp.ehlo()
            smtp.login(settings.username, settings.password)
            smtp.send_message(message)
        except SmtpDeliveryError:
            raise
        except Exception as exc:  # noqa: BLE001 - classified and re-raised safely
            code, permanent = _classify(exc)
            raise SmtpDeliveryError(code, permanent=permanent) from exc
        finally:
            if smtp is not None:
                try:
                    smtp.close()
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass


# ---------------------------------------------------------------------------
# Service (send + queue + bounce orchestration)
# ---------------------------------------------------------------------------


class EmailService:
    """Ties the queue, the sender, and bounce handling together."""

    def __init__(
        self,
        queue: EmailQueue,
        sender: SmtpSender,
        *,
        base_url: Optional[str] = None,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self._queue = queue
        self._sender = sender
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._now = now or time.time

    def _link(self, path: str, token: str) -> str:
        return f"{self._base_url}/{path}/{token}"

    def _resolve_expiry(
        self,
        kind: str,
        expires_at: Optional[float],
        ttl_seconds: Optional[int],
    ) -> float:
        if expires_at is not None:
            return expires_at
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS[kind]
        return self._now() + ttl

    def _enqueue(
        self,
        *,
        kind: str,
        recipient: str,
        event_id: str,
        template_vars: dict[str, str],
        expires_at: float,
    ) -> OutboxEmail:
        recipient = (recipient or "").strip()
        if not recipient or "@" not in recipient:
            raise EmailError("El destinatario es obligatorio")
        if kind not in VALID_KINDS:
            raise EmailError("Tipo de correo no válido")
        if self._queue.is_suppressed(recipient):
            raise EmailError("Destinatario suprimido por un rebote previo")

        email = OutboxEmail(
            id=make_email_id(kind, event_id),
            kind=kind,
            recipient=recipient,
            event_id=event_id,
            created_at=self._now(),
            expires_at=expires_at,
            template_vars=template_vars,
            attempts=0,
            state=STATE_QUEUED,
        )
        return self._queue.enqueue(email)

    # -- kind-specific builders -------------------------------------------
    def send_invitation(
        self,
        *,
        recipient: str,
        token: str,
        store_name: str,
        event_id: str,
        expires_at: Optional[float] = None,
        ttl_seconds: Optional[int] = None,
    ) -> OutboxEmail:
        expiry = self._resolve_expiry(KIND_INVITATION, expires_at, ttl_seconds)
        return self._enqueue(
            kind=KIND_INVITATION,
            recipient=recipient,
            event_id=event_id,
            template_vars={
                "link": self._link("invite", token),
                "store_name": store_name,
                "expires": _expires_label(expiry),
            },
            expires_at=expiry,
        )

    def send_verification(
        self,
        *,
        recipient: str,
        otp: str,
        event_id: str,
        expires_at: Optional[float] = None,
        ttl_seconds: Optional[int] = None,
    ) -> OutboxEmail:
        expiry = self._resolve_expiry(KIND_VERIFICATION, expires_at, ttl_seconds)
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS[KIND_VERIFICATION]
        minutes = max(1, int(round(ttl / 60.0)))
        return self._enqueue(
            kind=KIND_VERIFICATION,
            recipient=recipient,
            event_id=event_id,
            template_vars={"otp": otp, "minutes": str(minutes)},
            expires_at=expiry,
        )

    def send_recovery(
        self,
        *,
        recipient: str,
        token: str,
        event_id: str,
        expires_at: Optional[float] = None,
        ttl_seconds: Optional[int] = None,
    ) -> OutboxEmail:
        expiry = self._resolve_expiry(KIND_RECOVERY, expires_at, ttl_seconds)
        return self._enqueue(
            kind=KIND_RECOVERY,
            recipient=recipient,
            event_id=event_id,
            template_vars={
                "link": self._link("recovery", token),
                "expires": _expires_label(expiry),
            },
            expires_at=expiry,
        )

    # -- queue drain -------------------------------------------------------
    def _log(self, event: str, email: OutboxEmail) -> None:
        # safe_summary carries no OTP, link, or full mailbox.
        logger.info("%s %s", event, safe_summary(email))

    def drain_queue(
        self, *, limit: Optional[int] = None, now: Optional[float] = None
    ) -> DrainResult:
        now = self._now() if now is None else now
        pending = self._queue.pending()
        if limit is not None:
            pending = pending[:limit]

        sent = expired = failed = suppressed = 0
        for email in pending:
            if email.expires_at is not None and now > email.expires_at:
                self._queue.mark_expired(email.id)
                expired += 1
                self._log("email_expired", email)
                continue
            if self._queue.is_suppressed(email.recipient):
                suppressed += 1
                self._log("email_suppressed", email)
                continue
            try:
                self._sender.send(email)
            except SmtpDeliveryError as exc:
                self._queue.mark_failed(
                    email.id, error=exc.code, permanent=exc.permanent
                )
                failed += 1
                self._log("email_failed", email)
                continue
            self._queue.mark_sent(email.id, sent_at=now)
            sent += 1
            self._log("email_sent", email)

        return DrainResult(sent=sent, expired=expired, failed=failed, suppressed=suppressed)

    # -- bounce handling ---------------------------------------------------
    def handle_bounce(
        self,
        *,
        recipient: str,
        reason: str,
        message_id: Optional[str] = None,
        permanent: bool = True,
        now: Optional[float] = None,
    ) -> None:
        """Record a bounce and, when correlated, mark the outbox row bounced.

        A permanent bounce suppresses the recipient so future transactional
        email to that mailbox is refused at enqueue time.
        """

        recipient = (recipient or "").strip()
        if not recipient:
            raise EmailError("El destinatario del rebote es obligatorio")
        bounced_at = self._now() if now is None else now
        self._queue.record_bounce(
            Bounce(
                recipient=recipient,
                reason=reason,
                message_id=message_id,
                bounced_at=bounced_at,
                permanent=permanent,
            )
        )
        if message_id:
            email_id = message_id.strip().strip("<>")
            if "@" in email_id:
                email_id = email_id.split("@", 1)[0]
            self._queue.mark_bounced(email_id, reason=reason)

    def requeue(self, email_id: str) -> Optional[OutboxEmail]:
        return self._queue.requeue(email_id)

    def is_suppressed(self, recipient: str) -> bool:
        return self._queue.is_suppressed(recipient)
