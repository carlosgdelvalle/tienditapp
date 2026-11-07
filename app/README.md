# app · Abarpay (MVP del hackatón)

Venta dictada → cobro CoDi con pey → confirmación verificada → aviso de voz → inventario y corte del día.

## Correr en local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
cp .env.example .env     # llena PEY_API_KEY (y OPENAI_API_KEY si la tienen)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000` en la laptop. Desde un teléfono en la misma Wi-Fi: `http://<IP-de-la-laptop>:8000` (el dictado por micrófono en el teléfono necesita HTTPS; ahí usa texto o botones, o un túnel HTTPS).

## Cómo se confirma un pago

1. `POST /api/sales` calcula el total con los precios de la base y pide el QR a pey (`POST /codi/qr`). En `MODO_DEMO=true` se cobra $0.01 y la pantalla lo dice.
2. El teléfono consulta `GET /api/sales/{id}` cada 2.5 s. El servidor concilia con pey (`GET /transaction/codi/qr/{qrId}`) y, si hay una transacción `PAID` con el monto exacto, aplica el pago **una sola vez**: venta pagada e inventario descontado.
3. Con URL pública, pey también avisa por `POST /webhooks/pey` (firma Standard Webhooks con `PEY_WEBHOOK_SECRET`, deduplicado por `webhook-id` y por transacción).
4. Si `POST /codi/qr` no responde, la venta queda `por_conciliar` y no se genera otro cobro automáticamente.

## Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/bootstrap` | Tienda, empleados, catálogo, modo demo, motor de IA |
| POST | `/api/cart/parse` | Texto dictado → carrito (`engine`: `openai` o `local`) |
| POST | `/api/sales` | Crea la venta y el QR de pey |
| GET | `/api/sales/{id}` | Estado (concilia con pey) |
| POST | `/api/sales/{id}/cancel` | Cancela un cobro pendiente |
| POST | `/webhooks/pey` | Webhook firmado de pey |
| GET | `/api/paid-since?ts=` | Pagos nuevos (aviso en el teléfono del dueño) |
| GET | `/api/reports/today` | Corte del día |

## IA

Con `OPENAI_API_KEY`, `app/parse.py` usa OpenAI con salida estructurada y el modelo de `OPENAI_MODEL` (confirmar el ID con los mentores). Sin key, usa un intérprete local del catálogo y la pantalla lo dice. Si OpenAI falla, la venta no se cae: se usa el local y se avisa.

## Pruebas

`python -m pytest -q app/tests`: 12 pruebas con pey simulado (`FakePey`, etiquetado SIMULADO): totales en servidor, conciliación sin doble descuento, webhook con firma inválida o vieja, duplicados, monto distinto, QR desconocido, timeout de pey, QR vencido, reporte y dictado local.
