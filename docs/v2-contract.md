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

## Tickets de soporte (cobros no confirmados) · 15-nov

Decisión: los pendientes/por conciliar ya no son una alarma en el teléfono; son un rastro de eventos en la consola. Si un cobro queda en el limbo, la persona en la tienda crea un ticket en nuestra propia base (sin email/WhatsApp).

- Tabla `support_tickets (id TEXT PRIMARY KEY, store_id TEXT NOT NULL REFERENCES stores(id), sale_id TEXT REFERENCES sales(id), note TEXT, status TEXT NOT NULL CHECK(status IN ('open','resolved')), created_at REAL NOT NULL, resolved_at REAL)`.
- `POST /api/support/tickets` body `{saleId?, note?}`: crea ticket `tkt_<hex>` con contexto automático (estado, totalCents, chargedCents, peyTxId de la venta y nombre del empleado que reporta desde el header `X-Employee-Id`). Sin `saleId` la nota es obligatoria. Si ya hay un ticket abierto para esa venta, devuelve el mismo ticket con `alreadyOpen:true` (200). Responde `{id, saleId, saleStatus, saleTotalCents, chargedCents, peyTxId, note, status, createdAt, reportedByName, alreadyOpen}`.
- `GET /api/support/tickets?status=open|resolved|all` (owner): `{items:[...]}` ordenado por created_at desc.
- `PATCH /api/support/tickets/{id}` (owner) body `{status?, note?}`: actualiza; al resolver pone `resolved_at`.
- Android: la tarjeta «Pendientes» del Inicio del dueño se reemplaza por «Cobrado hoy» (collectedCents). En la pantalla de venta PEY `por_conciliar` (no asentada) aparece el botón «Reportar problema» → diálogo con nota opcional → `POST /api/support/tickets` → mensaje «Ticket #… creado» o «Ya existe el ticket #…». Expired/canceled quedan como estados normales sin acción.
- Consola: sección «Tickets de soporte» (tabla con ticket, venta, estado, reportado por, nota, fecha; botones Resolver/Reabrir vía PATCH) y tabla «Eventos PEY» con las ventas PEY recientes de cualquier estado (folio, estado, monto, hora) como rastro de eventos, resaltando pendientes/por_conciliar.

## v3 · Generalización a negocios pequeños · 15-nov

Decisiones del dueño (todas confirmadas): CRUD de catálogo en consola Y app; plantillas solo para negocios nuevos (tiendita usa un catálogo curado de resources/catalogo-mx/tiendita; revisar UX para catálogos grandes); tareas fijas por tipo y SOLO se muestran si están asignadas a un empleado; marca «Abarpay» y demo renombrada a nombre genérico; «Fiado» se conserva tal cual; segmentación Productos/Servicios/Comida preparada = sí; Gastos con registro simple + dictado = sí; comprobante compartible imagen/PDF = sí (cliente, en Android).

### Modelo (server/db.py, migraciones aditivas/idempotentes)

- products: ampliar unit CHECK a ('pieza','kg','g','litro','servicio','sesion','turno','minuto','hora','paquete','combo') (requiere recrear la tabla con copia de datos; probar idempotencia). Añadir kind TEXT NOT NULL DEFAULT 'producto' CHECK(kind IN ('producto','servicio','platillo')), category TEXT (NULL), duration_minutes INTEGER (NULL). unlimited_stock=1 significa «no lleva inventario» para servicios/platillos.
- day_tasks: (id INTEGER PK, store_id TEXT NOT NULL REFERENCES stores(id), key TEXT NOT NULL, title TEXT NOT NULL, assigned_employee_id INTEGER NULL REFERENCES employees(id), active INTEGER NOT NULL DEFAULT 1, UNIQUE(store_id,key)). Las plantillas por tipo se crean al aplicar plantilla con assigned NULL; un empleado SOLO ve las tareas que le están asignadas (GET /api/tasks con X-Employee-Id).
- expenses: (id INTEGER PK, store_id, employee_id INTEGER NULL REFERENCES employees(id), amount_cents INTEGER NOT NULL, note TEXT, created_at REAL NOT NULL).
- STORE_NAME por defecto pasa a «Mi negocio» (solo bases nuevas; Render conserva su nombre hasta que el dueño lo cambie).

### Endpoints nuevos

- GET /api/catalog?q=&category=&kind=&limit=&offset= → {items:[...con kind/category/durationMinutes/aliases/stock...], total} (público como bootstrap).
- POST /api/catalog (owner) {name, unit, priceCents, aliases?, stockMilli?, unlimitedStock?, kind?, category?, durationMinutes?, quick?}; PATCH /api/catalog/{id} (owner); DELETE /api/catalog/{id} (owner; 409 si tiene ventas o movimientos). Validar unit y kind.
- POST /api/catalog/templates/apply {businessType} (owner): SOLO si la tienda no tiene items todavía (409 si ya tiene); inserta los items de la plantilla del tipo + las day_tasks de la plantilla (assigned NULL). businessType ∈ {tiendita, tortilleria, taqueria, comida-corrida, peluqueria, estetica, fondita, otro}. Tiendita: catálogo curado (~24-32 items con categoría y precio demo) leído de resources/catalogo-mx/tiendita/ (README.md, resumen.json, catalogo-incluir.csv); no incrustar el CSV completo.
- GET /api/tasks (owner: todas; empleado: solo las suyas asignadas y activas). PATCH /api/tasks/{id} (owner) {assignedEmployeeId?: int|null, active?: bool, title?}.
- POST /api/expenses {amountCents, note?} (cualquier empleado activo vía X-Employee-Id; sin header abierto v1); GET /api/expenses?limit=50 (owner). POST /api/expenses/voice {text} → parse {amountCents, note} sin guardar (parser: «veinte pesos de gas» → 2000, nota «gas»; dígitos y palabras; la app confirma).
- /api/reports/today agrega totalExpensesCents (gastos de hoy).

### Android (1.2.0 / code 12)

- Onboarding: tipos ampliados (Tiendita/Abarrotes, Miscelánea, Tortillería, Taquería, Comida corrida, Peluquería/Barbería, Estética de uñas, Fondita, Otro); paso «¿Qué vendes?» multi-select (Productos / Servicios / Comida preparada y bebidas); metas con «Omitir»; al terminar: PUT profile, POST /api/store/photo (si hay foto), POST /api/catalog/templates/apply {tipo} (ignorar 409 si ya había catálogo), enlazar dueño.
- Catálogo del dueño (nueva pantalla accesible desde Inicio, no una pestaña nueva): lista con búsqueda, chips de categoría, favoritos/rápidos, LazyColumn para catálogos grandes; alta/edición con formulario (nombre, precio, unidad, kind, categoría, stock o sin límite, duración, aliases); borrar con 409 controlado. Los servicios/platillos no muestran controles de stock.
- Presets de cantidad por unidad: servicio/sesión/turno/combo → 1,2,3; kg → 250g/500g/1kg/2kg; minuto → 30/60/90; pieza/g/paquete → +1/−1.
- Tareas: Inicio del empleado muestra SOLO las tareas asignadas a él (GET /api/tasks); tareas sin asignar no aparecen. El dueño ve «Tareas del día» (todas) con asignación por empleado (pantalla desde Inicio).
- Gastos: botón «Registrar gasto» en Inicio (dueño y empleado) → diálogo monto + nota + micrófono (RecognizerIntent → /api/expenses/voice → confirmación) → POST /api/expenses. Los gastos de hoy salen en Reportes (totalExpensesCents).
- Comprobante: en venta asentada (cash/fiado/PEY pagada), botón «Compartir comprobante» → vista previa → «Compartir imagen» (Compose bitmap) y «Compartir PDF» (android.graphics.pdf.PdfDocument) vía ACTION_SEND + FileProvider.
- Copy: «Tu negocio» (no «Tu tiendita»), «Inventario bajo», «disponibles»/«unidades» en badges; «Fiado» se conserva. Demo genérica: referencias a «Tiendita de la Esquina» solo en textos de seed/legacy.

### Consola

- Sección «Catálogo»: tabla con búsqueda y paginación server-side (q/category/kind/limit/offset), alta/edición/borrado, campos kind/unit/category/duration; diseñada para catálogos grandes (no pintar todo de golpe).
- Sección «Gastos»: lista + total de hoy + alta (monto y nota).
- Sección «Tareas»: lista de day_tasks con asignación a empleado (dropdown) y activar/desactivar.
- Copy «negocio»; «Fiado» intacto. La consola ya muestra el tipo de negocio y la foto.

### Reglas que no cambian

- Solo apply_payment marca PEY pagado; el verde es la única señal de entrega; tickets de soporte y eventos PEY siguen igual; equipo/invitaciones/permisos siguen igual.
