"""Owner operations backed by the existing tenant-scoped PostgreSQL ledgers.

The audited operations are extracted into reusable functions so the employee
router can exercise the exact same ledgers and idempotency rules without
widening their authorization.
"""

from contextlib import contextmanager
from typing import Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from .auth_routes import SessionContext, require_owner
from .business_pg import PG_INT_MAX, read_catalog
from .db_pg import set_tenant_context

router = APIRouter(prefix="/api/owner")


@contextmanager
def _transaction(request: Request, tenant_id: str, user_id: str, *, snapshot: bool = False):
    with request.app.state.pool.connection() as conn:
        if snapshot:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        set_tenant_context(conn, tenant_id=tenant_id, user_id=user_id)
        with conn.cursor(row_factory=dict_row) as cursor:
            yield cursor


def _lock_intent(cursor, tenant_id: str, domain: str, key: UUID) -> UUID:
    row_id = uuid5(UUID(tenant_id), f"{domain}:{key}")
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(row_id),))
    return row_id


class StockAdjust(BaseModel):
    expectedStockMilli: int = Field(ge=-PG_INT_MAX - 1, le=PG_INT_MAX)
    stockMilli: int = Field(ge=0, le=PG_INT_MAX)
    reason: str = Field(min_length=1, max_length=200)


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AmountNote(BaseModel):
    amountCents: int = Field(gt=0, le=PG_INT_MAX)
    note: str = Field(min_length=1, max_length=200)


class FiadoEntryCreate(AmountNote):
    kind: Literal["charge", "payment"]


_SIGNED_AMOUNT = "CASE WHEN kind = 'charge' THEN amount_cents ELSE -amount_cents END"


def _note(body: AmountNote) -> str:
    note = body.note.strip()
    if not note:
        raise HTTPException(400, "Escribe un concepto para el registro.")
    return note


def _customer(cursor, customer_id: UUID, *, for_update: bool = False):
    query = "SELECT id, name, credit_limit_cents FROM fiado_customers WHERE id = %s AND active"
    cursor.execute(query + (" FOR UPDATE" if for_update else ""), (customer_id,))
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Cliente no encontrado.")
    return row


def _balance(cursor, customer_id: UUID) -> int:
    cursor.execute(f"SELECT COALESCE(SUM({_SIGNED_AMOUNT}), 0) AS balance FROM fiado_entries WHERE customer_id = %s", (customer_id,))
    return cursor.fetchone()["balance"]


def _entry(row) -> dict:
    return {
        "id": str(row["id"]), "amountCents": row["amount_cents"],
        "note": row["note"], "createdAt": row["created_at"].timestamp(),
    }


# ---------------------------------------------------------------------------
# Shared audited operations (owner and employee routers reuse these)
# ---------------------------------------------------------------------------


def list_inventory(request: Request, tenant_id: str, user_id: str) -> dict:
    with _transaction(request, tenant_id, user_id, snapshot=True) as cursor:
        items = read_catalog(cursor)
        cursor.execute(
            """SELECT m.id, p.name, m.delta_milli, m.reason, m.created_at
               FROM inventory_movements m
               JOIN products p ON (p.tenant_id, p.id) = (m.tenant_id, m.product_id)
               ORDER BY m.created_at DESC, m.id DESC LIMIT 50"""
        )
        movements = [
            {
                "id": str(row["id"]), "name": row["name"],
                "deltaMilli": row["delta_milli"], "reason": row["reason"],
                "createdAt": row["created_at"].timestamp(),
            }
            for row in cursor.fetchall()
        ]
    return {"items": items, "total": len(items), "movements": movements}


def adjust_stock(
    request: Request, tenant_id: str, user_id: str,
    product_id: UUID, body: StockAdjust, key: UUID,
) -> dict:
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(400, "Escribe el motivo del ajuste.")
    reason = "Ajuste: " + reason
    delta = body.stockMilli - body.expectedStockMilli
    if delta > PG_INT_MAX:
        raise HTTPException(400, "El ajuste supera el máximo permitido por movimiento.")
    with _transaction(request, tenant_id, user_id) as cursor:
        movement_id = _lock_intent(cursor, tenant_id, "inventory", key)
        cursor.execute(
            "SELECT stock_milli, unlimited_stock FROM products WHERE id = %s FOR UPDATE",
            (product_id,),
        )
        product = cursor.fetchone()
        if product is None:
            raise HTTPException(404, "Producto no encontrado.")
        cursor.execute(
            "SELECT product_id, delta_milli, reason, employee_id FROM inventory_movements WHERE id = %s",
            (movement_id,),
        )
        existing = cursor.fetchone()
        if existing:
            if (existing["product_id"], existing["delta_milli"], existing["reason"], str(existing["employee_id"])) != (
                product_id, delta, reason, user_id,
            ):
                raise HTTPException(409, "El intento guardado corresponde a otro ajuste.")
            return {"productId": str(product_id), "stockMilli": product["stock_milli"], "duplicate": True}
        if product["unlimited_stock"]:
            raise HTTPException(409, "Este producto tiene existencia ilimitada.")
        if product["stock_milli"] != body.expectedStockMilli:
            raise HTTPException(409, "La existencia cambió. Actualiza el inventario antes de guardar.")
        if delta:
            cursor.execute("UPDATE products SET stock_milli = %s WHERE id = %s", (body.stockMilli, product_id))
            cursor.execute(
                """INSERT INTO inventory_movements
                   (id, tenant_id, product_id, delta_milli, reason, employee_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (movement_id, tenant_id, product_id, delta, reason, user_id),
            )
    return {"productId": str(product_id), "stockMilli": body.stockMilli, "duplicate": False}


def list_customers(request: Request, tenant_id: str, user_id: str) -> dict:
    with _transaction(request, tenant_id, user_id) as cursor:
        cursor.execute(
            f"""SELECT c.id, c.name, COALESCE(SUM({_SIGNED_AMOUNT}), 0) AS balance_cents
                FROM fiado_customers c
                LEFT JOIN fiado_entries e ON (e.tenant_id, e.customer_id) = (c.tenant_id, c.id)
                WHERE c.active
                GROUP BY c.id ORDER BY lower(c.name), c.id"""
        )
        return {"items": [
            {"id": str(row["id"]), "name": row["name"], "balanceCents": row["balance_cents"]}
            for row in cursor.fetchall()
        ]}


@router.post("/fiado/customers")
def add_customer(
    request: Request,
    body: CustomerCreate,
    key: UUID = Header(alias="Idempotency-Key"),
    ctx: SessionContext = Depends(require_owner),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Escribe el nombre del cliente.")
    with _transaction(request, ctx.tenant_id, ctx.user_id) as cursor:
        customer_id = _lock_intent(cursor, ctx.tenant_id, "fiado-customer", key)
        cursor.execute("SELECT name FROM fiado_customers WHERE id = %s", (customer_id,))
        existing = cursor.fetchone()
        if existing and existing["name"] != name:
            raise HTTPException(409, "El intento guardado corresponde a otro cliente.")
        if not existing:
            cursor.execute(
                "INSERT INTO fiado_customers (id, tenant_id, name) VALUES (%s, %s, %s)",
                (customer_id, ctx.tenant_id, name),
            )
        return {"id": str(customer_id), "name": name}


def customer_detail(request: Request, tenant_id: str, user_id: str, customer_id: UUID) -> dict:
    with _transaction(request, tenant_id, user_id) as cursor:
        customer = _customer(cursor, customer_id)
        cursor.execute(
            f"""SELECT id, kind, amount_cents, note, created_at, SUM({_SIGNED_AMOUNT}) OVER () AS balance
                FROM fiado_entries WHERE customer_id = %s
                ORDER BY created_at DESC, id DESC LIMIT 50""",
            (customer_id,),
        )
        entries = cursor.fetchall()
        return {
            "id": str(customer_id), "name": customer["name"],
            "balanceCents": entries[0]["balance"] if entries else 0,
            "items": [{**_entry(row), "kind": row["kind"]} for row in entries],
        }


def add_fiado_entry(
    request: Request, tenant_id: str, user_id: str,
    customer_id: UUID, body: FiadoEntryCreate, key: UUID,
) -> dict:
    note = _note(body)
    with _transaction(request, tenant_id, user_id) as cursor:
        entry_id = _lock_intent(cursor, tenant_id, "fiado-entry", key)
        customer = _customer(cursor, customer_id, for_update=True)
        cursor.execute(
            "SELECT customer_id, kind, amount_cents, note, employee_id FROM fiado_entries WHERE id = %s",
            (entry_id,),
        )
        existing = cursor.fetchone()
        if existing:
            recorded = (existing["customer_id"], existing["kind"], existing["amount_cents"], existing["note"],
                        str(existing["employee_id"]))
            if recorded != (customer_id, body.kind, body.amountCents, note, user_id):
                raise HTTPException(409, "El intento guardado corresponde a otro movimiento.")
            return {"id": str(entry_id)}
        balance = _balance(cursor, customer_id)
        if body.kind == "payment" and body.amountCents > balance:
            raise HTTPException(409, "El abono excede el saldo pendiente.")
        limit = customer["credit_limit_cents"]
        if body.kind == "charge" and limit is not None and balance + body.amountCents > limit:
            raise HTTPException(409, "El cargo excede el límite de fiado del cliente.")
        cursor.execute(
            """INSERT INTO fiado_entries (id, tenant_id, customer_id, kind, amount_cents, note, employee_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (entry_id, tenant_id, customer_id, body.kind, body.amountCents, note, user_id),
        )
        return {"id": str(entry_id)}


@router.get("/expenses")
def list_expenses(request: Request, ctx: SessionContext = Depends(require_owner)):
    with _transaction(request, ctx.tenant_id, ctx.user_id) as cursor:
        cursor.execute(
            """SELECT id, amount_cents, note, created_at, sum(amount_cents) OVER () AS total_cents
               FROM expenses ORDER BY created_at DESC, id DESC LIMIT 50"""
        )
        rows = cursor.fetchall()
        return {"items": [_entry(row) for row in rows], "totalCents": rows[0]["total_cents"] if rows else 0}


@router.post("/expenses")
def add_expense(
    request: Request,
    body: AmountNote,
    key: UUID = Header(alias="Idempotency-Key"),
    ctx: SessionContext = Depends(require_owner),
):
    note = _note(body)
    with _transaction(request, ctx.tenant_id, ctx.user_id) as cursor:
        expense_id = _lock_intent(cursor, ctx.tenant_id, "expense", key)
        cursor.execute("SELECT amount_cents, note, employee_id FROM expenses WHERE id = %s", (expense_id,))
        existing = cursor.fetchone()
        if existing:
            if (existing["amount_cents"], existing["note"], str(existing["employee_id"])) != (
                body.amountCents, note, ctx.user_id,
            ):
                raise HTTPException(409, "El intento guardado corresponde a otro gasto.")
            return {"id": str(expense_id)}
        cursor.execute(
            "INSERT INTO expenses (id, tenant_id, employee_id, amount_cents, note) VALUES (%s, %s, %s, %s, %s)",
            (expense_id, ctx.tenant_id, ctx.user_id, body.amountCents, note),
        )
        return {"id": str(expense_id)}


# ---------------------------------------------------------------------------
# Owner routes
# ---------------------------------------------------------------------------


@router.get("/inventory")
def inventory(request: Request, ctx: SessionContext = Depends(require_owner)):
    return list_inventory(request, ctx.tenant_id, ctx.user_id)


@router.post("/inventory/{product_id}/adjust")
def adjust_stock_route(
    product_id: UUID,
    body: StockAdjust,
    request: Request,
    key: UUID = Header(alias="Idempotency-Key"),
    ctx: SessionContext = Depends(require_owner),
):
    return adjust_stock(request, ctx.tenant_id, ctx.user_id, product_id, body, key)


@router.get("/fiado/customers")
def list_customers_route(request: Request, ctx: SessionContext = Depends(require_owner)):
    return list_customers(request, ctx.tenant_id, ctx.user_id)


@router.get("/fiado/customers/{customer_id}")
def customer_detail_route(customer_id: UUID, request: Request, ctx: SessionContext = Depends(require_owner)):
    return customer_detail(request, ctx.tenant_id, ctx.user_id, customer_id)


@router.post("/fiado/customers/{customer_id}/entries")
def add_fiado_entry_route(
    customer_id: UUID,
    request: Request,
    body: FiadoEntryCreate,
    key: UUID = Header(alias="Idempotency-Key"),
    ctx: SessionContext = Depends(require_owner),
):
    return add_fiado_entry(request, ctx.tenant_id, ctx.user_id, customer_id, body, key)
