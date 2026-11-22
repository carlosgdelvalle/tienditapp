"""Offline sync HTTP surface: lease + signed price snapshot, event replay/ack.

`register(app)` installs this router. `server/main.py` is intentionally left
untouched; the coordinator wires the one-line `register(app)` call. The router
reuses the SQLite connection/transaction helpers from `server.db` and the
idempotent apply contract from `server.outbox`.

Endpoints (all under /api/sync):

- POST /lease   -> signed 12-hour offline authorization + signed price snapshot.
- POST /events  -> ordered replay of pending events, one receipt per applied
                   operation (the receipt gates client deletion).

Tenant isolation is enforced at three layers: a device is bound to one tenant
forever (`outbox_devices`), the lease signature proves that binding, and every
event must carry the same `tenantId`/`deviceId` as the lease.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .db import connect, write_transaction
from .outbox import (
    SyncError,
    apply_event,
    ensure_outbox_schema,
    last_applied_sequence,
)

LEASE_TTL_SECONDS = 12 * 60 * 60  # 12 hours: offline authorization only.
LEASE_VERSION = 1
SNAPSHOT_VERSION = 1

_SYNC_SIGNING_KEY_ENV = "ABARPAY_SYNC_SIGNING_KEY"


def _signing_key(settings: Any) -> bytes:
    """HMAC key for leases and snapshots.

    Production sets `ABARPAY_SYNC_SIGNING_KEY`; without it the server falls
    back to a deterministic key derived from the owner PIN so the demo and the
    test suite stay self-contained. This is a new configuration knob to report
    to the coordinator (see the integration notes).
    """

    raw = os.environ.get(_SYNC_SIGNING_KEY_ENV, "").strip()
    if raw:
        return raw.encode("utf-8")
    return hashlib.sha256(
        ("abarpay-sync-v1:" + str(settings.owner_pin)).encode("utf-8")
    ).digest()


def _sign(settings: Any, canonical: str) -> str:
    return hmac.new(
        _signing_key(settings), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _lease_canonical(lease: dict[str, Any]) -> str:
    return "|".join(
        str(lease.get(key))
        for key in (
            "v",
            "tenantId",
            "storeId",
            "deviceId",
            "membershipId",
            "issuedAt",
            "expiresAt",
        )
    )


def _snapshot_canonical(snapshot: dict[str, Any]) -> str:
    items = "|".join(
        "{0}:{1}:{2}:{3}".format(
            item.get("productId"),
            item.get("unit"),
            item.get("priceCents"),
            1 if item.get("unlimitedStock") else 0,
        )
        for item in sorted(
            snapshot.get("items") or [], key=lambda i: i.get("productId", "")
        )
    )
    return "|".join(
        [
            str(snapshot.get("v")),
            str(snapshot.get("catalogVersion")),
            str(snapshot.get("asOf")),
            str(snapshot.get("expiresAt")),
            items,
        ]
    )


def _catalog_fingerprint(items: list[dict[str, Any]]) -> str:
    """Deterministic full-hash fingerprint of a catalog snapshot's items."""

    canonical = "|".join(
        f"{item['productId']}:{item['unit']}:{item['priceCents']}:"
        f"{1 if item['unlimitedStock'] else 0}"
        for item in items
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _catalog_snapshot(
    conn, store_id: str, now: int, expires_at: int
) -> tuple[dict[str, Any], str]:
    """Current catalog as a signed snapshot plus its durable fingerprint.

    Prices come from the database. The full fingerprint is stored server-side
    so a later replay can recompute totals from the exact issued version.
    """

    rows = conn.execute(
        "SELECT id, unit, price_cents, unlimited_stock "
        "FROM products WHERE store_id = ? ORDER BY id",
        (store_id,),
    ).fetchall()
    items = [
        {
            "productId": row["id"],
            "unit": row["unit"],
            "priceCents": row["price_cents"],
            "unlimitedStock": bool(row["unlimited_stock"]),
        }
        for row in rows
    ]
    fingerprint = _catalog_fingerprint(items)
    return {
        "v": SNAPSHOT_VERSION,
        "catalogVersion": int(fingerprint[:8], 16),
        "asOf": now,
        "expiresAt": expires_at,
        "items": items,
    }, fingerprint


def _persist_snapshot(
    conn, store_id: str, snapshot: dict[str, Any], fingerprint: str
) -> None:
    """Durably store the issued snapshot keyed by (store, catalog version)."""

    version = int(snapshot["catalogVersion"])
    conn.execute(
        """INSERT OR REPLACE INTO catalog_snapshots
           (store_id, catalog_version, as_of, expires_at, fingerprint)
           VALUES (?, ?, ?, ?, ?)""",
        (
            store_id,
            version,
            int(snapshot["asOf"]),
            int(snapshot["expiresAt"]),
            fingerprint,
        ),
    )
    for item in snapshot["items"]:
        conn.execute(
            """INSERT OR REPLACE INTO catalog_snapshot_items
               (store_id, catalog_version, product_id, price_cents, unit,
                unlimited_stock)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                store_id,
                version,
                item["productId"],
                item["priceCents"],
                item["unit"],
                1 if item["unlimitedStock"] else 0,
            ),
        )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class LeaseIn(BaseModel):
    deviceId: str
    storeId: str
    tenantId: str
    membershipId: str


class SyncIn(BaseModel):
    lease: dict[str, Any]
    events: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def register(app) -> None:
    router = APIRouter(prefix="/api/sync")

    def get_settings(request: Request):
        return request.app.state.settings

    def get_sync_db(request: Request) -> Iterator:
        conn = connect(request.app.state.settings.db_path)
        try:
            ensure_outbox_schema(conn)
            yield conn
        finally:
            conn.close()

    @router.post("/lease")
    def issue_lease(
        body: LeaseIn,
        conn=Depends(get_sync_db),
        settings=Depends(get_settings),
    ):
        device_id = _require_id(body.deviceId, "deviceId")
        tenant_id = _require_id(body.tenantId, "tenantId")
        store_id = _require_id(body.storeId, "storeId")
        membership_id = _require_id(body.membershipId, "membershipId")

        store = conn.execute(
            "SELECT id FROM stores WHERE id = ?", (store_id,)
        ).fetchone()
        if store is None:
            raise HTTPException(status_code=404, detail="Tienda no encontrada")

        now = int(time.time())
        expires_at = now + LEASE_TTL_SECONDS

        with write_transaction(conn):
            existing = conn.execute(
                "SELECT * FROM outbox_devices WHERE device_id = ?", (device_id,)
            ).fetchone()
            if existing is not None and existing["tenant_id"] != tenant_id:
                raise HTTPException(
                    status_code=409,
                    detail="Dispositivo ya vinculado a otro negocio",
                )
            if existing is not None and existing["store_id"] != store_id:
                raise HTTPException(
                    status_code=409,
                    detail="Dispositivo ya vinculado a otra tienda",
                )
            conn.execute(
                """INSERT OR IGNORE INTO outbox_devices
                       (device_id, tenant_id, store_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (device_id, tenant_id, store_id, float(now)),
            )

        lease = {
            "v": LEASE_VERSION,
            "tenantId": tenant_id,
            "storeId": store_id,
            "deviceId": device_id,
            "membershipId": membership_id,
            "issuedAt": now,
            "expiresAt": expires_at,
        }
        lease["signature"] = _sign(settings, _lease_canonical(lease))

        snapshot, fingerprint = _catalog_snapshot(conn, store_id, now, expires_at)
        with write_transaction(conn):
            _persist_snapshot(conn, store_id, snapshot, fingerprint)
        snapshot["signature"] = _sign(settings, _snapshot_canonical(snapshot))

        return {"lease": lease, "snapshot": snapshot}

    @router.post("/events")
    def replay_events(
        body: SyncIn,
        conn=Depends(get_sync_db),
        settings=Depends(get_settings),
    ):
        tenant_id, store_id, device_id, expires_at = _verify_lease(
            settings, body.lease, conn
        )

        acks = [
            _apply_one(conn, tenant_id, store_id, device_id, expires_at, event)
            for event in body.events
        ]
        next_sequence = last_applied_sequence(conn, tenant_id, device_id) + 1
        return {
            "deviceId": device_id,
            "tenantId": tenant_id,
            "acks": acks,
            "nextSequence": next_sequence,
        }

    app.include_router(router)


# ---------------------------------------------------------------------------
# Verification and per-event application
# ---------------------------------------------------------------------------


def _require_id(value: str, field: str) -> str:
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{field} es obligatorio")
    return text


def _verify_lease(
    settings: Any, lease: dict[str, Any], conn
) -> tuple[str, str, str, int]:
    """Verify a lease signature and binding; return the trusted identity.

    The expiry is NOT rejected here: a legitimate operation finished just
    before expiry is still synchronized afterwards (the arrival time is never
    used to discard it). Per-event, only events recorded *after* expiry are
    rejected (see `_apply_one`).
    """

    if not isinstance(lease, dict):
        raise HTTPException(status_code=401, detail="Arrendamiento inválido")
    provided = lease.get("signature")
    if not provided or not _constant_time_equal(
        _sign(settings, _lease_canonical(lease)), str(provided)
    ):
        raise HTTPException(status_code=401, detail="Firma del arrendamiento inválida")

    try:
        expires_at = int(lease.get("expiresAt") or 0)
    except (TypeError, ValueError):
        expires_at = 0
    device_id = _require_id(lease.get("deviceId") or "", "deviceId")
    tenant_id = _require_id(lease.get("tenantId") or "", "tenantId")

    binding = conn.execute(
        "SELECT * FROM outbox_devices WHERE device_id = ?", (device_id,)
    ).fetchone()
    if binding is None or binding["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=409, detail="Dispositivo no vinculado a este negocio"
        )
    return tenant_id, binding["store_id"], device_id, expires_at


def _apply_one(
    conn,
    tenant_id: str,
    store_id: str,
    device_id: str,
    expires_at: int,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Apply one event and produce its ack (receipt or rejection)."""

    if not isinstance(event, dict):
        return _ack_error(None, None, "invalid_event", "Evento inválido")
    event_id = event.get("eventId")
    sequence = event.get("sequence")
    try:
        sequence = int(sequence)
    except (TypeError, ValueError):
        return _ack_error(sequence, event_id, "invalid_sequence", "sequence inválido")
    if not event_id or not str(event_id).strip():
        return _ack_error(sequence, event_id, "invalid_event_id", "eventId inválido")
    event_id = str(event_id)

    # Tenant + device scoping: a device may only replay its own, own-tenant
    # events. This is the tenant-isolation guard on top of the lease binding.
    if event.get("deviceId") != device_id:
        return _ack_error(
            sequence, event_id, "device_mismatch", "El evento no pertenece a este dispositivo"
        )
    if event.get("tenantId") != tenant_id:
        return _ack_error(
            sequence, event_id, "tenant_mismatch", "El evento pertenece a otro negocio"
        )

    try:
        occurred_at = int(event.get("occurredAt"))
    except (TypeError, ValueError):
        return _ack_error(
            sequence, event_id, "invalid_occurred_at", "occurredAt inválido"
        )
    if occurred_at > expires_at:
        return _ack_error(
            sequence,
            event_id,
            "lease_expired",
            "Vuelve a autorizar en línea para registrar más ventas",
        )

    payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    try:
        result = apply_event(
            conn,
            tenant_id=tenant_id,
            device_id=device_id,
            event_id=event_id,
            sequence=sequence,
            event_type=event.get("type"),
            occurred_at=occurred_at,
            payload=payload,
            store_id=store_id,
            catalog_version=event.get("catalogVersion"),
        )
    except SyncError as exc:
        return _ack_error(sequence, event_id, exc.code, exc.detail)

    return {
        "sequence": sequence,
        "eventId": event_id,
        "applied": bool(result["applied"]),
        "duplicate": bool(result["duplicate"]),
        "conflict": bool(result["conflict"]),
        "error": result.get("error"),
        "receipt": result.get("receipt"),
    }


def _ack_error(sequence, event_id, code: str, detail: str) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "eventId": event_id,
        "applied": False,
        "duplicate": False,
        "conflict": False,
        "error": code,
        "detail": detail,
        "receipt": None,
    }
