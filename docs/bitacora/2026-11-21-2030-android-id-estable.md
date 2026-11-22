# 2026-11-21 20:30 · android · id estable y recibo con precio emitido

- **PR / commits:** rama `cdv/recupera-caja`, `a291a11`
- **Qué cambió:** El cobro en efectivo genera un ULID estable antes del intento en línea, lo envía como `Idempotency-Key` en `POST /api/sales` y lo reutiliza en el evento del diario offline si se pierde la respuesta. El recibo local sin conexión calcula el total con la instantánea de precios emitida (no con el bootstrap), para coincidir con el total que recalcula el servidor.
- **Por qué:** Cerrar en el dispositivo la deduplicación entre el cobro en línea y el diario offline, y que el recibo muestre el mismo precio que queda en el libro.
- **Evidencia:**
  ```text
  JAVA_HOME=/Library/Java/JavaVirtualMachines/microsoft-21.jdk/Contents/Home \
  ANDROID_HOME=$HOME/Library/Android/sdk ./gradlew :app:testDebugUnitTest
  BUILD SUCCESSFUL in 2m 12s
  ```
- **Riesgos abiertos:** Verificación en teléfono físico pendiente (propagación del id y precio emitido en el recibo real).
- **Siguiente:** Instalar el APK de depuración y recorrer B4 en el teléfono; B8 (APK firmado con operaciones pendientes).

