# Operación, despliegue continuo y recuperación

## Estado de partida y destino

El Blueprint actual arranca un proceso FastAPI contra un SQLite preexistente en disco y tiene `autoDeployTrigger: 'off'`. La CI actual revisa secretos y ejecuta dos suites Python; el script local verifica secretos y el MVP anterior. El APK no pasa por esa CI. [Blueprint actual](../../render.yaml) · [Workflow](../../.github/workflows/ci.yml) · [Runbook de la demo](../despliegue-render.md)

Mantener la demo accesible y aislada. Para el piloto usar servicio web Render con HTTPS y PostgreSQL gestionado en la misma región. Usar secretos e identidades diferentes por entorno, remitente y realm OIDC adecuados. El acceso de los agentes a trabajo local no requiere acceso a llaves de producción. Cotizar instancia web, base, copias, identidad y tráfico; obtener una aprobación de presupuesto antes de crear nuevos recursos de pago. Aplicar la transición de decisiones indicada en el manual de arranque.

## Pipeline a implementar

1. PR hacia main: escaneo redactado de secretos, pruebas Python del backend y regresiones del MVP mientras esté soportado; prueba de migraciones y aislamiento con PostgreSQL desechable, tests web por flujos afectados y Android debug unit tests/build en cambios Android o contratos compartidos. Poner comprobaciones obligatorias estables que resuelvan también cambios documentales; un job omitido no debe dejar un check requerido perpetuamente pendiente.
2. Ensayar cada migración desde una copia controlada sin exportar la BD a modelos. El proceso migrador usa identidad distinta del servicio. Serializar migraciones y despliegues; patrón expandir → backfill reanudable → cambiar lecturas → contraer cuando la versión anterior y sus APK queden fuera de soporte. Preservar índices, claves externas y conciliaciones del corte.
3. Tras integración verde de main, activar despliegue automático tras checks, sin aprobación humana por release. Confirmar en el Blueprint y panel el servicio, rama y política efectivos; evitar dos disparadores distintos para el mismo SHA. Exponer versión compilada y salud de BD sin datos sensibles. Smoke de producción sólo lectura: landing, versión, bases disponibles, denegación anónima de vistas restringidas. La prueba integral sintética con escrituras va a tenant de prueba segregado y se excluye de métricas.
4. El integrador asocia SHA, ejecución CI, deploy y ventana de métricas. Si falla readiness o smoke, detener la promoción o restaurar aplicación anterior compatible con el esquema expandido. Verificar cola, datos y salud; abrir incidencia. Un rollback de aplicación no deshace ventas ni migra una base en sentido inverso por defecto.
5. APK piloto: build de release firmado por custodio o job protegido, publicar versión, cambios, huella de certificado y SHA-256 del archivo en dominio del producto. Probar instalación limpia y actualización en sitio con trabajos offline pendientes. Configurar App Links con la huella del certificado de distribución. Conservar clave y respaldo recuperable fuera del repo. Mantener el contrato para la versión anterior soportada; una actualización obligatoria permite exportar o recuperar trabajo pendiente primero.

Render y su comportamiento de despliegue se revalidan durante la ejecución. [Despliegues Render](https://render.com/docs/deploys) · [App Links Android](https://developer.android.com/training/app-links)

## Correo SMTP2GO

- Remitente `mailer@abarpay.app`, host `mail.smtp2go.com`, puerto `2525`, STARTTLS obligatorio y validación de certificado y nombre. Separar nombre de remitente de identidad SMTP. Definir `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` en el entorno que efectivamente envía. Para el proveedor de identidad configurar su remitente personalizado si entrega verificación y recuperación. Sin fallback a texto plano.
- Sustituir la contraseña expuesta y cargar el reemplazo directamente en Render. En el Blueprint versionar sólo referencias de secretos sin valor. Resolver DKIM y verificación del dominio en SMTP2GO; comprobar alineación SPF/DKIM/DMARC mediante encabezados de un mensaje de prueba en un buzón autorizado. Verificar conectividad real desde el plan de Render elegido. [Configuración de SMTP2GO](https://www.smtp2go.com/setup/)
- Generar correo mediante outbox transaccional ligado a evento, destinatario y plantilla. ID único estable y expiración para invitación y recuperación. Evitar referencias de invitación o links de acceso en logs. Registrar estado en cola, aceptado por proveedor, rebotado, caducado y fallo reintentable; aceptación SMTP no demuestra entrega en bandeja. Consentimiento independiente y baja para recordatorios de fiado; plantillas no deben revelar saldos en asunto.
- Pruebas: SMTP local de captura con buzones ficticios, STARTTLS ausente, timeout, bounce y enlace vencido. Después una sola entrega autorizada real, comprobada por el destinatario. Un resultado incierto después de DATA requiere reconciliación; limitar reintentos y no generar enlaces válidos diferentes en cascada. Separar pruebas de correo del notificador local Telegram.

## Respaldo, restauración y observabilidad

**Objetivos iniciales de piloto:** proponer RPO ≤1 h y RTO ≤4 h, contrastar con la cobertura efectiva del plan contratado. Si no se cumplen, mostrar brecha y costo a Carlos antes del alta pública. Cifrar respaldos, restringir acceso y ensayar una restauración aislada sin afectar el servicio. Validar cantidades por tenant y referencias, importes, deuda, inventario, último evento disponible y tiempo hasta servicio saludable. Registrar RPO/RTO **medidos**. Inyectar un evento posterior al punto restaurado para demostrar cómo detectar y conciliar la brecha. Nunca sobrescribir el disco activo de la demo con una copia antigua.

| Señal inicial | Dueño / acción |
|---|---|
| Salud consecutiva fallida o 5xx >2% durante 5 min con ≥20 solicitudes | Operación: comprobar release y BD; si el despliegue causó regresión, aplicar rollback compatible |
| Registro bancario más antiguo de cinco días hábiles, webhook inválido recurrente o diferencia CoDi sin resolver | Pagos: consultar pey por referencia y tenant; conservar trazabilidad sin cuerpos ni CLABE |
| Cola de correo, sync o jobs sin progreso durante 15 min con conectividad demostrada | Operación: identificar el consumidor, revisar error tipificado y reanudar desde la operación; no duplicar negocio |
| Base/disco >80%, fallo de respaldo o restauración sin evidencia dentro de 30 días | Infraestructura: revisar crecimiento, retención y recuperación; elevar presupuesto antes de ampliar recursos |
| Campaña sin atribución, informe suprimido o retiro de consentimiento pendiente | Negocio/privacidad: mostrar cobertura y motivo, bloquear entrega cuando proceda |

Distinguir venta ocurrida en teléfono desconectado de un atasco de sincronización del servidor. Medir percentiles de latencia, antigüedad y cantidad con ventana, versión y región. En el simulacro inducir un error reversible en pruebas y observar aviso, respuesta, recuperación y tiempo. En evidencia pública usar sólo fixtures y métricas redactadas. Evitar tokens de sesión, CLABE, correo, payload de pago, deuda o serial del teléfono. Los registros de soporte identificables requieren acceso auditado.

## Entrega del runbook operativo

Documentar propietario de dominio/DNS, accesos por rol, rotación, política de retención, bajas de usuarios y solicitudes de acceso/borrado, contacto de soporte, procedimiento de cuenta comprometida, sustitución de banco, incidente de aislamiento, pérdida de teléfono y restauración. Verificar revocación de dispositivos y sesiones; una baja debe resolver ventas offline pendientes con trazabilidad. Cada incidente incluye contención, preservación de movimientos, comunicación al responsable y prueba de recuperación.
