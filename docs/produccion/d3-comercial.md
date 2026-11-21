# D3 · Comercial — Abarpay

**Paquete:** D3 Commercial (work package board `docs/produccion/09-paquetes-y-aceptacion.md`)
**Rol:** Flash commercial analyst (commercial analyst), con revisión Pro
**Alcance de escritura:** SOLO este archivo (`docs/produccion/d3-comercial.md`). No se modifican `06`, `07`, `glossary`, `09` ni ningún otro archivo.
**Fuentes:** `docs/produccion/06-landing-y-comercial.md` (instrucción completa de página pública, oferta y APK), `docs/produccion/07-consola-saas-y-datos.md` (sección "Four-reviewer rehearsal · SIMULADO" con la instantánea de 28 días), `docs/produccion/glossary.md`, `docs/produccion/09-paquetes-y-aceptacion.md` (fila D3 y escenario B7).
**Criterio B7 asociado:** Cargar la fixture SIMULADO, recalcular embudo y dinero de forma independiente, restablecer el filtro; simular retiro entre preparación y entrega, dominancia e inferencia por diferencia; verificar una entrega permitida, autorizada y registrada.

> **Nota de discrepancia de revisión (verificada contra el repositorio):** el brief de este paquete indica un SHA base `6656f1e`, mientras que `06` declara `main` en `75c1f35` revisado el 21-nov-2026 y `09`/B0 repite `75c1f35`. El contenido comercial (precios, claims y cifras de la fixture) proviene de la documentación de producción vigente; la discrepancia de SHA se reporta como pregunta abierta al coordinador al final.

---

## 1. Copy de la landing page (español de México)

Las cadenas de primer pantalla se transcriben **verbatim** desde `06`. Ninguna cadena de esta sección inventa una promesa; cada claim concreto se rige por la tabla de veracidad de la sección 1.4.

### 1.1 Primer pantalla (first screen)

**H1**

> Cobra, controla lo que te deben y sabe qué reponer.

**Subcopy (párrafo)**

> Abarpay reúne la venta, el efectivo, el fiado, el inventario y CoDi en el teléfono de tu tienda. El efectivo y sus comprobantes quedan en el teléfono cuando falla la conexión. Al volver la señal, todo se sincroniza para que tu equipo trabaje con el mismo estado.

**Microcopy bajo los botones**

> Gratis incluye historial y exportación. Control cuesta MXN 149 por tienda al mes y se cobra manualmente. La web no procesa cargos automáticos.

### 1.2 Los tres CTAs

| CTA | Cadena exacta | Destino requerido (`06`) |
|---|---|---|
| Primario | `Empezar gratis` | `/empezar` — alta real o lista de espera honesta con estado visible |
| Retorno | `Entrar a mi tienda` | `/entrar` — reto de acceso por QR, con código manual si falla la cámara |
| Piloto | `Instalar APK piloto firmado` | `/apk-piloto` — APK firmado y con hash, o estado de no-disponible; nunca un archivo sin firma y hash |

Cada CTA debe tener una prueba de destino; un botón sin destino o que promete una función no publicada bloquea el paquete.

### 1.3 Líneas de propuesta de valor

Sección "Built for a store that does not stop" (`06`), tres columnas verificables:

| Columna | Texto |
|---|---|
| En el teléfono | `Cobra, consulta y conserva comprobantes en el dispositivo.` |
| Con tu equipo | `Invita por liga o QR y asigna permisos por persona.` |
| Para decidir | `Revisa ventas, deudas y reposición con periodos y fuentes claras.` |

Líneas de sección (títulos/copy verbatim de `06`) que refuerzan la propuesta:

- **Operación de hoy** — "Tu tienda, en orden desde el primer cobro." / "Abre el catálogo, cobra, registra un gasto y revisa lo que pasó hoy. El dueño ve la tienda completa. Cada empleado ve solo lo que necesita para su turno."
- **Efectivo offline** — "La caja sigue cuando la señal no." / "Cobra en efectivo, calcula el cambio y entrega un comprobante con una referencia estable aunque no haya internet…"
- **CoDi** — "El QR es el inicio. La confirmación es la que cuenta."
- **Fiado** — "Lo que te deben, con nombre y con historial."
- **Reposición** — "Sabe qué falta y qué sigue."
- **Historial/exportación** — "Lo que registraste sigue siendo tuyo."

### 1.4 Guardas de veracidad (obligatorias)

Se transcriben **solo** las cadenas de claim **permitidas** de `06`. Queda **prohibido** escribir cualquier claim prohibido; si un elemento carece de fuente/fecha/muestra/método, se muestra `Sin datos suficientes` o se omite.

| Capacidad | Claim permitido (usar solo este texto) | Claim prohibido (nunca escribir) |
|---|---|---|
| Efectivo offline | `Registra ventas en efectivo y comprobantes en el teléfono cuando no hay señal.` | `Todo Abarpay funciona sin internet.` |
| Ventas a crédito | `Consulta saldos y registra cargos o abonos con conexión.` | `Autoriza fiado sin conexión` / `cobra deudas automáticamente` |
| CoDi | `Muestra el QR y confirma el pago cuando el servidor lo verifica.` | `Pago garantizado`, `dinero inmediato`, `sin riesgo` |
| Inventario | `Comparte existencias cuando las cajas se sincronizan. Las diferencias se revisan.` | `Inventario exacto en tiempo real` sin evidencia de cada caja |
| Comunidad | `Participación opcional, apagada por defecto, con beneficio y retiro explicados.` | `Vendemos tus datos`, `datos anónimos garantizados` |
| Seguridad | `Datos separados por tienda y accesos por membresía.` | `100% seguro`, `bancos certifican todo`, certificaciones no ganadas |
| APK piloto | `Instala una versión firmada, verificable y con sus notas de versión.` | `Descarga el APK` junto a un archivo sin firma, sin hash o de origen desconocido |
| Formalización | `Piloto guiado de tres meses, sin renovación automática y con contador externo.` | `Trámite fiscal incluido`, `contador incluido`, `dossier bancario disponible` |

**Reglas adicionales de veracidad:** no publicar conteo de clientes, ahorro, aumento de ventas, tiempo de activación o beneficio del piloto de datos sin fuente, fecha, muestra y método. Un clic en `Me interesa` no cuenta como ingreso. CAC y ROI muestran `Sin datos suficientes` si falta costo o atribución.

---

## 2. Definición de ofertas (plans)

Tres ofertas + una investigación futura (dossier financiero) que **no** es un plan vendible ni tiene precio confirmado.

### 2.1 Gratis (self-service)

- **Precio:** MXN 0.
- **Incluye:** caja, catálogo, inventario básico, registro de ventas, CoDi sin recargo de Abarpay, historial y exportación. La web no procesa cargos automáticos.
- **CTA:** `Empezar gratis`.
- **Regla:** el servidor aplica la matriz por tienda; el aislamiento, los checks de permiso y la confirmación CoDi verificada son universales. Nunca bloquea consulta ni exportación de registros ya creados.

### 2.2 Control (pago manual)

- **Precio:** MXN 149 por tienda al mes.
- **Etiqueta:** `Piloto con cobro manual`.
- **Facturación:** manual, fuera de la landing; sin cargo automático. La activación se confirma tras el pago del periodo; la continuación se confirma antes del siguiente cobro manual.
- **Incluye:** permisos por empleado, alertas de reposición, herramientas de conciliación, reportes de margen y fiado.
- **Suspensión:** si no se paga el siguiente periodo, las automatizaciones de Control se suspenden y se conservan historial y exportación.
- **CTA:** `Me interesa Control`.
- **Términos visibles:** precio por tienda y por mes; cobro manual fuera de la página; fecha de inicio y periodo cubierto en la confirmación; impuestos y factura en la cotización aplicable; funciones listadas desde la matriz de producto (no se incluyen las no publicadas).
- **Prohibido:** `sin límites`, `ilimitado`, `cancelación instantánea`, `garantía de devolución` hasta que se aprueben.

### 2.3 Formalización (guiado, 3 meses)

- **Precio:** MXN 399 al mes durante 3 meses.
- **Etiqueta:** `Próximo piloto · registro de interés, sin renovación automática`.
- **Qué es:** tres meses de Control con acompañamiento para alta/actualización de RFC, preparación para facturar y un primer cierre para el contador. Al terminar, vuelve a Gratis o elige Control.
- **Contador:** externo, cotiza y cobra aparte (alcance, honorarios y responsabilidades por separado).
- **CTA:** `Me interesa el piloto`.
- **Sin:** renovación automática, trámite fiscal terminado, promesa de aceptación bancaria o de crédito.

### 2.4 Dossier financiero (investigación futura)

- **Etiqueta:** `Investigación futura`.
- **Estado:** solo se registra interés; sin precio, sin disponibilidad confirmada, no es solicitud de crédito ni producto vendible.
- **CTA:** `Me interesa el expediente`.

### 2.5 Matriz de comparación (versión comercial)

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

La expresión `Según build aceptado` se reemplaza por `Sí` solo cuando la versión publicada tenga evidencia del flujo y la prueba física correspondiente.

### 2.6 Tabla de producto/precio versionada

| Versión | Vigencia | Producto | Precio | Facturación | Renovación |
|---|---|---|---|---|---|
| v1.0 (borrador de referencia, 21-nov-2026) | desde el 21-nov-2026 hasta cambio autorizado | Gratis | MXN 0 | — | No aplica |
| v1.0 (borrador de referencia, 21-nov-2026) | ídem | Control | MXN 149 / tienda / mes | Manual, fuera de la landing | No automática; confirmación antes del siguiente cobro |
| v1.0 (borrador de referencia, 21-nov-2026) | ídem | Formalización | MXN 399 / mes por 3 meses | Manual (hipótesis de piloto) | Sin renovación automática |
| v1.0 (borrador de referencia, 21-nov-2026) | ídem | Dossier financiero | Sin precio confirmado | No aplica (solo interés) | No aplica |

**Autoridad de precio:** un cambio de precio, una nueva promesa comercial o una prueba con dinero requiere autorización del dueño de producto. Un experimento no cambia el precio cobrado. La tabla versionada es la autoridad; el precio real no se altera por un test.

---

## 3. Definición del embudo (funnel)

El embudo distingue etapas comparables y **nunca** confunde visita con registro, venta con pago, ni Control pagado con interés. Cada etapa se marca con el evento que produce la transición. `refund` y `campaign` no son etapas de avance: la campaña es atribución de adquisición y el reembolso ajusta el ingreso neto.

| # | Etapa | Evento que marca la transición | Unidad contada |
|---|---|---|---|
| 1 | Visita | `landing_view` (route, variant, UTMs permitidos, device, fecha) | Persona que ve la página/versión |
| 2 | CTA | `cta_click` (CTA, variant, campaign, actor responsable) | Intención y destino del clic |
| 3 | Registro verificado | `registration_verified` (nueva o existente tienda, campaign, actor) | Identidad verificada separada de email/visita |
| 4 | Creación de tienda | `store_created` (identificador interno no comercial, campaign, actor) | Activación inicial |
| 5 | Primera venta | `first_sale_completed` (canal, tienda interna, campaign, actor) | Continuidad a través de una venta real |
| 6 | Control pagado | `control_paid` (periodo, monto de software, campaign, actor) | Ingreso cobrado, no intención |
| 7 | Retención | `retention_checkpoint` (cohorte, periodo, estado activo) | Uso posterior |

**Reglas de medición del embudo:**

- Conversión de campaña = personas únicas que llegan a la siguiente etapa / personas elegibles en la etapa anterior; además, lead→pago global. Atribución determinística por código válido; si las fuentes se solapan sin resolverse, se conserva un bucket ambiguo. Guardar primer contacto y contactos posteriores sin asignar dos conversiones.
- Activación = primera venta completada por tienda + mediana de tiempo registro→primera venta (efectivo = venta publicada; CoDi = pago confirmado; mostrar retraso cuando el efectivo offline llega después).
- Retención = tiendas con venta completada en la semana / tiendas activadas en la cohorte elegible; fijar zona horaria y ventana de observación; marcar cohortes que aún no completan la ventana.
- Ingreso Control = suma de montos cobrados y reembolsos liquidados en centavos MXN, con fecha de cobro; distinguir periodo de servicio, cobro, estado de suscripción e impuestos. Un reembolso no prueba cancelación.
- CAC = gasto de campaña / nuevos pagadores atribuibles, misma ventana; sin gasto completo, atribución confiable o denominador positivo → `Sin datos suficientes`.

---

## 4. Taxonomía de eventos

Diez eventos: campaña, visita, CTA, registro verificado, creación de tienda, primera venta, Control pagado, reembolso, retención y el evento de auditoría de consentimiento. Los hechos durables se generan en el servidor; se acepta un evento de UI solo para visitas, clics e interacción consentida.

| Evento | Nombre de evento (referencia `06`) | Campos de uso (permitidos) |
|---|---|---|
| Campaña | `campaign_created` *(nombre inferido; `06`/`07` no fijan un identificador literal)* / atribución de adquisición | campaign, channel, owner, period; códigos first-party; ventana inicial de 28 días desde la adquisición |
| Visita | `landing_view` | route, variant, UTMs permitidos, device, fecha |
| CTA | `cta_click` | CTA, variant, campaign, actor responsable |
| Registro verificado | `registration_verified` | nueva o existente tienda, campaign, actor |
| Creación de tienda | `store_created` | identificador interno no comercial, campaign, actor |
| Primera venta | `first_sale_completed` | canal, tienda interna, campaign, actor |
| Control pagado | `control_paid` | periodo, monto de software, campaign, actor |
| Reembolso | `refund` | periodo, monto, razón agregada, campaign |
| Retención | `retention_checkpoint` | cohorte, periodo, estado activo |
| Consentimiento (auditoría) | `consent_changed` | version, state, date |

### 4.1 Campos requeridos en cada evento

Todo evento versionado debe almacenar:

1. **Event ID** (identificador estable para deduplicación).
2. **Occurrence timestamp** (cuándo ocurrió el hecho).
3. **Receipt timestamp** (cuándo se recibió/registró en el servidor).
4. **Version** (versión del esquema del evento).
5. **Origin** (origen del hecho; servidor = durable, UI = solo visita/clic/interacción consentida).
6. **Environment** (entorno: demo / producción; los eventos demo, tráfico interno y SIMULADO se excluyen de métricas reales por diseño).
7. **Campaign** (código first-party; guardar UTM, variant y actor responsable cuando aplique).
8. **Pseudonymous subject** (sujeto pseudónimo de la unidad requerida; separar indicadores de tienda, persona, operación y monto).

Reglas de integridad: deduplicar por ID estable; compras, reembolsos, entregas y confirmaciones referencian el hecho original. Usar centavos enteros para montos; declarar zona horaria de negocio, regla de corte, frescura y moneda en cada consulta. Un cambio histórico de campaña o dueño preserva trazabilidad.

### 4.2 Campos EXCLUIDOS (nunca se envían a analytics)

Los siguientes quedan **excluidos explícitamente** de todo evento de medición/análisis:

- **Datos bancarios** (incluida la CLABE completa; pey devuelve un account ID separado para ruteo).
- **Números de teléfono.**
- **CLABE.**
- **Emails** (no usar email como clave pública; usar un ID interno de tienda con acceso restringido).
- **Nombres de deudores** (y nombres de clientes).
- **Texto libre.**

Además (`06` regla 2, lista más amplia): tokens, dirección, contenido de venta e identificadores de pago tampoco se envían a analytics ni a publicidad. Los datos de clientes y la cuenta bancaria no forman parte del reporte agregado.

---

## 5. Decisiones de los cuatro revisores frente a la fixture de 28 días · SIMULADO

**Etiqueta:** esta sección completa es **SIMULADO**. Es un ensayo de planificación con una instantánea ficticia de 28 días; los números se entregan **sin conclusiones** y deben recalcularse de forma independiente (criterio B7). Repetir la revisión cuando cambien datos o lógica.

> **Nota de provisión de modelo:** en este ensayo, **Flash** no está provisionado en el entorno DSH, por lo que los dos roles "Flash" (economía y atribución) están representados aquí por **Pro de bajo esfuerzo**. Los hallazgos se atribuyen al rol, no al modelo real de Flash. Reportar como pregunta abierta al coordinador.

### 5.1 Re-derivación independiente de las cifras (CoDi)

Dado el estado de ventas/CoDi de la fixture:

| Magnitud | Valor |
|---|---|
| Registrado por las tiendas (todas las ventas, todos los canales) | MXN 100,000 |
| Etiquetado como CoDi (subconjunto del canal CoDi) | MXN 20,000 |
| Confirmado por pey (subconjunto de lo etiquetado CoDi) | MXN 18,000 |
| **Pendiente de conciliación** (CoDi etiquetado − confirmado) | **MXN 2,000** = 20,000 − 18,000 |
| **Porcentaje confirmado por monto CoDi** (confirmado / etiquetado CoDi) | **90%** = 18,000 / 20,000 |

**Corrección crítica (la trampa de comparación cruzada):**

- El **90%** es por **monto CoDi**: 18,000 / 20,000. NO es "18% de los 100,000" ni implica que el 82% restante esté "confirmado" o "pendiente".
- El **MXN 2,000 pendiente** se calcula **solo dentro del subconjunto CoDi** (20,000 − 18,000), no como 100,000 − 18,000 = 82,000.
- Los tres montos son **series distintas con denominadores distintos**: ventas registradas totales (100,000) ≠ etiquetado CoDi (20,000) ≠ confirmado pey (18,000). No son filas de una misma cuenta.
- El verificador **debe fallar cualquier query que haga esa comparación cruzada** (p. ej., "18,000 / 100,000 = 18% confirmado" o "82,000 pendiente de todo").

**Resultado corregido:** MXN 2,000 pendiente de conciliación CoDi y 90% de confirmación **por monto CoDi** (sobre los MXN 20,000 etiquetados), no sobre el total registrado.

### 5.2 Re-derivación: Formalización y dossier (ingresos)

- **3 manifestaciones de interés en Formalización** → **MXN 0** de ingreso.
- **2 solicitudes de dossier ficticias, sin destinatario ni cargo** → **MXN 0** de ingreso.
- Una manifestación de interés **no crea una cuenta por cobrar**. Solo se cuenta ingreso cuando ocurre el evento financiero correspondiente (cargo real autorizado y cobrado, o tarifa por expediente efectivamente entregado).
- **Resultado corregido:** los ingresos por Formalización y dossier son MXN 0 en la fixture; las expresiones de interés se cuentan como leads, no como revenue.

### 5.3 Revisores: hipótesis, cálculo, objeción (SIMULADO)

| Revisor (rol) | Pregunta adversaria | Hipótesis / cálculo / objeción | Corrección que debe permanecer en las pruebas |
|---|---|---|---|
| Pro · comercio y comunidad | ¿Quién se beneficia de este reporte y qué cambió realmente para la tienda? | Hipótesis: el reporte reduce agotados. Cálculo: 15/100 = 15% antes → 9/70 ≈ 12.86% después. Objeción: la mejora aparente esconde que el denominador cambió (cobertura cayó de 100 a 70 ítem-días observados). | Mostrar **ambos denominadores** y **no prometer mejora causal**. No inferir ventas perdidas, ahorros ni causalidad solo por el cambio de tasa. |
| Flash · economía *(representado por Pro de bajo esfuerzo)* | ¿Hay dinero cobrado y cuánto queda tras reembolsos? | Cálculo: 7 × MXN 149 = **MXN 1,043 brutos**; 2 reembolsos completos = MXN 298; **neto cobrado = MXN 745**. Objeción: no calcular rentabilidad sin costos (soporte, adquisición). | Registrar bruto 1,043, reembolsos 298, neto 745. **No calcular rentabilidad sin costos**. Distinguir periodo de servicio, cobro, estado e impuestos; un reembolso no prueba cancelación. |
| Pro · privacidad | ¿Podría un comprador aislar una tienda, incluso combinando reportes? | Hipótesis: con pocos participantes y alta concentración, se reidentifica. Cálculo: 8 de 20 tiendas invitadas aceptaron; zonas de 6 y 2; una tienda aporta 70% de una zona. Objeción: incluso porcentajes derivados pueden revelar por diferencia. | Suprimir **ambas salidas externas**, **incluidos los porcentajes derivados**. Umbral ≥10 por celda, contribución ≤25%, revisar concentración; pruebas 9/10/11 y pérdida de un consentimiento. |
| Flash · atribución *(representado por Pro de bajo esfuerzo)* | ¿Se puede elegir un ganador o asignar valor a cada dueño? | Cálculo: A = 100→30→12→4; B = 40→20→14→3. 10 leads compartidos ⇒ **130 leads únicos** (100+40−10). Tasas brutas lead→pago: **A = 4/100 = 4%**, **B = 3/40 = 7.5%**. Objeción: muestras chicas, solape sin resolver y reembolsos sin canal impiden declarar ganador causal. | Mostrar **solape** y **sin ganador causal**. Reembolsos sin canal **no se asignan**. Conservar bucket ambiguo; no asignar dos conversiones. |

**Cifras re-derivadas resumidas (corregidas):**

| Concepto | Valor corregido |
|---|---|
| Ventas registradas (todos los canales) | MXN 100,000 |
| Etiquetado CoDi | MXN 20,000 |
| Confirmado por pey | MXN 18,000 |
| Pendiente de conciliación CoDi | MXN 2,000 |
| % confirmado **por monto CoDi** | 90% (18,000/20,000) |
| Control bruto | MXN 1,043 (7 × 149) |
| Reembolsos | MXN 298 (2 × 149) |
| Control neto cobrado | MXN 745 |
| Leads únicos (A+B) | 130 |
| Tasa bruta lead→pago A | 4% (4/100) |
| Tasa bruta lead→pago B | 7.5% (3/40) |
| Ingreso Formalización | MXN 0 (3 expresiones de interés) |
| Ingreso Dossier | MXN 0 (2 solicitudes ficticias, sin cargo ni destinatario) |
| Agotados antes / después | 15/100 = 15% → 9/70 ≈ 12.86% (cobertura cayó) |
| Tiendas invitadas / aceptadas | 20 / 8 |

### 5.4 Desacuerdos remanentes (abiertos a arbitraje del integrador)

1. **Ganador de campaña:** B tiene mayor tasa (7.5% vs 4%) pero A tiene más pagadores absolutos (4 vs 3) y muestras chicas con solape de 10 leads; no hay ganador causal. Requiere arbitraje de unidades antes de construir tarjetas de negocio (el integrador arbitra unidades).
2. **Interpretación del "porcentaje":** algunos revisores trataron los montos como filas o asumieron que el remanente era "dinero confirmado"; la corrección exige mantener los tres denominadores separados y hacer fallar la query de comparación cruzada.
3. **Asignación de reembolsos sin canal:** quedan sin asignar; no deben imputarse a A ni a B.

---

## Preguntas abiertas para el coordinador

1. **Discrepancia de SHA base:** el brief indica `6656f1e`; `06` y `09`/B0 referencian `75c1f35` (revisado 21-nov-2026). ¿Cuál es el SHA de referencia correcto para este paquete D3? (No ejecuté comandos git, por instrucción.)
2. **Provisionamiento de Flash:** Flash no está provisionado en este entorno DSH; los roles Flash (economía y atribución) fueron cubiertos por Pro de bajo esfuerzo. ¿Debe repetirse esta revisión SIMULADO con Flash real antes de cerrar D3?
3. **Autoridad de precios/versión:** la tabla producto/precio se fijó como "v1.0 (borrador de referencia, 21-nov-2026)". ¿Confirma el dueño de producto esa versión como autoridad, o se espera un número de versión distinto para el lanzamiento de la página?
4. **Límite de ventana de campaña:** se usa la ventana inicial de 28 días de adquisición (per `07`). ¿Es correcta para todos los experimentos de `06`, o se necesita un ajuste por canal?

---

## Fallos del coordinador (Coordinator rulings)

1. **SHA base:** `6656f1e` es el SHA autoritativo. El `75c1f35` citado en `06`/`09` es la línea base histórica de evaluación de producto, no el SHA de este paquete.
2. **Flash:** Flash no está provisionado; **Pro@low es el sustituto aceptado** para los roles Flash (economía y atribución). Repetir con Flash real solo si Carlos lo provisiona.
3. **Versión de precios:** `v1.0 (borrador)` es aceptable. El número de versión final de lanzamiento es decisión del dueño de producto.
4. **Ventana de campaña:** la ventana inicial de 28 días de adquisición es correcta según `07`.
