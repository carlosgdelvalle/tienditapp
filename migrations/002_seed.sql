-- Abarpay tenancy seed: the two frozen test tenants.
-- Contract fixture: docs/produccion/contracts/tenancy.md
--   "Tienda Aurora" (tenant A) and "Tienda Beta" (tenant B), one store each.
--
-- Clean seed: tenants + stores only. NO demo data (no products, sales,
-- employees, or memberships) is inserted here. The SQLite demo store is
-- migrated separately by scripts/migrate_sqlite_to_pg.py into its own tenant.
--
-- Idempotent: ON CONFLICT DO NOTHING keyed on tenants.slug and
-- stores.tenant_id, so re-running never duplicates tenants or stores.

INSERT INTO tenants (slug, name, legal_name, country, timezone, status)
VALUES
    ('tienda-aurora', 'Tienda Aurora', 'Tienda Aurora S.A. de C.V.', 'MX', 'America/Mexico_City', 'active'),
    ('tienda-beta',   'Tienda Beta',   'Tienda Beta S.A. de C.V.',   'MX', 'America/Mexico_City', 'active')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO stores (tenant_id, name)
SELECT id, 'Tienda Aurora'
FROM tenants
WHERE slug = 'tienda-aurora'
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO stores (tenant_id, name)
SELECT id, 'Tienda Beta'
FROM tenants
WHERE slug = 'tienda-beta'
ON CONFLICT (tenant_id) DO NOTHING;
