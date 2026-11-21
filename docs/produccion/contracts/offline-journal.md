# Offline journal contract

- **Contract:** Atomic outbox, receipts, resumption, exactly-one-durable-operation
- **Version:** 1.0
- **Owner:** D2 Contracts — Pro domain owner
- **Consumers:** I3 (Mobile persistence), M2 (Checkout and till close), M3 (Purchasing and replenishment), G1 (Integration)
- **Fixture:** two test tenants — "Tienda Aurora" (tenant A) and "Tienda Beta" (tenant B) — one store each
- **Acceptance:** B4 · Offline sale and goods receipt; B8 · Recoverable release

## Invariants

1. **One durable operation = one outbox row.** Every mutating business operation (sale, goods receipt, inventory adjustment, payment) is written to a local atomic outbox in the same local transaction as the state change. The outbox and the state change commit together or not at all.
2. **Exactly-one-durable-operation.** Each outbox entry carries a stable idempotency key (the operation/sale id). Re-delivery, re-send after a lost ACK, or retry must produce the same server-side outcome: retries add neither money nor stock. The server deduplicates by the idempotency key — the current demo already enforces this shape with `payments.tx_id` (PK) and `webhook_events.webhook_id` (PK).
3. **Receipts gate deletion.** The server acknowledges each applied operation; the client only deletes the outbox entry after receiving the ACK. An entry is never deleted on a timeout.
4. **Resumption is ordered and safe.** On restart or reconnect the pending outbox replays in order. Each distinct sale survives. A second POS selling the same last unit is detected because stock is checked and applied server-side at apply time — the client cache is never trusted for a balance.
5. **No money or stock is synthesized from the cache.** The server recomputes line totals from its own catalog prices (never from the device) and applies each inventory movement exactly once per applied sale (cf. `apply_payment` → `decrement_inventory`, and `restore_inventory` on cancel).
6. **The journal is tenant-scoped.** Every outbox entry and its server-side `outbox_applied` counterpart is keyed by `tenant_id`; a device bound to Tienda Aurora can never replay an operation into Tienda Beta.

## Acceptance scenarios

- **B4 · Offline sale and goods receipt** — On the physical Android connected to ADB, enable airplane mode, sell the last unit, receive merchandise, close the app, reboot, and reconnect. A second POS sells the same unit. Lose the ACK and retry. Expected: both distinct sales survive, and retries add neither money nor stock.
- **B8 · Recoverable release** — Reinstall and upgrade the APK in place with a pending outbox. Expected: the outbox survives and replays; the database is restorable to a separate instance and rollback to a compatible build is rehearsed.

## Provenance

- `server/payments.py` (`decrement_inventory`, `restore_inventory`, `record_payment`, `apply_payment`), `server/db.py` (`write_transaction` `BEGIN IMMEDIATE` + retry), `server/main.py` (`POST /api/sales`, `POST /api/sales/{sale_id}/cancel`).
- Guide 09 rows I3 (Encrypted local database, atomic outbox, receipts, and resumption) and B4/B8.
