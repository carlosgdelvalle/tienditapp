# Pendientes de Carlos · piloto de producción de Abarpay

Esta hoja pública registra la acción, el hito y la evidencia que permite cerrarla. Los valores de credenciales, destinatarios, acuerdos privados y datos bancarios viven en sus sistemas correspondientes.

| Estado | Acción de Carlos | Se necesita para | Evidencia de cierre sin datos sensibles |
|---|---|---|---|
| Pendiente | Rotar la contraseña SMTP2GO expuesta en chat. Introducir el reemplazo directamente en Render como `SMTP_PASSWORD`, establecer `SMTP_USERNAME` y revocar el valor expuesto. Si el proveedor de identidad usa SMTP propio, actualizar su secreto también | M5 correo real | Fecha de rotación y revocación; prueba TLS y correo recibido en buzón autorizado. Si el valor expuesto sigue vigente, revocarlo de inmediato |
| Terminado | Verificar `abarpay.app` como dominio remitente, DNS y alineación SPF/DKIM/DMARC. Remitente `mailer@abarpay.app` en `mail.smtp2go.com:2525`, con STARTTLS | M5 / G2 | Resultado de entrega, autenticación y rebote sin publicar cabeceras personales |
| Terminado | Emparejar en Arquimedes el bot de Telegram existente con el chat privado de Carlos. Cargar el token mediante Acceso a Llaveros y ejecutar la prueba acordada | E1 notificaciones | Bot esperado, aviso de prueba recibido una vez, sin token ni chat ID en la evidencia |
| Pendiente | Conectar el Android por USB, autorizar depuración y elegir un perfil apto para pruebas | B2/B4/B6/B8 | ADB autorizado, modelo/versión y disponibilidad registrados sin número de serie |
| Pendiente | Confirmar acceso de DSH al proveedor para sesiones headless Pro/Flash y alcance Git/CI de integración | E0 / G2 | Modelo observado por sesión y alcance verificado, sin credenciales |
| Pendiente | Aprobar cotización de Render, PostgreSQL gestionado, identidad y correo. Registrar la transición acordada de demo/manual a CD tras CI para el SaaS | I5 / G2 | Tope aprobado, entornos y decisión de la mesa. Sin aprobación rutinaria por versión |
| Pendiente | Habilitar dominio, OIDC de comerciantes y Entra/MFA del equipo con roles separados | I2 / G2 | Identidad piloto y equipo autenticados, recuperación y revocación comprobadas |
| Pendiente | Confirmar con pey la modalidad comercial y credenciales apropiadas para cuentas de comercios independientes; coordinar la prueba humana de MXN 0.01 | CoDi real | Referencia no sensible de aprobación y resultado de conciliación sin CLABE |
| Pendiente | Identificar custodio de clave de firma APK y probar respaldo recuperable | G2 distribución | Huella pública del certificado y actualización en sitio aprobada |
| Pendiente | Nombrar responsable de facturación manual y tratamiento de cancelación/reembolso en Control | Piloto Control | Términos y evidencia de consentimiento/cobro en libro interno |
| Pendiente | Nombrar socio de cadena de suministro, propósito, responsable legal y encargado de retiro de consentimientos | M7 entrega real | Acuerdo, revisión de divulgación y responsable documentados en sistema privado |
| Pendiente | Coordinar observación de un dueño y un cajero para los flujos de venta, interrupción y cierre | B6 y afirmaciones comerciales | Hallazgos consentidos y anonimizados con acciones; ningún dato de clientes |

[Inicio del programa](docs/produccion/00-EMPIEZA-AQUI.md) · [Dependencias y aceptación](docs/produccion/09-paquetes-y-aceptacion.md)
