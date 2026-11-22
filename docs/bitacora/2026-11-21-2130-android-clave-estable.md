# 2026-11-21 · android · clave estable y recuperación del recibo sin conexión

- **PR / commits:** rama `cdv/recupera-caja`, `47d0aa8` y `b513cbb`
- **Qué cambió:** La clave del cobro en efectivo se guarda de forma duradera antes de despachar. La recuperación conserva la misma clave a través de reinicios y servidores, no duplica un evento ya reconocido y solo limpia la intención pendiente tras persistir el recibo. El id visible del recibo usa el folio determinista del servidor.
- **Por qué:** Cerrar el contrato de una operación y una clave entre el cobro en línea y el diario offline, incluidos los cierres de la app.
- **Evidencia:**
  ```text
  JAVA_HOME=/Library/Java/JavaVirtualMachines/microsoft-21.jdk/Contents/Home \
  ANDROID_HOME=$HOME/Library/Android/sdk ./gradlew :app:testDebugUnitTest
  BUILD SUCCESSFUL
  ```
- **Riesgos abiertos:** Verificación en teléfono físico pendiente.
- **Siguiente:** Recorrer B4 en el teléfono; B8 (APK firmado con operaciones pendientes).

