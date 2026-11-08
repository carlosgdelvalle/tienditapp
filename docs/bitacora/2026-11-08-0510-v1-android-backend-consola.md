# 2026-11-08 05:10 · v1 · Android, backend y consola nuevos

- **PR / commits:** rama `feat/abarpay-v1`, commits `eac9b6b` (README), `0a870ca` (contrato), `2c7ffd6` (backend), `3960908` (QR), `ff9a6e0` (Android), `fe38505` (docs) y siguientes.
- **Qué cambió:** se creó `server/` con FastAPI + SQLite, ventas en efectivo, PEY/CoDi, fiado, abonos, inventario con movimientos, reportes, webhook firmado y consola `/console`. La app Android se refactorizó al contrato v1 y se firmó un APK release 1.0.0. Se actualizó el README y se documentaron los pendientes.
- **Por qué:** la entrega es el APK Android; el MVP y los prototipos quedan como referencia. Ver [decisión 0005](../decisiones/0005-v1-android-backend-consola.md).
- **Evidencia:**
  ```text
  pytest server/tests -q                          → 57 passed
  ./gradle testDebugUnitTest                      → 46 tests, 0 failures
  apksigner verify app-release.apk                → Verifies, v2
  adb install -r app-release.apk                  → Success
  SM-A165M: efectivo, fiado, abono, inventario y consola verificados
  PEY: pago real $0.01 PAID, tx 01M6XZTYHZC3H4F1FZRYGKGF75, conciliado por polling
  ```
- **Riesgos abiertos:** el webhook real de PEY llegó con 400 `invalid_payload` por su formato plano; ya se acepta ese formato y el replay exacto devolvió 200, pero el retry del portal queda pendiente. Cámara y voz no se probaron con hardware real; el túnel es temporal; el acceso es mockup y la consola usa PIN demo; el reporte incluye pendientes en el total (ver [estado](../pendientes-manana.md)).
- **Siguiente:** que una persona pague un QR nuevo de $0.01, verificar `paid_pey`, webhook, consola y actualizar la evidencia del README.
