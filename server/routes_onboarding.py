"""FastAPI router for onboarding (signup) and bank-account endpoints.

Registers the production contracts from
docs/produccion/04-identidad-onboarding-y-pey.md (business onboarding + CLABE)
and docs/produccion/contracts/banking.md (collection routing). It exposes a
single register(app) function so main.py stays untouched: the integrator only
calls routes_onboarding.register(app) after building the app.

Owner identity is SIMULADO here (X-Owner-Id / X-Tenant-Id headers), mirroring
the demo X-Employee-Id header, until the real OIDC session from auth_routes is
wired into these endpoints by the integrator. The tenant is never taken from
an arbitrary header without an active owner membership check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .onboarding import (
    DEFAULT_TIMEZONE,
    OnboardingError,
    OnboardingService,
    OnboardingStore,
    MemoryOnboardingStore,
    bank_account_payload,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class SignupIn(BaseModel):
    email: str
    name: str
    storeName: str
    externalSub: str | None = None
    timezone: str | None = None


class BankAccountIn(BaseModel):
    alias: str
    name: str
    clabe: str
    entity: str = "BUSINESS"


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OwnerContext:
    user_id: str
    tenant_id: str


def _service(request: Request) -> OnboardingService:
    return request.app.state.onboarding_service


def require_owner(
    request: Request,
    x_owner_id: Annotated[str | None, Header(alias="X-Owner-Id")] = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    service: OnboardingService = Depends(_service),
) -> OwnerContext:
    """SIMULADO owner identity: an active owner membership is required."""

    if not x_owner_id or not x_tenant_id:
        raise HTTPException(
            status_code=401, detail="Identidad de dueño simulada requerida"
        )
    try:
        service.require_owner(x_owner_id, x_tenant_id)
    except OnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return OwnerContext(user_id=x_owner_id, tenant_id=x_tenant_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/signup")
def signup(
    body: SignupIn,
    service: OnboardingService = Depends(_service),
):
    """Atomic signup: tenant + store + owner + owner membership, zero demo data."""

    try:
        result = service.signup(
            email=body.email,
            owner_name=body.name,
            store_name=body.storeName,
            external_sub=body.externalSub,
            timezone=body.timezone or DEFAULT_TIMEZONE,
        )
    except OnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    user = service.get_user(result.user_id)
    tenant = service.get_tenant(result.tenant_id)
    store = service.get_store(result.tenant_id)
    return {
        "user": {
            "id": result.user_id,
            "email": user.email if user else "",
            "name": user.name if user else "",
        },
        "tenant": {
            "id": result.tenant_id,
            "slug": tenant.slug if tenant else "",
            "name": tenant.name if tenant else "",
            "timezone": tenant.timezone if tenant else DEFAULT_TIMEZONE,
        },
        "store": {
            "id": result.store_id,
            "name": store.name if store else "",
        },
        "membership": {
            "role": "owner",
            "canSell": True,
            "canFiado": True,
            "canInventory": True,
            "active": True,
        },
    }


@router.post("/tenant/bank-account")
def create_bank_account(
    body: BankAccountIn,
    ctx: OwnerContext = Depends(require_owner),
    service: OnboardingService = Depends(_service),
):
    try:
        account = service.register_bank_account(
            actor_user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            alias=body.alias,
            name=body.name,
            clabe=body.clabe,
            entity=body.entity,
        )
    except OnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return bank_account_payload(account)


@router.get("/tenant/bank-accounts")
def list_bank_accounts(
    ctx: OwnerContext = Depends(require_owner),
    service: OnboardingService = Depends(_service),
):
    try:
        accounts = service.list_bank_accounts(
            actor_user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )
    except OnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"items": [bank_account_payload(a) for a in accounts]}


@router.get("/tenant/bank-account/{bank_account_id}")
def get_bank_account(
    bank_account_id: str,
    ctx: OwnerContext = Depends(require_owner),
    service: OnboardingService = Depends(_service),
):
    try:
        account = service.get_bank_account(
            actor_user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            bank_account_id=bank_account_id,
        )
    except OnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return bank_account_payload(account)


@router.post("/tenant/bank-account/{bank_account_id}/activate")
def activate_bank_account(
    bank_account_id: str,
    ctx: OwnerContext = Depends(require_owner),
    service: OnboardingService = Depends(_service),
):
    """SIMULADO: move a pending bank account to ACTIVE and notify the owner."""

    try:
        account = service.activate_bank_account(
            actor_user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            bank_account_id=bank_account_id,
        )
    except OnboardingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return bank_account_payload(account)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _onboarding_error_handler(request: Request, exc: OnboardingError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


def register(
    app: FastAPI,
    *,
    store: OnboardingStore | None = None,
    notifier: Any = None,
) -> None:
    """Attach the onboarding router and its runtime state to an existing app.

    main.py stays untouched: the integrator calls this after create_app(). If
    no store is provided an in-memory store is used (SIMULADO); production
    attaches server/onboarding.PostgresOnboardingStore over the frozen schema.
    """

    onboarding_store = store or MemoryOnboardingStore()
    service = OnboardingService(onboarding_store, notifier=notifier)

    app.state.onboarding_store = onboarding_store
    app.state.onboarding_service = service

    app.add_exception_handler(OnboardingError, _onboarding_error_handler)
    app.include_router(router)
