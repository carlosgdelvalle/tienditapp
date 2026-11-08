# Abarpay v1 - backend y consola

Implementación nueva en FastAPI + SQLite para el contrato de docs/v1-contract.md. No importa nada de app/ ni de prototypes/ y no comparte la conexión SQLite global del backend viejo.

## Arranque

Desde la raíz del repositorio:

    /tmp/abar-venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000

La base se crea y se siembra sola al arrancar (tienda, 3 empleados, 12 productos y 5 códigos de barras). La ruta por defecto es server/abarpay.db; se puede cambiar con ABARPAY_DB.

El archivo .env de la raíz no se lee por defecto para que las pruebas y el demo no tomen credenciales reales. Si quieres cargarlo explícitamente:

    ABARPAY_LOAD_DOTENV=1 /tmp/abar-venv/bin/python -m uvicorn server.main:app --port 8000

Variables soportadas: PEY_API_KEY, PEY_WEBHOOK_SECRET, MODO_DEMO, OWNER_PIN, ABARPAY_DB. También PEY_BASE_URL, PEY_TIMEOUT_SECONDS, PEY_EXPIRATION_SECONDS, PEY_DEMO_CHARGE_CENTS y ABARPAY_TZ.

Con MODO_DEMO=true (default) el QR de PEY se crea por $0.01 MXN; las ventas guardan el total comercial en totalCents y el cobro real en chargedCents. La consola muestra el aviso de modo demo.

## Consola

Abre http://127.0.0.1:8000/console. El PIN sale de OWNER_PIN (default 1234) y se envía en el header X-Owner-Pin. La página es HTML/CSS/JS sin build y refresca cada 3 segundos. Es una vista de demostración para la dueña, no autenticación de producción.

## Endpoints

Públicos:

- GET /api/health
- GET /api/bootstrap
- POST /api/cart/parse
- POST /api/barcode/lookup
- POST /api/barcode/link
- POST /api/sales
- GET /api/sales/{id}
- POST /api/sales/{id}/cancel
- GET /api/reports/today
- GET /api/fiado/customers
- POST /api/fiado/customers
- GET /api/fiado/customers/{id}
- POST /api/fiado/customers/{id}/abono
- POST /api/inventory/adjust
- POST /webhooks/pey
- GET /console
- POST /api/console/login

Protegidos con X-Owner-Pin:

- GET /api/console/summary
- GET /api/console/sales?limit=50
- GET /api/console/inventory
- GET /api/console/fiado
- GET /api/console/webhooks?limit=20
- GET /api/console/pending

## Reglas de dinero y stock

- Todo el dinero es entero en centavos.
- Las cantidades son mili-unidades: 1000 = una pieza o un kilo.
- lineTotalCents = round(unitPriceCents * qtyMilli / 1000), calculado siempre con el precio de SQLite.
- Efectivo: status paid_cash, cambio calculado y stock descontado dentro de la misma transacción.
- Fiado: status credit, cargo en fiado_entries y stock descontado de inmediato.
- PEY: status pending; el stock se descuenta únicamente cuando apply_payment verifica el pago (webhook firmado o conciliación GET).
- Cualquier cambio de stock deja un renglón en inventory_movements. El stock negativo está permitido en la demo.
- Los pagos extra sobre una venta ya pagada se guardan en payments con applied=0 y una nota; no se descartan.

## Webhook PEY

POST /webhooks/pey verifica Standard Webhooks: webhook-id, webhook-timestamp, webhook-signature (HMAC-SHA256 de id.timestamp.cuerpo con el secreto whsec_...). Tolera 300 segundos de reloj. Deduplica por webhook-id y por transactionId. Un QR desconocido responde 200 con outcome unknown_qr; un monto que no coincide deja la venta en por_conciliar y registra el pago con applied=0.

## Pruebas

    ABARPAY_LOAD_DOTENV=0 /tmp/abar-venv/bin/python -m pytest server/tests -q

La suite usa FakePey, marcado SIMULADO, y nunca hace una llamada real a PEY. No usa la PEY_API_KEY real ni el archivo .env.

Cubre: venta en efectivo, PEY pendiente y conciliación, timeout 202, rechazo 502, webhook (firma, duplicados, monto incorrecto, QR desconocido), pago extra applied=0, fiado con abono, inventario y movimientos, parser de medio kilo y gramos, reporte, PIN de consola y webhooks concurrentes.

## Límites conocidos

- La consola usa PIN compartido de demo; no hay cuentas, sesiones firmadas ni permisos por empleado.
- La imagen del QR se devuelve al crear la venta y no se persiste en SQLite (el contrato no tiene columna para eso).
- Si la creación del QR en PEY hace timeout antes de recibir un qrId, la venta queda en por_conciliar con su saleId. Sin qrId no hay llave para consultar /transaction/codi/qr/{id}; ese caso necesita conciliación manual con PEY. Los por_conciliar con qrId sí se reintentan en cada GET y aceptan un pago posterior correcto.
- Un pago tardío sobre una venta cancelada se registra con applied=0 y nota, pero no se reabre la venta ni se re-descuenta stock; devoluciones/reembolsos quedan fuera de alcance.
- Cancelar una venta ya pagada o fiada repone stock con un movimiento reason=cancel; el reembolso del dinero no está implementado.
- No hay autenticación de producción, multi-tienda, modo offline ni lectura de códigos por cámara en el backend.
