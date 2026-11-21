# 03 · Flujos, ergonomía y aceptación física

## Uso por DSH

Este documento es la instrucción vigente para diseñar, implementar y verificar los flujos de trabajo de Abarpay. DSH significa DeepSeek Harness. La especificación parte de `main` en `75c1f35` y del estado documentado el 21-nov-2026. No supone que una columna de Trello pruebe una función.

Orden obligatorio para cada tarjeta de flujo:

1. El diseñador de operaciones, con criterio de ingeniería industrial, describe primero la operación física completa.
2. Un par programador revisa la secuencia, los estados, los contratos y las oportunidades de reducir pasos. Los dos comparan las alternativas contra el mismo escenario.
3. El implementador escribe el código dentro de las rutas permitidas por el paquete asignado.
4. Un verificador independiente deriva el resultado esperado del contrato, revisa la revisión exacta y ejecuta las comprobaciones automatizadas, de Android físico y de accesibilidad.
5. El coordinador acepta el paquete solo con evidencia reproducible. Una autocrítica del implementador no cierra el paquete.

DSH debe detenerse y registrar una decisión pendiente cuando falte un contrato de proveedor, una autorización externa, una credencial o una persona para la prueba física. Puede continuar con fixtures `SIMULADO` cuando la prueba no implique dinero ni datos reales.

## Baseline verificable

| Superficie | Estado observado en el código | Consecuencia para el diseño |
|---|---|---|
| Android | Pestañas Inicio, Cobrar, Fiado, Inventario y Reportes, con permisos por empleado. Existen efectivo, PEY/CoDi y fiado, invitaciones por liga o QR, catálogo, tareas, gastos y comprobante compartible. | El flujo actual sirve como base visual. La caja offline, la recepción de mercancía y el cierre de caja todavía requieren implementación. |
| Web | `/console` es la consola del dueño. `/invite/{token}` acepta invitaciones. `/` redirige a `/console`. | Todavía no existen landing pública, entrada por QR desde escritorio ni gestión SaaS separada. |
| API | Rutas de venta, inventario, catálogo, equipo, reportes, fiado y soporte bajo `/api`. Los cobros CoDi se confirman por webhook firmado o conciliación de servidor. | El teléfono no puede declarar pagada una venta CoDi. La UI debe reflejar estados de servidor. |
| Evidencia | Hay pruebas de servidor y Android para venta en efectivo, fiado, invitaciones, inventario, catálogo, CoDi e idempotencia. El worklog registra 183 pruebas de servidor, 154 unitarias Android y 16 legadas en `75c1f35`. | Esta revisión documental no volvió a ejecutar esas suites. Una implementación nueva necesita su propia evidencia. |

La base activa no debe servir como fixture ni como destino de datos sintéticos. Toda prueba usa una base aislada y datos identificables como `SIMULADO`.

## Límite funcional por conexión

| Operación | Sin conexión | Con conexión |
|---|---|---|
| Consultar catálogo y carrito | Último catálogo sincronizado, precio y existencia proyectada, con hora de sincronización visible. | Actualizar precio, disponibilidad y reservas vigentes. |
| Cobrar efectivo | Finalizar una vez, generar comprobante local con referencia estable, registrar movimiento de efectivo y descontar la existencia proyectada. | Publicar la venta, conciliar inventario y hacerla visible en otras cajas. |
| Emitir comprobante | Imagen o PDF local del importe, líneas, medio de pago, referencia y marca de sincronización pendiente. | Confirmar la referencia central y permitir nueva descarga o reenvío. |
| Recibir mercancía | Registrar cantidades físicas, diferencias, responsable y comprobante local contra un pedido en caché. | Aprobar la entrada, resolver duplicados o conflictos y publicar existencia. |
| Preparar fiado | Crear un borrador de cargo o abono con el saldo en caché. | Validar saldo, límite, elegibilidad y autorización antes de finalizar. |
| Cobrar CoDi, invitar, cambiar banco o aprobar acceso web | Conservar el contexto y explicar qué hace falta. | Autenticar, generar el QR, confirmar el pago o completar el cambio. |
| Cerrar caja | Contar efectivo, guardar el conteo y el borrador de entrega. | Finalizar cuando las operaciones requeridas estén sincronizadas y el dueño acepte la entrega. |

El efectivo se cobra sin conexión. El fiado se finaliza con conexión. CoDi, identidad, banco y aprobación web requieren servidor. Los borradores de fiado pueden prepararse sin red y nunca aumentan la deuda ni reducen la recaudación hasta que el servidor los confirma.

## Actores y entorno

| Actor | Objetivo operativo | Restricciones principales |
|---|---|---|
| Dueño | Cobrar, controlar deuda, reponer, conciliar y administrar equipo | Puede operar desde teléfono o consola web. Las acciones de dinero y datos requieren identidad verificada y membresía activa. |
| Empleado de caja | Completar una venta presencial con rapidez y recuperar el trabajo tras una interrupción | Solo ve la tienda y las funciones autorizadas. No administra banco, permisos ni reportes del dueño. |
| Cliente | Pagar y recibir un comprobante entendible | Puede no tener la app. Sus datos de pago se muestran solo lo necesario. |
| Contador | Revisar Formalización cuando el dueño la contrate | Sus honorarios y acceso se acuerdan por separado. |
| Personal interno de Abarpay | Operar suscripciones, soporte y pilotos de datos | Acceso mínimo, auditado y separado del comerciante. Los analistas ven agregados por defecto. |

El puesto real suele tener luz variable, una mano ocupada, clientes esperando, llamadas, bloqueo de pantalla y conectividad irregular. La secuencia más corta debe seguir siendo segura, recuperable y comprensible sin capacitación técnica extensa.

## Escenarios compartidos

Las tarjetas de cobertura citan estos identificadores. Cada escenario se puede ejecutar contra una base limpia o un fixture `SIMULADO`.

| ID | Dado | Cuando | Entonces |
|---|---|---|---|
| `S-01` | Una tienda nueva sin datos de demostración | El dueño completa el alta y crea su primer producto | No aparecen empleados, clientes ni catálogo ajenos. La primera venta en efectivo se puede completar y el estado sobrevive al reinicio. |
| `S-02` | El teléfono está en modo avión y tiene catálogo sincronizado | El cajero cobra en efectivo y el cliente paga con cambio | La venta se finaliza una vez, el comprobante local muestra importe, cambio y referencia. La existencia proyectada baja. El estado pasa a pendiente de sincronizar. |
| `S-03` | Hay una venta CoDi pendiente | El cliente escanea el QR pero el servidor aún no confirmó | La UI sigue en pendiente y no suma dinero cobrado. Una captura o el QR no alteran el estado. |
| `S-04` | Un cliente tiene saldo | El empleado registra una venta fiada | El servidor valida cliente, límite y permiso. La deuda sube una vez, la existencia baja una vez y la recaudación no aumenta. |
| `S-05` | Un pedido está en caché y no hay red | El empleado recibe una cantidad física distinta | Se guarda cantidad recibida, diferencia, actor y comprobante local. No se publica stock central antes de aprobar. |
| `S-06` | Hay ventas en efectivo del turno | El cajero cuenta, declara y entrega el efectivo | El dueño ve esperado, contado, diferencia y responsables. La caja solo queda aceptada tras la revisión del dueño. |
| `S-07` | Dos cajas sincronizan | Ambas venden la última unidad estando desconectadas | Las dos ventas en efectivo se conservan, cada una se publica una vez y se abre una diferencia de inventario auditable. No se borra un recibo. |
| `S-08` | Una operación ya se aplicó en el servidor | La respuesta se pierde antes del acuse al teléfono | El reintento devuelve el mismo resultado y no duplica venta, recibo, pago, deuda ni movimiento. |
| `S-09` | El dueño abre la consola en escritorio | Escanea el QR con su teléfono y confirma la tienda | La sesión queda ligada al navegador iniciador. Un código vencido, reutilizado o de otra cuenta falla con una acción clara. |
| `S-10` | Hay ventas, fiado y gastos | El dueño abre reportes y exporta | Cada total declara periodo, fuente y tratamiento de cancelados, pendientes y abonos. La exportación coincide con la pantalla y conserva historial. |
| `S-11` | El cajero está capturando un cobro | Llega una llamada, se bloquea la pantalla o el sistema mata la app | Al regresar aparecen importe, medio, cliente y estado. La operación se reanuda en el siguiente paso seguro sin doble envío. |
| `S-12` | Hay trabajo local pendiente | Se recupera la red después de un cierre forzado | La cola se reanuda y muestra pendiente, sincronizado o requiere atención. Un fallo de red no descarta el trabajo. |
| `S-13` | Un producto tiene existencia cero o negativa | Se intenta vender o ajustar | Mostrar disponibilidad y auditar ajustes. Si dos cajas desconectadas vendieron la última unidad, honrar ambas ventas, conservar el déficit y abrir varianza al dueño. |
| `S-14` | Una persona usa TalkBack, teclado externo, texto al 200% o alto contraste | Recorre un flujo completo | Todos los controles tienen nombre, estado, orden y foco útiles. Nada depende solo del color. No hay texto cortado ni objetivos menores de 48 dp en Android. |
| `S-15` | Existen dos tenants de prueba con una tienda cada uno | Una intenta leer o modificar datos de la otra por URL, caché, invitación, exportación o trabajo | El servidor y los jobs respetan la membresía. La caché se separa y no aparece información cruzada. |
| `S-16` | El proveedor no ofrece una función o responde con error | Se elige push, liga, terminal o CoDi no configurado | La UI lo marca como no disponible o pendiente. No crea un cobro falso ni muestra un resultado exitoso. |
| `S-17` | Un visitante de la landing usa móvil o escritorio | Pulsa `Empezar gratis`, `Entrar a mi tienda` o el APK piloto | Llega a un destino real y accesible, o ve una explicación honesta del estado y la siguiente acción. |
| `S-18` | Una tienda gratuita participa o no en el piloto agregado | Cambia de opinión y solicita historial | La participación está apagada por defecto. Historial y exportación siguen disponibles. La revocación tiene instrucciones y efecto verificable. |

## Tarjeta de flujo obligatoria

Antes de escribir UI, el diseñador de operaciones abre una tarjeta con este contenido:

| Campo | Contenido mínimo |
|---|---|
| Actor y puesto | Persona, tienda, dispositivo, rol y si usa una o dos manos. |
| Disparador | Qué inicia el flujo y qué información ya está disponible. |
| Entorno | Mostrador, bodega, teléfono personal, luz, red, ruido y tiempo de espera. |
| Secuencia segura mínima | Pasos indispensables, decisión irreversible y punto de confirmación. |
| Información en el momento | Precio, existencia, saldo, importe, cambio, estado o advertencia necesarios para decidir. |
| Resultado observable | Qué ve el actor y qué queda registrado cuando termina. |
| Errores caros | Pago duplicado, venta perdida, stock falso, deuda cruzada, recibo incorrecto o acceso indebido. |
| Interrupción | Evento probable, estado persistido y siguiente acción segura. |
| Métrica de esfuerzo | Toques, tiempo hasta confirmación, correcciones y recuperaciones fallidas. |

El par programador revisa la tarjeta y responde por escrito cuatro preguntas. ¿Qué paso se puede eliminar? ¿Qué dato debe venir del servidor? ¿Qué ocurre si el actor se distrae? ¿Cómo se demuestra que la alternativa es más segura y no solo más corta? El coordinador registra la decisión aceptada y su motivo.

## Reglas de interacción

1. Cada toque recibe confirmación local inmediata. Un objetivo de 100 ms es la meta práctica. Si una operación tarda más de 300 ms, la UI muestra progreso concreto.
2. El estado durable manda para dinero, inventario, deuda, correo y sincronización. Un spinner no convierte una operación en exitosa.
3. Los campos se conservan ante error de red o validación. Los botones de envío se deshabilitan mientras la solicitud está en curso y se vuelven a habilitar con una acción de reintento segura.
4. Cada acción destructiva pide confirmación solo cuando puede perder dinero, stock o datos. La cancelación de un QR pendiente y la eliminación de una venta completada tienen consecuencias distintas.
5. El estado se anuncia a tecnología de asistencia. Los mensajes usan verbos observables, por ejemplo `Venta registrada`, `Pago pendiente de confirmación`, `Guardado en el teléfono`, `Requiere atención`.
6. El color acompaña al texto y al icono. El importe, el medio y el estado nunca se identifican solo por verde, rojo o amarillo.
7. La pantalla conserva carrito, cliente, importe recibido y método al rotar, bloquear o volver del reconocimiento de voz.
8. El dueño puede ver quién registró cada movimiento autorizado. El nombre mostrado debe provenir de una sesión o membresía verificada, no de un encabezado elegido por el cliente.
9. Las funciones no disponibles se muestran como tales. No se simula un pago, una impresora, una terminal ni un envío que el sistema no puede completar.
10. Toda pantalla admite texto al 200%, teclado o TalkBack sin ocultar la acción principal ni el estado de la operación.

## Flujos

### F-01 · Alta, primer producto y primera venta

Ingeniería industrial primero. El dueño llega con una tienda abierta o en preparación, puede estar usando datos móviles y necesita un resultado útil antes de terminar toda la configuración. El avance se guarda en cada paso. Banco, invitaciones y participación de datos se ofrecen como tareas separadas.

Par programador. Reduce la ruta inicial a identidad verificada, nombre de tienda, primer artículo y venta de prueba en efectivo. Las tareas posteriores muestran qué desbloquean. No usa personal de ejemplo, un nombre heredado ni catálogo de otra tienda.

Acciones:

1. Verificar la identidad del dueño y crear o elegir la tienda.
2. Capturar nombre, tipo de negocio y primer artículo con precio y unidad.
3. Entrar al inicio con la tienda vacía o con el artículo creado.
4. Iniciar una venta en efectivo, capturar recibido y confirmar el cambio.
5. Mostrar el comprobante y la siguiente tarea útil, como invitar personal o recibir CoDi.

Interrupciones. Si se cierra la app, reabrir en el paso pendiente. Si la tienda ya se creó, no duplicarla. Si la primera venta quedó incierta, consultar su referencia antes de repetirla.

Aceptación. `S-01`, `S-11`, `S-14` y `S-15`. Prueba automática con base limpia. Prueba en Android físico desde instalación firmada, con reinicio después del alta y venta de un artículo. Auditoría WCAG 2.2 AA equivalente del recorrido.

### F-02 · Venta en efectivo y comprobante offline

Ingeniería industrial primero. El cajero consulta productos, arma el carrito, recibe billetes y calcula cambio. La red puede caer antes o después de tocar `Cobrar en efectivo`. El cliente necesita un comprobante antes de salir.

Par programador. La venta, el comprobante, el movimiento de efectivo y los movimientos de inventario forman una operación local atómica. Cada línea y la venta llevan IDs inmutables. La sincronización envía una operación individual y acepta acuse idempotente.

Acciones:

1. Buscar o escanear producto y fijar cantidad.
2. Revisar líneas, total y existencia proyectada.
3. Elegir Efectivo, capturar recibido y mostrar cambio.
4. Confirmar una sola vez.
5. Mostrar referencia local, estado de sincronización y opciones de comprobante.
6. Sincronizar al recuperar conexión o a solicitud explícita.

Interrupciones. Llamada o bloqueo durante el carrito, doble toque, cierre forzado, reinicio, caída de red, respuesta perdida después del commit y conflicto de última unidad.

Aceptación. `S-02`, `S-07`, `S-08`, `S-11`, `S-12` y `S-14`. En modo avión, cobrar, emitir comprobante, forzar detención, reiniciar teléfono y reconectar. Verificar una venta central, un comprobante, un movimiento por línea y un ingreso de efectivo. Repetir la entrega y comprobar una sola aplicación. TalkBack debe leer total, cambio, estado y referencia.

### F-03 · Cobro CoDi con confirmación verificada

Ingeniería industrial primero. El cliente escoge CoDi, ve el importe y escanea. Puede haber demora, vencimiento, cambio de red y pago tardío. El cajero necesita distinguir `Pendiente`, `Por conciliar`, `Pagada` y `Vencida` sin inferir éxito por una captura.

Par programador. Cada intento conserva tienda, venta, cuenta receptora, QR y transacción. La creación exige una cuenta activa de la tienda. El servidor aplica pago, inventario y comprobante de forma idempotente mediante el camino oficial de pago.

Acciones:

1. Elegir CoDi y revisar importe comercial y modo demo.
2. Generar el QR solo con cuenta activa y mostrar vigencia.
3. Consultar el estado con un indicador entendible y sin sumar recaudación.
4. Actualizar a pagado solo con respuesta confirmada del servidor.
5. Ofrecer comprobante y próxima venta. En caso incierto, conservar referencia y permitir consulta o soporte.

Interrupciones. Cierre de app mientras el QR está activo, vencimiento, timeout de creación, pago después de cancelar, webhook duplicado, cambio de red y cuenta bancaria inactiva.

Aceptación. `S-03`, `S-08`, `S-11`, `S-15` y `S-16`. Prueba automatizada con proveedor falso marcado `SIMULADO`. En Android físico verificar QR, pendiente, rotación, pantalla bloqueada y recuperación. La prueba con dinero real queda reservada a una persona autorizada y un pago de MXN 0.01. WCAG AA para estado, importe, vigencia y acciones.

### F-04 · Fiado en línea

Ingeniería industrial primero. El cliente conocido pide llevarse productos y pagar después. El empleado necesita saber el saldo, el límite, el vencimiento y si puede autorizar. Una venta fiada no es dinero cobrado. Un abono parcial no cierra la deuda.

Par programador. El cargo y el abono se validan en línea. El servidor deriva la sesión, la membresía y el actor. El teléfono puede preparar un borrador offline pero no finalizar deuda, cambio de límite ni excepción. La operación es idempotente y el historial conserva cargo, abono, actor y fecha.

Acciones:

1. Buscar o crear cliente con los datos mínimos y consentimiento de contacto cuando aplique.
2. Revisar saldo, deuda vencida, límite y elegibilidad actual.
3. Registrar importe, fecha límite y condiciones de forma comprensible.
4. Confirmar el cargo y descontar stock una vez sin sumar recaudación.
5. En una cobranza, capturar abono parcial o liquidación y mostrar el saldo nuevo.

Interrupciones. Pérdida de red al confirmar, doble abono, liquidación concurrente, cliente sin contacto, cambio de límite y relevo de caja a mitad del flujo.

Aceptación. `S-04`, `S-08`, `S-11`, `S-14` y `S-15`. En Android físico, preparar un borrador sin red y comprobar que no afecta saldo. Reintentar un abono con la misma operación y verificar un solo movimiento. Lectura accesible de saldo, vencimiento y estado.

### F-05 · Recepción física de mercancía sin red

Ingeniería industrial primero. La persona recibe cajas en bodega, cuenta lo que llegó y anota diferencias contra el pedido. La red puede faltar y la pantalla se usa con las manos ocupadas. El resultado no debe inflar la existencia disponible antes de la revisión.

Par programador. El pedido se guarda en caché con productos y cantidades esperadas. La recepción crea una operación local con cantidades observadas, diferencias, actor y comprobante. La aprobación y publicación central requieren conexión y permiso.

Acciones:

1. Abrir el pedido recibido o buscarlo en caché.
2. Confirmar proveedor, folio y fecha física.
3. Capturar cantidad recibida por producto.
4. Mostrar faltantes o sobrantes y pedir motivo cuando existan.
5. Guardar el comprobante local y el estado `Pendiente de aprobar`.
6. Sincronizar, revisar y aprobar la entrada una sola vez.

Interrupciones. Cierre forzado, batería baja, red intermitente, doble recepción, producto no previsto, cambio de responsable y aprobación simultánea desde la consola.

Aceptación. `S-05`, `S-07`, `S-08`, `S-12` y `S-14`. En Android físico sin red, recibir 8 de 10, guardar, forzar detención, reiniciar y sincronizar. Verificar una entrada, diferencia visible y comprobante local. La aprobación central publica existencia una sola vez. WCAG AA en captura, diferencia, estado y acciones.

### F-06 · Cierre, entrega y aceptación de efectivo

Ingeniería industrial primero. Al final del turno, el cajero cuenta el efectivo físico, declara entregado y el dueño confirma recepción o registra una diferencia. La cifra esperada excluye QR, fiado y terminales. La caja no está conciliada solo porque el empleado terminó de capturar.

Par programador. El cierre conserva apertura, ventas en efectivo sincronizadas, abonos cobrados aplicables, gastos, esperado, contado, diferencia, entrega y aceptación. Las operaciones pendientes impiden un cierre final o se muestran en una lista explícita.

Acciones:

1. Preparar el corte con periodo y caja visibles.
2. Mostrar efectivo esperado y operaciones pendientes.
3. Capturar contado y motivo cuando haya diferencia.
4. Registrar entrega con fecha, actor y comprobante.
5. El dueño revisa y acepta o marca discrepancia.
6. Cerrar el turno con estado final y siguiente acción.

Interrupciones. Ventas sin sincronizar, recarga de pantalla, entrega parcial, dueño ausente, doble toque y corrección después de aceptada.

Aceptación. `S-06`, `S-08`, `S-12` y `S-14`. Tres ventas en efectivo de MXN 80 cada una, esperado MXN 240. Entregar 240 y aceptar. Repetir con 220 y comprobar diferencia y estado no aceptado. Prueba física en Android y consola web, con lectura de totales y foco correcto.

### F-07 · Alerta de reposición y pedido a proveedor

Ingeniería industrial primero. El dueño revisa alertas de bajo stock, decide qué comprar y arma un pedido. El empleado puede recibirlo después. El flujo separa sugerencia, aprobación y entrada física.

Par programador. La alerta enlaza producto, existencia, mínimo y proveedor autorizado. El pedido tiene folio, cantidades, unidad, estado y aprobación. Enviar o recibir solo cambia la existencia por el flujo aprobado.

Acciones:

1. Abrir alerta desde Inicio o Inventario.
2. Revisar producto, existencia, mínimo y proveedor.
3. Agregar cantidad propuesta y otros artículos.
4. Revisar total, unidad y condiciones.
5. Aprobar y compartir o enviar el pedido por el canal disponible.
6. Recibir mercancía mediante F-05.

Interrupciones. Sin proveedor asignado, envío externo incierto, pedido duplicado, cantidades distintas y aprobación simultánea.

Aceptación. `S-05`, `S-08`, `S-10` y `S-16`. Seleccionar un producto agotado desde Inicio y verificar que llega al pedido con producto y cantidad precargados. Si el envío externo no está disponible, mostrar borrador y siguiente acción sin afirmar entrega.

### F-08 · Catálogo, inventario y códigos

Ingeniería industrial primero. El dueño mantiene nombre, unidad, precio, categoría, existencia o servicio. El empleado consulta y opera dentro de sus permisos. La búsqueda y el escaneo ocurren con clientes esperando.

Par programador. El precio siempre viene de la base. El servidor valida unidad, tipo, stock y límites. Un cambio de precio no reescribe ventas pasadas. Los movimientos guardan motivo, actor, fecha y vínculo.

Acciones:

1. Buscar, filtrar o escanear.
2. Consultar precio y disponibilidad con texto explícito.
3. Crear o editar un artículo según permiso.
4. Ajustar existencia con motivo y ver rastro.
5. Confirmar que la interfaz de cobro refleja datos actuales o la hora de la última sincronización.

Interrupciones. Código desconocido, imagen rota, producto sin stock, precio desactualizado, borrado con ventas y dos ediciones concurrentes.

Aceptación. `S-01`, `S-07`, `S-11`, `S-13` y `S-14`. S-13 en demo y en entorno normal. Android físico con búsqueda, escaneo, texto al 200% y TalkBack. La consola debe permitir el mismo resultado autorizado con teclado y foco visible.

### F-09 · Invitación, acceso y relevo de personal

Ingeniería industrial primero. El dueño invita a una persona, esta acepta con su propio nombre y recibe solo las tareas de la tienda correcta. Un cambio de turno no puede mezclar carritos, cobros pendientes ni datos de otra persona.

Par programador. La invitación expira y se consume una vez. La sesión y membresía determinan la tienda y permisos. El cierre de sesión no descarta trabajo local autorizado. La revocación bloquea nuevas finalizaciones y deja la recuperación de operaciones pendientes a una persona autorizada.

Acciones:

1. El dueño genera liga o QR con tienda, rol y vencimiento.
2. El empleado ve la identidad de la tienda y acepta con su nombre.
3. El servidor crea o activa la membresía una vez.
4. La app muestra solo pestañas y acciones permitidas.
5. El dueño revoca o cambia permisos desde una superficie de equipo.

Interrupciones. Enlace vencido, enlace reutilizado, instalación sin perfil, cambio de teléfono, revocación con trabajo pendiente y segundo empleado en el mismo dispositivo.

Aceptación. `S-08`, `S-11`, `S-14` y `S-15`. En Android físico, aceptar invitación por QR y por liga. Antes de aceptar no se puede vender. Después, el empleado no administra banco ni permisos. La pantalla de revocación debe explicar cómo conciliar trabajo pendiente.

### F-10 · Reportes, conciliación y exportación

Ingeniería industrial primero. El dueño revisa el día y detecta diferencias. Necesita saber qué significa cada cifra antes de decidir. La fecha del negocio es Ciudad de México.

Par programador. Cada indicador declara periodo, fuente, deduplicación y tratamiento de cancelados, pendientes y abonos. La exportación usa los mismos datos y los mismos filtros que la pantalla. Los roles sin permiso no acceden al detalle.

Acciones:

1. Elegir periodo y tienda.
2. Revisar vendido, cobrado, fiado, pendiente y gastos con definiciones visibles.
3. Filtrar por empleado, caja o medio de pago.
4. Abrir una venta o evento que explique una diferencia.
5. Exportar y comparar totales antes de compartir.

Interrupciones. Datos pendientes de sincronización, cancelación tardía, pago CoDi no confirmado, exportación interrumpida y cambio de zona horaria.

Aceptación. `S-10`, `S-12`, `S-14` y `S-15`. Fixture `SIMULADO` con ventas pagadas, crédito y pendientes. Las cifras de pantalla y archivo deben coincidir. En web, operar con teclado y lector de pantalla. En Android, totales y estados se leen completos.

### F-11 · Entrada del dueño a la consola por QR

Ingeniería industrial primero. El dueño está en una computadora y su teléfono ya tiene una sesión. Quiere abrir su tienda sin escribir una contraseña compartida. Debe poder negar un intento ajeno y recuperarse de un código vencido.

Par programador. La consola crea un desafío único ligado al navegador. El teléfono muestra tienda y navegador solicitante. La aprobación usa autenticación del dispositivo. El intercambio crea una sesión HttpOnly, Secure y SameSite. La reutilización, cuenta incorrecta o membresía revocada falla.

Acciones:

1. Abrir `Entrar a mi tienda`.
2. Mostrar QR y código corto, con vencimiento.
3. Escanear desde la app del dueño y revisar tienda y navegador.
4. Aprobar o negar explícitamente.
5. La computadora obtiene la sesión y entra a la consola correcta.

Interrupciones. Cámara sin permiso, rotación, red caída, desafío vencido, navegador cerrado, aprobación desde otra cuenta y sesión revocada.

Aceptación. `S-09`, `S-11`, `S-14` y `S-15`. Alternativa sin cámara mediante código manual. Android físico para aprobar o negar. Web con teclado y lector. Verificar reutilización, navegador distinto y vencimiento.

### F-12 · Landing, alta y continuidad hasta la primera venta

Ingeniería industrial primero. Un dueño llega desde una campaña o recomendación, compara la promesa con lo que puede hacer y elige empezar. La transición debe conservar campaña, versión de la página y consentimiento sin capturar datos bancarios o de clientes en analítica.

Par programador. `Empezar gratis`, `Entrar a mi tienda` y el APK piloto llevan a destinos reales. Si una ruta no está habilitada, la página lo explica y ofrece una acción disponible. La medición distingue visita, registro verificado, tienda creada, primera venta, Control pagado, devolución y retención.

Acciones:

1. Leer una promesa comprobable y ver el producto real.
2. Elegir alta móvil, entrada QR o APK piloto firmado según su caso.
3. Completar identidad y tienda sin datos de ejemplo ajenos.
4. Completar la primera venta en efectivo o la primera tarea útil.
5. Registrar el resultado de atribución sin datos sensibles.

Interrupciones. Alta abandonada, instalación sin permiso, APK aún no publicado, campaña sin costos y retorno desde QR vencido.

Aceptación. `S-17`, `S-11`, `S-14` y `S-18`. Cada CTA tiene prueba de destino. La landing usa WCAG 2.2 AA, teclado y móvil. La conversión se mide solo con eventos consentidos. La copia comercial completa vive en `06-landing-y-comercial.md`.

## Requisitos de accesibilidad

La meta es WCAG 2.2 nivel AA en web y comportamiento equivalente en Android. La norma aplicable es [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

| Área | Criterio de aceptación |
|---|---|
| Contraste | Texto normal con relación mínima 4.5:1 y texto grande con 3:1. Estados, bordes y foco también cumplen. Una captura en brillo alto confirma legibilidad. |
| Texto | Contenido y acciones funcionan al 200% sin recorte ni pérdida de información. Los importes no se superponen con botones. |
| TalkBack | Cada control tiene nombre y estado útil. El orden lee actor, producto, cantidad, total, medio y estado de confirmación. Los mensajes nuevos se anuncian. |
| Teclado y foco | La web completa sus flujos con teclado, foco visible y orden lógico. Diálogos atrapan y devuelven el foco correctamente. |
| Objetivos táctiles | En Android, controles de uso frecuente de al menos 48 por 48 dp. En web, al menos 24 por 24 CSS px y espaciado suficiente. |
| Color y forma | Estado, diferencia u obligatoriedad llevan texto o icono además de color. Ninguna decisión depende solo del tono. |
| Errores | El mensaje se asocia al campo, explica cómo corregir y conserva lo capturado. El foco llega al primer error pertinente. |
| Movimiento | Se respeta la reducción de movimiento. Las animaciones no bloquean la operación ni son la única señal de resultado. |
| Tiempo | Un vencimiento informa qué ocurrió y ofrece regenerar o reintentar. No se pierde un carrito por expirar un QR. |

## Protocolo de aceptación en Android físico

1. Instalar un APK firmado y registrar versión, código, SHA-256 y revisión fuente.
2. Usar una tienda de prueba y datos sintéticos. Confirmar que no se conecta a la base activa.
3. Ejecutar `S-02` en modo avión. Guardar recibo, forzar detención, reiniciar el teléfono y reconectar.
4. Ejecutar `S-05` sin red con un pedido en caché, diferencia de cantidad y cierre forzado.
5. Interrumpir una venta con llamada, bloqueo de pantalla, rotación y regreso desde el selector de voz.
6. Repetir la entrega de una operación aunque el servidor ya la hubiera aplicado. Confirmar una sola escritura.
7. Probar la última unidad desde dos cajas aisladas y verificar la diferencia auditable.
8. Probar `S-04` sin red y comprobar que solo se conserva un borrador. Finalizarlo al reconectar.
9. Revisar toda la pantalla con TalkBack, texto al 200%, teclado externo cuando exista y brillo bajo y alto.
10. Adjuntar capturas, video corto o registro de accesibilidad, versión del sistema Android y cualquier fallo observado.

Una prueba en emulador o Robolectric puede descubrir regresiones. Solo la prueba física acepta un flujo que depende de red, cámara, teclado, batería o comportamiento del sistema.

## Copy de estado

| Situación | Texto permitido | Texto prohibido |
|---|---|---|
| Efectivo offline | `Cobro en efectivo guardado en el teléfono. Se sincronizará al volver la conexión.` | `Sincronizado` o `Cobrado en la nube` antes del acuse. |
| CoDi pendiente | `Pago pendiente de confirmación. Revisa el estado antes de entregar.` | `Pagado` por mostrar el QR o una captura. |
| CoDi confirmado | `Pago confirmado por el servidor.` | `Pago confirmado por el banco` cuando no se verificó esa fuente. |
| Fiado | `Fiado registrado. Saldo pendiente: MXN …` | `Cobrado` o `Ingreso recibido`. |
| Recepción pendiente | `Mercancía recibida en este teléfono. Falta aprobación para publicar existencia.` | `Inventario actualizado` antes de la aprobación central. |
| Cola con problema | `Requiere atención. Conservamos los datos y te mostramos cómo resolverlo.` | `Error` sin siguiente acción. |

## Condición de cierre para DSH

Un paquete de flujo se considera aceptado cuando tiene tarjeta de operación revisada por ingeniería industrial y par programador, contrato de datos, acciones implementadas, estados de interrupción recuperados, pruebas automatizadas pertinentes, prueba en Android físico, auditoría WCAG AA y evidencia de la revisión exacta. Los pendientes externos quedan en la cola humana con dueño y condición de desbloqueo.
