import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.parse import parse_local
from app.pey import PeyTimeout, sign_webhook

SECRET = "whsec_" + base64.b64encode(b"secreto-de-prueba-123456").decode()


class FakePey:
    """SIMULADO: reemplaza a pey en las pruebas. No hace llamadas reales."""
    def __init__(self):
        self.txs: dict[str, list] = {}
        self.timeout = False
        self.n = 0

    def create_qr(self, amount_pesos, concept, expiration_sec, sale_id):
        if self.timeout:
            raise PeyTimeout("sin respuesta")
        self.n += 1
        self.last_amount = amount_pesos
        return {"id": f"QR{self.n}", "qrString": "x", "qrImage": "aGk="}

    def qr_transactions(self, qr_id):
        return self.txs.get(qr_id, [])


@pytest.fixture
def ctx(monkeypatch):
    c = db.connect(":memory:")
    db.init(c)
    fake = FakePey()
    main._state.update({"conn": c, "pey": fake, "last_reconcile": {}})
    monkeypatch.setattr(main, "RECONCILE_EVERY_SEC", 0)
    monkeypatch.setenv("MODO_DEMO", "true")
    monkeypatch.setenv("PEY_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return TestClient(main.app), c, fake


def stock(c, pid):
    return c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0]


def new_sale(client, items=None):
    r = client.post("/api/sales", json={"employeeId": 2, "items": items or [{"productId": 1, "qty": 2},
                                                                              {"productId": 2, "qty": 1}]})
    assert r.status_code == 200, r.text
    return r.json()


def test_total_se_calcula_en_servidor_y_en_demo_se_cobra_un_centavo(ctx):
    client, c, fake = ctx
    s = new_sale(client)
    assert s["totalCents"] == 2 * 1800 + 2200 == 5800
    assert s["chargedCents"] == 1
    assert fake.last_amount == 0.01


def test_carrito_vacio_o_cantidad_invalida_se_rechaza(ctx):
    client, _, _ = ctx
    assert client.post("/api/sales", json={"employeeId": 2, "items": []}).status_code == 400
    assert client.post("/api/sales", json={"employeeId": 2, "items": [{"productId": 1, "qty": 0}]}).status_code == 400


def test_conciliacion_marca_pagada_y_descuenta_inventario_una_sola_vez(ctx):
    client, c, fake = ctx
    antes = stock(c, 1)
    s = new_sale(client)
    assert client.get(f"/api/sales/{s['saleId']}").json()["status"] == "pending"
    fake.txs[s["qrId"]] = [{"id": "TX1", "status": "PAID", "amount": 0.01}]
    assert client.get(f"/api/sales/{s['saleId']}").json()["status"] == "paid"
    client.get(f"/api/sales/{s['saleId']}")
    assert stock(c, 1) == antes - 2


def _post_webhook(client, payload, wid="wh_1", secret=SECRET, ts=None):
    raw = json.dumps(payload).encode()
    ts = ts or int(time.time())
    return client.post("/webhooks/pey", content=raw, headers={
        "webhook-id": wid, "webhook-timestamp": str(ts),
        "webhook-signature": sign_webhook(wid, ts, raw, secret), "content-type": "application/json"})


def _paid_evt(qr, tx="TXW", amount=0.01):
    return {"type": "codi.qr.payment_received", "data": {"codiQrId": qr, "transactionId": tx, "amount": amount}}


def test_webhook_con_firma_invalida_regresa_401(ctx):
    client, _, _ = ctx
    s = new_sale(client)
    otro = "whsec_" + base64.b64encode(b"otro-secreto-xxxxxxxxxx").decode()
    assert _post_webhook(client, _paid_evt(s["qrId"]), secret=otro).status_code == 401


def test_webhook_valido_aplica_y_duplicado_no_descuenta_dos_veces(ctx):
    client, c, _ = ctx
    antes = stock(c, 1)
    s = new_sale(client)
    assert _post_webhook(client, _paid_evt(s["qrId"])).json()["outcome"] == "applied"
    assert _post_webhook(client, _paid_evt(s["qrId"])).json()["outcome"] == "duplicate"
    assert _post_webhook(client, _paid_evt(s["qrId"]), wid="wh_2").json()["outcome"] == "duplicate"
    assert stock(c, 1) == antes - 2


def test_monto_distinto_no_marca_pagada(ctx):
    client, _, _ = ctx
    s = new_sale(client)
    assert _post_webhook(client, _paid_evt(s["qrId"], amount=58.0)).json()["outcome"] == "amount_mismatch"
    assert client.get(f"/api/sales/{s['saleId']}").json()["status"] == "por_conciliar"


def test_qr_desconocido_no_toca_ventas(ctx):
    client, _, _ = ctx
    assert _post_webhook(client, _paid_evt("NOEXISTE")).json()["outcome"] == "unknown_qr"


def test_webhook_viejo_se_rechaza(ctx):
    client, _, _ = ctx
    s = new_sale(client)
    assert _post_webhook(client, _paid_evt(s["qrId"]), ts=int(time.time()) - 3600).status_code == 401


def test_timeout_de_pey_deja_venta_por_conciliar(ctx):
    client, c, fake = ctx
    fake.timeout = True
    r = client.post("/api/sales", json={"employeeId": 2, "items": [{"productId": 1, "qty": 1}]})
    assert r.status_code == 504
    assert c.execute("SELECT status FROM sales").fetchone()[0] == "por_conciliar"


def test_qr_vencido_sin_pago_queda_expired(ctx):
    client, c, _ = ctx
    s = new_sale(client)
    c.execute("UPDATE sales SET expires_at=? WHERE id=?", (time.time() - 1, s["saleId"]))
    assert client.get(f"/api/sales/{s['saleId']}").json()["status"] == "expired"


def test_reporte_solo_cuenta_ventas_pagadas(ctx):
    client, _, fake = ctx
    a, b = new_sale(client), new_sale(client, [{"productId": 3, "qty": 1}])
    fake.txs[a["qrId"]] = [{"id": "TXA", "status": "PAID", "amount": 0.01}]
    client.get(f"/api/sales/{a['saleId']}")
    client.get(f"/api/sales/{b['saleId']}")
    rep = client.get("/api/reports/today").json()
    assert rep["salesCount"] == 1
    assert rep["totalCents"] == 5800
    assert rep["byEmployee"][0]["name"] == "Lupita"


def test_dictado_local_arma_carrito_con_precios_del_catalogo(ctx):
    _, c, _ = ctx
    catalog = [dict(r) for r in c.execute("SELECT id, name, aliases, price_cents FROM products")]
    r = parse_local("dos cocas y unas sabritas", catalog)
    got = {i["name"]: (i["qty"], i["unitPriceCents"]) for i in r["items"]}
    assert got == {"Coca-Cola 600 ml": (2, 1800), "Sabritas sal 45 g": (1, 2200)}
    r2 = parse_local("un chicle de menta y una coca", catalog)
    assert any("chicle" in u for u in r2["unmatched"])
    assert [i["name"] for i in r2["items"]] == ["Coca-Cola 600 ml"]


def test_codigo_desconocido_se_enlaza_y_despues_se_encuentra(ctx):
    client, _, _ = ctx
    assert client.post("/api/barcode/lookup", json={"code": "7500000000001"}).status_code == 404
    r = client.post("/api/barcode/link", json={"code": "7500000000001", "productId": 1})
    assert r.status_code == 200 and r.json()["name"] == "Coca-Cola 600 ml"
    r = client.post("/api/barcode/lookup", json={"code": " 7500000000001 "})
    assert r.json() == {"productId": 1, "name": "Coca-Cola 600 ml", "unitPriceCents": 1800, "stock": 24}


def test_enlazar_a_producto_inexistente_o_codigo_vacio_falla(ctx):
    client, _, _ = ctx
    assert client.post("/api/barcode/link", json={"code": "123", "productId": 999}).status_code == 400
    assert client.post("/api/barcode/lookup", json={"code": "   "}).status_code == 400


def test_foto_sin_openai_regresa_503_y_no_inventa_productos(ctx):
    client, _, _ = ctx
    r = client.post("/api/cart/photo", json={"image": "aGk="})
    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.json()["detail"]
