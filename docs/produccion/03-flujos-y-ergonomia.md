# 03 · Flows, ergonomics and physical acceptance

## Use by DSH

This document is the standing instruction for designing, implementing and verifying Abarpay workflows. DSH stands for DeepSeek Harness. The specification is based on `main` at `75c1f35` and on the state documented on 21-nov-2026. It does not assume that a Trello column proves a feature.

Mandatory order for each flow card:

1. The operations designer, applying industrial-engineering judgment, first describes the complete physical operation.
2. A paired developer reviews the sequence, the states, the contracts and the opportunities to reduce steps. The developer and the industrial designer compare the alternatives against the same scenario.
3. The implementer writes the code within the routes allowed by the assigned package.
4. An independent verifier derives the expected result from the contract, checks the exact revision and runs the automated, physical-Android and accessibility checks.
5. The coordinator accepts the package only with reproducible evidence. An implementer self-review does not close the package.

DSH must stop and record a pending decision when a provider contract, an external authorization, a credential or a person for the physical test is missing. It may continue with `SIMULADO` fixtures when the test involves neither money nor real data.

## Verifiable baseline

| Surface | State observed in the code | Consequence for the design |
|---|---|---|
| Android | Tabs Inicio, Cobrar, Fiado, Inventario and Reportes, with per-employee permissions. Cash, PEY/CoDi and credit exist, along with link or QR invitations, catalog, tasks, expenses and a shareable receipt. | The current flow serves as the visual baseline. Offline cash register, goods receiving and register closing still require implementation. |
| Web | `/console` is the owner's console. `/invite/{token}` accepts invitations. `/` redirects to `/console`. | A public landing page, QR entry from desktop and separate SaaS management do not exist yet. |
| API | Sales, inventory, catalog, team, reports, credit and support routes under `/api`. CoDi charges are confirmed by signed webhook or server reconciliation. | The phone cannot declare a CoDi sale paid. The UI must reflect server states. |
| Evidence | There are server and Android tests for cash sales, credit, invitations, inventory, catalog, CoDi and idempotency. The worklog records 183 server tests, 154 Android unit tests and 16 legacy tests at `75c1f35`. | This document review did not rerun those suites. A new implementation needs its own evidence. |

The active database must not serve as a fixture or as a destination for synthetic data. Every test uses an isolated database and data identifiable as `SIMULADO`.

## Functional boundary by connectivity

| Operation | Offline | Online |
|---|---|---|
| Browse catalog and cart | Last synced catalog, price and projected stock, with a visible sync time. | Update price, availability and current reservations. |
| Take cash payment | Finalize once, generate a local receipt with a stable reference, record the cash movement and deduct the projected stock. | Publish the sale, reconcile inventory and make it visible on other registers. |
| Issue receipt | Local image or PDF of the amount, lines, payment method, reference and pending-sync mark. | Confirm the central reference and allow a new download or resend. |
| Receive goods | Record physical quantities, differences, responsible party and local receipt against a cached order. | Approve the intake, resolve duplicates or conflicts and publish stock. |
| Prepare credit | Create a charge or payment draft with the cached balance. | Validate balance, limit, eligibility and authorization before finalizing. |
| Charge CoDi, invite, change bank or approve web access | Keep the context and explain what is missing. | Authenticate, generate the QR, confirm the payment or complete the change. |
| Close the register | Count cash, save the count and the handover draft. | Finalize when the required operations are synced and the owner accepts the handover. |

Cash is charged offline. Credit is finalized online. CoDi, identity, bank and web approval require the server. Credit drafts can be prepared without a network and never increase debt or reduce collections until the server confirms them.

## Actors and environment

| Actor | Operational objective | Main constraints |
|---|---|---|
| Owner | Charge, control debt, restock, reconcile and manage the team. | Can operate from phone or web console. Money and data actions require verified identity and active membership. |
| Cash register employee | Complete an in-person sale quickly and recover the work after an interruption. | Sees only the store and the authorized functions. Does not manage bank, permissions or owner reports. |
| Customer | Pay and receive an understandable receipt. | May not have the app. Their payment data is shown only as necessary. |
| Accountant | Review Formalización when the owner contracts it. | Their fees and access are agreed separately. |
| Abarpay internal staff | Operate subscriptions, support and data pilots. | Minimal, audited access separated from the merchant. Analysts see aggregates by default. |

The real point of sale usually has variable lighting, one hand occupied, customers waiting, calls, screen lock and irregular connectivity. The shortest sequence must remain safe, recoverable and understandable without extensive technical training.

## Shared scenarios

The coverage cards cite these identifiers. Each scenario can be run against a clean database or a `SIMULADO` fixture.

| ID | Given | When | Then |
|---|---|---|---|
| `S-01` | A new store with no demo data. | The owner completes signup and creates their first product. | No foreign employees, customers or catalog appear. The first cash sale can be completed and the state survives a restart. |
| `S-02` | The phone is in airplane mode and has a synced catalog. | The cashier charges in cash and the customer pays with change. | The sale is finalized once, the local receipt shows amount, change and reference. Projected stock decreases. The state becomes pending sync. |
| `S-03` | There is a pending CoDi sale. | The customer scans the QR but the server has not confirmed yet. | The UI stays pending and does not add collected money. A screenshot or the QR does not change the state. |
| `S-04` | A customer has a balance. | The employee records a credit sale. | The server validates customer, limit and permission. Debt increases once, stock decreases once and collections do not increase. |
| `S-05` | An order is cached and there is no network. | The employee receives a different physical quantity. | Received quantity, difference, actor and local receipt are saved. Central stock is not published before approval. |
| `S-06` | There are cash sales for the shift. | The cashier counts, declares and hands over the cash. | The owner sees expected, counted, difference and responsible parties. The register is only accepted after the owner's review. |
| `S-07` | Two registers sync. | Both sell the last unit while disconnected. | Both cash sales are preserved, each is published once and an auditable inventory difference is opened. A receipt is not deleted. |
| `S-08` | An operation was already applied on the server. | The response is lost before the phone acknowledgment. | The retry returns the same result and does not duplicate a sale, receipt, payment, debt or movement. |
| `S-09` | The owner opens the console on desktop. | Scans the QR with their phone and confirms the store. | The session stays bound to the initiating browser. An expired, reused or other-account code fails with a clear action. |
| `S-10` | There are sales, credit and expenses. | The owner opens reports and exports. | Each total declares period, source and treatment of canceled, pending and payments. The export matches the screen and preserves history. |
| `S-11` | The cashier is capturing a charge. | A call arrives, the screen locks or the system kills the app. | On return, amount, method, customer and state appear. The operation resumes at the next safe step without double submission. |
| `S-12` | There is pending local work. | The network recovers after a forced close. | The queue resumes and shows pending, synced or requires attention. A network failure does not discard the work. |
| `S-13` | A product has zero or negative stock. | A sale or adjustment is attempted. | Show availability and audit adjustments. If two disconnected registers sold the last unit, honor both sales, keep the deficit and open variance to the owner. |
| `S-14` | A person uses TalkBack, an external keyboard, 200% text or high contrast. | Walks a complete flow. | All controls have useful name, state, order and focus. Nothing depends on color alone. There is no clipped text and no targets smaller than 48 dp on Android. |
| `S-15` | There are two test tenants, each with one store. | One tries to read or modify the other's data by URL, cache, invitation, export or job. | The server and the jobs respect membership. The cache is separated and no crossed information appears. |
| `S-16` | The provider does not offer a feature or responds with an error. | Push, link, terminal or unconfigured CoDi is chosen. | The UI marks it as unavailable or pending. It does not create a false charge or show a successful result. |
| `S-17` | A landing page visitor uses mobile or desktop. | Taps `Empezar gratis`, `Entrar a mi tienda` or the pilot APK. | Arrives at a real, accessible destination, or sees an honest explanation of the state and the next action. |
| `S-18` | A free store participates or not in the aggregated pilot. | Changes its mind and requests history. | Participation is off by default. History and export remain available. Revocation has instructions and a verifiable effect. |

## Mandatory flow card

Before writing UI, the operations designer opens a card with this content:

| Field | Minimum content |
|---|---|
| Actor and role | Person, store, device, role and whether they use one or two hands. |
| Trigger | What starts the flow and what information is already available. |
| Environment | Counter, stockroom, personal phone, light, network, noise and wait time. |
| Minimum safe sequence | Indispensable steps, irreversible decision and confirmation point. |
| Information at the moment | Price, stock, balance, amount, change, state or warning needed to decide. |
| Observable result | What the actor sees and what remains recorded when it ends. |
| Costly errors | Duplicate payment, lost sale, false stock, crossed debt, incorrect receipt or improper access. |
| Interruption | Likely event, persisted state and next safe action. |
| Effort metric | Taps, time to confirmation, corrections and failed recoveries. |

The paired developer reviews the card and answers four questions in writing. What step can be removed? What data must come from the server? What happens if the actor gets distracted? How is it demonstrated that the alternative is safer and not just shorter? The coordinator records the accepted decision and its rationale.

## Interaction rules

1. Every tap receives immediate local confirmation. A target of 100 ms is the practical goal. If an operation takes longer than 300 ms, the UI shows concrete progress.
2. Durable state rules for money, inventory, debt, email and sync. A spinner does not turn an operation into a success.
3. Fields are preserved on network or validation errors. Submit buttons are disabled while the request is in flight and re-enabled with a safe retry action.
4. Every destructive action asks for confirmation only when it can lose money, stock or data. Canceling a pending QR and deleting a completed sale have different consequences.
5. State is announced to assistive technology. Messages use observable verbs, for example `Venta registrada`, `Pago pendiente de confirmación`, `Guardado en el teléfono`, `Requiere atención`.
6. Color accompanies text and icon. Amount, method and state are never identified by green, red or yellow alone.
7. The screen preserves cart, customer, amount received and method when rotating, locking or returning from voice recognition.
8. The owner can see who recorded each authorized movement. The displayed name must come from a verified session or membership, not from a header chosen by the client.
9. Unavailable features are shown as such. A payment, a printer, a terminal or a shipment that the system cannot complete is not simulated.
10. Every screen supports 200% text, keyboard or TalkBack without hiding the main action or the operation state.

## Flows

### F-01 · Signup, first product and first sale

Industrial engineering first. The owner arrives with a store open or in preparation, may be using mobile data and needs a useful result before finishing all setup. Progress is saved at each step. Bank, invitations and data participation are offered as separate tasks.

Paired developer. Reduces the initial path to verified identity, store name, first item and a test cash sale. Later tasks show what they unlock. It does not use example staff, an inherited name or another store's catalog.

Actions:

1. Verify the owner's identity and create or choose the store.
2. Capture name, business type and first item with price and unit.
3. Enter the home screen with the empty store or with the created item.
4. Start a cash sale, capture the amount received and confirm the change.
5. Show the receipt and the next useful task, such as inviting staff or receiving CoDi.

Interruptions. If the app closes, reopen at the pending step. If the store was already created, do not duplicate it. If the first sale became uncertain, check its reference before repeating it.

Acceptance. `S-01`, `S-11`, `S-14` and `S-15`. Automated test with a clean database. Physical Android test from a signed install, with a restart after signup and the sale of one item. WCAG 2.2 AA equivalent audit of the walkthrough.

### F-02 · Cash sale and offline receipt

Industrial engineering first. The cashier browses products, builds the cart, receives bills and calculates change. The network can drop before or after tapping `Cobrar en efectivo`. The customer needs a receipt before leaving.

Paired developer. The sale, the receipt, the cash movement and the inventory movements form one atomic local operation. Each line and the sale carry immutable IDs. Sync sends an individual operation and accepts an idempotent acknowledgment.

Actions:

1. Search or scan a product and set the quantity.
2. Review lines, total and projected stock.
3. Choose Efectivo, capture the amount received and show the change.
4. Confirm once.
5. Show local reference, sync state and receipt options.
6. Sync when the connection recovers or on explicit request.

Interruptions. Call or lock during the cart, double tap, forced close, restart, network drop, lost response after commit and last-unit conflict.

Acceptance. `S-02`, `S-07`, `S-08`, `S-11`, `S-12` and `S-14`. In airplane mode, charge, issue a receipt, force-stop, restart the phone and reconnect. Verify one central sale, one receipt, one movement per line and one cash intake. Repeat the delivery and check a single application. TalkBack must read total, change, state and reference.

### F-03 · CoDi charge with verified confirmation

Industrial engineering first. The customer chooses CoDi, sees the amount and scans. There can be delay, expiry, network change and late payment. The cashier needs to distinguish `Pendiente`, `Por conciliar`, `Pagada` and `Vencida` without inferring success from a screenshot.

Paired developer. Each attempt preserves store, sale, receiving account, QR and transaction. Creation requires an active store account. The server applies payment, inventory and receipt idempotently through the official payment path.

Actions:

1. Choose CoDi and review the commercial amount and demo mode.
2. Generate the QR only with an active account and show validity.
3. Check the state with an understandable indicator and without adding to collections.
4. Update to paid only with a confirmed server response.
5. Offer a receipt and the next sale. In an uncertain case, keep the reference and allow lookup or support.

Interruptions. App close while the QR is active, expiry, creation timeout, payment after canceling, duplicate webhook, network change and inactive bank account.

Acceptance. `S-03`, `S-08`, `S-11`, `S-15` and `S-16`. Automated test with a fake provider marked `SIMULADO`. On physical Android verify QR, pending, rotation, locked screen and recovery. The real-money test is reserved for an authorized person and a payment of MXN 0.01. WCAG AA for state, amount, validity and actions.

### F-04 · Online credit

Industrial engineering first. The known customer asks to take products and pay later. The employee needs to know the balance, the limit, the due date and whether they can authorize. A credit sale is not collected money. A partial payment does not close the debt.

Paired developer. The charge and the payment are validated online. The server derives the session, the membership and the actor. The phone can prepare an offline draft but cannot finalize debt, limit change or exception. The operation is idempotent and the history preserves charge, payment, actor and date.

Actions:

1. Search for or create the customer with the minimum data and contact consent when applicable.
2. Review balance, overdue debt, limit and current eligibility.
3. Record amount, due date and conditions in an understandable way.
4. Confirm the charge and deduct stock once without adding to collections.
5. In a collection, capture a partial payment or settlement and show the new balance.

Interruptions. Network loss on confirm, double payment, concurrent settlement, customer without contact, limit change and register handover mid-flow.

Acceptance. `S-04`, `S-08`, `S-11`, `S-14` and `S-15`. On physical Android, prepare a draft without a network and verify that it does not affect the balance. Retry a payment with the same operation and verify a single movement. Accessible reading of balance, due date and state.

### F-05 · Physical goods receiving without a network

Industrial engineering first. The person receives boxes in the stockroom, counts what arrived and notes differences against the order. The network may be absent and the screen is used with busy hands. The result must not inflate available stock before review.

Paired developer. The order is cached with products and expected quantities. Receiving creates a local operation with observed quantities, differences, actor and receipt. Central approval and publication require connection and permission.

Actions:

1. Open the received order or find it in cache.
2. Confirm provider, folio and physical date.
3. Capture the received quantity per product.
4. Show missing or surplus items and ask for a reason when they exist.
5. Save the local receipt and the `Pendiente de aprobar` state.
6. Sync, review and approve the intake once.

Interruptions. Forced close, low battery, intermittent network, double receiving, unexpected product, change of responsible party and simultaneous approval from the console.

Acceptance. `S-05`, `S-07`, `S-08`, `S-12` and `S-14`. On physical Android without a network, receive 8 of 10, save, force-stop, restart and sync. Verify one intake, a visible difference and the local receipt. Central approval publishes stock once. WCAG AA for capture, difference, state and actions.

### F-06 · Closing, handover and acceptance of cash

Industrial engineering first. At the end of the shift, the cashier counts the physical cash, declares the handover and the owner confirms receipt or records a difference. The expected figure excludes QR, credit and terminals. The register is not reconciled just because the employee finished capturing.

Paired developer. The closing preserves opening, synced cash sales, applicable collected payments, expenses, expected, counted, difference, handover and acceptance. Pending operations prevent a final close or are shown in an explicit list.

Actions:

1. Prepare the cut with period and register visible.
2. Show expected cash and pending operations.
3. Capture counted and a reason when there is a difference.
4. Record the handover with date, actor and receipt.
5. The owner reviews and accepts or marks a discrepancy.
6. Close the shift with final state and next action.

Interruptions. Unsynced sales, screen reload, partial handover, absent owner, double tap and correction after acceptance.

Acceptance. `S-06`, `S-08`, `S-12` and `S-14`. Three cash sales of MXN 80 each, expected MXN 240. Hand over 240 and accept. Repeat with 220 and verify the difference and the not-accepted state. Physical test on Android and web console, with reading of totals and correct focus.

### F-07 · Restock alert and order to provider

Industrial engineering first. The owner reviews low-stock alerts, decides what to buy and builds an order. The employee can receive it later. The flow separates suggestion, approval and physical intake.

Paired developer. The alert links product, stock, minimum and authorized provider. The order has folio, quantities, unit, state and approval. Sending or receiving only changes stock through the approved flow.

Actions:

1. Open the alert from Inicio or Inventario.
2. Review product, stock, minimum and provider.
3. Add the proposed quantity and other items.
4. Review total, unit and conditions.
5. Approve and share or send the order through the available channel.
6. Receive goods through F-05.

Interruptions. No assigned provider, uncertain external send, duplicate order, different quantities and simultaneous approval.

Acceptance. `S-05`, `S-08`, `S-10` and `S-16`. Select a sold-out product from Inicio and verify that it reaches the order with the product and quantity preloaded. If the external send is unavailable, show a draft and next action without claiming delivery.

### F-08 · Catalog, inventory and codes

Industrial engineering first. The owner maintains name, unit, price, category, stock or service. The employee consults and operates within their permissions. Search and scanning happen with customers waiting.

Paired developer. The price always comes from the database. The server validates unit, type, stock and limits. A price change does not rewrite past sales. Movements store reason, actor, date and link.

Actions:

1. Search, filter or scan.
2. Consult price and availability with explicit text.
3. Create or edit an item according to permission.
4. Adjust stock with a reason and see the trace.
5. Confirm that the charge interface reflects current data or the last sync time.

Interruptions. Unknown code, broken image, product without stock, outdated price, deletion with sales and two concurrent edits.

Acceptance. `S-01`, `S-07`, `S-11`, `S-13` and `S-14`. S-13 in demo and in a normal environment. Physical Android with search, scanning, 200% text and TalkBack. The console must allow the same authorized result with keyboard and visible focus.

### F-09 · Invitation, access and staff handover

Industrial engineering first. The owner invites a person, who accepts with their own name and receives only the tasks of the correct store. A shift change cannot mix carts, pending charges or another person's data.

Paired developer. The invitation expires and is consumed once. The session and membership determine the store and permissions. Logout does not discard authorized local work. Revocation blocks new finalizations and leaves recovery of pending operations to an authorized person.

Actions:

1. The owner generates a link or QR with store, role and expiry.
2. The employee sees the store's identity and accepts with their name.
3. The server creates or activates the membership once.
4. The app shows only allowed tabs and actions.
5. The owner revokes or changes permissions from a team surface.

Interruptions. Expired link, reused link, install without profile, phone change, revocation with pending work and a second employee on the same device.

Acceptance. `S-08`, `S-11`, `S-14` and `S-15`. On physical Android, accept an invitation by QR and by link. Before accepting, selling is not possible. Afterward, the employee does not manage bank or permissions. The revocation screen must explain how to reconcile pending work.

### F-10 · Reports, reconciliation and export

Industrial engineering first. The owner reviews the day and detects differences. They need to know what each figure means before deciding. The business date is Mexico City.

Paired developer. Each indicator declares period, source, deduplication and treatment of canceled, pending and payments. The export uses the same data and the same filters as the screen. Roles without permission do not access the detail.

Actions:

1. Choose period and store.
2. Review sold, collected, credit, pending and expenses with visible definitions.
3. Filter by employee, register or payment method.
4. Open a sale or event that explains a difference.
5. Export and compare totals before sharing.

Interruptions. Data pending sync, late cancellation, unconfirmed CoDi payment, interrupted export and time-zone change.

Acceptance. `S-10`, `S-12`, `S-14` and `S-15`. `SIMULADO` fixture with paid sales, credit and pending items. Screen and file figures must match. On web, operate with keyboard and screen reader. On Android, totals and states are read in full.

### F-11 · Owner sign-in to the console by QR

Industrial engineering first. The owner is at a computer and their phone already has a session. They want to open their store without typing a shared password. They must be able to deny a foreign attempt and recover from an expired code.

Paired developer. The console creates a unique challenge bound to the browser. The phone shows the store and the requesting browser. Approval uses device authentication. The exchange creates an HttpOnly, Secure and SameSite session. Reuse, wrong account or revoked membership fails.

Actions:

1. Open `Entrar a mi tienda`.
2. Show the QR and short code, with expiry.
3. Scan from the owner's app and review store and browser.
4. Approve or deny explicitly.
5. The computer obtains the session and enters the correct console.

Interruptions. Camera without permission, rotation, network down, expired challenge, closed browser, approval from another account and revoked session.

Acceptance. `S-09`, `S-11`, `S-14` and `S-15`. Camera-free alternative through a manual code. Physical Android to approve or deny. Web with keyboard and reader. Verify reuse, a different browser and expiry.

### F-12 · Landing, signup and continuity through the first sale

Industrial engineering first. An owner arrives from a campaign or recommendation, compares the promise with what they can do and chooses to start. The transition must preserve campaign, page version and consent without capturing bank or customer data in analytics.

Paired developer. `Empezar gratis`, `Entrar a mi tienda` and the pilot APK lead to real destinations. If a route is not enabled, the page explains it and offers an available action. Measurement distinguishes visit, verified signup, store created, first sale, Control paid, refund and retention.

Actions:

1. Read a checkable promise and see the real product.
2. Choose mobile signup, QR entry or signed pilot APK according to their case.
3. Complete identity and store without foreign example data.
4. Complete the first cash sale or the first useful task.
5. Record the attribution result without sensitive data.

Interruptions. Abandoned signup, install without permission, APK not yet published, campaign without costs and return from an expired QR.

Acceptance. `S-17`, `S-11`, `S-14` and `S-18`. Each CTA has a destination test. The landing page uses WCAG 2.2 AA, keyboard and mobile. Conversion is measured only with consented events. The complete commercial copy lives in `06-landing-y-comercial.md`.

## Accessibility requirements

The goal is WCAG 2.2 level AA on web and equivalent behavior on Android. The applicable standard is [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

| Area | Acceptance criterion |
|---|---|
| Contrast | Normal text with a minimum ratio of 4.5:1 and large text with 3:1. States, borders and focus also comply. A screenshot at high brightness confirms legibility. |
| Text | Content and actions work at 200% without clipping or loss of information. Amounts do not overlap buttons. |
| TalkBack | Each control has a useful name and state. The order reads actor, product, quantity, total, method and confirmation state. New messages are announced. |
| Keyboard and focus | The web completes its flows with keyboard, visible focus and logical order. Dialogs trap and return focus correctly. |
| Touch targets | On Android, frequently used controls of at least 48 by 48 dp. On web, at least 24 by 24 CSS px and sufficient spacing. |
| Color and shape | State, difference or required fields carry text or icon in addition to color. No decision depends on tone alone. |
| Errors | The message is associated with the field, explains how to correct and preserves what was captured. Focus reaches the first relevant error. |
| Motion | Reduced motion is respected. Animations do not block the operation nor are they the only signal of result. |
| Time | An expiry reports what happened and offers to regenerate or retry. A cart is not lost because a QR expired. |

## Physical Android acceptance protocol

1. Install a signed APK and record version, code, SHA-256 and source revision.
2. Use a test store and synthetic data. Confirm that it does not connect to the active database.
3. Run `S-02` in airplane mode. Save the receipt, force-stop, restart the phone and reconnect.
4. Run `S-05` without a network with a cached order, a quantity difference and a forced close.
5. Interrupt a sale with a call, screen lock, rotation and return from the voice picker.
6. Repeat the delivery of an operation even if the server had already applied it. Confirm a single write.
7. Test the last unit from two isolated registers and verify the auditable difference.
8. Test `S-04` without a network and verify that only a draft is kept. Finalize it on reconnect.
9. Review the whole screen with TalkBack, 200% text, external keyboard when present, and low and high brightness.
10. Attach screenshots, a short video or accessibility log, the Android system version and any observed failure.

An emulator or Robolectric test can discover regressions. Only the physical test accepts a flow that depends on network, camera, keyboard, battery or system behavior.

## State copy

| Situation | Allowed text | Forbidden text |
|---|---|---|
| Offline cash | `Cobro en efectivo guardado en el teléfono. Se sincronizará al volver la conexión.` | `Sincronizado` or `Cobrado en la nube` before the acknowledgment. |
| Pending CoDi | `Pago pendiente de confirmación. Revisa el estado antes de entregar.` | `Pagado` because of showing the QR or a screenshot. |
| Confirmed CoDi | `Pago confirmado por el servidor.` | `Pago confirmado por el banco` when that source was not verified. |
| Credit | `Fiado registrado. Saldo pendiente: MXN …` | `Cobrado` or `Ingreso recibido`. |
| Pending receiving | `Mercancía recibida en este teléfono. Falta aprobación para publicar existencia.` | `Inventario actualizado` before central approval. |
| Queue with a problem | `Requiere atención. Conservamos los datos y te mostramos cómo resolverlo.` | `Error` without a next action. |

## Closing condition for DSH

A flow package is considered accepted when it has an operation card reviewed by industrial engineering and the paired developer, a data contract, implemented actions, recovered interruption states, relevant automated tests, a physical Android test, a WCAG AA audit and evidence of the exact revision. External pending items remain in the human queue with an owner and an unblocking condition.
