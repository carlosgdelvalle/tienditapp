# Tenancy isolation contract

- **Contract:** Tenancy isolation and resource ownership (multi-tenant on PostgreSQL with RLS)
- **Version:** 1.0
- **Owner:** D2 Contracts — Pro domain owner
- **Consumers:** I1 (Tenancy), I2 (Identity), I3 (Mobile persistence), M1, M2, M3, M4, M6, G1
- **Fixture:** two test tenants — "Tienda Aurora" (tenant A) and "Tienda Beta" (tenant B) — one store each
- **Acceptance:** B1 · Signup, invitations, isolation

## Invariants

1. **A store equals a tenant (1-to-1).** Enforced in the schema with `stores.tenant_id UNIQUE`. Each tenant has at most one store and each store belongs to exactly one tenant. A second `stores` row for the same tenant must fail.
2. **`tenant_id` is the isolation unit.** Every business table — `products`, `sales`, `sale_items`, `payments`, `inventory_movements`, `fiado_customers`, `fiado_entries`, `fiado_drafts`, `expenses`, `day_tasks`, `bank_accounts`, `purchase_orders`, `receipts`, `till_shifts`, `outbox_applied` — carries `tenant_id`.
3. **RLS deny-by-default.** Each business table has `FORCE ROW LEVEL SECURITY` plus a `FOR ALL` policy `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)` and the same `WITH CHECK`. With no context set, `current_setting` returns `NULL`, the comparison yields `NULL`, and the row is filtered out: nothing is read, nothing is written.
4. **Writes are guarded, not silently filtered.** The `WITH CHECK` clause makes an `INSERT`/`UPDATE` that targets another `tenant_id` fail with no partial write.
5. **One service role, no superuser.** All app queries run as `abarpay_app` (`NOLOGIN`, no `BYPASSRLS`, not a table owner, no `DDL`). The migrator is a separate principal. `FORCE ROW LEVEL SECURITY` prevents the table owner from bypassing the policy.
6. **Context is per-transaction.** Each authorized request opens a transaction and sets `set_config('app.tenant_id', %s, true)` (equivalent to `SET LOCAL`); the value reverts at `COMMIT`/`ROLLBACK`. Global/session values are blocked, and `NULLIF` covers the empty marker of a reused pool connection.
7. **The tenant is resolved from verified identity, never from a client header.** `GET /api/me/memberships` lists only the caller's active memberships; `POST /api/session/store` verifies the chosen membership before rotating the session. Knowing another tenant's UUID is not enough: the selection API rejects it.
8. **Roles bound to the membership.** `owner` controls the whole tenant including bank-account management; `employee` is limited to what `can_sell`, `can_fiado`, and `can_inventory` enable. The owner is identified by `membership.role = 'owner'`.
9. **Cross-tenant foreign keys are impossible.** Every parent table declares `UNIQUE (tenant_id, id)` and foreign keys are composite `(tenant_id, …)`, so a row can only reference another row of the same tenant.
10. **Membership and invite writes are the only escape from pure RLS.** They run through a `SECURITY DEFINER` function limited to that purpose: minimal execution identity, qualified schema names, fixed `search_path`, `EXECUTE` revoked from `PUBLIC`, and role + tenant validated inside each operation. A direct call cannot assign an owner or a foreign membership.
11. **Invites are unguessable and untraceable.** The token is 32 random bytes, shown once, stored only as `SHA-256(token)` in `invites.token_hash`; the plaintext never appears in the database or logs.
12. **Legacy rows are inert.** `users.idp='legacy'` rows exist only to preserve the demo employees' history through migration and are never automatically claimed by a real sign-in.

## What a tenant cannot read or write

With context set to "Tienda Aurora", the service:

- **Cannot read** Tienda Beta's products, sales, sale items, payments, inventory movements, fiado customers or entries, expenses, tasks, tickets, bank accounts, purchase orders, receipts, till shifts, or outbox rows — reads return zero rows.
- **Cannot write** any of the above for Tienda Beta — writes fail (`WITH CHECK`), with no balance, stock, or ledger change.
- **Cannot learn of resource existence** — a request for Beta's product or sale id returns "not found", indistinguishable from a non-existent id.
- **Cannot select** Tienda Beta's store through `POST /api/session/store` even when the caller knows its UUID.
- **Cannot assign** an owner or a foreign membership through a direct membership write.

## Acceptance scenarios

- **B1 · Signup, invitations, isolation** — Register A (Tienda Aurora) and B (Tienda Beta) from scratch; create identical product codes and same-name debt records; invite employee A; then attempt to read and write B's resources as A via API, jobs, export, and mobile cache. Expected: denial without balance changes and without disclosure of resource existence.

## Provenance

- `docs/produccion/02-contratos-y-tenencia.md` (design, schema, RLS policies, migration).
- `docs/decisiones/0005-v1-android-backend-consola.md` (single-store demo baseline; `X-Employee-Id`/`X-Owner-Pin` are demo-only and are replaced by verified identity + `app.tenant_id` in production).
