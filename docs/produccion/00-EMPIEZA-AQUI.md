# Abarpay · instrucciones para el coordinador Pro

**Resultado:** una persona abre una tienda en México desde su Android, cobra aun con una interrupción de red, concilia su propia cuenta CoDi y administra su tienda desde el navegador. Carlos y su equipo operan el SaaS desde una consola separada. La entrega incluye pilotos medibles y evidencia reproducible de recuperación.

## Primera instrucción para DSH

> Lee este archivo y [el tablero de paquetes](09-paquetes-y-aceptacion.md). Actúa como coordinador DeepSeek Pro en Arquimedes. Recupera el worklog y compara su revisión con Git. Empieza por E0, distribuye los paquetes listos y verifica cada implementación con otra sesión. Ejecuta y deja evidencia. Si hay una decisión externa, regístrala, avisa a Carlos y continúa los paquetes independientes. Sólo Carlos decide cuándo consultar a Astra.

## Primer arranque y reanudación

1. En Arquimedes abre el checkout que contiene **este paquete**. La referencia del producto analizado es `75c1f35`, no una revisión a la que deba volver el árbol. Lee [las reglas del proyecto](../../AGENTS.md), las decisiones vigentes y la bitácora. Conserva cambios ajenos. La aplicación activa es Android + `server/`; la decisión 0005 sustituyó al MVP de `app/`.
2. Lee [agentes y worktrees](01-agentes-y-trabajo.md). Comprueba modelos, entorno Python y permisos con datos ficticios. Prueba el [aviso directo por Telegram](telegram.md). Si faltan token, móvil o presupuesto, registra el bloqueo puntual en [PendientesCarlos](../../PendientesCarlos.md) y avanza con los paquetes sin esa dependencia.
3. Mantén **un solo** `docs/worklog.md` local en el checkout coordinador. Si falta en el clon, créalo allí con objetivo, instrucciones, decisiones, propietario, estados, dependencias y pruebas. Nunca lo incluyas en un commit. Usa `AskAstra.md` en este directorio para las decisiones; sólo el coordinador edita la copia de trabajo de la cola. Los demás remiten hallazgos al coordinador.
4. Selecciona una fila lista del tablero; copia su contrato de asignación, crea un worktree y designa un verificador distinto. Un paquete queda aceptado al pasar en el SHA integrado. En cada reinicio, recupera leases, sesiones, ramas y resultados antes de volver a llamar a proveedores.
5. Cierra la entrega con los recorridos de la tabla de aceptación. Una etiqueta de Trello, una compilación o un proveedor configurado por sí solos no acreditan un resultado de negocio.

## Inventario de Arquimedes y dependencias

Comprobado por SSH el 21-nov: Apple silicon, 16 GB RAM, más de 170 GiB libres, Git, Python 3.12 en `.venv`, `uv`, Gitleaks, JDK 21, Android SDK 35/build-tools 35.0.0, ADB y DSH Desktop 0.2.2-rc.5. Los parches Pro y Flash se compusieron con la CLI instalada; esto verifica los nombres de modelo, no el acceso de facturación ni la identidad de una ejecución real. El repo remoto de esta máquina estaba en `75c1f35` antes de recibir el paquete.

Para ejecutar las puertas, desde el checkout en la sesión de integración:

```sh
export PATH="$HOME/.local/bin:$HOME/Library/Android/sdk/platform-tools:$PATH"
export JAVA_HOME="$HOME/.local/share/tienditapp/jdk-21/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
source .venv/bin/activate
./scripts/verificar.sh
python -m pytest -q server/tests
adb devices
(cd android && ./gradlew testDebugUnitTest assembleRelease)
```

**Dependencia nueva para I1:** una instancia PostgreSQL real de desarrollo y un cliente de migración para el diagnóstico. No aparecieron `psql`, `pg_ctl` ni Docker en los PATH de uso habitual. Elegir por defecto PostgreSQL local de la misma versión mayor que Render; instalar el servidor/cliente para el usuario de pruebas o usar un servicio PostgreSQL efímero de CI mientras se prepara el Mac. No conectar las pruebas de aislamiento a la base de producción. Docker y GitHub CLI son opcionales; Git, Actions y una instancia PostgreSQL accesible bastan. Para G1 usar un navegador con automatización y accesibilidad disponibles; provisionar sus dependencias en el entorno del proyecto. Una segunda sesión o emulador sirve como segundo POS, el teléfono físico queda reservado para los recorridos de aceptación. No se necesita OpenClaw.

## Ruta por decisión

| Necesidad | Documento |
|---|---|
| Identidad, aislamiento, API, migración | [Tenencia](02-contratos-y-tenencia.md) |
| Menos pasos en caja, retorno tras interrupción, sugerencias de Trello | [Ergonomía](03-flujos-y-ergonomia.md) · [Matriz de tarjetas](trello-cobertura.md) |
| Registro de tienda, QR de sesión, alta CLABE y cobro | [Identidad y pey](04-identidad-onboarding-y-pey.md) |
| Venta sin red, recibo de mercancía, cierre, reposición, fiado | [Operación móvil](05-caja-offline-e-inventario.md) |
| Página pública, APK y prueba comercial | [Landing y ventas](06-landing-y-comercial.md) |
| Dueños del SaaS, indicadores, campañas y socio de datos | [Consola de plataforma](07-consola-saas-y-datos.md) |
| Mail, CI, producción, versiones, respaldo y reversión | [Operación](08-operacion-y-despliegue.md) |
| Pregunta que requiere decisión | [Cola manual](AskAstra.md) · [Telegram](telegram.md) |

## Autoridad de ejecución

Carlos eligió DeepSeek Pro y Flash para este repositorio y pidió CD sin aprobación humana rutinaria por versión. Usa únicamente esos modelos para el programa. Las decisiones anteriores de entrega demo sobre SQLite, PIN, CLABE en portal y despliegue manual requieren una decisión nueva y el procedimiento de aprobación de la mesa ya documentado. Solicita **una transición de política**, no una autorización por cada paquete. A partir de su habilitación, la integración verde en main despliega automáticamente. Mantén aislada la demo activa durante la migración.

La creación de recursos con costo espera una cotización aprobada; la exportación real a socios requiere consentimiento, revisión y acuerdo; cada pago de prueba real de MXN 0.01 lo opera una persona. Trabaja con datos SIMULADOS hasta cumplir el requisito de cada integración. La actividad de desarrollo no habilita enviar secretos, CLABE, bases, mensajes de clientes ni datos comerciales identificables a los modelos. Antes de publicar evidencia revisa que sólo incluya fixtures seguros. Para este programa, los pilotos y las altas reales se habilitan por capacidad verificada.
