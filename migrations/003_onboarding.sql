-- Abarpay onboarding + bank-account migration (M1 integration).
-- Folds the former ONBOARDING_DDL from server/onboarding.py into a real,
-- idempotent migration owned by the migrator (same style as 001).
--
-- DECISION (coordinator): the full CLABE is entered during registration but is
-- NEVER persisted in production. bank_accounts.clabe is made NULLABLE; the
-- production path stores only the local bank_account_id (the row id) and last4.
-- The SIMULADO in-memory store may keep a transient copy, clearly labeled
-- SIMULADO, and that copy never leaves the process.

-- ---------------------------------------------------------------------------
-- 1) The full CLABE is never persisted: relax the frozen NOT NULL from 001.
-- ---------------------------------------------------------------------------
ALTER TABLE bank_accounts ALTER COLUMN clabe DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- 2) Bank-account columns for the async production contract (additive; the
--    frozen demo columns bank_name/account_holder/active stay intact).
-- ---------------------------------------------------------------------------
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS alias text NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS account_name text NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS entity text NOT NULL DEFAULT 'BUSINESS';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'PENDING';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS last4 text NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS pey_account_id text;
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS simulated boolean NOT NULL DEFAULT true;
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS error_message text;
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS activated_at timestamptz;

-- ---------------------------------------------------------------------------
-- 3) Atomic signup: the ONLY way the first owner membership is created. The
--    service role cannot write tenants/stores/users/memberships directly
--    (membership writes are owner-only and manage_membership refuses the owner
--    role), so this SECURITY DEFINER function is the escape hatch that creates
--    tenant + store + owner + owner membership in ONE transaction.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION signup_tenant(
    p_idp text,
    p_external_sub text,
    p_email text,
    p_owner_name text,
    p_slug text,
    p_tenant_name text,
    p_store_name text,
    p_timezone text
)
RETURNS TABLE (tenant_id uuid, store_id uuid, user_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user uuid;
    v_tenant uuid;
    v_store uuid;
BEGIN
    INSERT INTO public.users (email, name, idp, external_sub)
    VALUES (coalesce(p_email, ''), coalesce(p_owner_name, ''), p_idp, p_external_sub)
    ON CONFLICT (idp, external_sub) DO NOTHING;

    SELECT u.id INTO v_user
    FROM public.users u
    WHERE u.idp = p_idp AND u.external_sub = p_external_sub;

    IF v_user IS NULL THEN
        RAISE EXCEPTION 'user not found after create' USING ERRCODE = '23505';
    END IF;

    v_tenant := gen_random_uuid();
    INSERT INTO public.tenants (id, slug, name, timezone, status)
    VALUES (v_tenant, p_slug, p_tenant_name,
            coalesce(p_timezone, 'America/Mexico_City'), 'active');

    v_store := gen_random_uuid();
    INSERT INTO public.stores (id, tenant_id, name)
    VALUES (v_store, v_tenant, coalesce(p_store_name, p_tenant_name));

    INSERT INTO public.memberships
        (user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active)
    VALUES
        (v_user, v_tenant, 'owner', true, true, true, true);

    RETURN QUERY SELECT v_tenant, v_store, v_user;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4) Clean-seed introspection (memberships use a self-read policy, so a plain
--    tenant-scoped count always sees zero; this count is internal-only).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION count_tenant_members(p_tenant_id uuid)
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT count(*) FROM public.memberships WHERE tenant_id = p_tenant_id;
$$;

REVOKE ALL ON FUNCTION signup_tenant(text, text, text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION count_tenant_members(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION signup_tenant(text, text, text, text, text, text, text, text) TO abarpay_app;
GRANT EXECUTE ON FUNCTION count_tenant_members(uuid) TO abarpay_app;
