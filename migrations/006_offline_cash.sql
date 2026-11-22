-- Canonical price snapshots for phone tills. Each lease is issued for one
-- verified device and tenant. Sync only reads snapshots from this ledger.
CREATE TABLE IF NOT EXISTS public.cash_offline_leases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id),
    user_id uuid NOT NULL,
    device_id uuid NOT NULL REFERENCES owner_auth.credentials(device_id),
    issued_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    items jsonb NOT NULL,
    FOREIGN KEY (tenant_id, user_id) REFERENCES public.memberships(tenant_id, user_id)
);

CREATE INDEX IF NOT EXISTS cash_offline_leases_device
    ON public.cash_offline_leases (tenant_id, device_id, issued_at DESC);

ALTER TABLE public.cash_offline_leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cash_offline_leases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cash_offline_leases_tenant_isolation ON public.cash_offline_leases;
CREATE POLICY cash_offline_leases_tenant_isolation ON public.cash_offline_leases
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
           AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
                AND user_id = NULLIF(current_setting('app.user_id', true), '')::uuid);
REVOKE ALL ON public.cash_offline_leases FROM PUBLIC, abarpay_app;
GRANT SELECT, INSERT ON public.cash_offline_leases TO abarpay_app;
