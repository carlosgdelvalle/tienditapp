"""PG-backed business routes for the owner journey (catalog + cash sale).

Tenant and user are always derived from the verified session (auth_routes); the
per-transaction RLS context is set by db_pg so the canonical tenant_isolation
policies govern every query. The SQLite demo routes in server/main.py are
untouched, and pey payment application stays with the money worker: this module
implements only the cash path (no apply_payment, no pey, no CLABE).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from .auth_routes import IdentityContext, SessionContext, require_identity, require_owner, require_session
from .db_pg import set_tenant_context
from .identity import IdentityService
from .owner_phone import MobileIdentity
from .parser import line_total_cents

router = APIRouter(prefix="/api")
PG_INT_MAX = 2_147_483_647


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ProductIn(BaseModel):
    name: str
    unit: str
    priceCents: int
    stockMilli: int | None = None
    unlimitedStock: bool | None = None
    kind: str | None = None
    category: str | None = None
    durationMinutes: int | None = None
    quick: bool | None = None
    imageUrl: str | None = None


class ProductEditIn(BaseModel):
    name: str = Field(max_length=120)
    unit: str = Field(max_length=30)
    priceCents: int = Field(ge=0, le=PG_INT_MAX)


class BarcodeLinkIn(BaseModel):
    productId: str
    code: str


class SaleItemIn(BaseModel):
    productId: str
    qtyMilli: int


class SaleIn(BaseModel):
    items: list[SaleItemIn]
    cashReceivedCents: int | None = None
    note: str | None = None
    expectedTotalCents: int | None = Field(default=None, ge=0, le=PG_INT_MAX)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _aliases(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = []
    elif isinstance(raw, list):
        parsed = raw
    else:
        parsed = []
    return [str(alias) for alias in parsed if str(alias).strip()]


def _product_dict(row: dict) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "unit": row["unit"],
        "priceCents": row["price_cents"],
        "stockMilli": row["stock_milli"],
        "lowStockMilli": row["low_stock_milli"],
        "quick": bool(row["quick"]),
        "unlimitedStock": bool(row["unlimited_stock"]),
        "kind": row["kind"],
        "category": row["category"],
        "durationMinutes": row["duration_minutes"],
        "imageUrl": row["image_url"],
        "aliases": _aliases(row["aliases"]),
    }


def _sale_summary(sale: dict) -> dict[str, Any]:
    return {
        "saleId": str(sale["id"]),
        "createdAt": _epoch(sale["created_at"]),
        "status": sale["status"],
        "paymentMethod": sale["payment_method"],
        "totalCents": sale["total_cents"],
        "cashReceivedCents": sale["cash_received_cents"],
        "changeCents": sale["change_cents"],
    }


def _sale_dict(sale: dict, items: list[dict]) -> dict[str, Any]:
    return {
        **_sale_summary(sale),
        "id": str(sale["id"]),
        "storeId": str(sale["store_id"]),
        "employeeId": str(sale["employee_id"]),
        "chargedCents": sale["charged_cents"],
        "customerId": None,
        "customer": None,
        "qrId": sale["pey_qr_id"],
        "peyQrId": sale["pey_qr_id"],
        "txId": sale["pey_tx_id"],
        "peyTxId": sale["pey_tx_id"],
        "paidAt": _epoch(sale["paid_at"]),
        "expiresAt": _epoch(sale["expires_at"]),
        "note": sale["note"],
        "items": [
            {
                "productId": str(item["product_id"]),
                "name": item["name"],
                "unit": item["unit"],
                "qtyMilli": item["qty_milli"],
                "unitPriceCents": item["unit_price_cents"],
                "lineTotalCents": item["line_total_cents"],
            }
            for item in items
        ],
    }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class PostgresBusinessStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def add_product(
        self,
        *,
        tenant_id: str,
        name: str,
        unit: str,
        price_cents: int,
        stock_milli: int,
        unlimited_stock: bool,
        kind: str,
        category: str | None,
        duration_minutes: int | None,
        quick: bool,
        image_url: str | None,
        aliases: list[str],
    ) -> dict[str, Any]:
        low_stock_milli = 0 if unlimited_stock else 5000
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """INSERT INTO products
                       (tenant_id, name, aliases, unit, price_cents, stock_milli,
                        low_stock_milli, quick, unlimited_stock, kind, category,
                        duration_minutes, image_url)
                       VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s)
                       RETURNING id, name, unit, price_cents, stock_milli,
                                 low_stock_milli, quick, unlimited_stock, kind,
                                 category, duration_minutes, image_url, aliases""",
                    (
                        tenant_id,
                        name,
                        json.dumps(aliases, ensure_ascii=False),
                        unit,
                        price_cents,
                        stock_milli,
                        low_stock_milli,
                        quick,
                        unlimited_stock,
                        kind,
                        category,
                        duration_minutes,
                        image_url,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return _product_dict(row)

    def list_products(self, *, tenant_id: str, q: str | None = None) -> dict[str, Any]:
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT id, name, unit, price_cents, stock_milli,
                              low_stock_milli, quick, unlimited_stock, kind,
                              category, duration_minutes, image_url, aliases
                       FROM products ORDER BY lower(name) ASC, id ASC"""
                )
                rows = cur.fetchall()
        items = [_product_dict(row) for row in rows]
        if q and q.strip():
            needle = q.strip().lower()
            items = [
                item
                for item in items
                if needle in item["name"].lower()
                or any(needle in alias.lower() for alias in item["aliases"])
            ]
        return {"items": items, "total": len(items)}

    def update_product(self, tenant_id: str, product_id: uuid.UUID, body: ProductEditIn) -> dict[str, Any]:
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """UPDATE products SET name = %s, unit = %s, price_cents = %s
                       WHERE id = %s
                       RETURNING *""",
                    (body.name.strip(), body.unit.strip(), body.priceCents, product_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise HTTPException(404, "Producto no encontrado")
                return _product_dict(row)

    def overview(self, tenant_id: str) -> dict[str, Any]:
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            tz_name = conn.execute("SELECT timezone FROM tenants WHERE id = %s", (tenant_id,)).fetchone()[0]
            try:
                local_zone = ZoneInfo(tz_name)
            except (ValueError, ZoneInfoNotFoundError):
                local_zone = ZoneInfo("America/Mexico_City")
            today = datetime.now(local_zone).date()
            beginning = datetime.combine(today, time.min, local_zone)
            end = datetime.combine(today + timedelta(days=1), time.min, local_zone)
            count, amount = conn.execute(
                """SELECT count(*), coalesce(sum(total_cents), 0) FROM sales
                   WHERE status = 'paid_cash' AND created_at >= %s AND created_at < %s""",
                (beginning, end),
            ).fetchone()
            catalog_count = conn.execute("SELECT count(*) FROM products").fetchone()[0]
        return {
            "date": today.isoformat(), "timezone": local_zone.key, "cashSaleCount": count,
            "cashSalesCents": amount, "productCount": catalog_count,
        }

    def list_sales(self, tenant_id: str, limit: int, offset: int) -> dict[str, Any]:
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT id, created_at, status, payment_method, total_cents,
                              cash_received_cents, change_cents FROM sales
                       ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s""",
                    (limit + 1, offset),
                )
                rows = cur.fetchall()
        return {"items": [_sale_summary(row) for row in rows[:limit]], "hasMore": len(rows) > limit}

    def link_barcode(self, *, tenant_id: str, code: str, product_id: str) -> dict[str, Any]:
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT id FROM products WHERE id = %s::uuid", (product_id,)
                )
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Producto no encontrado")
                cur.execute(
                    """INSERT INTO barcodes (tenant_id, code, product_id)
                       VALUES (%s::uuid, %s, %s::uuid)
                       ON CONFLICT (tenant_id, code)
                       DO UPDATE SET product_id = EXCLUDED.product_id
                       RETURNING product_id""",
                    (tenant_id, code, product_id),
                )
                cur.execute(
                    """SELECT id, name, unit, price_cents, stock_milli,
                              low_stock_milli, quick, unlimited_stock, kind,
                              category, duration_minutes, image_url, aliases
                       FROM products WHERE id = %s::uuid""",
                    (product_id,),
                )
                row = cur.fetchone()
            conn.commit()
        return _product_dict(row)

    def _fetch_sale(self, cur, sale_id: str) -> dict[str, Any] | None:
        cur.execute("SELECT * FROM sales WHERE id = %s::uuid", (sale_id,))
        sale = cur.fetchone()
        if sale is None:
            return None
        cur.execute(
            "SELECT * FROM sale_items WHERE sale_id = %s::uuid ORDER BY id ASC",
            (sale_id,),
        )
        items = cur.fetchall()
        return _sale_dict(sale, items)

    def _verify_replay(
        self,
        existing: dict[str, Any],
        user_id: str,
        items: list[dict[str, Any]],
        cash_received_cents: int | None,
        expected_total_cents: int | None,
    ) -> None:
        """Reject a reused Idempotency-Key whose normalized inputs changed."""

        if existing["employeeId"] != user_id:
            raise HTTPException(
                status_code=409, detail="Idempotency-Key reutilizada por otro usuario"
            )
        if existing["paymentMethod"] != "cash":
            raise HTTPException(
                status_code=409, detail="Idempotency-Key reutilizada con otro método"
            )
        existing_cart = {(item["productId"], item["qtyMilli"]) for item in existing["items"]}
        incoming_cart = {(item["product_id"], item["qty_milli"]) for item in items}
        if existing_cart != incoming_cart:
            raise HTTPException(
                status_code=409, detail="Idempotency-Key reutilizada con un carrito distinto"
            )
        total_cents = existing["totalCents"]
        received = total_cents if cash_received_cents is None else cash_received_cents
        if existing["cashReceivedCents"] != received or (
            expected_total_cents is not None and expected_total_cents != total_cents
        ):
            raise HTTPException(
                status_code=409, detail="Idempotency-Key reutilizada con un importe distinto"
            )

    def get_sale(self, *, tenant_id: str, sale_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id="")
            with conn.cursor(row_factory=dict_row) as cur:
                return self._fetch_sale(cur, sale_id)

    def create_cash_sale(
        self,
        *,
        tenant_id: str,
        user_id: str,
        items: list[dict[str, Any]],
        cash_received_cents: int | None,
        note: str | None,
        idempotency_key: str | None = None,
        expected_total_cents: int | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        sale_id = (
            str(uuid.uuid5(uuid.UUID(tenant_id), idempotency_key))
            if idempotency_key
            else str(uuid.uuid4())
        )
        with self._pool.connection() as conn:
            set_tenant_context(conn, tenant_id=tenant_id, user_id=user_id)
            with conn.cursor(row_factory=dict_row) as cur:
                if idempotency_key:
                    # Serialize attempts at the same sale before looking at stock.
                    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (sale_id,))
                # Idempotent replay: a committed id returns its receipt before
                # any product lock or stock validation.
                existing = self._fetch_sale(cur, sale_id)
                if existing is not None:
                    self._verify_replay(existing, user_id, items, cash_received_cents, expected_total_cents)
                    conn.rollback()
                    return existing

                cur.execute(
                    "SELECT id FROM stores WHERE tenant_id = %s::uuid", (tenant_id,)
                )
                store_row = cur.fetchone()
                if store_row is None:
                    raise HTTPException(status_code=404, detail="Tienda no encontrada")
                store_id = str(store_row["id"])

                # Lock products in deterministic id order (FOR UPDATE) so two
                # concurrent sales cannot deadlock or lose a stock update.
                product_ids = sorted({item["product_id"] for item in items})
                products: dict[str, dict[str, Any]] = {}
                for product_id in product_ids:
                    cur.execute(
                        """SELECT id, name, unit, price_cents, stock_milli,
                                  unlimited_stock
                           FROM products WHERE id = %s::uuid FOR UPDATE""",
                        (product_id,),
                    )
                    product = cur.fetchone()
                    if product is None:
                        raise HTTPException(status_code=404, detail="Producto no encontrado")
                    products[product_id] = product

                # Finite stock is rejected before creating the sale.
                total_cents = 0
                lines: list[dict[str, Any]] = []
                for item in items:
                    product = products[item["product_id"]]
                    if not bool(product["unlimited_stock"]) and int(product["stock_milli"]) < item["qty_milli"]:
                        raise HTTPException(
                            status_code=409,
                            detail="Inventario insuficiente",
                        )
                    line_total = line_total_cents(int(product["price_cents"]), item["qty_milli"])
                    total_cents += line_total
                    lines.append({"product": product, "qty_milli": item["qty_milli"], "line_total": line_total})

                if expected_total_cents is not None and expected_total_cents != total_cents:
                    raise HTTPException(409, "El precio cambió. Actualiza el catálogo antes de cobrar.")
                received = total_cents if cash_received_cents is None else cash_received_cents
                if total_cents > PG_INT_MAX or received > PG_INT_MAX:
                    raise HTTPException(400, "El importe excede el límite de la venta")
                if received < total_cents:
                    raise HTTPException(status_code=400, detail="El efectivo recibido no cubre el total")
                change = received - total_cents

                cur.execute(
                    """INSERT INTO sales
                       (id, tenant_id, store_id, employee_id, status, payment_method,
                        total_cents, charged_cents, cash_received_cents, change_cents,
                        paid_at, note)
                       VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, 'paid_cash',
                               'cash', %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO NOTHING RETURNING id""",
                    (
                        sale_id, tenant_id, store_id, user_id,
                        total_cents, total_cents, received, change, now, note,
                    ),
                )
                if cur.fetchone() is None:
                    winner = self._fetch_sale(cur, sale_id)
                    if winner is None:
                        raise HTTPException(409, "No se pudo reservar el folio de la venta")
                    self._verify_replay(winner, user_id, items, cash_received_cents, expected_total_cents)
                    return winner

                for line in lines:
                    product = line["product"]
                    product_id = str(product["id"])
                    cur.execute(
                        """INSERT INTO sale_items
                           (tenant_id, sale_id, product_id, name, unit, qty_milli,
                            unit_price_cents, line_total_cents)
                           VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s)""",
                        (
                            tenant_id, sale_id, product_id,
                            product["name"], product["unit"],
                            line["qty_milli"], int(product["price_cents"]), line["line_total"],
                        ),
                    )
                    if not bool(product["unlimited_stock"]):
                        cur.execute(
                            "UPDATE products SET stock_milli = stock_milli - %s "
                            "WHERE id = %s::uuid AND unlimited_stock = false",
                            (line["qty_milli"], product_id),
                        )
                    cur.execute(
                        """INSERT INTO inventory_movements
                           (tenant_id, product_id, delta_milli, reason, sale_id, employee_id)
                           VALUES (%s::uuid, %s::uuid, %s, 'sale', %s::uuid, %s::uuid)""",
                        (tenant_id, product_id, -line["qty_milli"], sale_id, user_id),
                    )

                cur.execute(
                    """INSERT INTO payments
                       (tenant_id, tx_id, sale_id, amount_cents, method, source, applied)
                       VALUES (%s::uuid, %s, %s::uuid, %s, 'cash', 'pos', true)""",
                    (tenant_id, "cash_" + sale_id, sale_id, total_cents),
                )
            conn.commit()
        return self.get_sale(tenant_id=tenant_id, sale_id=sale_id) or {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _store(request: Request) -> PostgresBusinessStore:
    return request.app.state.business_store


@router.get("/catalog")
def list_catalog(
    q: str | None = None,
    ctx: SessionContext = Depends(require_session),
    store: PostgresBusinessStore = Depends(_store),
):
    return store.list_products(tenant_id=ctx.tenant_id, q=q)


@router.post("/catalog")
def create_catalog_item(
    body: ProductIn,
    ctx: SessionContext = Depends(require_owner),
    store: PostgresBusinessStore = Depends(_store),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    unit = body.unit.strip()
    if not unit:
        raise HTTPException(status_code=400, detail="La unidad es obligatoria")
    if not 0 <= body.priceCents <= PG_INT_MAX:
        raise HTTPException(status_code=400, detail="El precio está fuera del rango permitido")
    stock = 0 if body.stockMilli is None else int(body.stockMilli)
    if not 0 <= stock <= PG_INT_MAX:
        raise HTTPException(status_code=400, detail="La existencia está fuera del rango permitido")
    kind = (body.kind or "").strip() or "producto"
    unlimited = body.unlimitedStock if body.unlimitedStock is not None else kind != "producto"
    return store.add_product(
        tenant_id=ctx.tenant_id,
        name=name,
        unit=unit,
        price_cents=int(body.priceCents),
        stock_milli=0 if unlimited else stock,
        unlimited_stock=unlimited,
        kind=kind,
        category=(body.category or "").strip() or None,
        duration_minutes=body.durationMinutes,
        quick=bool(body.quick),
        image_url=body.imageUrl,
        aliases=[],
    )


@router.patch("/catalog/{product_id}")
def update_catalog_item(
    product_id: uuid.UUID,
    body: ProductEditIn,
    ctx: SessionContext = Depends(require_owner),
    store: PostgresBusinessStore = Depends(_store),
):
    if not body.name.strip() or not body.unit.strip():
        raise HTTPException(400, "Escribe el nombre y la unidad del producto.")
    return store.update_product(ctx.tenant_id, product_id, body)


@router.get("/owner/overview")
def owner_overview(
    ctx: SessionContext = Depends(require_owner),
    store: PostgresBusinessStore = Depends(_store),
):
    return store.overview(ctx.tenant_id)



@router.post("/barcode/link")
def barcode_link(
    body: BarcodeLinkIn,
    ctx: SessionContext = Depends(require_owner),
    store: PostgresBusinessStore = Depends(_store),
):
    code = body.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Código vacío")
    return store.link_barcode(tenant_id=ctx.tenant_id, code=code, product_id=body.productId)


def _record_cash_sale(
    body: SaleIn,
    store: PostgresBusinessStore,
    tenant_id: str,
    user_id: str,
    idempotency_key: str | None,
):
    merged: dict[str, int] = {}
    for item in body.items:
        try:
            product_id = str(uuid.UUID(item.productId))
        except ValueError:
            raise HTTPException(400, "Identificador de producto inválido") from None
        quantity = merged.get(product_id, 0) + item.qtyMilli
        if not 0 < item.qtyMilli <= quantity <= PG_INT_MAX:
            raise HTTPException(400, "Cantidad de producto fuera del rango permitido")
        merged[product_id] = quantity
    if not merged:
        raise HTTPException(status_code=400, detail="La venta no tiene productos")
    if idempotency_key:
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            raise HTTPException(status_code=400, detail="Idempotency-Key no es un UUID válido")
    items = [{"product_id": pid, "qty_milli": qty} for pid, qty in merged.items()]
    return store.create_cash_sale(
        tenant_id=tenant_id,
        user_id=user_id,
        items=items,
        cash_received_cents=body.cashReceivedCents,
        note=body.note,
        idempotency_key=idempotency_key,
        expected_total_cents=body.expectedTotalCents,
    )


@router.post("/sales")
def create_sale(
    body: SaleIn,
    ctx: SessionContext = Depends(require_owner),
    store: PostgresBusinessStore = Depends(_store),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _record_cash_sale(body, store, ctx.tenant_id, ctx.user_id, idempotency_key)


@router.get("/sales")
def sale_history(
    ctx: SessionContext = Depends(require_owner),
    store: PostgresBusinessStore = Depends(_store),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return store.list_sales(ctx.tenant_id, limit, offset)


@router.get("/sales/{sale_id}")
def get_sale(
    sale_id: uuid.UUID,
    ctx: SessionContext = Depends(require_session),
    store: PostgresBusinessStore = Depends(_store),
):
    sale = store.get_sale(tenant_id=ctx.tenant_id, sale_id=str(sale_id))
    if sale is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return sale


def _require_mobile_cash_owner(
    tenant_id: uuid.UUID,
    request: Request,
    ctx: IdentityContext = Depends(require_identity),
) -> IdentityContext:
    if not isinstance(ctx.token, MobileIdentity):
        raise HTTPException(403, "Entra desde tu celular vinculado.")
    service: IdentityService = request.app.state.identity_service
    membership = service.select_tenant(ctx.user.id, str(tenant_id))
    if membership.role != "owner" or not membership.can_sell:
        raise HTTPException(403, "No tienes permiso para cobrar en esta tienda.")
    return ctx


@router.get("/owner/pos/{tenant_id}/catalog")
def mobile_cash_catalog(
    tenant_id: uuid.UUID,
    ctx: IdentityContext = Depends(_require_mobile_cash_owner),
    store: PostgresBusinessStore = Depends(_store),
):
    return store.list_products(tenant_id=str(tenant_id))


@router.post("/owner/pos/{tenant_id}/sales")
def record_mobile_cash_sale(
    tenant_id: uuid.UUID,
    body: SaleIn,
    ctx: IdentityContext = Depends(_require_mobile_cash_owner),
    store: PostgresBusinessStore = Depends(_store),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),
):
    if body.expectedTotalCents is None or body.cashReceivedCents is None:
        raise HTTPException(400, "Confirma el total y el efectivo recibido.")
    return _record_cash_sale(body, store, str(tenant_id), ctx.user.id, idempotency_key)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(app: FastAPI, pool: Any) -> None:
    store = PostgresBusinessStore(pool)
    app.state.business_store = store
    app.include_router(router)
