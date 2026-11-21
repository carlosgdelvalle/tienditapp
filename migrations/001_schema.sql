-- Abarpay production schema: multi-tenant PostgreSQL with RLS.
-- Tenancy contract: docs/produccion/contracts/tenancy.md
-- Design + data model: docs/produccion/02-contratos-y-tenencia.md
--
-- Idempotent: safe to run repeatedly (CREATE TABLE IF NOT EXISTS,
-- CREATE OR REPLACE FUNCTION, DROP POLICY IF EXISTS ... CREATE POLICY).
-- Owned by the migrator (a superuser principal). The service role is
-- abarpay_app (NOLOGIN, no BYPASSRLS, not a table owner, no DDL).
-- gen_random_uuid() is built into PostgreSQL 13+; no extension is required.

-- ---------------------------------------------------------------------------
-- Role: the single service role. It already exists in the dev cluster; the
-- guard keeps the file portable and idempotent.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'abarpay_app') THEN
        CREATE ROLE abarpay_app NOLOGIN;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Identity / tenancy core
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tenants (
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

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    name text NOT NULL DEFAULT '',
    idp text NOT NULL CHECK (idp IN ('auth0','entra','legacy')),
    external_sub text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (idp, external_sub)
);

CREATE TABLE IF NOT EXISTS memberships (
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

-- 1-to-1: a store equals a tenant. stores.tenant_id is UNIQUE and the
-- composite UNIQUE (tenant_id, id) is the target of composite foreign keys.
CREATE TABLE IF NOT EXISTS stores (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL UNIQUE REFERENCES tenants(id),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

-- The plaintext invite token is never stored. Only SHA-256(token) lives here.
CREATE TABLE IF NOT EXISTS invites (
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

-- ---------------------------------------------------------------------------
-- Business tables. Every one carries tenant_id, a composite
-- UNIQUE (tenant_id, id), and composite foreign keys so a row can only
-- reference another row of the same tenant.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL,
    aliases text NOT NULL DEFAULT '[]',
    unit text NOT NULL,
    price_cents integer NOT NULL,
    stock_milli integer NOT NULL,
    low_stock_milli integer NOT NULL DEFAULT 5000,
    quick boolean NOT NULL DEFAULT false,
    unlimited_stock boolean NOT NULL DEFAULT false,
    kind text NOT NULL DEFAULT 'producto',
    category text,
    duration_minutes integer,
    image_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS fiado_customers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL,
    phone text,
    credit_limit_cents integer,
    due_days integer,
    active boolean NOT NULL DEFAULT true,
    reminders_consent boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS sales (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    store_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    status text NOT NULL,
    payment_method text NOT NULL CHECK (payment_method IN ('cash','pey','fiado')),
    total_cents integer NOT NULL,
    charged_cents integer NOT NULL,
    cash_received_cents integer,
    change_cents integer,
    customer_id uuid,
    pey_qr_id text UNIQUE,
    pey_tx_id text,
    paid_at timestamptz,
    expires_at timestamptz,
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    occurred_at timestamptz,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, employee_id) REFERENCES memberships (tenant_id, user_id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id) REFERENCES fiado_customers (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS sale_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    sale_id uuid NOT NULL,
    product_id uuid NOT NULL,
    name text NOT NULL,
    unit text NOT NULL,
    qty_milli integer NOT NULL,
    unit_price_cents integer NOT NULL,
    line_total_cents integer NOT NULL,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS payments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    tx_id text NOT NULL UNIQUE,
    sale_id uuid NOT NULL,
    amount_cents integer NOT NULL,
    method text NOT NULL,
    source text NOT NULL,
    applied boolean NOT NULL DEFAULT true,
    received_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    product_id uuid NOT NULL,
    delta_milli integer NOT NULL,
    reason text NOT NULL,
    sale_id uuid,
    employee_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id),
    FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id),
    FOREIGN KEY (tenant_id, employee_id) REFERENCES memberships (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS fiado_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    customer_id uuid NOT NULL,
    sale_id uuid,
    kind text NOT NULL CHECK (kind IN ('charge','payment')),
    amount_cents integer NOT NULL,
    note text,
    employee_id uuid,
    due_at timestamptz,
    reminded_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id) REFERENCES fiado_customers (tenant_id, id),
    FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id),
    FOREIGN KEY (tenant_id, employee_id) REFERENCES memberships (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS fiado_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    customer_id uuid NOT NULL,
    sale_id uuid,
    kind text NOT NULL DEFAULT 'charge' CHECK (kind IN ('charge','payment')),
    amount_cents integer NOT NULL,
    note text,
    employee_id uuid,
    due_at timestamptz,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','authorized','rejected','applied')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id) REFERENCES fiado_customers (tenant_id, id),
    FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id),
    FOREIGN KEY (tenant_id, employee_id) REFERENCES memberships (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS expenses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    employee_id uuid,
    amount_cents integer NOT NULL,
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, employee_id) REFERENCES memberships (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS day_tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    key text NOT NULL,
    title text NOT NULL,
    assigned_employee_id uuid,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, key),
    FOREIGN KEY (tenant_id, assigned_employee_id) REFERENCES memberships (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    clabe text NOT NULL,
    bank_name text NOT NULL DEFAULT '',
    account_holder text NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    supplier_name text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','partial','received','canceled')),
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    issued_at timestamptz,
    received_at timestamptz,
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    purchase_order_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'awaiting_approval' CHECK (status IN ('awaiting_approval','approved')),
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_at timestamptz,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, purchase_order_id) REFERENCES purchase_orders (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS till_shifts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    store_id uuid NOT NULL,
    opened_by uuid,
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_by uuid,
    closed_at timestamptz,
    opening_float_cents integer NOT NULL DEFAULT 0,
    expected_cents integer NOT NULL DEFAULT 0,
    counted_cents integer,
    variance_cents integer,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','counted','delivered','accepted','observed')),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores (tenant_id, id),
    FOREIGN KEY (tenant_id, opened_by) REFERENCES memberships (tenant_id, user_id),
    FOREIGN KEY (tenant_id, closed_by) REFERENCES memberships (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS outbox_applied (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    device_id text NOT NULL,
    event_id text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (device_id, event_id)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    webhook_id text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    outcome text NOT NULL,
    UNIQUE (tenant_id, id),
    UNIQUE (webhook_id)
);

CREATE TABLE IF NOT EXISTS barcodes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    code text NOT NULL,
    product_id uuid NOT NULL,
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, code),
    FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id)
);

-- Per-store settings (onboarding answers kept from the SQLite demo).
CREATE TABLE IF NOT EXISTS store_settings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL UNIQUE REFERENCES tenants(id),
    store_id uuid,
    business_type text NOT NULL DEFAULT '',
    owner_name text NOT NULL DEFAULT '',
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, store_id) REFERENCES stores (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    sale_id uuid,
    note text,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, sale_id) REFERENCES sales (tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------

-- Canonical tenant-isolation policy: deny-by-default. With no context,
-- current_setting(...) is NULL, the comparison yields NULL, and the row is
-- filtered out. Writes are guarded by WITH CHECK, so a cross-tenant write
-- fails instead of being silently dropped. FORCE keeps the table owner from
-- bypassing the policy.
ALTER TABLE stores ENABLE ROW LEVEL SECURITY;
ALTER TABLE stores FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS stores_tenant_isolation ON stores;
CREATE POLICY stores_tenant_isolation ON stores FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE products FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS products_tenant_isolation ON products;
CREATE POLICY products_tenant_isolation ON products FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sales_tenant_isolation ON sales;
CREATE POLICY sales_tenant_isolation ON sales FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE sale_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale_items FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sale_items_tenant_isolation ON sale_items;
CREATE POLICY sale_items_tenant_isolation ON sale_items FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS payments_tenant_isolation ON payments;
CREATE POLICY payments_tenant_isolation ON payments FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE inventory_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_movements FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS inventory_movements_tenant_isolation ON inventory_movements;
CREATE POLICY inventory_movements_tenant_isolation ON inventory_movements FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE fiado_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE fiado_customers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fiado_customers_tenant_isolation ON fiado_customers;
CREATE POLICY fiado_customers_tenant_isolation ON fiado_customers FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE fiado_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE fiado_entries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fiado_entries_tenant_isolation ON fiado_entries;
CREATE POLICY fiado_entries_tenant_isolation ON fiado_entries FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE fiado_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE fiado_drafts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS fiado_drafts_tenant_isolation ON fiado_drafts;
CREATE POLICY fiado_drafts_tenant_isolation ON fiado_drafts FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE expenses FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS expenses_tenant_isolation ON expenses;
CREATE POLICY expenses_tenant_isolation ON expenses FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE day_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE day_tasks FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS day_tasks_tenant_isolation ON day_tasks;
CREATE POLICY day_tasks_tenant_isolation ON day_tasks FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE bank_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_accounts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bank_accounts_tenant_isolation ON bank_accounts;
CREATE POLICY bank_accounts_tenant_isolation ON bank_accounts FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_orders FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS purchase_orders_tenant_isolation ON purchase_orders;
CREATE POLICY purchase_orders_tenant_isolation ON purchase_orders FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS receipts_tenant_isolation ON receipts;
CREATE POLICY receipts_tenant_isolation ON receipts FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE till_shifts ENABLE ROW LEVEL SECURITY;
ALTER TABLE till_shifts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS till_shifts_tenant_isolation ON till_shifts;
CREATE POLICY till_shifts_tenant_isolation ON till_shifts FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE outbox_applied ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_applied FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outbox_applied_tenant_isolation ON outbox_applied;
CREATE POLICY outbox_applied_tenant_isolation ON outbox_applied FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS webhook_events_tenant_isolation ON webhook_events;
CREATE POLICY webhook_events_tenant_isolation ON webhook_events FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE barcodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE barcodes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS barcodes_tenant_isolation ON barcodes;
CREATE POLICY barcodes_tenant_isolation ON barcodes FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE store_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE store_settings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS store_settings_tenant_isolation ON store_settings;
CREATE POLICY store_settings_tenant_isolation ON store_settings FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_tickets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS support_tickets_tenant_isolation ON support_tickets;
CREATE POLICY support_tickets_tenant_isolation ON support_tickets FOR ALL
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- Auxiliary policies.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_self_read ON users;
CREATE POLICY user_self_read ON users FOR SELECT
    USING (id = NULLIF(current_setting('app.user_id', true), '')::uuid);

ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS membership_self_read ON memberships;
CREATE POLICY membership_self_read ON memberships FOR SELECT
    USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid);

-- Invites are readable/writable only through the SECURITY DEFINER functions.
ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- SECURITY DEFINER functions: the only escape from pure RLS for membership
-- and invite writes. Fixed search_path, qualified names, EXECUTE revoked from
-- PUBLIC, and role + tenant validated inside each operation.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION manage_membership(
    p_tenant_id uuid,
    p_user_id uuid,
    p_role text,
    p_can_sell boolean,
    p_can_fiado boolean,
    p_can_inventory boolean,
    p_active boolean
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_caller uuid;
    v_ok boolean;
    v_id uuid;
BEGIN
    v_caller := NULLIF(current_setting('app.user_id', true), '')::uuid;
    IF v_caller IS NULL THEN
        RAISE EXCEPTION 'missing app.user_id context' USING ERRCODE = '42501';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM public.memberships
        WHERE tenant_id = p_tenant_id
          AND user_id = v_caller
          AND role = 'owner'
          AND active
    ) INTO v_ok;
    IF NOT v_ok THEN
        RAISE EXCEPTION 'forbidden: caller is not an owner of this tenant'
            USING ERRCODE = '42501';
    END IF;

    IF p_role NOT IN ('owner','employee') THEN
        RAISE EXCEPTION 'invalid role' USING ERRCODE = '22023';
    END IF;
    -- This escape hatch can never assign the owner role; the first owner is
    -- created only by the atomic signup flow.
    IF p_role = 'owner' THEN
        RAISE EXCEPTION 'forbidden: owner role is not assignable here'
            USING ERRCODE = '42501';
    END IF;
    -- Protect the last owner: an existing owner membership is immutable here.
    IF EXISTS (
        SELECT 1 FROM public.memberships
        WHERE tenant_id = p_tenant_id AND user_id = p_user_id AND role = 'owner'
    ) THEN
        RAISE EXCEPTION 'forbidden: owner memberships are immutable here'
            USING ERRCODE = '42501';
    END IF;

    INSERT INTO public.memberships
        (user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active)
    VALUES
        (p_user_id, p_tenant_id, p_role, p_can_sell, p_can_fiado, p_can_inventory, p_active)
    ON CONFLICT (tenant_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            can_sell = EXCLUDED.can_sell,
            can_fiado = EXCLUDED.can_fiado,
            can_inventory = EXCLUDED.can_inventory,
            active = EXCLUDED.active
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION create_invite(
    p_tenant_id uuid,
    p_email text,
    p_role text,
    p_can_sell boolean,
    p_can_fiado boolean,
    p_can_inventory boolean,
    p_token_hash text,
    p_expires_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_caller uuid;
    v_ok boolean;
BEGIN
    v_caller := NULLIF(current_setting('app.user_id', true), '')::uuid;
    IF v_caller IS NULL THEN
        RAISE EXCEPTION 'missing app.user_id context' USING ERRCODE = '42501';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM public.memberships
        WHERE tenant_id = p_tenant_id
          AND user_id = v_caller
          AND role = 'owner'
          AND active
    ) INTO v_ok;
    IF NOT v_ok THEN
        RAISE EXCEPTION 'forbidden: caller is not an owner of this tenant'
            USING ERRCODE = '42501';
    END IF;

    -- Invites only grant the employee role; acceptance cannot elevate it.
    IF p_role <> 'employee' THEN
        RAISE EXCEPTION 'forbidden: invites are employee-only' USING ERRCODE = '42501';
    END IF;
    IF p_token_hash IS NULL OR p_token_hash = '' THEN
        RAISE EXCEPTION 'invalid token hash' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.invites
        (token_hash, tenant_id, email, role, can_sell, can_fiado, can_inventory, expires_at)
    VALUES
        (p_token_hash, p_tenant_id, p_email, p_role, p_can_sell, p_can_fiado, p_can_inventory, p_expires_at);
END;
$$;

CREATE OR REPLACE FUNCTION accept_invite(
    p_token_hash text,
    p_tenant_id uuid,
    p_user_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_role text;
    v_can_sell boolean;
    v_can_fiado boolean;
    v_can_inventory boolean;
    v_inv_tenant uuid;
    v_revoked timestamptz;
    v_accepted timestamptz;
    v_expires timestamptz;
    v_id uuid;
BEGIN
    SELECT tenant_id, role, can_sell, can_fiado, can_inventory,
           revoked_at, accepted_at, expires_at
      INTO v_inv_tenant, v_role, v_can_sell, v_can_fiado, v_can_inventory,
           v_revoked, v_accepted, v_expires
    FROM public.invites
    WHERE token_hash = p_token_hash;

    IF NOT FOUND OR v_inv_tenant IS DISTINCT FROM p_tenant_id THEN
        RAISE EXCEPTION 'invite not found' USING ERRCODE = '22023';
    END IF;
    IF v_revoked IS NOT NULL OR v_accepted IS NOT NULL THEN
        RAISE EXCEPTION 'invite no longer valid' USING ERRCODE = '22023';
    END IF;
    IF v_expires < now() THEN
        RAISE EXCEPTION 'invite expired' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.memberships
        (user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active)
    VALUES
        (p_user_id, p_tenant_id, v_role, v_can_sell, v_can_fiado, v_can_inventory, true)
    ON CONFLICT (tenant_id, user_id) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        SELECT id INTO v_id FROM public.memberships
        WHERE tenant_id = p_tenant_id AND user_id = p_user_id;
    END IF;

    UPDATE public.invites SET accepted_at = now() WHERE token_hash = p_token_hash;

    RETURN v_id;
END;
$$;

-- EXECUTE is revoked from PUBLIC; only the service role may call them.
REVOKE ALL ON FUNCTION manage_membership(uuid, uuid, text, boolean, boolean, boolean, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION create_invite(uuid, text, text, boolean, boolean, boolean, text, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION accept_invite(text, uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION manage_membership(uuid, uuid, text, boolean, boolean, boolean, boolean) TO abarpay_app;
GRANT EXECUTE ON FUNCTION create_invite(uuid, text, text, boolean, boolean, boolean, text, timestamptz) TO abarpay_app;
GRANT EXECUTE ON FUNCTION accept_invite(text, uuid, uuid) TO abarpay_app;

-- ---------------------------------------------------------------------------
-- abarpay_app grants. RLS governs what the role can read/write.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO abarpay_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO abarpay_app;
GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public TO abarpay_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO abarpay_app;
