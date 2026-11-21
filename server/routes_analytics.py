"""FastAPI router for analytics and Control revenue (M6).

register(app) installs the router under /api/analytics. Like routes_platform.py
and routes_purchasing.py, server/main.py is left untouched for the coordinator
to wire the one-line register_analytics_routes(app) call.

Access separation is enforced on the server, never only in the UI, via the
X-Platform-Role header (SIMULADO SaaS identity). Roles:

  analytics  - gross merchandise margin (aggregates + coverage)
  finance    - Control subscription ledger (manual bill / refund)
  support    - CoDi reconciliation (pending, masked bank data)
  staff      - every endpoint (super-role)

Missing role -> 401; insufficient role -> 403.

Endpoints:
  GET  /api/analytics/meta
  GET  /api/analytics/margin
  GET  /api/analytics/reconciliation   (?source=simulado|live)
  GET  /api/analytics/subscriptions
  POST /api/analytics/subscriptions
  POST /api/analytics/subscriptions/{id}/refund
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from . import analytics
from .db import STORE_ID, connect, write_transaction


class BillSubscriptionIn(BaseModel):
    plan: str = "control"
    campaign: str | None = None
    owner: str | None = None
    amountCents: int | None = None
    periodStart: float | None = None
    periodEnd: float | None = None
    receiptRef: str | None = None


class RefundIn(BaseModel):
    chargeId: int
    amountCents: int | None = None
    reason: str | None = None


def _role(x_platform_role: str | None) -> str:
    if not x_platform_role:
        raise HTTPException(
            status_code=401, detail="Falta rol de plataforma (header X-Platform-Role)"
        )
    return (x_platform_role or "").strip().lower()


def _require_role(x_platform_role: str | None, *allowed: str) -> str:
    role = _role(x_platform_role)
    if role in analytics.SUPER_ROLES:
        return role
    if role not in allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_access",
                "message": "Acceso insuficiente para este recurso",
                "providedRole": role,
                "requiredRoles": list(allowed),
            },
        )
    return role


def register(app) -> None:
    router = APIRouter(prefix="/api/analytics")

    def get_analytics_db(request: Request) -> Iterator[sqlite3.Connection]:
        conn = connect(request.app.state.settings.db_path)
        try:
            analytics.ensure_analytics_schema(conn)
            yield conn
        finally:
            conn.close()

    @router.get("/meta")
    def meta() -> dict:
        return {
            "simulado": True,
            "roles": ["staff", analytics.ROLE_ANALYTICS, analytics.ROLE_FINANCE, analytics.ROLE_SUPPORT],
            "sections": [
                {
                    "id": "margin",
                    "role": analytics.ROLE_ANALYTICS,
                    "title": "Margen bruto de mercancía",
                    "summary": "Ventas netas cobradas menos costo atribuible, con cobertura.",
                },
                {
                    "id": "reconciliation",
                    "role": analytics.ROLE_SUPPORT,
                    "title": "Conciliación CoDi",
                    "summary": "Registrado / etiquetado CoDi / confirmado por pey (series separadas).",
                },
                {
                    "id": "subscriptions",
                    "role": analytics.ROLE_FINANCE,
                    "title": "Ingreso Control (suscripción)",
                    "summary": "Cobros manuales MXN 149 y reembolsos liquidados.",
                },
            ],
        }

    @router.get("/margin")
    def margin(
        store_id: str = STORE_ID,
        conn: sqlite3.Connection = Depends(get_analytics_db),
        x_platform_role: Annotated[str | None, Header(alias="X-Platform-Role")] = None,
    ) -> dict:
        _require_role(x_platform_role, analytics.ROLE_ANALYTICS)
        return analytics.gross_margin_report(conn, store_id)

    @router.get("/reconciliation")
    def reconciliation(
        source: str = "simulado",
        conn: sqlite3.Connection = Depends(get_analytics_db),
        x_platform_role: Annotated[str | None, Header(alias="X-Platform-Role")] = None,
    ) -> dict:
        _require_role(x_platform_role, analytics.ROLE_SUPPORT)
        if source.strip().lower() == "live":
            return analytics.sales_reconciliation(conn, STORE_ID)
        return analytics.simulado_reconciliation()

    @router.get("/subscriptions")
    def subscriptions_list(
        store_id: str = STORE_ID,
        conn: sqlite3.Connection = Depends(get_analytics_db),
        x_platform_role: Annotated[str | None, Header(alias="X-Platform-Role")] = None,
    ) -> dict:
        _require_role(x_platform_role, analytics.ROLE_FINANCE)
        return {
            "items": analytics.list_subscriptions(conn, store_id),
            "revenue": analytics.control_revenue(conn, store_id),
        }

    @router.post("/subscriptions")
    def subscriptions_bill(
        body: BillSubscriptionIn,
        store_id: str = STORE_ID,
        conn: sqlite3.Connection = Depends(get_analytics_db),
        x_platform_role: Annotated[str | None, Header(alias="X-Platform-Role")] = None,
    ) -> dict:
        _require_role(x_platform_role, analytics.ROLE_FINANCE)
        if body.plan != "control":
            raise HTTPException(status_code=400, detail="Solo se factura el plan Control")
        with write_transaction(conn):
            return analytics.bill_control_subscription(
                conn,
                store_id=store_id,
                campaign=body.campaign,
                owner=body.owner,
                amount_cents=analytics.CONTROL_PRICE_CENTS
                if body.amountCents is None
                else body.amountCents,
                period_start=body.periodStart,
                period_end=body.periodEnd,
                receipt_ref=body.receiptRef,
            )

    @router.post("/subscriptions/{subscription_id}/refund")
    def subscriptions_refund(
        subscription_id: str,
        body: RefundIn,
        store_id: str = STORE_ID,
        conn: sqlite3.Connection = Depends(get_analytics_db),
        x_platform_role: Annotated[str | None, Header(alias="X-Platform-Role")] = None,
    ) -> dict:
        _require_role(x_platform_role, analytics.ROLE_FINANCE)
        with write_transaction(conn):
            try:
                return analytics.refund_subscription_charge(
                    conn,
                    subscription_id=subscription_id,
                    charge_id=body.chargeId,
                    amount_cents=body.amountCents or analytics.CONTROL_PRICE_CENTS,
                    store_id=store_id,
                    reason=body.reason,
                )
            except analytics.AnalyticsError as exc:
                raise HTTPException(status_code=404, detail=exc.detail)

    app.include_router(router)
