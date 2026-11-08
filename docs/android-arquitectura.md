# Android, identidad y consola · propuesta de implementación

Requisitos expresados por Carlos el 7 de noviembre de 2026: el dueño se registra y crea su tiendita; da acceso a sus empleados desde la aplicación; todos operan en móvil; una consola web permite al dueño consultar la misma información. Backend API compartido con SQLite para facilitar el MVP. Actualización posterior de Carlos: **los logins del móvil y de la consola web deben ser mockups** para facilitar la revisión de los jueces. Esta instrucción reemplaza la integración de login real en el alcance de esta demo. No implementar ni solicitar OAuth.

Esta nota **no reemplaza** las decisiones vigentes ni afirma que esas capacidades ya existan. `app/` sigue siendo FastAPI/SQLite y `android/` añade un cliente nativo. Los prototipos quedan como referencia.

## Estado real

Android 0.1.1 añade login/registro visuales de solo lectura con datos ficticios, perfiles de dueño/empleado y botones Google/Apple locales. No crean identidad, cuenta, tienda ni invitación. Este PR incorpora únicamente el cliente Android y su documentación. La consola autónoma del paquete de demostración queda fuera del PR; sus datos ficticios son independientes de Android y no están sincronizados. El modelo y los proveedores descritos abajo son únicamente diseño para una etapa futura con autorización nueva, no tareas de esta demo.

La API actual no tiene autenticación, usuarios de identidad, tiendas separadas, invitaciones, sesiones ni roles efectivos. `employees.role` es un atributo de presentación; enviar `employeeId` no prueba quién opera. La web y Android son superficies de desarrollo de una sola tienda. No deben abrirse a datos reales o a internet sin estos controles.

## Modelo mínimo propuesto en SQLite

- `users`: identidad interna. `identities`: proveedor y `subject` verificado, con restricción única `(provider, subject)`; no identificar a una persona únicamente por un email declarado por el cliente.
- `stores`: tienda. `memberships`: relación `(store_id,user_id)` y rol `owner`/`employee`; estado activo/revocado. Cada tienda tiene al menos un dueño activo.
- `invites`: creador, tienda, rol, hash del token de un solo uso, expiración, fecha de consumo. El móvil del dueño crea y revoca invitaciones; el empleado las acepta estando autenticado.
- Productos, ventas, partidas, movimientos y pagos ligados a `store_id`. Relaciones compuestas o validaciones transaccionales impiden asociar productos/ventas de tiendas distintas.
- SQLite solo en el servidor, con migraciones, claves foráneas activas, transacciones y pruebas de concurrencia. No copiar la base completa a cada teléfono ni desplegar SQLite en almacenamiento efímero.

## API objetivo, aún no disponible

- Sesión: alta/inicio/cierre, `GET /api/me`; validación de tokens en el servidor. En web, cookies `HttpOnly`, `Secure`, `SameSite` y protección CSRF. En móvil, mecanismo de sesión adecuado y almacenamiento protegido por Android Keystore; no guardar tokens en SharedPreferences plano.
- Tienda: creación por dueño, selección de una membresía autorizada, catálogo y datos de la tienda actual.
- Equipo: invitar, aceptar y revocar. Solo el dueño gestiona empleados y privilegios.
- Ventas: dueño y empleado capturan ventas; el servidor deriva vendedor y tienda de la sesión. No confiar en `employeeId` o `storeId` arbitrarios enviados por el teléfono.
- Inventario: lectura, conteo y ajuste con motivo/auditoría. Definir quién puede aplicar ajustes; propuesta inicial: dueño, con captura de conteos de empleados pendiente de aprobación.
- Reportes y consola: dueño consulta totales/equipo y pendientes; limitar al empleado según política explícita. No proteger únicamente escondiendo botones.
- Cobros: `Idempotency-Key` durable vinculada a tienda, usuario y huella del carrito; identificador de intento recuperable incluso en timeout; estado consultable por intento; detalle completo de venta/QR/vencimiento; conciliación explícita de casos inciertos.

Cada endpoint debe validar sesión, membresía, rol, tienda y propiedad del recurso. Una URL con `store_id` no es aislamiento. Agregar pruebas de usuario A intentando leer/modificar tienda B, invitaciones vencidas/reusadas, empleado intentando elevar su rol, revocación efectiva y dos dispositivos con la misma solicitud de cobro.

## Trazabilidad PEY por tienda y cuenta receptora

**Hecho documentado, verificado el 7 de noviembre de 2026:** PEY indica que el webhook QR solo incluye `bankAccountId` cuando ese campo se envió al crear el QR. El contrato OpenAPI, versión `2026-10-20`, establece que omitirlo dirige el pago a la cuenta CoDi asociada a la API key. Por tanto, su ausencia no demuestra un error ni permite identificar por sí sola la tienda receptora. Fuentes: [webhook de pago QR](https://docs.pey.mx/docs/webhooks/codi/qr/) y [contrato OpenAPI, POST /codi/qr](https://docs.pey.mx/openapi.json).

**Propuesta de diseño, no capacidad implementada ni fallo confirmado:** conservar en el servidor una relación durable entre tienda, venta, intento, QR PEY y conexión de pagos. Cada intento debe registrar la referencia interna/versionada de la credencial utilizada y su `apiKeyId` cuando se conoce, el modo de selección de cuenta (`explicit` o `api_key_default`), la referencia de cuenta explícita o la configuración receptora verificada en ese momento, moneda esperada e importe efectivamente cobrado en centavos. Guardar referencias a secretos, nunca el valor de la API key en ventas, logs, respuestas al móvil o documentación. Una rotación de clave o un cambio de cuenta no debe reescribir la asociación histórica.

Al procesar una confirmación:

1. Verificar firma y controles de repetición del webhook; resolver el QR contra el vínculo guardado por el servidor. No deducir tienda o cuenta únicamente de `bankAccountId`, `metadata` ni valores enviados por Android.
2. Contrastar `apiKeyId` con la conexión que generó el intento. Si viene `bankAccountId`, compararlo con la cuenta receptora registrada. Si falta y el intento usó cuenta implícita, mantener la asociación guardada; no inventar un identificador ni cambiar de tienda. Si se esperaba cuenta explícita y faltan datos, conservar el caso por conciliar y contrastar con PEY usando la conexión original.
3. Relacionar la transacción con ese QR y venta, comprobar el importe recibido contra `chargedCents` (no contra el total comercial de una demo), respetar MXN y deduplicar evento y transacción. Ante discrepancias o vínculo desconocido, no acreditar otra tienda ni cerrar automáticamente la venta.
4. Aplicar pago e inventario de forma transaccional y una sola vez. La conciliación por API sigue la misma relación de tienda/conexión/cuenta y las mismas comprobaciones; no es una excepción a los controles.

Pruebas futuras con proveedores falsos: webhook sin `bankAccountId` para cuenta implícita; cuenta explícita coincidente, ausente o diferente; `apiKeyId` inesperado; QR desconocido o ligado a otra tienda; importe distinto; transacción repetida; y evento tardío después de rotar la clave o cambiar la cuenta configurada. Deben demostrar que ninguna ausencia o discrepancia produce un cruce de tiendas o un doble abono. Este añadido solo precisa el diseño; no modifica `app/main.py`, `apply_payment` ni la integración real.

## Identidad futura, fuera del alcance de los mockups

**Google primero**, si el equipo puede configurar OAuth: Android Credential Manager / Sign in with Google; cliente Android asociado al package y huella de firma, cliente web para el backend y audiencia; servidor verifica firma, issuer, audiencia, expiración y nonce. La consola web comparte la misma identidad interna. No poner client secrets en el APK. La configuración y las pantallas de consentimiento se hacen con la cuenta del propietario y los permisos correspondientes.

**Apple como segunda etapa**: en Android y web se usa un flujo web Sign in with Apple. Requiere configuración de Apple Developer, identificadores apropiados (App ID/Services ID), dominio y redirect HTTPS autorizados y credenciales de firma en servidor. Debe resolverse manejo de email privado y vinculación de cuentas sin asumir que dos emails iguales prueban la misma identidad. No es un botón que pueda activarse solo desde Android y no se ha configurado.

Si esas altas retrasan el MVP, considerar login propio con identificador y contraseña, hash robusto (Argon2id), sesiones revocables, rate limiting y mensajes de error seguros. No usar selección de empleado, PIN compartido o códigos de tienda públicos como sustituto de autenticación. Esta alternativa también necesita implementación y pruebas; no existe todavía.

Referencias oficiales: [Google Credential Manager](https://developer.android.com/identity/sign-in/credential-manager-siwg), [validación de Google ID tokens](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token), [Sign in with Apple para web](https://developer.apple.com/help/account/capabilities/configure-sign-in-with-apple-for-the-web/).

## Entregas recomendadas

1. Compilación de la base móvil y flujo SIMULADO comprobados localmente (ver `android/VERIFICACION.md`); completar la validación de cámara y uso en teléfono físico, sin mover dinero.
2. Para los jueces: login/registro mockup y datos ficticios también en consola demo aislada. No abrir la API sin autenticar a internet.
3. En una fase productiva autorizada: migraciones SQLite + sesión + tienda + membresías; prueba de aislamiento antes de conectar usuarios reales.
4. Alta móvil real del dueño e invitación de empleado; consola web con la misma sesión/API.
5. Recuperación/idempotencia de cobros y conteo de inventario auditado. Ensayar interrupción de red, muerte de proceso, doble toque y pago tardío.
6. Google/Apple solo en una fase futura autorizada, según configuración disponible; prueba física de escáner y accesibilidad. Pago real de $0.01 solo por una persona autorizada, sin agentes.
