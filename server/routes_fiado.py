"""FastAPI router for extended fiado (M4): limits, due dates, override, repayment, reminders, export.

register(app) installs the router under /api. Like server/routes_till.py and
server/routes_purchasing.py, server/main.py is intentionally left untouched:
the integrator wires the one-line register_fiado_routes(app) call in create_app.

Identity is SIMULADO via the X-Employee-Id header (same convention as the v2
gates in main.py): the owner can do everything, an employee with can_fiado can
charge and register repayments, and only the owner can raise a credit limit,
authorize an override, list/send reminders, or export. No header keeps the open
v1 behavior (console and scripts).

Endpoints:
  PATCH  /api/fiado/customers/{id}              limits / due days / consent / active
  POST   /api/fiado/customers/{id}/charges      validated charge (limit enforced)
  POST   /api/fiado/overrides                   owner-authorized charge beyond limit
  POST   /api/fiado/customers/{id}/repayments   partial installment or settlement
  GET    /api/fiado/reminders                   overdue/upcoming (consent only)
  POST   /api/fiado/reminders/send              SIMULADO send + trace
  GET    /api/fiado/export                      CSV ledger, no PII (Gratis plan)
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel

from .db import STORE_ID, connect, write_transaction
from .fiado import (
    FiadoError,
    create_charge,
    create_override,
    create_repayment,
    ensure_fiado_schema,
    export_csv,
    list_reminders,
    patch_customer,
    send_reminders,
)

OWNER_ONLY_DETAIL = "Solo el dueño puede hacer esto"
FIADO_FORBIDDEN_DETAIL = "Tu perfil no puede registrar abonos"
INVALID_EMPLOYEE_DETAIL = "Empleado no válido o inactivo"

_FIADO_ERROR_STATUS = {
    "customer_not_found": 404,
    "entry_not_found": 404,
    "override_not_found": 404,
    "customer_inactive": 409,
    "credit_limit_exceeded": 409,
    "overpayment": 409,
    "invalid_amount": 400,
    "invalid_due_at": 400,
    "invalid_credit_limit": 400,
    "invalid_due_days": 400,
    "override_requires_reason": 400,
}


class CustomerPatchIn(BaseModel):
    creditLimitCents: int | None = None
    dueDays: int | None = None
    active: bool | None = None
    remindersConsent: bool | None = None


class ChargeIn(BaseModel):
    amountCents: int
    dueAt: float | None = None
    note: str | None = None


class OverrideIn(BaseModel):
    customerId: int
    amountCents: int
    reason: str
    dueAt: float | None = None
    note: str | None = None


class RepaymentIn(BaseModel):
    amountCents: int
    note: str | None = None


def _raise(exc: FiadoError) -> None:
    status = _FIADO_ERROR_STATUS.get(exc.code, 400)
    detail: dict = {"code": exc.code.upper(), "message": exc.detail}
    detail.update(exc.payload)
    raise HTTPException(status_code=status, detail=detail)


def register(app) -> None:
    router = APIRouter(prefix="/api")

    def get_fiado_db(request: Request) -> Iterator[sqlite3.Connection]:
        conn = connect(request.app.state.settings.db_path)
        try:
            ensure_fiado_schema(conn)
            yield conn
        finally:
            conn.close()

    def _employee_row(
        conn: sqlite3.Connection, employee_id: int | None
    ) -> sqlite3.Row | None:
        if employee_id is None:
            return None
        row = conn.execute(
            "SELECT * FROM employees WHERE id = ? AND store_id = ? AND active = 1",
            (employee_id, STORE_ID),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=403, detail=INVALID_EMPLOYEE_DETAIL)
        return row

    def _require_fiado(
        conn: sqlite3.Connection, employee_id: int | None
    ) -> sqlite3.Row | None:
        employee = _employee_row(conn, employee_id)
        if (
            employee is not None
            and employee["role"] != "owner"
            and not employee["can_fiado"]
        ):
            raise HTTPException(status_code=403, detail=FIADO_FORBIDDEN_DETAIL)
        return employee

    def _require_owner(
        conn: sqlite3.Connection, employee_id: int | None
    ) -> sqlite3.Row | None:
        employee = _employee_row(conn, employee_id)
        if employee is not None and employee["role"] != "owner":
            raise HTTPException(status_code=403, detail=OWNER_ONLY_DETAIL)
        return employee

    # Customer limits / due days / consent / active -------------------------

    @router.patch("/fiado/customers/{customer_id}")
    def fiado_customer_patch(
        customer_id: int,
        body: CustomerPatchIn,
        conn: sqlite3.Connection = Depends(get_fiado_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            employee = _require_fiado(conn, x_employee_id)
            provided = getattr(body, "model_fields_set", set())
            # Consent is captured at the point of sale, so an employee with
            # can_fiado may flip remindersConsent; the money/eligibility fields
            # (limit, due days, active) stay owner-only.
            if employee is not None and employee["role"] != "owner":
                if provided & {"creditLimitCents", "dueDays", "active"}:
                    raise HTTPException(status_code=403, detail=OWNER_ONLY_DETAIL)
            kwargs: dict = {}
            if "creditLimitCents" in provided:
                kwargs["credit_limit_cents"] = body.creditLimitCents
            if "dueDays" in provided:
                kwargs["due_days"] = body.dueDays
            if "active" in provided:
                kwargs["active"] = body.active
            if "remindersConsent" in provided:
                kwargs["reminders_consent"] = body.remindersConsent
            try:
                return patch_customer(conn, customer_id=customer_id, **kwargs)
            except FiadoError as exc:
                _raise(exc)

    # Charges with the credit-limit check -----------------------------------

    @router.post("/fiado/customers/{customer_id}/charges")
    def fiado_charge(
        customer_id: int,
        body: ChargeIn,
        conn: sqlite3.Connection = Depends(get_fiado_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            employee = _require_fiado(conn, x_employee_id)
            try:
                return create_charge(
                    conn,
                    customer_id=customer_id,
                    amount_cents=body.amountCents,
                    due_at=body.dueAt,
                    note=body.note,
                    employee_id=employee["id"] if employee is not None else None,
                )
            except FiadoError as exc:
                _raise(exc)

    # Owner-authorized override beyond the limit ----------------------------

    @router.post("/fiado/overrides")
    def fiado_override(
        body: OverrideIn,
        conn: sqlite3.Connection = Depends(get_fiado_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            owner = _require_owner(conn, x_employee_id)
            try:
                return create_override(
                    conn,
                    customer_id=body.customerId,
                    amount_cents=body.amountCents,
                    reason=body.reason,
                    due_at=body.dueAt,
                    note=body.note,
                    employee_id=owner["id"] if owner is not None else None,
                )
            except FiadoError as exc:
                _raise(exc)

    # Repayment (partial installment or full settlement) --------------------

    @router.post("/fiado/customers/{customer_id}/repayments")
    def fiado_repayment(
        customer_id: int,
        body: RepaymentIn,
        conn: sqlite3.Connection = Depends(get_fiado_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            employee = _require_fiado(conn, x_employee_id)
            try:
                return create_repayment(
                    conn,
                    customer_id=customer_id,
                    amount_cents=body.amountCents,
                    note=body.note,
                    employee_id=employee["id"] if employee is not None else None,
                )
            except FiadoError as exc:
                _raise(exc)

    # Reminders (opt-in, SIMULADO) ------------------------------------------

    @router.get("/fiado/reminders")
    def fiado_reminders(
        conn: sqlite3.Connection = Depends(get_fiado_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
        dueWithinDays: int = Query(default=7),
    ):
        _require_owner(conn, x_employee_id)
        return list_reminders(conn, due_within_days=dueWithinDays)

    @router.post("/fiado/reminders/send")
    def fiado_reminders_send(
        conn: sqlite3.Connection = Depends(get_fiado_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
        dueWithinDays: int = Query(default=7),
    ):
        _require_owner(conn, x_employee_id)
        with write_transaction(conn):
            return send_reminders(conn, due_within_days=dueWithinDays)

    # CSV export (Gratis plan, no PII) --------------------------------------

    @router.get("/fiado/export")
    def fiado_export(
        conn: sqlite3.Connection = Depends(get_fiado_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner(conn, x_employee_id)
        csv_text = export_csv(conn)
        return Response(
            content=csv_text.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="fiado.csv"'},
        )

    app.include_router(router)
