# Evidencia de verificación

## Integración del código fuente · 8 de noviembre de 2026 UTC

Se importa la carpeta Android de la versión 3 del paquete fuente entregado, sobre `main` en `ecedb441347d509f7d1538b7943cc54830da0337`. No se importan APK, consola web demo, claves, configuración local ni salidas de compilación. La integración conserva el código Kotlin, recursos, Gradle y pruebas del paquete; solo adapta documentación y exclusiones de archivos generados.

La evidencia siguiente corresponde al trabajo original del 7 de noviembre. No equivale a haber repetido la compilación completa en el entorno de este PR. Las comprobaciones de integración y sus límites se registran en `../docs/bitacora/2026-11-08-0152-android-fuente-pr.md`.

## Evidencia histórica del paquete fuente · 7 de noviembre de 2026

Base de repositorio: `ee5cb67a650f2bcf068f6c3756f5421134c4db8b`.
Rama local original: `feat/android-native-base`. En esa entrega todavía no había push ni PR; tampoco despliegue ni pagos reales.

## Instalación y licencia

Android SDK Platform 35 y Build Tools 35.0.0 instalados después de la autorización explícita del propietario para aceptar el [Android SDK License Agreement](https://developer.android.com/studio/terms). La licencia fue aceptada. Gradle instaló también Platform-Tools como dependencia del entorno. Se utilizó OpenJDK/Temurin 21.0.13 verificado con el SHA-256 publicado por Adoptium y Gradle 8.13 con su distribución y wrapper verificados. No se creó cuenta ni hubo pago.

## Comprobaciones aprobadas

- **Compilación Android completa:** tareas Gradle `testDebugUnitTest lintDebug assembleDebug`, `BUILD SUCCESSFUL`. Kotlin, Compose, recursos, manifiesto, dex y empaquetado compilados.
- **27 pruebas locales Android/JVM:** 8 de dominio, 9 de repositorio/transporte, 3 de recuperación de sesión con Robolectric y 7 de interfaz Compose con Robolectric/API 35. Cero fallos.
- **Verificador sin SDK:** `cd android && ./scripts/test-core.sh`, `OK (17 tests)`. Es el subconjunto de dominio/repositorio anterior, no 17 pruebas adicionales.
- **Servidor original:** `./scripts/verificar.sh`, `16 passed`, `VERIFICAR: OK`. Proveedor falso; backend y `apply_payment` no se modificaron.
- **Lint:** sin errores; quedan avisos de versiones más nuevas/target y sugerencias de estilo KTX. No se ocultaron con una baseline. Se conservó el SDK 35 autorizado.
- **APK debug:** generado y comprobado con `apksigner verify --verbose`; firma APK v2 válida. Paquete `mx.abarpay.mobile.dev`, versión `0.1.1-dev`, versionCode 2, mínimo API 26/Android 8.0, target/compile API 35. La firma es de desarrollo, no de publicación.
- **Diseño:** se inspeccionaron los mockups antes de implementar y se revisaron imágenes del login, registro, inicio y confirmación renderizadas por Robolectric a 390 × 844. Son capturas del entorno de pruebas, no de un teléfono físico. Logo original conservado sin cambios de bytes, en recurso `drawable-nodpi`.
- **Seguridad básica de empaquetado:** sin claves de PEY/OpenAI/OAuth/Apple, copias de seguridad y transferencia de datos deshabilitadas; HTTPS salvo el emulador debug `10.0.2.2`; escaneo mínimo de secretos sin hallazgos (gitleaks no instalado).

## Qué se ejercitó

Cantidades, centavos, productos desconocidos, configuración HTTPS, estados de pago, expiración visual, payload sin precios/estado enviados por el móvil, campos opcionales y persistencia. El journal corrupto, el intento interrumpido y la venta recuperada sin dirección de servidor permanecen bloqueados, sin consultar el repositorio simulado como si fuera real.

Se comprobó con MockWebServer que la creación envía **un solo POST** si el servidor recibe la petición y corta la conexión, si devuelve 307 o si responde 503 con `Retry-After: 0`. El cliente desactiva retries/redirecciones y usa un cuerpo de un solo uso. No se llamó a PEY.

Los flujos Compose probaron login de dueño → carrito → confirmación explícita → pago SIMULADO → nuevo cobro → reporte actualizado; empleado e invitación ficticia → inventario → búsqueda sin resultados → Atrás; registro → abandono → confirmación local → Inicio; Google/Apple locales y retorno al login; bloqueo de cambio de perfil con carrito y con cobro. Las pruebas de recuperación visual comprueban que una venta pending/expired o un intento interrumpido prevalecen sobre el login y conservan el journal. La simulación actualiza inventario y reporte una sola vez.

## Pendiente y límites

- Sin instalación ni prueba en teléfono físico o emulador completo. Cámara/Google Code Scanner, descarga de su módulo, Google Play Services, permisos y hardware reales están pendientes.
- Robolectric no sustituye comprobar accesibilidad/TalkBack, fuentes grandes, distintos fabricantes, comportamiento en segundo plano ni muerte real del proceso en un teléfono.
- No se verificó un cobro con servidor/PEY reales ni se movió dinero. La primera apertura del APK usa **SIMULADO**. Usarlo para revisar esa modalidad, no para una caja productiva.
- El login y registro son mockups por petición expresa, no autenticación. Alta persistente del dueño/tienda, invitación real de empleados, aislamiento multitienda, consola protegida y conteo/ajuste de inventario no existen todavía. No se implementó ni se solicitó OAuth. La API actual no autentica.
- En la API de desarrollo, intentos inciertos y cobros vencidos conservan bloqueo. Hace falta recuperación backend y lista durable de pendientes para continuar vendiendo sin perder referencias. No borrar datos ni reinstalar para resolver un cobro.
- El borrador de carrito/perfil sobrevive rotación mediante ViewModel, pero no muerte del proceso. Solo intento/venta real y QR son durables. La simulación se reinicia al cerrar el proceso.

## Siguiente validación

Instalar el APK de desarrollo en un Android compatible y comprobar primero el flujo SIMULADO, cámara, cancelación del escáner, entrada manual, fuente grande, Atrás y reanudación. Después probar un servidor aislado con proveedor falso. Identidad, aislamiento e idempotencia/recuperación deben llegar antes de operación real. Un pago real solo lo realiza una persona autorizada.

## Identidad del APK entregado

`Abarpay-Android-desarrollo-0.1.apk`, 18867262 bytes.

SHA-256: `b0e608382122f89912205bbb3e13ad1799a40ad134dd080c4809c55bdf1fe099`.
