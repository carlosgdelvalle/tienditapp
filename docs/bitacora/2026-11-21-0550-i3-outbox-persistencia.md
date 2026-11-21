# 2026-11-21 05:50 · i3 · outbox offline y persistencia Android

- **PR / commits:** paquete I3 · rama `cdv/plan-produccion-dsh`
- **Qué cambió:** Contrato de outbox en el servidor (`server/outbox.py` + `server/sync_routes.py`) y persistencia Android cifrada (`AtomicOutbox`, `CryptoBox` AES-256-GCM, `IdempotencyKeys`, `OutboxModels`). Una operación durable = una fila de outbox; dedup por (tenant_id, device_id, event_id); idempotencia exactamente-una-vez; totales siempre recalculados desde el catálogo del servidor, nunca desde el dispositivo.
- **Por qué:** Base de persistencia para ventas offline y recepción de mercancía (M2/M3).
- **Evidencia:**
  ```text
  i3-verifier (deepseek-account/deepseek-v4-pro @ high) = PASS
  server/tests/test_sync.py: 9 passed; suite completa: 192 passed
  gradlew testDebugUnitTest assembleRelease: BUILD SUCCESSFUL (2m12s)
  retry tras ACK perdido no suma dinero ni stock; aislamiento entre tenants verificado
  ```
- **Riesgos abiertos:** la guarda de última unidad (stock negativo) queda para M2 (`decrement_inventory` aún resta sin tope); solo `sale.created` e `inventory.adjust` aplicados; cablear `register(app)` en `main.py` (integración).
- **Siguiente:** integrar rutas en `main.py`; espejo DDL de `outbox_applied`/`outbox_devices` en la migración I1; M2 (última unidad) y M3 (recepción).
