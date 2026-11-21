# Organización de agentes y recuperación del trabajo

## Geometría según la dependencia

Un coordinador Pro es propietario de contratos e integración. Para investigar problemas independientes, reparte preguntas ciegas y combina resultados después. Para dinero, identidad y sincronización, una persona lógica decide el contrato y otra lo comprueba. Los estudios disponibles comparan topologías en tareas específicas; el número óptimo de agentes de Abarpay se obtiene midiendo esta máquina. [Estudio de topologías](https://arxiv.org/abs/2512.08296) · [Experiencia de ingeniería multiagente](https://www.anthropic.com/engineering/multi-agent-research-system)

| Agente | Entrada y salida | Verificación |
|---|---|---|
| Coordinador Pro | DAG, contratos congelados, asignaciones, resolución de conflictos e integración | Ejecuta las puertas sobre el SHA integrado y publica el índice de evidencia |
| Ingeniería industrial Pro | Observa el entorno de la tienda, diseña la secuencia sin código, entrega tarjeta y retorno tras distracción | El implementador recorre la tarjeta, propone reducciones y devuelve objeciones al diseñador |
| Implementador Pro | Cambios con consecuencias en dinero, identidad, aislamiento, revelación o recuperación | Segundo Pro con contexto limpio y ejemplos derivados del contrato |
| Implementador Flash | Pantallas, fixtures, métricas, migraciones ya diseñadas, documentación y pruebas acotadas | Otro agente reproduce el resultado; puede ser Flash si el impacto está acotado |
| Evaluadores comerciales | Dos Pro y dos Flash evalúan por separado un conjunto SIMULADO común | El coordinador comprueba cálculos, corrige errores de unidad y conserva el desacuerdo |
| Verificador | Recibe primero el requisito; fija resultados esperados; después inspecciona el commit candidato | Dictamen PASS, FAIL o BLOCKED con reproducción y límites |

Un trabajador solicita revisión de otro agente enviando al coordinador el ID, SHA y pregunta. El coordinador despacha o programa esa sesión dentro del cupo. El verificador puede preguntar directamente al autor por el contrato; ambos registran el caso concreto. Un tercer parecer sólo se abre cuando hay desacuerdo material y una pregunta resoluble. Evita árboles recursivos sin dueño del resultado.

## Arrancar DSH en Arquimedes

Se verificó en el perfil distribuido `headless` de DSH Desktop 0.2.2-rc.5 la presencia de `subagent`, `subagent_fork`, perfiles por parche, entrada estándar y reanudación por ID. El perfil predeterminado seleccionaba Flash. Declara el modelo por archivo para cada proceso. Desde la raíz del repo, con sesión iniciada o credencial del proveedor provisionada por el operador para el modo elegido:

```sh
DSH_BIN="/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"
PLAN_ROOT="$(pwd)/docs/produccion"
"$DSH_BIN" headless --help
"$DSH_BIN" headless --patch "$PLAN_ROOT/perfiles/pro.yml" --permission-mode workspace-write \
  'Lee docs/produccion/00-EMPIEZA-AQUI.md. Inicia por E0 y recupera el estado del coordinador.'
```

Para un trabajador en un worktree, selecciona el parche [Flash](perfiles/flash.yml) o [Pro](perfiles/pro.yml) explícitamente. El ejemplo usa una asignación local redactada por el coordinador. La CLI admite la lectura desde stdin:

```sh
"$DSH_BIN" headless --patch "$PLAN_ROOT/perfiles/flash.yml" --permission-mode workspace-write - < "$ASIGNACION_LOCAL"
```

Para reanudar usa el mismo directorio/perfil y `--session-id "$SESION_DSH"`. El coordinador realiza los commits si el sandbox del trabajador no tiene acceso al directorio Git común. E0 verifica en una tarea inocua la identidad **observada** del modelo en los eventos o la interfaz, el directorio efectivo y la ausencia de secretos de producción. No guardes trazas completas con prompts o variables en Git. La presencia de un plugin no demuestra que una subllamada herede el modelo correcto. Cuando el dispatcher nativo no permita fijarlo o comprobarlo, usa procesos headless independientes con los parches. Si las credenciales de Desktop no están disponibles en headless, usa sesiones Desktop con selección explícita mientras Carlos habilita el acceso del perfil; evita volcar la configuración compuesta o copiar credenciales desde el llavero.

## Reparto y exclusión mutua

Empieza con coordinador y dos trabajadores. Tras dos paquetes registra tiempo total y de espera, reprocesos, presión de memoria y límites del proveedor. Sube a cuatro trabajadores ligeros cuando aumente el trabajo aceptado por hora. Si predominan reintentos o espera de compilación, reduce el cupo. En el Mac de 16 GB usa **una** compilación Gradle, un propietario de ADB, un escritor de la secuencia de migraciones y un despliegue productivo. Los demás pueden construir y verificar en otros subsistemas.

Un worktree por paquete con rama `cdv/<paquete>` basada en el SHA contractual. Mantén el checkout coordinador para el worklog y revisión integrada. Divide ediciones de `server/main.py`, `db.py` y la consola por responsabilidad o secuéncialas; dos agentes con la misma ruta de escritura esperan al contrato o al integrador. No hagas resets o limpiezas para resolver divergencia. Cada PR conserva su bitácora, mensaje de commit español y trazabilidad a paquete.

**Plantilla del implementador**

> Paquete / revisión base / dependencia aceptada / rutas con permiso de escritura / evento inicial / datos de entrada / ejemplo de éxito / caso interrumpido / resultado durable / límite de costo y tiempo / comandos de prueba / verificador previsto. Entrega SHA, decisiones tomadas y cualquier resultado sin verificar.

**Plantilla del verificador**

> A partir del contrato reproduce dos casos normales, un fallo relevante y la reanudación si aplica. En un checkout limpio comprueba los datos observables antes y después, registra comandos y entorno. Clasifica las diferencias por impacto y decide PASS, FAIL o BLOCKED. Indica qué evidencia adicional cambiaría tu decisión.

**Registro mínimo en el worklog:** paquete, estado (`ready/leased/implemented/verifying/accepted/blocked`), sesión y rama, persona lógica, base y candidato, hora del último avance, evidencia, siguiente paso. Antes de recuperar un lease comprueba si hay proceso vivo, cambios sin commit, verificador activo o efecto externo ambiguo. Recupera el trabajo existente. Una caída después de un cobro, correo o push requiere consultar el resultado antes de reintentar.

## Escalación

Una pregunta para Carlos abre una entrada en [AskAstra](AskAstra.md). El coordinador usa el [notificador](telegram.md). Carlos responde él mismo o decide consultar a Astra. Una decisión cambia las entradas afectadas del worklog y se comunica de forma directa a responsables y verificadores; los paquetes independientes siguen. Registra uso de tokens por modelo, latencia y porcentaje de paquetes reabiertos para decidir si otro agente aporta valor.
