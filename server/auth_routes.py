"""FastAPI router for the identity and tenancy endpoints.

Registers the production contracts from docs/produccion/04-identidad-onboarding-y-pey.md
and docs/produccion/02-contratos-y-tenencia.md. It exposes a single register(app)
function so that main.py stays untouched: the integrator only calls
auth_routes.register(app) after building the app.

The tenant is always resolved from a verified session (cookie or opaque session
token) or from verified identity - never from a client-supplied tenant header.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .auth import AuthConfig, TokenValidationError, TokenValidator
from .identity import (
    CHALLENGE_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SESSION_HEADER_NAME,
    IdentityError,
    IdentityService,
    IdentityStore,
    MemoryIdentityStore,
    SessionRecord,
    User,
)

INVITE_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://abarpay-api.onrender.com")


# ---------------------------------------------------------------------------
# Dependency results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityContext:
    user: User
    token: Any  # ValidatedToken


@dataclass(frozen=True)
class SessionContext:
    user_id: str
    tenant_id: str
    role: str
    session: SessionRecord
    from_cookie: bool


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class DeviceRegisterIn(BaseModel):
    deviceId: str
    publicKey: str
    label: str | None = None


class ChallengeCreateIn(BaseModel):
    intent: Literal["browser_login", "device_link"]


class ChallengeApproveIn(BaseModel):
    deviceSignature: str
    code: str
    deviceId: str | None = None
    tenantId: str | None = None


class SessionStoreIn(BaseModel):
    tenantId: str


class InviteCreateIn(BaseModel):
    email: str | None = None
    role: str = "employee"
    canSell: bool = False
    canFiado: bool = False
    canInventory: bool = False


class MemberPatchIn(BaseModel):
    role: str | None = None
    canSell: bool | None = None
    canFiado: bool | None = None
    canInventory: bool | None = None
    active: bool | None = None


class InviteAcceptIn(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _service(request: Request) -> IdentityService:
    return request.app.state.identity_service


def _validator(request: Request) -> TokenValidator | None:
    return getattr(request.app.state, "auth_validator", None)


def _config(request: Request) -> AuthConfig:
    return getattr(request.app.state, "auth_config", None) or AuthConfig()


def require_identity(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    service: IdentityService = Depends(_service),
    validator: TokenValidator | None = Depends(_validator),
) -> IdentityContext:
    if validator is None:
        raise HTTPException(status_code=501, detail="Identidad no configurada")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token de acceso requerido")
    token = authorization.split(" ", 1)[1].strip()
    try:
        validated = validator.validate_access_token(token)
    except TokenValidationError as exc:
        raise HTTPException(status_code=401, detail=f"{exc}") from exc
    user = service.resolve_user(
        validated.idp, validated.external_sub, validated.email, validated.name
    )
    return IdentityContext(user=user, token=validated)


def require_session(
    request: Request,
    service: IdentityService = Depends(_service),
) -> SessionContext:
    token = request.cookies.get(SESSION_COOKIE_NAME) or request.headers.get(
        SESSION_HEADER_NAME
    )
    session = service.verify_session(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o vencida")
    if session.tenant_id is None:
        raise HTTPException(status_code=400, detail="No has seleccionado una tienda")
    try:
        membership = service.select_tenant(session.user_id, session.tenant_id)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SessionContext(
        user_id=session.user_id,
        tenant_id=session.tenant_id,
        role=membership.role,
        session=session,
        from_cookie=SESSION_COOKIE_NAME in request.cookies,
    )


def require_owner(
    request: Request,
    ctx: SessionContext = Depends(require_session),
    csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> SessionContext:
    if ctx.role != "owner":
        raise HTTPException(status_code=403, detail="Solo el dueño puede hacer esto")
    # Web mutations authenticated by an ambient cookie need CSRF protection.
    if ctx.from_cookie and request.method in {"POST", "PATCH", "DELETE", "PUT"}:
        if not csrf_token or not hmac.compare_digest(
            csrf_token.encode("utf-8"), ctx.session.csrf_token.encode("utf-8")
        ):
            raise HTTPException(status_code=403, detail="Token CSRF inválido")
    return ctx


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def _set_session_cookie(response: Response, token: str, config: AuthConfig) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=config.secure_cookies,
        samesite=config.cookie_samesite,
        path="/",
    )


def _set_challenge_cookie(
    response: Response, token: str, challenge_id: str, config: AuthConfig
) -> None:
    response.set_cookie(
        CHALLENGE_COOKIE_NAME,
        token,
        httponly=True,
        secure=config.secure_cookies,
        samesite=config.cookie_samesite,
        max_age=120,
        path=f"/api/auth/challenge/{challenge_id}",
    )


def _qr_svg(data: str) -> str | None:
    """Render the challenge QR as an inline SVG for the browser console.

    Uses the optional segno dependency so the owner page never needs a JS QR
    library. Returns None when segno is unavailable; production installs it via
    server/requirements.txt.
    """

    try:
        import segno
    except ImportError:
        return None
    try:
        svg = segno.make_qr(data).svg_inline(scale=6)
        # svg_inline() omits the XML namespace; a Blob served as image/svg+xml
        # requires a valid standalone SVG document.
        if "xmlns=" not in svg[:80]:
            svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        return svg
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


@router.post("/auth/device/register")
def device_register(
    body: DeviceRegisterIn,
    ctx: IdentityContext = Depends(require_identity),
    service: IdentityService = Depends(_service),
):
    try:
        device = service.register_device(
            ctx.user.id, body.deviceId, body.publicKey, body.label or ""
        )
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "deviceId": device.device_id,
        "label": device.label,
        "createdAt": device.created_at,
    }


@router.post("/auth/challenge")
def create_challenge(
    body: ChallengeCreateIn,
    response: Response,
    service: IdentityService = Depends(_service),
    config: AuthConfig = Depends(_config),
):
    try:
        challenge, browser_token = service.create_challenge(body.intent)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    _set_challenge_cookie(response, browser_token, challenge.id, config)
    qr = (
        f"abarpay://challenge/{challenge.id}?code={challenge.code}"
        f"&nonce={challenge.nonce}&exp={int(challenge.expires_at)}"
        f"&intent={challenge.intent}"
    )
    return {
        "challengeId": challenge.id,
        "code": challenge.code,
        "qr": qr,
        "qrSvg": _qr_svg(qr),
        "expiresAt": challenge.expires_at,
    }


@router.get("/auth/challenge/{challenge_id}")
def get_challenge(
    challenge_id: str,
    service: IdentityService = Depends(_service),
):
    try:
        challenge = service.get_challenge(challenge_id)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if challenge.status == "pending" and service.now() > challenge.expires_at:
        return {"status": "expired", "expiresAt": challenge.expires_at}
    return {"status": challenge.status, "expiresAt": challenge.expires_at}


@router.post("/auth/challenge/{challenge_id}/approve")
def approve_challenge(
    challenge_id: str,
    body: ChallengeApproveIn,
    ctx: IdentityContext = Depends(require_identity),
    service: IdentityService = Depends(_service),
):
    try:
        device_id = body.deviceId
        if device_id is None:
            devices = service.list_devices(ctx.user.id)
            if len(devices) != 1:
                raise IdentityError(
                    "Especifica el dispositivo que aprueba", status_code=400
                )
            device_id = devices[0].device_id
        challenge = service.approve_challenge(
            user_id=ctx.user.id,
            device_id=device_id,
            challenge_id=challenge_id,
            signature_b64=body.deviceSignature,
            code=body.code,
            tenant_id=body.tenantId,
            token_issued_at=ctx.token.issued_at,
        )
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "status": challenge.status,
        "approvedAt": challenge.approved_at,
        "tenantId": challenge.selected_tenant_id,
    }


@router.post("/auth/challenge/{challenge_id}/exchange")
def exchange_challenge(
    challenge_id: str,
    request: Request,
    response: Response,
    service: IdentityService = Depends(_service),
    config: AuthConfig = Depends(_config),
):
    browser_token = request.cookies.get(CHALLENGE_COOKIE_NAME)
    try:
        session = service.exchange_challenge(challenge_id, browser_token)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    _set_session_cookie(response, session.token, config)
    response.delete_cookie(
        CHALLENGE_COOKIE_NAME, path=f"/api/auth/challenge/{challenge_id}"
    )
    user = service.get_user(session.user_id)
    assert session.tenant_id is not None
    tenant = service.tenant_payload(session.tenant_id)
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name} if user else None,
        "tenant": tenant,
        "csrfToken": session.csrf_token,
    }


@router.delete("/auth/devices/{device_id}")
def revoke_device(
    device_id: str,
    ctx: IdentityContext = Depends(require_identity),
    service: IdentityService = Depends(_service),
):
    try:
        service.revoke_device(ctx.user.id, device_id)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/me/memberships")
def my_memberships(
    ctx: IdentityContext = Depends(require_identity),
    service: IdentityService = Depends(_service),
):
    return {"items": service.memberships_payload(ctx.user.id)}


@router.post("/session/store")
def session_store(
    body: SessionStoreIn,
    request: Request,
    response: Response,
    ctx: IdentityContext = Depends(require_identity),
    service: IdentityService = Depends(_service),
    config: AuthConfig = Depends(_config),
):
    try:
        old_token = request.cookies.get(SESSION_COOKIE_NAME)
        session = service.create_session(
            ctx.user.id, body.tenantId, rotate_from=old_token
        )
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    _set_session_cookie(response, session.token, config)
    return {
        "sessionToken": session.token,
        "expiresAt": session.expires_at,
        "csrfToken": session.csrf_token,
    }


@router.get("/tenant")
def get_tenant(
    ctx: SessionContext = Depends(require_session),
    service: IdentityService = Depends(_service),
):
    try:
        return service.tenant_payload(ctx.tenant_id)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/tenant/members")
def list_members(
    ctx: SessionContext = Depends(require_owner),
    service: IdentityService = Depends(_service),
):
    try:
        members = service.list_tenant_members(ctx.user_id, ctx.tenant_id)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "items": [
            {
                "userId": m.user_id,
                "email": m.email,
                "name": m.name,
                "role": m.role,
                "canSell": m.can_sell,
                "canFiado": m.can_fiado,
                "canInventory": m.can_inventory,
                "active": m.active,
            }
            for m in members
        ]
    }


@router.post("/tenant/members/invite")
def create_invite(
    body: InviteCreateIn,
    ctx: SessionContext = Depends(require_owner),
    service: IdentityService = Depends(_service),
):
    try:
        token, _invite = service.create_invite(
            actor_user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            email=body.email,
            role=body.role,
            can_sell=body.canSell,
            can_fiado=body.canFiado,
            can_inventory=body.canInventory,
        )
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"token": token, "url": f"{INVITE_BASE_URL}/invite/{token}"}


@router.get("/tenant/members/invites/{token}")
def get_invite(
    token: str,
    service: IdentityService = Depends(_service),
):
    try:
        invite = service.get_invite(token)
        payload = service.invite_payload(invite)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return payload


@router.post("/tenant/members/invites/{token}/accept")
def accept_invite(
    token: str,
    ctx: IdentityContext = Depends(require_identity),
    service: IdentityService = Depends(_service),
):
    try:
        membership, tenant = service.accept_invite(token, ctx.user.id)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "userId": ctx.user.id,
        "email": ctx.user.email,
        "name": ctx.user.name,
        "tenantId": membership.tenant_id,
        "tenantName": tenant.name,
        "role": membership.role,
        "canSell": membership.can_sell,
        "canFiado": membership.can_fiado,
        "canInventory": membership.can_inventory,
        "active": membership.active,
    }


@router.patch("/tenant/members/{user_id}")
def patch_member(
    user_id: str,
    body: MemberPatchIn,
    ctx: SessionContext = Depends(require_owner),
    service: IdentityService = Depends(_service),
):
    try:
        membership = service.patch_member(
            ctx.user_id,
            ctx.tenant_id,
            user_id,
            role=body.role,
            can_sell=body.canSell,
            can_fiado=body.canFiado,
            can_inventory=body.canInventory,
            active=body.active,
        )
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "userId": membership.user_id,
        "role": membership.role,
        "canSell": membership.can_sell,
        "canFiado": membership.can_fiado,
        "canInventory": membership.can_inventory,
        "active": membership.active,
    }


@router.delete("/tenant/members/{user_id}")
def delete_member(
    user_id: str,
    ctx: SessionContext = Depends(require_owner),
    service: IdentityService = Depends(_service),
):
    try:
        membership = service.deactivate_member(ctx.user_id, ctx.tenant_id, user_id)
    except IdentityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"ok": True, "userId": membership.user_id, "active": membership.active}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _identity_error_handler(request: Request, exc: IdentityError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


def register(
    app: FastAPI,
    *,
    store: IdentityStore | None = None,
    validator: TokenValidator | None = None,
    auth_config: AuthConfig | None = None,
    now: Any = None,
) -> None:
    """Attach the identity router and its runtime state to an existing app.

    main.py is left untouched: the integrator calls this after create_app(). If
    no store is provided an in-memory store is used (SIMULADO); production
    attaches a PostgreSQL-backed IdentityStore over the frozen schema.
    """

    config = auth_config or AuthConfig.from_env()
    identity_store = store or MemoryIdentityStore()
    token_validator = validator or TokenValidator(
        config.issuers,
        clock_skew_seconds=config.clock_skew_seconds,
        jwks_ttl_seconds=config.jwks_ttl_seconds,
        now=now,
    )
    service = IdentityService(identity_store, now=now)

    app.state.identity_store = identity_store
    app.state.auth_validator = token_validator
    app.state.auth_config = config
    app.state.identity_service = service

    app.add_exception_handler(IdentityError, _identity_error_handler)
    app.include_router(router)
