"""Minimal PEY client and Standard Webhooks signature verification.

Only the HTTP boundary lives here. No real PEY request is made by the test
suite: production code receives a PeyClient, tests inject a clearly labeled
FakePey.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any, Mapping
from urllib.parse import quote

import httpx

DEFAULT_BASE_URL = "https://api.pey.mx"
SIGNATURE_TOLERANCE_SECONDS = 300


class PeyError(Exception):
    """PEY rejected the request (HTTP error or malformed response)."""

    def __init__(self, type_: str, message: str = "", status_code: int | None = None):
        super().__init__(f"{type_}: {message}".strip(": "))
        self.type = type_
        self.message = message
        self.status_code = status_code


class PeyTimeout(Exception):
    """The request has no response: the charge is uncertain and must reconcile."""


class PeyClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        client_kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": httpx.Timeout(timeout),
            "headers": {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.Client(**client_kwargs)

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise PeyTimeout(str(exc)) from exc

        if response.status_code >= 400:
            error_type = f"HTTP_{response.status_code}"
            message = ""
            try:
                payload = response.json()
                error = payload.get("error") if isinstance(payload, dict) else None
                if isinstance(error, dict):
                    error_type = str(error.get("type") or error_type)
                    message = str(error.get("message") or "")
            except (ValueError, TypeError):
                message = ""
            raise PeyError(error_type, message, status_code=response.status_code)

        try:
            payload = response.json()
        except ValueError as exc:
            raise PeyError("invalid_json", "PEY returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise PeyError("invalid_response", "PEY returned an unexpected payload")
        return payload

    def create_qr(
        self,
        amount_cents: int,
        concept: str,
        expiration_sec: int,
        sale_id: str,
    ) -> dict[str, Any]:
        amount_pesos = round(int(amount_cents) / 100, 2)
        return self._call(
            "POST",
            "/codi/qr",
            {
                "amount": amount_pesos,
                "concept": concept[:40],
                "expiration": int(expiration_sec),
                "generateImage": True,
                "metadata": {"saleId": sale_id},
            },
        )

    def qr_transactions(self, qr_id: str) -> list[dict[str, Any]]:
        encoded = quote(qr_id, safe="")
        payload = self._call("GET", f"/transaction/codi/qr/{encoded}")
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []


def _header(headers: Mapping[str, str], name: str) -> str:
    value = headers.get(name)
    if value is not None:
        return str(value)
    wanted = name.lower()
    for key, item in headers.items():
        if str(key).lower() == wanted:
            return str(item)
    return ""


def _decode_secret(secret: str) -> bytes | None:
    if not secret:
        return None
    encoded = secret[6:] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None
    return key or None


def verify_webhook(
    headers: Mapping[str, str],
    raw_body: bytes,
    secret: str,
    tolerance_sec: int = SIGNATURE_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """Verify a Standard Webhooks signature.

    The signed content is {webhook-id}.{webhook-timestamp}.{raw-body} and the
    HMAC-SHA256 key is the base64 part of whsec_...
    """

    message_id = _header(headers, "webhook-id")
    timestamp = _header(headers, "webhook-timestamp")
    signature_header = _header(headers, "webhook-signature")
    if not (message_id and timestamp and signature_header and secret):
        return False

    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - timestamp_int) > tolerance_sec:
        return False

    key = _decode_secret(secret)
    if key is None:
        return False

    signed = f"{message_id}.{timestamp}.".encode("utf-8") + raw_body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")

    candidates: list[str] = []
    for part in signature_header.split():
        version, separator, candidate = part.partition(",")
        if separator and version == "v1" and candidate:
            candidates.append(candidate)
    return any(hmac.compare_digest(expected, candidate) for candidate in candidates)


def payload_cents(amount: Any) -> int | None:
    """Convert a PEY peso amount (number or string) to integer cents."""

    if amount is None or isinstance(amount, bool):
        return None
    try:
        from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

        value = Decimal(str(amount).replace(",", "."))
        if not value.is_finite() or value < 0:
            return None
        return int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return None
