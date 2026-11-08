# Abarpay para Android · base nativa 0.1.1

Cliente Kotlin + Jetpack Compose para Android 8.0 o posterior. Reutiliza **el servidor FastAPI/SQLite en `app/`**, no los prototipos y no ejecuta Python en el teléfono. Es una base de desarrollo, **no una versión productiva ni un sistema multitienda terminado**.

## Qué contiene

- Login y registro visuales **MOCKUP/SIMULADO**, con dueño y empleado de ejemplo, invitación ficticia y botones Google/Apple de demostración. Campos de solo lectura: no se capturan contraseñas, no se crean cuentas, no hay OAuth ni solicitudes de credenciales.
- Inicio, catálogo y carrito, inventario con búsqueda y reporte diario.
- Diseño derivado de los mockups existentes: púrpura `#2A0065`, violeta `#8400FF`, lavanda, tarjetas amplias y navegación inferior. Se conserva el logo original; no se inventan montos o porcentajes para la API.
- Escáner nativo mediante Google Code Scanner y entrada manual de respaldo. No se solicita permiso general de cámara: Google Play Services presenta su lector. Requiere un equipo compatible y puede necesitar descargar su módulo. No está probado todavía en dispositivo físico.
- Dos repositorios: **SIMULADO** local, predeterminado, sin red ni dinero; API de desarrollo configurable.
- La simulación actualiza inventario y reportes al simular una confirmación, una sola vez. Sus datos se reinician al cerrar el proceso. Los códigos `DEMO-1` a `DEMO-5` son ficticios, no EAN reales.
- En la API solo se muestra éxito ante `status=paid` del servidor. La cifra principal del cobro es `chargedCents`; el total comercial se muestra por separado cuando difiere.
- Intento de creación guardado antes de enviar; recuperación de QR y referencia tras cierre; bloqueo de dobles toques y de repetición después de una respuesta incierta. Consulta cada tres segundos solo en primer plano.
- Sin claves de PEY, OpenAI, Google OAuth ni Apple en el APK. Sin publicación ni pagos reales efectuados durante este trabajo.

## Abrir y compilar

1. Abrir la carpeta `android/` en Android Studio. Usar JDK 17 o 21, Android SDK Platform 35 y Build Tools 35.0.0. El SDK requiere aceptar su licencia de Google.
2. Sincronizar Gradle. El wrapper fija Gradle 8.13 y verifica SHA-256 de la distribución; AGP 8.11.1 y Kotlin 2.1.21.
3. Ejecutar sobre un emulador o teléfono:

```sh
./gradlew testDebugUnitTest lintDebug assembleDebug
```

El APK de desarrollo queda en `app/build/outputs/apk/debug/app-debug.apk`; paquete `mx.abarpay.mobile.dev`, Android 8.0/API 26 o superior. Es para probar la simulación, no para operación productiva. Este PR incorpora el código fuente; no incluye APK, claves de firma ni resultados de compilación. Consulta `VERIFICACION.md` para distinguir la evidencia histórica del paquete fuente, las comprobaciones de integración y los pendientes en dispositivo.

## Pruebas de lógica sin SDK

Con JDK 17/21, Python 3 y curl:

```sh
./scripts/test-core.sh
```

Descarga dependencias versionadas de Maven Central a una caché temporal y comprueba SHA-256. Compila dominio/repositorio y ejecuta 17 pruebas JUnit; **no** valida el proyecto Android completo. Este script no acepta licencias SDK ni llama PEY. Cada entorno de compilación Android necesita su SDK y la aceptación correspondiente de su licencia.

## Probar sin servicios externos

La primera apertura muestra **Iniciar sesión** en simulación. Elegir «Soy dueño» o «Soy empleado» y «Entrar en simulación». «Crear cuenta demo» abre el registro del dueño; al confirmar solo se abre la tienda ficticia. Google y Apple muestran un aviso y abren el mismo ejemplo, sin conectar con esos servicios. Desde Ajustes se puede volver al login simulado si no hay carrito ni cobro pendiente. Después, agregar productos, revisar y crear cobro simulado, luego pulsar **Simular confirmación · sin dinero**. Ningún QR de esta modalidad sirve para pagar. Nuevo cobro permite consultar el inventario y el reporte actualizados.

## Conectar el backend de desarrollo

1. Arrancar el FastAPI existente según `../app/README.md`. Para catálogo y reportes no hace falta una clave de PEY; **no configurar una clave real solo para validar UI**.
2. En Ajustes de Android, usar `http://10.0.2.2:8000` desde el emulador. Es la única excepción HTTP y solo existe en debug. En un teléfono físico, utilizar HTTPS con certificado válido; no deshabilitar la verificación TLS.
3. Confirmar que es un servidor propio y controlado. La selección de empleado **no autentica**, y el backend actual carece de permisos. No exponerlo al público ni usar datos reales de clientes.
4. La API no se conecta directamente a PEY desde el móvil. Solo el servidor crea QR y verifica pagos. Generar un QR real requiere una acción explícita; pagar lo hace una persona en su banco.

El transporte usa OkHttp con reintentos de conexión y redirecciones deshabilitados y cuerpo de POST de un solo uso. Se probó contra un servidor falso que corta la conexión tras recibir la petición, devuelve una redirección y responde 503 con `Retry-After: 0`: en cada caso se envió un solo POST. Si se interrumpe la creación, la app conserva el bloqueo incluso al reiniciar. Si no recibió `saleId`, la API actual no permite recuperar el intento: hace falta revisión en el servidor. No borrar datos ni reinstalar para “solucionarlo”. Si se oculta el QR o vence, todavía podría llegar un pago tardío; la app conserva la referencia. La recuperación y cierre seguro de estos casos requieren cambios de backend antes de uso operativo.

## Alcance pendiente

Por instrucción de Carlos, el acceso de esta entrega es únicamente un mockup, también para la consola demo. El alta real del dueño, creación persistente de tienda, invitación real de empleados, aislamiento por tienda, autenticación y consola web protegida están especificados en [`../docs/android-arquitectura.md`](../docs/android-arquitectura.md), **no implementados**. Inventario aquí significa consulta; conteos y ajustes necesitan endpoints nuevos. Tampoco están implementados reconocimiento de fotos, dictado nativo, avisos al dueño en segundo plano, edición de catálogo ni comprobante compartible.

La consola offline separada del paquete de demostración no se incorpora en este PR. No hay sincronización entre sus datos ficticios y los del móvil.

`app/static/` sigue siendo la consola/web de demostración existente y no se modificó. La aplicación móvil deberá ser la herramienta principal de dueños y empleados; la consola será una vista del mismo servicio, no otra base de datos.

## Referencias visuales

- `docs/diseno/pantallas/{inicio,inventario,reportes,cobro-qr-pey,cobro-exitoso}.jpeg`
- `docs/diseno/sistema-diseno/fundamentos-visuales.jpeg`
- `assets/branding/identidadVisual.jpeg` y `logo.jpeg`

No se trasladan a producción el QR, cifras, gráficos de evolución o porcentajes ilustrativos de esas imágenes. La fuente Abarpay Sans no existe como archivo en el repositorio: se usa la tipografía del sistema Android como respaldo.
