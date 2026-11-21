# 02 · Contracts and tenancy (multi-tenant on PostgreSQL with RLS)

Status: handoff package for the DSH team. Written 21-nov-2026. Implementation instructions for production. It does not modify the current demo code.

## Purpose

Convert the single-store demo backend (FastAPI + SQLite, one connection per request) into a multi-tenant service on PostgreSQL, with row-level security (RLS) and user-to-tenant membership. User identity (Auth0 and Microsoft Entra ID) lives in `04-identidad-onboarding-y-pey.md`, which this document consumes.

## Inherited context

- The demo stores a single store `tiendita-esquina` and three employees in SQLite (`server/db.py`, contract `docs/v1-contract.md`).
- Access is simulated with the `X-Employee-Id` header and the console uses a shared PIN (`docs/decisiones/0005-v1-android-backend-consola.md`).
- The rule that only `apply_payment` marks a PEY sale as paid is kept in production (`server/payments.py`).

## Design decisions

- A store equals a tenant. The relationship is 1 to 1 and is enforced in the schema.
- An owner user can be a member of several independent tenants. Each tenant is an isolated business.
- The isolation unit is `tenant_id`. RLS filters by tenant in every business table.
- The backend uses a single database role `abarpay_app` and sets the context per transaction with the variables `app.tenant_id` and `app.user_id`.
- No application query uses the superuser role or the owner of the tables.

## Data model

| Table | Purpose | Isolation key |
| --- | --- | --- |
| `tenants` | Business (1 to 1 with its store) | PK `id` |
| `stores` | Point of sale, unique per tenant | `tenant_id` UNIQUE |
| `users` | Unique identity of a person | PK `id` |
| `memberships` | User-tenant relationship with role and permissions | `tenant_id`, `user_id` |
| `invites` | Pending invites with a hashed token | `tenant_id` |
| Business tables | `products`, `sales`, `sale_items`, `payments`, `inventory_movements`, `fiado_customers`, `fiado_entries`, `fiado_drafts`, `expenses`, `day_tasks`, `bank_accounts`, `purchase_orders`, `receipts`, `till_shifts`, `outbox_applied` | `tenant_id` |

```sql
CREATE TABLE tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE,
  name text NOT NULL,
  legal_name text NOT NULL DEFAULT '',
  rfc text,
  country text NOT NULL DEFAULT 'MX',
  timezone text NOT NULL DEFAULT 'America/Mexico_City',
  status text NOT NULL CHECK (status IN ('active','suspended','closed')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE stores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL UNIQUE REFERENCES tenants(id),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  name text NOT NULL DEFAULT '',
  idp text NOT NULL CHECK (idp IN ('auth0','entra','legacy')),
  external_sub text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (idp, external_sub)
);

CREATE TABLE memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  role text NOT NULL CHECK (role IN ('owner','employee')),
  can_sell boolean NOT NULL DEFAULT false,
  can_fiado boolean NOT NULL DEFAULT false,
  can_inventory boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, user_id)
);

CREATE TABLE invites (
  token_hash text PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  email text,
  role text NOT NULL CHECK (role IN ('owner','employee')),
  can_sell boolean NOT NULL DEFAULT false,
  can_fiado boolean NOT NULL DEFAULT false,
  can_inventory boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz,
  revoked_at timestamptz
);
```

- `users.idp = 'legacy'` exists only to preserve the demo employees' history during migration. Those rows are historical and are never automatically linked to a real sign-in. A real sign-in creates its own `users` row.
- `UNIQUE (tenant_id)` on `stores` enforces the 1-to-1 relationship. Each tenant has at most one store and each store belongs to a single tenant.
- The invite token is generated with 32 random bytes, shown once, and persisted as `SHA-256(token)` in `token_hash`. The plaintext token is never stored or logged.

## Preventing cross-tenant foreign keys

Each parent table declares `UNIQUE (tenant_id, id)` and the foreign keys are composite, so a row can only reference another row from the same tenant.

```sql
ALTER TABLE stores ADD CONSTRAINT stores_tenant_id_id_key UNIQUE (tenant_id, id);
ALTER TABLE products ADD CONSTRAINT products_tenant_id_id_key UNIQUE (tenant_id, id);

CREATE TABLE sales (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  store_id uuid NOT NULL,
  employee_id uuid NOT NULL,
  status text NOT NULL,
  total_cents integer NOT NULL,
  charged_cents integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  occurred_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, employee_id) REFERENCES memberships (tenant_id, user_id),
  FOREIGN KEY (tenant_id, store_id) REFERENCES stores (tenant_id, id)
);

CREATE TABLE sale_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  sale_id uuid NOT NULL,
  product_id uuid NOT NULL,
  qty_milli integer NOT NULL,
  unit_price_cents integer NOT NULL,
  line_total_cents integer NOT NULL,
  FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id),
  FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id)
);
```

## Isolation with RLS

### Role and context variables

```sql
CREATE ROLE abarpay_app NOLOGIN;
-- The LOGIN connection role, without administrative privileges, assumes abarpay_app.
-- The migrator is a different principal. The service role lacks BYPASSRLS and DDL.
```

Each authorized request opens a transaction and sets the context before any query:

```python
def set_tenant_context(conn, *, tenant_id: str, user_id: str) -> None:
    conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id,))
```

The third argument `true` is equivalent to `SET LOCAL`. The local value is reverted when the transaction ends or aborts. Block global session values. Test reuse with commit and rollback. NULLIF also covers the empty marker of a reused connection.

### Canonical policy

```sql
ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE stores FORCE ROW LEVEL SECURITY;

CREATE POLICY store_tenant_isolation ON stores FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

The same policy applies to every business table, changing only its name. Rules:

- `current_setting('app.tenant_id', true)` returns `NULL` when the variable is not set. Comparing with `NULL` yields `NULL`, and a row yielding `NULL` is filtered out. The result is deny-by-default: without context, nothing is read or written.
- `FORCE ROW LEVEL SECURITY` prevents the table owner from bypassing the policy.
- The `FOR ALL` policies cover reads and writes with `USING` and `WITH CHECK`, so an `INSERT` or `UPDATE` that tries to write another `tenant_id` fails instead of being silently filtered.

### Auxiliary policies

```sql
-- A user sees their own record.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_self_read ON users FOR SELECT
  USING (id = NULLIF(current_setting('app.user_id', true), '')::uuid);

-- A user sees their own memberships; the owner manages them through the
-- application layer via a SECURITY DEFINER function limited to that purpose.
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY membership_self_read ON memberships FOR SELECT
  USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid);

ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE ROW LEVEL SECURITY;
```

Atomic signup creates the tenant, store, and owner, or rolls everything back. Set the user context from verified identity to query their memberships and select the tenant. The selection API rejects other tenants even if the requester knows the UUID. Resolve the OIDC identity by issuer and subject with a restricted bootstrap operation. The token grants no table permissions.

The management of `memberships` and `invites` is handled by the owner endpoint through a `SECURITY DEFINER` function limited to that purpose, with minimal execution identity, qualified schema names, a fixed search_path, and EXECUTE revoked from PUBLIC. Validate role and tenant inside each operation. Verify that a direct call cannot assign an owner or a foreign membership.

## SQLite → PostgreSQL migration

The migration is a one-time, idempotent utility with `--dry-run`:

1. Create the schema and apply RLS.
2. Inventory the stores and assign the explicitly identified demo store to its demo tenant. For that store, create `tenants` and its `stores` (1 to 1) and propagate `tenant_id` to all business rows.
3. Create historical `users` with `idp='legacy'` for **all** employees present in the cutover copy, including inactive ones, and their `memberships` with the v2-equivalent permissions. They are never claimed automatically.
4. Reassign `employee_id` and foreign-key references to the new UUIDs without losing inventory movements or payments.
5. Verify per-table counts against the SQLite database and emit a difference report.

The SQLite database remains only as the migration source. The active production database becomes PostgreSQL, and SQLite is never written after the cutover.

## Tenancy contracts (API)

Membership operations require verified identity. Issue invites only to employees with the selected permissions; acceptance cannot elevate the role. Protect the store's last owner. To select a store, `GET /api/me/memberships` lists only the user's active memberships and `POST /api/session/store` verifies the chosen one before rotating the session. The selected tenant is never trusted to a client identity header. The owner is identified by their `membership.role = 'owner'`.

- `GET /api/tenant` → `{id, slug, name, legalName, rfc, timezone, status, store:{id, name}}` for the token's tenant.
- `GET /api/tenant/members` (owner) → `{items:[{userId, email, name, role, canSell, canFiado, canInventory, active}]}`.
- `POST /api/tenant/members/invite` (owner) body `{email?, role, canSell, canFiado, canInventory}` → `{token, url}`.
- `GET /api/tenant/members/invites/{token}` → minimal invite data (404 if expired or revoked). The token is looked up by its hash.
- `POST /api/tenant/members/invites/{token}/accept` → creates the `membership` and returns the profile.
- `PATCH /api/tenant/members/{userId}` (owner) body `{role?, canSell?, canFiado?, canInventory?, active?}`.
- `DELETE /api/tenant/members/{userId}` (owner) → deactivates the membership.

Authorization rules:

- `owner`: the entire tenant, including bank account management.
- `employee`: only what `can_sell`, `can_fiado`, and `can_inventory` enable.

## Per-request context flow

```mermaid
sequenceDiagram
    participant C as Client (app/console)
    participant A as API (FastAPI)
    participant D as PostgreSQL
    C->>A: request with Bearer token
    A->>A: validates access token (aud, iss, exp) and resolves user
    A->>A: resolves membership and tenant_id
    A->>D: BEGIN; set_config('app.tenant_id',...,true)
    A->>D: business query (RLS filters by tenant)
    A->>D: COMMIT (context reverts)
    A->>C: response
```

## Failure modes and recovery

| Failure | Behavior | Recovery |
| --- | --- | --- |
| Missing tenant context | RLS returns zero rows and writes fail | The endpoint requires 401/403 before querying |
| Reused pool connection | `SET LOCAL` reverts when the transaction ends | Verify that a second request without context sees no rows |
| Attempt to write another `tenant_id` | `WITH CHECK` fails the statement | Logged as a 403 error, with no partial write |
| Cross-tenant foreign key | The composite FK fails | The row is rejected without modifying the database |
| Interrupted migration | `--dry-run` first and one transaction per table | Rerun; idempotency does not duplicate rows |
| `current_setting` with an unqualified name | PostgreSQL rejects variables without a namespace | Always use `app.tenant_id` and `app.user_id` |

## Acceptance criteria

- [ ] Two tenants A and B: A's `GET /api/tenant` returns no rows from B in any business table.
- [ ] A direct query with `app.tenant_id` unset returns zero rows (deny-by-default).
- [ ] `FORCE ROW LEVEL SECURITY` is active and `abarpay_app` is neither an owner nor a superuser.
- [ ] The 1-to-1 relationship is enforced: a second `stores` row for the same tenant fails.
- [ ] A foreign key that points to another `tenant_id` fails.
- [ ] The invite token is only stored as a hash and the plaintext token does not appear in the database or in logs.
- [ ] A real sign-in never automatically claims a `legacy` row.
- [ ] An owner can belong to several independent tenants.
- [ ] Migrating a SQLite database with sales, movements, and fiado reproduces the counts in PostgreSQL.
- [ ] There are no credentials or secrets in the schema, migrations, or logs.

## Gates

- [ ] Integration test against a test PostgreSQL instance that exercises the policies of two tenants and the negative cases.
- [ ] Regression test that lists the schema tables and fails if any business table lacks RLS enabled (`pg_class.relrowsecurity = true`) and a tenant policy.
- [ ] Test of the 1-to-1 constraints and composite cross-tenant foreign keys.
- [ ] `--dry-run` and `--apply` migration over a SQLite fixture in green, run twice to prove idempotency.
- [ ] Backup and restore exercise without losing isolation.

## Provenance

- CREATE POLICY (PostgreSQL): <https://www.postgresql.org/docs/current/sql-createpolicy.html>
- Inherited v1 contract: `docs/v1-contract.md`
- Inherited v2 contract (team, permissions, invites): `docs/v2-contract.md`

## Locked decisions

- A store equals a tenant (1 to 1). An owner user can be a member of several tenants.
- Production roles: `owner` and `employee` with the described permissions.
- Invite tokens are stored hashed and shown once.
