# 06 · Landing pública, oferta y APK piloto

## Uso por DSH

Este documento es la instrucción completa para la página pública de Abarpay, la oferta comercial y la distribución del APK piloto. DSH significa DeepSeek Harness. La base de código es `main` en `75c1f35`, revisada el 21-nov-2026.

El alcance público confirma una oferta de autoservicio `Gratis`, un piloto `Control` de MXN 149 por tienda al mes con cobro manual, y una invitación a expresar interés en el futuro piloto guiado `Formalización` de MXN 399 al mes durante tres meses. El dossier financiero es una investigación futura. La distribución del piloto usa un APK Android firmado en el dominio del producto.

DSH debe seguir este orden:

1. Implementar primero la página y sus estados reales con datos y precios versionados.
2. Conectar cada CTA a un destino existente. Un botón sin destino o un enlace que promete una función no publicada bloquea el paquete.
3. Instrumentar eventos de campaña, visita, CTA, registro verificado, tienda creada, primera venta, Control pagado, devolución y retención, sin datos bancarios ni datos de clientes.
4. Verificar afirmaciones contra la build desplegada, la versión del APK y el contrato de cada flujo.
5. Validar responsividad, teclado, lector de pantalla, contraste y reducción de movimiento antes de aceptar.

Un cambio de precio, una promesa comercial nueva o una prueba con dinero requiere autorización del responsable del producto. La página puede usar fixtures `SIMULADO` para producto y métricas mientras la implementación real avanza.

## Estado actual y destinos

| Ruta | Estado en `75c1f35` | Uso público requerido |
|---|---|---|
| `/` | Redirige a `/console`. | Mostrar la landing pública. La consola queda en una ruta separada. |
| `/console` | Consola del dueño con PIN compartido y vistas de tienda. | Uso interno durante la transición. La meta es entrada del dueño por QR y sesión propia. |
| `/invite/{token}` | Página de invitación con enlace a la app. | Mantenerla y probar liga vencida, reutilizada y aceptación correcta. |
| `/empezar` | No existe. | Destino del CTA `Empezar gratis`. Debe abrir alta real o una lista de espera honesta, con estado visible. |
| `/entrar` | No existe. | Destino del CTA `Entrar a mi tienda`. Debe iniciar el desafío de acceso por QR. |
| `/apk-piloto` | No existe. | Entrega del APK firmado o explicación del estado del piloto. Nunca sirve un archivo sin firma ni hash. |

DSH puede usar otras rutas si el coordinador las aprueba, siempre que cada CTA tenga una prueba de destino y no quede un enlace muerto.

## Posicionamiento

La landing vende control operativo para una tienda pequeña. La promesa central es cobrar, saber quién debe y reponer con información del negocio. La prueba es el producto real en operación, no una lista abstracta de tecnología.

| Elemento | Decisión |
|---|---|
| Público | Dueño de tiendita o negocio pequeño en México que cobra en efectivo, paga CoDi y anota deudas. |
| Trabajo principal | Cerrar una venta, cobrar una deuda y decidir qué comprar sin perder claridad. |
| Objetivo a demostrar antes de publicarlo | Efectivo y comprobantes disponibles sin conexión, fiado en línea con saldo e historial, CoDi con confirmación del servidor y stock compartido al sincronizar. |
| Tono | Directo, operativo y en español mexicano. Habla de la tienda, no de la arquitectura. |
| Prueba visual | Capturas o grabación del build aceptado, con datos ficticios etiquetados. |
| Autoridad de precios | Tabla versionada del producto. Un experimento no cambia el precio cobrado. |

## Reglas de veracidad

| Capacidad | Afirmación permitida | Afirmación prohibida |
|---|---|---|
| Efectivo offline | `Registra ventas en efectivo y comprobantes en el teléfono cuando no hay señal.` | `Todo Abarpay funciona sin internet.` |
| Fiado | `Consulta saldos y registra cargos o abonos con conexión.` | `Autoriza fiado sin conexión` o `cobra deudas automáticamente`. |
| CoDi | `Muestra el QR y confirma el pago cuando el servidor lo verifica.` | `Pago garantizado`, `dinero inmediato` o `sin riesgo`. |
| Inventario | `Comparte existencias cuando las cajas se sincronizan. Las diferencias se revisan.` | `Inventario exacto en tiempo real` sin prueba de cada caja. |
| Comunidad | `Participación opcional, apagada por defecto, con beneficio y retiro explicados.` | `Vendemos tus datos` o `datos anónimos garantizados`. |
| Seguridad | `Datos separados por tienda y accesos por membresía.` | `100% seguro`, `bancos certifican todo` o una certificación no obtenida. |
| APK piloto | `Instala una versión firmada, verificable y con sus notas de versión.` | `Descarga el APK` junto a un archivo sin firma, sin hash o de origen desconocido. |
| Formalización | `Piloto guiado de tres meses, sin renovación automática y con contador externo.` | `Trámite fiscal incluido`, `contador incluido` o `dossier bancario disponible`. |

No se publica un número de clientes, ahorro, aumento de ventas, tiempo de activación o beneficio del piloto de datos sin fuente, fecha, muestra y método. Si falta alguno, la sección muestra `Sin datos suficientes` o se omite.

## Copia de la primera pantalla

### Navegación

- Marca enlazada a `/`.
- Enlaces `Cómo funciona`, `Planes`, `Preguntas`.
- CTA secundario `Entrar a mi tienda`.

### Contenido exacto

**H1**

> Cobra, controla lo que te deben y sabe qué reponer.

**Párrafo**

> Abarpay reúne la venta, el efectivo, el fiado, el inventario y CoDi en el teléfono de tu tienda. El efectivo y sus comprobantes quedan en el teléfono cuando falla la conexión. Al volver la señal, todo se sincroniza para que tu equipo trabaje con el mismo estado.

**CTA principal**

> Empezar gratis

**CTA de regreso**

> Entrar a mi tienda

**CTA de piloto**

> Instalar APK piloto firmado

**Microcopia bajo los botones**

> Gratis incluye historial y exportación. Control cuesta MXN 149 por tienda al mes y se cobra manualmente. La web no procesa cargos automáticos.

**Prueba visual**

La imagen principal muestra una venta en efectivo con cambio, el estado `Guardado en el teléfono` y un comprobante. Si el build aceptado no contiene esa función, la imagen y la promesa de offline se retiran hasta que exista evidencia.

## Secciones de la página

### 1. La operación de hoy

**Título**

> Tu tienda, en orden desde el primer cobro.

**Copia**

> Abre el catálogo, cobra, registra un gasto y revisa lo que pasó hoy. El dueño ve la tienda completa. Cada empleado ve solo lo que necesita para su turno.

Tres pruebas visuales, cada una con etiqueta `SIMULADO` cuando use datos ficticios:

1. `Cobrar` con productos, total y cambio.
2. `Inicio` con ventas, cobrado, fiado por cobrar y productos bajos.
3. `Inventario` con existencia, último movimiento y alerta de reposición.

### 2. Efectivo y comprobantes sin conexión

**Título**

> La caja sigue cuando la señal no.

**Copia**

> Cobra en efectivo, calcula el cambio y entrega un comprobante con una referencia estable aunque no haya internet. El teléfono conserva la venta y el movimiento de existencia. Al reconectar, envía la operación una sola vez y muestra si quedó pendiente, sincronizada o necesita atención.

**Aclaración**

> CoDi, fiado, invitaciones y cambios de cuenta necesitan conexión. Abarpay muestra qué se puede terminar en el teléfono y qué falta del servidor.

**Prueba requerida**

Video corto del teléfono en modo avión, una venta, el comprobante, el reinicio y la sincronización. La grabación se reemplaza si la versión cambia.

### 3. CoDi a la cuenta de la tienda

**Título**

> El QR es el inicio. La confirmación es la que cuenta.

**Copia**

> Abarpay crea el cobro CoDi para la cuenta activa de tu tienda. El pago se marca como confirmado cuando el servidor verifica la transacción. Una captura de pantalla no cambia el estado.

Pasos concisos:

1. Registra la cuenta receptora y espera su activación.
2. Genera el QR desde la venta.
3. Consulta el estado hasta recibir la confirmación verificada.

**Aclaración**

> La activación bancaria puede tardar hasta cinco días hábiles. La página no promete disponibilidad inmediata ni un banco específico hasta que la cuenta esté activa.

### 4. Fiado con historia

**Título**

> Lo que te deben, con nombre y con historial.

**Copia**

> Registra una venta fiada con el cliente correcto. Consulta el saldo, registra un abono parcial o liquida la deuda. Cada movimiento conserva fecha, responsable y nota. El fiado se confirma con conexión para no duplicar una deuda desde dos teléfonos.

No mostrar montos de deuda de personas reales. La demo usa nombres ficticios y una etiqueta visible `SIMULADO`.

### 5. Reposición con una acción siguiente

**Título**

> Sabe qué falta y qué sigue.

**Copia**

> Las existencias bajas se convierten en una lista de trabajo. Revisa el producto, arma el pedido con tu proveedor, recibe la mercancía y publica la entrada cuando esté aprobada. Si dos cajas vendieron la última unidad, Abarpay conserva ambas ventas y abre una diferencia para revisar.

**Estado**

La sección se publica solo si el flujo de pedido y recepción existe en el build aceptado. Mientras sea un borrador, usar `Estamos preparando esta función` y un CTA `Me interesa el piloto`.

### 6. Hecho para una tienda que no se detiene

Tres columnas con afirmaciones verificables:

| Columna | Texto |
|---|---|
| En el teléfono | `Cobra, consulta y conserva comprobantes en el dispositivo.` |
| Con tu equipo | `Invita por liga o QR y asigna permisos por persona.` |
| Para decidir | `Revisa ventas, deudas y reposición con periodos y fuentes claras.` |

### 7. Historial y exportación siempre disponibles

**Título**

> Lo que registraste sigue siendo tuyo.

**Copia**

> El plan Gratis incluye historial y exportación. Si usas Control o participas en un piloto de datos, puedes consultar y recuperar tus registros. Cambiar de opinión sobre la comunidad no borra tu historial.

Evitar `propiedad absoluta` o promesas legales no revisadas. La copia describe acceso operativo mientras el aviso de privacidad y los términos definan la relación jurídica completa.

## Planes

### Gratis

**Precio**

> MXN 0

**Texto**

> Incluye caja, catálogo, inventario básico, registro de ventas, CoDi sin recargo de Abarpay, historial y exportación. La web no procesa cargos automáticos.

**CTA**

> Empezar gratis

El servidor aplica la matriz por tienda. El aislamiento, la comprobación de permisos y la confirmación verificada de CoDi son universales. Nunca bloquea la consulta o exportación de registros ya creados.

### Control

**Precio**

> MXN 149 por tienda al mes

**Etiqueta**

> Piloto con cobro manual

**Texto**

> Control incluye permisos por empleado, alertas de reposición, herramientas de conciliación y reportes de margen y fiado. Se activa para una tienda después de confirmar el pago del periodo. La facturación es manual y no existe cargo automático desde la landing. La continuación se confirma antes de emitir el siguiente cobro manual. Si no se paga el siguiente periodo, las automatizaciones de Control se suspenden y conservas historial y exportación.

**CTA**

> Me interesa Control

**Términos visibles**

- Precio por tienda y por mes.
- Cobro manual fuera de esta página.
- Fecha de inicio y periodo cubierto en la confirmación.
- Impuestos y factura se muestran en la cotización aplicable.
- Las funciones de Control se listan desde la matriz de producto. Las no publicadas no se incluyen.

No afirmar `sin límites`, `ilimitado`, `cancelación instantánea` ni `garantía de devolución` hasta aprobar esas condiciones.

### Formalización

**Precio**

> MXN 399 al mes durante 3 meses

**Etiqueta**

> Próximo piloto · registro de interés, sin renovación automática

**Texto**

> Estamos preparando tres meses de Control con acompañamiento para alta o actualización en el RFC, preparación para facturar y un primer cierre para tu contador. Al terminar vuelves a Gratis o eliges Control. El contador se cotiza aparte. Hoy puedes registrar interés; no hay cargo ni renovación automática.

**CTA**

> Me interesa el piloto

**Aclaraciones**

- La página no presenta Formalización como trámite fiscal terminado.
- La página no promete aceptación bancaria ni crédito.
- El contador externo define alcance, honorarios y responsabilidades aparte.
- Al terminar los tres meses, la continuidad requiere una decisión nueva.

### Dossier financiero

**Etiqueta**

> Investigación futura

**Texto**

> Estamos evaluando un expediente que tú, incluso en Gratis, podrías revisar y compartir con una financiera específica. Distinguiría ventas de caja y cobros confirmados. Probaríamos una tarifa fija que pagaría la financiera por expediente entregado. La financiera decide el crédito. Hoy sólo registramos interés.

**CTA**

> Me interesa el expediente

El CTA abre una explicación o formulario de interés. No se presenta como solicitud de crédito ni como producto vendible.

### Matriz comparativa

| Capacidad | Gratis | Control | Formalización |
|---|---|---|---|
| Operación de tienda | Sí | Sí | Sí |
| Historial y exportación | Sí | Sí | Sí |
| Efectivo y comprobantes offline | Según build aceptado | Según build aceptado | Según build aceptado |
| Fiado en línea | Según build aceptado | Según build aceptado | Según build aceptado |
| Permisos configurables por empleado, alertas de reposición, conciliación operativa y reportes de margen/fiado | No | Incluidos | Incluidos en la hipótesis de piloto |
| Acompañamiento operativo | No | No | Sí, durante tres meses |
| Contador | No | No | Servicio externo, pagado aparte |
| Renovación automática | No aplica | No, cobro manual | No |
| Precio | MXN 0 | MXN 149 al mes por tienda | MXN 399 al mes por 3 meses |

La expresión `Según build aceptado` solo puede sustituirse por `Sí` cuando la versión publicada tenga evidencia del flujo y la prueba física correspondiente.

## APK piloto firmado

La sección de descarga contiene estos campos obligatorios. Si un campo falta, el botón queda deshabilitado y la página explica qué falta.

| Campo | Contenido |
|---|---|
| Versión | Nombre y código, por ejemplo el baseline actual `1.2.3` y `15` cuando el artefacto coincida. |
| Fecha | Fecha de compilación en zona de México. |
| Revisión fuente | SHA de Git que produjo el APK. |
| SHA-256 | Hash del archivo exacto publicado. |
| Firma | Huella del certificado y resultado de verificación. |
| Compatibilidad | Android mínimo soportado por la build, `API 26` en el baseline. |
| Notas | Funciones incluidas, límites y cambios de datos locales. |
| Instrucciones | Instalación, actualización, respaldo y recuperación. |

Copias:

**Título**

> Prueba Abarpay en el teléfono de tu tienda.

**Texto**

> El piloto se instala con un APK firmado. Antes de descargar, revisa la versión, el SHA-256 y las notas. La actualización conserva los datos locales autorizados.

**CTA**

> Instalar APK piloto firmado

**Estado no disponible**

> El APK piloto aún no está publicado. Déjanos tu interés y te avisaremos cuando exista una versión firmada y verificada.

**CTA alternativo**

> Solicitar el APK piloto

No se permite un botón que descargue desde una URL temporal, un archivo debug, un enlace vencido de Cloudflare o un binario cuya firma no coincida con los App Links.

## Comunidad y datos

**Título**

> Tú decides si compartes. Gratis sigue teniendo historial y exportación.

**Copia**

> Podemos pedir tu permiso para usar información agregada de tienda en un piloto con un socio de abasto. La participación empieza apagada. Antes de activarla verás qué campos se usan, para qué decisión, qué recibe el socio, cuánto se conserva y cómo salir. La salida detiene contribuciones futuras y conserva las reglas de los reportes ya entregados. Tus datos de clientes y tu cuenta bancaria no forman parte del reporte agregado.

**Controles visibles**

- Interruptor `Participar en el piloto de datos`, apagado por defecto.
- Enlace al aviso de privacidad y al propósito vigente.
- Fecha de versión del consentimiento.
- Botón `Dejar de participar` con confirmación y siguiente paso.
- Enlace `Descargar mi historial` disponible incluso sin participación.

La página no usa la frase `datos anónimos` como garantía jurídica. Puede decir `datos agregados con controles de divulgación`. La revisión legal ocurre antes de una entrega externa real.

## Medición de campañas

La medición sostiene la mejora de la página y la operación comercial. No se convierte en una promesa de retorno publicitario.

| Evento | Campos permitidos | Uso |
|---|---|---|
| `landing_view` | ruta, variante, UTM permitidos, dispositivo y fecha | Saber qué versión vio la persona. |
| `cta_click` | CTA, variante, campaña, actor responsable | Medir intención y destino. |
| `registration_verified` | tienda nueva o existente, campaña, actor | Separar alta verificada de correo o visita. |
| `store_created` | identificador interno no comercial, campaña, actor | Medir activación inicial. |
| `first_sale_completed` | medio, tienda interna, campaña, actor | Medir continuidad hasta una venta real. |
| `control_paid` | periodo, importe de software, campaña, actor | Medir ingreso cobrado, no una intención. |
| `refund` | periodo, importe, motivo agregado, campaña | Separar ingreso bruto y neto. |
| `retention_checkpoint` | cohorte, periodo, estado activo | Medir uso posterior. |
| `consent_changed` | versión, estado, fecha | Auditar participación. |

Reglas:

1. Guardar campaña, UTM, variante y actor responsable en cada evento pertinente.
2. No enviar CLABE, tokens, nombre de cliente, teléfono, deuda, dirección, contenido de venta ni identificadores de pago a analítica o publicidad.
3. Usar un ID interno de tienda con acceso restringido. No usar correo como clave pública.
4. Distinguir leads, altas, tiendas activas, ventas, Control pagado y retención. No sumar etapas que no son comparables.
5. Si faltan costos o la atribución está incompleta, mostrar `Sin datos suficientes` para CAC y ROI.
6. Registrar la atribución superpuesta de campañas y no borrar duplicados por conveniencia.
7. Una prueba de precio o copy se evalúa con cobros reales y retención, no solo clics.

### Experimentos iniciales

| Experimento | Variantes | Métrica principal | Guardas |
|---|---|---|---|
| Primera pantalla | Promesa completa contra promesa centrada en efectivo | CTA a alta verificada | Legibilidad, comprensión y reclamos aprobados. |
| CTA de entrada | `Entrar a mi tienda` visible contra enlace secundario | Sesiones web aprobadas | Fallo de cámara con código manual. |
| Tarjeta Control | Precio y cobro manual visibles contra detalle plegado | Inicio de alta de Control | No ocultar el precio. |
| APK piloto | Descarga directa contra solicitud guiada | Instalación completada | Firma, versión y hash presentes. |
| Comunidad | Explicación breve contra ejemplo de reporte | Consentimiento informado | Apagado por defecto y salida visible. |

Las entrevistas se registran aparte de la conversión. La disposición a pagar se prueba con cargos reales autorizados. Un clic en `Me interesa` no cuenta como ingreso.

## Objeciones y respuestas

| Objeción | Respuesta pública |
|---|---|
| ¿Qué pasa si se cae el internet? | El efectivo, su comprobante y los movimientos locales se conservan en el teléfono. CoDi, fiado e invitaciones requieren conexión y la app lo indica. |
| ¿A dónde llega el dinero de CoDi? | A la cuenta receptora activa de la tienda. La página explica el registro y la activación por el proveedor. No afirma que Abarpay retiene el saldo. |
| ¿Puedo perder mi historial? | Gratis incluye historial y exportación. La recuperación de teléfono y la restauración se documentan. |
| ¿Control se cobra solo? | No. El precio es MXN 149 por tienda al mes y el cobro es manual. La confirmación indica el periodo cubierto. |
| ¿Cómo cancelo Control? | La página muestra el canal de contacto y explica que las automatizaciones se suspenden al terminar el periodo pagado. El historial y la exportación permanecen accesibles. |
| ¿Formalización incluye contador? | No. El contador externo trabaja y cobra por separado. El piloto dura tres meses y no se renueva automáticamente. |
| ¿El dossier financiero está disponible? | Es una investigación futura. No está incluido en los planes ni tiene precio o disponibilidad confirmados. |
| ¿Comparten mis datos? | Solo con consentimiento para el piloto descrito. Participación apagada por defecto. Los datos de clientes y la cuenta bancaria quedan fuera del reporte agregado. |
| ¿Por qué piden el APK en vez de Google Play? | El piloto distribuye una build firmada desde el dominio del producto. La ficha de Google Play es una etapa separada. |

## Estados responsivos y de disponibilidad

| Estado | Escritorio | Móvil | Acción |
|---|---|---|---|
| Alta abierta | CTA principal y handoff por teléfono. | `Empezar gratis` abre alta o descarga del APK piloto disponible. | Ambos destinos deben responder. |
| Alta en lista de espera | Formulario o explicación del estado. | La misma promesa y la misma fecha de revisión. | No presentar como disponible lo que aún no lo está. |
| QR disponible | Muestra QR y código manual, con vencimiento. | `Entrar a mi tienda` inicia el mismo desafío. | Negar, reintentar y caducar con texto claro. |
| APK disponible | Ficha con versión y SHA-256. | Botón de descarga y notas. | Verificar firma antes de publicar. |
| APK no disponible | Explicación y CTA de interés. | La misma explicación sin enlace roto. | Registrar interés, no simular descarga. |
| Error de red | Conserva la última sección y ofrece reintento. | Igual. | No borra un formulario completado. |

La página debe funcionar a 320 CSS px de ancho y en escritorio sin desplazamiento horizontal. La acción principal permanece visible y los bloques de precio no se convierten en tablas ilegibles en móvil.

## Accesibilidad de la landing

1. Un solo `h1` y jerarquía de encabezados coherente.
2. Enlace de salto al contenido principal.
3. Foco visible y orden lógico de tabulación.
4. Contraste mínimo 4.5:1 para texto normal y 3:1 para texto grande.
5. Texto al 200% sin pérdida de contenido ni acciones.
6. Controles de al menos 24 por 24 CSS px, con espacio suficiente.
7. Estados de precio, disponibilidad y comunidad con texto además de color.
8. Imágenes informativas con texto alternativo. Imágenes decorativas vacías.
9. Video sin reproducción automática con sonido. Controles accesibles y transcripción cuando explique un flujo.
10. Formularios con etiquetas, ayuda, error asociado y conservación de datos.
11. Movimiento reducido respetado.
12. Ningún texto comercial se oculta en una imagen.

Verificar con teclado, lector de pantalla, zoom y una prueba móvil. La meta es WCAG 2.2 AA. [WCAG 2.2](https://www.w3.org/TR/WCAG22/)

## Pruebas de aceptación

### Contenido y verdad comercial

1. La primera pantalla contiene exactamente `Cobra, controla lo que te deben y sabe qué reponer.`
2. Existen y funcionan `Empezar gratis`, `Entrar a mi tienda` e `Instalar APK piloto firmado` o su estado alternativo documentado.
3. Gratis muestra MXN 0 e incluye historial y exportación.
4. Control muestra MXN 149 por tienda al mes y cobro manual.
5. Formalización muestra MXN 399 al mes durante tres meses, sin renovación automática y con contador pagado aparte.
6. El dossier aparece como investigación futura sin precio ni disponibilidad inventados.
7. Comunidad está apagada por defecto, explica propósito y retiro, y no condiciona historial ni exportación.
8. Cada cifra de producto tiene fuente, fecha y versión.
9. No aparece ningún dato de cliente, CLABE, credencial, identificador de pago o captura de deuda real.

### Rutas y CTA

1. `/` responde la landing y no redirige a la consola.
2. `Empezar gratis` llega a alta o lista de espera y conserva campaña permitida.
3. `Entrar a mi tienda` llega al desafío y ofrece código manual si falla la cámara.
4. El CTA de APK entrega solo una versión firmada o muestra el estado no disponible.
5. El APK publicado muestra versión, revisión fuente, SHA-256, huella de firma, notas e instrucciones.
6. La actualización en sitio conserva carrito, ventas pendientes, comprobantes y datos locales autorizados.
7. Las rutas de invitación existentes siguen funcionando.

### Medición

1. Cada evento lleva variante, campaña y actor responsable cuando aplique.
2. No se envían datos bancarios, de deuda o de clientes a analítica.
3. La suma de eventos no confunde visita con registro, venta con cobro, ni Control pagado con interés.
4. Devoluciones y cancelaciones se restan del ingreso cobrado.
5. CAC y ROI muestran `Sin datos suficientes` si falta información.
6. Una prueba de piloto real enlaza la campaña, el cobro manual y la retención del periodo.

### Accesibilidad y rendimiento

1. Recorrido completo con teclado en escritorio.
2. Prueba con lector de pantalla en primera pantalla, planes, comunidad y formulario.
3. Texto al 200% sin recortes ni solapamientos.
4. Contraste medido en todos los estados.
5. Ancho móvil de 320 CSS px sin desplazamiento horizontal.
6. La imagen principal no bloquea el LCP ni carga videos sin acción del usuario.
7. Los estados de error y carga son accesibles y no dependen solo del color.

## Registro de campañas

Cada campaña necesita un propietario, propósito, fecha, canal, UTM, variante, presupuesto o costo conocido, audiencia, consentimiento aplicable y criterio de continuidad. Si el costo no existe, la página no publica ROI. Si la atribución es compartida, el registro conserva la superposición.

La aprobación de una campaña incluye la promesa comercial, la versión de la landing y el destino del CTA. Un cambio de precio o de disponibilidad invalida la aprobación anterior.

## Condición de cierre para DSH

Una lista de espera o un aviso de APK pendiente sólo sirven en preapertura. G2 exige alta de autoservicio, primer cobro en efectivo, entrada QR y APK piloto firmado descargable. Los formularios de interés de Formalización y expediente no activan planes ni generan ingresos.

El paquete público se acepta con la landing desplegada detrás de una ruta aprobada, todos los CTA con destino probado, precios y estados reales, APK firmado con hash verificable cuando se ofrezca descarga, medición sin datos sensibles, revisión WCAG 2.2 AA y captura de la versión revisada en móvil y escritorio. Un recurso ausente queda como estado explícito, nunca como promesa implícita.
