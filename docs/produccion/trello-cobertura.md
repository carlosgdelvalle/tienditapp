# Product card coverage

## Use by DSH

This file is self-contained for reconciling the product scope. DSH stands for DeepSeek Harness. It does not need to read the downloaded export to consult the normalized list. For each pending card, DSH uses the local numeric reference as the stable key, the theme to locate the corresponding package and the acceptance scenario to define the test.

`already covered` requires keeping the current evidence and running the package acceptance when a surface changes. `build` requires a contract and write scope before code. `defer` keeps the feature reported as unavailable until the provider or the external operation exists. `duplicate` points to the canonical card and does not create a second work item. No disposition by itself authorizes deploying, charging or exposing real data.

## Scope and verification

Source board: `AbarPay: Funcionalidades`. The 85 product cards were normalized and the 6 cards from the initial Trello guide were excluded. This document does not reproduce members, internal identifiers, attachments, emails, private links or personal data from the original export.

The evidence was checked against the `main` code at `75c1f35`, reviewed on 21-nov-2026. The cited tests existed at that revision. This document task did not rerun the suites and did not run a new device test.

**Default physical state: NO VERIFICADO EN DISPOSITIVO.** No row constitutes physical acceptance. The `automatizado`, `lectura estática` or `sin implementación` indications describe the available evidence, not a real Android test.

Allowed dispositions:

| Disposition | Meaning |
|---|---|
| `build` | The need is not complete in the baseline and requires contract, implementation and verification. |
| `already covered` | The core behavior exists and has automated evidence in the baseline. It does not imply full product acceptance or a physical test. |
| `defer` | It depends on a provider, operation, authorization or channel that is not yet known. The state reported in the UI may be kept. |
| `duplicate` | The need is covered by another canonical card. The additional scope, if any, is listed in the acceptance. |

Routing to the [execution board](09-paquetes-y-aceptacion.md): T-01 → I6/M1; T-02 → I1/I2/M1; T-03 → I2/M2; T-04 → I1/M3; T-05 → M1/M2/M4; T-06 → M2; T-07 → M2/M4/M6; T-08 → M3; T-09 → M4; T-10 → M1; T-11 → I6/M6; T-12 → I1/M6/M7. In T-07 the store reports belong to the merchant console. The acquisition, software billing and community indicators belong to M6 in the platform.

The T reference followed by a number comes from the `idShort` of each card (e.g. T7 corresponds to `idShort=7`). It is not the feature number written by the team. In the original export the 85 values can be reconciled without publishing board links.

Delivery themes:

| Theme | Scope |
|---|---|
| `T-01 Alta y entrega` | Installation, initial signup and APK distribution. |
| `T-02 Identidad, banco y tienda` | Commercial identity, receiving accounts and sessions. |
| `T-03 Equipo` | Invitations, accesses, roles, employees and registers. |
| `T-04 Catálogo e inventario` | Products, prices, stock, adjustments and traceability. |
| `T-05 Cobro` | Cart, cash, CoDi, credit and provider-dependent methods. |
| `T-06 Caja` | Cash movements, closing and handover. |
| `T-07 Reportes y consola` | Indicators, filters, detail, export and web navigation. |
| `T-08 Reposición` | Alerts, providers, orders, receiving and publication. |
| `T-09 Fiado` | Customer, debt, limits, payments, reminders and settlement. |
| `T-10 Soporte y conciliación` | Tickets, CoDi events and differences. |
| `T-11 Web y comercial` | Landing, QR entry and campaign measurement. |
| `T-12 Plataforma` | Internal operation, community and multi-company isolation. |

Scenarios `S-01` through `S-18` and flows `F-01` through `F-12` are defined in `03-flujos-y-ergonomia.md`. The landing copy and gates are defined in `06-landing-y-comercial.md`.

## Reconciliation

| # | Card ref. (Trello, Spanish) | Normalized need | Disposition | Evidence or baseline | Theme | Acceptance |
|---|---|---|---|---|---|---|
| 1 | `T7` · Descarga e instalación | Find and install a usable version and complete the first launch. | `build` | There is no Google Play listing nor a public APK page. The worklog records local signed APKs and `mx.abarpay.mobile`. Google Play is a later channel. | `T-01` | `S-17` · The landing page delivers a signed APK with version, source, SHA-256 and instructions, and allows a clean install on physical Android before G2. Google Play is left for later. |
| 2 | `T8` · Alta e identidad del negocio | Create the store with a name and logo that staff recognize. | `build` | `PUT /api/store/profile` and `/store/photo` exist with tests, but there is no separate logo nor complete multi-company isolation. | `T-02` | `S-01`, `S-15` · A new store shows its name and image, without another store's staff or brand. Android and console match. |
| 3 | `T9` · Cuenta bancaria | Register a valid receiving account, verify the state and block charges without activation. | `build` | There is no CLABE route nor activation. `apply_payment` preserves the CoDi confirmation, but creation depends on an account configured outside the product. | `T-02` | `S-01`, `S-16` · Save a valid account, show pending activation and reject charges if it is missing or inactive. Data masked and audited. |
| 4 | `T10` · Catálogo y precios | Create and consult the name, unit and price used in the sale. | `already covered` | `/api/catalog`, Android and console CRUD, tests `test_catalog_v3`. Price always from the database. | `T-04` | `S-07`, `S-14` · Create a product and see it in the console and in an authorized employee with the same price. Device NO verificado. |
| 5 | `T11` · Inventario inicial | Set initial stock for several products. | `already covered` | `/api/inventory/set`, `/api/inventory/adjust`, tests `test_inventory_v2` and inventory UI. | `T-04` | `S-07` · Set 10 units on three products and verify the same values on reload. Device NO verificado. |
| 6 | `T12` · Puntos de venta | Define users or devices that operate as the business's register. | `build` | The baseline uses employees and a single-store warehouse. There is no register, device or assigned-session entity. | `T-03` | `S-08`, `S-15` · Create two registers for a store, assign staff, separate operations and prevent one register from using another store. |
| 7 | `T13` · Invitación por QR o liga | Generate a business invitation that opens the correct employee's signup. | `already covered` | `/api/employees/invites`, `/invite/{token}`, App Links and Android QR/link tests. Duration and single use are covered. | `T-03` | `S-08` · Open the QR and link, scan on Android and verify the correct store. Expired and reused links fail. Device NO verificado en esta revisión. |
| 8 | `T14` · Registro del empleado | The employee accepts with their name and sees the business's identity before selling. | `build` | The screen and acceptance token exist, but the API identity used by the operations is still declarative. | `T-03` | `S-08`, `S-15` · Accept with a verified identity, see the correct business and remain without sell permission until activation. |
| 9 | `T15` · Autorización y acceso | Apply the owner's real permissions to the employee. | `build` | There are UI gates and tests for `canSell`, `canFiado` and `canInventory`, but `X-Employee-Id` and the shared PIN do not prove identity. | `T-03` | `S-08`, `S-15` · An unauthorized employee receives a server denial, not just a hidden button. Revocation and handover work on physical Android. |
| 10 | `T16` · Consulta de productos | Consult price and availability for an in-person customer. | `already covered` | Public catalog and bootstrap include stock, unit and price. The Cobrar UI shows `disponibles` or `Sin límite`. | `T-04` | `S-07` · An available and a sold-out product show the correct price and availability. NO verificado con usuario real. |
| 11 | `T17` · Carrito | Add products and quantities and confirm the total. | `already covered` | Cart UI, bottom sheet and `cartEstimate` use catalog prices. Tests for quantities and totals. | `T-05` | `S-02`, `S-14` · Two products with different quantities show lines and total. Rotation and TalkBack preserve state. |
| 12 | `T18` · Dictado para agregar | Interpret product and quantity, show them for confirmation and correct errors. | `already covered` | `/api/cart/parse`, local demo parser and phrase tests. Confirmation exists before adding. | `T-04` | `S-07`, `S-14` · Dictate three products, correct one match and charge only after confirming. Physical dictation NO verificado. |
| 13 | `T19` · Selección de medio | Present all applicable methods without executing a charge on selection. | `build` | The current UI shows cash, CoDi and credit. Link, push and terminal do not exist. | `T-05` | `S-16` · The six options are shown only if they are supported. Selecting does not create a payment. The unavailable ones explain the reason. |
| 14 | `T60` · Medio QR | Choose QR and open the flow without marking it paid. | `already covered` | The PEY/CoDi chip and `POST /api/sales` create a pending sale. Confirmation does not happen on selection. | `T-05` | `S-03` · Selecting CoDi opens QR generation and keeps the sale pending until the server. |
| 15 | `T61` · Medio liga | Generate and deliver a link without marking it paid. | `defer` | There is no link integration nor operational evidence from the provider. | `T-05` | `S-16` · If support does not exist, the option is not offered. If it is enabled, order, amount and confirmation are tested with the provider and authorized money. |
| 16 | `T62` · Medio push | Start a push request or report unavailability without charging. | `defer` | There is no push support in the client nor evidence from the provider. | `T-05` | `S-16` · The UI does not promise push. A future integration tests acceptance, rejection and states without changing the order to paid. |
| 17 | `T63` · Medio efectivo | Choose cash and open received-amount and change capture. | `already covered` | The Efectivo chip, `parseCashCents`, `POST /api/sales` and change tests. The per-shift register is handled in cards 28–30. | `T-05` | `S-02` · Selecting cash shows received amount and change, not QR nor bank confirmation. |
| 18 | `T64` · Medio tarjeta | Process card or vouchers through a terminal and wait for a valid result. | `defer` | There is no terminal integration. | `T-05` | `S-16` · The option remains unavailable until there is a terminal, contract and result test. |
| 19 | `T65` · Medio fiado | Direct to the customer and validate credit without counting the amount as collected. | `already covered` | The Fiado chip, required customer, `paymentMethod=fiado`, `credit` state and tests that exclude collection. | `T-09` | `S-04` · Selecting credit requires a customer and does not add to collections. New limits are covered in cards 51–57. |
| 20 | `T20` · Generación de QR | Show a QR with amount, reference and link to the sale. | `already covered` | `POST /api/sales` and the PEY client store `saleId`, `qrId`, amount and expiry. The UI shows the sale's QR. | `T-05` | `S-03` · The QR belongs to a single sale and shows amount and validity. A screenshot does not confirm payment. |
| 21 | `T21` · Confirmación bancaria | Distinguish pending from confirmed and apply only one valid event. | `already covered` | Webhook signature, reconciliation, tests `test_webhooks`, `test_pey_flow`, `test_concurrent_webhooks` and `apply_payment`. | `T-05` | `S-03`, `S-08` · Scanning does not change the state. A valid webhook or reconciliation pays once. A different amount remains to be reconciled. |
| 22 | `T22` · Avisos de pago | Notify customer, employee and owner with the correct order, amount and register. | `build` | Tickets and reports exist, but there is no per-actor notification model nor a notice outbox. | `T-10` | `S-03`, `S-08` · A confirmed payment creates one notice per recipient, deduplicated, without confusing pending with collected. |
| 23 | `T23` · Descuento de inventario | Deduct the sale once and update registers. | `already covered` | `decrement_inventory`, movements and tests for sale, concurrency and duplicate webhook. | `T-04` | `S-02`, `S-08` · Selling 2 of 10 leaves 8. Repeating the confirmation does not deduct again. Multi-register sync remains subject to `S-07`. |
| 24 | `T24` · Entrega del producto | Close the delivery of a paid sale and leave a final state. | `build` | The sale has payment states, but no delivery or fulfillment record. | `T-05` | `S-02`, `S-03` · A confirmed sale can be marked delivered once with actor and date. A pending sale is not delivered as paid. |
| 25 | `T25` · Cobro push | Charge by push request in an enabled environment. | `defer` | There is no provider support nor integration. | `T-05` | `S-16` · It is only enabled with a contract and a provider environment. Acceptance, rejection and payment are confirmed by the server. |
| 26 | `T26` · Cobro por liga | Issue a link with an amount and associate it with the sale's payment. | `defer` | There is no payment link. | `T-05` | `S-16` · If integrated, a link stays bound to an order and the payment is applied once after confirmation. |
| 27 | `T27` · Terminal con tarjetas | Record credit, debit or vouchers through a terminal and apply the correct result. | `defer` | There is no terminal nor acquirer contract. | `T-05` | `S-16` · The option is not offered until the terminal is integrated. The sale stays pending until a valid result. |
| 28 | `T28` · Cobro en efectivo | Receive cash, calculate change, confirm the sale and accumulate the register per responsible register. | `build` | The charge, change, paid state and movement exist. A register session and accumulation separate from other methods are missing. | `T-06` | `S-02`, `S-06` · Charging 80 while receiving 100 leaves change 20 and adds 80 only to the cash register. It does not create a webhook. |
| 29 | `T66` · Cierre de caja | Add cash by employee or register, capture counted and show the difference. | `build` | There is no closing entity. The report adds the day's cash, without an expected figure per shift. | `T-06` | `S-06` · Three sales add up to the expected figure, counted compares against expected and shows the difference. It does not mix credit or CoDi. |
| 30 | `T67` · Entrega al dueño | Record the cash handover and the owner's acceptance or discrepancy. | `build` | There is no handover nor acceptance. | `T-06` | `S-06` · Hand over 300 and accept. Repeat with 280 and leave a not-accepted state with difference and responsible parties. |
| 31 | `T29` · Inventario y agotados | Consult stock and identify zero or minimum. | `already covered` | `/api/inventory`, bootstrap, `lowStock` and inventory/reports UI. Tests `test_inventory_v2` and `test_report`. | `T-04` | `S-07` · Sell out an item and see `0`/`Inventario bajo`. Authorized roles consult the same data. NO verificado físicamente. |
| 32 | `T30` · Historial de movimientos | Consult intakes, sales and adjustments with reason and responsible party. | `build` | The server stores movements and reason, but the UI does not offer a complete per-product history. | `T-04` | `S-07`, `S-13` · A +5 adjustment shows quantity, reason, actor and date in the history. Only authorized roles adjust. |
| 33 | `T31` · Sincronización entre cajas | Show the same stock to authorized devices. | `build` | They share a central database when there is a network, but there is no cache, queue nor offline conflict between registers. | `T-04` | `S-07`, `S-12` · Update on one register and see it on another when syncing. Two offline sales of the last unit preserve both and generate a difference. |
| 34 | `T32` · Tablero y filtros | Consult confirmed charges with filters by date, employee or register and separate pending items. | `build` | `/api/reports/today` returns today, by employee and methods. There is no range, filters or register/POS selector. | `T-07` | `S-10` · Day and register filter paid totals. Pending items appear separately and do not inflate collected. |
| 35 | `T33` · Desglose por medio | See subtotals and reconciled references per method. | `build` | There are `cashCents`, `peyCents`, `fiadoCents`, but no detail reconciled per sale/reference in a reconciliation view. | `T-07` | `S-10` · CoDi, cash and credit have subtotals and detail. The sum matches paid sales and applied payments. |
| 36 | `T34` · Diferencias y fallos | Flag pending items, rejections or discrepant amounts without adding them as collected. | `build` | The `pending`, `por_conciliar` and `failed` states exist and there are tickets. Amount/reference comparison in a reconciled view is missing. | `T-10` | `S-03`, `S-08`, `S-10` · A failed payment or different amount does not increase collected. The difference has a reference and next action. |
| 37 | `T35` · Ventas por producto | Report units and amounts per period and highlights. | `build` | `topProducts` is limited to five and only today. There is no range report nor export. | `T-07` | `S-10` · A selected period matches sales units and amounts. Canceled products are excluded once. |
| 38 | `T36` · Ventas por empleado o caja | Attribute sales and amounts to each responsible party. | `build` | `byEmployee` exists for today, without register/POS nor range. The productive actor is not yet verified. | `T-07` | `S-10`, `S-15` · Two registers and two employees produce an exact breakdown. Changing store does not mix responsible parties. |
| 39 | `T37` · Inventario y exportación | Export intakes, outflows and stock with controlled access. | `build` | There is no inventory export. | `T-07` | `S-10`, `S-14` · Export and compare quantities with the screen. The file respects store, permissions and period. |
| 40 | `T38` · Faltantes para compra | Flag sold-out or low items as restock work. | `already covered` | `lowStock` feeds Inicio and inventory. The order-preparation action is evaluated in C-04 and cards 41–49. | `T-04` | `S-07` · A sold-out product appears among products to restock. The next action is covered with `S-05`/`S-10`. |
| 41 | `T39` · Registro de proveedor | Create and assign the right provider to a product without crossing stores. | `build` | There is no provider entity. | `T-08` | `S-05`, `S-15` · Create a provider, assign it to a product and verify that another store neither sees nor reuses it. |
| 42 | `T40` · Pedido y aprobación | Assemble quantities, units and conditions and approve before sending. | `build` | There is no purchase order. | `T-08` | `S-05` · Create an order of two items, review quantities/units and approve. Without approval it is not sent. |
| 43 | `T41` · Envío al proveedor | Send or share the order and store folio and state. | `build` | There is no sending nor tracking. | `T-08` | `S-05`, `S-16` · If the external channel is unavailable, the draft is kept and delivery is not claimed. With a channel, folio and recipient are recorded. |
| 44 | `T42` · Recepción y conteo | Capture physical quantities received against the order. | `build` | Only manual adjustment exists. There is no receiving against an order nor offline operation. | `T-08` | `S-05` · Receive 8 of 10, save the difference and recover after a forced close. It does not publish stock before approval. |
| 45 | `T43` · Entrada de inventario | Link received goods to order, date and responsible party. | `build` | Adjustment movements have an actor, but no link to order/receiving. | `T-08` | `S-05`, `S-08` · Record six units, see the folio and the actor. Retrying creates a single intake. |
| 46 | `T44` · Diferencias de recepción | Show missing or surplus items before closing. | `build` | There is no order-against-received comparison. | `T-08` | `S-05` · Receive 8 of 10 and show a difference of 2 with reason and next action. |
| 47 | `T45` · Aprobación de stock | Approve the intake and publish stock without duplicating. | `build` | There is no idempotent approval or publication of receiving. | `T-08` | `S-05`, `S-08` · Approving a receiving updates stock once. Repeating the event does not duplicate. |
| 48 | `T46` · Alerta de reabastecimiento | Notify when going from zero to positive stock, once per recipient. | `build` | `lowStock` detects zero, but there is no 0→positive event nor notices. | `T-08` | `S-05`, `S-08` · Restocking 0→5 generates one notice per recipient. Changing 5→6 does not generate a notice. |
| 49 | `T47` · Disponibilidad tras reposición | Offer the product again and consult the event and its notices. | `build` | There is no restock history nor notices. | `T-08` | `S-05`, `S-10` · A restocked product appears available with price and intake event. The notice stays in the history. |
| 50 | `T48` · Fiado y cliente | Register or consult the customer and create debt without marking it collected. | `already covered` | `/api/fiado/customers`, credit sale, UI and tests `test_fiado`. | `T-09` | `S-04` · Save the customer, create a credit sale and see the debt. It does not appear as collected. |
| 51 | `T49` · Límites de fiado | Configure debt, amount and due date and show eligibility. | `build` | There are no limits nor due dates. | `T-09` | `S-04` · Block with active debt and show the reason. An authorized exception stays audited. |
| 52 | `T50` · Confirmación de fiado | Preserve amount, term and accepted conditions before delivering. | `build` | There is amount and customer, but no term, conditions nor acceptance. | `T-09` | `S-04`, `S-14` · Record amount and due date, show conditions and preserve acceptance. Text readable with TalkBack. |
| 53 | `T51` · Liga por WhatsApp | Generate a link to the debt and send it with recipient, amount and reference. | `defer` | There is no link nor WhatsApp sending. It requires consent and a provider. | `T-09` | `S-16` · Without integration the UI does not promise sending. If it is enabled, the recipient consents and the link binds to a debt. |
| 54 | `T52` · Deuda y cartera | Consult balance, due date, folio, employee and states per customer. | `build` | There is customer, balance, phone and charge/payment history. Due date, explicit state and debt folio are missing. | `T-09` | `S-04`, `S-10` · Register a debt of 100, see folio, due date and portfolio. A partial payment keeps the debt open. |
| 55 | `T53` · Entrega fiada y stock | Deduct inventory once without adding to collections. | `already covered` | A credit sale creates `credit`, a movement and `fiado_entries`. Tests confirm it. | `T-09` | `S-04` · Delivering two units lowers stock by 2 and does not increase collected. A retry does not deduct again. |
| 56 | `T54` · Recordatorios | Send reminders by due date without duplicating or exceeding. | `build` | There is no due date, channel consent nor outbox. | `T-09` | `S-04`, `S-18` · It is only enabled with an authorized channel. One reminder per due date and verified deduplication. |
| 57 | `T55` · Bloqueo de nuevos fiados | Apply delinquency, balance and active credits to a new request. | `build` | There are no rules nor exception authorization. | `T-09` | `S-04` · A customer with overdue debt stays blocked or pending authorization. Decision and actor stay audited. |
| 58 | `T56` · Pago parcial o total | Distinguish payment from settlement and update the balance correctly. | `build` | Manual payments reduce the balance and a zero balance is not declared collected. A link and a formal settlement state are missing. | `T-09` | `S-04` · Paying 40 of 100 leaves 60, then 60 leaves zero. A repeated payment does not reduce twice. |
| 59 | `T57` · Conciliación de abonos | Apply each payment once and notify actors. | `build` | The current payment does not use an idempotency key nor emits notices. | `T-09` | `S-04`, `S-08` · Repeating the same event leaves a single movement and balance. Notices correspond to the payment. |
| — | `T58` · Conciliación de abonos | Literal duplicate of card 59. | `duplicate` | Same need and acceptance text as `T57`. | `T-09` | It closes with the acceptance of 59. The deliverable scope is recorded once. |
| 60 | `T59` · Liquidación y elegibilidad | Close the debt with a zero balance and apply rules to a new credit. | `build` | The arithmetic reaches zero, but there is no closed state nor eligibility reopening. | `T-09` | `S-04` · Settling leaves a closed state. A partial balance stays open. The next request applies current rules. |
| 61 | `T68` · Identidad visual de consola | Align logo and colors with the mobile app. | `already covered` | `server/static/console.html` contains the purple palette and the worklog records the console v5 deployment. | `T-07` | `S-14` · The console loads logo and palette, keeps navigation and passes contrast. Later visual revalidation NO realizada. |
| 62 | `T69` · Identidad inicial incorrecta | A new store must not start with foreign staff. | `already covered` | `test_new_database_seeds_only_the_owner` protects the new signup. The inherited demo may keep staff if labeled as demo. | `T-02` | `S-01`, `S-15` · Create a clean store and see no employees, customers or another store's name. |
| 63 | `T70` · Empleados heredados en primer alta | Avoid preloaded staff in a new account. | `already covered` | Same evidence as 62. `test_new_database_seeds_only_the_owner`. | `T-02` | `S-01` · The first Android and console opening match and contain no seed staff. |
| 64 | `T71` · Administración de empleados | Add, remove and manage permissions from the console. | `build` | The API and Android manage the team, but there is no Team view in console v5. The shared PIN is pending replacement. | `T-03` | `S-08`, `S-15` · The owner invites, revokes and changes permissions from the console. An employee cannot change roles. |
| 65 | `T72` · Inicio por empleado y medio | See the breakdown by register, employee and method with reconciled subtotals. | `build` | Inicio shows totals and latest sales. Reports deliver by employee and method, without register or period filters. Static audit, NO verificado. | `T-07` | `S-10` · Two registers and methods produce subtotals that add up to confirmed sales and exclude pending items. |
| 66 | `T73` · Consola de cierre de efectivo | Consolidate cash, count, hand over and accept from the console. | `duplicate` | It repeats the result of 29 and 30 with console scope. There is no implementation. | `T-06` | It closes with 29–30 · The same transaction is managed from the console with an authorized role and `S-06` evidence. |
| 67 | `T74` · Definición de indicadores | Explain period and criterion for sales, collected, credit and pending items. | `build` | Separate fields exist, but the UI does not document all criteria nor filters. | `T-07` | `S-10` · Each indicator shows period, source and treatment of payments, pending items and canceled. |
| 68 | `T75` · Acción desde stock bajo | Take a low-stock product to restock preparation with product and quantity preloaded. | `build` | Inicio only links to inventory. There is no order. Static audit, NO verificado. | `T-08` | `S-05` · Selecting an alert opens order preparation with the product and suggested quantity. |
| 69 | `T76` · Motivo de ajustes | Require reason, actor and previous/new value when adjusting. | `build` | `/api/inventory/adjust` accepts reason and actor, but the console UI uses quick adjustments without a complete reason flow. | `T-04` | `S-13` · Adjusting +5 requires a reason and shows actor, previous, new and history. |
| 70 | `T77` · Historial por producto | See chronological movements with type, quantity and link. | `build` | There are aggregated latest movements, not complete per-product detail. | `T-04` | `S-07`, `S-10` · A product with a sale, intake and adjustment shows a complete, exportable history. |
| 71 | `T78` · Existencias negativas | Apply an explicit rule for negatives in demo and normal environments. | `build` | An existing test allows negatives. An approved policy, warning and per-register consistency are missing. | `T-04` | `S-13`, `S-15` · Demo and production apply different visible rules. Neither writes negative stock by permission rebase. |
| 72 | `T79` · Proveedor en catálogo | Assign and consult the provider from the catalog without crossing businesses. | `duplicate` | Same provider-product relationship need as 41. The current console does not show it. | `T-08` | It closes with 41 · Edit the product, assign the provider and test `S-15` isolation. |
| 73 | `T80` · Recepción y aprobación en consola | Receive a different quantity than ordered, record the difference and publish once. | `duplicate` | It repeats the result of 44–47 with a web surface. | `T-08` | It closes with 44–47 · Console receiving preserves differences and uses `S-05`, `S-08`. |
| 74 | `T81` · Detalle de fiado | See folio, balance, due date, state and payment history. | `build` | The console has detail and entries, but folio, due date and debt state are missing. Static audit, NO verificado. | `T-09` | `S-04` · Open the debt and see due date, state and payments. A partial payment does not close. |
| 75 | `T82` · Contacto para avisos | Validate channel and consent and handle legacy records without contact. | `build` | The customer accepts an optional phone. There is no validation, consent nor notice. | `T-09` | `S-04`, `S-18` · Create a customer with a valid channel and consent. A legacy record without contact is shown and allows correction. |
| 76 | `T83` · Límites y bloqueo en consola | Configure amount, delinquency and new-credit restrictions. | `duplicate` | The functional rule belongs to 51 and 57. The console UI is the channel, not a distinct need. | `T-09` | It closes with 51 and 57 · Rules, exception and blocking are tested in `S-04`. |
| 77 | `T84` · Detalle, ligas y cobros | Open debt, create a link and reconcile payments without duplicating. | `duplicate` | The detail/payment part relates to 54 and 58. The link stays deferred in 53. | `T-09` | It closes with 54 and 58 for detail/payment. The link stays blocked until 53. |
| 78 | `T85` · Filtros de gastos | Filter expenses by period, category and responsible party. | `build` | Expenses exist with a list and the day's total. There are no categories nor filters. Static audit, NO verificado. | `T-07` | `S-10` · Expenses of different dates, categories and responsible parties filter with correct subtotals. |
| 79 | `T86` · Identidad del registrante | Distinguish the historical author from the current session and demonstrate isolation. | `build` | The employee name is stored in expenses, but the API identity is declarative and the PIN is shared. | `T-02` | `S-08`, `S-15` · A new account does not show foreign records. The expense author matches the verified session. |
| 80 | `T87` · Plantillas de tareas | Locate template application, generate tasks and assign them. | `build` | The template is applied in onboarding/API and Android shows tasks. The console does not allow applying or editing from its view. | `T-03` | `S-01` · A new business applies the template, receives assignable tasks and preserves activation. It does not duplicate on retry. |
| 81 | `T88` · Conciliación CoDi en soporte | Inspect and reconcile an event with the correct reference, order and amount. | `build` | Support lists tickets and PEY events, but does not offer a per-event reconciliation action. Static audit, NO verificado. | `T-10` | `S-03`, `S-08` · Open pending, expired and paid. Reconcile once without double charge and with a separate demo amount. |
| 82 | `T89` · Módulo de reportes | Navigate reports by period, product, employee/register and inventory with export and permissions. | `build` | The console has no Reports tab. `/api/reports/today` covers only today. | `T-07` | `S-10`, `S-14` · Each report matches the source, respects permissions and navigates to detail with keyboard. |
| 83 | `T90` · Ajustes de identidad y banco | Edit name, logo and receiving account with validation and audit. | `duplicate` | The business need is split between 2 and 3. The current console does not edit logo nor CLABE. | `T-02` | It closes with 2 and 3 · Edit name/logo and account with authentication, validation and audit. |
| 84 | `T91` · Acceso a roles desde Ajustes | Open team management only for the owner. | `duplicate` | The functional management is 64. Ajustes only needs an authorized link. | `T-03` | It closes with 64 · The link appears for the owner and the employee stays blocked on the server. |

## Coverage verification

- Cards included: **85 of 85**.
- Unique short references: **85**.
- Initial Trello guide cards excluded: **6**.
- Explicit duplicate: one unnumbered card that repeats need 59. The 84 numbered cards are present, from 1 to 84.
- Internal board IDs, members, attachments or personal data from the screenshots were not included.

Reproducible check of the document:

```bash
python3 - <<'PY'
from pathlib import Path
import re

path = Path("docs/produccion/trello-cobertura.md")
rows = []
for line in path.read_text(encoding="utf-8").splitlines():
    match = re.match(r"\|\s*(\d+|—)\s*\|\s*`([A-Za-z0-9]+)`", line)
    if match:
        rows.append(match.group(2))

assert len(rows) == 85, len(rows)
assert len(set(rows)) == 85, "hay referencias repetidas"
numbered = {int(line.split("|")[1].strip()) for line in path.read_text(encoding="utf-8").splitlines()
            if re.match(r"\|\s*\d+\s*\|\s*`[A-Za-z0-9]+`", line)}
assert numbered == set(range(1, 85)), sorted(set(range(1, 85)) - numbered)
print("85 tarjetas únicas, 84 numeradas, 6 starter excluidas")
PY
```

The reference verification against the original export was done during writing. The document does not depend on `/Users/carlos/Downloads` to be read or run.
