-- Employee phone invitations and server-enforced mobile permissions.
-- Additive: preserves legacy email invites and the frozen role checks.

ALTER TABLE public.invites ADD COLUMN IF NOT EXISTS phone text;
ALTER TABLE public.invites ADD COLUMN IF NOT EXISTS accepted_by uuid;

-- Superseded pending phone invites for the same tenant + number are revoked
-- when a new one is minted, so stale links cannot grant older permissions.
-- Replacement is serialized per (tenant, phone) with an advisory lock.
CREATE OR REPLACE FUNCTION create_invite(
    p_tenant_id uuid,
    p_email text,
    p_phone text,
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
        SELECT 1 FROM public.memberships m
        WHERE m.tenant_id = p_tenant_id
          AND m.user_id = v_caller
          AND m.role = 'owner'
          AND m.active
    ) INTO v_ok;
    IF NOT v_ok THEN
        RAISE EXCEPTION 'forbidden: caller is not an owner of this tenant'
            USING ERRCODE = '42501';
    END IF;

    IF p_role <> 'employee' THEN
        RAISE EXCEPTION 'forbidden: invites are employee-only' USING ERRCODE = '42501';
    END IF;
    IF p_token_hash IS NULL OR p_token_hash = '' THEN
        RAISE EXCEPTION 'invalid token hash' USING ERRCODE = '22023';
    END IF;

    IF p_phone IS NOT NULL THEN
        PERFORM pg_advisory_xact_lock(
            hashtextextended(p_tenant_id::text || ':' || p_phone, 0)
        );
        UPDATE public.invites i
           SET revoked_at = now()
         WHERE i.tenant_id = p_tenant_id
           AND i.phone = p_phone
           AND i.accepted_at IS NULL
           AND i.revoked_at IS NULL
           AND i.token_hash <> p_token_hash;
    END IF;

    INSERT INTO public.invites
        (token_hash, tenant_id, email, phone, role, can_sell, can_fiado, can_inventory, expires_at)
    VALUES
        (p_token_hash, p_tenant_id, p_email, p_phone, p_role, p_can_sell, p_can_fiado, p_can_inventory, p_expires_at);
END;
$$;

-- Accept returns the resulting membership row and records accepted_by. A retry
-- by the exact same user recovers current status without re-granting flags or
-- reactivating. The bound phone is re-checked under the row lock.
CREATE OR REPLACE FUNCTION accept_invite(
    p_token_hash text,
    p_tenant_id uuid,
    p_user_id uuid,
    p_name text,
    p_phone text
)
RETURNS TABLE (
    user_id uuid, tenant_id uuid, role text,
    can_sell boolean, can_fiado boolean, can_inventory boolean, active boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_can_sell boolean;
    v_can_fiado boolean;
    v_can_inventory boolean;
    v_inv_tenant uuid;
    v_inv_phone text;
    v_revoked timestamptz;
    v_accepted timestamptz;
    v_accepted_by uuid;
    v_expires timestamptz;
BEGIN
    SELECT i.tenant_id, i.can_sell, i.can_fiado, i.can_inventory, i.phone,
           i.revoked_at, i.accepted_at, i.accepted_by, i.expires_at
      INTO v_inv_tenant, v_can_sell, v_can_fiado, v_can_inventory, v_inv_phone,
           v_revoked, v_accepted, v_accepted_by, v_expires
    FROM public.invites i
    WHERE i.token_hash = p_token_hash
    FOR UPDATE;

    IF NOT FOUND OR v_inv_tenant IS DISTINCT FROM p_tenant_id THEN
        RAISE EXCEPTION 'invite not found' USING ERRCODE = '22023';
    END IF;
    IF v_revoked IS NOT NULL THEN
        RAISE EXCEPTION 'invite no longer valid' USING ERRCODE = '22023';
    END IF;
    IF v_expires < now() THEN
        RAISE EXCEPTION 'invite expired' USING ERRCODE = '22023';
    END IF;
    IF v_inv_phone IS DISTINCT FROM p_phone THEN
        RAISE EXCEPTION 'invite phone does not match the verified caller'
            USING ERRCODE = '42501';
    END IF;
    IF v_inv_phone IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM owner_auth.credentials c
        WHERE c.user_id = p_user_id AND c.phone = v_inv_phone
    ) THEN
        RAISE EXCEPTION 'invite has no matching phone credential'
            USING ERRCODE = '42501';
    END IF;

    IF v_accepted IS NOT NULL OR v_accepted_by IS NOT NULL THEN
        IF v_accepted_by IS NULL OR v_accepted_by <> p_user_id THEN
            RAISE EXCEPTION 'invite already accepted' USING ERRCODE = '22023';
        END IF;
        RETURN QUERY
        SELECT m.user_id, m.tenant_id, m.role, m.can_sell, m.can_fiado,
               m.can_inventory, m.active
          FROM public.memberships m
         WHERE m.tenant_id = p_tenant_id AND m.user_id = p_user_id;
        RETURN;
    END IF;

    IF p_name IS NOT NULL AND p_name <> '' THEN
        UPDATE public.users SET name = p_name WHERE id = p_user_id AND name = '';
    END IF;

    INSERT INTO public.memberships
        (user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active)
    VALUES
        (p_user_id, p_tenant_id, 'employee', v_can_sell, v_can_fiado, v_can_inventory, true)
    ON CONFLICT ON CONSTRAINT memberships_tenant_id_user_id_key DO NOTHING;

    UPDATE public.invites
       SET accepted_at = now(), accepted_by = p_user_id
     WHERE token_hash = p_token_hash;

    RETURN QUERY
    SELECT m.user_id, m.tenant_id, m.role, m.can_sell, m.can_fiado,
           m.can_inventory, m.active
      FROM public.memberships m
     WHERE m.tenant_id = p_tenant_id AND m.user_id = p_user_id;
END;
$$;

-- Legacy self-service claim (email invites) cannot consume phone-bound rows.
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
    v_inv_phone text;
    v_revoked timestamptz;
    v_accepted timestamptz;
    v_expires timestamptz;
    v_id uuid;
BEGIN
    SELECT i.tenant_id, i.role, i.can_sell, i.can_fiado, i.can_inventory, i.phone,
           i.revoked_at, i.accepted_at, i.expires_at
      INTO v_inv_tenant, v_role, v_can_sell, v_can_fiado, v_can_inventory, v_inv_phone,
           v_revoked, v_accepted, v_expires
    FROM public.invites i
    WHERE i.token_hash = p_token_hash
    FOR UPDATE;

    IF NOT FOUND OR v_inv_tenant IS DISTINCT FROM p_tenant_id THEN
        RAISE EXCEPTION 'invite not found' USING ERRCODE = '22023';
    END IF;
    IF v_revoked IS NOT NULL OR v_accepted IS NOT NULL THEN
        RAISE EXCEPTION 'invite no longer valid' USING ERRCODE = '22023';
    END IF;
    IF v_expires < now() THEN
        RAISE EXCEPTION 'invite expired' USING ERRCODE = '22023';
    END IF;
    IF v_inv_phone IS NOT NULL THEN
        RAISE EXCEPTION 'phone-bound invite requires verified phone' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.memberships
        (user_id, tenant_id, role, can_sell, can_fiado, can_inventory, active)
    VALUES
        (p_user_id, p_tenant_id, v_role, v_can_sell, v_can_fiado, v_can_inventory, true)
    ON CONFLICT ON CONSTRAINT memberships_tenant_id_user_id_key DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NULL THEN
        SELECT m.id INTO v_id FROM public.memberships m
        WHERE m.tenant_id = p_tenant_id AND m.user_id = p_user_id;
    END IF;

    UPDATE public.invites
       SET accepted_at = now(), accepted_by = p_user_id
     WHERE token_hash = p_token_hash;

    RETURN v_id;
END;
$$;

-- Self-service invite read returns the bound phone and accepted_by so the
-- service layer can enforce the phone match without exposing it to clients.
CREATE OR REPLACE FUNCTION get_employee_invite_by_hash(
    p_token_hash text
)
RETURNS TABLE (
    token_hash text, tenant_id uuid, email text, phone text, role text,
    can_sell boolean, can_fiado boolean, can_inventory boolean,
    created_at timestamptz, expires_at timestamptz,
    accepted_at timestamptz, revoked_at timestamptz, accepted_by uuid
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT i.token_hash, i.tenant_id, i.email, i.phone, i.role,
           i.can_sell, i.can_fiado, i.can_inventory,
           i.created_at, i.expires_at, i.accepted_at, i.revoked_at, i.accepted_by
    FROM public.invites i
    WHERE i.token_hash = p_token_hash;
$$;

REVOKE ALL ON FUNCTION create_invite(uuid, text, text, text, boolean, boolean, boolean, text, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION accept_invite(text, uuid, uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION accept_invite(text, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION get_employee_invite_by_hash(text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION create_invite(uuid, text, text, text, boolean, boolean, boolean, text, timestamptz) TO abarpay_app;
GRANT EXECUTE ON FUNCTION accept_invite(text, uuid, uuid, text, text) TO abarpay_app;
GRANT EXECUTE ON FUNCTION accept_invite(text, uuid, uuid) TO abarpay_app;
GRANT EXECUTE ON FUNCTION get_employee_invite_by_hash(text) TO abarpay_app;
