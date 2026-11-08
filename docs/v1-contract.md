# Abarpay v1 · contract for the new backend, console and Android app

Status: implementation contract for the fresh v1. The old `app/` and `prototypes/` are reference only. Do not copy their database or UI code.

## Layout

- `server/` — new FastAPI + SQLite backend and owner console.
- `android/` — existing Kotlin/Compose project, refactored to consume this contract.
- `app/`, `prototypes/` — reference only; do not modify as part of v1.
- `docs/v1-contract.md` — this file.

## Runtime

- Backend default: `http://127.0.0.1:8000`; API prefix `/api`; webhook `/webhooks/pey`; console `/console`.
- Environment from the repository root `.env`: `PEY_API_KEY`, `PEY_WEBHOOK_SECRET`, `MODO_DEMO`, `OWNER_PIN`, `ABARPAY_DB`.
- `MODO_DEMO=true` means every PEY QR charges `0.01` MXN and the UI must say so.
- `OWNER_PIN` default for the demo is `1234`; console endpoints require header `X-Owner-Pin`.
- SQLite: one connection per request, WAL, `busy_timeout=5000`, foreign keys on. No shared global connection. Use `BEGIN IMMEDIATE` for writes that must serialize.

## Money and quantities

- All money is integer cents.
- All quantities are integer milli-units: `1000 = 1 unit`.
  - `unit="pieza"`: 1000 = one piece.
  - `unit="kg"`: 1000 = one kilogram; 500 = 0.5 kg; 250 = 250 g.
- `lineTotalCents = round(unitPriceCents * qtyMilli / 1000)`.
- Product `priceCents` is per unit (per piece or per kg).
- Stock is `stockMilli`; negative stock is allowed in the demo (no guardrails), but every change must create an `inventory_movements` row.

## Seed

Single store: `tiendita-esquina`, name `Tiendita de la Esquina`.
Employees: 1 Doña Rosa (owner), 2 Lupita (employee), 3 Toño (employee).
Products (name, unit, price cents, stock milli, low stock milli, quick):
- Coca-Cola 600 ml, pieza, 1800, 24000, 5000, true
- Sabritas sal 45 g, pieza, 2200, 18000, 5000, true
- Pan Bimbo grande, pieza, 4800, 6000, 5000, true
- Huevo (kg), kg, 4500, 10000, 5000, true
- Leche Lala 1 L, pieza, 3100, 12000, 5000, true
- Agua Bonafont 1 L, pieza, 1500, 20000, 5000, true
- Maruchan camarón, pieza, 1600, 30000, 5000, true
- Gansito, pieza, 1700, 15000, 5000, true
- Tortillas (kg), kg, 2600, 8000, 5000, false
- Jabón Zote, pieza, 2300, 9000, 5000, false
- Galletas Marías, pieza, 1900, 14000, 5000, false
- Fanta 600 ml, pieza, 1700, 12000, 5000, false

Barcodes seed: `7500000000001`→Coca-Cola, `7500000000002`→Sabritas, `7500000000003`→Pan Bimbo, `7500000000004`→Huevo, `7500000000005`→Leche.

## Database

```sql
stores(id TEXT PRIMARY KEY, name TEXT NOT NULL);
employees(id INTEGER PRIMARY KEY, store_id TEXT NOT NULL, name TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('owner','employee')), active INTEGER NOT NULL DEFAULT 1);
products(id INTEGER PRIMARY KEY, store_id TEXT NOT NULL, name TEXT NOT NULL,
         aliases TEXT NOT NULL DEFAULT '[]', unit TEXT NOT NULL CHECK(unit IN ('pieza','kg')),
         price_cents INTEGER NOT NULL, stock_milli INTEGER NOT NULL,
         low_stock_milli INTEGER NOT NULL DEFAULT 5000, quick INTEGER NOT NULL DEFAULT 0);
barcodes(code TEXT PRIMARY KEY, product_id INTEGER NOT NULL);
sales(id TEXT PRIMARY KEY, store_id TEXT NOT NULL, employee_id INTEGER NOT NULL,
      created_at REAL NOT NULL, status TEXT NOT NULL,
      payment_method TEXT NOT NULL CHECK(payment_method IN ('cash','pey','fiado')),
      total_cents INTEGER NOT NULL, charged_cents INTEGER NOT NULL,
      cash_received_cents INTEGER, change_cents INTEGER, customer_id INTEGER,
      pey_qr_id TEXT UNIQUE, pey_tx_id TEXT, paid_at REAL, expires_at REAL, note TEXT);
sale_items(id INTEGER PRIMARY KEY, sale_id TEXT NOT NULL, product_id INTEGER NOT NULL,
           name TEXT NOT NULL, unit TEXT NOT NULL, qty_milli INTEGER NOT NULL,
           unit_price_cents INTEGER NOT NULL, line_total_cents INTEGER NOT NULL);
payments(tx_id TEXT PRIMARY KEY, sale_id TEXT NOT NULL, amount_cents INTEGER NOT NULL,
         method TEXT NOT NULL, source TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 1,
         received_at REAL NOT NULL);
inventory_movements(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL,
                     delta_milli INTEGER NOT NULL, reason TEXT NOT NULL,
                     sale_id TEXT, employee_id INTEGER, created_at REAL NOT NULL);
fiado_customers(id INTEGER PRIMARY KEY, store_id TEXT NOT NULL, name TEXT NOT NULL,
                phone TEXT, created_at REAL NOT NULL);
fiado_entries(id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, sale_id TEXT,
              kind TEXT NOT NULL CHECK(kind IN ('charge','payment')), amount_cents INTEGER NOT NULL,
              note TEXT, employee_id INTEGER, created_at REAL NOT NULL);
webhook_events(webhook_id TEXT PRIMARY KEY, received_at REAL NOT NULL, outcome TEXT NOT NULL);
```

Sale statuses: `pending`, `paid_pey`, `paid_cash`, `credit`, `canceled`, `expired`, `por_conciliar`, `failed`.
- Cash and fiado are final immediately; PEY starts `pending`.
- A PEY sale may become `paid_pey` only through `apply_payment` after a verified webhook or PEY reconciliation.
- `por_conciliar` is retried if it has a `pey_qr_id`; do not make it a dead end.
- An extra payment on an already-paid sale must be recorded in `payments` with `applied=0` and must not be silently dropped.

## API

### Public/bootstrap

`GET /api/health` → `{"ok":true,"mode":"demo"|"live","db":"ok","peyConfigured":true}`

`GET /api/bootstrap` →
```json
{"store":{"id":"tiendita-esquina","name":"Tiendita de la Esquina"},
 "employees":[{"id":1,"name":"Doña Rosa","role":"owner"}],
 "products":[{"id":1,"name":"Coca-Cola 600 ml","unit":"pieza","priceCents":1800,"stockMilli":24000,"lowStockMilli":5000,"quick":true}],
 "demoMode":true,"ai":"local"}
```

### Cart and barcode

`POST /api/cart/parse` `{"text":"medio kilo de tortillas y dos cocas"}` →
```json
{"items":[{"productId":9,"name":"Tortillas (kg)","qtyMilli":500,"unit":"kg","unitPriceCents":2600,"lineTotalCents":1300},
          {"productId":1,"name":"Coca-Cola 600 ml","qtyMilli":2000,"unit":"pieza","unitPriceCents":1800,"lineTotalCents":3600}],
 "unmatched":[],"engine":"local"}
```
Local parser must understand `medio`, `1/2`, `un cuarto`, `250 gramos`, `1.5 kg`, `dos`, `tres`, pieces and kg.
Optional OpenAI can be added, but the local parser must work without a key.

`POST /api/barcode/lookup` `{"code":"7500000000001"}` → product object or 404.
`POST /api/barcode/link` `{"code":"...","productId":1}` → product object.

### Sales

`POST /api/sales`
```json
{"employeeId":2,"items":[{"productId":1,"qtyMilli":2000}],
 "paymentMethod":"cash","cashReceivedCents":5000}
```
- `paymentMethod`: `cash`, `pey`, `fiado`.
- Cash: `cashReceivedCents >= total`; response `status:"paid_cash"`, `changeCents`.
- Fiado: requires `customerId`; response `status:"credit"`; creates a `fiado_entries` charge; inventory decrements.
- PEY: response `status:"pending"`, `qrId`, `qrImage` (data URL or empty), `expiresAt`; in demo `chargedCents=1`.
- On PEY timeout: HTTP 202 with `saleId`, `status:"por_conciliar"`; do not return a 504 without the id.
- On PEY rejection: HTTP 502 with `saleId`, `status:"failed"`.
- Server computes all prices and totals from the DB; never trusts client prices.

`GET /api/sales/{id}` → status, totals, method, cash change, customer, tx, note. Reconcile pending/expired/por_conciliar PEY sales.
`POST /api/sales/{id}/cancel` → status `canceled`; late payment is still accepted with a note.
`GET /api/reports/today` →
```json
{"totalCents":0,"collectedCents":0,"cashCents":0,"peyCents":0,"fiadoCents":0,
 "salesCount":0,"byEmployee":[],"topProducts":[],"lowStock":[],"pending":0,
 "fiadoOutstandingCents":0,"demoMode":true}
```

### Fiado

`GET /api/fiado/customers` → `{"customers":[{"id":1,"name":"...","phone":"...","balanceCents":0}]}`
`POST /api/fiado/customers` `{"name":"...","phone":"..."}` → customer.
`GET /api/fiado/customers/{id}` → customer + entries.
`POST /api/fiado/customers/{id}/abono` `{"amountCents":500,"employeeId":2,"note":"..."}` → `{"customerId":1,"balanceCents":...}`.

### Inventory

`POST /api/inventory/adjust` `{"employeeId":2,"productId":1,"deltaMilli":-1000,"reason":"conteo"}` → product object.
Every adjustment writes an `inventory_movements` row. Negative stock allowed in the demo.

### PEY webhook

`POST /webhooks/pey` — Standard Webhooks signature with `PEY_WEBHOOK_SECRET`; verify `webhook-id`, `webhook-timestamp`, `webhook-signature`; dedupe by `webhook-id` and transaction. Event type `codi.qr.payment_received`; data has `codiQrId`, `transactionId`, `amount` in pesos. Apply exactly once; amount mismatch → `por_conciliar`; unknown QR → `unknown_qr`.

### Owner console

`GET /console` → static console HTML (vanilla JS, no build step).
`POST /api/console/login` `{"pin":"1234"}` → `{"ok":true}` or 401.
All `/api/console/*` require `X-Owner-Pin`.
- `GET /api/console/summary` → store, today (report shape), employees, recentSales, lowStock, fiadoOutstandingCents.
- `GET /api/console/sales?limit=50` → `{"items":[...]}`.
- `GET /api/console/inventory` → `{"items":[product...]}`.
- `GET /api/console/fiado` → `{"customers":[...],"totalOutstandingCents":...}`.
Console is demo owner-only; it is not production authentication.

## Android

- Keep the current Kotlin/Compose project, theme, logo and general visual language.
- Refactor the API client and screens to this contract; do not call `app/` endpoints.
- Screens: mock access (owner/employee), home, checkout with text + voice + barcode + catalog, payment method selector (cash/PEY/fiado), cash received/change, PEY QR + polling, success, inventory list + simple adjustment, fiado customers + abono, reports, settings (server URL/simulation).
- Voice: Android speech recognition; fill the text field; server parses.
- Barcode: Google Code Scanner; unknown code → link dialog; then add.
- Cash: confirm received amount; server returns change; no PEY call.
- Fiado: choose existing customer or add name/phone; show balance; abono.
- API mode uses HTTPS; the current debug exception `http://10.0.2.2:8000` may remain for the emulator.
- No keys in the APK.

## Non-goals for this delivery

Real accounts/passkeys, multi-store isolation, offline sale creation, supplier data exchange, advanced forecasting, real webhook deploy beyond the tunnel, and production-grade console auth. Label these as roadmap.

## Verification

- Backend tests with FakePey: cash, PEY, fiado, half-kilo parse, inventory movement, report, webhook signature/duplicate/mismatch, console PIN, concurrent webhooks (no 500s).
- Android: build `assembleDebug`; install on the connected SM-A165M; exercise simulation and API mode; no real sale in automated tests.
- One real $0.01 app-screen payment by a human, then verify sale/report/console.
