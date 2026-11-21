"""FastAPI router for purchasing and replenishment.

register(app) installs the router under /api. Like server/routes_till.py,
server/main.py is intentionally left untouched; the coordinator wires the
one-line register_purchasing(app) call. The router reuses server.db connection
helpers and the purchasing core from server.purchasing.

Identity is SIMULADO via the X-Employee-Id header (same convention as the v2
owner/inventory gates in main.py): the owner mutates suppliers and purchase
orders, and anyone with the inventory permission records a goods receipt; only
the owner approves a receipt.

Endpoints:
  GET/POST /api/suppliers, PATCH/DELETE /api/suppliers/{id}
  GET/POST /api/purchase-orders, POST /api/purchase-orders/{id}/issue|cancel
  GET/POST /api/receipts, POST /api/receipts/{id}/approve
  GET /api/receipts/cases
"""

from __future__ import annotations

import sqlite3
from typing import Annotated, Iterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .db import STORE_ID, connect, write_transaction
from .purchasing import (
    PurchasingError,
    approve_receipt,
    cancel_purchase_order,
    create_purchase_order,
    create_receipt,
    create_supplier,
    delete_supplier,
    ensure_purchasing_schema,
    get_purchase_order,
    get_receipt,
    issue_purchase_order,
    list_purchase_orders,
    list_receipt_cases,
    list_receipts,
    list_suppliers,
    update_supplier,
)


_PURCHASING_ERROR_STATUS = {
    "supplier_not_found": 404,
    "supplier_inactive": 409,
    "invalid_name": 400,
    "purchase_order_not_found": 404,
    "purchase_order_not_draft": 409,
    "purchase_order_not_receivable": 409,
    "purchase_order_not_cancelable": 409,
    "product_not_found": 404,
    "product_not_ordered": 409,
    "invalid_qty": 400,
    "invalid_cost": 400,
    "invalid_lines": 400,
    "duplicate_line": 400,
    "receipt_not_found": 404,
    "receipt_not_approvable": 409,
}


class SupplierIn(BaseModel):
    name: str
    contact: str | None = None


class SupplierPatchIn(BaseModel):
    name: str | None = None
    contact: str | None = None
    active: bool | None = None


class POLineIn(BaseModel):
    productId: int
    qtyMilli: int
    unitCostCents: int | None = None


class PurchaseOrderIn(BaseModel):
    supplierId: int
    lines: list[POLineIn] = Field(min_length=1)
    note: str | None = None


class ReceiptLineIn(BaseModel):
    productId: int
    qtyMilli: int


class ReceiptIn(BaseModel):
    purchaseOrderId: int
    lines: list[ReceiptLineIn] = Field(min_length=1)
    clientReceiptId: str | None = None
    shipmentRef: str | None = None
    note: str | None = None


def _raise(exc: PurchasingError) -> None:
    raise HTTPException(
        status_code=_PURCHASING_ERROR_STATUS.get(exc.code, 400), detail=exc.detail
    )


def register(app) -> None:
    router = APIRouter(prefix="/api")

    def get_purchasing_db(request: Request) -> Iterator[sqlite3.Connection]:
        conn = connect(request.app.state.settings.db_path)
        try:
            ensure_purchasing_schema(conn)
            yield conn
        finally:
            conn.close()

    def _employee_row(
        conn: sqlite3.Connection, employee_id: int | None
    ) -> sqlite3.Row | None:
        # No header keeps the open v1 behavior (console and scripts); a header
        # that points to an unknown or inactive employee is rejected, matching
        # main.py's _optional_employee.
        if employee_id is None:
            return None
        row = conn.execute(
            "SELECT * FROM employees WHERE id = ? AND store_id = ? AND active = 1",
            (employee_id, STORE_ID),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=403, detail="Empleado no válido o inactivo"
            )
        return row

    def _require_owner(
        conn: sqlite3.Connection, x_employee_id: int | None
    ) -> sqlite3.Row | None:
        employee = _employee_row(conn, x_employee_id)
        if employee is not None and employee["role"] != "owner":
            raise HTTPException(status_code=403, detail="Solo el dueño puede hacer esto")
        return employee

    def _require_inventory(
        conn: sqlite3.Connection, x_employee_id: int | None
    ) -> sqlite3.Row | None:
        employee = _employee_row(conn, x_employee_id)
        if (
            employee is not None
            and employee["role"] != "owner"
            and not employee["can_inventory"]
        ):
            raise HTTPException(
                status_code=403, detail="No tienes permiso para inventario"
            )
        return employee

    # Suppliers -------------------------------------------------------------

    @router.get("/suppliers")
    def suppliers_list(conn: sqlite3.Connection = Depends(get_purchasing_db)):
        return {"items": list_suppliers(conn, STORE_ID)}

    @router.post("/suppliers")
    def suppliers_create(
        body: SupplierIn,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            _require_owner(conn, x_employee_id)
            try:
                return create_supplier(
                    conn, store_id=STORE_ID, name=body.name, contact=body.contact
                )
            except PurchasingError as exc:
                _raise(exc)

    @router.patch("/suppliers/{supplier_id}")
    def suppliers_update(
        supplier_id: int,
        body: SupplierPatchIn,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            _require_owner(conn, x_employee_id)
            try:
                return update_supplier(
                    conn,
                    store_id=STORE_ID,
                    supplier_id=supplier_id,
                    name=body.name,
                    contact=body.contact,
                    active=body.active,
                )
            except PurchasingError as exc:
                _raise(exc)

    @router.delete("/suppliers/{supplier_id}")
    def suppliers_delete(
        supplier_id: int,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            _require_owner(conn, x_employee_id)
            try:
                return delete_supplier(conn, store_id=STORE_ID, supplier_id=supplier_id)
            except PurchasingError as exc:
                _raise(exc)

    # Purchase orders -------------------------------------------------------

    @router.get("/purchase-orders")
    def purchase_orders_list(conn: sqlite3.Connection = Depends(get_purchasing_db)):
        return {"items": list_purchase_orders(conn, STORE_ID)}

    @router.get("/purchase-orders/{po_id}")
    def purchase_orders_get(
        po_id: int, conn: sqlite3.Connection = Depends(get_purchasing_db)
    ):
        try:
            return get_purchase_order(conn, STORE_ID, po_id)
        except PurchasingError as exc:
            _raise(exc)

    @router.post("/purchase-orders")
    def purchase_orders_create(
        body: PurchaseOrderIn,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            owner = _require_owner(conn, x_employee_id)
            lines = [
                {"productId": line.productId, "qtyMilli": line.qtyMilli, "unitCostCents": line.unitCostCents}
                for line in body.lines
            ]
            try:
                return create_purchase_order(
                    conn,
                    store_id=STORE_ID,
                    supplier_id=body.supplierId,
                    lines=lines,
                    employee_id=owner["id"] if owner is not None else None,
                    note=body.note,
                )
            except PurchasingError as exc:
                _raise(exc)

    @router.post("/purchase-orders/{po_id}/issue")
    def purchase_orders_issue(
        po_id: int,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            _require_owner(conn, x_employee_id)
            try:
                return issue_purchase_order(conn, store_id=STORE_ID, po_id=po_id)
            except PurchasingError as exc:
                _raise(exc)

    @router.post("/purchase-orders/{po_id}/cancel")
    def purchase_orders_cancel(
        po_id: int,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            _require_owner(conn, x_employee_id)
            try:
                return cancel_purchase_order(conn, store_id=STORE_ID, po_id=po_id)
            except PurchasingError as exc:
                _raise(exc)

    # Receipts --------------------------------------------------------------

    @router.get("/receipts")
    def receipts_list(conn: sqlite3.Connection = Depends(get_purchasing_db)):
        return {"items": list_receipts(conn, STORE_ID)}

    @router.get("/receipts/cases")
    def receipts_cases(conn: sqlite3.Connection = Depends(get_purchasing_db)):
        return {"items": list_receipt_cases(conn, STORE_ID)}

    @router.get("/receipts/{receipt_id}")
    def receipts_get(
        receipt_id: int, conn: sqlite3.Connection = Depends(get_purchasing_db)
    ):
        try:
            return get_receipt(conn, STORE_ID, receipt_id)
        except PurchasingError as exc:
            _raise(exc)

    @router.post("/receipts")
    def receipts_create(
        body: ReceiptIn,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            employee = _require_inventory(conn, x_employee_id)
            lines = [
                {"productId": line.productId, "qtyMilli": line.qtyMilli}
                for line in body.lines
            ]
            try:
                return create_receipt(
                    conn,
                    store_id=STORE_ID,
                    purchase_order_id=body.purchaseOrderId,
                    lines=lines,
                    employee_id=employee["id"] if employee is not None else None,
                    client_receipt_id=body.clientReceiptId,
                    shipment_ref=body.shipmentRef,
                    note=body.note,
                )
            except PurchasingError as exc:
                _raise(exc)

    @router.post("/receipts/{receipt_id}/approve")
    def receipts_approve(
        receipt_id: int,
        conn: sqlite3.Connection = Depends(get_purchasing_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            owner = _require_owner(conn, x_employee_id)
            try:
                return approve_receipt(
                    conn,
                    store_id=STORE_ID,
                    receipt_id=receipt_id,
                    approved_by=owner["id"] if owner is not None else None,
                )
            except PurchasingError as exc:
                _raise(exc)

    app.include_router(router)
