# 2026-11-21 06:30 · integración · wiring del servidor

- **PR / commits:** integración · rama `cdv/plan-produccion-dsh`
- **Qué cambió:** Se cablean `auth_routes` y `sync_routes` en `main.py` (`register(app)`); se añade `outbox_devices` al esquema PG (binding tenant↔device, RLS); se escribe `identity_pg.py` (adaptador `IdentityStore` a PostgreSQL vía `db_pg` + funciones SECURITY DEFINER); 2 tests de humo.
- **Por qué:** Deja el servidor integrado con los módulos I1/I2/I3 antes de M1/M2.
- **Evidencia:**
  ```text
  suite completa: 223 passed, 0 failed
  smoke test: app arranca y responde POST /api/auth/challenge y POST /api/sync/lease (200)
  outbox_devices: UNIQUE (tenant_id, device_id) + RLS verificados
  ```
- **Riesgos abiertos:** camino PG de identidad incompleto (faltan tablas devices/challenges/sessions y funciones resolve/create_user, lectura de invites/memberships; `claim_invite` sin `tenant_id`). Se resolverá en M1.
- **Siguiente:** M1 (onboarding/CLABE) y M2 (checkout/cierre), con la extensión de esquema de identidad.
