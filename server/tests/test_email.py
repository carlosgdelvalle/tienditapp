"""Transactional email core tests (SIMULADO, no network except loopback).

Covers the M5 email worker:

- queue enqueue/drain with the state machine (queued -> accepted / expired /
  retryable-failure / failed) and idempotent re-enqueue,
- bounce handling (permanent bounce suppresses the recipient and marks the
  outbox row bounced),
- secret hygiene: OTPs and access links never appear in logs, repr, or
  safe_summary,
- SMTP2GO sender over mandatory STARTTLS against a loopback capture server
  (STARTTLS is actually used; a missing-STARTTLS server is rejected with no
  plaintext fallback), and the SIMULADO "no credentials" guard.

No test contacts a real SMTP server; the capture server binds 127.0.0.1 only.
"""

from __future__ import annotations

import datetime
import logging
import socket
import ssl
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.email import (  # noqa: E402
    BODY_TEMPLATES,
    DEFAULT_BASE_URL,
    EmailService,
    EmailSettings,
    EmailError,
    KIND_INVITATION,
    KIND_RECOVERY,
    KIND_VERIFICATION,
    MemoryEmailQueue,
    OutboxEmail,
    Smtp2GoSender,
    SmtpDeliveryError,
    SmtpSender,
    STATE_ACCEPTED,
    STATE_BOUNCED,
    STATE_EXPIRED,
    STATE_FAILED,
    STATE_QUEUED,
    STATE_RETRYABLE_FAILURE,
    make_email_id,
    mask_email,
    redact,
    render_body,
    render_message,
    safe_summary,
)


# ---------------------------------------------------------------------------
# SIMULADO recording sender (queue tests)
# ---------------------------------------------------------------------------


class RecordingSender(SmtpSender):
    """SIMULADO - records what it would have sent; no network."""

    simulated = True

    def __init__(self) -> None:
        self.sent: list[OutboxEmail] = []
        self.fail_with: SmtpDeliveryError | None = None

    def send(self, email: OutboxEmail) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(email)


def _service(
    queue: MemoryEmailQueue | None = None,
    sender: SmtpSender | None = None,
    *,
    base_url: str = DEFAULT_BASE_URL,
    now=None,
) -> EmailService:
    return EmailService(
        queue or MemoryEmailQueue(),
        sender or RecordingSender(),
        base_url=base_url,
        now=now,
    )


# ---------------------------------------------------------------------------
# Queue: enqueue / drain
# ---------------------------------------------------------------------------


def test_enqueue_and_drain_marks_accepted():
    queue = MemoryEmailQueue()
    sender = RecordingSender()
    service = _service(queue, sender)

    inv = service.send_invitation(
        recipient="lupita@abarpay.test",
        token="TOKEN_INVITE",
        store_name="Tienda Rosa",
        event_id="inv_1",
    )
    ver = service.send_verification(
        recipient="rosa@abarpay.test", otp="123456", event_id="usr_1"
    )

    assert inv.state == STATE_QUEUED
    assert ver.state == STATE_QUEUED
    assert len(queue.pending()) == 2

    result = service.drain_queue()
    assert result.sent == 2
    assert result.failed == 0
    assert result.expired == 0

    assert queue.get(inv.id).state == STATE_ACCEPTED
    assert queue.get(ver.id).state == STATE_ACCEPTED
    assert [e.id for e in sender.sent] == [inv.id, ver.id]


def test_enqueue_is_idempotent_for_same_event():
    queue = MemoryEmailQueue()
    service = _service(queue)

    first = service.send_recovery(
        recipient="rosa@abarpay.test", token="REC1", event_id="recover_1"
    )
    second = service.send_recovery(
        recipient="rosa@abarpay.test", token="REC2", event_id="recover_1"
    )

    assert first.id == second.id
    assert first.id == make_email_id(KIND_RECOVERY, "recover_1")
    assert len(queue.pending()) == 1


def test_retryable_failure_then_requeue_and_success():
    queue = MemoryEmailQueue()
    sender = RecordingSender()
    service = _service(queue, sender)

    email = service.send_verification(
        recipient="rosa@abarpay.test", otp="111111", event_id="usr_1"
    )

    sender.fail_with = SmtpDeliveryError("transport_error", permanent=False)
    result = service.drain_queue()
    assert result.failed == 1
    assert queue.get(email.id).state == STATE_RETRYABLE_FAILURE
    assert queue.get(email.id).last_error == "transport_error"

    # Requeue moves it back to queued; a healthy drain delivers it.
    requeued = service.requeue(email.id)
    assert requeued is not None and requeued.state == STATE_QUEUED

    sender.fail_with = None
    result = service.drain_queue()
    assert result.sent == 1
    assert queue.get(email.id).state == STATE_ACCEPTED
    assert queue.get(email.id).attempts == 2


def test_permanent_failure_is_not_retryable():
    queue = MemoryEmailQueue()
    sender = RecordingSender()
    service = _service(queue, sender)

    email = service.send_verification(
        recipient="rosa@abarpay.test", otp="222222", event_id="usr_2"
    )
    sender.fail_with = SmtpDeliveryError("auth_failed", permanent=True)
    service.drain_queue()

    assert queue.get(email.id).state == STATE_FAILED
    assert queue.get(email.id).last_error == "auth_failed"
    # requeue refuses a permanent failure.
    assert service.requeue(email.id) is None


def test_expired_email_is_never_sent():
    queue = MemoryEmailQueue()
    sender = RecordingSender()
    t0 = 1_000_000.0
    service = _service(queue, sender, now=lambda: t0)

    email = service.send_recovery(
        recipient="rosa@abarpay.test",
        token="REC_EXPIRED",
        event_id="recover_expired",
        expires_at=t0 - 1,  # already expired
    )

    result = service.drain_queue(now=t0)
    assert result.expired == 1
    assert result.sent == 0
    assert sender.sent == []
    assert queue.get(email.id).state == STATE_EXPIRED


# ---------------------------------------------------------------------------
# Bounce handling
# ---------------------------------------------------------------------------


def test_bounce_marks_row_and_suppresses_recipient():
    queue = MemoryEmailQueue()
    sender = RecordingSender()
    service = _service(queue, sender)

    email = service.send_invitation(
        recipient="noexiste@abarpay.test",
        token="INV_BOUNCE",
        store_name="Tienda Rosa",
        event_id="inv_bounce",
    )
    service.drain_queue()
    assert queue.get(email.id).state == STATE_ACCEPTED

    service.handle_bounce(
        recipient="noexiste@abarpay.test",
        reason="550 mailbox not found",
        message_id=email.id,
        permanent=True,
    )

    assert queue.get(email.id).state == STATE_BOUNCED
    assert service.is_suppressed("noexiste@abarpay.test") is True
    assert len(queue.bounces) == 1
    assert queue.bounces[0].permanent is True


def test_suppressed_recipient_is_refused_at_enqueue():
    queue = MemoryEmailQueue()
    service = _service(queue)

    service.handle_bounce(
        recipient="nula@abarpay.test", reason="550", permanent=True
    )
    assert service.is_suppressed("nula@abarpay.test") is True

    with pytest.raises(EmailError):
        service.send_verification(
            recipient="nula@abarpay.test", otp="999999", event_id="usr_9"
        )


def test_soft_bounce_does_not_suppress():
    queue = MemoryEmailQueue()
    service = _service(queue)

    service.handle_bounce(
        recipient="llena@abarpay.test", reason="452 mailbox full", permanent=False
    )
    assert service.is_suppressed("llena@abarpay.test") is False


# ---------------------------------------------------------------------------
# Secret hygiene: OTPs and access links never leak
# ---------------------------------------------------------------------------


def test_secrets_never_appear_in_logs_repr_or_summary(caplog):
    caplog.set_level(logging.INFO, logger="abarpay.email")
    queue = MemoryEmailQueue()
    sender = RecordingSender()
    service = _service(queue, sender)

    otp = "731904"
    email = service.send_verification(
        recipient="secreto@abarpay.test", otp=otp, event_id="usr_secret"
    )
    link = service.send_recovery(
        recipient="secreto@abarpay.test", token="SUPER_SECRET_TOKEN", event_id="rec_secret"
    )
    service.drain_queue()

    # Logs, repr, and safe_summary must not contain the OTP, the access token,
    # or the full mailbox.
    for leaked in (otp, "SUPER_SECRET_TOKEN", "secreto@abarpay.test"):
        assert leaked not in caplog.text
        assert leaked not in repr(email)
        assert leaked not in repr(link)
        assert leaked not in str(safe_summary(email))
        assert leaked not in str(safe_summary(link))

    # The mailbox is masked in summaries.
    assert "secreto@abarpay.test" not in str(safe_summary(email))
    assert mask_email("secreto@abarpay.test") == "s******@abarpay.test"
    assert "s******@abarpay.test" in str(safe_summary(email))


def test_render_body_contains_secret_but_subject_never_does():
    queue = MemoryEmailQueue()
    service = _service(queue)

    email = service.send_verification(
        recipient="rosa@abarpay.test", otp="424242", event_id="usr_otp"
    )
    body = render_body(email)
    assert "424242" in body

    from server.email import SUBJECTS

    assert "424242" not in SUBJECTS[KIND_VERIFICATION]

    msg = render_message(email, sender="mailer@abarpay.app", sender_name="Abarpay")
    assert "424242" in msg.get_payload()
    assert "424242" not in msg["Subject"]


def test_redact_replaces_all_secrets():
    text = "Enviado a rosa@abarpay.test con codigo 123456 y enlace https://x/invite/TK"
    out = redact(text, ["123456", "https://x/invite/TK", "rosa@abarpay.test"])
    assert "123456" not in out
    assert "https://x/invite/TK" not in out
    assert "rosa@abarpay.test" not in out
    assert out.count("[REDACTED]") == 3


def test_invitation_link_points_at_invite_route():
    queue = MemoryEmailQueue()
    service = _service(queue, base_url="https://abarpay.app")

    email = service.send_invitation(
        recipient="emp@abarpay.test",
        token="ABC123",
        store_name="Tienda Rosa",
        event_id="inv_route",
    )
    body = render_body(email)
    assert "https://abarpay.app/invite/ABC123" in body
    assert "Tienda Rosa" in body


# ---------------------------------------------------------------------------
# SIMULADO guard: no credentials -> refuse delivery
# ---------------------------------------------------------------------------


def test_sender_without_credentials_is_simulado():
    sender = Smtp2GoSender(EmailSettings())
    assert sender.configured is False
    queue = MemoryEmailQueue()
    service = _service(queue, sender)
    email = service.send_verification(
        recipient="rosa@abarpay.test", otp="000000", event_id="usr_nocred"
    )

    result = service.drain_queue()
    assert result.sent == 0
    assert result.failed == 1
    assert queue.get(email.id).state == STATE_RETRYABLE_FAILURE
    assert queue.get(email.id).last_error == "smtp_not_configured"


# ---------------------------------------------------------------------------
# Loopback capture SMTP server (no network)
# ---------------------------------------------------------------------------


class _CaptureChannel:
    def __init__(self, conn: socket.socket, server: "_CaptureSmtpServer") -> None:
        self.conn = conn
        self.server = server
        self.tls = False
        self.mail_from: str | None = None
        self.rcpt_tos: list[str] = []
        self.buffer = b""

    def _readline(self) -> str | None:
        while b"\r\n" not in self.buffer:
            data = self.conn.recv(4096)
            if not data:
                return None
            self.buffer += data
        line, self.buffer = self.buffer.split(b"\r\n", 1)
        return line.decode("utf-8", "replace")

    def _send(self, text: str) -> None:
        self.conn.sendall((text + "\r\n").encode("utf-8"))

    def _ehlo(self) -> None:
        caps = []
        if self.server.offer_starttls and not self.tls:
            caps.append("STARTTLS")
        caps.append("AUTH PLAIN")
        caps.append("8BITMIME")
        lines = ["250-localhost"]
        for cap in caps[:-1]:
            lines.append("250-" + cap)
        lines.append("250 " + caps[-1])
        for line in lines:
            self._send(line)

    def handle(self) -> None:
        self._send("220 localhost SMTP capture ready")
        while True:
            line = self._readline()
            if line is None:
                break
            command = line.split(" ", 1)[0].upper()
            if command == "EHLO" or command == "HELO":
                self._ehlo()
            elif command == "STARTTLS":
                if not self.server.offer_starttls or self.server.tls_context is None:
                    self._send("500 STARTTLS not supported")
                else:
                    self._send("220 ready for TLS")
                    self.conn = self.server.tls_context.wrap_socket(
                        self.conn, server_side=True
                    )
                    self.tls = True
                    self.server.used_tls = True
                    self.buffer = b""
            elif command == "AUTH":
                self._send("235 2.7.0 Authentication successful")
            elif command == "MAIL":
                self.mail_from = line
                self._send("250 ok")
            elif command == "RCPT":
                self.rcpt_tos.append(line)
                self._send("250 ok")
            elif command == "DATA":
                self._send("354 end with .")
                data_lines: list[str] = []
                while True:
                    dline = self._readline()
                    if dline is None:
                        break
                    if dline == ".":
                        break
                    if dline.startswith(".."):
                        dline = dline[1:]
                    data_lines.append(dline)
                self.server.messages.append(
                    {
                        "mail_from": self.mail_from,
                        "rcpt_tos": list(self.rcpt_tos),
                        "data": "\n".join(data_lines),
                        "tls": self.tls,
                    }
                )
                self._send("250 queued")
                self.mail_from = None
                self.rcpt_tos = []
            elif command == "RSET":
                self.mail_from = None
                self.rcpt_tos = []
                self._send("250 ok")
            elif command == "QUIT":
                self._send("221 bye")
                break
            else:
                self._send("250 ok")
        try:
            self.conn.close()
        except OSError:
            pass


class _CaptureSmtpServer:
    """SIMULADO loopback SMTP capture server with optional STARTTLS."""

    simulated = True

    def __init__(self, *, offer_starttls: bool, tls_context: ssl.SSLContext | None) -> None:
        self.offer_starttls = offer_starttls
        self.tls_context = tls_context
        self.messages: list[dict] = []
        self.used_tls = False
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._sock is not None
        while True:
            try:
                conn, _addr = self._sock.accept()
            except OSError:
                break
            channel = _CaptureChannel(conn, self)
            threading.Thread(target=channel.handle, daemon=True).start()

    def stop(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass


def _make_self_signed(tmp_path: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    key_path = tmp_path / "smtp-key.pem"
    cert_path = tmp_path / "smtp-cert.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def _client_context(cert_path: Path) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(cert_path))
    ctx.check_hostname = False  # loopback; only the CA trust is asserted here
    return ctx


# ---------------------------------------------------------------------------
# SMTP2GO sender over STARTTLS (loopback capture, no network)
# ---------------------------------------------------------------------------


def test_tls_delivery_to_capture_server(tmp_path):
    cert_path, key_path = _make_self_signed(tmp_path)
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

    server = _CaptureSmtpServer(offer_starttls=True, tls_context=server_ctx)
    server.start()
    try:
        settings = EmailSettings(
            host="127.0.0.1",
            port=server.port,
            username="smtp2go-test",
            password="test-secret",
            sender="mailer@abarpay.app",
            sender_name="Abarpay",
        )
        sender = Smtp2GoSender(settings, ssl_context=_client_context(cert_path))
        queue = MemoryEmailQueue()
        service = _service(queue, sender)

        email = service.send_verification(
            recipient="destino@abarpay.test", otp="880011", event_id="usr_tls"
        )
        result = service.drain_queue()

        assert result.sent == 1
        assert queue.get(email.id).state == STATE_ACCEPTED
        # STARTTLS was actually negotiated; the message arrived encrypted.
        assert server.used_tls is True
        assert len(server.messages) == 1
        captured = server.messages[0]
        assert captured["tls"] is True
        assert "destino@abarpay.test" in captured["rcpt_tos"][0]
        assert "880011" in captured["data"]
    finally:
        server.stop()


def test_missing_starttls_is_rejected_without_plaintext_fallback():
    server = _CaptureSmtpServer(offer_starttls=False, tls_context=None)
    server.start()
    try:
        settings = EmailSettings(
            host="127.0.0.1",
            port=server.port,
            username="smtp2go-test",
            password="test-secret",
            sender="mailer@abarpay.app",
            sender_name="Abarpay",
        )
        sender = Smtp2GoSender(settings)
        queue = MemoryEmailQueue()
        service = _service(queue, sender)

        email = service.send_verification(
            recipient="destino@abarpay.test", otp="121212", event_id="usr_nostarttls"
        )
        result = service.drain_queue()

        assert result.sent == 0
        assert result.failed == 1
        assert queue.get(email.id).state == STATE_RETRYABLE_FAILURE
        assert queue.get(email.id).last_error == "starttls_not_supported"
        # Nothing was delivered in plaintext.
        assert server.messages == []
        assert server.used_tls is False
    finally:
        server.stop()
