# Abarpay

**Cobros verificados, ventas e inventario para la tiendita de barrio, desde el teléfono.**

Hackatón DevDay Exchange Community · Ciudad de México · 7-8 de noviembre de 2026
Construido con la API de pey (CoDi) y la API de OpenAI. Comercio de demostración: **Tiendita de la Esquina** (ficticio).

---

## El problema

La tiendita de barrio cobra en efectivo. Cuando un cliente paga por transferencia, el tendero tiene que sacar el celular, abrir la app del banco y buscar si ya le cayó el dinero, con la fila esperando. Si cobran varios familiares o empleados, el dueño no sabe quién vendió qué ni si lo que entró cuadra con lo que salió del anaquel. El inventario se lleva de memoria o en libreta.

CoDi ya resolvió mover el dinero sin comisión. A finales de 2025 tenía unos 22 millones de cuentas validadas, pero solo registró 4.4 millones de operaciones en todo el año ([ClearingPost, sep-2026](https://clearingpost.com/insights/mexico-s-codi-logged-4-4-million-operations-in-2025-as-banxico-sets-december-sta/)). La gente lo tiene y no lo usa. El cuello de botella está del lado del que cobra: falta una herramienta que le diga al comercio, sin ambigüedad, que ya le pagaron.

## La solución

Abarpay convierte el teléfono que el comerciante ya tiene en su caja:

1. **El empleado dicta la venta**: "dos cocas y unas sabritas". OpenAI propone el carrito con el catálogo de la tienda y el empleado lo confirma. Los precios salen del catálogo, nunca de la IA. Si el dictado falla, hay botones rápidos.
2. **Se cobra por CoDi con pey**: aparece un QR, el cliente paga desde la app de su banco y no hay comisión por transacción.
3. **Confirmación verificada**: la venta se marca como pagada solo cuando llega la notificación firmada de pey. Ni la pantalla del cliente ni el QR cuentan como prueba de pago.
4. **Aviso en voz alta**: el teléfono de quien cobró y el del dueño dicen "ya te pagaron 58 pesos". Nadie tiene que revisar el banco.
5. **El negocio se actualiza solo**: la venta queda registrada producto por producto, el inventario baja una sola vez y el dueño ve en su panel cuánto vendió, quién cobró y qué hay que resurtir.

## Qué vamos a demostrar el domingo

Un recorrido completo y real: una venta dictada, un QR generado por pey, un pago real de $0.01 MXN hecho por un integrante del equipo, la confirmación firmada, el aviso de voz en dos teléfonos y el panel del dueño actualizado. Si usamos algún respaldo simulado en la presentación, lo vamos a identificar como tal.

## Por qué pey y por qué ahora

- Conectarse directo a CoDi requiere un trámite de alrededor de 12 meses. Con la API de pey toma minutos y acepta cuentas de cualquier banco participante (instrucciones de pey para el hackatón).
- pey no custodia fondos: el pago se liquida de banco a banco por la infraestructura de Banxico ([pey, aviso de privacidad](https://pey.mx/legal/aviso-de-privacidad)). Abarpay tampoco toca el dinero.
- El 14 de diciembre de 2026, la Circular 9/2026 obliga a los bancos a estandarizar cómo se ven CoDi y los pagos QR en sus apps ([ClearingPost](https://clearingpost.com/insights/mexico-s-codi-logged-4-4-million-operations-in-2025-as-banxico-sets-december-sta/)). El lado del que paga se vuelve más fácil, y el que llegue con la herramienta del que cobra se queda con el canal.

## Lo que ya funciona en otros países

| Caso | Qué hace | Cómo gana dinero |
|---|---|---|
| Paytm Soundbox (India, UPI) | Bocina que anuncia cada pago recibido | Renta mensual; Paytm reporta 15.1M de suscripciones de comercios entre QR, Soundbox y terminales ([Paytm, may-2026](https://paytm.com/blog/payments/paytm-merchant-payments-network-1-51-crore-storefronts/)) |
| BharatPe (India, UPI) | QR gratis para la tiendita | Préstamos con socio regulado, evaluados con el historial de pagos; 7M+ comercios en 2021 ([TechCrunch](https://techcrunch.com/2021/02/10/india-fintech-bharatpe-valued-at-900-million-in-new-108-million-fundraise)) |
| InfinitePay (Brasil, Pix) | El celular como terminal y Pix gratis | Comisión de tarjeta y crédito a PyMEs ([Sacra](https://sacra.com/c/cloudwalk/)) |

El patrón se repite: el pago gratis atrae al comercio y el negocio está en lo que se construye encima. Ninguno de estos casos sabe *qué* se vendió, solo *cuánto*. Abarpay sabe las dos cosas.

## Modelo de negocio (hipótesis por validar)

El comerciante no paga por cobrar. Las fuentes de ingreso que vamos a probar:

1. **Servicios financieros con socios regulados**: con meses de ventas verificables, el comercio puede pedir financiamiento a un socio autorizado y Abarpay cobra comisión por referencia. No prestamos ni custodiamos fondos.
2. **Plan para el dueño**: renta mensual baja por varios empleados, reportes y alertas de resurtido.
3. **Servicios para proveedores**: pedidos sugeridos y demanda agregada por zona, anónima, siempre con permiso del comercio.

Nada de esto está validado. Falta confirmar quién paga, cuánto y bajo qué condiciones de uso de datos. Los datos son del comerciante y él decide si los comparte.

## Hoja de ruta

| Etapa | Qué incluye |
|---|---|
| Hackatón | Venta dictada, QR de pey, confirmación verificada, aviso de voz, inventario y corte del día |
| Piloto (meses 1-3) | 50 tienditas en una colonia de CDMX; medir tiempo de cobro, pagos confirmados, diferencias de inventario y uso recurrente |
| Operación ampliada | Consultas por voz, alertas de reposición, fiado digital, trabajo sin conexión |
| Proveedores y financiamiento | Pedidos sugeridos, demanda agregada, financiamiento con socios autorizados |
| Investigación | Reconocimiento visual de productos, pronóstico de demanda, indicador físico de pago |

## Arquitectura

Una aplicación web para el teléfono, sin instalar nada desde tiendas, con un servidor propio en Python/FastAPI y SQLite que guarda las credenciales y decide comercio, cuenta e importe. Una base de datos transaccional registra ventas, pagos, inventario y eventos recibidos. La IA (OpenAI) interpreta el dictado y propone el carrito; los cálculos, permisos y cambios de dinero los hacen reglas del servidor. Los pagos llegan por webhook de pey con firma verificada y deduplicación. Si el webhook no llega, el servidor concilia consultando las transacciones del QR en pey.

Reglas no negociables: las credenciales nunca van al repositorio ni a la aplicación del teléfono; la venta solo pasa a pagada con una confirmación verificada; una confirmación repetida no descuenta inventario dos veces; un importe distinto queda pendiente de conciliación.

## Equipo

Mesa de innovación colaborativa (atribuciones por confirmar): Sergio Arturo Gasca, Carlos del Valle, Ricardo Flores, Agustín Vaquero, Eduardo García, Oswaldo, Luis Murillo y compañeros.

## Estado al 7 de noviembre, 16:00

| Elemento | Estado y evidencia |
|---|---|
| Producto, alcance del MVP y modelo de negocio | Definidos (este documento, `docs/decisiones/0002`) |
| Acceso a la API de pey con la nueva clave | `GET /transaction/api-key` → HTTP 200 (15:00) |
| Cuenta receptora CoDi | Activa: pey generó el QR y recibió el pago |
| Primer pago real | $0.01 por CoDi, transacción `01M6VXE5HTXV66NPJCR1XY7T4A`, `PAID` a las 15:08:08, conciliada con `GET /transaction/codi/qr/{id}` |
| App del MVP (`app/`) | Funciona en local: venta escrita o dictada → QR real de pey → espera de pago con conciliación → aviso de voz → inventario y corte. 12 pruebas automáticas en verde (con pey simulado) |
| IA de OpenAI | Integrada en el código con salida estructurada; pendiente de key para probarla en vivo. Mientras tanto, la pantalla avisa que usa el intérprete local |
| Webhook en internet | Código listo con firma verificada; falta URL pública HTTPS para registrarlo en pey |
| Pago real desde la pantalla de la app | Pendiente: el pago de las 15:08 se hizo a un QR creado directo por API |
