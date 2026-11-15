# Contrato v2 · Onboarding, equipo e inventario

Estado: acuerdo de diseño 15-nov-2026. Implementan juntos backend (`server/`), Android y consola.
Los endpoints nuevos siguen el estilo v1: JSON, montos en centavos enteros, cantidades en `qtyMilli` (1000 = 1 pieza o 1 kg), una tienda, acceso mock.

## Decisiones confirmadas con el dueño

- Invitaciones de empleados: flujo multi-dispositivo con token (seguridad falsa, persistencia real).
- Valor de inventario: **precio de venta × existencias** (no hay costo).
- Base nueva: solo el dueño. Bases existentes conservan empleados con historial; el dueño puede desactivarlos en la app.
- Foto del negocio: se sube al backend y se muestra en la consola.
- Reportes solo dueño: se ocultan en la app y el servidor rechaza con 403 si llega el header `X-Employee-Id` de un empleado.
- Desplegar a Render al final (autorizado).

## Identidad simulada

Header opcional `X-Employee-Id` (int). Regla: si el header viene, el servidor lo valida contra `employees` (activo=1) y aplica rol/permisos; si no viene, se conserva el comportamiento abierto v1 (consola y scripts no se rompen). La app Android **siempre** manda el header después de elegir perfil.

## Esquema nuevo (migración aditiva, idempotente)

- `employees`: agregar `nickname TEXT`, `can_sell INTEGER NOT NULL DEFAULT 1`, `can_fiado INTEGER NOT NULL DEFAULT 1`, `can_inventory INTEGER NOT NULL DEFAULT 0`. `role` sigue en ('owner','employee').
- `invites`: tabla `invites (token TEXT PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), created_at REAL NOT NULL, expires_at REAL NOT NULL, accepted INTEGER NOT NULL DEFAULT 0)`.
- `store_settings` (una fila por tienda): `store_id TEXT PRIMARY KEY REFERENCES stores(id), business_type TEXT NOT NULL DEFAULT '', owner_name TEXT NOT NULL DEFAULT 'Doña Rosa'`. El nombre visible de la tienda sigue en `stores.name`.
- Seed nuevo: `SEED_EMPLOYEES` solo el dueño (id 1). En bases existentes NO se borran empleados; las migraciones solo agregan columnas y la fila de `store_settings`.

## Endpoints

### Perfil de tienda

- `GET /api/store/profile` → `{storeId, name, businessType, ownerName}`.
- `PUT /api/store/profile` (owner) body `{name?, businessType?, ownerName?}` → perfil actualizado.
- `POST /api/store/photo` (owner) body `{"dataUrl": "data:image/jpeg;base64,..."}` → valida prefijo/≤5 MB, guarda en el **directorio de la base** como `store-photo.jpg` (persiste en el disco de Render), devuelve `{ok:true}`.
- `GET /api/store/photo` → FileResponse de la foto (404 si no existe). La consola usa `<img src="/api/store/photo">` con cache-buster.

### Empleados y permisos

- `GET /api/employees` (owner) → `{items:[{id,name,nickname,role,active,canSell,canFiado,canInventory}]}`.
- `PATCH /api/employees/{id}` (owner) body `{name?, nickname?, active?, canSell?, canFiado?, canInventory?}` → empleado actualizado.
- `POST /api/employees/invites` (owner) body `{name, canSell=true, canFiado=true, canInventory=false}` → crea empleado `active=0`, token de 32 hex, expira en 7 días; responde `{token, employeeId, url: "https://abarpay-api.onrender.com/invite/<token>"}`.
- `GET /api/employees/invites/{token}` → `{token, employeeId, name, storeName, businessType, permissions...}` (404 si no existe o expiró; 410 si ya aceptado).
- `POST /api/employees/invites/{token}/accept` body `{nickname}` → activa el empleado (`active=1`), guarda nickname, `accepted=1`; responde el perfil completo del empleado.
- `DELETE /api/employees/invites/{token}` (owner) → desactiva/borra el pendiente; no toca empleados ya aceptados.

### Inventario

- `GET /api/inventory` → `{items:[{productId,name,unit,priceCents,stockMilli,unlimitedStock,valueCents,lastUpdatedAt,lastUpdatedById,lastUpdatedByName,lastUpdatedByNickname}], totalValueCents}`. `valueCents = round(priceCents * stockMilli / 1000)` (0 si ilimitado). `lastUpdated*` sale del movimiento más reciente de `inventory_movements` (o null).
- `POST /api/inventory/set` body `{productId, qtyMilli, note?}` con `X-Employee-Id` dueño o `can_inventory`: fija el stock absoluto (delta = target − actual), inserta movimiento con `employee_id`; rechaza productos ilimitados; stock negativo permitido como en v1.
- `POST /api/inventory/adjust` (existente): ahora exige `X-Employee-Id` dueño o `can_inventory` (si el header falta, sigue abierto).
- `POST /api/inventory/voice` body `{text}` → `{items:[{productId,name,qtyMilli,unit}], note?}`. Solo interpreta, **no aplica**; la app confirma y llama `/set`.

### Parser de conteo por voz

- `parse_count(text)` en `server/parser.py`: frase tipo «coca colas de 600… 4, 5, 6… 12 piezas» → Coca-Cola 600 ml con **12** piezas. Reglas: el último número explícito (dígitos o palabras «doce») gana para ese producto; «piezas/pieza» → unidad pieza, «kilos/kilo/medio kilo» → kg; productos por alias existente; si no hay cantidad y hay un solo producto, devolver 1? No: si no hay cantidad, devolver el producto con qty null para que la app pregunte. Varios productos en una frase: cada uno con su último número antes del siguiente producto (esfuerzo razonable; la app siempre muestra confirmación).

### Reportes

- `GET /api/reports/today`: si llega `X-Employee-Id` y el rol no es `owner` → 403 `{"detail":"Solo el dueño ve reportes"}`. Sin header: compatible v1.

### Bootstrap

- `GET /api/bootstrap` ahora incluye: `store: {id, name, businessType, ownerName}`, `employees` solo activos con `{id,name,nickname,role,canSell,canFiado,canInventory}` y `demoMode`.

### Enlace profundo / App Links

- El backend sirve `GET /invite/{token}` → HTML mínimo que intenta `abarpay://empleado/<token>` y ofrece el enlace; y `GET /.well-known/assetlinks.json` con `[{relation:["delegate_permission/common.handle_all_urls"], target:{namespace:"android_app", package_name:"mx.abarpay.mobile", sha256_cert_fingerprints:["f5219d47c4ac345bb4671d546653038a9ca949018ec47e713d2a6f06a4482618"]}}]` para que el enlace HTTPS abra la app.
- Android declara intent-filter para `abarpay://empleado/{token}` y para `https://abarpay-api.onrender.com/invite/{token}`.

## Android (v1.1.0 / code 11)

- Onboarding solo dueño en primer arranque (SharedPreferences `onboarded_owner`): metas (chips multi-select: «Organizar mis ventas y gastos», «Controlar lo que me deben», «Gestionar mejor mi inventario», «Ver estadísticas avanzadas»), nombre del dueño, nombre y tipo del negocio (chips: Tiendita, Abarrotes, Miscelánea, Fondita, Otro), foto con cámara (TakePicture) → `PUT /api/store/profile` + `POST /api/store/photo`. Metas se guardan solo en local.
- Encabezado compacto: solo logo pequeño integrado en el contenido (sin nombre de tienda, URL ni engrane arriba). El engrane vive en Inicio del dueño.
- Inicio dueño: tarjetas de estado (Ventas de hoy, Fiado por cobrar, Pendientes, Stock bajo) y «Actividades» (productos bajo stock, invitaciones pendientes, ajustes recientes). Inicio empleado: sus tareas («Contar inventario», «Limpiar tienda», productos bajo stock) y permisos. **Se eliminan** los botones duplicados Fiado/Inventario/Reportes del Inicio (quedan en las pestañas).
- Permisos en la app: sin `can_sell` se oculta «Cobrar»; sin `can_fiado` se deshabilita el chip Fiado; sin `can_inventory` se oculta «Inventario»; «Reportes» solo dueño.
- Equipo (dueño): lista de empleados con nombre propio + nickname y switches de permisos (`PATCH`); «Invitar empleado» → nombre propio + permisos → `POST /invites` → diálogo con QR (generar con ZXing core, agregar `com.google.zxing:core`) y botón compartir (`ACTION_SEND` con el `url`).
- Aceptación de invitado: al abrir `abarpay://empleado/<token>` o el enlace HTTPS, pantalla «Ponle tu apodo» (nickname) → `POST /invites/{token}/accept` → guarda `employee_id` local, auto-selecciona perfil, Reportes oculto. El picker `¿Quién cobra hoy?` solo aparece si no hay perfil ligado.
- Inventario por voz: botón micrófono en Inventario → `RecognizerIntent` (es-MX) → `POST /api/inventory/voice` → hoja de confirmación «Coca-Cola 600 ml: 12 pza» → `POST /api/inventory/set`. Solo si `can_inventory`.
- No tocar MobileFlowTest salvo por nuevos tags/expectativas; la aserción de stock ya usa `stockLabel`.

## Consola (solo `server/static/console.html`)

- Módulo Inventario completo: tarjeta de valor total, tabla por producto con nivel actual, unidad, **valor (precio × nivel)**, **última persona en actualizar** (nombre propio + nickname) y fecha; filtro «solo stock bajo»; controles +1/−1 (usa `/api/inventory/adjust` con `X-Employee-Id: 1`) y «Fijar cantidad» (`/api/inventory/set` con nota).
- La consola muestra la foto del negocio (`/api/store/photo`) si existe, junto al nombre/tipo/owner (`GET /api/store/profile`).
- El resto de la consola no cambia; PIN y refresco de 3 s iguales.

## Pruebas requeridas

- Backend (`/tmp/abar-venv2/bin/python -m pytest server/tests -q`): perfil de tienda + foto (mock de archivos), empleados/permisos, invitaciones (crear/consultar/aceptar/cancelar/expirada), inventario value/lastUpdated, set absoluto, gate de reportes 403, parser de conteo («4, 5, 6… 12 piezas» → 12).
- Android (`cd android && JAVA_HOME=/Library/Java/JavaVirtualMachines/microsoft-21.jdk/Contents/Home ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" ./gradlew testDebugUnitTest`): repo/dominio nuevos + flujos Compose debug (onboarding, equipo/QR, aceptar invitación, confirmación de voz, permisos).
- Ningún agente usa adb, Render, ni hace push/merge. Los cambios se dejan en el working tree; el lead integra, commitea, prueba en el Samsung y despliega.

## Reglas de casa (AGENTS)

Nada de credenciales en chats/commits. Sin pagos reales (solo FakePey SIMULADO). Etiquetas y textos en español. No editar bases de producción; las pruebas usan bases temporales.
