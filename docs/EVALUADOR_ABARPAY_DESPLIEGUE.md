# Abarpay / Tiendita Inteligente — entrega a evaluador
Estado: preparación técnica en rama; despliegue y pago real PENDIENTES.

## Código y diseño
Repositorio: https://github.com/carlosgdelvalle/tienditapp
Rama: feature/abarpay-evaluator-deploy-v04
Versión: prototypes/tiendita-inteligente-pey-v0.4/
Branding: assets/branding/logo.jpeg, usado por /branding/logo.jpeg en las vistas / y /empleado.
No se modificó la aplicación principal del equipo en app/, ni el código local de la laptop.

## Despliegue propuesto
Proveedor candidato: Railway (conexión a la cuenta todavía pendiente).
El servicio se despliega desde la raíz del repositorio, usando railway.json y Dockerfile.evaluator.
Configurar un volumen persistente montado en /data. La base de datos usa TIENDITA_DB=/data/tiendita.db.
Configurar una sola réplica y un worker. Verificar persistencia tras reinicio y despliegue.
Generar una URL HTTPS real y verificar /api/health, /, /empleado y /branding/logo.jpeg.

## Variables privadas, nunca compartir su contenido
PEY_API_KEY
PEY_WEBHOOK_SECRET
TIENDITA_OPERATOR_TOKEN (20 o más caracteres)
TIENDITA_SESSION_SECRET (32 o más caracteres)
TIENDITA_EMPLOYEE_PIN_ANA, _LUIS, _MARIA
TIENDITA_PUBLIC_URL=https://URL_REAL
PEY_ENABLE_LIVE=1
PEY_CONFIRM_REAL_MONEY=YES_I_AUTHORIZE
TIENDITA_EVALUATOR_DEMO=1
TIENDITA_TEST_ONE_CENT=1
TIENDITA_DB=/data/tiendita.db

La rama de evaluación bloquea PEY LIVE si TIENDITA_EVALUATOR_DEMO=1 y no se ha establecido el importe fijo de un centavo. En PEY se debe registrar https://URL_REAL/webhooks/pey y configurar el secreto firmado distinto de la clave API. Toda credencial que se haya mostrado en capturas o chats debe rotarse antes del lanzamiento público.

## Pruebas de aceptación
1. Páginas del dueño y empleado con branding, en escritorio y teléfono.
2. Inicio de sesión de empleado mediante PIN; APIs del dueño no accesibles como empleado.
3. Venta desde catálogo, QR PEY real de exactamente MXN $0.01.
4. Persona del equipo autoriza pago desde aplicación bancaria CoDi.
5. Verificación firmada más lectura PEY independiente en estado PAID.
6. Venta PAGADA_PRUEBA e inventario descontado una sola vez.
7. Webhook duplicado, firma inválida, monto incorrecto y cobro incierto tratados sin falsa confirmación.
8. Reinicio con transacción e inventario persistentes.
9. Protección de abuso y acceso de evaluación acotado.

## Límites actuales
Los 15 tests anteriores del prototipo v0.4 son simulados; no acreditan un pago real.
La conciliación automática integral si se pierde definitivamente el webhook y los límites de tasa públicos no están completados ni validados.
Sin cuenta Railway conectada, volumen comprobado, configuración privada y pruebas E2E no existe URL funcional ni cobro real habilitado.
No fusionar a main ni registrar Webhook/credenciales reales sin validación.

## Actualización de pagos reales — recuperación y controles (7 nov 2026)
- En modo evaluador, solamente QR por **$0.01 MXN**. Push y abonos PEY en fiados se bloquean (HTTP 403), y la interfaz del dueño los oculta.
- El backend limita a 20 intentos QR reales por hora para esta demo; las credenciales del empleado bloquean nuevos intentos tras cinco PIN incorrectos por IP en 15 minutos. Este umbral es acotado y **no sustituye** un WAF/rate limit en el perímetro.
- Si el webhook firmado no llega, la consulta autenticada `GET /transaction/codi/qr/{qrId}` permite detectar transacciones del QR. Para aplicar una venta se exige una sola transacción `PAID` corroborada mediante `GET /transaction/{id}`, con monto exacto, moneda MXN, método CoDi, tipo QR, ID de QR y metadatos de venta coherentes. Ante error, más de una transacción o datos ambiguos, queda PENDIENTE para revisión.
- El estado y origen de la confirmación se registran como `PEY_AUTHENTICATED_QR_API` o `PEY_SIGNED_WEBHOOK_AND_API`. La operación del inventario es transaccional y no se ejecuta una segunda vez ante confirmación duplicada.
- El panel del dueño y la vista de empleado consultan el estado para mostrar el pago confirmado; ninguna pantalla de QR por sí sola indica que ya se pagó.
- Esta vía de recuperación está implementada para **ventas QR**; CoDi Push y abonos siguen fuera del demo público.
- La recuperación y los controles han sido implementados con simulaciones; siguen pendientes la aceptación bancaria real, el volumen persistente, seguridad pública complementaria, accesibilidad visual, portal PEY y URL HTTPS.
