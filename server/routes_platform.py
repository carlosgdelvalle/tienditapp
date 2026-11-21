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

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

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

# SaaS staff may open every section; a functional role may open only its own.
_SUPER_ROLES = {"staff"}


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
# register(app)
# ---------------------------------------------------------------------------


def register(app: Any) -> None:
    api = APIRouter(prefix="/api/platform")

    @api.get("/meta")
    def platform_meta() -> JSONResponse:
        return JSONResponse(
            content={
                "simulado": True,
                "sections": SECTIONS,
                "roles": ["staff", "operations", "marketing", "finance", "analyst"],
            }
        )

    @api.get("/{section_id}")
    def platform_section(
        section_id: str,
        request: Request,
        fixture: str = "data",
        x_platform_role: str | None = Header(default=None, alias="X-Platform-Role"),
    ) -> JSONResponse:
        if section_id not in SECTION_BY_ID:
            raise HTTPException(status_code=404, detail="Sección no encontrada")
        section = SECTION_BY_ID[section_id]

        # Access separation is enforced on the server, never only in the UI.
        if not x_platform_role:
            raise HTTPException(
                status_code=401,
                detail="Falta rol de plataforma (header X-Platform-Role)",
            )
        if not _role_allows(x_platform_role.strip().lower(), section["role"]):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "insufficient_access",
                    "message": "Acceso insuficiente para esta sección",
                    "providedRole": x_platform_role,
                    "requiredRole": section["role"],
                },
            )

        empty = fixture.strip().lower() == "empty"
        return JSONResponse(content=_envelope(section_id, empty))

    @app.get("/platform", include_in_schema=False)
    def platform_page(request: Request) -> FileResponse:
        static_dir = Path(
            getattr(getattr(request.app.state, "settings", None), "static_dir", None)
            or STATIC_DIR
        )
        page = static_dir / "platform.html"
        if not page.exists():
            raise HTTPException(
                status_code=500, detail="Consola de plataforma no instalada"
            )
        return FileResponse(
            page,
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/platform/", include_in_schema=False)
    def platform_page_slash() -> RedirectResponse:
        return RedirectResponse(url="/platform")

    app.include_router(api)
