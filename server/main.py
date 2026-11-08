"""Abarpay v1 - FastAPI application.

Public POS endpoints live under /api, the PEY webhook at /webhooks/pey and the
owner demo console at /console. Every request uses its own SQLite connection.
"""

from __future__ import annotations

import hmac
import json
import logging
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Iterator, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .config import Settings
from .db import (
    STORE_ID,
    connect,
    initialize_db,
    store_row,
    write_transaction,
)
from .parser import line_total_cents, parse_text
from .payments import apply_payment, restore_inventory, decrement_inventory
from .pey import PeyClient, PeyError, PeyTimeout, payload_cents, verify_webhook
from .reports import build_today_report, fiado_outstanding_cents
from .serializers import (
    customer_balance_cents,
    customer_to_dict,
    employee_to_dict,
    product_to_dict,
    sale_to_dict,
    store_to_dict,
)

logger = logging.getLogger("abarpay")

_PEY_RECONCILABLE = {"pending", "por_conciliar", "expired"}
_PEY_SUCCESS_STATUSES = {
    "completed",
    "complete",
    "paid",
    "success",
    "succeeded",
    "approved",
    "received",
}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    settings: Settings | None = None,
    pey_client: Any | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Iterator[None]:
        initialize_db(app.state.settings.db_path)
        yield
        client = app.state.pey
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:  # pragma: no cover - best effort shutdown
                pass

    app = FastAPI(
        title="Abarpay v1",
        version="1.0.0",
        description="Cobros CoDi, ventas e inventario para la tiendita.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    if pey_client is not None:
        app.state.pey = pey_client
    elif settings.pey_configured:
        app.state.pey = PeyClient(
            settings.pey_api_key,
            base_url=settings.pey_base_url,
            timeout=settings.pey_timeout_seconds,
        )
    else:
        app.state.pey = None

    _install_routes(app)
    return app


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_pey(request: Request) -> Any | None:
    return request.app.state.pey


def require_owner(
    request: Request,
    x_owner_pin: Annotated[str | None, Header(alias="X-Owner-Pin")] = None,
) -> None:
    settings: Settings = request.app.state.settings
    if not x_owner_pin or not hmac.compare_digest(
        str(x_owner_pin).encode("utf-8"), settings.owner_pin.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="PIN de dueño inválido")


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CartParseIn(BaseModel):
    text: str


class BarcodeIn(BaseModel):
    code: str


class BarcodeLinkIn(BaseModel):
    code: str
    productId: int


class SaleItemIn(BaseModel):
    productId: int
    qtyMilli: int


class SaleIn(BaseModel):
    employeeId: int
    items: list[SaleItemIn] = Field(min_length=1)
    paymentMethod: Literal["cash", "pey", "fiado"]
    cashReceivedCents: int | None = None
    customerId: int | None = None
    note: str | None = None


class AdjustIn(BaseModel):
    employeeId: int
    productId: int
    deltaMilli: int
    reason: str = "ajuste"


class CustomerIn(BaseModel):
    name: str
    phone: str | None = None


class AbonoIn(BaseModel):
    amountCents: int
    employeeId: int
    note: str | None = None


class LoginIn(BaseModel):
    pin: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> float:
    return time.time()


def _sale_row(conn: sqlite3.Connection, sale_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()


def _require_sale(conn: sqlite3.Connection, sale_id: str) -> sqlite3.Row:
    row = _sale_row(conn, sale_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return row


def _require_employee(conn: sqlite3.Connection, employee_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM employees WHERE id = ? AND store_id = ? AND active = 1",
        (employee_id, STORE_ID),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return row


def _require_product(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM products WHERE id = ? AND store_id = ?",
        (product_id, STORE_ID),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return row


def _require_customer(conn: sqlite3.Connection, customer_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM fiado_customers WHERE id = ? AND store_id = ?",
        (customer_id, STORE_ID),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Cliente de fiado no encontrado")
    return row


def _sale_or_404(conn: sqlite3.Connection, sale_id: str) -> sqlite3.Row:
    row = _sale_row(conn, sale_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return row


def _serialize_sale(conn: sqlite3.Connection, sale_id: str) -> dict[str, Any]:
    row = _sale_or_404(conn, sale_id)
    return sale_to_dict(conn, row)


def _pey_containers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = [payload]
    for key in ("data", "qr"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            containers.append(nested)
    return containers


def _pey_qr_id(payload: dict[str, Any]) -> str | None:
    for container in _pey_containers(payload):
        for key in ("id", "qrId", "codiQrId", "qr_id"):
            value = container.get(key)
            if value:
                return str(value)
    return None


def _pey_qr_image(payload: dict[str, Any]) -> str:
    for container in _pey_containers(payload):
        for key in ("image", "qrImage", "imageUrl", "qr_image"):
            value = container.get(key)
            if not value:
                continue
            raw = str(value).strip()
            if raw.startswith("data:"):
                return raw
            # PEY may return raw base64. The Android client only decodes data URLs.
            return "data:image/png;base64," + raw
    return ""


def _transaction_cents(item: dict[str, Any]) -> int | None:
    if item.get("amountCents") is not None:
        try:
            return int(item["amountCents"])
        except (TypeError, ValueError):
            return None
    return payload_cents(item.get("amount"))


def _transaction_id(item: dict[str, Any]) -> str | None:
    for key in ("transactionId", "transaction_id", "txId", "tx_id", "id"):
        value = item.get(key)
        if value:
            return str(value)
    return None


def _transaction_status_ok(item: dict[str, Any]) -> bool:
    raw = item.get("status")
    if raw is None:
        return True
    status = str(raw).strip().lower()
    return not status or status in _PEY_SUCCESS_STATUSES


def _choose_transaction(
    items: list[dict[str, Any]], charged_cents: int
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not _transaction_status_ok(item):
            continue
        if _transaction_id(item) is None:
            continue
        if _transaction_cents(item) is None:
            continue
        candidates.append(item)
    if not candidates:
        return None
    exact = [item for item in candidates if _transaction_cents(item) == charged_cents]
    return (exact or candidates)[0]


def _reconcile_sale(
    conn: sqlite3.Connection,
    sale_id: str,
    pey_client: Any | None,
    now: float | None = None,
) -> sqlite3.Row:
    """Try to resolve pending / expired / por_conciliar PEY sales.

    The network call happens outside any write transaction. The resulting
    payment is then applied inside BEGIN IMMEDIATE, and apply_payment is
    idempotent by transaction id, so a concurrent webhook cannot double-apply.
    """

    now = _now() if now is None else now
    row = _sale_row(conn, sale_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if row["payment_method"] != "pey" or row["status"] not in _PEY_RECONCILABLE:
        return row
    if not row["pey_qr_id"]:
        if row["status"] == "pending" and row["expires_at"] and row["expires_at"] < now:
            with write_transaction(conn):
                conn.execute(
                    "UPDATE sales SET status = 'expired' WHERE id = ? AND status = 'pending'",
                    (sale_id,),
                )
            return _sale_row(conn, sale_id) or row
        return row

    items: list[dict[str, Any]] | None = None
    if pey_client is not None:
        try:
            raw_items = pey_client.qr_transactions(row["pey_qr_id"])
            if isinstance(raw_items, dict):
                raw_items = raw_items.get("items", [])
            items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        except (PeyTimeout, PeyError):
            items = None

    if items:
        chosen = _choose_transaction(items, int(row["charged_cents"]))
        if chosen is not None:
            tx_id = _transaction_id(chosen)
            amount_cents = _transaction_cents(chosen)
            if tx_id is not None and amount_cents is not None:
                with write_transaction(conn):
                    current = _sale_row(conn, sale_id)
                    if current is not None and current["status"] in _PEY_RECONCILABLE:
                        apply_payment(
                            conn,
                            sale_id=sale_id,
                            transaction_id=tx_id,
                            amount_cents=amount_cents,
                            source="reconcile",
                            received_at=now,
                        )
                return _sale_row(conn, sale_id) or row

    if row["status"] == "pending" and row["expires_at"] and row["expires_at"] < now:
        with write_transaction(conn):
            conn.execute(
                "UPDATE sales SET status = 'expired' WHERE id = ? AND status = 'pending'",
                (sale_id,),
            )
        return _sale_row(conn, sale_id) or row
    return row


def _mark_pey_failed(
    conn: sqlite3.Connection, sale_id: str, note: str
) -> sqlite3.Row | None:
    with write_transaction(conn):
        conn.execute(
            """UPDATE sales
               SET status = 'failed', note = CASE
                   WHEN note IS NULL OR note = '' THEN ?
                   ELSE note || ' | ' || ?
               END
               WHERE id = ? AND status = 'pending'""",
            (note, note, sale_id),
        )
    return _sale_row(conn, sale_id)


def _mark_pey_por_conciliar(
    conn: sqlite3.Connection, sale_id: str, note: str
) -> sqlite3.Row | None:
    with write_transaction(conn):
        conn.execute(
            """UPDATE sales
               SET status = 'por_conciliar', note = CASE
                   WHEN note IS NULL OR note = '' THEN ?
                   ELSE note || ' | ' || ?
               END
               WHERE id = ? AND status = 'pending'""",
            (note, note, sale_id),
        )
    return _sale_row(conn, sale_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _install_routes(app: FastAPI) -> None:
    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health(conn: sqlite3.Connection = Depends(get_db), settings: Settings = Depends(get_settings)):
        try:
            conn.execute("SELECT 1").fetchone()
            db_status = "ok"
            ok = True
        except sqlite3.Error:
            db_status = "error"
            ok = False
        body = {
            "ok": ok,
            "mode": "demo" if settings.modo_demo else "live",
            "db": db_status,
            "peyConfigured": settings.pey_configured,
        }
        return JSONResponse(status_code=200 if ok else 503, content=body)

    @api.get("/bootstrap")
    def bootstrap(conn: sqlite3.Connection = Depends(get_db), settings: Settings = Depends(get_settings)):
        store = store_row(conn)
        if store is None:
            raise HTTPException(status_code=500, detail="Tienda no inicializada")
        employees = conn.execute(
            "SELECT * FROM employees WHERE store_id = ? AND active = 1 ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        products = conn.execute(
            "SELECT * FROM products WHERE store_id = ? ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        return {
            "store": store_to_dict(store),
            "employees": [employee_to_dict(row) for row in employees],
            "products": [product_to_dict(row) for row in products],
            "demoMode": settings.modo_demo,
            "ai": "local",
        }

    @api.post("/cart/parse")
    def cart_parse(body: CartParseIn, conn: sqlite3.Connection = Depends(get_db)):
        catalog = [
            dict(row)
            for row in conn.execute(
                """SELECT id, name, aliases, unit, price_cents
                   FROM products WHERE store_id = ? ORDER BY id""",
                (STORE_ID,),
            ).fetchall()
        ]
        return parse_text(body.text, catalog)

    @api.post("/barcode/lookup")
    def barcode_lookup(body: BarcodeIn, conn: sqlite3.Connection = Depends(get_db)):
        code = body.code.strip()
        if not code:
            raise HTTPException(status_code=400, detail="Código vacío")
        product = conn.execute(
            """SELECT p.* FROM products p JOIN barcodes b ON b.product_id = p.id
               WHERE b.code = ? AND p.store_id = ?""",
            (code, STORE_ID),
        ).fetchone()
        if product is None:
            raise HTTPException(status_code=404, detail="Código no vinculado")
        return product_to_dict(product)

    @api.post("/barcode/link")
    def barcode_link(body: BarcodeLinkIn, conn: sqlite3.Connection = Depends(get_db)):
        code = body.code.strip()
        if not code:
            raise HTTPException(status_code=400, detail="Código vacío")
        with write_transaction(conn):
            product = _require_product(conn, body.productId)
            conn.execute(
                """INSERT INTO barcodes (code, product_id) VALUES (?, ?)
                   ON CONFLICT(code) DO UPDATE SET product_id = excluded.product_id""",
                (code, product["id"]),
            )
        return product_to_dict(product)

    @api.post("/sales")
    def create_sale(
        body: SaleIn,
        conn: sqlite3.Connection = Depends(get_db),
        settings: Settings = Depends(get_settings),
        pey_client: Any | None = Depends(get_pey),
    ):
        merged: dict[int, int] = {}
        for item in body.items:
            if item.qtyMilli <= 0:
                raise HTTPException(status_code=400, detail="qtyMilli debe ser mayor que cero")
            merged[item.productId] = merged.get(item.productId, 0) + item.qtyMilli
        if not merged:
            raise HTTPException(status_code=400, detail="La venta no tiene productos")

        sale_id = "sale_" + uuid.uuid4().hex[:20]
        now = _now()
        cash_received: int | None = None
        change_cents: int | None = None

        with write_transaction(conn):
            employee = _require_employee(conn, body.employeeId)
            products: list[sqlite3.Row] = []
            for product_id in merged:
                products.append(_require_product(conn, product_id))

            total_cents = 0
            lines: list[dict[str, Any]] = []
            for product in products:
                qty_milli = merged[int(product["id"])]
                line_total = line_total_cents(int(product["price_cents"]), qty_milli)
                total_cents += line_total
                lines.append(
                    {
                        "product": product,
                        "qty_milli": qty_milli,
                        "line_total": line_total,
                    }
                )

            customer = None
            if body.paymentMethod == "fiado":
                if body.customerId is None:
                    raise HTTPException(
                        status_code=400,
                        detail="customerId es obligatorio para fiado",
                    )
                customer = _require_customer(conn, body.customerId)

            if body.paymentMethod == "cash":
                cash_received = (
                    total_cents if body.cashReceivedCents is None else body.cashReceivedCents
                )
                if cash_received < total_cents:
                    raise HTTPException(
                        status_code=400,
                        detail="El efectivo recibido no cubre el total",
                    )
                change_cents = cash_received - total_cents
                status = "paid_cash"
                charged_cents = total_cents
                paid_at = now
                expires_at = None
            elif body.paymentMethod == "fiado":
                cash_received = None
                change_cents = None
                status = "credit"
                charged_cents = total_cents
                paid_at = None
                expires_at = None
            else:
                cash_received = None
                change_cents = None
                status = "pending"
                charged_cents = settings.demo_charge_cents if settings.modo_demo else total_cents
                paid_at = None
                expires_at = now + settings.pey_expiration_seconds

            conn.execute(
                """INSERT INTO sales
                   (id, store_id, employee_id, created_at, status, payment_method,
                    total_cents, charged_cents, cash_received_cents, change_cents,
                    customer_id, pey_qr_id, pey_tx_id, paid_at, expires_at, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)""",
                (
                    sale_id,
                    STORE_ID,
                    employee["id"],
                    now,
                    status,
                    body.paymentMethod,
                    total_cents,
                    charged_cents,
                    cash_received,
                    change_cents,
                    body.customerId,
                    paid_at,
                    expires_at,
                    body.note,
                ),
            )
            for line in lines:
                product = line["product"]
                conn.execute(
                    """INSERT INTO sale_items
                       (sale_id, product_id, name, unit, qty_milli,
                        unit_price_cents, line_total_cents)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sale_id,
                        product["id"],
                        product["name"],
                        product["unit"],
                        line["qty_milli"],
                        product["price_cents"],
                        line["line_total"],
                    ),
                )

            if body.paymentMethod == "cash":
                decrement_inventory(conn, sale_id, employee["id"], now=now)
                conn.execute(
                    """INSERT INTO payments
                       (tx_id, sale_id, amount_cents, method, source, applied, received_at)
                       VALUES (?, ?, ?, 'cash', 'pos', 1, ?)""",
                    (f"cash_{sale_id}", sale_id, total_cents, now),
                )
            elif body.paymentMethod == "fiado":
                decrement_inventory(conn, sale_id, employee["id"], now=now)
                conn.execute(
                    """INSERT INTO fiado_entries
                       (customer_id, sale_id, kind, amount_cents, note,
                        employee_id, created_at)
                       VALUES (?, ?, 'charge', ?, ?, ?, ?)""",
                    (
                        customer["id"],
                        sale_id,
                        total_cents,
                        body.note,
                        employee["id"],
                        now,
                    ),
                )

        if body.paymentMethod != "pey":
            return _serialize_sale(conn, sale_id)

        # PEY: the sale already exists, so a timeout can always return its id.
        if pey_client is None:
            sale = _mark_pey_failed(
                conn,
                sale_id,
                "PEY no configurado: no se generó el QR.",
            )
            return JSONResponse(
                status_code=502,
                content={
                    "saleId": sale_id,
                    "status": sale["status"] if sale else "failed",
                    "error": "pey_not_configured",
                },
            )

        concept = f"Abarpay {sale_id}"
        try:
            payload = pey_client.create_qr(
                amount_cents=int(_sale_row(conn, sale_id)["charged_cents"]),
                concept=concept,
                expiration_sec=settings.pey_expiration_seconds,
                sale_id=sale_id,
            )
        except PeyTimeout:
            sale = _mark_pey_por_conciliar(
                conn,
                sale_id,
                "PEY no respondió al crear el QR; venta por conciliar.",
            )
            return JSONResponse(
                status_code=202,
                content={
                    "saleId": sale_id,
                    "status": sale["status"] if sale else "por_conciliar",
                    "totalCents": sale["total_cents"] if sale else None,
                    "chargedCents": sale["charged_cents"] if sale else None,
                    "expiresAt": sale["expires_at"] if sale else None,
                    "note": sale["note"] if sale else None,
                },
            )
        except PeyError as exc:
            sale = _mark_pey_failed(
                conn,
                sale_id,
                f"PEY rechazó la creación del QR ({exc.type}).",
            )
            return JSONResponse(
                status_code=502,
                content={
                    "saleId": sale_id,
                    "status": sale["status"] if sale else "failed",
                    "error": "pey_rejected",
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.warning("Unexpected PEY client failure: %s", type(exc).__name__)
            sale = _mark_pey_failed(
                conn,
                sale_id,
                "Error inesperado al crear el QR de PEY.",
            )
            return JSONResponse(
                status_code=502,
                content={
                    "saleId": sale_id,
                    "status": sale["status"] if sale else "failed",
                    "error": "pey_error",
                },
            )

        qr_id = _pey_qr_id(payload)
        if not qr_id:
            sale = _mark_pey_failed(
                conn,
                sale_id,
                "PEY no devolvió un identificador de QR.",
            )
            return JSONResponse(
                status_code=502,
                content={
                    "saleId": sale_id,
                    "status": sale["status"] if sale else "failed",
                    "error": "pey_without_qr",
                },
            )

        with write_transaction(conn):
            conn.execute(
                "UPDATE sales SET pey_qr_id = ? WHERE id = ? AND status = 'pending'",
                (qr_id, sale_id),
            )

        sale_data = _serialize_sale(conn, sale_id)
        sale_data["qrImage"] = _pey_qr_image(payload)
        return sale_data

    @api.get("/sales/{sale_id}")
    def get_sale(
        sale_id: str,
        conn: sqlite3.Connection = Depends(get_db),
        pey_client: Any | None = Depends(get_pey),
    ):
        _sale_or_404(conn, sale_id)
        _reconcile_sale(conn, sale_id, pey_client)
        return _serialize_sale(conn, sale_id)

    @api.post("/sales/{sale_id}/cancel")
    def cancel_sale(sale_id: str, conn: sqlite3.Connection = Depends(get_db)):
        with write_transaction(conn):
            sale = _require_sale(conn, sale_id)
            if sale["status"] == "canceled":
                return sale_to_dict(conn, sale)
            if sale["status"] in {"paid_cash", "paid_pey", "credit"}:
                restore_inventory(conn, sale_id, sale["employee_id"], now=_now())
            note = sale["note"]
            if note:
                note = note + " | Venta cancelada."
            else:
                note = "Venta cancelada."
            conn.execute(
                "UPDATE sales SET status = 'canceled', note = ? WHERE id = ?",
                (note, sale_id),
            )
        return _serialize_sale(conn, sale_id)

    @api.get("/reports/today")
    def reports_today(
        conn: sqlite3.Connection = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ):
        return build_today_report(conn, settings)

    @api.get("/fiado/customers")
    def fiado_customers(conn: sqlite3.Connection = Depends(get_db)):
        rows = conn.execute(
            "SELECT * FROM fiado_customers WHERE store_id = ? ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        return {"customers": [customer_to_dict(conn, row) for row in rows]}

    @api.post("/fiado/customers")
    def create_fiado_customer(body: CustomerIn, conn: sqlite3.Connection = Depends(get_db)):
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="El nombre es obligatorio")
        phone = body.phone.strip() if body.phone else None
        with write_transaction(conn):
            cursor = conn.execute(
                """INSERT INTO fiado_customers (store_id, name, phone, created_at)
                   VALUES (?, ?, ?, ?)""",
                (STORE_ID, name, phone, _now()),
            )
            customer_id = int(cursor.lastrowid)
        return customer_to_dict(conn, _require_customer(conn, customer_id))

    @api.get("/fiado/customers/{customer_id}")
    def fiado_customer(customer_id: int, conn: sqlite3.Connection = Depends(get_db)):
        row = _require_customer(conn, customer_id)
        return customer_to_dict(conn, row, include_entries=True)

    @api.post("/fiado/customers/{customer_id}/abono")
    def fiado_abono(
        customer_id: int,
        body: AbonoIn,
        conn: sqlite3.Connection = Depends(get_db),
    ):
        if body.amountCents <= 0:
            raise HTTPException(status_code=400, detail="El abono debe ser mayor que cero")
        with write_transaction(conn):
            _require_customer(conn, customer_id)
            _require_employee(conn, body.employeeId)
            conn.execute(
                """INSERT INTO fiado_entries
                   (customer_id, sale_id, kind, amount_cents, note,
                    employee_id, created_at)
                   VALUES (?, NULL, 'payment', ?, ?, ?, ?)""",
                (customer_id, body.amountCents, body.note, body.employeeId, _now()),
            )
        return {
            "customerId": customer_id,
            "balanceCents": customer_balance_cents(conn, customer_id),
        }

    @api.post("/inventory/adjust")
    def inventory_adjust(body: AdjustIn, conn: sqlite3.Connection = Depends(get_db)):
        reason = body.reason.strip() or "ajuste"
        with write_transaction(conn):
            _require_employee(conn, body.employeeId)
            _require_product(conn, body.productId)
            conn.execute(
                "UPDATE products SET stock_milli = stock_milli + ? WHERE id = ?",
                (body.deltaMilli, body.productId),
            )
            conn.execute(
                """INSERT INTO inventory_movements
                   (product_id, delta_milli, reason, sale_id, employee_id, created_at)
                   VALUES (?, ?, ?, NULL, ?, ?)""",
                (body.productId, body.deltaMilli, reason, body.employeeId, _now()),
            )
        return product_to_dict(_require_product(conn, body.productId))

    @api.post("/console/login")
    def console_login(body: LoginIn, settings: Settings = Depends(get_settings)):
        if not hmac.compare_digest(
            body.pin.encode("utf-8"), settings.owner_pin.encode("utf-8")
        ):
            raise HTTPException(status_code=401, detail="PIN incorrecto")
        return {"ok": True}

    console = APIRouter(prefix="/api/console", dependencies=[Depends(require_owner)])

    @console.get("/summary")
    def console_summary(
        conn: sqlite3.Connection = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ):
        report = build_today_report(conn, settings)
        employees = conn.execute(
            "SELECT * FROM employees WHERE store_id = ? AND active = 1 ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        recent = conn.execute(
            "SELECT * FROM sales WHERE store_id = ? ORDER BY created_at DESC LIMIT 8",
            (STORE_ID,),
        ).fetchall()
        store = store_row(conn)
        return {
            "store": store_to_dict(store) if store else None,
            "today": report,
            "employees": [employee_to_dict(row) for row in employees],
            "recentSales": [sale_to_dict(conn, row) for row in recent],
            "lowStock": report["lowStock"],
            "fiadoOutstandingCents": report["fiadoOutstandingCents"],
        }

    @console.get("/sales")
    def console_sales(
        limit: int = Query(default=50, ge=1, le=200),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        rows = conn.execute(
            "SELECT * FROM sales WHERE store_id = ? ORDER BY created_at DESC LIMIT ?",
            (STORE_ID, limit),
        ).fetchall()
        return {"items": [sale_to_dict(conn, row) for row in rows]}

    @console.get("/pending")
    def console_pending(conn: sqlite3.Connection = Depends(get_db)):
        rows = conn.execute(
            """SELECT * FROM sales WHERE store_id = ?
               AND status IN ('pending','por_conciliar','failed')
               ORDER BY created_at DESC LIMIT 50""",
            (STORE_ID,),
        ).fetchall()
        return {"items": [sale_to_dict(conn, row) for row in rows]}

    @console.get("/inventory")
    def console_inventory(conn: sqlite3.Connection = Depends(get_db)):
        rows = conn.execute(
            "SELECT * FROM products WHERE store_id = ? ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        return {"items": [product_to_dict(row) for row in rows]}

    @console.get("/webhooks")
    def console_webhooks(
        limit: int = Query(default=20, ge=1, le=200),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        rows = conn.execute(
            """SELECT webhook_id, received_at, outcome FROM webhook_events
               ORDER BY received_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return {
            "items": [
                {
                    "webhookId": row["webhook_id"],
                    "receivedAt": row["received_at"],
                    "outcome": row["outcome"],
                }
                for row in rows
            ]
        }

    @console.get("/fiado")
    def console_fiado(conn: sqlite3.Connection = Depends(get_db)):
        rows = conn.execute(
            "SELECT * FROM fiado_customers WHERE store_id = ? ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        customers = [customer_to_dict(conn, row) for row in rows]
        return {
            "customers": customers,
            "totalOutstandingCents": fiado_outstanding_cents(conn),
        }

    app.include_router(api)
    app.include_router(console)

    @app.post("/webhooks/pey")
    async def pey_webhook(
        request: Request,
        conn: sqlite3.Connection = Depends(get_db),
    ):
        settings: Settings = request.app.state.settings
        if not settings.webhook_configured:
            return JSONResponse(
                status_code=503,
                content={"ok": False, "error": "webhook_not_configured"},
            )

        raw_body = await request.body()
        if not verify_webhook(request.headers, raw_body, settings.pey_webhook_secret):
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "invalid_signature"},
            )

        webhook_id = request.headers.get("webhook-id", "").strip()
        if not webhook_id:
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "invalid_signature"},
            )

        try:
            event = json.loads(raw_body)
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "invalid_json"},
            )
        if not isinstance(event, dict):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "invalid_payload"},
            )

        event_type = event.get("type") or event.get("event")
        if not event_type:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "invalid_payload"},
            )

        if str(event_type) != "codi.qr.payment_received":
            with write_transaction(conn):
                duplicate = conn.execute(
                    "SELECT outcome FROM webhook_events WHERE webhook_id = ?",
                    (webhook_id,),
                ).fetchone()
                if duplicate is not None:
                    return JSONResponse(
                        status_code=200,
                        content={"ok": True, "outcome": "duplicate"},
                    )
                conn.execute(
                    "INSERT INTO webhook_events (webhook_id, received_at, outcome) VALUES (?, ?, 'ignored_event')",
                    (webhook_id, _now()),
                )
            return JSONResponse(
                status_code=200,
                content={"ok": True, "outcome": "ignored_event"},
            )

        data = event.get("data")
        if not isinstance(data, dict):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "invalid_payload"},
            )

        qr_id = data.get("codiQrId")
        transaction_id = data.get("transactionId")
        amount_cents = payload_cents(data.get("amount"))
        if not qr_id or not transaction_id or amount_cents is None:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "invalid_payload"},
            )
        qr_id = str(qr_id)
        transaction_id = str(transaction_id)
        received_at = _now()

        with write_transaction(conn):
            duplicate = conn.execute(
                "SELECT outcome FROM webhook_events WHERE webhook_id = ?",
                (webhook_id,),
            ).fetchone()
            if duplicate is not None:
                return JSONResponse(
                    status_code=200,
                    content={"ok": True, "outcome": "duplicate"},
                )

            sale = conn.execute(
                "SELECT * FROM sales WHERE pey_qr_id = ?", (qr_id,)
            ).fetchone()
            if sale is None:
                conn.execute(
                    "INSERT INTO webhook_events (webhook_id, received_at, outcome) VALUES (?, ?, 'unknown_qr')",
                    (webhook_id, received_at),
                )
                return JSONResponse(
                    status_code=200,
                    content={"ok": True, "outcome": "unknown_qr"},
                )

            result = apply_payment(
                conn,
                sale_id=sale["id"],
                transaction_id=transaction_id,
                amount_cents=amount_cents,
                source="webhook",
                received_at=received_at,
            )
            conn.execute(
                "INSERT INTO webhook_events (webhook_id, received_at, outcome) VALUES (?, ?, ?)",
                (webhook_id, received_at, result["outcome"]),
            )
            current = result["sale"]
            response_body = {
                "ok": True,
                "outcome": result["outcome"],
                "saleId": sale["id"],
                "status": current["status"] if current is not None else None,
            }
            if result["applied"]:
                response_body["applied"] = True
            return JSONResponse(status_code=200, content=response_body)

    @app.get("/console", include_in_schema=False)
    def console_page(request: Request):
        static_dir: Path = request.app.state.settings.static_dir
        page = static_dir / "console.html"
        if not page.exists():
            raise HTTPException(status_code=500, detail="Consola no instalada")
        return FileResponse(
            page,
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/console/", include_in_schema=False)
    def console_page_slash():
        return RedirectResponse(url="/console")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/console")


app = create_app()
