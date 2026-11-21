"""FastAPI router for the till (cash register) lifecycle.

register(app) installs the router under /api/till. Like server/sync_routes.py,
server/main.py is intentionally left untouched; the coordinator wires the
one-line register(app) call. The router reuses the SQLite connection helpers
from server.db and the till core from server.till.

Endpoints:
  POST /api/till/open            open a shift with its opening float
  POST /api/till/close           blind count + handover (computes variance)
  POST /api/till/{id}/accept     owner acceptance or observed discrepancy
  GET  /api/till/current         open shift with expected/counted/variance
  POST /api/till/audit-variance  inventory audit variance (inventory_movements)
"""

from __future__ import annotations

import sqlite3
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .db import STORE_ID, connect, write_transaction
from .till import (
    TillError,
    accept_shift,
    close_shift,
    current_shift,
    ensure_till_schema,
    open_shift,
    record_audit_variance,
    _shift_payload,
)


_TILL_ERROR_STATUS = {
    "shift_open": 409,
    "shift_not_found": 404,
    "shift_not_closed": 409,
    "invalid_float": 400,
    "invalid_count": 400,
    "product_not_found": 404,
    "unlimited_stock": 400,
}


class TillOpenIn(BaseModel):
    openingFloatCents: int
    employeeId: int


class TillCloseIn(BaseModel):
    countedCents: int
    employeeId: int
    # Optional for doc compatibility; a retry re-sends it for idempotency.
    shiftId: int | None = None


class TillAcceptIn(BaseModel):
    employeeId: int
    reason: str | None = None


class AuditVarianceIn(BaseModel):
    productId: int
    countedMilli: int
    employeeId: int


def _raise(exc: TillError) -> None:
    raise HTTPException(
        status_code=_TILL_ERROR_STATUS.get(exc.code, 400), detail=exc.detail
    )


def register(app) -> None:
    router = APIRouter(prefix="/api/till")

    def get_till_db(request: Request) -> Iterator[sqlite3.Connection]:
        conn = connect(request.app.state.settings.db_path)
        try:
            ensure_till_schema(conn)
            yield conn
        finally:
            conn.close()

    def _require_employee(
        conn: sqlite3.Connection, employee_id: int
    ) -> None:
        row = conn.execute(
            "SELECT * FROM employees WHERE id = ? AND store_id = ? AND active = 1",
            (employee_id, STORE_ID),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        return row

    def _require_owner(conn: sqlite3.Connection, employee_id: int) -> None:
        row = _require_employee(conn, employee_id)
        if row["role"] != "owner":
            raise HTTPException(status_code=403, detail="Solo el dueño puede hacer esto")
        return row

    def _require_inventory(
        conn: sqlite3.Connection, employee_id: int
    ) -> None:
        row = _require_employee(conn, employee_id)
        if row["role"] != "owner" and not row["can_inventory"]:
            raise HTTPException(
                status_code=403, detail="No tienes permiso para inventario"
            )
        return row

    @router.post("/open")
    def till_open(
        body: TillOpenIn, conn: sqlite3.Connection = Depends(get_till_db)
    ):
        with write_transaction(conn):
            _require_employee(conn, body.employeeId)
            try:
                payload = open_shift(
                    conn,
                    store_id=STORE_ID,
                    opened_by=body.employeeId,
                    opening_float_cents=body.openingFloatCents,
                )
            except TillError as exc:
                _raise(exc)
        return payload

    @router.post("/close")
    def till_close(
        body: TillCloseIn, conn: sqlite3.Connection = Depends(get_till_db)
    ):
        with write_transaction(conn):
            _require_employee(conn, body.employeeId)
            if body.shiftId is not None:
                shift_id = body.shiftId
            else:
                shift = current_shift(conn, STORE_ID)
                if shift is None:
                    raise HTTPException(
                        status_code=409, detail="No hay caja abierta"
                    )
                shift_id = int(shift["id"])
            try:
                result = close_shift(
                    conn,
                    store_id=STORE_ID,
                    shift_id=shift_id,
                    counted_cents=body.countedCents,
                    closed_by=body.employeeId,
                )
            except TillError as exc:
                _raise(exc)
        payload = dict(result["shift"])
        payload["duplicate"] = result["duplicate"]
        return payload

    @router.post("/{shift_id}/accept")
    def till_accept(
        shift_id: int,
        body: TillAcceptIn,
        conn: sqlite3.Connection = Depends(get_till_db),
    ):
        with write_transaction(conn):
            _require_owner(conn, body.employeeId)
            try:
                result = accept_shift(
                    conn,
                    store_id=STORE_ID,
                    shift_id=shift_id,
                    accepted_by=body.employeeId,
                    reason=(body.reason or "").strip() or None,
                )
            except TillError as exc:
                _raise(exc)
        payload = dict(result["shift"])
        payload["duplicate"] = result["duplicate"]
        return payload

    @router.get("/current")
    def till_current(conn: sqlite3.Connection = Depends(get_till_db)):
        shift = current_shift(conn, STORE_ID)
        if shift is None:
            raise HTTPException(status_code=404, detail="No hay caja abierta")
        return _shift_payload(conn, STORE_ID, int(shift["id"]))

    @router.post("/audit-variance")
    def till_audit_variance(
        body: AuditVarianceIn, conn: sqlite3.Connection = Depends(get_till_db)
    ):
        with write_transaction(conn):
            _require_inventory(conn, body.employeeId)
            try:
                return record_audit_variance(
                    conn,
                    store_id=STORE_ID,
                    product_id=body.productId,
                    counted_milli=body.countedMilli,
                    employee_id=body.employeeId,
                )
            except TillError as exc:
                _raise(exc)

    app.include_router(router)