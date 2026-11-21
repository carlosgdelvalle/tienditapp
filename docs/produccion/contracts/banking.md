# Banking and CoDi payment contract

- **Contract:** CoDi/PEY payment flow, reconciliation, and payment application
- **Version:** 1.0
- **Owner:** D2 Contracts — Pro domain owner
- **Consumers:** M1 (Onboarding and CLABE), M2 (Checkout and till close), G2 (Public pilot)
- **Fixture:** two test tenants — "Tienda Aurora" (tenant A) and "Tienda Beta" (tenant B) — one store each, one active bank account/CLABE per tenant
- **Acceptance:** B3 · Banking and money

## Invariants

1. **`apply_payment` in `server/payments.py` is the only place a PEY/CoDi sale becomes `paid_pey`.** A PEY sale transitions to `paid_pey` exclusively inside `apply_payment`. The QR image, the client screen, and `payments` rows with `applied=0` prove nothing. Any change to `apply_payment` requires a new test in `server/tests` and notice to the integrator (AGENTS).
2. **Two verifiable triggers only.** A PEY sale is paid via (a) a validly signed webhook on `POST /webhooks/pey` (Standard Webhooks: signed content `{webhook-id}.{webhook-timestamp}.{raw-body}`, HMAC-SHA256 over the base64 part of `whsec_...`, ±300 s tolerance), or (b) reconciliation against `GET /transaction/codi/qr/{id}`.
3. **Exact recipient at QR creation.** `POST /codi/qr` creates the QR against the single PEY account bound to the tenant's active bank account/CLABE (the account the configured API key belongs to). The QR amount is exactly `charged_cents`; in demo mode the client charges `$0.01` and must show "Modo demo: se cobra $0.01". The QR carries `concept` (≤40 chars) and `metadata.saleId`, and the returned `qr_id` is persisted on `sales.pey_qr_id` (`UNIQUE`) so a sale maps to at most one QR.
4. **Reconciliation path.** `GET /api/sales/{sale_id}` (and cancel with `pendingOnly`) reconciles `pending`/`por_conciliar`/`expired` PEY sales: the `GET /transaction/codi/qr/{id}` call happens **outside** any write transaction; the chosen transaction (amount exactly `charged_cents`, falling back to the first eligible success-status transaction) is applied inside `BEGIN IMMEDIATE` through `apply_payment`, which is idempotent by `tx_id` — a concurrent webhook cannot double-apply.
5. **Duplicate webhooks are absorbed.** Each accepted webhook id is recorded in `webhook_events` (PK `webhook_id`); a repeated webhook id returns `{ok: true, outcome: "duplicate"}` without re-applying. A second payment with an already-seen `transaction_id` is `duplicate_transaction` (written `applied=0`, sale unchanged).
6. **Amount mismatch never pays.** A payment whose amount differs from `charged_cents` is recorded `applied=0` and the sale is set to `por_conciliar` with a note; it is never shown as paid and never decrements inventory.
7. **Late and extra payments are kept, not dropped.** A payment on a canceled sale (`late_payment`) or an extra payment on an already-paid sale (`extra_payment`) is written `applied=0` with a note, leaving the sale status untouched.
8. **Provider failure is uncertainty, not success.** `PeyTimeout` while creating the QR marks the sale `por_conciliar` (HTTP 202) and `PeyError`/`unexpected` marks it `failed` (HTTP 502); the `saleId` is always returned so the client can poll. A timeout means "must reconcile", never "paid". Reconciliation keeps working afterward through invariant 4.
9. **Money is integer cents internally; pesos only at the PEY HTTP boundary.** `amount_pesos = round(cents / 100, 2)` on the way out; `payload_cents` converts pesos (number or string, comma or dot) back to integer cents with half-up rounding.
10. **Collection is tenant-scoped.** A QR, its reconciliation, and its payment apply only to the sale's tenant; a webhook resolving a QR id is matched to the sale that owns that `pey_qr_id`, never across tenants.

## Acceptance scenarios

- **B3 · Banking and money** — Use a FakePey fixture labeled SIMULADO with two active IDs, a pending account, and a replacement account. Verify the exact recipient when a QR is created, reconciliation of the previous charge, duplicate webhook handling, and provider failure. The real $0.01 payment is recorded separately as a human-operated scenario.

## Provenance

- `server/payments.py` (`apply_payment`), `server/pey.py` (`PeyClient.create_qr`, `qr_transactions`, `verify_webhook`, `payload_cents`), `server/main.py` (`POST /api/sales`, `GET /api/sales/{sale_id}`, `POST /webhooks/pey`, `_reconcile_sale`).
- `docs/decisiones/0003-credenciales-y-pagos.md` (real-money test payments; no sandbox).
