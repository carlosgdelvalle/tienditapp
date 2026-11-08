# Estado y decisiones · Abarpay v1

Actualizado: 2026-11-08 10:38 CDMX.

Este archivo resume el pago real ya verificado, la evidencia y las decisiones que conviene confirmar antes de la entrega.

## Pago real verificado

- Venta: **sale_fed4e2ffe9684050b4d6**.
- QR PEY: **352712e8e3**.
- Transacción PEY: **01M6XZTYHZC3H4F1FZRYGKGF75**, estado **PAID**, **0.01 MXN**.
- Fecha PEY: 8-nov-2026, 10:28:33 CDMX; el servidor la aplicó a las 10:28:34.
- Origen de la confirmación: **reconciliación/consulta** con PEY. El webhook real **sí llegó**, pero respondió 400 `invalid_payload` porque PEY manda `codiQrId`, `transactionId` y `amount` en la raíz, no en `data`. Ya se corrigió y el replay exacto devolvió 200 `duplicate_transaction`; falta que el portal reintente el evento.
- Consola: 3 ventas, PEY comercial $36.00, efectivo $18.00, fiado $18.00, fiado por cobrar $13.00, pendientes 0.
- No hace falta hacer otro pago para la demo; este ya quedó en la base y en la consola.

## Cómo verificar el pago

    ./scripts/check_v1.sh sale_fed4e2ffe9684050b4d6

También se puede revisar a mano con curl: /api/sales/sale_fed4e2ffe9684050b4d6 y /api/console/summary con el header X-Owner-Pin: 1234.

La venta muestra status paid_pey, txId y paidAt; la consola debe tener PENDIENTES 0. Si en el futuro un pago llega después de cancelar/vencer, el servidor lo registra con applied=0 y no reabre la venta.

## Estado actual

- Backend v1 nuevo en **server/**: FastAPI + SQLite, 57 pruebas.
- Android v1 release firmado: paquete **mx.abarpay.mobile**, versión **1.0.0**, versionCode **3**.
- APK de release: **android/app/build/outputs/apk/release/app-release.apk** (34 MB); SHA-256 **da8b14c6a85b66093b06a5d3b789bdf34fe05022a409cae60f36252737937dfc**. La app release trae el servidor de demo fijo, de solo lectura y se conecta sola; el escáner continuo requiere permiso de cámara.
- Consola del dueño: **/console**, PIN demo **1234**.
- Efectivo, fiado, abono, ajuste de inventario y consola probados en el dispositivo/API.
- PEY: pago real confirmado por conciliación; tx 01M6XZTYHZC3H4F1FZRYGKGF75, PAID $0.01 a las 10:28:34. El webhook real llegó con 400 por payload plano; corregido; retry del portal pendiente.
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

- Backend: 57 pruebas aprobadas con FakePey; smoke de salud, bootstrap, efectivo, consola y webhook firmado.
- Android: build release firmado; 46 pruebas Gradle y 35 de núcleo en el reporte del agente; instalación y ejecución en SM-A165M.
- Dispositivo: venta en efectivo, venta fiada, abono, ajuste de inventario y consola verificados.
- PEY: pago real confirmado por conciliación; tx 01M6XZTYHZC3H4F1FZRYGKGF75, PAID $0.01 a las 10:28:34; webhook real llegó con 400 por payload plano, corregido; retry del portal pendiente.
