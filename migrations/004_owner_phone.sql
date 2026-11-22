-- Local owner credentials. A phone number is a replaceable authenticator,
-- never the user's subject or the tenant's identifier.
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_idp_check;
ALTER TABLE public.users ADD CONSTRAINT users_idp_check
    CHECK (idp IN ('auth0', 'entra', 'legacy', 'phone'));

CREATE SCHEMA IF NOT EXISTS owner_auth;
REVOKE ALL ON SCHEMA owner_auth FROM PUBLIC;
GRANT USAGE ON SCHEMA owner_auth TO abarpay_app;

CREATE TABLE IF NOT EXISTS owner_auth.credentials (
    phone text PRIMARY KEY,
    user_id uuid NOT NULL UNIQUE REFERENCES public.users(id),
    device_id uuid NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS owner_auth.challenges (
    id uuid PRIMARY KEY,
    device_id uuid NOT NULL,
    phone text,
    public_key text,
    code_mac text,
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used boolean NOT NULL DEFAULT false,
    CHECK ((phone IS NULL AND public_key IS NULL AND code_mac IS NULL)
        OR (phone IS NOT NULL AND public_key IS NOT NULL AND code_mac IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS owner_challenges_created ON owner_auth.challenges (created_at);

CREATE TABLE IF NOT EXISTS owner_auth.mobile_sessions (
    token_hash text PRIMARY KEY,
    device_id uuid NOT NULL REFERENCES owner_auth.credentials(device_id) ON DELETE CASCADE,
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS owner_mobile_session_expiry ON owner_auth.mobile_sessions (expires_at);

GRANT SELECT, INSERT ON owner_auth.credentials TO abarpay_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON owner_auth.challenges TO abarpay_app;
GRANT SELECT, INSERT, DELETE ON owner_auth.mobile_sessions TO abarpay_app;

-- One first store per phone owner. A dropped response must not create a
-- second store when the app retries. Legacy signup keeps its old contract.
CREATE OR REPLACE FUNCTION public.signup_phone_tenant(
    p_sub text, p_owner_name text, p_slug text, p_store_name text, p_timezone text
)
RETURNS TABLE (tenant_id uuid, store_id uuid, user_id uuid)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user uuid;
BEGIN
    SELECT u.id INTO STRICT v_user FROM public.users u
    JOIN owner_auth.credentials c ON c.user_id = u.id
    WHERE u.idp = 'phone' AND u.external_sub = p_sub
    FOR UPDATE OF u;

    RETURN QUERY SELECT m.tenant_id, s.id, m.user_id
    FROM public.memberships m JOIN public.stores s ON s.tenant_id = m.tenant_id
    WHERE m.user_id = v_user AND m.role = 'owner' AND m.active
    ORDER BY m.created_at LIMIT 1;
    IF FOUND THEN
        RETURN;
    END IF;

    UPDATE public.users SET name = p_owner_name WHERE id = v_user;
    RETURN QUERY SELECT * FROM public.signup_tenant(
        'phone', p_sub, '', p_owner_name, p_slug, p_store_name, p_store_name, p_timezone
    );
END;
$$;

REVOKE ALL ON FUNCTION public.signup_phone_tenant(text, text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.signup_phone_tenant(text, text, text, text, text) TO abarpay_app;
