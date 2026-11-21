# Cobertura de tarjetas de producto

## Uso por DSH

Este archivo es autosuficiente para reconciliar el alcance de producto. DSH significa DeepSeek Harness. No necesita leer el export descargado para consultar la lista normalizada. Para cada tarjeta pendiente, DSH usa la referencia numérica local como clave estable, el tema para localizar el paquete correspondiente y el escenario de aceptación para definir la prueba.

`already covered` exige conservar la evidencia actual y ejecutar la aceptación del paquete cuando una superficie cambie. `build` exige contrato y alcance de escritura antes del código. `defer` mantiene la función informada como no disponible hasta contar con el proveedor o la operación externa. `duplicate` remite a la tarjeta canónica y no crea un segundo trabajo. Ninguna disposición autoriza desplegar, cobrar o exponer datos reales por sí sola.

## Alcance y verificación

Tablero de origen: `AbarPay: Funcionalidades`. Se normalizaron las 85 tarjetas de producto y se excluyeron las 6 tarjetas de la guía inicial de Trello. Este documento no reproduce miembros, identificadores internos, adjuntos, correos, enlaces privados ni datos personales del export original.

La evidencia se contrastó con el código de `main` en `75c1f35`, revisado el 21-nov-2026. Las pruebas citadas existían en esa revisión. Esta tarea documental no volvió a ejecutar las suites y no hizo una prueba nueva en dispositivo.

**Estado físico por defecto: NO VERIFICADO EN DISPOSITIVO.** Ninguna fila constituye aceptación física. Las indicaciones `automatizado`, `lectura estática` o `sin implementación` describen la evidencia disponible, no una prueba en Android real.

Disposiciones permitidas:

| Disposición | Significado |
|---|---|
| `build` | La necesidad no está completa en el baseline y requiere contrato, implementación y verificación. |
| `already covered` | El comportamiento central existe y tiene evidencia automatizada en el baseline. No implica aceptación del producto completo ni prueba física. |
| `defer` | Depende de un proveedor, operación, autorización o canal que aún no se conoce. Puede conservarse el estado informado en la UI. |
| `duplicate` | La necesidad queda cubierta por otra tarjeta canónica. El alcance adicional, si existe, se enumera en la aceptación. |

Ruteo al [tablero de ejecución](09-paquetes-y-aceptacion.md): T-01 → I6/M1; T-02 → I1/I2/M1; T-03 → I2/M2; T-04 → I1/M3; T-05 → M1/M2/M4; T-06 → M2; T-07 → M2/M4/M6; T-08 → M3; T-09 → M4; T-10 → M1; T-11 → I6/M6; T-12 → I1/M6/M7. En T-07 los informes de la tienda pertenecen a la consola del comerciante. Los indicadores de captación, facturación del software y comunidad pertenecen a M6 en la plataforma.

La referencia T seguida de un número se obtiene de `idShort` de cada tarjeta (p. ej. T7 corresponde a `idShort=7`). No es el número de funcionalidad escrito por el equipo. En el export original se pueden reconciliar los 85 valores sin publicar enlaces al tablero.

Temas de entrega:

| Tema | Alcance |
|---|---|
| `T-01 Alta y entrega` | Instalación, alta inicial y distribución del APK. |
| `T-02 Identidad, banco y tienda` | Identidad comercial, cuentas receptoras y sesiones. |
| `T-03 Equipo` | Invitaciones, accesos, roles, empleados y cajas. |
| `T-04 Catálogo e inventario` | Productos, precios, existencias, ajustes y trazabilidad. |
| `T-05 Cobro` | Carrito, efectivo, CoDi, fiado y métodos sujetos a proveedor. |
| `T-06 Caja` | Movimientos de efectivo, cierre y entrega. |
| `T-07 Reportes y consola` | Indicadores, filtros, detalle, exportación y navegación web. |
| `T-08 Reposición` | Alertas, proveedores, pedidos, recepción y publicación. |
| `T-09 Fiado` | Cliente, deuda, límites, abonos, recordatorios y liquidación. |
| `T-10 Soporte y conciliación` | Tickets, eventos CoDi y diferencias. |
| `T-11 Web y comercial` | Landing, entrada QR y medición de campañas. |
| `T-12 Plataforma` | Operación interna, comunidad y aislamiento multiempresa. |

Los escenarios `S-01` a `S-18` y los flujos `F-01` a `F-12` se definen en `03-flujos-y-ergonomia.md`. La copia y los gates de la landing se definen en `06-landing-y-comercial.md`.

## Reconciliación

| # | Ref. tarjeta | Necesidad normalizada | Disposición | Evidencia o baseline | Tema | Aceptación |
|---|---|---|---|---|---|---|
| 1 | `T7` · Descarga e instalación | Encontrar e instalar una versión utilizable y completar la primera apertura. | `build` | No hay ficha de Google Play ni página pública de APK. El worklog registra APKs firmados locales y `mx.abarpay.mobile`. Google Play es un canal posterior. | `T-01` | `S-17` · La landing entrega un APK firmado con versión, fuente, SHA-256 e instrucciones, y permite la instalación limpia en Android físico antes de G2. Google Play queda para después. |
| 2 | `T8` · Alta e identidad del negocio | Crear la tienda con nombre y logotipo que el personal reconozca. | `build` | `PUT /api/store/profile` y `/store/photo` existen con pruebas, pero no hay logotipo separado ni aislamiento multiempresa completo. | `T-02` | `S-01`, `S-15` · Tienda nueva muestra su nombre e imagen, sin personal ni marca de otra tienda. Android y consola coinciden. |
| 3 | `T9` · Cuenta bancaria | Registrar una cuenta receptora válida, verificar el estado y bloquear cobros sin activación. | `build` | No hay ruta de CLABE ni activación. `apply_payment` conserva la confirmación CoDi, pero la creación depende de una cuenta configurada fuera del producto. | `T-02` | `S-01`, `S-16` · Guardar una cuenta válida, mostrar activación pendiente y rechazar cobros si falta o está inactiva. Datos enmascarados y auditados. |
| 4 | `T10` · Catálogo y precios | Crear y consultar nombre, unidad y precio usados en la venta. | `already covered` | `/api/catalog`, CRUD Android y consola, tests `test_catalog_v3`. Precio siempre desde la base. | `T-04` | `S-07`, `S-14` · Crear producto, verlo en consola y en empleado autorizado con el mismo precio. Dispositivo NO verificado. |
| 5 | `T11` · Inventario inicial | Fijar existencias iniciales para varios productos. | `already covered` | `/api/inventory/set`, `/api/inventory/adjust`, tests `test_inventory_v2` y UI de inventario. | `T-04` | `S-07` · Fijar 10 unidades en tres productos y verificar los mismos valores al recargar. Dispositivo NO verificado. |
| 6 | `T12` · Puntos de venta | Definir usuarios o dispositivos que operan como caja del negocio. | `build` | El baseline usa empleados y un almacén de una sola tienda. No hay entidad de caja, dispositivo o sesión asignada. | `T-03` | `S-08`, `S-15` · Crear dos cajas de una tienda, asignar personal, separar operaciones y impedir que una caja use otra tienda. |
| 7 | `T13` · Invitación por QR o liga | Generar una invitación del negocio que abra el registro del empleado correcto. | `already covered` | `/api/employees/invites`, `/invite/{token}`, App Links y pruebas de QR/liga Android. La duración y consumo único están cubiertos. | `T-03` | `S-08` · Abrir QR y liga, escanear en Android y comprobar la tienda correcta. Enlace vencido y reutilizado fallan. Dispositivo NO verificado en esta revisión. |
| 8 | `T14` · Registro del empleado | El empleado acepta con su nombre y ve la identidad del negocio antes de vender. | `build` | Existe la pantalla y token de aceptación, pero la identidad de API usada por las operaciones todavía es declarativa. | `T-03` | `S-08`, `S-15` · Aceptar con identidad verificada, ver negocio correcto y quedar sin permiso de venta hasta activación. |
| 9 | `T15` · Autorización y acceso | Aplicar permisos reales del dueño al empleado. | `build` | Hay gates de UI y pruebas de `canSell`, `canFiado` y `canInventory`, pero `X-Employee-Id` y el PIN compartido no prueban identidad. | `T-03` | `S-08`, `S-15` · Empleado no autorizado recibe denegación de servidor, no solo ocultamiento de botón. Revocación y relevo funcionan en Android físico. |
| 10 | `T16` · Consulta de productos | Consultar precio y disponibilidad para cliente presencial. | `already covered` | Catálogo público y bootstrap incluyen stock, unidad y precio. UI de Cobrar muestra `disponibles` o `Sin límite`. | `T-04` | `S-07` · Producto disponible y agotado muestran precio y disponibilidad correctos. NO verificado con usuario real. |
| 11 | `T17` · Carrito | Agregar productos y cantidades y confirmar el total. | `already covered` | UI de carrito, hoja inferior y `cartEstimate` usan precios del catálogo. Pruebas de cantidades y totales. | `T-05` | `S-02`, `S-14` · Dos productos con cantidades distintas muestran líneas y total. Rotación y TalkBack conservan estado. |
| 12 | `T18` · Dictado para agregar | Interpretar producto y cantidad, mostrarlos para confirmación y corregir errores. | `already covered` | `/api/cart/parse`, parser local de demo y pruebas de frases. La confirmación existe antes de agregar. | `T-04` | `S-07`, `S-14` · Dictar tres productos, corregir una coincidencia y cobrar solo después de confirmar. Dictado físico NO verificado. |
| 13 | `T19` · Selección de medio | Presentar todos los medios aplicables sin ejecutar un cobro al elegir. | `build` | La UI actual muestra efectivo, CoDi y fiado. Liga, push y terminal no existen. | `T-05` | `S-16` · Las seis opciones se muestran solo si están soportadas. Elegir no crea pago. Las no disponibles explican el motivo. |
| 14 | `T60` · Medio QR | Elegir QR y abrir el flujo sin marcar pagado. | `already covered` | Chip PEY/CoDi y `POST /api/sales` crean venta pendiente. La confirmación no ocurre al seleccionar. | `T-05` | `S-03` · Seleccionar CoDi abre generación de QR y mantiene venta pendiente hasta servidor. |
| 15 | `T61` · Medio liga | Generar y entregar una liga sin marcar pagado. | `defer` | No hay integración de liga ni evidencia operativa del proveedor. | `T-05` | `S-16` · Si no existe soporte, la opción no se ofrece. Si se habilita, orden, monto y confirmación se prueban con proveedor y dinero autorizado. |
| 16 | `T62` · Medio push | Iniciar solicitud push o informar indisponibilidad sin cobrar. | `defer` | No hay soporte push en el cliente ni evidencia del proveedor. | `T-05` | `S-16` · La UI no promete push. Una integración futura prueba aceptación, rechazo y estados sin cambiar la orden a pagada. |
| 17 | `T63` · Medio efectivo | Elegir efectivo y abrir captura de recibido y cambio. | `already covered` | Chip Efectivo, `parseCashCents`, `POST /api/sales` y tests de cambio. La caja por turno se trata en las tarjetas 28–30. | `T-05` | `S-02` · Seleccionar efectivo muestra recibido y cambio, no QR ni confirmación bancaria. |
| 18 | `T64` · Medio tarjeta | Procesar tarjeta o vales por terminal y esperar resultado válido. | `defer` | No hay integración de terminal. | `T-05` | `S-16` · La opción permanece no disponible hasta contar con terminal, contrato y prueba de resultado. |
| 19 | `T65` · Medio fiado | Dirigir al cliente y validar crédito sin contar el monto como cobrado. | `already covered` | Chip Fiado, cliente requerido, `paymentMethod=fiado`, estado `credit` y tests que excluyen cobro. | `T-09` | `S-04` · Seleccionar fiado exige cliente y no suma recaudación. Límites nuevos se cubren en tarjetas 51–57. |
| 20 | `T20` · Generación de QR | Mostrar QR con importe, referencia y vínculo a la venta. | `already covered` | `POST /api/sales` y cliente PEY guardan `saleId`, `qrId`, importe y vencimiento. UI muestra QR de la venta. | `T-05` | `S-03` · El QR pertenece a una sola venta y muestra importe y vigencia. Captura no confirma pago. |
| 21 | `T21` · Confirmación bancaria | Distinguir pendiente de confirmado y aplicar solo un evento válido. | `already covered` | Firma de webhook, conciliación, tests `test_webhooks`, `test_pey_flow`, `test_concurrent_webhooks` y `apply_payment`. | `T-05` | `S-03`, `S-08` · Escanear no cambia estado. Webhook válido o conciliación pagan una vez. Importe distinto queda por conciliar. |
| 22 | `T22` · Avisos de pago | Avisar a cliente, empleado y dueño con orden, importe y caja correctos. | `build` | Existen tickets y reportes, pero no un modelo de notificaciones por actor ni outbox de avisos. | `T-10` | `S-03`, `S-08` · Un pago confirmado crea un aviso por destinatario, deduplicado, sin confundir pendiente con cobrado. |
| 23 | `T23` · Descuento de inventario | Descontar la venta una sola vez y actualizar cajas. | `already covered` | `decrement_inventory`, movimientos y pruebas de venta, concurrencia y webhook duplicado. | `T-04` | `S-02`, `S-08` · Vender 2 de 10 deja 8. Repetir confirmación no vuelve a descontar. Sincronización multi-caja queda sujeta a `S-07`. |
| 24 | `T24` · Entrega del producto | Cerrar la entrega de una venta pagada y dejar estado final. | `build` | La venta tiene estados de pago, pero no un registro de entrega o fulfillment. | `T-05` | `S-02`, `S-03` · Una venta confirmada puede marcarse entregada una vez con actor y fecha. Una venta pendiente no se entrega como pagada. |
| 25 | `T25` · Cobro push | Cobrar por solicitud push en un ambiente habilitado. | `defer` | No hay soporte de proveedor ni integración. | `T-05` | `S-16` · Solo se habilita con contrato y ambiente de proveedor. Aceptación, rechazo y pago se confirman por servidor. |
| 26 | `T26` · Cobro por liga | Emitir una liga con importe y asociarla al pago de la venta. | `defer` | No hay liga de pago. | `T-05` | `S-16` · Si se integra, una liga queda ligada a una orden y el pago se aplica una vez después de confirmación. |
| 27 | `T27` · Terminal con tarjetas | Registrar crédito, débito o vales por terminal y aplicar el resultado correcto. | `defer` | No hay terminal ni contrato de adquirente. | `T-05` | `S-16` · La opción no se ofrece hasta integrar la terminal. La venta sigue pendiente hasta resultado válido. |
| 28 | `T28` · Cobro en efectivo | Recibir efectivo, calcular cambio, confirmar venta y acumular caja por caja responsable. | `build` | El cobro, cambio, estado pagado y movimiento existen. Falta sesión de caja y acumulación separada de otros medios. | `T-06` | `S-02`, `S-06` · Cobrar 80 recibiendo 100 deja cambio 20 y suma 80 solo a la caja de efectivo. No crea webhook. |
| 29 | `T66` · Cierre de caja | Sumar efectivo por empleado o caja, capturar contado y mostrar diferencia. | `build` | No hay entidad de cierre. El reporte suma efectivo del día, sin esperado por turno. | `T-06` | `S-06` · Tres ventas suman esperado, contado compara contra esperado y muestra diferencia. No mezcla fiado ni CoDi. |
| 30 | `T67` · Entrega al dueño | Registrar entrega de efectivo y aceptación o discrepancia del dueño. | `build` | No hay handover ni aceptación. | `T-06` | `S-06` · Entregar 300 y aceptar. Repetir con 280 y dejar estado no aceptado con diferencia y responsables. |
| 31 | `T29` · Inventario y agotados | Consultar existencias e identificar cero o mínimo. | `already covered` | `/api/inventory`, bootstrap, `lowStock` y UI de inventario/reportes. Tests `test_inventory_v2` y `test_report`. | `T-04` | `S-07` · Agotar artículo y ver `0`/`Inventario bajo`. Roles autorizados consultan el mismo dato. NO verificado físicamente. |
| 32 | `T30` · Historial de movimientos | Consultar entradas, ventas y ajustes con motivo y responsable. | `build` | El servidor guarda movimientos y motivo, pero la UI no ofrece historial completo por producto. | `T-04` | `S-07`, `S-13` · Un ajuste +5 muestra cantidad, motivo, actor y fecha en historial. Solo roles autorizados ajustan. |
| 33 | `T31` · Sincronización entre cajas | Mostrar la misma existencia a dispositivos autorizados. | `build` | Comparten base central cuando hay red, pero no existe caché, cola ni conflicto entre cajas offline. | `T-04` | `S-07`, `S-12` · Actualizar en una caja y verlo en otra al sincronizar. Dos ventas offline de última unidad conservan ambas y generan diferencia. |
| 34 | `T32` · Tablero y filtros | Consultar cobros confirmados con filtros por fecha, empleado o caja y separar pendientes. | `build` | `/api/reports/today` entrega hoy, por empleado y métodos. No hay rango, filtros ni selector de caja/POS. | `T-07` | `S-10` · Día y caja filtran totales pagados. Pendientes aparecen separados y no inflan cobrado. |
| 35 | `T33` · Desglose por medio | Ver subtotales y referencias conciliadas por medio. | `build` | Hay `cashCents`, `peyCents`, `fiadoCents`, pero no detalle conciliado por venta/referencia en una vista de conciliación. | `T-07` | `S-10` · CoDi, efectivo y fiado tienen subtotales y detalle. La suma coincide con ventas pagadas y abonos aplicados. |
| 36 | `T34` · Diferencias y fallos | Señalar pendientes, rechazos o importes discrepantes sin sumarlos como cobrados. | `build` | Estados `pending`, `por_conciliar` y `failed` existen y hay tickets. Falta comparación de importe/referencia en una vista conciliada. | `T-10` | `S-03`, `S-08`, `S-10` · Un pago fallido o importe distinto no aumenta cobrado. La diferencia tiene referencia y siguiente acción. |
| 37 | `T35` · Ventas por producto | Reportar unidades y montos por periodo y destacados. | `build` | `topProducts` limita a cinco y solo hoy. No hay reporte por rango ni exportación. | `T-07` | `S-10` · Un periodo seleccionado coincide con unidades y montos de ventas. Productos cancelados se excluyen una vez. |
| 38 | `T36` · Ventas por empleado o caja | Atribuir ventas y montos a cada responsable. | `build` | `byEmployee` existe para hoy, sin caja/POS ni rango. El actor productivo aún no está verificado. | `T-07` | `S-10`, `S-15` · Dos cajas y dos empleados producen desglose exacto. Cambiar de tienda no mezcla responsables. |
| 39 | `T37` · Inventario y exportación | Exportar entradas, salidas y existencias con acceso controlado. | `build` | No hay exportación de inventario. | `T-07` | `S-10`, `S-14` · Exportar y comparar cantidades con la pantalla. El archivo respeta tienda, permisos y periodo. |
| 40 | `T38` · Faltantes para compra | Señalar agotados o bajos como trabajo de reposición. | `already covered` | `lowStock` alimenta Inicio e inventario. La acción de preparar pedido se evalúa en C-04 y tarjetas 41–49. | `T-04` | `S-07` · Un producto agotado aparece en productos por reponer. La acción siguiente se cubre con `S-05`/`S-10`. |
| 41 | `T39` · Registro de proveedor | Crear y asignar el proveedor adecuado a un producto sin cruzar tiendas. | `build` | No hay entidad de proveedor. | `T-08` | `S-05`, `S-15` · Crear proveedor, asignarlo a producto y comprobar que otra tienda no lo ve ni lo reutiliza. |
| 42 | `T40` · Pedido y aprobación | Armar cantidades, unidades y condiciones y aprobar antes de enviar. | `build` | No hay pedido de compra. | `T-08` | `S-05` · Crear pedido de dos artículos, revisar cantidades/unidades y aprobar. Sin aprobación no se envía. |
| 43 | `T41` · Envío al proveedor | Enviar o compartir el pedido y guardar folio y estado. | `build` | No hay envío ni seguimiento. | `T-08` | `S-05`, `S-16` · Si el canal externo no está disponible, se conserva borrador y no se afirma envío. Con canal, folio y destinatario quedan registrados. |
| 44 | `T42` · Recepción y conteo | Capturar cantidades físicas recibidas frente al pedido. | `build` | Solo existe ajuste manual. No hay recepción contra pedido ni operación offline. | `T-08` | `S-05` · Recibir 8 de 10, guardar diferencia y recuperar tras cierre forzado. No publica stock antes de aprobar. |
| 45 | `T43` · Entrada de inventario | Vincular mercancía recibida a pedido, fecha y responsable. | `build` | Los movimientos de ajuste tienen actor, pero no vínculo a pedido/recepción. | `T-08` | `S-05`, `S-08` · Registrar seis unidades, ver el folio y el actor. Reintentar crea una sola entrada. |
| 46 | `T44` · Diferencias de recepción | Mostrar faltantes o sobrantes antes de cerrar. | `build` | No existe comparación pedido contra recibido. | `T-08` | `S-05` · Recibir 8 de 10 y mostrar diferencia 2 con motivo y siguiente acción. |
| 47 | `T45` · Aprobación de stock | Aprobar entrada y publicar existencia sin duplicar. | `build` | No hay aprobación o publicación idempotente de recepción. | `T-08` | `S-05`, `S-08` · Aprobar una recepción actualiza stock una vez. Repetir el evento no duplica. |
| 48 | `T46` · Alerta de reabastecimiento | Avisar al pasar de cero a existencia positiva, una vez por destinatario. | `build` | `lowStock` detecta cero, pero no hay evento 0→positivo ni avisos. | `T-08` | `S-05`, `S-08` · Reponer 0→5 genera un aviso por destinatario. Cambiar 5→6 no genera aviso. |
| 49 | `T47` · Disponibilidad tras reposición | Volver a ofrecer el producto y consultar el evento y sus avisos. | `build` | No hay historial de reposición ni avisos. | `T-08` | `S-05`, `S-10` · Producto repuesto aparece disponible con precio y evento de entrada. El aviso queda en historial. |
| 50 | `T48` · Fiado y cliente | Registrar o consultar cliente y crear deuda sin marcarla cobrada. | `already covered` | `/api/fiado/customers`, venta fiada, UI y tests `test_fiado`. | `T-09` | `S-04` · Guardar cliente, crear venta fiada y ver deuda. No aparece como cobrada. |
| 51 | `T49` · Límites de fiado | Configurar deuda, monto y vencimiento y mostrar elegibilidad. | `build` | No hay límites ni vencimientos. | `T-09` | `S-04` · Bloquear con deuda activa y mostrar motivo. Excepción autorizada queda auditada. |
| 52 | `T50` · Confirmación de fiado | Conservar importe, plazo y condiciones aceptadas antes de entregar. | `build` | Hay importe y cliente, no plazo, condiciones ni aceptación. | `T-09` | `S-04`, `S-14` · Registrar monto y vencimiento, mostrar condiciones y conservar aceptación. Texto legible con TalkBack. |
| 53 | `T51` · Liga por WhatsApp | Generar liga al adeudo y enviarla con destinatario, importe y referencia. | `defer` | No hay liga ni envío WhatsApp. Requiere consentimiento y proveedor. | `T-09` | `S-16` · Sin integración la UI no promete envío. Si se habilita, el destinatario consiente y la liga se liga a una deuda. |
| 54 | `T52` · Deuda y cartera | Consultar saldo, vencimiento, folio, empleado y estados por cliente. | `build` | Hay cliente, saldo, teléfono e historial de cargos/abonos. Faltan vencimiento, estado explícito y folio de deuda. | `T-09` | `S-04`, `S-10` · Registrar deuda de 100, ver folio, vencimiento y cartera. Abono parcial mantiene deuda abierta. |
| 55 | `T53` · Entrega fiada y stock | Descontar inventario una vez sin sumar recaudación. | `already covered` | Venta fiada crea `credit`, movimiento y `fiado_entries`. Tests lo confirman. | `T-09` | `S-04` · Entregar dos unidades baja stock 2 y no aumenta cobrado. Reintento no descuenta otra vez. |
| 56 | `T54` · Recordatorios | Enviar recordatorios según vencimiento sin duplicar ni exceder. | `build` | No hay vencimiento, consentimiento de canal ni outbox. | `T-09` | `S-04`, `S-18` · Solo se habilita con canal autorizado. Un recordatorio por vencimiento y deduplicación verificada. |
| 57 | `T55` · Bloqueo de nuevos fiados | Aplicar morosidad, saldo y créditos activos a una nueva solicitud. | `build` | No hay reglas ni autorización de excepción. | `T-09` | `S-04` · Cliente con deuda vencida queda bloqueado o pendiente de autorización. Decisión y actor quedan auditados. |
| 58 | `T56` · Pago parcial o total | Distinguir abono de liquidación y actualizar saldo correctamente. | `build` | Abonos manuales reducen saldo y el saldo cero no se declara cobrado. Falta liga y estado formal de liquidación. | `T-09` | `S-04` · Pagar 40 de 100 deja 60, luego 60 deja cero. Un pago repetido no reduce dos veces. |
| 59 | `T57` · Conciliación de abonos | Aplicar cada pago una sola vez y notificar actores. | `build` | El abono actual no usa idempotency key ni emite avisos. | `T-09` | `S-04`, `S-08` · Repetir el mismo evento deja un solo movimiento y saldo. Avisos corresponden al pago. |
| — | `T58` · Conciliación de abonos | Duplicado literal de la tarjeta 59. | `duplicate` | Mismo texto de necesidad y aceptación que `T57`. | `T-09` | Se cierra con la aceptación de 59. El alcance entregable se registra una vez. |
| 60 | `T59` · Liquidación y elegibilidad | Cerrar deuda con saldo cero y aplicar reglas a un nuevo fiado. | `build` | La aritmética llega a cero, pero no hay estado cerrado ni reapertura de elegibilidad. | `T-09` | `S-04` · Liquidar deja estado cerrado. Un saldo parcial sigue abierto. La siguiente solicitud aplica reglas vigentes. |
| 61 | `T68` · Identidad visual de consola | Alinear logo y colores con la app móvil. | `already covered` | `server/static/console.html` contiene la paleta morada y el worklog registra despliegue de consola v5. | `T-07` | `S-14` · Consola carga logo y paleta, mantiene navegación y pasa contraste. Revalidación visual posterior NO realizada. |
| 62 | `T69` · Identidad inicial incorrecta | Una tienda nueva no debe iniciar con personal ajeno. | `already covered` | `test_new_database_seeds_only_the_owner` protege el alta nueva. El demo heredado puede conservar personal si se etiqueta como demo. | `T-02` | `S-01`, `S-15` · Crear una tienda limpia y no ver empleados, clientes ni nombre de otra tienda. |
| 63 | `T70` · Empleados heredados en primer alta | Evitar personal precargado en una cuenta nueva. | `already covered` | Misma evidencia que 62. `test_new_database_seeds_only_the_owner`. | `T-02` | `S-01` · Primera apertura de Android y consola coincide y no contiene personal semilla. |
| 64 | `T71` · Administración de empleados | Agregar, quitar y gestionar permisos desde la consola. | `build` | La API y Android administran equipo, pero no existe vista de Equipo en la consola v5. PIN compartido pendiente de reemplazo. | `T-03` | `S-08`, `S-15` · Dueño invita, revoca y cambia permisos desde consola. Empleado no puede cambiar roles. |
| 65 | `T72` · Inicio por empleado y medio | Ver desglose por caja, empleado y método con subtotales conciliados. | `build` | Inicio muestra totales y últimas ventas. Reportes entrega por empleado y método, sin filtros por caja o periodo. Auditoría estática, NO verificado. | `T-07` | `S-10` · Dos cajas y métodos producen subtotales que suman ventas confirmadas y excluyen pendientes. |
| 66 | `T73` · Consola de cierre de efectivo | Consolidar efectivo, contar, entregar y aceptar desde consola. | `duplicate` | Repite el resultado de 29 y 30 con alcance de consola. No existe implementación. | `T-06` | Se cierra con 29–30 · La misma transacción se administra desde consola con rol autorizado y evidencia `S-06`. |
| 67 | `T74` · Definición de indicadores | Explicar periodo y criterio de ventas, cobrado, fiado y pendientes. | `build` | Existen campos separados, pero la UI no documenta todos los criterios ni filtros. | `T-07` | `S-10` · Cada indicador muestra periodo, fuente y tratamiento de abonos, pendientes y cancelados. |
| 68 | `T75` · Acción desde stock bajo | Llevar un producto bajo a preparar reposición con producto y cantidad precargados. | `build` | Inicio solo enlaza a inventario. No existe pedido. Auditoría estática, NO verificado. | `T-08` | `S-05` · Seleccionar alerta abre preparación de pedido con producto y cantidad sugerida. |
| 69 | `T76` · Motivo de ajustes | Exigir motivo, actor y valor anterior/nuevo al ajustar. | `build` | `/api/inventory/adjust` acepta motivo y actor, pero la UI de consola usa ajustes rápidos sin flujo de motivo completo. | `T-04` | `S-13` · Ajustar +5 exige motivo y muestra actor, anterior, nuevo e historial. |
| 70 | `T77` · Historial por producto | Ver movimientos cronológicos con tipo, cantidad y vínculo. | `build` | Hay últimos movimientos agregados, no detalle completo por producto. | `T-04` | `S-07`, `S-10` · Producto con venta, entrada y ajuste muestra historial completo y exportable. |
| 71 | `T78` · Existencias negativas | Aplicar una regla explícita de negativos en demo y entorno normal. | `build` | Prueba existente permite negativos. Falta política aprobada, advertencia y consistencia por caja. | `T-04` | `S-13`, `S-15` · Demo y producción aplican reglas distintas visibles. Ninguna escribe stock negativo por rebase de permisos. |
| 72 | `T79` · Proveedor en catálogo | Asignar y consultar proveedor desde catálogo sin cruzar negocios. | `duplicate` | Misma necesidad de relación proveedor-producto que 41. La consola actual no lo muestra. | `T-08` | Se cierra con 41 · Editar producto, asignar proveedor y probar aislamiento `S-15`. |
| 73 | `T80` · Recepción y aprobación en consola | Recibir distinto al pedido, registrar diferencia y publicar una sola vez. | `duplicate` | Repite el resultado de 44–47 con superficie web. | `T-08` | Se cierra con 44–47 · La recepción desde consola conserva diferencias y usa `S-05`, `S-08`. |
| 74 | `T81` · Detalle de fiado | Ver folio, saldo, vencimiento, estado e historial de abonos. | `build` | La consola tiene detalle y entries, pero faltan folio, vencimiento y estado de deuda. Auditoría estática, NO verificado. | `T-09` | `S-04` · Abrir adeudo y ver vencimiento, estado y abonos. Pago parcial no cierra. |
| 75 | `T82` · Contacto para avisos | Validar canal y consentimiento y manejar registros antiguos sin contacto. | `build` | El cliente acepta teléfono opcional. No hay validación, consentimiento ni aviso. | `T-09` | `S-04`, `S-18` · Crear cliente con canal válido y consentimiento. Registro legado sin contacto se muestra y permite corregir. |
| 76 | `T83` · Límites y bloqueo en consola | Configurar monto, mora y restricciones de nuevos créditos. | `duplicate` | La regla funcional pertenece a 51 y 57. La UI de consola es el canal, no una necesidad distinta. | `T-09` | Se cierra con 51 y 57 · Reglas, excepción y bloqueo se prueban en `S-04`. |
| 77 | `T84` · Detalle, ligas y cobros | Abrir deuda, crear liga y conciliar abonos sin duplicar. | `duplicate` | La parte de detalle/abono se relaciona con 54 y 58. La liga se mantiene diferida en 53. | `T-09` | Se cierra con 54 y 58 para detalle/abono. La liga permanece bloqueada hasta 53. |
| 78 | `T85` · Filtros de gastos | Filtrar gastos por periodo, categoría y responsable. | `build` | Gastos existen con lista y total del día. No hay categorías ni filtros. Auditoría estática, NO verificado. | `T-07` | `S-10` · Gastos de fechas, categorías y responsables distintos filtran con subtotales correctos. |
| 79 | `T86` · Identidad del registrante | Distinguir autor histórico de sesión actual y demostrar aislamiento. | `build` | Se guarda nombre de empleado en gastos, pero la identidad de API es declarativa y el PIN es compartido. | `T-02` | `S-08`, `S-15` · Una cuenta nueva no muestra registros ajenos. El autor del gasto coincide con la sesión verificada. |
| 80 | `T87` · Plantillas de tareas | Localizar aplicación de plantilla, generar tareas y asignarlas. | `build` | La plantilla se aplica en onboarding/API y Android muestra tareas. La consola no permite aplicar o editar desde su vista. | `T-03` | `S-01` · Negocio nuevo aplica plantilla, recibe tareas asignables y conserva activación. No duplica al reintentar. |
| 81 | `T88` · Conciliación CoDi en soporte | Inspeccionar y conciliar un evento con referencia, orden e importe correctos. | `build` | Soporte lista tickets y eventos PEY, pero no ofrece acción de conciliación por evento. Auditoría estática, NO verificado. | `T-10` | `S-03`, `S-08` · Abrir pendiente, expirado y pagado. Conciliar una vez sin doble cobro y con importe demo separado. |
| 82 | `T89` · Módulo de reportes | Navegar reportes por periodo, producto, empleado/caja e inventario con exportación y permisos. | `build` | La consola no tiene pestaña Reportes. `/api/reports/today` cubre solo hoy. | `T-07` | `S-10`, `S-14` · Cada reporte coincide con fuente, respeta permisos y navega a detalle con teclado. |
| 83 | `T90` · Ajustes de identidad y banco | Editar nombre, logo y cuenta receptora con validación y auditoría. | `duplicate` | La necesidad comercial se divide entre 2 y 3. La consola actual no edita logo ni CLABE. | `T-02` | Se cierra con 2 y 3 · Editar nombre/logo y cuenta con autenticación, validación y auditoría. |
| 84 | `T91` · Acceso a roles desde Ajustes | Abrir la gestión de equipo solo para el dueño. | `duplicate` | La gestión funcional es 64. Ajustes solo necesita un enlace autorizado. | `T-03` | Se cierra con 64 · El enlace aparece para dueño y el empleado queda bloqueado en servidor. |

## Verificación de cobertura

- Tarjetas incluidas: **85 de 85**.
- Referencias cortas únicas: **85**.
- Tarjetas de la guía inicial de Trello excluidas: **6**.
- Duplicado explícito: una tarjeta sin número que repite la necesidad 59. Las 84 tarjetas numeradas están presentes, del 1 al 84.
- No se incluyeron IDs internos del tablero, miembros, adjuntos ni datos personales de las capturas.

Comprobación reproducible del documento:

```bash
python3 - <<'PY'
from pathlib import Path
import re

path = Path("docs/produccion/trello-cobertura.md")
rows = []
for line in path.read_text(encoding="utf-8").splitlines():
    match = re.match(r"\|\s*(\d+|—)\s*\|\s*`([A-Za-z0-9]+)`", line)
    if match:
        rows.append(match.group(2))

assert len(rows) == 85, len(rows)
assert len(set(rows)) == 85, "hay referencias repetidas"
numbered = {int(line.split("|")[1].strip()) for line in path.read_text(encoding="utf-8").splitlines()
            if re.match(r"\|\s*\d+\s*\|\s*`[A-Za-z0-9]+`", line)}
assert numbered == set(range(1, 85)), sorted(set(range(1, 85)) - numbered)
print("85 tarjetas únicas, 84 numeradas, 6 starter excluidas")
PY
```

La verificación de referencia contra el export original se hizo durante la redacción. El documento no depende de `/Users/carlos/Downloads` para leerse o ejecutarse.
