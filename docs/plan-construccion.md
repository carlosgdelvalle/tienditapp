# Abarpay · Plan de construcción (hackatón)

> **Actualización 7-nov 15:30:** el stack cambió a Python/FastAPI + SQLite (ver [`decisiones/0001-stack.md`](decisiones/0001-stack.md)) y la app vive en `app/`. Los contratos, reglas, fallas a cubrir y el orden de trabajo de este plan siguen vigentes; las rutas y comandos de Next.js/Supabase quedan como referencia. Equivalencias: `lib/pey.ts` → `app/pey.py`, `lib/sales.ts` + webhook → `app/main.py`, `lib/parse.ts` → `app/parse.py`, pantallas → `app/static/`, Supabase → `app/db.py` (SQLite). El aviso a varios teléfonos usa consulta periódica (`/api/paid-since`) en lugar de Realtime.

> **Para quien ejecute:** cada bloque (A-E) tiene un dueño y un contrato. Construye contra el contrato, no contra el código de otro equipo. Los pasos usan checkboxes (`- [ ]`).

**Meta:** que una tiendita cobre una venta real por CoDi con pey, desde el celular de cualquier empleado, con confirmación verificada por webhook, aviso en voz alta e inventario que se actualiza solo.

**Arquitectura:** una sola web app móvil (sin instalar desde tiendas) y un backend en el mismo proyecto, desplegado con URL pública HTTPS para recibir el webhook de pey. Una sola entrada de IA convierte texto o voz en el mismo carrito. La base de datos avisa en tiempo real a todos los teléfonos cuando una venta se paga.

**Stack (propuesto; el README lo deja pendiente y la mesa lo confirma en el kickoff):** Next.js + TypeScript · Vercel (deploy y URL pública) · Supabase (Postgres + Realtime) · API de OpenAI (transcripción, visión y salida estructurada) · `standardwebhooks` para verificar firmas · Vitest para pruebas.

**Spec:** [`README.md`](../README.md) del repo (producto, reglas de consistencia e integración con pey) + brief ejecutivo de la mesa (7-nov) + [`modelo-de-negocio.md`](modelo-de-negocio.md) + [`boceto-producto.html`](boceto-producto.html).

**Decisiones de la mesa (default, confirmar en el kickoff):** solo tienditas · la IA captura la venta, no hace de asistente administrativo · cobro real de $0.01 con confirmación verificada; lo demás va como prototipo visual.

## Reglas globales (aplican a todas las tareas)

- Las API keys de pey y OpenAI viven **solo** en `.env.local` y en las variables de entorno de Vercel. El primer commit del repo es `.gitignore` con `.env*`. **El repo es público.**
- No hay sandbox de pey: cada prueba mueve dinero real. Monto de prueba: `$0.01 MXN`. Los pagos de prueba los hace una persona desde su app bancaria, nunca un script.
- Cero datos de terceros: el catálogo es inventado y los teléfonos de prueba son del equipo.
- `MODO_DEMO=true` cobra $0.01 sin importar el total del carrito, y la pantalla lo dice explícitamente: "Modo demo: se cobra $0.01". Nunca se muestra un monto cobrado distinto del real.
- Una venta solo pasa a `paid` por un webhook con firma válida. Ninguna pantalla marca "pagado" por su cuenta.
- Expiración del QR: `600` segundos (pey pide 0 o un mínimo de 360).
- Montos internos en centavos (`int`). A pey se mandan en pesos (`number`): `cents / 100`.
- Español para todo el texto de la interfaz. Tono: verbos simples, sin tecnicismos ("Cobrar $58", "Ya te pagaron").

## Puntos de revisión (fallas que ninguna prueba de los equipos cubre por defecto)

1. **Webhook duplicado:** pey reintenta y llega dos veces el mismo `webhook-id`. Esperado: una sola venta pagada y el inventario se descuenta una sola vez. → prueba en Tarea A3.
2. **Webhook falso o de otra venta:** firma inválida → 401; `codiQrId` desconocido o monto distinto al cobrado → no se marca pagada y queda en log. → prueba en Tarea A3.
3. **Producto ambiguo o fuera de catálogo** ("una coca" sin tamaño, "chicles" que no existen): esperado, que aparezca en `unmatched` y el empleado lo resuelva con un toque, sin inventar precio. → prueba en Tarea B1.
4. **QR expirado:** el cliente tarda más de 10 min. Esperado: la venta pasa a `expired`, la pantalla ofrece "Generar nuevo cobro" y un pago tardío no reactiva la venta vieja en silencio. → prueba en Tarea A2.
5. **Teléfono sin señal al momento del pago:** se cae Realtime. Esperado: al reconectar, la pantalla consulta `GET /api/sales/:id` y muestra el estado real. → paso en Tarea C2.

6. **El webhook no llega** (red, configuración): si a los 30 s la venta sigue `pending`, el servidor consulta `GET /transaction/codi/qr/{id}` en pey y aplica el pago con las mismas validaciones (monto, una sola vez). → Tarea A3.
7. **`POST /codi/qr` sin respuesta (timeout):** pey no tiene idempotencia al crear cobros. La venta queda "por conciliar" y no se crea otro QR en automático hasta revisar las transacciones. → Tarea A2.
8. **Primera prueba de acceso:** `GET /transaction/api-key` debe responder 200 con la key nueva antes de escribir código (la anterior dio 403). → Tarea D1.

---

## Contratos compartidos (todos construyen contra esto)

### Tablas (Supabase)

```sql
create table products (
  id uuid primary key default gen_random_uuid(),
  name text not null,            -- "Coca-Cola 600 ml"
  aliases text[] not null default '{}', -- {"coca","coca chica","refresco de cola"}
  price_cents int not null,
  stock int not null default 0,
  low_stock_at int not null default 5
);
create table employees (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  role text not null check (role in ('owner','employee'))
);
create table sales (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  employee_id uuid not null references employees(id),
  items jsonb not null,          -- CartItem[]
  total_cents int not null,      -- total del carrito
  charged_cents int not null,    -- lo que se cobró (1 en modo demo)
  status text not null check (status in ('pending','paid','expired')),
  pey_qr_id text unique,         -- "id" que devuelve POST /codi/qr
  pey_transaction_id text,
  paid_at timestamptz,
  expires_at timestamptz not null
);
create table webhook_events (
  webhook_id text primary key,   -- header webhook-id (idempotencia)
  received_at timestamptz not null default now(),
  payload jsonb not null,
  outcome text not null          -- 'applied' | 'duplicate' | 'unknown_qr' | 'amount_mismatch' | 'late_payment'
);
```

Realtime activado en `sales`.

### Tipos

```ts
type CartItem = { productId: string; name: string; qty: number; unitPriceCents: number };
type ParseResult = { items: CartItem[]; unmatched: string[] };
type SaleCreated = { saleId: string; totalCents: number; chargedCents: number;
                     qrString: string; qrImage: string | null; expiresAt: string };
type SaleStatus = { saleId: string; status: 'pending'|'paid'|'expired'; paidAt: string | null };
type DayReport = { totalCents: number; salesCount: number;
                   byEmployee: { name: string; totalCents: number }[];
                   lowStock: { name: string; stock: number }[];
                   topProducts: { name: string; qty: number }[] };
```

### Endpoints

| Método y ruta | Entrada | Salida | Dueño |
|---|---|---|---|
| `POST /api/cart/parse` | `{ type: 'text'\|'audio', data: string }` (texto, o audio en base64) | `ParseResult` | B |
| `POST /api/sales` | `{ employeeId, items: CartItem[] }` | `SaleCreated` | A |
| `GET /api/sales/:id` | — | `SaleStatus` | A |
| `POST /api/webhooks/pey` | webhook de pey | `200` / `401` | A |
| `GET /api/reports/today` | — | `DayReport` | A |

---

## Equipos y horario

| Bloque | Personas | Qué entrega |
|---|---|---|
| D · Infra y datos | 1 | Repo, deploy, Supabase, catálogo de 30 productos, variables de entorno |
| A · Cobro pey | 2 | Ventas, QR, webhook, idempotencia, reporte |
| B · Captura IA | 2 | `/api/cart/parse` con texto y voz |
| C · App del tendero | 3 | Pantallas: Cobrar, QR, Pagado (voz), Mi tienda, y pruebas en celulares reales |
| E · Pitch y demo | 2 (Eduardo + Luis) | Guion, deck, video de respaldo, modelo de negocio |

**Hitos (hora CDMX).** El detalle minuto a minuto, con la evidencia de cada punto, está en [`plan-entrega.md`](plan-entrega.md). Resumen:

- **Sáb 14:20-14:35 · Kickoff:** confirmar decisiones, stack y dueños. Probar la key nueva con `GET /transaction/api-key`. Cuenta CoDi: dar de alta **una** de las CLABEs pre-autorizadas que habilitó pey en `https://portal.pey.mx`. Los centavos de prueba le llegan a esa persona y no se devuelven. Quien quiera registrar su propia CLABE debe saber que tarda ~5 días hábiles: no llega para el domingo.
- **Sáb 15:20-15:45 · H1 · Primer pago real:** QR de $0.01 → una persona paga → el webhook llega (log de pey) y `GET /transaction/codi/qr/{id}` muestra el pago.
- **Sáb 16:00 · Entrega de la propuesta** ([`propuesta-4pm.md`](propuesta-4pm.md)).
- **Sáb noche · H2:** webhook verificado de punta a punta, dictado, pantalla verde con aviso en voz alta, varios empleados, Mi tienda.
- **Dom 09:00 · Congelamiento:** no entran más funciones. Solo bugs y pulido.
- **Dom 09:00-11:00:** demo ensayado tres veces, **video de respaldo grabado** con un pago real.
- **Dom 12:00 · Entrega final por correo a `hola@aibuilders.lat`** (una hora de colchón antes del cierre de las 13:00).

---

### Tarea D1: Repo, deploy y datos base

**Archivos:**
- Crear: `.gitignore`, `.env.example` (solo nombres, sin valores), `supabase/schema.sql`, `supabase/seed.sql`, `README.md`

**Interfaces:**
- Produce: las tablas de "Contratos compartidos", 30 productos de tiendita con `aliases` y `stock`, 3 empleados (1 owner, 2 employee) y una URL pública de Vercel.
- Variables: `PEY_API_KEY`, `PEY_WEBHOOK_SECRET`, `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `MODO_DEMO`.

- [ ] **Paso 1:** antes de cualquier código, commit con `.gitignore` que incluya `.env*` y `!.env.example` (el repo ya existe y es público).
- [ ] **Paso 2:** deploy de una página vacía en Vercel. Verificación: la URL HTTPS responde 200.
- [ ] **Paso 3:** cargar `schema.sql` y `seed.sql` en Supabase. Verificación: `select count(*) from products` → `30`.
- [ ] **Paso 3b:** en `portal.pey.mx`: dar de alta una CLABE pre-autorizada en Finanzas, crear la API key en Desarrollador y vincularla. Verificación: la cuenta aparece con `codiStatus: ACTIVE` (`GET /bank-account/{id}`). **La CLABE no va al repo ni al seed.**
- [ ] **Paso 4:** registrar el webhook en el portal de pey (Desarrollador) apuntando a `https://<deploy>/api/webhooks/pey` y guardar el secreto en Vercel.
- [ ] **Paso 5:** verificar que ninguna key quedó en git: `git log -p | grep -iE "whsec_|sk-|Bearer "` → sin resultados.

### Tarea A1: Cliente de pey

**Archivos:**
- Crear: `lib/pey.ts`
- Prueba: `tests/pey.test.ts`

**Interfaces:**
- Produce: `createCodiQr(input: { amountPesos: number; concept: string; expirationSec: number }): Promise<{ id: string; qrString: string; qrImage: string | null }>`, que llama a `POST https://api.pey.mx/codi/qr` con `Authorization: Bearer ${PEY_API_KEY}`, `generateImage: true` y `concept` de 40 caracteres como máximo.

- [ ] **Paso 1: prueba que falla**

```ts
test('manda el monto en pesos y la expiración', async () => {
  const fetchMock = mockFetch({ status: 201, body: { id: 'IDC1', qrString: 'x', qrImage: 'b64' } });
  await createCodiQr({ amountPesos: 0.01, concept: 'Venta Abarpay', expirationSec: 600 });
  expect(fetchMock.lastBody()).toMatchObject({ amount: 0.01, expiration: 600, generateImage: true });
});
test('error de pey se propaga con su type', async () => {
  mockFetch({ status: 400, body: { error: { message: 'm', type: 'INVALID_AMOUNT', requestId: 'r' } } });
  await expect(createCodiQr({ amountPesos: -1, concept: 'x', expirationSec: 600 })).rejects.toThrow('INVALID_AMOUNT');
});
```

- [ ] **Paso 2:** `npx vitest run tests/pey.test.ts` → FAIL.
- [ ] **Paso 3:** implementar `createCodiQr` en `lib/pey.ts`.
- [ ] **Paso 4:** `npx vitest run tests/pey.test.ts` → PASS.
- [ ] **Paso 5:** prueba manual con la key real: un QR de $0.01. Verificación: devuelve `id` y `qrString`. **No pagar todavía.**
- [ ] **Paso 6:** commit.

### Tarea A2: Crear venta y consultar estado

**Archivos:**
- Crear: `app/api/sales/route.ts`, `app/api/sales/[id]/route.ts`, `lib/sales.ts`
- Prueba: `tests/sales.test.ts`

**Interfaces:**
- Consume: `createCodiQr` (A1), tablas de D1.
- Produce: `POST /api/sales` → `SaleCreated`; `GET /api/sales/:id` → `SaleStatus`. `chargedCents = MODO_DEMO ? 1 : totalCents`. `expiresAt = now + 600s`.

- [ ] **Paso 1: pruebas que fallan**

```ts
test('total = suma de qty × unitPriceCents; en demo cobra 1 centavo', async () => {
  const r = await createSale({ employeeId: E1, items: [{ productId: P1, name: 'Coca', qty: 2, unitPriceCents: 1800 },
                                                      { productId: P2, name: 'Sabritas', qty: 1, unitPriceCents: 2200 }] }, { modoDemo: true });
  expect(r.totalCents).toBe(5800);
  expect(r.chargedCents).toBe(1);
});
test('carrito vacío o qty <= 0 se rechaza', async () => {
  await expect(createSale({ employeeId: E1, items: [] }, { modoDemo: true })).rejects.toThrow();
});
test('venta pendiente con expiresAt vencido se reporta expired', async () => {
  const s = await insertSale({ status: 'pending', expiresAt: minutesAgo(1) });
  expect((await getSaleStatus(s.id)).status).toBe('expired');
});
```

- [ ] **Paso 2:** correr → FAIL.
- [ ] **Paso 3:** implementar `createSale(input, opts): Promise<SaleCreated>` y `getSaleStatus(id): Promise<SaleStatus>` en `lib/sales.ts`. Los precios se toman de la tabla `products`, nunca del cliente. `getSaleStatus` marca `expired` si la venta sigue `pending` y ya pasó `expires_at`.
- [ ] **Paso 4:** correr → PASS.
- [ ] **Paso 5:** commit.

### Tarea A3: Webhook de pey (lo más crítico)

**Archivos:**
- Crear: `app/api/webhooks/pey/route.ts`, `lib/webhook.ts`
- Prueba: `tests/webhook.test.ts`

**Interfaces:**
- Consume: tablas de D1. Evento documentado: `type: "codi.qr.payment_received"` con `codiQrId`, `transactionId`, `datePaid`, `amount`.
- Produce: `handlePeyWebhook(rawBody: string, headers: Headers): Promise<{ status: 200 | 401; outcome: string }>`. Al aplicar el pago: venta → `paid`, `pey_transaction_id`, `paid_at`, y descuenta `stock` de cada item, todo en una sola transacción.

- [ ] **Paso 1: pruebas que fallan**

```ts
test('firma inválida → 401 y nada cambia', async () => {
  const r = await handlePeyWebhook(body(paidEvt), headersWithBadSignature());
  expect(r.status).toBe(401);
});
test('pago válido marca paid y descuenta inventario una vez', async () => {
  const sale = await seedPendingSale({ peyQrId: 'IDC1', chargedCents: 1, items: [{ productId: P1, qty: 2 }] });
  const stockAntes = await stockOf(P1);
  await handlePeyWebhook(...signed(paidEvt({ codiQrId: 'IDC1', amount: 0.01 }), 'wh_1'));
  expect((await getSaleStatus(sale.id)).status).toBe('paid');
  expect(await stockOf(P1)).toBe(stockAntes - 2);
});
test('mismo webhook-id dos veces → outcome duplicate, inventario no baja dos veces', async () => {
  const evt = signed(paidEvt({ codiQrId: 'IDC1', amount: 0.01 }), 'wh_1');
  await handlePeyWebhook(...evt);
  const r = await handlePeyWebhook(...evt);
  expect(r.outcome).toBe('duplicate');
});
test('codiQrId desconocido → 200 con outcome unknown_qr, no toca ventas', async () => { /* ... */ });
test('monto distinto a charged_cents → amount_mismatch, la venta sigue pending', async () => { /* ... */ });
test('pago que llega para una venta expired → se registra, no reactiva en silencio', async () => { /* outcome 'late_payment' visible en Mi tienda */ });
```

- [ ] **Paso 2:** correr → FAIL.
- [ ] **Paso 3:** implementar. Verificar la firma sobre el **body crudo** con `standardwebhooks` y `PEY_WEBHOOK_SECRET`. Insertar primero en `webhook_events` (la llave primaria `webhook_id` asegura la idempotencia). Comparar `Math.round(amount*100) === charged_cents`.
- [ ] **Paso 4:** correr → PASS.
- [ ] **Paso 5 · H1 (sábado 16:00):** prueba real. Venta de texto → QR de $0.01 → **una persona paga desde su app bancaria** → el log de webhooks de pey muestra 200 → `select status from sales` → `paid`. Pegar la captura en el canal del equipo.
- [ ] **Paso 6:** commit.

### Tarea B1: Captura por texto y voz

**Archivos:**
- Crear: `app/api/cart/parse/route.ts`, `lib/parse.ts`
- Prueba: `tests/parse.test.ts`

**Interfaces:**
- Consume: tabla `products` (nombre, alias, precio).
- Produce: `parseCart(input: { type: 'text'|'audio'; data: string }): Promise<ParseResult>`. Para audio: transcripción con OpenAI y luego el mismo camino que texto. El modelo devuelve salida estructurada con `productId` **solo de la lista del catálogo** que se le pasa en el prompt; lo que no empata va a `unmatched`. Los precios salen de la base, nunca del modelo.

- [ ] **Paso 1: pruebas que fallan** (contra la API real, marcadas como `integration`)

```ts
test('"dos cocas y unas sabritas" → 2 Coca-Cola 600 ml + 1 Sabritas sal 45 g', async () => {
  const r = await parseCart({ type: 'text', data: 'dos cocas y unas sabritas' });
  expect(r.items).toEqual(expect.arrayContaining([
    expect.objectContaining({ name: 'Coca-Cola 600 ml', qty: 2 }),
    expect.objectContaining({ name: 'Sabritas sal 45 g', qty: 1 })]));
});
test('producto fuera de catálogo va a unmatched y no inventa precio', async () => {
  const r = await parseCart({ type: 'text', data: 'un chicle de menta y una coca' });
  expect(r.unmatched.join(' ')).toMatch(/chicle/i);
  expect(r.items.every(i => i.productId)).toBe(true);
});
test('los precios vienen del catálogo', async () => {
  const r = await parseCart({ type: 'text', data: 'una coca' });
  expect(r.items[0].unitPriceCents).toBe(await priceOf('Coca-Cola 600 ml'));
});
```

- [ ] **Paso 2:** correr → FAIL.
- [ ] **Paso 3:** implementar `parseCart` para `text` y `audio`. El ID de modelo de OpenAI se confirma con los mentores; va en una constante en `lib/parse.ts`.
- [ ] **Paso 4:** correr → PASS en 10 frases de prueba del equipo (al menos 9/10 correctas; anotar las que fallan).
- [ ] **Paso 5:** commit.

### Tarea C1: Pantallas Cobrar y QR

**Archivos:**
- Crear: `app/page.tsx` (selector de empleado), `app/cobrar/page.tsx`, `app/cobro/[id]/page.tsx`

**Interfaces:**
- Consume: `POST /api/cart/parse`, `POST /api/sales`, `GET /api/sales/:id`.
- Produce: el flujo del boceto (pantallas 1 y 2). Botón "Cobrar $X". Si `chargedCents !== totalCents`, mostrar "Modo demo: se cobra $0.01". Si hay `unmatched`, mostrar chips para resolver o quitar.

- [ ] **Paso 1:** pantalla Cobrar con dos entradas (escribir, mantener presionado para dictar) que llenan el mismo carrito editable (+/−, quitar), más botones rápidos para los 8 productos que más se venden.
- [ ] **Paso 2:** pantalla QR con `qrImage`, monto y "Esperando pago…". Al expirar: "El cobro venció" y botón "Generar nuevo cobro".
- [ ] **Paso 3:** verificación en un celular real (no solo el emulador del navegador): el QR se ve y se escanea desde una app bancaria.
- [ ] **Paso 4:** commit.

### Tarea C2: Pantalla Pagado (voz) y varios empleados

**Archivos:**
- Crear: `app/cobro/[id]/pagado.tsx`, `lib/realtime.ts`, `lib/announce.ts`

**Interfaces:**
- Consume: Realtime de `sales` (update a `paid`), `GET /api/sales/:id`.
- Produce: `announcePaid(amountCents: number): void`, que dice "Ya te pagaron N pesos" con `speechSynthesis` del navegador en `es-MX` (sin red, sin latencia). Todos los teléfonos con la app abierta reciben el aviso, y el dueño ve quién cobró.

- [ ] **Paso 1:** suscribirse a cambios de `sales`. Al llegar `paid`: pantalla verde completa más `announcePaid`.
- [ ] **Paso 2:** al recuperar foco o red (`visibilitychange`, `online`), consultar `GET /api/sales/:id` y pintar el estado real.
- [ ] **Paso 3:** verificación con 2 celulares: el empleado cobra, una persona paga $0.01 y **los dos** teléfonos se ponen verdes y hablan. El navegador exige un toque previo para habilitar audio: poner un botón "Activar avisos de pago" en la entrada.
- [ ] **Paso 4:** commit.

### Tarea C3: Mi tienda (corte del día)

**Archivos:**
- Crear: `app/mi-tienda/page.tsx`, `app/api/reports/today/route.ts`
- Prueba: `tests/report.test.ts`

**Interfaces:**
- Produce: `GET /api/reports/today` → `DayReport`. Solo cuenta ventas `paid` de hoy en hora de CDMX (`America/Mexico_City`). `lowStock` = productos con `stock <= low_stock_at`.

- [ ] **Paso 1: prueba que falla:** con 2 ventas `paid`, 1 `pending` y 1 `expired`, `totalCents` suma solo las 2 pagadas, y `byEmployee` las separa por empleado.
- [ ] **Paso 2:** implementar y correr → PASS.
- [ ] **Paso 3:** pantalla con total, por empleado, por resurtir y lo que más salió (pantalla 4 del boceto). Pagos tardíos (`late_payment`) visibles como alerta.
- [ ] **Paso 4:** commit.

### Tarea E1: Pitch, demo y entrega

**Archivos:**
- Crear: `docs/pitch.md`, `docs/demo-guion.md`; video de respaldo fuera del repo.

- [ ] **Paso 1:** guion del demo de 3 minutos: problema (30 s) → venta en vivo con pago real de $0.01 (90 s) → Mi tienda (20 s) → modelo de negocio y visión de crédito (40 s).
- [ ] **Paso 2:** deck con los datos del modelo de negocio que tienen fuente. Lo que es hipótesis se presenta como hipótesis. Nada de cifras sin fuente en láminas.
- [ ] **Paso 3:** domingo antes de las 11:00, grabar el video de respaldo con un pago real (por si falla la red del venue).
- [ ] **Paso 4:** domingo 12:00, correo a `hola@aibuilders.lat` con nombre del proyecto, integrantes, link al repo, URL del deploy, video y deck. Verificación: captura del correo enviado (y de la respuesta, si llega).

---

## Fuera de alcance (roadmap en el pitch)

Captura por cámara / visión artificial (gemelo digital del mostrador) · Fiado por WhatsApp · pronóstico de demanda · crédito · recompensas · semáforo físico (precedente: Paytm Soundbox) · pedidos a proveedores/BEES · taquerías · cobro por push (`/codi/pn`).
