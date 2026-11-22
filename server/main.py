"""Abarpay v1 - FastAPI application.

Public POS endpoints live under /api, the PEY webhook at /webhooks/pey and the
owner demo console at /console. Every request uses its own SQLite connection.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import html
import json
import logging
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Iterator, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .catalog_templates import business_template
from .config import Settings
from .db import (
    DEFAULT_BUSINESS_TYPE,
    DEFAULT_OWNER_NAME,
    PRODUCT_KINDS,
    PRODUCT_UNITS,
    STORE_ID,
    connect,
    initialize_db,
    store_row,
    store_settings_row,
    write_transaction,
)
from .parser import line_total_cents, normalize, parse_count, parse_expense, parse_text
from .payments import apply_payment, restore_inventory, decrement_inventory
from .outbox import (
    SyncError,
    cash_intent_matches,
    catalog_unit_prices,
    ensure_outbox_schema,
    sale_id_from_event,
)
from .pey import PeyClient, PeyError, PeyTimeout, payload_cents, verify_webhook
from .reports import build_today_report, fiado_outstanding_cents, today_expenses_cents
from .serializers import (
    catalog_item_to_dict,
    customer_balance_cents,
    customer_to_dict,
    day_task_to_dict,
    employee_summary_to_dict,
    employee_to_dict,
    expense_to_dict,
    fiado_entry_to_dict,
    product_to_dict,
    sale_to_dict,
    store_to_dict,
)

# I-phase: OIDC identity + offline sync, wired non-breaking with SIMULADO
# defaults so the server boots without real OIDC credentials. Production swaps
# the in-memory store for server/identity_pg.PostgresIdentityStore and a real
# AuthConfig (see server/identity_pg.py).
from .auth import AuthConfig
from .auth_routes import register as register_auth_routes
from .identity import MemoryIdentityStore
from .sync_routes import register as register_sync_routes
from .routes_onboarding import register as register_onboarding_routes
from .routes_till import register as register_till_routes
from .routes_platform import register as register_platform_routes
from .routes_purchasing import register as register_purchasing_routes
from .routes_landing import register as register_landing_routes, landing_page_response
from .routes_fiado import register as register_fiado_routes
from .routes_aggregate import register as register_aggregate_routes
from .routes_analytics import register as register_analytics_routes

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

# v2: invitations, store photo and simulated identity.
INVITE_BASE_URL = "https://abarpay-api.onrender.com"
INVITE_TTL_SECONDS = 7 * 24 * 60 * 60
STORE_PHOTO_FILENAME = "store-photo.jpg"
STORE_PHOTO_DATA_PREFIX = "data:image/jpeg;base64,"
MAX_STORE_PHOTO_BYTES = 5 * 1024 * 1024

# v3.1 product images: only https URLs of at most 500 characters are accepted.
IMAGE_URL_MAX_LENGTH = 500

OWNER_ONLY_DETAIL = "Solo el dueño puede hacer esto"
REPORTS_OWNER_ONLY_DETAIL = "Solo el dueño ve reportes"
INVENTORY_FORBIDDEN_DETAIL = "No tienes permiso para inventario"
INVALID_EMPLOYEE_DETAIL = "Empleado no válido o inactivo"
FIADO_FORBIDDEN_DETAIL = "Tu perfil no puede registrar abonos"

ANDROID_PACKAGE_NAME = "mx.abarpay.mobile"
ANDROID_SHA256_CERT_FINGERPRINT = (
    "f5219d47c4ac345bb4671d546653038a9ca949018ec47e713d2a6f06a4482618"
)


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
        initialize_db(app.state.settings.db_path, seed_catalog=app.state.settings.seed_catalog)
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
    _install_identity_and_sync(app)
    _install_onboarding(app)
    register_till_routes(app)
    register_platform_routes(app)
    register_purchasing_routes(app)
    register_landing_routes(app)
    register_fiado_routes(app)
    register_aggregate_routes(app)
    register_analytics_routes(app)
    return app


def _install_identity_and_sync(app: FastAPI) -> None:
    """Wire the I-phase routers with SIMULADO/test defaults (non-breaking).

    Identity boots on an in-memory store with an empty AuthConfig so the app
    starts without OIDC credentials; sync reuses the existing SQLite path.
    """

    register_auth_routes(
        app,
        store=MemoryIdentityStore(),
        auth_config=AuthConfig(secure_cookies=False, cookie_samesite="lax"),
    )
    register_sync_routes(app)


def _install_onboarding(app: FastAPI) -> None:
    """Wire the M1 onboarding + bank-account router (SIMULADO memory store).

    The default store is the SIMULADO in-memory reference; production swaps in
    server/onboarding.PostgresOnboardingStore via routes_onboarding.register.
    """

    register_onboarding_routes(app)


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
    expectedTotalCents: int | None = Field(default=None, ge=0)
    catalogVersion: int | None = Field(default=None, ge=0, le=0xFFFFFFFF)
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


class StoreProfileIn(BaseModel):
    name: str | None = None
    businessType: str | None = None
    ownerName: str | None = None


class StorePhotoIn(BaseModel):
    dataUrl: str


class EmployeePatchIn(BaseModel):
    name: str | None = None
    nickname: str | None = None
    active: bool | None = None
    canSell: bool | None = None
    canFiado: bool | None = None
    canInventory: bool | None = None


class InviteIn(BaseModel):
    name: str
    canSell: bool = True
    canFiado: bool = True
    canInventory: bool = False


class InviteAcceptIn(BaseModel):
    nickname: str | None = None


class InventorySetIn(BaseModel):
    productId: int
    qtyMilli: int
    note: str | None = None


class InventoryVoiceIn(BaseModel):
    text: str


class SupportTicketIn(BaseModel):
    saleId: str | None = None
    note: str | None = None


class SupportTicketPatchIn(BaseModel):
    status: Literal["open", "resolved"] | None = None
    note: str | None = None


# v3 catalog, templates, day tasks and expenses -----------------------------


class CatalogItemIn(BaseModel):
    name: str
    unit: str
    priceCents: int
    aliases: list[str] | None = None
    stockMilli: int | None = None
    unlimitedStock: bool | None = None
    kind: str | None = None
    category: str | None = None
    durationMinutes: int | None = None
    quick: bool | None = None
    imageUrl: str | None = None


class CatalogItemPatchIn(BaseModel):
    name: str | None = None
    unit: str | None = None
    priceCents: int | None = None
    aliases: list[str] | None = None
    stockMilli: int | None = None
    unlimitedStock: bool | None = None
    kind: str | None = None
    category: str | None = None
    durationMinutes: int | None = None
    quick: bool | None = None
    imageUrl: str | None = None


class TemplateApplyIn(BaseModel):
    businessType: str


class TaskPatchIn(BaseModel):
    assignedEmployeeId: int | None = None
    active: bool | None = None
    title: str | None = None


class ExpenseIn(BaseModel):
    amountCents: int
    note: str | None = None


class ExpenseVoiceIn(BaseModel):
    text: str


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


# v2 simulated identity ------------------------------------------------------


def _employee_row(
    conn: sqlite3.Connection, employee_id: int, *, only_active: bool = False
) -> sqlite3.Row | None:
    query = "SELECT * FROM employees WHERE id = ? AND store_id = ?"
    if only_active:
        query += " AND active = 1"
    return conn.execute(query, (employee_id, STORE_ID)).fetchone()


def _optional_employee(
    conn: sqlite3.Connection, employee_id: int | None
) -> sqlite3.Row | None:
    """Validate the optional X-Employee-Id header.

    No header keeps the open v1 behavior (console and scripts). A header that
    points to an unknown or inactive employee is rejected.
    """

    if employee_id is None:
        return None
    employee = _employee_row(conn, employee_id, only_active=True)
    if employee is None:
        raise HTTPException(status_code=403, detail=INVALID_EMPLOYEE_DETAIL)
    return employee


def _require_owner_employee(
    conn: sqlite3.Connection, employee_id: int | None
) -> sqlite3.Row | None:
    employee = _optional_employee(conn, employee_id)
    if employee is not None and employee["role"] != "owner":
        raise HTTPException(status_code=403, detail=OWNER_ONLY_DETAIL)
    return employee


def _require_inventory_employee(
    conn: sqlite3.Connection, employee_id: int | None
) -> sqlite3.Row | None:
    employee = _optional_employee(conn, employee_id)
    if (
        employee is not None
        and employee["role"] != "owner"
        and not employee["can_inventory"]
    ):
        raise HTTPException(status_code=403, detail=INVENTORY_FORBIDDEN_DETAIL)
    return employee


# v3.2 fiado payments -------------------------------------------------------


def _require_fiado_employee(
    conn: sqlite3.Connection, employee_id: int | None
) -> sqlite3.Row | None:
    """Gate abonos/history on canFiado.

    The owner can always register an abono. No header keeps the open v1
    behavior (console and scripts); a header for an employee without the
    canFiado permission is rejected with the app's Spanish copy.
    """

    employee = _optional_employee(conn, employee_id)
    if (
        employee is not None
        and employee["role"] != "owner"
        and not employee["can_fiado"]
    ):
        raise HTTPException(status_code=403, detail=FIADO_FORBIDDEN_DETAIL)
    return employee


def _fiado_entry_rows(
    conn: sqlite3.Connection, customer_id: int
) -> list[sqlite3.Row]:
    """Movements of one customer, newest first (deterministic on ties)."""

    return conn.execute(
        """SELECT e.id, e.kind, e.amount_cents, e.note, e.employee_id,
                  e.created_at, emp.name AS employee_name
           FROM fiado_entries e
           LEFT JOIN employees emp ON emp.id = e.employee_id
           WHERE e.customer_id = ?
           ORDER BY e.created_at DESC, e.id DESC""",
        (customer_id,),
    ).fetchall()


def _fiado_entries_payload(
    conn: sqlite3.Connection, customer_id: int
) -> list[dict[str, Any]]:
    return [
        fiado_entry_to_dict(row) for row in _fiado_entry_rows(conn, customer_id)
    ]


# v2 support tickets --------------------------------------------------------


def _support_ticket_row(
    conn: sqlite3.Connection, ticket_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM support_tickets WHERE id = ? AND store_id = ?",
        (ticket_id, STORE_ID),
    ).fetchone()


def _support_ticket_sale_row(
    conn: sqlite3.Connection, sale_id: str | None
) -> sqlite3.Row | None:
    """Live sale context for a ticket: status, totals and the PEY tx id.

    The contract keeps the sale context out of the ticket row, so every read
    resolves it from sales (with the employee name used as "reported by" when
    the reporter is not known from the current request header).
    """

    if sale_id is None:
        return None
    return conn.execute(
        """SELECT s.status, s.total_cents, s.charged_cents, s.pey_tx_id,
                  e.name AS employee_name
           FROM sales s LEFT JOIN employees e ON e.id = s.employee_id
           WHERE s.id = ?""",
        (sale_id,),
    ).fetchone()


def _support_ticket_payload(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    reported_by_name: str | None = None,
    include_resolved_at: bool = False,
) -> dict[str, Any]:
    """Ticket JSON per the v2 contract.

    POST responses use the contract's create shape (no resolvedAt); list and
    PATCH responses add resolvedAt. A ticket without a sale has no sale
    context at all.
    """

    sale = _support_ticket_sale_row(conn, row["sale_id"])
    if reported_by_name is None and sale is not None:
        reported_by_name = sale["employee_name"]
    payload: dict[str, Any] = {
        "id": row["id"],
        "saleId": row["sale_id"],
        "saleStatus": sale["status"] if sale is not None else None,
        "saleTotalCents": sale["total_cents"] if sale is not None else None,
        "chargedCents": sale["charged_cents"] if sale is not None else None,
        "peyTxId": sale["pey_tx_id"] if sale is not None else None,
        "note": row["note"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "reportedByName": reported_by_name,
    }
    if include_resolved_at:
        payload["resolvedAt"] = row["resolved_at"]
    return payload


# v2 store profile ----------------------------------------------------------


def _store_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    store = store_row(conn)
    if store is None:
        raise HTTPException(status_code=500, detail="Tienda no inicializada")
    settings_row = store_settings_row(conn)
    return {
        "storeId": store["id"],
        "name": store["name"],
        "businessType": (
            settings_row["business_type"]
            if settings_row is not None
            else DEFAULT_BUSINESS_TYPE
        ),
        "ownerName": (
            settings_row["owner_name"]
            if settings_row is not None
            else DEFAULT_OWNER_NAME
        ),
    }


# v2 catalog / inventory helpers -------------------------------------------


def _catalog_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """SELECT id, name, aliases, unit, price_cents
               FROM products WHERE store_id = ? ORDER BY id""",
            (STORE_ID,),
        ).fetchall()
    ]


def _validate_product_unit(unit: str | None) -> str:
    value = (unit or "").strip().lower()
    if value not in PRODUCT_UNITS:
        raise HTTPException(
            status_code=400,
            detail="Unidad no válida. Usa: " + ", ".join(PRODUCT_UNITS),
        )
    return value


def _validate_product_kind(kind: str | None) -> str:
    value = (kind or "producto").strip().lower()
    if value not in PRODUCT_KINDS:
        raise HTTPException(
            status_code=400,
            detail="Tipo no válido. Usa: " + ", ".join(PRODUCT_KINDS),
        )
    return value


def _validate_image_url(value: str | None) -> str | None:
    """Optional product image URL: https only, at most 500 characters.

    A missing or blank value clears the image (NULL); anything else must be a
    real https URL. The check is deliberately narrow: we never fetch or build
    the URL here, the client loads it directly.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not text.lower().startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="La URL de imagen debe empezar con https://",
        )
    if len(text) > IMAGE_URL_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=(
                "La URL de imagen no puede pasar de "
                f"{IMAGE_URL_MAX_LENGTH} caracteres"
            ),
        )
    return text


def _catalog_search_text(row: sqlite3.Row) -> str:
    """Accent/hyphen-insensitive text used by the catalog search."""

    names = [str(row["name"] or "")]
    raw_aliases = row["aliases"]
    if isinstance(raw_aliases, str):
        try:
            raw_aliases = json.loads(raw_aliases)
        except (TypeError, ValueError):
            raw_aliases = []
    if isinstance(raw_aliases, list):
        names.extend(str(alias) for alias in raw_aliases)
    return normalize(" ".join(names)).replace("-", " ")


def _catalog_item_values(body: CatalogItemIn) -> dict[str, Any]:
    """Validate a new catalog item and return the DB column values."""

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    unit = _validate_product_unit(body.unit)
    kind = _validate_product_kind(body.kind)
    if body.priceCents < 0:
        raise HTTPException(status_code=400, detail="El precio no puede ser negativo")
    stock = 0 if body.stockMilli is None else int(body.stockMilli)
    if stock < 0:
        raise HTTPException(status_code=400, detail="El stock no puede ser negativo")
    duration = body.durationMinutes
    if duration is not None and duration < 0:
        raise HTTPException(
            status_code=400, detail="La duración no puede ser negativa"
        )
    unlimited = body.unlimitedStock
    if unlimited is None:
        # Services and dishes do not carry inventory by default.
        unlimited = kind != "producto"
    category = (body.category or "").strip() or None
    aliases = [str(alias).strip() for alias in (body.aliases or []) if str(alias).strip()]
    return {
        "name": name,
        "unit": unit,
        "kind": kind,
        "price_cents": int(body.priceCents),
        "stock_milli": 0 if unlimited else stock,
        "unlimited_stock": 1 if unlimited else 0,
        "low_stock_milli": 0 if unlimited else 5000,
        "category": category,
        "duration_minutes": duration,
        "aliases": aliases,
        "quick": 1 if body.quick else 0,
        "image_url": _validate_image_url(body.imageUrl),
    }


def _insert_catalog_item(
    conn: sqlite3.Connection, values: dict[str, Any]
) -> int:
    cursor = conn.execute(
        """INSERT INTO products
               (store_id, name, aliases, unit, price_cents, stock_milli,
                low_stock_milli, quick, unlimited_stock, kind, category,
                duration_minutes, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            STORE_ID,
            values["name"],
            json.dumps(values["aliases"], ensure_ascii=False),
            values["unit"],
            values["price_cents"],
            values["stock_milli"],
            values["low_stock_milli"],
            values["quick"],
            values["unlimited_stock"],
            values["kind"],
            values["category"],
            values["duration_minutes"],
            values["image_url"],
        ),
    )
    return int(cursor.lastrowid)


def _catalog_item_row(
    conn: sqlite3.Connection, product_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM products WHERE id = ? AND store_id = ?",
        (product_id, STORE_ID),
    ).fetchone()


# v3 day tasks --------------------------------------------------------------


def _day_task_row(
    conn: sqlite3.Connection, task_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT t.*, e.name AS assigned_employee_name
           FROM day_tasks t
           LEFT JOIN employees e ON e.id = t.assigned_employee_id
           WHERE t.id = ? AND t.store_id = ?""",
        (task_id, STORE_ID),
    ).fetchone()


# v3 expenses ---------------------------------------------------------------


def _expense_row(
    conn: sqlite3.Connection, expense_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT x.*, e.name AS employee_name
           FROM expenses x
           LEFT JOIN employees e ON e.id = x.employee_id
           WHERE x.id = ? AND x.store_id = ?""",
        (expense_id, STORE_ID),
    ).fetchone()


def _inventory_value_cents(price_cents: int, stock_milli: int) -> int:
    """round(priceCents * stockMilli / 1000), half up, also for negatives."""

    product = int(price_cents) * int(stock_milli)
    if product >= 0:
        return (product + 500) // 1000
    return -((-product + 500) // 1000)


def _inventory_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT p.*,
                  m.created_at AS last_updated_at,
                  m.employee_id AS last_updated_by_id,
                  e.name AS last_updated_by_name,
                  e.nickname AS last_updated_by_nickname
           FROM products p
           LEFT JOIN inventory_movements m ON m.id = (
               SELECT m2.id FROM inventory_movements m2
               WHERE m2.product_id = p.id
               ORDER BY m2.created_at DESC, m2.id DESC LIMIT 1)
           LEFT JOIN employees e ON e.id = m.employee_id
           WHERE p.store_id = ?
           ORDER BY p.id""",
        (STORE_ID,),
    ).fetchall()
    items: list[dict[str, Any]] = []
    total_value_cents = 0
    for row in rows:
        unlimited = bool(row["unlimited_stock"])
        value_cents = (
            0
            if unlimited
            else _inventory_value_cents(row["price_cents"], row["stock_milli"])
        )
        total_value_cents += value_cents
        items.append(
            {
                "productId": row["id"],
                "name": row["name"],
                "unit": row["unit"],
                "priceCents": row["price_cents"],
                "stockMilli": row["stock_milli"],
                "unlimitedStock": unlimited,
                "valueCents": value_cents,
                "lastUpdatedAt": row["last_updated_at"],
                "lastUpdatedById": row["last_updated_by_id"],
                "lastUpdatedByName": row["last_updated_by_name"],
                "lastUpdatedByNickname": row["last_updated_by_nickname"],
            }
        )
    return {"items": items, "totalValueCents": total_value_cents}


# v2 invitations ------------------------------------------------------------


def _invite_payload(
    conn: sqlite3.Connection, invite: sqlite3.Row, employee: sqlite3.Row
) -> dict[str, Any]:
    store = store_row(conn)
    settings_row = store_settings_row(conn)
    return {
        "token": invite["token"],
        "employeeId": employee["id"],
        "name": employee["name"],
        "nickname": employee["nickname"],
        "role": employee["role"],
        "storeName": store["name"] if store is not None else "",
        "businessType": (
            settings_row["business_type"]
            if settings_row is not None
            else DEFAULT_BUSINESS_TYPE
        ),
        "canSell": bool(employee["can_sell"]),
        "canFiado": bool(employee["can_fiado"]),
        "canInventory": bool(employee["can_inventory"]),
    }


def _require_invite(
    conn: sqlite3.Connection, token: str
) -> tuple[sqlite3.Row, sqlite3.Row]:
    invite = conn.execute(
        "SELECT * FROM invites WHERE token = ?", (token,)
    ).fetchone()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")
    if invite["accepted"]:
        raise HTTPException(
            status_code=410, detail="La invitación ya fue aceptada"
        )
    if float(invite["expires_at"]) < _now():
        raise HTTPException(status_code=404, detail="La invitación expiró")
    employee = _employee_row(conn, int(invite["employee_id"]))
    if employee is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return invite, employee


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
        profile = _store_profile(conn)
        employees = conn.execute(
            "SELECT * FROM employees WHERE store_id = ? AND active = 1 ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        products = conn.execute(
            "SELECT * FROM products WHERE store_id = ? ORDER BY id",
            (STORE_ID,),
        ).fetchall()
        return {
            "store": {
                "id": profile["storeId"],
                "name": profile["name"],
                "businessType": profile["businessType"],
                "ownerName": profile["ownerName"],
            },
            "employees": [employee_summary_to_dict(row) for row in employees],
            "products": [product_to_dict(row) for row in products],
            "demoMode": settings.modo_demo,
            "ai": "local",
        }

    # v2 store profile -----------------------------------------------------

    @api.get("/store/profile")
    def get_store_profile(conn: sqlite3.Connection = Depends(get_db)):
        return _store_profile(conn)

    @api.put("/store/profile")
    def update_store_profile(
        body: StoreProfileIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)

        name = None if body.name is None else body.name.strip()
        if name is not None and not name:
            raise HTTPException(
                status_code=400, detail="El nombre de la tienda no puede estar vacío"
            )
        business_type = (
            None if body.businessType is None else body.businessType.strip()
        )
        owner_name = None if body.ownerName is None else body.ownerName.strip()
        if owner_name is not None and not owner_name:
            raise HTTPException(
                status_code=400, detail="El nombre del dueño no puede estar vacío"
            )

        with write_transaction(conn):
            # The settings row exists on every initialized database; the
            # INSERT OR IGNORE keeps this safe on old databases.
            conn.execute(
                """INSERT OR IGNORE INTO store_settings
                       (store_id, business_type, owner_name)
                   VALUES (?, ?, ?)""",
                (STORE_ID, DEFAULT_BUSINESS_TYPE, DEFAULT_OWNER_NAME),
            )
            if name is not None:
                conn.execute(
                    "UPDATE stores SET name = ? WHERE id = ?", (name, STORE_ID)
                )
            if business_type is not None:
                conn.execute(
                    "UPDATE store_settings SET business_type = ? WHERE store_id = ?",
                    (business_type, STORE_ID),
                )
            if owner_name is not None:
                conn.execute(
                    "UPDATE store_settings SET owner_name = ? WHERE store_id = ?",
                    (owner_name, STORE_ID),
                )
        return _store_profile(conn)

    @api.post("/store/photo")
    def upload_store_photo(
        body: StorePhotoIn,
        settings: Settings = Depends(get_settings),
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        data_url = body.dataUrl.strip()
        if not data_url.startswith(STORE_PHOTO_DATA_PREFIX):
            raise HTTPException(
                status_code=400, detail="La foto debe venir como data:image/jpeg;base64,..."
            )
        encoded = data_url[len(STORE_PHOTO_DATA_PREFIX) :]
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=400, detail="La foto no está en base64 válido"
            )
        if not payload:
            raise HTTPException(status_code=400, detail="La foto está vacía")
        if len(payload) > MAX_STORE_PHOTO_BYTES:
            raise HTTPException(
                status_code=400, detail="La foto no puede pesar más de 5 MB"
            )
        photo_path = Path(settings.db_path).parent / STORE_PHOTO_FILENAME
        photo_path.parent.mkdir(parents=True, exist_ok=True)
        # Write through a temporary file so a crash never leaves a half photo.
        temporary = photo_path.with_name(photo_path.name + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(photo_path)
        return {"ok": True}

    @api.get("/store/photo")
    def get_store_photo(settings: Settings = Depends(get_settings)):
        photo_path = Path(settings.db_path).parent / STORE_PHOTO_FILENAME
        if not photo_path.is_file():
            raise HTTPException(status_code=404, detail="Sin foto del negocio")
        return FileResponse(
            photo_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    # v2 employees ----------------------------------------------------------

    @api.get("/employees")
    def list_employees(
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        rows = conn.execute(
            "SELECT * FROM employees WHERE store_id = ? ORDER BY id", (STORE_ID,)
        ).fetchall()
        return {"items": [employee_to_dict(row) for row in rows]}

    @api.patch("/employees/{employee_id}")
    def patch_employee(
        employee_id: int,
        body: EmployeePatchIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        employee = _employee_row(conn, employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")

        updates: dict[str, Any] = {}
        if body.name is not None:
            name = body.name.strip()
            if not name:
                raise HTTPException(
                    status_code=400, detail="El nombre no puede estar vacío"
                )
            updates["name"] = name
        if body.nickname is not None:
            nickname = body.nickname.strip()
            updates["nickname"] = nickname or None
        if body.active is not None:
            updates["active"] = 1 if body.active else 0
        if body.canSell is not None:
            updates["can_sell"] = 1 if body.canSell else 0
        if body.canFiado is not None:
            updates["can_fiado"] = 1 if body.canFiado else 0
        if body.canInventory is not None:
            updates["can_inventory"] = 1 if body.canInventory else 0

        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            with write_transaction(conn):
                conn.execute(
                    f"UPDATE employees SET {assignments} WHERE id = ? AND store_id = ?",
                    (*updates.values(), employee_id, STORE_ID),
                )
        updated = _employee_row(conn, employee_id)
        assert updated is not None
        return employee_to_dict(updated)

    # v2 invitations --------------------------------------------------------

    @api.post("/employees/invites")
    def create_employee_invite(
        body: InviteIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        name = body.name.strip()
        if not name:
            raise HTTPException(
                status_code=400, detail="El nombre del empleado es obligatorio"
            )
        token = secrets.token_hex(16)
        now = _now()
        with write_transaction(conn):
            cursor = conn.execute(
                """INSERT INTO employees
                       (store_id, name, nickname, role, active,
                        can_sell, can_fiado, can_inventory)
                   VALUES (?, ?, NULL, 'employee', 0, ?, ?, ?)""",
                (
                    STORE_ID,
                    name,
                    1 if body.canSell else 0,
                    1 if body.canFiado else 0,
                    1 if body.canInventory else 0,
                ),
            )
            employee_id = int(cursor.lastrowid)
            conn.execute(
                """INSERT INTO invites
                       (token, employee_id, created_at, expires_at, accepted)
                   VALUES (?, ?, ?, ?, 0)""",
                (token, employee_id, now, now + INVITE_TTL_SECONDS),
            )
        return {
            "token": token,
            "employeeId": employee_id,
            "url": f"{INVITE_BASE_URL}/invite/{token}",
        }

    @api.get("/employees/invites/{token}")
    def get_employee_invite(token: str, conn: sqlite3.Connection = Depends(get_db)):
        invite, employee = _require_invite(conn, token)
        return _invite_payload(conn, invite, employee)

    @api.post("/employees/invites/{token}/accept")
    def accept_employee_invite(
        token: str,
        body: InviteAcceptIn,
        conn: sqlite3.Connection = Depends(get_db),
    ):
        invite, employee = _require_invite(conn, token)
        nickname = body.nickname.strip() if body.nickname else ""
        with write_transaction(conn):
            conn.execute(
                "UPDATE employees SET active = 1, nickname = ? WHERE id = ? AND store_id = ?",
                (nickname or None, employee["id"], STORE_ID),
            )
            conn.execute(
                "UPDATE invites SET accepted = 1 WHERE token = ?", (token,)
            )
        accepted = _employee_row(conn, int(employee["id"]))
        assert accepted is not None
        return employee_to_dict(accepted)

    @api.delete("/employees/invites/{token}")
    def delete_employee_invite(
        token: str,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        invite = conn.execute(
            "SELECT * FROM invites WHERE token = ?", (token,)
        ).fetchone()
        if invite is None:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        if invite["accepted"]:
            raise HTTPException(
                status_code=409, detail="La invitación ya fue aceptada"
            )
        with write_transaction(conn):
            conn.execute("DELETE FROM invites WHERE token = ?", (token,))
            # Only pending (inactive) employees are removed here; accepted
            # employees keep their history and are deactivated from the app.
            conn.execute(
                "DELETE FROM employees WHERE id = ? AND store_id = ? AND active = 0",
                (invite["employee_id"], STORE_ID),
            )
        return {"ok": True}

    # v2 inventory ----------------------------------------------------------

    @api.get("/inventory")
    def get_inventory(conn: sqlite3.Connection = Depends(get_db)):
        return _inventory_payload(conn)

    @api.post("/inventory/set")
    def inventory_set(
        body: InventorySetIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        with write_transaction(conn):
            employee = _require_inventory_employee(conn, x_employee_id)
            product = _require_product(conn, body.productId)
            if product["unlimited_stock"]:
                raise HTTPException(
                    status_code=400,
                    detail="Este producto tiene inventario sin límite",
                )
            target = int(body.qtyMilli)
            delta = target - int(product["stock_milli"])
            note = (body.note or "").strip() or "set"
            conn.execute(
                "UPDATE products SET stock_milli = ? WHERE id = ?",
                (target, product["id"]),
            )
            conn.execute(
                """INSERT INTO inventory_movements
                       (product_id, delta_milli, reason, sale_id, employee_id, created_at)
                   VALUES (?, ?, ?, NULL, ?, ?)""",
                (
                    product["id"],
                    delta,
                    note,
                    employee["id"] if employee is not None else None,
                    _now(),
                ),
            )
        return product_to_dict(_require_product(conn, body.productId))

    @api.post("/inventory/voice")
    def inventory_voice(
        body: InventoryVoiceIn, conn: sqlite3.Connection = Depends(get_db)
    ):
        # SIMULADO: only interprets the phrase; the app confirms and calls /set.
        return parse_count(body.text, _catalog_rows(conn))


    # v3 catalog ------------------------------------------------------------

    @api.get("/catalog")
    def list_catalog(
        q: str | None = None,
        category: str | None = None,
        kind: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        # Public like bootstrap: the app needs the catalog after onboarding.
        kind_value: str | None = None
        if kind is not None and kind.strip():
            kind_value = _validate_product_kind(kind)
        category_value = (category or "").strip() or None
        query = "SELECT * FROM products WHERE store_id = ?"
        params: list[Any] = [STORE_ID]
        if kind_value is not None:
            query += " AND kind = ?"
            params.append(kind_value)
        if category_value is not None:
            query += " AND category = ? COLLATE NOCASE"
            params.append(category_value)
        rows = conn.execute(
            query + " ORDER BY name COLLATE NOCASE ASC, id ASC", params
        ).fetchall()
        needle = normalize(q or "").replace("-", " ").strip() if q else ""
        if needle:
            rows = [row for row in rows if needle in _catalog_search_text(row)]
        total = len(rows)
        page = rows[offset : offset + limit]
        return {
            "items": [catalog_item_to_dict(row) for row in page],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @api.post("/catalog")
    def create_catalog_item(
        body: CatalogItemIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        values = _catalog_item_values(body)
        with write_transaction(conn):
            product_id = _insert_catalog_item(conn, values)
        return catalog_item_to_dict(_require_product(conn, product_id))

    @api.patch("/catalog/{product_id}")
    def patch_catalog_item(
        product_id: int,
        body: CatalogItemPatchIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        product = _require_product(conn, product_id)
        fields = body.model_fields_set
        updates: dict[str, Any] = {}
        if "name" in fields:
            name = (body.name or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="El nombre es obligatorio")
            updates["name"] = name
        if "unit" in fields:
            updates["unit"] = _validate_product_unit(body.unit)
        if "kind" in fields:
            updates["kind"] = _validate_product_kind(body.kind)
        if "priceCents" in fields:
            if body.priceCents is None or int(body.priceCents) < 0:
                raise HTTPException(
                    status_code=400, detail="El precio no puede ser negativo"
                )
            updates["price_cents"] = int(body.priceCents)
        if "durationMinutes" in fields:
            duration = body.durationMinutes
            if duration is not None and duration < 0:
                raise HTTPException(
                    status_code=400, detail="La duración no puede ser negativa"
                )
            updates["duration_minutes"] = duration
        if "category" in fields:
            updates["category"] = (body.category or "").strip() or None
        if "imageUrl" in fields:
            updates["image_url"] = _validate_image_url(body.imageUrl)
        if "aliases" in fields:
            aliases = [
                str(alias).strip()
                for alias in (body.aliases or [])
                if str(alias).strip()
            ]
            updates["aliases"] = json.dumps(aliases, ensure_ascii=False)
        if "quick" in fields:
            updates["quick"] = 1 if body.quick else 0
        if "stockMilli" in fields:
            if body.stockMilli is None or int(body.stockMilli) < 0:
                raise HTTPException(
                    status_code=400, detail="El stock no puede ser negativo"
                )
            updates["stock_milli"] = int(body.stockMilli)
            if "unlimitedStock" not in fields:
                updates["unlimited_stock"] = 0
        if "unlimitedStock" in fields:
            unlimited = bool(body.unlimitedStock)
            updates["unlimited_stock"] = 1 if unlimited else 0
            if unlimited:
                updates["stock_milli"] = 0
        elif "kind" in fields and updates["kind"] != "producto":
            # A service/dish has no inventory unless the owner says otherwise.
            updates["unlimited_stock"] = 1
            updates["stock_milli"] = 0
        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            with write_transaction(conn):
                conn.execute(
                    f"UPDATE products SET {assignments} WHERE id = ? AND store_id = ?",
                    (*updates.values(), product_id, STORE_ID),
                )
        updated = _catalog_item_row(conn, product_id)
        assert updated is not None
        return catalog_item_to_dict(updated)

    @api.delete("/catalog/{product_id}")
    def delete_catalog_item(
        product_id: int,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        with write_transaction(conn):
            _require_product(conn, product_id)
            sales_count = conn.execute(
                "SELECT COUNT(*) AS n FROM sale_items WHERE product_id = ?",
                (product_id,),
            ).fetchone()["n"]
            movements = conn.execute(
                "SELECT COUNT(*) AS n FROM inventory_movements WHERE product_id = ?",
                (product_id,),
            ).fetchone()["n"]
            if sales_count or movements:
                raise HTTPException(
                    status_code=409,
                    detail="No se puede borrar: el producto tiene ventas o movimientos",
                )
            # A barcode only points at the product; drop it with the product.
            conn.execute("DELETE FROM barcodes WHERE product_id = ?", (product_id,))
            conn.execute(
                "DELETE FROM products WHERE id = ? AND store_id = ?",
                (product_id, STORE_ID),
            )
        return {"ok": True, "id": product_id}

    @api.post("/catalog/templates/apply")
    def apply_catalog_template(
        body: TemplateApplyIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        template = business_template(body.businessType)
        if template is None:
            raise HTTPException(
                status_code=400,
                detail="Tipo de negocio no válido. Usa: tiendita, tortilleria, taqueria, "
                "comida-corrida, peluqueria, estetica, fondita u otro",
            )
        with write_transaction(conn):
            existing = conn.execute(
                "SELECT COUNT(*) AS n FROM products WHERE store_id = ?", (STORE_ID,)
            ).fetchone()["n"]
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="La tienda ya tiene catálogo; la plantilla solo aplica a un negocio nuevo",
                )
            items_created = 0
            for item in template["items"]:
                _insert_catalog_item(
                    conn,
                    {
                        "name": item["name"],
                        "unit": item["unit"],
                        "kind": item["kind"],
                        "price_cents": item["priceCents"],
                        "stock_milli": item["stockMilli"],
                        "unlimited_stock": 1 if item["unlimitedStock"] else 0,
                        "low_stock_milli": item["lowStockMilli"],
                        "category": item["category"],
                        "duration_minutes": item["durationMinutes"],
                        "aliases": item["aliases"],
                        "quick": 1 if item["quick"] else 0,
                        "image_url": item.get("imageUrl"),
                    },
                )
                items_created += 1
            tasks_created = 0
            for task in template["tasks"]:
                cursor = conn.execute(
                    """INSERT INTO day_tasks
                           (store_id, key, title, assigned_employee_id, active)
                       VALUES (?, ?, ?, NULL, 1)
                       ON CONFLICT(store_id, key) DO NOTHING""",
                    (STORE_ID, task["key"], task["title"]),
                )
                if cursor.rowcount:
                    tasks_created += 1
        return {
            "businessType": template["businessType"],
            "applied": True,
            "itemsCreated": items_created,
            "tasksCreated": tasks_created,
            "source": template["source"],
        }

    # v3 day tasks ----------------------------------------------------------

    @api.get("/tasks")
    def list_tasks(
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        employee = _optional_employee(conn, x_employee_id)
        query = """SELECT t.*, e.name AS assigned_employee_name
                   FROM day_tasks t
                   LEFT JOIN employees e ON e.id = t.assigned_employee_id
                   WHERE t.store_id = ?"""
        params: list[Any] = [STORE_ID]
        if employee is not None and employee["role"] != "owner":
            # An employee only sees their own active, assigned tasks.
            query += " AND t.assigned_employee_id = ? AND t.active = 1"
            params.append(employee["id"])
        query += " ORDER BY t.id ASC"
        rows = conn.execute(query, params).fetchall()
        return {"items": [day_task_to_dict(row) for row in rows]}

    @api.patch("/tasks/{task_id}")
    def patch_task(
        task_id: int,
        body: TaskPatchIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        if _day_task_row(conn, task_id) is None:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        fields = body.model_fields_set
        updates: dict[str, Any] = {}
        if "assignedEmployeeId" in fields:
            if body.assignedEmployeeId is None:
                updates["assigned_employee_id"] = None
            else:
                assigned = _employee_row(
                    conn, int(body.assignedEmployeeId), only_active=True
                )
                if assigned is None:
                    raise HTTPException(status_code=400, detail=INVALID_EMPLOYEE_DETAIL)
                updates["assigned_employee_id"] = int(body.assignedEmployeeId)
        if "active" in fields:
            if body.active is None:
                raise HTTPException(
                    status_code=400, detail="active debe ser verdadero o falso"
                )
            updates["active"] = 1 if body.active else 0
        if "title" in fields:
            title = (body.title or "").strip()
            if not title:
                raise HTTPException(
                    status_code=400, detail="El título no puede estar vacío"
                )
            updates["title"] = title
        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            with write_transaction(conn):
                conn.execute(
                    f"UPDATE day_tasks SET {assignments} WHERE id = ? AND store_id = ?",
                    (*updates.values(), task_id, STORE_ID),
                )
        row = _day_task_row(conn, task_id)
        assert row is not None
        return day_task_to_dict(row)

    # v3 expenses -----------------------------------------------------------

    @api.post("/expenses")
    def create_expense(
        body: ExpenseIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        # Any active employee can register an expense; no header keeps the
        # open v1 behavior for scripts and the console.
        employee = _optional_employee(conn, x_employee_id)
        if body.amountCents <= 0:
            raise HTTPException(
                status_code=400, detail="El gasto debe ser mayor que cero"
            )
        note = (body.note or "").strip() or None
        with write_transaction(conn):
            cursor = conn.execute(
                """INSERT INTO expenses
                       (store_id, employee_id, amount_cents, note, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    STORE_ID,
                    employee["id"] if employee is not None else None,
                    int(body.amountCents),
                    note,
                    _now(),
                ),
            )
            expense_id = int(cursor.lastrowid)
        row = _expense_row(conn, expense_id)
        assert row is not None
        return expense_to_dict(row)

    @api.post("/expenses/voice")
    def expense_voice(body: ExpenseVoiceIn):
        # SIMULADO: only interprets the phrase. The app confirms and then calls
        # POST /api/expenses; nothing is saved here.
        return parse_expense(body.text)

    @api.get("/expenses")
    def list_expenses(
        limit: int = Query(default=50, ge=1, le=500),
        conn: sqlite3.Connection = Depends(get_db),
        settings: Settings = Depends(get_settings),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        rows = conn.execute(
            """SELECT x.*, e.name AS employee_name
               FROM expenses x
               LEFT JOIN employees e ON e.id = x.employee_id
               WHERE x.store_id = ?
               ORDER BY x.created_at DESC, x.id DESC
               LIMIT ?""",
            (STORE_ID, limit),
        ).fetchall()
        return {
            "items": [expense_to_dict(row) for row in rows],
            "totalTodayCents": today_expenses_cents(conn, settings),
        }

    @api.post("/cart/parse")
    def cart_parse(body: CartParseIn, conn: sqlite3.Connection = Depends(get_db)):
        return parse_text(body.text, _catalog_rows(conn))

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
        request: Request,
        conn: sqlite3.Connection = Depends(get_db),
        settings: Settings = Depends(get_settings),
        pey_client: Any | None = Depends(get_pey),
        x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ):
        merged: dict[int, int] = {}
        for item in body.items:
            if item.qtyMilli <= 0:
                raise HTTPException(status_code=400, detail="qtyMilli debe ser mayor que cero")
            merged[item.productId] = merged.get(item.productId, 0) + item.qtyMilli
        if not merged:
            raise HTTPException(status_code=400, detail="La venta no tiene productos")

        # Multi-tenant collection routing: a PEY/CoDi charge must resolve the
        # tenant's ACTIVE bank account (SIMULADO tenant identity via X-Tenant-Id,
        # mirroring routes_onboarding). Without the header the legacy
        # single-tenant demo path is used and no bankAccountId is sent.
        bank_account_id: str | None = None
        if body.paymentMethod == "pey" and x_tenant_id:
            service = getattr(request.app.state, "onboarding_service", None)
            active = (
                service.resolve_active_bank_account(x_tenant_id)
                if service is not None
                else None
            )
            if active is None:
                return JSONResponse(
                    status_code=409,
                    content={
                        "code": "NO_ACTIVE_BANK_ACCOUNT",
                        "message": "No hay cuenta bancaria activa para cobrar",
                    },
                )
            bank_account_id = active.id

        idempotent_cash = (
            body.paymentMethod == "cash"
            and bool(idempotency_key)
            and bool(idempotency_key.strip())
        )
        sale_id = (
            sale_id_from_event(idempotency_key)
            if idempotent_cash
            else "sale_" + uuid.uuid4().hex[:20]
        )
        now = _now()
        cash_received: int | None = None
        change_cents: int | None = None
        if idempotent_cash and body.catalogVersion is not None:
            ensure_outbox_schema(conn)

        try:
            with write_transaction(conn):
                if idempotent_cash:
                    existing = conn.execute(
                        "SELECT * FROM sales WHERE id = ?", (sale_id,)
                    ).fetchone()
                    if existing is not None:
                        if (
                            body.expectedTotalCents is not None
                            and body.expectedTotalCents != existing["total_cents"]
                        ) or not cash_intent_matches(
                            conn,
                            existing,
                            employee_id=body.employeeId,
                            payment_method=body.paymentMethod,
                            merged_items=merged,
                            cash_received_cents=body.cashReceivedCents,
                        ):
                            raise HTTPException(
                                status_code=409,
                                detail="Idempotency-Key reusada con contenido distinto",
                            )
                        return _serialize_sale(conn, sale_id)
                employee = _require_employee(conn, body.employeeId)
                products: list[sqlite3.Row] = []
                for product_id in merged:
                    products.append(_require_product(conn, product_id))

                issued_prices = None
                if idempotent_cash and body.catalogVersion is not None:
                    issued_prices = catalog_unit_prices(
                        conn, STORE_ID, body.catalogVersion, current_at=now,
                    )
                total_cents = 0
                lines: list[dict[str, Any]] = []
                for product in products:
                    product_id = int(product["id"])
                    qty_milli = merged[product_id]
                    if issued_prices is not None and product_id not in issued_prices:
                        raise HTTPException(
                            status_code=422,
                            detail="El producto no está en el catálogo autorizado. Actualiza para cobrar.",
                        )
                    unit_price = int(product["price_cents"]) if issued_prices is None else issued_prices[product_id]
                    line_total = line_total_cents(unit_price, qty_milli)
                    total_cents += line_total
                    lines.append(
                        {
                            "product": product,
                            "qty_milli": qty_milli,
                            "unit_price": unit_price,
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
                    if body.expectedTotalCents is not None and body.expectedTotalCents != total_cents:
                        raise HTTPException(
                            status_code=422,
                            detail="El total cambió. Actualiza el catálogo antes de cobrar.",
                        )
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
                            line["unit_price"],
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

        except SyncError as exc:
            if exc.code == "catalog_version_unavailable":
                raise HTTPException(status_code=422, detail=exc.detail) from exc
            if exc.code == "stock_conflict":
                return JSONResponse(
                    status_code=409,
                    content={"code": exc.code, "message": exc.detail},
                )
            raise
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
                bank_account_id=bank_account_id,
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
    def cancel_sale(
        sale_id: str,
        pendingOnly: bool = False,
        conn: sqlite3.Connection = Depends(get_db),
        pey_client: Any | None = Depends(get_pey),
    ):
        if pendingOnly:
            _sale_or_404(conn, sale_id)
            _reconcile_sale(conn, sale_id, pey_client)
        with write_transaction(conn):
            sale = _require_sale(conn, sale_id)
            if sale["status"] == "canceled":
                return sale_to_dict(conn, sale)
            if pendingOnly and (
                sale["payment_method"] != "pey"
                or sale["status"] not in {"pending", "por_conciliar", "expired"}
            ):
                raise HTTPException(status_code=409, detail="El cobro ya no está pendiente. Consulta su estado.")
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
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        employee = _optional_employee(conn, x_employee_id)
        if employee is not None and employee["role"] != "owner":
            raise HTTPException(status_code=403, detail=REPORTS_OWNER_ONLY_DETAIL)
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

    @api.get("/fiado/customers/{customer_id}/entries")
    def fiado_customer_entries(
        customer_id: int,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_customer(conn, customer_id)
        _require_fiado_employee(conn, x_employee_id)
        return {"items": _fiado_entries_payload(conn, customer_id)}

    @api.post("/fiado/customers/{customer_id}/abono")
    def fiado_abono(
        customer_id: int,
        body: AbonoIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        if body.amountCents <= 0:
            raise HTTPException(status_code=400, detail="El abono debe ser mayor que cero")
        with write_transaction(conn):
            _require_customer(conn, customer_id)
            _require_fiado_employee(conn, x_employee_id)
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
    def inventory_adjust(
        body: AdjustIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        reason = body.reason.strip() or "ajuste"
        with write_transaction(conn):
            _require_inventory_employee(conn, x_employee_id)
            _require_employee(conn, body.employeeId)
            product = _require_product(conn, body.productId)
            if product["unlimited_stock"]:
                raise HTTPException(status_code=400, detail="Este producto tiene inventario sin límite")
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

    # v2 support tickets ----------------------------------------------------

    @api.post("/support/tickets")
    def create_support_ticket(
        body: SupportTicketIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        # Any active employee in the store can report a problem; no header keeps
        # the open v1 behavior (scripts/tests).
        employee = _optional_employee(conn, x_employee_id)
        reported_by_name = employee["name"] if employee is not None else None
        note = (body.note or "").strip() or None
        sale_id: str | None = None
        if body.saleId is not None:
            sale_id = body.saleId.strip()
            if not sale_id:
                raise HTTPException(
                    status_code=400, detail="El id de la venta no es válido"
                )
        if sale_id is None and note is None:
            raise HTTPException(
                status_code=400,
                detail="La nota es obligatoria cuando el ticket no tiene venta",
            )

        with write_transaction(conn):
            if sale_id is not None:
                _require_sale(conn, sale_id)
                # One open ticket per sale: reporting twice returns the same one.
                existing = conn.execute(
                    """SELECT * FROM support_tickets
                       WHERE store_id = ? AND sale_id = ? AND status = 'open'
                       ORDER BY created_at ASC, id ASC LIMIT 1""",
                    (STORE_ID, sale_id),
                ).fetchone()
                if existing is not None:
                    payload = _support_ticket_payload(
                        conn, existing, reported_by_name=reported_by_name
                    )
                    payload["alreadyOpen"] = True
                    return payload
            ticket_id = "tkt_" + secrets.token_hex(8)
            conn.execute(
                """INSERT INTO support_tickets
                       (id, store_id, sale_id, note, status, created_at, resolved_at)
                   VALUES (?, ?, ?, ?, 'open', ?, NULL)""",
                (ticket_id, STORE_ID, sale_id, note, _now()),
            )
        row = _support_ticket_row(conn, ticket_id)
        assert row is not None
        payload = _support_ticket_payload(
            conn, row, reported_by_name=reported_by_name
        )
        payload["alreadyOpen"] = False
        return payload

    @api.get("/support/tickets")
    def list_support_tickets(
        status: Literal["open", "resolved", "all"] = "all",
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        query = "SELECT * FROM support_tickets WHERE store_id = ?"
        params: list[Any] = [STORE_ID]
        if status != "all":
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC, id DESC"
        rows = conn.execute(query, params).fetchall()
        return {
            "items": [
                _support_ticket_payload(conn, row, include_resolved_at=True)
                for row in rows
            ]
        }

    @api.patch("/support/tickets/{ticket_id}")
    def patch_support_ticket(
        ticket_id: str,
        body: SupportTicketPatchIn,
        conn: sqlite3.Connection = Depends(get_db),
        x_employee_id: Annotated[int | None, Header(alias="X-Employee-Id")] = None,
    ):
        _require_owner_employee(conn, x_employee_id)
        if _support_ticket_row(conn, ticket_id) is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
        updates: dict[str, Any] = {}
        if body.note is not None:
            updates["note"] = body.note.strip() or None
        if body.status is not None:
            updates["status"] = body.status
            # Resolving stamps resolved_at; reopening clears it.
            updates["resolved_at"] = _now() if body.status == "resolved" else None
        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            with write_transaction(conn):
                conn.execute(
                    f"UPDATE support_tickets SET {assignments} "
                    "WHERE id = ? AND store_id = ?",
                    (*updates.values(), ticket_id, STORE_ID),
                )
        row = _support_ticket_row(conn, ticket_id)
        assert row is not None
        return _support_ticket_payload(conn, row, include_resolved_at=True)

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
            "fiadoCollectedCents": report["fiadoCollectedCents"],
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

    @console.get("/fiado/{customer_id}")
    def console_fiado_customer(
        customer_id: int, conn: sqlite3.Connection = Depends(get_db)
    ):
        row = _require_customer(conn, customer_id)
        return {
            "customer": customer_to_dict(conn, row),
            "entries": _fiado_entries_payload(conn, customer_id),
        }

    app.include_router(api)
    app.include_router(console)

    @app.post("/api/webhooks/pey", include_in_schema=False)
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
            logger.warning(
                "PEY webhook rejected: invalid signature (id=%s, path=%s)",
                request.headers.get("webhook-id", ""),
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "invalid_signature"},
            )

        webhook_id = request.headers.get("webhook-id", "").strip()
        logger.info("PEY webhook accepted for processing id=%s path=%s", webhook_id, request.url.path)
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

        # PEY sends the payment fields at the top level; older/test payloads
        # may nest them under "data". Accept both shapes.
        data = event.get("data")
        if not isinstance(data, dict):
            data = event
        if not isinstance(data, dict):
            logger.warning("PEY webhook rejected: invalid payload (id=%s)", webhook_id)
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

    # v2 App Links: the HTTPS invite opens the Android app -------------------

    @app.get("/invite/{token}", include_in_schema=False)
    def invite_page(token: str):
        safe_token = html.escape(token)
        deep_link = "abarpay://empleado/" + safe_token
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
        return HTMLResponse(
            content=page, headers={"Cache-Control": "no-store"}
        )

    @app.get("/.well-known/assetlinks.json", include_in_schema=False)
    def assetlinks():
        return JSONResponse(
            content=[
                {
                    "relation": ["delegate_permission/common.handle_all_urls"],
                    "target": {
                        "namespace": "android_app",
                        "package_name": ANDROID_PACKAGE_NAME,
                        "sha256_cert_fingerprints": [
                            ANDROID_SHA256_CERT_FINGERPRINT
                        ],
                    },
                }
            ]
        )

    @app.get("/", include_in_schema=False)
    def root(request: Request):
        return landing_page_response(request)


app = create_app()
