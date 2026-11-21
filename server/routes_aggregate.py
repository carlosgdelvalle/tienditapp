"""FastAPI router for the M7 aggregate-data partner (SIMULADO).

Serves /api/aggregate with role-based authorization (X-Platform-Role header),
separate from the merchant console. The integrator wires one line next to the
other register_* calls in server/main.py:

    from .routes_aggregate import register as register_aggregate_routes
    register_aggregate_routes(app)

Roles (SIMULADO identity, X-Platform-Role header):
  staff     SaaS staff - full access (demo default)
  operator  authorized publication operator - consent and publication
  analyst   reviews the simulated report, eligible cohorts, and suppression
            reasons; cannot deliver and never receives per-store detail.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .aggregate import (
    APPROVED_METRICS,
    APPROVED_PURPOSES,
    APPROVED_SCOPES,
    MAX_CONTRIBUTION_RATIO,
    MIN_PARTICIPANTS,
    AggregateService,
    Consent,
    DeliveryRecord,
    InvalidStateError,
    RecordNotFoundError,
    default_simulado_service,
)

_READ_ROLES = {"staff", "operator", "analyst"}
_WRITE_ROLES = {"staff", "operator"}


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ConsentIn(BaseModel):
    storeId: str
    purpose: str
    scope: str


class PrepareIn(BaseModel):
    purpose: str
    scope: str
    metric: str
    recipient: str


class AuthorizeIn(BaseModel):
    operator: str | None = None
    recipient: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _role(
    x_platform_role: str | None, allowed: set[str]
) -> str:
    if not x_platform_role:
        raise HTTPException(
            status_code=401,
            detail="Falta rol de plataforma (header X-Platform-Role)",
        )
    role = x_platform_role.strip().lower()
    if role == "staff" or role in allowed:
        return role
    raise HTTPException(
        status_code=403,
        detail={
            "code": "insufficient_access",
            "message": "Acceso insuficiente para esta operación",
            "providedRole": role,
            "requiredRoles": sorted(allowed) + ["staff"],
        },
    )


def _require_catalog(
    purpose: str, scope: str, metric: str | None = None
) -> None:
    if purpose not in APPROVED_PURPOSES:
        raise HTTPException(status_code=400, detail="Propósito no aprobado")
    if scope not in APPROVED_SCOPES:
        raise HTTPException(status_code=400, detail="Alcance no aprobado")
    if metric is not None and metric not in APPROVED_METRICS:
        raise HTTPException(status_code=400, detail="Métrica no aprobada")


def _consent_payload(consent: Consent) -> dict[str, Any]:
    return {
        "storeId": consent.store_id,
        "purpose": consent.purpose,
        "scope": consent.scope,
        "version": consent.version,
        "status": consent.status,
        "consentedAt": consent.consented_at,
        "withdrawnAt": consent.withdrawn_at,
    }


def _record_payload(
    record: DeliveryRecord, *, include_participants: bool
) -> dict[str, Any]:
    """Serialize a report without leaking per-store detail to analysts.

    A suppressed (or invalidated) record exposes the permitted reasons only:
    the protected value and derived percentages stay hidden.
    """

    reveal_aggregate = record.status in {"allowed", "authorized", "delivered"}
    payload: dict[str, Any] = {
        "simulado": True,
        "id": record.id,
        "purpose": record.purpose,
        "scope": record.scope,
        "metric": record.metric,
        "recipient": record.recipient,
        "status": record.status,
        "participantCount": len(record.participants),
        "suppressionReasons": list(record.suppression_reasons),
        "suppressionDetails": list(record.suppression_details),
        "total": record.total if reveal_aggregate else None,
        "dominanceRatio": record.dominance_ratio if reveal_aggregate else None,
        "operator": record.operator,
        "artifactFingerprint": record.artifact_fingerprint,
        "preparedAt": record.prepared_at,
        "authorizedAt": record.authorized_at,
        "deliveredAt": record.delivered_at,
        "expiresAt": record.expires_at,
        "invalidatedReason": record.invalidated_reason,
    }
    if include_participants:
        payload["participants"] = list(record.participants)
    return payload


# ---------------------------------------------------------------------------
# register(app)
# ---------------------------------------------------------------------------


def register(app: Any, service: AggregateService | None = None) -> None:
    if service is None:
        service = default_simulado_service()
    app.state.aggregate_service = service
    svc = service

    api = APIRouter(prefix="/api/aggregate")

    @api.get("/meta")
    def aggregate_meta() -> JSONResponse:
        return JSONResponse(
            content={
                "simulado": True,
                "purposes": list(APPROVED_PURPOSES),
                "scopes": list(APPROVED_SCOPES),
                "metrics": list(APPROVED_METRICS),
                "minParticipants": MIN_PARTICIPANTS,
                "maxContributionRatio": MAX_CONTRIBUTION_RATIO,
                "roles": ["staff", "operator", "analyst"],
            }
        )

    @api.get("/consent")
    def list_consent(
        purpose: str | None = None,
        scope: str | None = None,
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        role = _role(x_platform_role, _READ_ROLES)
        consents = [
            consent
            for consent in svc.consent.all()
            if (purpose is None or consent.purpose == purpose)
            and (scope is None or consent.scope == scope)
        ]
        consents = sorted(
            consents, key=lambda c: (c.store_id, c.purpose, c.scope, c.version)
        )
        if role == "analyst":
            active = sum(1 for c in consents if c.status == "active")
            return JSONResponse(
                content={
                    "simulado": True,
                    "activeCount": active,
                    "totalCount": len(consents),
                }
            )
        return JSONResponse(
            content={
                "simulado": True,
                "items": [_consent_payload(c) for c in consents],
            }
        )

    @api.post("/consent/opt-in")
    def consent_opt_in(
        body: ConsentIn,
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        _role(x_platform_role, _WRITE_ROLES)
        _require_catalog(body.purpose, body.scope)
        store_id = body.storeId.strip()
        if not store_id:
            raise HTTPException(status_code=400, detail="storeId es obligatorio")
        consent = svc.opt_in(store_id, body.purpose, body.scope)
        return JSONResponse(
            content={"simulado": True, "consent": _consent_payload(consent)}
        )

    @api.post("/consent/withdraw")
    def consent_withdraw(
        body: ConsentIn,
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        _role(x_platform_role, _WRITE_ROLES)
        _require_catalog(body.purpose, body.scope)
        store_id = body.storeId.strip()
        if not store_id:
            raise HTTPException(status_code=400, detail="storeId es obligatorio")
        consent = svc.withdraw(store_id, body.purpose, body.scope)
        return JSONResponse(
            content={
                "simulado": True,
                "consent": _consent_payload(consent) if consent else None,
            }
        )

    @api.post("/reports/prepare")
    def reports_prepare(
        body: PrepareIn,
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        role = _role(x_platform_role, _READ_ROLES)  # analyst may review
        _require_catalog(body.purpose, body.scope, body.metric)
        recipient = body.recipient.strip()
        if not recipient:
            raise HTTPException(status_code=400, detail="recipient es obligatorio")
        record = svc.prepare(body.purpose, body.scope, body.metric, recipient)
        return JSONResponse(
            content=_record_payload(
                record, include_participants=(role in _WRITE_ROLES)
            )
        )

    @api.get("/reports/{record_id}")
    def reports_get(
        record_id: str,
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        role = _role(x_platform_role, _READ_ROLES)
        record = svc.ledger.get(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Reporte no encontrado")
        return JSONResponse(
            content=_record_payload(
                record, include_participants=(role in _WRITE_ROLES)
            )
        )

    @api.post("/reports/{record_id}/authorize")
    def reports_authorize(
        record_id: str,
        body: AuthorizeIn | None = None,
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        role = _role(x_platform_role, _WRITE_ROLES)
        body = body or AuthorizeIn()
        operator = (body.operator or "").strip() or role
        try:
            record = svc.authorize(record_id, operator, recipient=body.recipient)
        except RecordNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(
            content=_record_payload(record, include_participants=True)
        )

    @api.post("/reports/{record_id}/deliver")
    def reports_deliver(
        record_id: str,
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        _role(x_platform_role, _WRITE_ROLES)
        try:
            record = svc.deliver(record_id)
        except RecordNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if record.status == "invalidated":
            return JSONResponse(
                status_code=409,
                content=_record_payload(record, include_participants=True),
            )
        return JSONResponse(
            content=_record_payload(record, include_participants=True)
        )

    @api.get("/ledger")
    def ledger_list(
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        role = _role(x_platform_role, _READ_ROLES)
        records = sorted(svc.ledger.all(), key=lambda r: (r.prepared_at, r.id))
        return JSONResponse(
            content={
                "simulado": True,
                "items": [
                    _record_payload(r, include_participants=(role in _WRITE_ROLES))
                    for r in records
                ],
            }
        )

    app.include_router(api)
