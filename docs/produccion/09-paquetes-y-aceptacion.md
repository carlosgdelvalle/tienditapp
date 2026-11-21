# Tablero ejecutable · definición de terminado

El coordinador abre el paquete cuyo prerrequisito tenga evidencia. Los IDs son estables y sirven para bloqueos, ramas y revisiones. La columna de ámbito asigna una superficie lógica. Antes de despachar, acota los archivos reales del worktree y el punto de integración. Un contrato aceptado permite construir un cliente contra un fixture mientras se implementa el servicio. Los hitos integrados exigen equivalencia comprobada entre fixture y servicio.

| ID | Depende de | Propietario y ámbito | Resultado que verifica otra sesión |
|---|---|---|---|
| E0 Entorno | Inicio | Pro coordinador, entorno DSH | CLI y modelo efectivos, sesión independiente de verificación, prueba de restart, línea base Python/Android, rutas ignoradas. Registrar aparte dependencias externas como teléfono o bot pendientes |
| E1 Avisos | E0 entorno | Flash operaciones locales | Configurar notificador incluido, probar preview/deduplicación aislada, confirmar un aviso real en chat privado autorizado. Simular fallo y consumir una resolución de prueba sin invocar Astra |
| D1 Flujos | E0 | Pro industrial, interfaz sin código | Tarjetas de cada recorrido del documento 03, matriz Trello completa, pasos, recuperación y accesibilidad; un codificador discute y firma cada tarjeta antes de implementar su pantalla |
| D2 Contratos | E0 | Pro dominios, API e invariantes | Inventario de rutas, jobs y eventos; contratos de tenant, banco, journal offline y métricas con ejemplos de dos tenants de prueba, cada uno con su tienda. Congelar por dominio e informar al consumidor correspondiente |
| D3 Comercial | E0 | Flash comercial con revisor Pro | Copy y fichas de oferta, embudo, taxonomía de eventos y decisiones de los cuatro revisores. Verificar contra fixture de 28 días |
| I1 Tenencia | D2 tenencia | Pro backend/BD, único dueño de migraciones | PostgreSQL, contexto de tienda y RBAC/RLS, semilla limpia, dos tiendas y prueba de pool. Conteos y totales concilian con migración ensayada |
| I2 Identidad | D2 identidad + D1 flujo correspondiente | Pro auth, Flash web/móvil en worktrees separados | Alta y recuperación OIDC, invitaciones, selección de tienda, QR, código manual, sesiones, Entra/MFA. Cambiar membresía o perder el móvil revoca acceso |
| I3 Persistencia móvil | D2 sync + D1 caja | Pro sincronización, Kotlin y contrato servidor | DB local cifrada, outbox atómico, recibos y reanudación. Interrumpir confirmación y reiniciar conserva una sola operación durable |
| I4 Plataforma | D3 + D2 roles | Flash web de plataforma | Navegación separada con vistas de salud, crecimiento, ingresos y datos, y estados de espera/vacío. Usar fixtures SIMULADOS hasta conectar agregados |
| I5 CI e infraestructura | E0 y D2 para BD | Flash CI, Pro integración | CI cubre backend, migraciones, aislamiento y cambios Android; validar workflow de PR y main. Infra local independiente del presupuesto Render |
| I6 Landing y APK | D1 acceso + D3 | Flash sitio público | CTA móvil/escritorio, página de precios y transparencia, entrada de propietario QR y embudo. APK firmado y subido sólo al superar G2 |
| M1 Onboarding y CLABE | I1 + I2 + D1 | Pro banco, Flash pantallas | Alta sin datos demo, primera venta sin datos bancarios, estados asíncronos y correo; cobro explícitamente dirigido a la cuenta activa del tenant |
| M2 Caja y cierre | I1 + I3 + I2 + D1 | Pro caja, Flash cierre | Efectivo offline, agotado en dos cajas, handover, aceptación, diferencia auditada y reintentos. Móvil real más segundo cliente |
| M3 Compras y reposición | I1 + I3 + D1 | Pro inventario, Flash cliente | Proveedor→pedido→recepción offline→diferencia→aprobación→stock. Dos recepciones del mismo envío generan caso trazable sin duplicar existencias |
| M4 Fiado | I1 + I2 + D1 | Pro deuda, Flash interfaz | Vencimiento y límite, excepción autorizada, abonos parciales y liquidación, recordatorio opt-in, permisos y exportación en Gratis |
| M5 Correo | D2 + I2 contrato | Flash servicios | Invitación, verificación y recuperación con emisor definido, cola y rebotes. TLS probado con servidor de captura; OTP/enlaces nunca aparecen en telemetría |
| M6 Analítica y Control | I1 + I4 + D3 | Pro métricas, Flash vistas | Fuentes durables de eventos, suscripción piloto manual, campaña y responsable, conciliación del fixture y aislamiento entre analista, finanzas y soporte |
| M7 Socio agregado | D2 consentimiento + I4 + D3 | Pro privacidad, Flash proyección | Opt-in/withdrawal, simulador y publicación gated con ledger. Caso suprimido y elegible reproducidos por revisor independiente |
| G1 Integración | I1–I6, M1–M6 | Pro integrador y verificadores distintos | Recorrer Android y navegador con dos tenants independientes, cada uno con una tienda, en entorno aislado. Registro de latencia, red lenta, teléfono físico, incidentes, restore y rollback |
| G2 Piloto público | G1 + decisiones externas aplicables | Pro operador | Auto-CD verificado con SHA, APK firmado actualizable, correo real autorizado, página y métricas reales; marcar CoDi en espera hasta aval proveedor y prueba humana |
| G3 Operación comercial | G2; M7 para socio | Equipo negocio y Pro datos | Control con cobros consentidos y datos reales segregados; publicar agregado sólo cuando existan socio, consentimientos y revisión legal. Investigación Formalización/expediente con valor monetario cero hasta un hecho real |

**Camino crítico:** E0 → D2 → I1/I2/I3 → M1/M2 → G1 → G2. E1, D1 y D3 avanzan en paralelo. Permitir que un retraso externo bloquee sólo su capacidad: implementación y verificación simulada de M1 funcionan sin una CLABE real, E1 puede probar errores sin token, y M7 puede demostrar supresión y entrega sintética sin un comprador. Conservar estado parcial y nombrar qué falta; la demo o el fixture no cierran la puerta externa.

### Dependencia entre precios y reportes

En M3 registrar costo de compra en centavos y cantidad recibida al aprobar una entrada. En M6 conservar el costo promedio ponderado vigente al vender en la línea histórica. Calcular margen bruto de mercancía sobre venta neta menos costo atribuible, con misma base, cantidad y moneda; documentar tratamiento de descuentos y devoluciones. Mostrar por separado las líneas sin costo conocido o en conflicto por venta offline y la cobertura del informe, sin imputar costo cero. Una compra posterior no cambia el margen ya cerrado. B5 debe cubrir dos compras a costos distintos, venta parcial, devolución y artículo sin costo. La conciliación verificadora que autoriza el estado pagado es universal; Control añade herramientas de operación y reportes.

## Banco de pruebas y evidencia

| Escenario | Ejecución y resultado esperado |
|---|---|
| B0 · Línea base | En venv Python 3.12 con dependencias de app y server ejecutar `./scripts/verificar.sh` y `python -m pytest -q server/tests`. En Android con JDK 21 y SDK 35 ejecutar `./gradlew testDebugUnitTest assembleRelease`. Referencia del 21-nov: 16 MVP, 183 backend y 154 Android en 75c1f35. Revalidar revisión actual; el conteo no es una cuota |
| B1 · Alta, invitaciones y aislamiento | Dar de alta A y B desde cero; crear productos de igual código y deudas de igual nombre; invitar empleado A. Intentar leer y escribir recursos B con identidad A en API, jobs, exportación y caché móvil. Denegación, sin diferencia en saldos ni detalle de existencia del recurso |
| B2 · QR y cambio de teléfono | Dos navegadores. Escanear en uno; validar tienda y código visible; aprobar sólo su sesión. Probar rechazo, expiración, código manual, acceso same-device, recuperación y pérdida de membresía. Auditar sin registrar el secreto |
| B3 · Banco y dinero | FakePey SIMULADO con dos IDs activos, una cuenta pendiente y un cambio de cuenta. Verificar cuenta destino exacta al crear QR, conciliación del cobro anterior, duplicados y fallo de proveedor. Mantener un pago real como caso humano documentado aparte |
| B4 · Venta y recepción offline | En el Android conectado a ADB, usar modo avión, vender la última unidad, recibir mercancía, cerrar aplicación, reiniciar y reconectar. Segundo POS vende la misma unidad. Perder ACK y reintentar. Dos ventas reales distintas sobreviven; ningún reintento multiplica dinero o stock |
| B5 · Cierre y deuda | Dos operadores, fondo inicial, venta, diferencia contada y entrega aceptada. Solicitud de fiado que excede límite, autorización del dueño, abono parcial, cobro final y exportación tras volver a Gratis. Verificar ledger y auditoría |
| B6 · Ergonomía | Registrar teléfono y versión sin serial, estado de red y tarea. Medir toque→respuesta y acción→estado comprensible. Repetir con letra ampliada, TalkBack, luz intensa y una distracción. En navegador usar teclado y zoom. Documentar tarea, tiempo, resultado y fallos observados |
| B7 · Negocio y privacidad | Cargar fixture SIMULADO, recalcular a mano embudo y dinero; restablecer filtro. Simular retiro entre preparación y entrega, dominancia e inferencia por diferencia. Verificar también una entrega permitida, autorizada y registrada |
| B8 · Release recuperable | Reinstalación y actualización in situ del APK con outbox pendiente. Ensayo de restore a BD aparte y rollback compatible. Validar SHA y smoke de sólo lectura después de auto-CD. Documentar RPO/RTO medidos |
| B9 · Coordinación | A vence un lease con commit existente, B recupera sin duplicarlo. Crear pregunta de prueba, interrumpir worker tras avisar, reanudar: sin doble notificación automática. Respuesta de Carlos desbloquea sólo dependientes |

Cada informe contiene **pregunta, SHA, entorno, datos, comando/pasos, esperado, observado, PASS/FAIL/BLOCKED y ruta de evidencia saneada**. Para teléfono, registrar prueba física, emulador o segundo cliente según corresponda. Para operaciones financieras, comparar libro y servidor; la captura de pantalla por sí sola no acredita movimiento. Para un ajuste en `apply_payment` incluir prueba nueva en `server/tests` y aviso al integrador conforme a AGENTS.

## Cierre

El integrador enumera capacidades desplegadas, versión API/APK, aprobaciones necesarias aún pendientes, pruebas omitidas y motivo. Entrega al dueño recorridos completos, no porcentajes subjetivos de avance. Para cualquier segunda ejecución, consulta el worklog, Git y evidencia antes de retomar la fila siguiente.
