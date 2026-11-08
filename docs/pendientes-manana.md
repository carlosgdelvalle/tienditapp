# Pendientes para la mañana · Abarpay v1

Actualizado: 2026-11-08 05:05 CDMX.

Este archivo resume lo que quedó hecho, lo único que está bloqueado por una persona y las decisiones que conviene confirmar antes de la entrega.

## Lo único bloqueado: el pago real de $0.01

El agente no puede pagar; **una persona debe escanear y pagar**. El QR que estaba en el teléfono (sale_37fbb44419dd47578f18, QR 355b286b39) venció y se canceló; además se retiró el registro de prueba de la consola. **No hay un QR activo en este momento.** Hay que crear uno nuevo desde la app. Para cerrar la evidencia:

1. Verificar que el backend y el túnel siguen vivos (ver comandos abajo).
2. En el teléfono SM-A165M, abrir **Abarpay** (release, paquete mx.abarpay.mobile).
3. Elegir **Lupita**, **Cobrar**, agregar un producto, elegir **PEY / CoDi**, **Generar QR PEY**.
4. Escanear el QR con la app bancaria y pagar **$0.01 MXN**.
5. Dejar la app abierta; consulta el estado cada 3 s. También puede usar **Consultar estado**.
6. Avisar al agente o revisar la consola. La venta debe pasar a paid_pey, con folio PEY y sin descontar inventario dos veces.

Si el backend o el túnel se reinician, hay que repetir el QR; el portal de PEY no cambia si el túnel sigue siendo el mismo.

## Cómo verificar el pago

    ./scripts/check_v1.sh <saleId>

También se puede revisar a mano con curl: /api/sales/<saleId> y /api/console/summary con el header X-Owner-Pin: 1234.

La venta debe mostrar status paid_pey, txId y paidAt; la consola debe bajar PENDIENTES a 0 y sumar el monto en PEY. Si el pago llega después de cancelar/vencer, el servidor lo registra con applied=0 y no reabre la venta.

## Estado actual

- Backend v1 nuevo en **server/**: FastAPI + SQLite, 54 pruebas.
- Android v1 release firmado: paquete **mx.abarpay.mobile**, versión **1.0.0**, versionCode **3**.
- APK de release: **android/app/build/outputs/apk/release/app-release.apk** (12 MB); SHA-256 **6bc70411c953faf845674e3a60347d2b13bbab39e02eee810a74bdf2413ff17d**.
- Consola del dueño: **/console**, PIN demo **1234**.
- Efectivo, fiado, abono, ajuste de inventario y consola probados en el dispositivo/API.
- PEY: el QR real se creó y se mostró en el teléfono; el pago real sigue pendiente.
- El backend y el túnel están corriendo en esta sesión.

## Comandos para levantarlo

Desde la raíz del repositorio:

    ABARPAY_LOAD_DOTENV=1 \
    ABARPAY_DB=/Users/carlos/repos/tienditapp/server/data/abarpay.db \
    MODO_DEMO=true \
    /tmp/abar-venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000

En otra terminal, túnel público:

    cloudflared tunnel --url http://127.0.0.1:8000

Anotar la URL **https://<algo>.trycloudflare.com**; si cambia, actualizar:

- La dirección del servidor en Ajustes de la app Android.
- La URL del webhook en el portal de PEY: **https://<algo>.trycloudflare.com/webhooks/pey**.

Consola: **https://<algo>.trycloudflare.com/console** (PIN 1234).

## Firma del APK

- Keystore: **~/.config/tienditapp/abarpay-release.jks**
- Propiedades: **~/.config/tienditapp/release.properties** (permisos 600)
- La contraseña **no** está en el repositorio ni en este documento.
- El build.gradle.kts lee ese archivo; si no existe, el build de release queda sin firma.
- Decisión sugerida: conservar este keystore para la demo; si más adelante se publica, crear uno de producción y respaldarlo.

## Decisiones que necesito de ti (puedes contestar por número)

1. **PIN de la consola**: dejar **1234** para la demo o cambiarlo por otro. Default actual: 1234.
2. **Reporte “Ventas de hoy”**: hoy suma las ventas registradas, incluyendo una venta PEY pendiente y una fiada; “Cobrado” solo suma efectivo + PEY pagado. ¿Prefieres que “Ventas de hoy” excluya pendientes y las muestre solo en la tarjeta **Pendientes**? Default actual: incluir todas las ventas no canceladas; pendientes se muestran aparte.
3. **Túnel**: dejar el quick tunnel actual (efímero) para la demo o usar un túnel con nombre/URL estable. Default actual: quick tunnel; si se reinicia cambia la URL y hay que actualizarla en PEY.
4. **Autenticación**: confirmar que para el hackatón el login sigue siendo **mockup** y la consola usa PIN demo; sin cuentas reales. Default actual: mockup.
5. **Alcance de efectivo**: hoy se registra la venta y el cambio, pero no hay corte de caja por turno ni arqueo. ¿Es suficiente para la demo? Default actual: sí; corte/arqueo queda en roadmap.
6. **Barcode y voz en teléfono físico**: falta probar cámara real y dictado con micrófono. ¿Tienes un código de barras físico y un momento para probarlo? Default actual: flujo de código manual y enlace de códigos implementado; cámara usa Google Code Scanner.
7. **Distribución del APK**: ¿se comparte el archivo por correo/AirDrop o se sube a un release de GitHub? Default actual: APK local firmado; no se ha subido a ningún lado.
8. **Después del hackatón**: cuentas reales, passkeys, multi-tienda, offline y datos para proveedores quedan fuera de esta entrega. Confirmar que se presentan como roadmap, no como hechos.

## Limitaciones conocidas

- La autenticación es mockup; la consola usa PIN compartido, no sesiones firmadas.
- Una sola tienda; no hay aislamiento multi-tienda.
- El quick tunnel es temporal y expone la app sin auth; no dejarlo público más de lo necesario.
- Si la creación del QR PEY hace timeout antes de recibir un qrId, la venta queda por_conciliar con saleId pero sin llave para consultar; requiere revisión manual con PEY.
- No hay corte de caja/arqueo, reembolsos ni edición de catálogo.
- La voz usa el reconocimiento de Android; la cámara usa Google Code Scanner. Ambas dependen del teléfono y de los servicios de Google.
- El reporte incluye ventas pendientes en el total; ver decisión 2.
- El APK release está firmado con una clave de demo local, no de producción.

## Evidencia que ya existe

- Backend: 54 pruebas aprobadas con FakePey; smoke de salud, bootstrap, efectivo, consola y webhook firmado.
- Android: build release firmado; 46 pruebas Gradle y 35 de núcleo en el reporte del agente; instalación y ejecución en SM-A165M.
- Dispositivo: venta en efectivo, venta fiada, abono, ajuste de inventario y consola verificados.
- PEY: QR real creado y mostrado; pendiente el pago humano.
