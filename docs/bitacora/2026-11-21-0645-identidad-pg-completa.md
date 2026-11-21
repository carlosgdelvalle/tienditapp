# 2026-11-21 06:45 · integración · camino PG de identidad completo

- **PR / commits:** integración · rama `cdv/plan-produccion-dsh`
- **Qué cambió:** Tablas `devices`/`challenges`/`sessions` + funciones SECURITY DEFINER (`resolve_user`, `create_user`, `list_tenant_members`, `get_invite_by_hash`, y puentes save/get/transition/revoke). `lookup_invite` añadido al protocolo `IdentityStore`. `identity_pg.py` completo (cero `NotImplementedError`). `outbox_devices` en la compuerta RLS.
- **Por qué:** Completa el camino de identidad PostgreSQL para M1 (onboarding).
- **Evidencia:**
  ```text
  suite completa: 229 passed, 0 failed (6 tests nuevos en test_identity_pg.py)
  grep NotImplementedError en identity_pg.py: 0
  tablas devices/challenges/sessions presentes en PG
  ```
- **Riesgos abiertos:** devices/challenges/sessions con `tenant_id` NULL hasta aprobar reto (acceso vía SECURITY DEFINER); `claim_invite` retorna `""` en conflicto (funcionalmente correcto); `accepted_at` usa `now()` de BD.
- **Siguiente:** M1 (onboarding/CLABE) y M2 (checkout/cierre).
