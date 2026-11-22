"""FastAPI router for the SaaS platform console (SIMULADO).

Serves the dedicated SaaS platform console at /platform, separate from the
merchant's /console and /api/console. It exposes a single register(app) so
server/main.py stays untouched: the coordinator wires one line,
routes_platform.register(app), after building the app (next to the other
register_* calls in create_app).

Scope (docs/produccion/07-consola-saas-y-datos.md and d3-comercial.md):

* Four sections - Salud (operations/support), Crecimiento (growth/marketing),
  Ingresos (revenue/finance), Datos (community/partners/analyst).
* Access separation on the server: every section endpoint requires a
  SIMULADO 'X-Platform-Role' header and rejects roles that cannot see the
  section (401 when missing, 403 when insufficient). Hiding a button only
  improves presentation; the server still authorizes.
* Every response is labeled SIMULADO ('simulado: true') and backed by the
  28-day fixture snapshot from d3-comercial.md. There are no real aggregate
  data sources yet: 'lastCalcAt' is null and the Datos section's publishable
  cells are suppressed.

Endpoints:

  GET /platform                     serve platform.html
  GET /platform/                    redirect to /platform
  GET /api/platform/meta            section catalog (roles) - no auth
  GET /api/platform/{section}       role-gated SIMULADO fixture
                                    (?fixture=empty returns the empty state)

Roles (SIMULADO identity, X-Platform-Role header):
  staff       SaaS staff - every section (demo default)
  operations  Salud
  marketing   Crecimiento
  finance     Ingresos
  analyst     Datos
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from .platform_auth import (
    COOKIE_NAME,
    INVITE_TTL_SECONDS,
    PlatformAuth,
    PlatformAuthError,
    ROLE_LABELS,
    ROLES,
    SESSION_TTL_SECONDS,
    SUPER_ROLES,
    Staff,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# ---------------------------------------------------------------------------
# Section catalog and role mapping
# ---------------------------------------------------------------------------

SECTIONS: list[dict[str, str]] = [
    {
        "id": "salud",
        "title": "Salud",
        "subtitle": "Operaciones y soporte",
        "role": "operations",
        "summary": (
            "Prioriza registros bancarios atrasados, errores de correo, "
            "registros sin sincronizar y conciliaciones pendientes."
        ),
    },
    {
        "id": "crecimiento",
        "title": "Crecimiento",
        "subtitle": "Marketing y embudo",
        "role": "marketing",
        "summary": (
            "Embudo por campaña, activación, retención y costo de adquisición."
        ),
    },
    {
        "id": "ingresos",
        "title": "Ingresos",
        "subtitle": "Ingreso SaaS y finanzas",
        "role": "finance",
        "summary": (
            "Libro de cargos y reembolsos de Control; interés de Formalización "
            "y dossier sin ingreso hasta el evento financiero."
        ),
    },
    {
        "id": "datos",
        "title": "Datos",
        "subtitle": "Comunidad, socios y analista",
        "role": "analyst",
        "summary": (
            "Viabilidad del producto de datos, supresión y celdas publicables."
        ),
    },
]

SECTION_BY_ID = {section["id"]: section for section in SECTIONS}

# Owners and administrators may open every section; a functional role may open
# only its own.
_SUPER_ROLES = {"owner", "admin"}


def _role_allows(role: str, section_role: str) -> bool:
    return role in _SUPER_ROLES or role == section_role


# ---------------------------------------------------------------------------
# SIMULADO fixtures (28-day snapshot, docs/produccion/d3-comercial.md)
# ---------------------------------------------------------------------------

# Amounts are integer MXN cents. Counts/percentages are plain numbers.
_FIXTURES: dict[str, dict[str, Any]] = {
    "salud": {
        "blocks": [
            {
                "type": "metric",
                "label": "Conciliación CoDi pendiente",
                "value": 200000,  # MXN 2,000 = 20,000 etiquetado - 18,000 confirmado
                "kind": "moneyCents",
                "note": "MXN 20,000 etiquetado CoDi - MXN 18,000 confirmado por pey",
            },
            {
                "type": "metric",
                "label": "% confirmado por monto CoDi",
                "value": 90,
                "kind": "percent",
                "note": "18,000 / 20,000 (solo dentro del subconjunto CoDi)",
            },
            {
                "type": "table",
                "columns": ["Prioridad", "Código de causa", "Conteo", "Antigüedad", "Siguiente acción"],
                "rows": [
                    ["Alta", "coDi_pending", "MXN 2,000", "2 días", "Conciliar contra el QR del cobro"],
                    ["Media", "bank_late", "—", "—", "Datos bancarios enmascarados"],
                    ["Media", "email_failure", "—", "—", "Reintentar envío y registrar causa"],
                    ["Baja", "register_unsynced", "—", "—", "Sincronizar registro al volver la señal"],
                ],
            },
            {
                "type": "note",
                "level": "info",
                "text": (
                    "Los datos bancarios se enmascaran en esta vista. El acceso "
                    "a un incidente por tienda requiere razón y trazabilidad."
                ),
            },
        ],
    },
    "crecimiento": {
        "blocks": [
            {
                "type": "metric",
                "label": "Leads únicos (A + B)",
                "value": 130,
                "kind": "count",
                "note": "100 + 40 - 10 leads compartidos",
            },
            {
                "type": "funnel",
                "campaigns": [
                    {
                        "name": "A",
                        "stages": [
                            {"label": "Leads", "value": 100},
                            {"label": "CTA", "value": 30},
                            {"label": "Registro", "value": 12},
                            {"label": "Pago", "value": 4},
                        ],
                    },
                    {
                        "name": "B",
                        "stages": [
                            {"label": "Leads", "value": 40},
                            {"label": "CTA", "value": 20},
                            {"label": "Registro", "value": 14},
                            {"label": "Pago", "value": 3},
                        ],
                    },
                ],
            },
            {
                "type": "table",
                "columns": ["Campaña", "Leads", "Pagadores", "Tasa lead a pago bruta"],
                "rows": [
                    ["A", "100", "4", "4.0%"],
                    ["B", "40", "3", "7.5%"],
                ],
            },
            {
                "type": "note",
                "level": "warn",
                "text": (
                    "Sin ganador causal: muestras chicas, solape de 10 leads sin "
                    "resolver y reembolsos sin canal no asignados a A ni a B."
                ),
            },
            {
                "type": "metric",
                "label": "CAC",
                "value": None,
                "kind": "text",
                "note": "Sin datos suficientes (sin gasto completo ni atribución confiable)",
            },
        ],
    },
    "ingresos": {
        "blocks": [
            {
                "type": "metric",
                "label": "Control bruto",
                "value": 104300,  # 7 x MXN 149
                "kind": "moneyCents",
                "note": "7 cobros x MXN 149",
            },
            {
                "type": "metric",
                "label": "Reembolsos liquidados",
                "value": 29800,  # 2 x MXN 149
                "kind": "moneyCents",
                "note": "2 reembolsos completos x MXN 149",
            },
            {
                "type": "metric",
                "label": "Control neto cobrado",
                "value": 74500,  # 1,043 - 298
                "kind": "moneyCents",
                "note": "Bruto 1,043 - reembolsos 298",
            },
            {
                "type": "metric",
                "label": "Formalización",
                "value": 0,
                "kind": "moneyCents",
                "note": "3 expresiones de interés no son ingreso",
            },
            {
                "type": "metric",
                "label": "Dossier financiero",
                "value": 0,
                "kind": "moneyCents",
                "note": "2 solicitudes ficticias, sin destinatario ni cargo",
            },
            {
                "type": "note",
                "level": "info",
                "text": (
                    "No se calcula rentabilidad sin costos (soporte, "
                    "adquisición). Un reembolso no prueba cancelación."
                ),
            },
        ],
    },
    "datos": {
        "blocks": [
            {
                "type": "empty",
                "message": (
                    "Sin celdas publicables. No hay fuentes de datos agregadas "
                    "reales todavía; ambas salidas externas quedan suprimidas."
                ),
            },
            {
                "type": "table",
                "columns": ["Concepto", "Valor"],
                "rows": [
                    ["Tiendas invitadas / aceptadas", "20 / 8"],
                    ["Zonas observadas", "6 y 2"],
                    ["Contribución máxima de una tienda", "70% de una zona"],
                ],
            },
            {
                "type": "note",
                "level": "warn",
                "text": (
                    "Suprimidas ambas salidas externas, incluidos los porcentajes "
                    "derivados (al menos 10 por celda y contribución de 25% como "
                    "máximo; se revisa la concentración aun cumpliendo el umbral)."
                ),
            },
            {
                "type": "table",
                "columns": ["Agotados", "Antes", "Después"],
                "rows": [
                    ["Tasa", "15 / 100 = 15%", "9 / 70 = 12.86%"],
                    ["Denominador (ítem-días)", "100", "70"],
                ],
            },
            {
                "type": "note",
                "level": "info",
                "text": (
                    "No se infiere mejora causal: la cobertura cayó de 100 a 70 "
                    "ítem-días observados. Se muestran ambos denominadores."
                ),
            },
        ],
    },
}


def _envelope(section_id: str, empty: bool) -> dict[str, Any]:
    section = SECTION_BY_ID[section_id]
    payload: dict[str, Any] = {
        "simulado": True,
        "section": section_id,
        "title": section["title"],
        "subtitle": section["subtitle"],
        "role": section["role"],
        "empty": empty,
        "emptyMessage": None,
        "lastCalcAt": None,  # no real aggregate data source yet
        "delayed": False,
        "blocks": [] if empty else _FIXTURES[section_id]["blocks"],
    }
    if empty:
        payload["emptyMessage"] = (
            "Sin datos para esta sección (SIMULADO). "
            "No hay fuentes de datos agregadas reales todavía."
        )
    return payload


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class LoginIn(BaseModel):
    email: str
    password: str


class SetupIn(BaseModel):
    name: str = ""
    email: str
    password: str


class PasswordIn(BaseModel):
    currentPassword: str
    newPassword: str


class InviteIn(BaseModel):
    email: str
    name: str = ""
    role: str


class AcceptInviteIn(BaseModel):
    name: str = ""
    password: str


class StaffPatchIn(BaseModel):
    role: str | None = None
    active: bool | None = None


# ---------------------------------------------------------------------------
# Cookie + session helpers
# ---------------------------------------------------------------------------


def _request_is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return request.url.scheme == "https" or forwarded == "https"


def _set_session_cookie(
    response: Response, request: Request, token: str
) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_request_is_https(request),
        samesite="lax",
        path="/",
    )


def _require_staff(
    request: Request, store: PlatformAuth, roles: set[str] | None = None
) -> Staff:
    staff = store.session_staff(request.cookies.get(COOKIE_NAME))
    if staff is None:
        raise HTTPException(
            status_code=401,
            detail="Inicia sesión con tu cuenta del equipo Abarpay.",
        )
    if roles is not None and staff.role not in roles:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_access",
                "message": "Tu cuenta no tiene permiso para esta sección.",
                "requiredRole": sorted(roles),
            },
        )
    return staff


# ---------------------------------------------------------------------------
# register(app)
# ---------------------------------------------------------------------------


def register(app: Any) -> None:
    settings = getattr(app.state, "settings", None)
    db_path = Path(
        getattr(settings, "db_path", None) or Path("server") / "data" / "abarpay.db"
    )
    store = PlatformAuth(db_path)
    store.ensure_schema()
    store.bootstrap(os.environ)
    app.state.platform_auth = store

    api = APIRouter(prefix="/api/platform")

    def auth_error(error: PlatformAuthError) -> HTTPException:
        return HTTPException(status_code=error.status_code, detail=str(error))

    # -- authentication -------------------------------------------------
    @api.get("/auth/me")
    def auth_me(request: Request) -> JSONResponse:
        staff = store.session_staff(request.cookies.get(COOKIE_NAME))
        staff_count = store.count_staff()
        return JSONResponse(
            content={
                "authenticated": staff is not None,
                "configured": staff_count > 0,
                "setupOpen": staff_count == 0
                and os.environ.get("ABARPAY_PLATFORM_SETUP_OPEN", "").strip() == "1",
                "staff": staff.payload() if staff else None,
            }
        )

    @api.post("/auth/setup", status_code=201)
    def auth_setup(body: SetupIn, request: Request) -> JSONResponse:
        if os.environ.get("ABARPAY_PLATFORM_SETUP_OPEN", "").strip() != "1":
            raise HTTPException(
                status_code=403,
                detail="El alta inicial está cerrada. Pide una invitación al propietario.",
            )
        try:
            staff = store.create_owner(
                email=body.email, name=body.name, password=body.password
            )
        except PlatformAuthError as error:
            raise auth_error(error) from error
        token = store.create_session(staff.id)
        payload = JSONResponse(
            status_code=201, content={"staff": staff.payload()}
        )
        _set_session_cookie(payload, request, token)
        return payload

    @api.post("/auth/login")
    def auth_login(body: LoginIn, request: Request) -> JSONResponse:
        client_ip = (request.client.host if request.client else "") or ""
        try:
            staff = store.authenticate(
                body.email, body.password, client_ip=client_ip
            )
        except PlatformAuthError as error:
            raise auth_error(error) from error
        if staff is None:
            raise HTTPException(
                status_code=401, detail="Correo o contraseña incorrectos."
            )
        token = store.create_session(staff.id)
        payload = JSONResponse(content={"staff": staff.payload()})
        _set_session_cookie(payload, request, token)
        return payload

    @api.post("/auth/logout", status_code=204)
    def auth_logout(request: Request) -> Response:
        store.revoke_session(request.cookies.get(COOKIE_NAME))
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(
            COOKIE_NAME, httponly=True, samesite="lax", path="/"
        )
        return response

    @api.post("/auth/password")
    def auth_password(body: PasswordIn, request: Request) -> JSONResponse:
        staff = _require_staff(request, store)
        token = request.cookies.get(COOKIE_NAME)
        try:
            store.change_password(
                staff.id,
                body.currentPassword,
                body.newPassword,
                keep_token=token,
            )
        except PlatformAuthError as error:
            raise auth_error(error) from error
        updated = store.get_staff(staff.id)
        return JSONResponse(
            content={"staff": updated.payload() if updated else staff.payload()}
        )

    # -- team -----------------------------------------------------------
    @api.get("/team")
    def team_list(request: Request) -> JSONResponse:
        _require_staff(request, store, set(SUPER_ROLES))
        return JSONResponse(
            content={
                "items": store.list_staff(),
                "roles": [
                    {"id": role, "label": ROLE_LABELS[role]} for role in ROLES
                ],
            }
        )

    @api.post("/team/invites", status_code=201)
    def team_invite(body: InviteIn, request: Request) -> JSONResponse:
        actor = _require_staff(request, store, set(SUPER_ROLES))
        try:
            token, expires = store.invite(
                email=body.email, name=body.name, role=body.role, actor=actor
            )
        except PlatformAuthError as error:
            raise auth_error(error) from error
        return JSONResponse(
            status_code=201,
            content={
                "inviteUrl": "/platform/invite/" + token,
                "expiresAt": expires.isoformat(timespec="seconds"),
            },
        )

    @api.get("/team/invites/{token}")
    def team_invite_preview(token: str) -> JSONResponse:
        try:
            return JSONResponse(content=store.invite_preview(token))
        except PlatformAuthError as error:
            raise auth_error(error) from error

    @api.post("/team/invites/{token}")
    def team_invite_accept(
        token: str, body: AcceptInviteIn, request: Request
    ) -> JSONResponse:
        try:
            staff = store.accept_invite(
                token, name=body.name, password=body.password
            )
        except PlatformAuthError as error:
            raise auth_error(error) from error
        session = store.create_session(staff.id)
        payload = JSONResponse(content={"staff": staff.payload()})
        _set_session_cookie(payload, request, session)
        return payload

    @api.patch("/team/{staff_id}")
    def team_patch(
        staff_id: str, body: StaffPatchIn, request: Request
    ) -> JSONResponse:
        actor = _require_staff(request, store, set(SUPER_ROLES))
        try:
            staff = store.patch_staff(
                staff_id, actor=actor, role=body.role, active=body.active
            )
        except PlatformAuthError as error:
            raise auth_error(error) from error
        return JSONResponse(content={"staff": staff.payload()})

    # -- catalog and sections -------------------------------------------
    @api.get("/meta")
    def platform_meta() -> JSONResponse:
        return JSONResponse(
            content={"simulado": True, "sections": SECTIONS, "roles": list(ROLES)}
        )

    @api.get("/{section_id}")
    def platform_section(
        section_id: str, request: Request, fixture: str = "data"
    ) -> JSONResponse:
        if section_id not in SECTION_BY_ID:
            raise HTTPException(status_code=404, detail="Sección no encontrada")
        section = SECTION_BY_ID[section_id]
        staff = _require_staff(request, store)
        if not _role_allows(staff.role, section["role"]):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "insufficient_access",
                    "message": "Tu cuenta no tiene permiso para esta sección.",
                    "providedRole": staff.role,
                    "requiredRole": section["role"],
                },
            )
        empty = fixture.strip().lower() == "empty"
        return JSONResponse(content=_envelope(section_id, empty))

    # -- pages -----------------------------------------------------------
    @app.get("/platform", include_in_schema=False)
    def platform_page(request: Request) -> FileResponse:
        return _serve_page(request)

    @app.get("/platform/", include_in_schema=False)
    def platform_page_slash() -> RedirectResponse:
        return RedirectResponse(url="/platform")

    @app.get("/platform/invite/{token}", include_in_schema=False)
    def platform_invite_page(token: str, request: Request) -> FileResponse:
        return _serve_page(request)

    app.include_router(api)


def _serve_page(request: Request) -> FileResponse:
    static_dir = Path(
        getattr(getattr(request.app.state, "settings", None), "static_dir", None)
        or STATIC_DIR
    )
    page = static_dir / "platform.html"
    if not page.exists():
        raise HTTPException(status_code=500, detail="Consola de plataforma no instalada")
    return FileResponse(
        page, media_type="text/html", headers={"Cache-Control": "no-store"}
    )
