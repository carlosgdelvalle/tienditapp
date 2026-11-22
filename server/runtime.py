"""Production runtime factory for Abarpay (PostgreSQL + verified identity).

This module is the production entry point for the tenancy/identity vertical
slice. It is intentionally separate from server/main.py (the SQLite demo
factory), which stays untouched.

Normal isolated production entry command (not deployed yet; render.yaml still
points at the demo):

    uvicorn server.runtime:create_production_app --factory --host 0.0.0.0 --port PORT

Migrations are a separate setup/release step (the migrator principal), not a
runtime concern: apply migrations/001_schema.sql, 002_seed.sql and
003_onboarding.sql and 004_owner_phone.sql before starting the app (CI already does
this with psql). The app itself only verifies the migrated schema and the
service role and then fails closed.
"""

from __future__ import annotations

import html
import json
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Any, Iterator, Mapping

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from .auth import AuthConfig, TokenValidator, ValidatedToken
from .business_pg import register as register_business_routes
from .auth_routes import (
    IdentityContext,
    register as register_auth_routes,
    require_identity,
)
from .config import Settings
from .db_pg import SERVICE_ROLE, create_pool
from .employee_operations_pg import router as employee_operations_router
from .identity_pg import PostgresIdentityStore
from .owner_phone import PhoneAuth, PhoneSettings, register_phone
from .owner_operations_pg import router as owner_operations_router
from .onboarding import (
    DEFAULT_TIMEZONE,
    OnboardingError,
    OnboardingService,
    PostgresOnboardingStore,
)

logger = logging.getLogger("abarpay.production")

_TRUE_VALUES = {"1", "true", "yes", "si", "sí", "on"}
SERVER_ROOT = Path(__file__).resolve().parent

_TENANT_ISOLATION_TABLES = (
    "stores", "products", "sales", "sale_items", "payments",
    "inventory_movements", "fiado_customers", "fiado_entries",
    "fiado_drafts", "expenses", "day_tasks", "bank_accounts",
    "purchase_orders", "receipts", "till_shifts", "outbox_devices",
    "outbox_applied", "webhook_events", "barcodes", "store_settings",
    "support_tickets",
)


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in _TRUE_VALUES


@dataclass(frozen=True)
class ProductionRuntime:
    service_dsn: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ProductionRuntime":
        env = os.environ if env is None else env
        if (env.get("ABARPAY_RUNTIME") or "").strip().lower() != "production":
            raise RuntimeError("production runtime requires ABARPAY_RUNTIME=production")
        if _env_bool(env, "MODO_DEMO", True):
            raise RuntimeError("production runtime requires MODO_DEMO=false")
        service_dsn = (env.get("ABARPAY_PG_DSN") or "").strip()
        if not service_dsn:
            raise RuntimeError("production runtime requires ABARPAY_PG_DSN")
        return cls(service_dsn=service_dsn)


def _verify_invariants(conn: Any) -> None:
    """Fail closed when the login principal or migrated schema is unsafe.

    Runs on a fresh service connection (autocommit). It checks the login
    principal (session_user) is non-superuser and non-BYPASSRLS, that the
    NOLOGIN service role abarpay_app exists and can be assumed with SET ROLE,
    that the service role owns no tables, and that every business table has
    RLS + FORCE + a tenant_isolation policy.
    """

    with conn.cursor() as cur:
        cur.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles "
            "WHERE rolname = session_user"
        )
        login = cur.fetchone()
        if login is None or login != (False, False):
            raise RuntimeError(
                "login principal must be non-superuser and non-BYPASSRLS"
            )

        cur.execute(
            "SELECT rolsuper, rolbypassrls, rolcanlogin "
            "FROM pg_roles WHERE rolname = %s",
            (SERVICE_ROLE,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("service role is missing; apply the migrations first")
        if row != (False, False, False):
            raise RuntimeError("service role violates privileges: " + repr(row))

        cur.execute("SET ROLE " + SERVICE_ROLE)
        cur.execute("SELECT current_user")
        if cur.fetchone()[0] != SERVICE_ROLE:
            raise RuntimeError("login principal cannot assume the service role")

        cur.execute(
            "SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_roles r ON r.oid = c.relowner "
            "WHERE n.nspname = %s AND r.rolname = %s",
            ("public", SERVICE_ROLE),
        )
        if cur.fetchone()[0] != 0:
            raise RuntimeError("service role owns tables; it must not")

        cur.execute(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind = %s",
            ("public", "r"),
        )
        flags = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        cur.execute(
            "SELECT tablename, policyname FROM pg_policies "
            "WHERE schemaname = %s",
            ("public",),
        )
        policies: dict = {}
        for table, policy in cur.fetchall():
            policies.setdefault(table, set()).add(policy)

    for table in _TENANT_ISOLATION_TABLES:
        rls, forced = flags.get(table, (False, False))
        if not rls or not forced:
            raise RuntimeError(table + " lacks RLS/FORCE row security")
        if not any("tenant_isolation" in p for p in policies.get(table, set())):
            raise RuntimeError(table + " lacks a tenant_isolation policy")


class ProductionSignupIn(BaseModel):
    name: str
    storeName: str
    timezone: str | None = None


def _onboarding_service(request: Request) -> OnboardingService:
    return request.app.state.onboarding_service


signup_router = APIRouter(prefix="/api")
health_router = APIRouter(prefix="/api")
console_router = APIRouter()
invite_router = APIRouter()


@console_router.get("/console", include_in_schema=False)
def owner_console():
    page = SERVER_ROOT / "static" / "owner-console.html"
    if not page.exists():
        return JSONResponse(status_code=404, content={"detail": "Consola no disponible"})
    return FileResponse(page, media_type="text/html")


@console_router.get("/console/operations.js", include_in_schema=False)
def owner_console_operations():
    return FileResponse(SERVER_ROOT / "static" / "owner-operations.js", media_type="text/javascript")


@invite_router.get("/invite/{token}", include_in_schema=False)
def invite_page(token: str):
    """Serve the employee invitation CTA that deep-links into the app."""

    safe_token = html.escape(token)
    deep_link = "abarpay://equipo/" + safe_token
    page = "".join(
        [
            "<!doctype html>",
            '<html lang="es">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Abarpay · Invitación de empleado</title>",
            "</head>",
            "<body>",
            "<h1>Abarpay</h1>",
            "<p>Te invitaron a unirte al equipo de la tienda.</p>",
            f'<p><a href="{html.escape(deep_link, quote=True)}">Abrir Abarpay</a></p>',
            "<p>Si la app no se abre sola, toca el botón.</p>",
            "<script>window.location.href = "
            + json.dumps(deep_link)
            + ";</script>",
            "</body>",
            "</html>",
        ]
    )
    return HTMLResponse(content=page, headers={
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
    })


@signup_router.post("/signup")
def signup(
    body: ProductionSignupIn,
    ctx: IdentityContext = Depends(require_identity),
    service: OnboardingService = Depends(_onboarding_service),
) -> dict[str, Any]:
    """Atomic signup: tenant + store + owner membership from verified identity.

    The account comes from verified credentials. Staff identities cannot
    create merchant tenants.
    """

    if ctx.user.idp not in {"phone", "auth0"}:
        raise HTTPException(
            status_code=403,
            detail="Esta cuenta no puede registrar tiendas.",
        )
    try:
        result = service.signup(
            email=(ctx.token.email or "") if isinstance(ctx.token, ValidatedToken) else "",
            owner_name=body.name,
            store_name=body.storeName,
            idp=ctx.user.idp,
            external_sub=ctx.user.external_sub,
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


@health_router.get("/health")
def health(request: Request) -> JSONResponse:
    pool = request.app.state.pool
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        pg = "ok"
    except Exception:  # pragma: no cover
        pg = "error"
    payload = {
        "status": "ok" if pg == "ok" else "degraded",
        "runtime": "production",
        "pg": pg,
    }
    return JSONResponse(status_code=200 if pg == "ok" else 503, content=payload)


def _onboarding_error_handler(request: Request, exc: OnboardingError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


def create_production_app(
    settings: Settings | None = None,
    *,
    env: Mapping[str, str] | None = None,
    auth_config: AuthConfig | None = None,
    validator: TokenValidator | None = None,
    phone_settings: PhoneSettings | None = None,
) -> FastAPI:
    """Build the production app. Raises (fails closed) if preconditions fail."""

    runtime = ProductionRuntime.from_env(env)
    environ = os.environ if env is None else env
    phone_settings = phone_settings or PhoneSettings.from_env(environ)
    config = auth_config or AuthConfig.from_env(environ)
    if phone_settings:
        config = replace(config, issuers=tuple(i for i in config.issuers if i.kind != "auth0"))
    if not config.enabled and not phone_settings:
        raise RuntimeError("production runtime requires owner phone sign-in or at least one OIDC issuer")

    try:
        verify_conn = psycopg.connect(runtime.service_dsn, autocommit=True)
    except Exception as exc:
        raise RuntimeError(
            "production runtime cannot connect as the service login principal"
        ) from exc
    try:
        _verify_invariants(verify_conn)
        if phone_settings and not verify_conn.execute(
            "SELECT to_regclass('owner_auth.mobile_sessions')"
        ).fetchone()[0]:
            raise RuntimeError("apply 004_owner_phone.sql before enabling owner phone sign-in")
    finally:
        verify_conn.close()

    try:
        pool = create_pool(runtime.service_dsn, min_size=1, max_size=10)
    except Exception as exc:
        raise RuntimeError("production runtime cannot open the service pool") from exc

    try:
        identity_store = PostgresIdentityStore(pool)
        onboarding_store = PostgresOnboardingStore(pool)
        token_validator = validator or TokenValidator(
            config.issuers,
            clock_skew_seconds=config.clock_skew_seconds,
            jwks_ttl_seconds=config.jwks_ttl_seconds,
        )

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Iterator[None]:
            yield
            onboarding_store.close()
            identity_store.close()
            pool.close()

        app = FastAPI(
            title="Abarpay (production)",
            version="1.0.0",
            lifespan=lifespan,
        )
        app.state.settings = settings or Settings.from_env()
        app.state.pool = pool
        app.state.identity_store = identity_store
        app.state.onboarding_store = onboarding_store
        app.state.onboarding_service = OnboardingService(onboarding_store)

        register_auth_routes(
            app,
            store=identity_store,
            validator=token_validator,
            auth_config=config,
        )
        if phone_settings:
            register_phone(app, PhoneAuth(pool, phone_settings))
        register_business_routes(app, pool)
        app.include_router(owner_operations_router)
        app.include_router(employee_operations_router)
        app.add_exception_handler(OnboardingError, _onboarding_error_handler)
        app.include_router(signup_router)
        app.include_router(health_router)
        app.include_router(console_router)
        app.include_router(invite_router)
        logger.info("production runtime initialized: PostgreSQL verified, RLS enforced")
        return app
    except Exception:
        pool.close()
        raise
