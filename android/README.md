# Abarpay para Android · cliente v1

App Kotlin + Jetpack Compose para Android 8.0 o posterior. Consume **la API v1 descrita en [`../docs/v1-contract.md`](../docs/v1-contract.md)**: una sola tienda, dinero en centavos, cantidades en miliunidades y ventas con efectivo, PEY/CoDi o fiado. No ejecuta Python en el teléfono ni llama a los endpoints de `app/`.

Conserva la identidad visual Abarpay: púrpura `#2A0065`, violeta `#8400FF`, lavanda, tarjetas amplias, logo original y navegación inferior.

## Flujos

- **Acceso mockup**: dueño o empleado de ejemplo (`GET /api/bootstrap`). No hay contraseñas, OAuth ni sesiones; los campos son de solo lectura. En modo API se elige uno de los empleados que devuelve el servidor.
- **Inicio**: tienda, nombre de quien cobra y reporte del día (total, efectivo, PEY, fiado, cobrado y fiado por cobrar).
- **Cobrar**: catálogo con búsqueda y atajos rápidos, entrada de texto, dictado con el reconocimiento de voz de Android (`RecognizerIntent`, sin dependencias en la nube), escáner con Google Code Scanner y código manual. El carrito usa `qtyMilli`; los precios y el total salen del catálogo del servidor y el servidor confirma el importe al crear la venta.
- **Efectivo**: campo de efectivo recibido, cambio calculado y `POST /api/sales` con `paymentMethod:"cash"` y `cashReceivedCents`. Nunca se llama a PEY.
- **PEY/CoDi**: `paymentMethod:"pey"`, QR del servidor, consulta cada 3 s y éxito **solo** con `status:"paid_pey"`. Se muestran `por_conciliar` (se sigue consultando), `failed`, `canceled` y `expired` (un pago tardío todavía puede llegar).
- **Fiado**: cliente existente o alta con nombre/teléfono, `paymentMethod:"fiado"` + `customerId`, saldo del cliente y pantalla de abonos (`POST /api/fiado/customers/{id}/abono`).
- **Barcode**: si `POST /api/barcode/lookup` responde 404 se abre un selector de producto, se enlaza con `POST /api/barcode/link` y se agrega al carrito.
- **Inventario**: búsqueda y ajuste simple de ±1 unidad (1000 milli) con `POST /api/inventory/adjust`; el stock se muestra como `stockMilli` y en unidades legibles (pza / kg).
- **Reportes**: efectivo, PEY, fiado, cobrado, pendiente por conciliar, fiado por cobrar, por empleado, productos más vendidos y stock bajo.
- **Ajustes**: en release el servidor de demo está fijo y es de solo lectura (`BuildConfig.DEMO_SERVER`); la app se conecta sola. Si cambia el túnel, actualizar ese valor y recompilar. El modo simulación queda disponible solo en debug. Sin claves de PEY, OpenAI ni OAuth en el APK.
- **Simulación**: `DemoRepository` replica las formas v1 sin red ni dinero. El QR PEY simulado no es escaneable y la confirmación es explícitamente SIMULADA. Datos ficticios: los códigos `DEMO-1`…`DEMO-12` y los del seed (`7500000000001`…`7500000000005`). La simulación se reinicia al cerrar el proceso.

## Contrato usado

`GET /api/bootstrap`, `GET /api/reports/today`, `POST /api/cart/parse`, `POST /api/barcode/lookup`, `POST /api/barcode/link`, `POST /api/sales`, `GET /api/sales/{id}`, `GET/POST /api/fiado/customers`, `GET /api/fiado/customers/{id}`, `POST /api/fiado/customers/{id}/abono`, `POST /api/inventory/adjust`.

Campos: `qtyMilli`, `unit` (`pieza`/`kg`), `priceCents`, `lineTotalCents`, `paymentMethod` (`cash`/`pey`/`fiado`), `cashReceivedCents`, `changeCents`, `qrId`, `qrImage`, `expiresAt` y los estados `pending`, `paid_cash`, `paid_pey`, `credit`, `por_conciliar`, `failed`, `canceled`, `expired`.

El móvil nunca envía precios ni totales: solo `employeeId`, `productId`, `qtyMilli`, método de pago y, cuando aplica, efectivo recibido o cliente.

## Compilar y probar

Requisitos: JDK 17/21, Android SDK Platform 35 y Build Tools 35.0.0. Gradle 8.13, AGP 8.11.1, Kotlin 2.1.21.

```sh
cd android
./gradlew assembleDebug
./gradlew testDebugUnitTest
```

Si el wrapper no puede descargar Gradle en la red actual, usar una instalación local equivalente:

```sh
cd android
JAVA_HOME=/Library/Java/JavaVirtualMachines/microsoft-21.jdk/Contents/Home \
ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" \
/tmp/gradle-8.13/bin/gradle assembleDebug --no-daemon --console=plain
```

El APK de desarrollo queda en `app/build/outputs/apk/debug/app-debug.apk` (paquete `mx.abarpay.mobile.dev`). Las capturas de las pruebas Robolectric se guardan en `app/build/qa-screenshots/`.

Pruebas cubiertas: dominio (miliunidades, centavos, redondeo, parser demo, estados), repositorio (contrato JSON, 202/502 de PEY, barcode 404, journal, demo), recuperación tras cierre y flujos Compose (efectivo, PEY simulado, fiado + abono, inventario). No hay pagos reales ni llamadas a PEY.

## Límites conocidos

- El acceso sigue siendo un mockup sin autenticación; la API v1 tampoco autentica.
- No se usa `POST /api/sales/{id}/cancel` ni `GET /api/health` desde la app.
- Si una creación de venta queda incierta (corte de red sin respuesta), la app conserva el bloqueo y la referencia; no reintenta a ciegas. Resolverlo requiere revisar el servidor.
- El carrito y el perfil viven en el ViewModel; solo la venta en curso se guarda en preferencias.
- Sin integración de impresión, avisos en segundo plano, edición de catálogo ni consola web.
