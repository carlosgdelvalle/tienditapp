"""Abarpay: venta dictada → cobro CoDi con pey → confirmación verificada → inventario y corte."""
import json
import os
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

from . import db  # noqa: E402
from .parse import parse_cart  # noqa: E402
from .pey import PeyClient, PeyError, PeyTimeout, verify_webhook  # noqa: E402

QR_EXPIRATION_SEC = 600
RECONCILE_EVERY_SEC = 3.0
TZ = ZoneInfo("America/Mexico_City")

app = FastAPI(title="Abarpay")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_state: dict = {"conn": None, "pey": None, "last_reconcile": {}}


def conn():
    if _state["conn"] is None:
        _state["conn"] = db.connect()
        db.init(_state["conn"])
    return _state["conn"]


def pey() -> PeyClient:
    if _state["pey"] is None:
        key = os.getenv("PEY_API_KEY", "")
        if not key:
            raise HTTPException(503, "Falta PEY_API_KEY en .env")
        _state["pey"] = PeyClient(key)
    return _state["pey"]


def modo_demo() -> bool:
    return os.getenv("MODO_DEMO", "true").lower() != "false"


# ---------- Pagos: el único lugar donde una venta pasa a pagada ----------

def apply_payment(c, sale_id: str, tx_id: str, amount_pesos: float, source: str) -> str:
    """Aplica un pago verificado una sola vez. Devuelve el outcome."""
    c.execute("BEGIN IMMEDIATE")
    try:
        if c.execute("SELECT 1 FROM payments WHERE tx_id=?", (tx_id,)).fetchone():
            c.execute("COMMIT")
            return "duplicate"
        sale = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if sale is None:
            c.execute("COMMIT")
            return "unknown_sale"
        if sale["status"] == "paid":
            c.execute("COMMIT")
            return "duplicate"
        cents = round(float(amount_pesos) * 100)
        c.execute("INSERT INTO payments(tx_id, sale_id, amount_cents, source, received_at) VALUES (?,?,?,?,?)",
                  (tx_id, sale_id, cents, source, time.time()))
        if cents != sale["charged_cents"]:
            c.execute("UPDATE sales SET status='por_conciliar', note=? WHERE id=?",
                      (f"monto recibido {cents} ≠ cobrado {sale['charged_cents']}", sale_id))
            c.execute("COMMIT")
            return "amount_mismatch"
        late = sale["status"] == "expired"
        c.execute("UPDATE sales SET status='paid', pey_tx_id=?, paid_at=?, note=? WHERE id=?",
                  (tx_id, time.time(), "pago tardío" if late else None, sale_id))
        for item in json.loads(sale["items"]):
            c.execute("UPDATE products SET stock = stock - ? WHERE id=?", (item["qty"], item["productId"]))
        c.execute("COMMIT")
        return "late_payment" if late else "applied"
    except Exception:
        c.execute("ROLLBACK")
        raise


def reconcile(c, sale) -> None:
    """Consulta a pey las transacciones del QR y aplica las pagadas (respaldo del webhook)."""
    if not sale["pey_qr_id"] or sale["status"] not in ("pending", "expired"):
        return
    last = _state["last_reconcile"].get(sale["id"], 0)
    if time.time() - last < RECONCILE_EVERY_SEC:
        return
    _state["last_reconcile"][sale["id"]] = time.time()
    try:
        txs = pey().qr_transactions(sale["pey_qr_id"])
    except (PeyError, PeyTimeout):
        return
    for t in txs:
        if t.get("status") == "PAID":
            apply_payment(c, sale["id"], t["id"], t.get("amount", 0), "conciliacion")


# ---------- API ----------

class ParseIn(BaseModel):
    text: str


class CartLine(BaseModel):
    productId: int
    qty: int


class SaleIn(BaseModel):
    employeeId: int
    items: list[CartLine]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/bootstrap")
def bootstrap():
    c = conn()
    return {
        "store": "Tiendita de la Esquina",
        "modoDemo": modo_demo(),
        "ia": "openai" if os.getenv("OPENAI_API_KEY") else "local",
        "employees": [dict(r) for r in c.execute("SELECT id, name, role FROM employees ORDER BY id")],
        "products": [dict(r) for r in c.execute(
            "SELECT id, name, price_cents, stock, quick FROM products ORDER BY quick DESC, id")],
    }


@app.post("/api/cart/parse")
def cart_parse(body: ParseIn):
    if not body.text.strip():
        raise HTTPException(400, "Dicta o escribe qué se lleva el cliente")
    return parse_cart(conn(), body.text)


@app.post("/api/sales")
def create_sale(body: SaleIn):
    c = conn()
    if not c.execute("SELECT 1 FROM employees WHERE id=?", (body.employeeId,)).fetchone():
        raise HTTPException(400, "Empleado no existe")
    lines = [l for l in body.items if l.qty > 0]
    if not lines or len(lines) != len(body.items):
        raise HTTPException(400, "El carrito está vacío o tiene cantidades inválidas")
    items, total = [], 0
    for l in lines:
        p = c.execute("SELECT id, name, price_cents FROM products WHERE id=?", (l.productId,)).fetchone()
        if p is None:
            raise HTTPException(400, f"Producto {l.productId} no existe")
        items.append({"productId": p["id"], "name": p["name"], "qty": l.qty, "unitPriceCents": p["price_cents"]})
        total += p["price_cents"] * l.qty
    charged = 1 if modo_demo() else total
    sale_id = uuid.uuid4().hex[:12]
    now = time.time()
    c.execute("INSERT INTO sales(id, created_at, employee_id, items, total_cents, charged_cents, status, expires_at) "
              "VALUES (?,?,?,?,?,?,?,?)",
              (sale_id, now, body.employeeId, json.dumps(items, ensure_ascii=False), total, charged, "pending",
               now + QR_EXPIRATION_SEC))
    try:
        qr = pey().create_qr(charged / 100, "Tiendita de la Esquina", QR_EXPIRATION_SEC, sale_id)
    except PeyTimeout:
        c.execute("UPDATE sales SET status='por_conciliar', note='pey no respondió al crear el QR' WHERE id=?",
                  (sale_id,))
        raise HTTPException(504, "pey no respondió. La venta quedó por conciliar; no generes otro cobro todavía.")
    except PeyError as e:
        c.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        raise HTTPException(502, f"pey rechazó el cobro: {e.type}")
    c.execute("UPDATE sales SET pey_qr_id=? WHERE id=?", (qr["id"], sale_id))
    image = qr.get("qrImage") or ""
    if image and not image.startswith("data:"):
        image = "data:image/png;base64," + image
    return {"saleId": sale_id, "totalCents": total, "chargedCents": charged, "items": items,
            "qrId": qr["id"], "qrImage": image, "expiresAt": now + QR_EXPIRATION_SEC}


@app.get("/api/sales/{sale_id}")
def sale_status(sale_id: str):
    c = conn()
    sale = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if sale is None:
        raise HTTPException(404, "Venta no existe")
    reconcile(c, sale)
    sale = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if sale["status"] == "pending" and time.time() > sale["expires_at"]:
        c.execute("UPDATE sales SET status='expired' WHERE id=? AND status='pending'", (sale_id,))
        sale = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    return {"saleId": sale["id"], "status": sale["status"], "paidAt": sale["paid_at"],
            "chargedCents": sale["charged_cents"], "totalCents": sale["total_cents"],
            "txId": sale["pey_tx_id"], "note": sale["note"]}


@app.post("/api/sales/{sale_id}/cancel")
def cancel_sale(sale_id: str):
    c = conn()
    c.execute("UPDATE sales SET status='expired', note='cancelada' WHERE id=? AND status='pending'", (sale_id,))
    return {"ok": True}


@app.post("/webhooks/pey")
async def pey_webhook(request: Request):
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not verify_webhook(headers, raw, os.getenv("PEY_WEBHOOK_SECRET", "")):
        raise HTTPException(401, "Firma inválida")
    c = conn()
    wid = headers["webhook-id"]
    if c.execute("SELECT 1 FROM webhook_events WHERE webhook_id=?", (wid,)).fetchone():
        return {"outcome": "duplicate"}
    payload = json.loads(raw or b"{}")
    data = payload.get("data", payload)
    outcome = "ignored"
    if payload.get("type") == "codi.qr.payment_received":
        sale = c.execute("SELECT id FROM sales WHERE pey_qr_id=?", (str(data.get("codiQrId")),)).fetchone()
        outcome = "unknown_qr" if sale is None else apply_payment(
            c, sale["id"], str(data.get("transactionId")), data.get("amount", 0), "webhook")
    c.execute("INSERT OR IGNORE INTO webhook_events(webhook_id, received_at, outcome) VALUES (?,?,?)",
              (wid, time.time(), outcome))
    return {"outcome": outcome}


@app.get("/api/paid-since")
def paid_since(ts: float = 0):
    """Para el teléfono del dueño: ventas pagadas después de ts (aviso en voz alta)."""
    c = conn()
    rows = c.execute("SELECT s.id, s.charged_cents, s.total_cents, s.paid_at, e.name AS employee "
                     "FROM sales s JOIN employees e ON e.id=s.employee_id "
                     "WHERE s.status='paid' AND s.paid_at > ? ORDER BY s.paid_at", (ts,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/reports/today")
def report_today():
    c = conn()
    start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    paid = c.execute("SELECT s.*, e.name AS employee FROM sales s JOIN employees e ON e.id=s.employee_id "
                     "WHERE s.status='paid' AND s.paid_at >= ?", (start,)).fetchall()
    by_emp: dict[str, dict] = {}
    top: dict[str, int] = {}
    for s in paid:
        e = by_emp.setdefault(s["employee"], {"name": s["employee"], "totalCents": 0, "chargedCents": 0, "sales": 0})
        e["totalCents"] += s["total_cents"]
        e["chargedCents"] += s["charged_cents"]
        e["sales"] += 1
        for it in json.loads(s["items"]):
            top[it["name"]] = top.get(it["name"], 0) + it["qty"]
    low = c.execute("SELECT name, stock FROM products WHERE stock <= low_stock_at ORDER BY stock").fetchall()
    pend = c.execute("SELECT COUNT(*) FROM sales WHERE status='por_conciliar'").fetchone()[0]
    return {
        "totalCents": sum(s["total_cents"] for s in paid),
        "chargedCents": sum(s["charged_cents"] for s in paid),
        "salesCount": len(paid),
        "byEmployee": list(by_emp.values()),
        "topProducts": [{"name": k, "qty": v} for k, v in sorted(top.items(), key=lambda kv: -kv[1])[:5]],
        "lowStock": [dict(r) for r in low],
        "porConciliar": pend,
        "modoDemo": modo_demo(),
    }
