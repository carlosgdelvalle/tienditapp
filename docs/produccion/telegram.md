# Notificador local a Telegram

Aviso directo a un chat privado aprobado cuando una pregunta de la cola requiere la decisión de Carlos. El notificador es solo saliente y usa una plantilla fija. No envía texto arbitrario, no imprime secretos ni cuerpos de error y nunca configura ni borra el webhook del bot.

## Qué envía

Cada aviso contiene el identificador de pregunta, la revisión y el indicador «Trabajo independiente», leídos de [AskAstra.md](AskAstra.md). Si se añade «Tema del aviso» con uno de los valores presupuesto, acceso, proveedor, piloto, dispositivo o criterio, el bot incluye la decisión correspondiente con texto predefinido. El detalle de la pregunta permanece en el Mac.

```text
Abarpay DSH
Pregunta Q-001 · r1
Trabajo independiente: sí
```

«Trabajo independiente: sí» indica que los paquetes independientes pueden seguir sin esperar la respuesta de Carlos. «no» indica que hay que esperar.

## Alcance del acceso

El notificador consulta la existencia del webhook únicamente si Carlos solicita emparejamiento. Nunca lo cambia. Durante la entrega mantiene privados el token, el chat_id, los cuerpos de error y el texto de las excepciones. No sigue redirecciones ni usa proxies, de modo que el token no pasa por un intermediario. No vuelve a enviar una revisión ya entregada.

## Requisitos previos

- El bot existente bajo control de Carlos. Puede conservar un webhook u otra integración. La entrega sólo necesita acceso HTTPS saliente a Telegram.
- El token del bot guardado en Keychain.
- El chat_id privado aprobado guardado en Keychain.
- Una pregunta abierta en [AskAstra.md](AskAstra.md) en el checkout coordinador con su encabezado y su línea de trabajo independiente.

## Configurar Keychain

El token y el chat_id se guardan en el llavero de macOS y se leen con `/usr/bin/security`. No se escriben en el historial del shell. Para agregar cada secreto abre Keychain Access, selecciona el llavero «login» y usa Archivo → Nuevo elemento de contraseña.

| Elemento | Nombre del elemento | Nombre de cuenta | Contraseña |
|---|---|---|---|
| Token | `abarpay-dsh-telegram` | `bot-token` | el token que entrega BotFather |
| Destino | `abarpay-dsh-telegram` | `chat-id` | el id numérico del chat privado |

El «nombre del elemento» es el servicio que lee el notificador y el «nombre de cuenta» es la cuenta. No uses `security add-generic-password` en una terminal, porque la contraseña quedaría en el historial o en la lista de procesos.

## Obtener el chat_id privado

Desde la cuenta de Carlos, abrir el chat privado con su bot y pulsar **Iniciar**. Si ya conoce el ID verificado de ese chat, guardarlo directamente en el llavero. Un webhook existente puede seguir recibiendo actualizaciones mientras DSH envía avisos.

Para obtener el ID sin servicios de terceros, ejecutar personalmente en una Terminal privada de Arquimedes:

```sh
scripts/notify-carlos --whoami
scripts/notify-carlos --pair
```

Confirmar primero el usuario del bot. Si hay un webhook, solicitar el ID al operador de esa integración y usar la configuración manual. Si otro proceso consume actualizaciones por polling, usar también el ID de esa integración. Cuando el bot esté libre para el emparejamiento, copiar la frase aleatoria en el chat privado propio, pulsar Intro en Terminal y guardar el único ID que coincidió en el llavero. El helper examina una página sin offset; nunca vacía la cola. Si no encuentra la frase o aparece más de un destino, detiene la operación. La frase y el ID de configuración se manejan en Terminal, fuera de prompts de DSH y capturas públicas.

## Confirmar el emparejamiento

Ejecuta `--whoami` para ver la identidad del bot.

```bash
scripts/notify-carlos --whoami
```

La salida muestra el `@usuario` y el `id` del bot. Confirma que coincide con tu bot existente y que el `chat-id` guardado es el chat privado de Carlos. Para la primera entrega autorizada, el coordinador crea una pregunta de prueba con ID libre, revisión 1, «Trabajo independiente: sí», «Tema del aviso: acceso» y «Estado: abierta». Carlos confirma la recepción en su teléfono, se repite el mismo ID para verificar la deduplicación y se cierra la entrada. Los trabajadores ordinarios no leen el llavero. El coordinador invoca únicamente este comando; si se requiere una barrera entre procesos del mismo usuario, ejecutar el notificador con una cuenta de macOS dedicada y permisos separados sobre la cola.

## Uso

```bash
scripts/notify-carlos Q-001                # envía si la revisión no fue enviada
scripts/notify-carlos Q-001 --preview      # muestra el mensaje sin red ni estado
scripts/notify-carlos Q-001 --resolve-sent    # marca un registro dudoso como enviado
scripts/notify-carlos Q-001 --resolve-unsent  # borra un registro dudoso para reenviar
```

Códigos de salida: `0` enviado u omitido, `1` fallo definitivo o no enviado, `2` requiere resolución manual o espera por límite de Telegram.

## Estado y deduplicación

El notificador guarda el estado en `~/Library/Application Support/abarpay-dsh/notify-carlos-state.json` en macOS. Antes de enviar persiste una reserva «pending» y mantiene un bloqueo exclusivo durante todo el envío, de modo que dos ejecuciones simultáneas no duplican el aviso.

- `sent`: la revisión ya se entregó y se omite.
- `pending`: el envío quedó interrumpido o está en curso, y no se reenvía solo.
- `uncertain`: la entrega no se pudo confirmar, y no se reenvía solo.

Cuando una revisión queda en `pending` o `uncertain`, verifica a mano en el chat si llegó el aviso y resuélvelo con `--resolve-sent` o `--resolve-unsent`. Una caída después de que Telegram aceptó el mensaje deja la reserva `pending`, y la siguiente ejecución se detiene en lugar de reenviar.

## Límites y reintentos

El notificador reintenta los fallos de conexión previos a enviar y respeta `retry_after` en las respuestas 429. Si Telegram pide esperar más que el tope de 60 segundos, el notificador no reintenta antes de tiempo. Registra una hora de reintento y termina, y la siguiente ejecución espera hasta esa hora.

## Variables de entorno

- `ASK_ASTRA_FILE`: ruta alternativa a la cola de decisiones.
- `ABARPAY_DSH_STATE_DIR`: carpeta alternativa para el archivo de estado.
- `ABARPAY_DSH_TIMEOUT`: segundos de espera de la conexión HTTPS, 30 por defecto.

## Verificación

```bash
scripts/notify-carlos Q-001 --preview   # sin red y sin estado
uv run --with pytest --no-project python -m pytest -q scripts/tests
```

La prueba aislada cubre la deduplicación, la ejecución concurrente, la caída tras la reserva, el 429 diferido y la resolución manual. La confirmación del aviso real en el chat privado la hace Carlos después del emparejamiento.


[Telegram: sendMessage](https://core.telegram.org/bots/api#sendmessage) · [Telegram: getUpdates](https://core.telegram.org/bots/api#getupdates) · [Telegram: getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo)
