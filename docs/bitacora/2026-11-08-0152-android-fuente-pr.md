# 2026-11-08 01:52 CDMX · Android · incorporación de la base nativa

- **PR / commits:** rama `feat/android-native-base-pr`, contra `main` en `ecedb441347d509f7d1538b7943cc54830da0337`.
- **Qué cambió:** incorpora el código fuente Android 0.1.1 previamente entregado: Kotlin/Compose, acceso MOCKUP/SIMULADO de dueño y empleado, catálogo, carrito, inventario, reporte y cliente de la API existente. Incluye wrapper de Gradle, pruebas y documentación. No incluye APK, consola web demo, credenciales, claves de firma ni resultados de compilación.
- **Por qué:** permitir revisar y continuar el proyecto móvil desde el repositorio, por solicitud de Carlos. Conserva FastAPI/SQLite y las reglas de pagos de las decisiones [0001](../decisiones/0001-stack.md) y [0003](../decisiones/0003-credenciales-y-pagos.md). No modifica `app/`, prototipos, decisiones, CI ni `HANDOFF.md`.
- **Evidencia de esta integración (8-nov-2026 UTC):**
  ```text
  cd android && ./scripts/test-core.sh
  OK (17 tests)

  ./scripts/verificar.sh
  Sin hallazgos (patrones mínimos; gitleaks no instalado).
  16 passed
  VERIFICAR: OK
  ```
  El JAR del wrapper coincide con el SHA-256 oficial de Gradle 8.13 (`81a82aaea5abcc8ff68b3dfcb58b3c3c429378efd98e7433460610fecd7ae45f`). Los tests Android de dominio/transporte usan datos y servidores falsos; no se llamó a PEY. La revisión estática contrastó los contratos con `app/`, comprobó que los accesos fueran simulados y no encontró secretos evidentes. Los archivos Kotlin, recursos, configuración Gradle y pruebas conservan los bytes del paquete fuente; se adaptan únicamente documentación y exclusiones de archivos generados.
- **Riesgos abiertos:** la compilación completa `testDebugUnitTest lintDebug assembleDebug` no se repitió: Gradle falló al descargar su distribución con `Network is unreachable` y este entorno no tiene Android SDK. El subconjunto JVM no valida Compose, empaquetado ni lint. La evidencia previa de 27 pruebas y APK está identificada como histórica en [`android/VERIFICACION.md`](../../android/VERIFICACION.md). Sin prueba en dispositivo físico ni pago real. La CI existente verifica secretos y backend, no compila Android. El login no autentica y el backend no tiene aislamiento de tiendas; no es una caja productiva.
- **Siguiente:** revisar el PR en borrador, repetir las tareas Gradle en Android Studio con JDK 17/21 y SDK 35, y probar primero el flujo SIMULADO en un dispositivo compatible. No fusionar ni desplegar sin autorización.
