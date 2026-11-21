# 2026-11-21 12:55 · android · venta offline integrada (B4)

- **PR / commits:** integración Android (B4) · rama `cdv/plan-produccion-dsh`
- **Qué cambió:** `SaleCoordinator` cablea `AtomicOutbox` en la venta en efectivo: sin conexión finaliza localmente (evento + venta + stock local) y sincroniza al reconectar (`POST /api/sync/events`). `normalizeServer` permite http en debug (teléfono físico vía `adb reverse`). Fix: esquema del outbox separado en `execSQL` por tabla (Robolectric solo ejecutaba la primera). `DomainTest` actualizado.
- **Por qué:** Habilita la venta offline end-to-end (B4).
- **Evidencia:**
  ```text
  ./gradlew testDebugUnitTest: BUILD SUCCESSFUL (154 unit + nuevos SaleCoordinator/OfflineSync)
  ```
- **Riesgos abiertos:** identidad SIMULADO (tenantId=storeId); sincroniza en loadAll (sin botón dedicado); stock local proyectado sin render (el servidor sigue siendo autoritativo).
- **Siguiente:** recorrido B4 con el teléfono físico.
