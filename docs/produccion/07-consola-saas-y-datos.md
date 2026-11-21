# Consola de plataforma, medición y piloto de datos

**Usuarios:** equipo de Abarpay. El dueño de una tiendita entra a su consola mediante QR; el equipo SaaS entra a una ruta y audiencia OIDC propias con Entra y MFA. El objetivo operativo es decidir a qué tienda ayudar, qué campaña funciona, qué cobros debe conciliar Finanzas y qué información aporta valor a una cadena de suministro sin revelar a sus participantes.

## Vistas que debe implementar el equipo

| Vista / rol mínimo | Decisión y controles | Detalle verificable |
|---|---|---|
| Operación / soporte | Filtrar fecha, release y severidad; priorizar altas bancarias demoradas, fallos de correo, cajas sin sincronizar y conciliaciones pendientes | Cantidad, antigüedad, código de causa y siguiente acción. Acceso a una incidencia de tienda con motivo y auditoría; enmascarar datos bancarios |
| Crecimiento / marketing | Crear campaña, canal, responsable y período, registrar inversión, repartir códigos/enlaces no personales, medir la activación y la permanencia | Etapas con usuarios únicos y tiendas únicas diferenciados, conversiones, denominadores, desconocidos y cobertura. Historial del responsable efectivo en la fecha del evento |
| Ingreso propio / finanzas | Dar de alta un piloto Control consentido, registrar cargo manual, comprobante, moneda, reembolso y vigencia; conciliar e identificar mora o cancelación | Libro de cargos y devoluciones del SaaS. El dueño ve sus condiciones y puede cancelar. Un cambio de plan preserva historial y exportación |
| Comunidad y socios / analista | Ver hipótesis, utilidad para la tienda, socios interesados, revisión del informe simulado, cohortes elegibles y razones de supresión | Estado y costo por experimento; estimaciones separadas de cobros. El analista trabaja con agregados. Un operador de publicación autorizado entrega únicamente la versión aprobada |

Crear proyecciones y endpoints de plataforma separados de `/api/console` del comerciante. Responder en servidor según rol; ocultar un botón sólo mejora la presentación. Denegar exportaciones y detalle por tienda a marketing y analistas. Filtros se conservan al regresar del detalle. Mostrar carga, vacío, dato retrasado, acceso insuficiente y último cálculo exitoso. Si falla la actualización, conservar la fecha del valor anterior.

## Contrato de medición

Usar eventos de dominio versionados, generados en servidor para los hechos durables. Aceptar evento de interfaz sólo para visita, clic e interacción consentida. Guardar ID de evento, instante de ocurrencia y recepción, versión, origen, entorno, campaña y sujeto seudónimo de la unidad necesaria. Separar indicadores de tienda, persona, operación e importe. Las campañas usan códigos de primera parte y una ventana inicial de 28 días desde la captación. Deduplicar por ID estable; compras, reembolsos, entregas y confirmaciones referencian el hecho original. No pasar teléfonos, CLABE, correos, nombres de deudores ni conceptos libres a analítica.

| Indicador | Fuente y cálculo | Casos especiales |
|---|---|---|
| Altas y usuarios nuevos | Identidades verificadas únicas y tiendas creadas únicas en el período, series separadas | Un dueño con dos tiendas cuenta una persona y dos tiendas. Si la invitación no se acepta, no cuenta como alta verificada |
| Activación | Primera venta completada por tienda y mediana de tiempo alta→primera venta | Caja usa venta en efectivo asentada; CoDi usa pago confirmado. Mostrar retraso cuando llega efectivo hecho offline |
| Uso y retención | Tiendas con venta completada en la semana / tiendas activadas de la cohorte elegible | Fijar zona y ventana de observación; marcar cohortes que aún no completan la ventana |
| Conversión de campaña | Personas únicas con siguiente etapa / personas elegibles en etapa anterior; además lead→pago global | Captación determinista por código válido; si las fuentes se superponen sin resolución conservar bucket ambiguo. Guardar primer contacto y contactos posteriores sin adjudicar dos conversiones |
| Ingreso de Control | Suma de cargos cobrados y reembolsos liquidados en centavos MXN, con fecha de caja | Distinguir periodo de servicio, cobranza, estado de suscripción e impuestos. Un reembolso no demuestra cancelación |
| CAC | Inversión de campaña / nuevos pagadores atribuibles, misma ventana | Sin inversión completa, atribución fiable o denominador positivo, mostrar «Sin datos suficientes» |
| Ventas de tienda y CoDi | Importes capturados por canal, importe verificado por pey y diferencia por conciliar | Usar período, moneda y cohorte de transacciones comparables; mostrar reversos/ajustes por separado. Incluir vínculo autorizado al caso pendiente |
| Abasto | Días-artículo sin existencia / días-artículo observados; cobertura de observación y plazo pedido→recepción | No inferir ventas perdidas, ahorro ni causalidad sólo por cambios en la tasa |
| Viabilidad del producto de datos | Participación consentida, celdas publicables, informes entregados, costo de preparación, facturas cobradas, renovación y beneficio declarado por tiendas | Acuerdo firmado, factura emitida y cobro recibido son hitos distintos |

Para importes usa enteros en centavos. Declara zona comercial, regla de corte, frescura y moneda en cada consulta. En vistas agregadas nacionales fija la zona de reporte y muéstrala. Una modificación histórica de campaña o responsable conserva trazabilidad. Excluye tiendas demo, tráfico interno y eventos SIMULADOS de métricas reales por diseño.

## Ensayo de cuatro revisores · SIMULADO

En esta planificación se consultó a cuatro agentes DeepSeek con el mismo corte ficticio de 28 días. Repetir la revisión al cambiar datos o lógica. Entregar números sin conclusiones, pedir a cada agente su hipótesis, cálculo, objeción y prueba que podría refutarla; reunirlos sólo después. El integrador arbitra unidades antes de construir tarjetas de negocio.

| Revisor | Pregunta adversarial | Resolución que debe permanecer en las pruebas |
|---|---|---|
| Pro · comercio y comunidad | ¿Quién gana con este informe y qué cambió realmente para la tienda? | Los faltantes pasan de 15/100 = 15% a 9/70 ≈ 12.86%; bajó la cobertura. Mostrar dos denominadores y no prometer mejora causal |
| Flash · economía | ¿Existe dinero cobrado y cuánto queda después de devoluciones? | 7 × MXN 149 = 1,043 brutos; dos reembolsos completos = 298; neto cobrado = 745. No calcular rentabilidad sin costos |
| Pro · privacidad | ¿Puede un comprador aislar una tienda, incluso combinando informes? | 8 de 20 tiendas invitadas aceptaron. Zonas de 6 y 2, una aporta 70% de una zona. Ambas salidas externas quedan suprimidas, incluidos porcentajes derivados |
| Flash · atribución | ¿Se puede elegir ganador o asignar valor a cada responsable? | A: 100→30→12→4; B: 40→20→14→3. Diez leads comunes = 130 leads únicos. Tasas brutas lead→pago 4% y 7.5%. Mostrar solapamiento y sin ganador causal; los reembolsos sin canal no se adjudican |

Prueba adicional: MXN 100,000 registrados por tiendas, MXN 20,000 etiquetados CoDi, MXN 18,000 confirmados por pey. Resultado: MXN 2,000 pendientes y 90% por **importe CoDi**. Algunos revisores trataron los importes como filas o asumieron que el resto era dinero confirmado. El verificador debe fallar cualquier consulta que cometa ese cruce. Tres expresiones de interés en Formalización y dos solicitudes ficticias de expediente sin destinatario ni cobro generan MXN 0 de ingresos por esos productos. No multiplicar intereses por tarifa como si fueran contratos.

## Experimentos y publicación externa

1. **Control primero.** El responsable comercial acuerda condiciones, período y seguimiento con cada piloto. Usar cobro real manual y seguimiento de permanencia; registrar minutos ahorrados con el dueño y costos de atención.
2. **Formalización.** Entrevistar a un despacho para validar el alcance futuro y registrar interés de tiendas. En esta entrega no se abren expedientes, se realizan trámites ni se cobra por esta oferta. Hipótesis MXN 399/mes durante tres meses; incluye Control, sin renovación automática. Cotizar al contador aparte. Vencimiento vuelve a Gratis salvo elección explícita de Control. Distinguir acompañamiento del trámite oficial. No almacenar documentos fiscales en la analítica.
3. **Expediente para financiera.** Investigación posterior con una entidad. Hipótesis de tarifa fija pagada por expediente efectivamente entregado. La futura tienda revisaría y autorizaría un destinatario específico; distinguir ventas capturadas y cobros conciliados. En este programa sólo registrar interés. Revisión legal previa a automatizar.
4. **Piloto agregado de abasto.** Un socio, una decisión concreta (p. ej. reposición por categoría y zona amplia), un propósito escrito, vigencia, destinatarios y obligaciones de borrado establecidos. Carlos identifica socio y revisor; mostrar a las tiendas el beneficio y un ejemplo antes de solicitar consentimiento opcional. El rechazo no cambia Gratis ni la exportación.

### Ciclo del informe

Registrar consentimiento versionado y revocable por tienda, propósito y alcance. Diseñar una consulta de ventana fija sobre tiendas elegibles. Exigir ≥10 participantes por celda y contribución individual ≤25%. Suprimir totales auxiliares, celdas complementarias y consultas sucesivas que permitan recuperar valores por diferencias. Revisar concentración incluso si el recuento cumple. Restringir dimensiones y ventanas a un catálogo aprobado. Versionar datos, reglas y huella del artefacto. Privacidad y negocio firman la versión antes de entregarla por acceso limitado y con vencimiento. El ledger conserva destinatario autorizado, propósito, artefacto y fecha. Retiro de consentimiento excluye nuevas contribuciones e inicia el tratamiento pactado para históricos y entregas previas. Los umbrales son controles iniciales; requieren revisión ante el informe real.

**Puerta de entrega:** probar 9/10/11 participantes, concentración justo debajo/en/arriba del límite, pérdida de un consentimiento entre preparación y entrega, filtros superpuestos y permisos de exportación. Incluir una cohorte sintética que sí califique, además de las dos suprimidas, para probar el camino de entrega. Cambiar elegibilidad o destinatario invalida la aprobación previa. Explicar al usuario el motivo permitido sin revelar el valor protegido. Un socio real, contrato, revisión legal y consentimientos son dependencias para entregar datos reales. [Ley de datos personales](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf) · [Ley para regular las sociedades de información crediticia](https://www.diputados.gob.mx/LeyesBiblio/pdf/LRSIC.pdf)
