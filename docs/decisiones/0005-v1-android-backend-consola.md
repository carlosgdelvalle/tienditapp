# 0005 · La entrega v1 es la app Android con backend y consola nuevos

- **Estado:** vigente para la entrega del 8-nov-2026
- **Fecha:** 2026-11-08
- **Contexto:** la app Android es la distribución elegida (un APK), y el MVP anterior en `app/` y los prototipos quedan como referencia. El backend viejo no tiene efectivo, fiado, movimientos de inventario ni una consola de dueño, y su conexión SQLite compartida no es apta para varios teléfonos. La app Android necesita una API nueva y una consola administrativa separada.
- **Decisión:** construir la entrega v1 con tres piezas:
  1. `server/`: FastAPI + SQLite nuevo, conexión por request, WAL, efectivo, PEY/CoDi, fiado, inventario con movimientos, reportes, webhook firmado y consola.
  2. `android/`: cliente Kotlin/Compose v1 que consume ese contrato; conserva la identidad visual y los flujos de cobro, texto, voz, código de barras, efectivo, PEY, fiado, inventario y reportes.
  3. `/console`: vista de administración para el dueño, con PIN de demostración y refresco periódico; no es autenticación de producción.
- **Opciones descartadas:** seguir iterando `app/` o el prototipo v0.4; usar el frontend viejo como consola; autenticación real, multi-tienda y offline para esta entrega; una consola en otro framework con build separado.
- **Consecuencias:** el acceso es mockup y la consola usa PIN compartido; una sola tienda; el túnel HTTPS es temporal; el keystore de release vive fuera del repositorio; el pago real de $0.01 lo hace una persona. La app vieja y los prototipos no deben presentarse como la entrega.
- **Cómo se verifica:** 57 pruebas del backend con `FakePey`; 46 pruebas Android y build release firmado; instalación y ejecución en SM-A165M; venta en efectivo, fiado, abono, inventario y consola; pago real de $0.01 confirmado por conciliación con PEY (tx `01M6XZTYHZC3H4F1FZRYGKGF75`, `PAID`). El webhook real de PEY llegó con 400 `invalid_payload` porque manda los campos en la raíz; ya se acepta ese formato y el replay exacto devolvió 200, pero el retry del portal queda pendiente.
