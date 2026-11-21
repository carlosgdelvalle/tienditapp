# 06 · Public landing page, offer, and pilot APK

## Use by DSH

This document is the complete instruction set for Abarpay's public page, commercial offer, and pilot APK distribution. DSH means DeepSeek Harness. The codebase is `main` at `75c1f35`, reviewed on 21-Nov-2026.

The public scope confirms a self-service `Gratis` offer, a `Control` pilot at MXN 149 per store per month with manual billing, and an invitation to express interest in the future guided `Formalización` pilot at MXN 399 per month for three months. The financial dossier is future research. Pilot distribution uses a signed Android APK on the product domain.

DSH must follow this order:

1. Implement the page and its real states first, with versioned data and prices.
2. Connect each CTA to an existing destination. A button without a destination, or a link that promises an unpublished feature, blocks the package.
3. Instrument campaign, visit, CTA, verified registration, store creation, first sale, paid Control, refund, and retention events without bank data or customer data.
4. Verify claims against the deployed build, the APK version, and each flow's contract.
5. Validate responsiveness, keyboard use, screen-reader support, contrast, and reduced motion before acceptance.

A price change, a new commercial promise, or a test involving money requires authorization from the product owner. The page may use `SIMULADO` fixtures for product and metrics while the real implementation is in progress.

## Current state and destinations

| Route | State in `75c1f35` | Required public use |
|---|---|---|
| `/` | Redirects to `/console`. | Show the public landing page. The console remains on a separate route. |
| `/console` | Owner console with a shared PIN and store views. | Internal use during the transition. The target is owner entry by QR and a dedicated session. |
| `/invite/{token}` | Invitation page with a link to the app. | Keep it and test expired, reused, and correctly accepted links. |
| `/empezar` | Does not exist. | Destination for the `Empezar gratis` CTA. It must open real sign-up or an honest waiting list with a visible state. |
| `/entrar` | Does not exist. | Destination for the `Entrar a mi tienda` CTA. It must start the QR access challenge. |
| `/apk-piloto` | Does not exist. | Delivery of the signed APK or an explanation of pilot status. Never serve a file without a signature and hash. |

DSH may use other routes if the coordinator approves them, provided every CTA has a destination test and no dead link remains.

## Positioning

The landing page sells operational control for a small store. The central promise is to collect payment, know who owes money, and restock with information from the business. The proof is the real product in operation, not an abstract list of technology.

| Element | Decision |
|---|---|
| Audience | Owner of a small neighborhood store or small business in Mexico who takes cash, accepts CoDi, and records debts. |
| Primary job | Complete a sale, collect a debt, and decide what to buy without losing clarity. |
| Objective to demonstrate before publishing | Cash and receipts available offline, online credit sales with balance and history, CoDi with server confirmation, and stock shared when registers synchronize. |
| Tone | Direct, operational, and in Mexican Spanish. Talk about the store, not the architecture. |
| Visual proof | Screenshots or a recording of the accepted build, with fictional data labeled as such. |
| Price authority | Versioned product table. An experiment does not change the charged price. |

## Truthfulness rules

| Capability | Permitted claim | Prohibited claim |
|---|---|---|
| Offline cash | `Registra ventas en efectivo y comprobantes en el teléfono cuando no hay señal.` | `Todo Abarpay funciona sin internet.` |
| Credit sales | `Consulta saldos y registra cargos o abonos con conexión.` | `Autoriza fiado sin conexión` or `cobra deudas automáticamente`. |
| CoDi | `Muestra el QR y confirma el pago cuando el servidor lo verifica.` | `Pago garantizado`, `dinero inmediato` or `sin riesgo`. |
| Inventory | `Comparte existencias cuando las cajas se sincronizan. Las diferencias se revisan.` | `Inventario exacto en tiempo real` without evidence from every till. |
| Community | `Participación opcional, apagada por defecto, con beneficio y retiro explicados.` | `Vendemos tus datos` or `datos anónimos garantizados`. |
| Security | `Datos separados por tienda y accesos por membresía.` | `100% seguro`, `bancos certifican todo` or a certification the product has not earned. |
| Pilot APK | `Instala una versión firmada, verificable y con sus notas de versión.` | `Descarga el APK` next to an unsigned file, a file without a hash, or one of unknown origin. |
| Formalización | `Piloto guiado de tres meses, sin renovación automática y con contador externo.` | `Trámite fiscal incluido`, `contador incluido` or `dossier bancario disponible`. |

Do not publish a customer count, savings, sales increase, activation time, or data-pilot benefit without a source, date, sample, and method. If any element is missing, the section shows `Sin datos suficientes` or is omitted.

## First-screen copy

### Navigation

- Brand linked to `/`.
- Links `Cómo funciona`, `Planes`, `Preguntas`.
- Secondary CTA `Entrar a mi tienda`.

### Exact content

**H1**

> Cobra, controla lo que te deben y sabe qué reponer.

**Paragraph**

> Abarpay reúne la venta, el efectivo, el fiado, el inventario y CoDi en el teléfono de tu tienda. El efectivo y sus comprobantes quedan en el teléfono cuando falla la conexión. Al volver la señal, todo se sincroniza para que tu equipo trabaje con el mismo estado.

**Primary CTA**

> Empezar gratis

**Return CTA**

> Entrar a mi tienda

**Pilot CTA**

> Instalar APK piloto firmado

**Microcopy below the buttons**

> Gratis incluye historial y exportación. Control cuesta MXN 149 por tienda al mes y se cobra manualmente. La web no procesa cargos automáticos.

**Visual proof**

The main image shows a cash sale with change, the status `Guardado en el teléfono`, and a receipt. If the accepted build does not contain that feature, the image and the offline promise are removed until evidence exists.

## Page sections

### 1. Today's operation

**Title**

> Tu tienda, en orden desde el primer cobro.

**Copy**

> Abre el catálogo, cobra, registra un gasto y revisa lo que pasó hoy. El dueño ve la tienda completa. Cada empleado ve solo lo que necesita para su turno.

Three visual proofs, each labeled `SIMULADO` when it uses fictional data:

1. `Cobrar` with products, total, and change.
2. `Inicio` with sales, amount collected, credit owed, and low-stock products.
3. `Inventario` with stock, latest movement, and a restock alert.

### 2. Offline cash and receipts

**Title**

> La caja sigue cuando la señal no.

**Copy**

> Cobra en efectivo, calcula el cambio y entrega un comprobante con una referencia estable aunque no haya internet. El teléfono conserva la venta y el movimiento de existencia. Al reconectar, envía la operación una sola vez y muestra si quedó pendiente, sincronizada o necesita atención.

**Clarification**

> CoDi, fiado, invitaciones y cambios de cuenta necesitan conexión. Abarpay muestra qué se puede terminar en el teléfono y qué falta del servidor.

**Required proof**

A short video of the phone in airplane mode showing a sale, the receipt, a restart, and synchronization. The recording is replaced if the version changes.

### 3. CoDi to the store account

**Title**

> El QR es el inicio. La confirmación es la que cuenta.

**Copy**

> Abarpay crea el cobro CoDi para la cuenta activa de tu tienda. El pago se marca como confirmado cuando el servidor verifica la transacción. Una captura de pantalla no cambia el estado.

Concise steps:

1. Register the receiving account and wait for activation.
2. Generate the QR from the sale.
3. Check the status until verified confirmation is received.

**Clarification**

> La activación bancaria puede tardar hasta cinco días hábiles. La página no promete disponibilidad inmediata ni un banco específico hasta que la cuenta esté activa.

### 4. Credit sales with history

**Title**

> Lo que te deben, con nombre y con historial.

**Copy**

> Registra una venta fiada con el cliente correcto. Consulta el saldo, registra un abono parcial o liquida la deuda. Cada movimiento conserva fecha, responsable y nota. El fiado se confirma con conexión para no duplicar una deuda desde dos teléfonos.

Do not show debt amounts for real people. The demo uses fictional names and a visible `SIMULADO` label.

### 5. Restocking with a next action

**Title**

> Sabe qué falta y qué sigue.

**Copy**

> Las existencias bajas se convierten en una lista de trabajo. Revisa el producto, arma el pedido con tu proveedor, recibe la mercancía y publica la entrada cuando esté aprobada. Si dos cajas vendieron la última unidad, Abarpay conserva ambas ventas y abre una diferencia para revisar.

**Status**

The section is published only if the order and receiving flow exists in the accepted build. While it is a draft, use `Estamos preparando esta función` and a `Me interesa el piloto` CTA.

### 6. Built for a store that does not stop

Three columns with verifiable claims:

| Columna | Texto |
|---|---|
| En el teléfono | `Cobra, consulta y conserva comprobantes en el dispositivo.` |
| Con tu equipo | `Invita por liga o QR y asigna permisos por persona.` |
| Para decidir | `Revisa ventas, deudas y reposición con periodos y fuentes claras.` |

### 7. History and export always available

**Title**

> Lo que registraste sigue siendo tuyo.

**Copy**

> El plan Gratis incluye historial y exportación. Si usas Control o participas en un piloto de datos, puedes consultar y recuperar tus registros. Cambiar de opinión sobre la comunidad no borra tu historial.

Avoid `propiedad absoluta` and unreviewed legal promises. The copy describes operational access while the privacy notice and terms define the complete legal relationship.

## Plans

### Gratis

**Price**

> MXN 0

**Text**

> Incluye caja, catálogo, inventario básico, registro de ventas, CoDi sin recargo de Abarpay, historial y exportación. La web no procesa cargos automáticos.

**CTA**

> Empezar gratis

The server applies the matrix per store. Isolation, permission checks, and verified CoDi confirmation are universal. It never blocks consultation or export of records that have already been created.

### Control

**Price**

> MXN 149 por tienda al mes

**Label**

> Piloto con cobro manual

**Text**

> Control incluye permisos por empleado, alertas de reposición, herramientas de conciliación y reportes de margen y fiado. Se activa para una tienda después de confirmar el pago del periodo. La facturación es manual y no existe cargo automático desde la landing. La continuación se confirma antes de emitir el siguiente cobro manual. Si no se paga el siguiente periodo, las automatizaciones de Control se suspenden y conservas historial y exportación.

**CTA**

> Me interesa Control

**Visible terms**

- Precio por tienda y por mes.
- Cobro manual fuera de esta página.
- Fecha de inicio y periodo cubierto en la confirmación.
- Impuestos y factura se muestran en la cotización aplicable.
- Las funciones de Control se listan desde la matriz de producto. Las no publicadas no se incluyen.

Do not claim `sin límites`, `ilimitado`, `cancelación instantánea`, or `garantía de devolución` until those conditions are approved.

### Formalización

**Price**

> MXN 399 al mes durante 3 meses

**Label**

> Próximo piloto · registro de interés, sin renovación automática

**Text**

> Estamos preparando tres meses de Control con acompañamiento para alta o actualización en el RFC, preparación para facturar y un primer cierre para tu contador. Al terminar vuelves a Gratis o eliges Control. El contador se cotiza aparte. Hoy puedes registrar interés; no hay cargo ni renovación automática.

**CTA**

> Me interesa el piloto

**Clarifications**

- La página no presenta Formalización como trámite fiscal terminado.
- La página no promete aceptación bancaria ni crédito.
- El contador externo define alcance, honorarios y responsabilidades aparte.
- Al terminar los tres meses, la continuidad requiere una decisión nueva.

### Financial dossier

**Label**

> Investigación futura

**Text**

> Estamos evaluando un expediente que tú, incluso en Gratis, podrías revisar y compartir con una financiera específica. Distinguiría ventas de caja y cobros confirmados. Probaríamos una tarifa fija que pagaría la financiera por expediente entregado. La financiera decide el crédito. Hoy sólo registramos interés.

**CTA**

> Me interesa el expediente

The CTA opens an explanation or interest form. It is not presented as a credit application or as a sellable product.

### Comparison matrix

| Capacidad | Gratis | Control | Formalización |
|---|---|---|---|
| Operación de tienda | Sí | Sí | Sí |
| Historial y exportación | Sí | Sí | Sí |
| Efectivo y comprobantes offline | Según build aceptado | Según build aceptado | Según build aceptado |
| Fiado en línea | Según build aceptado | Según build aceptado | Según build aceptado |
| Permisos configurables por empleado, alertas de reposición, conciliación operativa y reportes de margen/fiado | No | Incluidos | Incluidos en la hipótesis de piloto |
| Acompañamiento operativo | No | No | Sí, durante tres meses |
| Contador | No | No | Servicio externo, pagado aparte |
| Renovación automática | No aplica | No, cobro manual | No |
| Precio | MXN 0 | MXN 149 al mes por tienda | MXN 399 al mes por 3 meses |

The expression `Según build aceptado` may be replaced by `Sí` only when the published version has evidence of the flow and the corresponding physical test.

## Signed pilot APK

The download section contains these required fields. If a field is missing, the button is disabled and the page explains what is missing.

| Field | Content |
|---|---|
| Versión | Name and code, for example the current baseline `1.2.3` and `15` when the artifact matches. |
| Fecha | Build date in Mexico's time zone. |
| Revisión fuente | Git SHA that produced the APK. |
| SHA-256 | Hash of the exact published file. |
| Firma | Certificate fingerprint and verification result. |
| Compatibilidad | Minimum Android supported by the build, `API 26` in the baseline. |
| Notas | Included features, limits, and local data changes. |
| Instrucciones | Installation, update, backup, and recovery. |

Copy:

**Title**

> Prueba Abarpay en el teléfono de tu tienda.

**Text**

> El piloto se instala con un APK firmado. Antes de descargar, revisa la versión, el SHA-256 y las notas. La actualización conserva los datos locales autorizados.

**CTA**

> Instalar APK piloto firmado

**Unavailable state**

> El APK piloto aún no está publicado. Déjanos tu interés y te avisaremos cuando exista una versión firmada y verificada.

**Alternative CTA**

> Solicitar el APK piloto

A button that downloads from a temporary URL, a debug file, an expired Cloudflare link, or a binary whose signature does not match the App Links is not permitted.

## Community and data

**Title**

> Tú decides si compartes. Gratis sigue teniendo historial y exportación.

**Copy**

> Podemos pedir tu permiso para usar información agregada de tienda en un piloto con un socio de abasto. La participación empieza apagada. Antes de activarla verás qué campos se usan, para qué decisión, qué recibe el socio, cuánto se conserva y cómo salir. La salida detiene contribuciones futuras y conserva las reglas de los reportes ya entregados. Tus datos de clientes y tu cuenta bancaria no forman parte del reporte agregado.

**Visible controls**

- Toggle `Participar en el piloto de datos`, off by default.
- Link to the privacy notice and the current purpose.
- Consent version date.
- Button `Dejar de participar` with confirmation and next step.
- Link `Descargar mi historial` available even without participation.

The page does not use the phrase `datos anónimos` as a legal guarantee. It may say `datos agregados con controles de divulgación`. Legal review occurs before any real external delivery.

## Campaign measurement

Measurement supports improvement of the page and commercial operations. It does not become a promise of advertising return.

| Event | Permitted fields | Use |
|---|---|---|
| `landing_view` | route, variant, permitted UTMs, device, and date | Know which version the person saw. |
| `cta_click` | CTA, variant, campaign, responsible actor | Measure intent and destination. |
| `registration_verified` | new or existing store, campaign, actor | Separate verified sign-up from email or visit. |
| `store_created` | non-commercial internal identifier, campaign, actor | Measure initial activation. |
| `first_sale_completed` | channel, internal store, campaign, actor | Measure continuity through a real sale. |
| `control_paid` | period, software amount, campaign, actor | Measure collected revenue, not intent. |
| `refund` | period, amount, aggregate reason, campaign | Separate gross and net revenue. |
| `retention_checkpoint` | cohort, period, active state | Measure later use. |
| `consent_changed` | version, state, date | Audit participation. |

Rules:

1. Store campaign, UTM, variant, and responsible actor on every relevant event.
2. Do not send CLABE, tokens, customer name, phone number, debt, address, sale content, or payment identifiers to analytics or advertising.
3. Use an internal store ID with restricted access. Do not use email as a public key.
4. Distinguish leads, sign-ups, active stores, sales, paid Control, and retention. Do not add stages that are not comparable.
5. If costs are missing or attribution is incomplete, show `Sin datos suficientes` for CAC and ROI.
6. Record overlapping campaign attribution and do not delete duplicates for convenience.
7. Evaluate a price or copy test using real charges and retention, not clicks alone.

### Initial experiments

| Experiment | Variants | Primary metric | Guards |
|---|---|---|---|
| First screen | Full value proposition versus a cash-focused proposition | CTA to verified sign-up | Legibility, comprehension, and approved claims. |
| Entry CTA | `Entrar a mi tienda` as a prominent action versus a secondary link | Approved web sessions | Camera failure with manual code. |
| Control card | Price and manual billing displayed upfront versus in expandable details | Start of Control sign-up | Do not hide the price. |
| Pilot APK | Direct download versus a guided request | Completed installation | Signature, version, and hash present. |
| Community | Short explanation versus a sample report | Informed consent | Off by default and visible exit. |

Interviews are recorded separately from conversion. Willingness to pay is tested with authorized real charges. A click on `Me interesa` does not count as revenue.

## Objections and answers

| Objeción | Respuesta pública |
|---|---|
| ¿Qué pasa si se cae el internet? | El efectivo, su comprobante y los movimientos locales se conservan en el teléfono. CoDi, fiado e invitaciones requieren conexión y la app lo indica. |
| ¿A dónde llega el dinero de CoDi? | A la cuenta receptora activa de la tienda. La página explica el registro y la activación por el proveedor. No afirma que Abarpay retiene el saldo. |
| ¿Puedo perder mi historial? | Gratis incluye historial y exportación. La recuperación de teléfono y la restauración se documentan. |
| ¿Control se cobra solo? | No. El precio es MXN 149 por tienda al mes y el cobro es manual. La confirmación indica el periodo cubierto. |
| ¿Cómo cancelo Control? | La página muestra el canal de contacto y explica que las automatizaciones se suspenden al terminar el periodo pagado. El historial y la exportación permanecen accesibles. |
| ¿Formalización incluye contador? | No. El contador externo trabaja y cobra por separado. El piloto dura tres meses y no se renueva automáticamente. |
| ¿El dossier financiero está disponible? | Es una investigación futura. No está incluido en los planes ni tiene precio o disponibilidad confirmados. |
| ¿Comparten mis datos? | Solo con consentimiento para el piloto descrito. Participación apagada por defecto. Los datos de clientes y la cuenta bancaria quedan fuera del reporte agregado. |
| ¿Por qué piden el APK en vez de Google Play? | El piloto distribuye una build firmada desde el dominio del producto. La ficha de Google Play es una etapa separada. |

## Responsive and availability states

| State | Desktop | Mobile | Action |
|---|---|---|---|
| Sign-up open | Primary CTA and phone handoff. | `Empezar gratis` opens sign-up or download of the available pilot APK. | Both destinations must respond. |
| Sign-up on waiting list | Form or explanation of status. | The same promise and the same review date. | Do not present as available what is not yet available. |
| QR available | Shows QR and manual code with expiration. | `Entrar a mi tienda` starts the same challenge. | Deny, retry, and expire with clear text. |
| APK available | Details with version and SHA-256. | Download button and notes. | Verify the signature before publishing. |
| APK unavailable | Explanation and interest CTA. | The same explanation without a broken link. | Record interest, do not simulate download. |
| Network error | Preserves the last section and offers retry. | Same. | Does not erase a completed form. |

The page must work at 320 CSS px width and on desktop without horizontal scrolling. The primary action remains visible and price blocks do not become illegible tables on mobile.

## Landing-page accessibility

1. A single `h1` and a coherent heading hierarchy.
2. Skip link to the main content.
3. Visible focus and logical tab order.
4. Minimum contrast of 4.5:1 for normal text and 3:1 for large text.
5. Text at 200% without loss of content or actions.
6. Controls at least 24 by 24 CSS px, with sufficient spacing.
7. Price, availability, and community states conveyed with text as well as color.
8. Informative images with alternative text. Decorative images empty.
9. Video without autoplay with sound. Accessible controls and a transcript when it explains a flow.
10. Forms with labels, help, associated errors, and retained data.
11. Reduced motion respected.
12. No commercial text hidden in an image.

Verify with a keyboard, screen reader, zoom, and a mobile test. The target is WCAG 2.2 AA. [WCAG 2.2](https://www.w3.org/TR/WCAG22/)

## Acceptance tests

### Content and commercial truth

1. The first screen contains exactly `Cobra, controla lo que te deben y sabe qué reponer.`
2. `Empezar gratis`, `Entrar a mi tienda`, and `Instalar APK piloto firmado`, or their documented alternative state, exist and work.
3. Gratis shows MXN 0 and includes history and export.
4. Control shows MXN 149 per store per month and manual billing.
5. Formalización shows MXN 399 per month for three months, without automatic renewal and with an accountant paid separately.
6. The dossier appears as future research without an invented price or availability.
7. Community is off by default, explains purpose and withdrawal, and does not condition history or export.
8. Every product figure has a source, date, and version.
9. No customer data, CLABE, credential, payment identifier, or screenshot of real debt appears.

### Routes and CTAs

1. `/` serves the landing page and does not redirect to the console.
2. `Empezar gratis` reaches sign-up or waiting list and preserves the permitted campaign.
3. `Entrar a mi tienda` reaches the challenge and offers a manual code if the camera fails.
4. The APK CTA delivers only a signed version or shows the unavailable state.
5. The published APK shows version, source revision, SHA-256, signature fingerprint, notes, and instructions.
6. In-place update preserves cart, pending sales, receipts, and authorized local data.
7. Existing invitation routes continue to work.

### Measurement

1. Every event carries variant, campaign, and responsible actor when applicable.
2. No bank, debt, or customer data is sent to analytics.
3. Event totals do not confuse visit with registration, sale with payment, or paid Control with interest.
4. Refunds and cancellations are subtracted from collected revenue.
5. CAC and ROI show `Sin datos suficientes` if information is missing.
6. A real pilot test links the campaign, manual charge, and period retention.

### Accessibility and performance

1. Complete keyboard traversal on desktop.
2. Screen-reader test on the first screen, plans, community, and form.
3. Text at 200% without clipping or overlap.
4. Contrast measured in every state.
5. Mobile width of 320 CSS px without horizontal scrolling.
6. The main image does not block LCP or load videos without user action.
7. Error and loading states are accessible and do not rely on color alone.

## Campaign log

Each campaign needs an owner, purpose, date, channel, UTM, variant, known budget or cost, audience, applicable consent, and continuation criterion. If the cost does not exist, the page does not publish ROI. If attribution is shared, the log preserves the overlap.

Approval of a campaign includes the commercial promise, landing-page version, and CTA destination. A change in price or availability invalidates the previous approval.

## DSH completion condition

A waiting list or notice of a pending APK is useful only in pre-launch. G2 requires self-service sign-up, a first cash sale, QR entry, and a downloadable signed pilot APK. Formalización and dossier interest forms do not activate plans or generate revenue.

The public package is accepted with the landing page deployed behind an approved route, every CTA with a tested destination, real prices and states, a signed APK with verifiable hash when download is offered, measurement without sensitive data, a WCAG 2.2 AA review, and a capture of the reviewed version on mobile and desktop. A missing resource remains an explicit state, never an implicit promise.
