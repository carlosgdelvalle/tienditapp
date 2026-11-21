# Local Telegram notifier

Notify Carlos in the approved private chat when a queued question needs his decision. The outbound notifier uses a fixed template. It excludes arbitrary question text, secrets, and error bodies and leaves the bot’s webhook configuration intact.

## Notification contents

Each notification contains the question ID, revision, and `Trabajo independiente` indicator from [AskAstra.md](AskAstra.md). The optional `Tema del aviso` field accepts `presupuesto`, `acceso`, `proveedor`, `piloto`, `dispositivo`, or `criterio`. The bot maps these values to predefined Spanish decision text. The full question stays on the Mac.

```text
Abarpay DSH
Pregunta Q-001 · r1
Trabajo independiente: sí
```

`Trabajo independiente: sí` means other packages can proceed while Carlos considers the question. Use `no` when work must wait.

## Access boundaries

The notifier checks for a webhook only when Carlos requests pairing. It never changes the webhook. During delivery, the token, chat ID, error bodies, and exception text stay private. The client connects directly to Telegram, excludes proxies, and does not follow redirects. A delivered revision is deduplicated.

## Prerequisites

- The existing bot under Carlos’s control. It can retain its webhook or another integration. Delivery requires outbound HTTPS access to Telegram.
- Bot token and approved private chat ID stored in Keychain.
- An open question in [AskAstra.md](AskAstra.md) in the coordinator checkout with its heading and independent-work field.

## Configure Keychain

The helper reads both values using `/usr/bin/security`. For each item, open Keychain Access, select the login keychain, and choose **Archivo → Nuevo elemento de contraseña**. Avoid entering credentials in shell commands or command-line arguments that could appear in history or process listings.

| Item | Item name (service) | Account name | Password field |
|---|---|---|---|
| Token | `abarpay-dsh-telegram` | `bot-token` | The token supplied by BotFather |
| Destination | `abarpay-dsh-telegram` | `chat-id` | The approved numeric private chat ID |

## Obtain the private chat ID

From Carlos’s account, open the private bot chat and tap **Iniciar**. If the verified chat ID is already known, store it directly in Keychain. An existing webhook can continue receiving updates while DSH sends notifications.

To discover the ID without a third-party service, Carlos runs these commands himself in a private interactive terminal on Arquimedes:

```sh
scripts/notify-carlos --whoami
scripts/notify-carlos --pair
```

Confirm the bot username first. If an existing webhook or polling process handles updates, get the ID from its operator and use manual configuration. Otherwise, send the random pairing phrase in the private chat, press Enter in Terminal, and store the one matching ID in Keychain. The helper reads one page without an offset and leaves the queue intact. It stops if it finds no unique private match. Keep the pairing phrase and private ID outside DSH prompts and public screenshots.

## Confirm pairing

Run `--whoami` to identify the bot:

```bash
scripts/notify-carlos --whoami
```

The output shows the bot username and ID. Confirm the expected bot and approved private destination. For the first authorized delivery, create a test question with an unused ID, revision 1, `Trabajo independiente: sí`, `Tema del aviso: acceso`, and `Estado: abierta`. Carlos confirms receipt on his phone. Run the same ID again to prove deduplication and close the entry. Ordinary workers do not read Keychain. The coordinator invokes the notifier command. If processes under the same user must be isolated, run the notifier under a dedicated macOS account with separate queue permissions.

## Usage

```bash
scripts/notify-carlos Q-001                  # send if this revision has not been delivered
scripts/notify-carlos Q-001 --preview        # preview without network or persistent state
scripts/notify-carlos Q-001 --resolve-sent   # mark an uncertain delivery as received
scripts/notify-carlos Q-001 --resolve-unsent # clear an uncertain delivery after confirming it did not arrive
```

Exit codes: `0` means delivered or already sent, `1` means definite failure or no delivery, and `2` means manual resolution or a Telegram rate-limit wait is required.

## State and deduplication

On macOS the notifier stores state in `~/Library/Application Support/abarpay-dsh/notify-carlos-state.json`. Before sending it persists a `pending` reservation and holds an exclusive lock throughout dispatch to serialize concurrent runs.

- `sent`: The revision was delivered. Skip it.
- `pending`: Dispatch is in progress or was interrupted. Do not resend automatically.
- `uncertain`: Delivery could not be confirmed. Do not resend automatically.

For an unresolved `pending` or `uncertain` revision, inspect the private chat and use `--resolve-sent` or `--resolve-unsent` according to what actually arrived. If the process crashes after Telegram accepted a message, the reservation survives and the next run stops for review.

## Rate limits and retries

Retry connection failures that occur before dispatch. Respect Telegram’s `retry_after` on HTTP 429. When the required wait exceeds the 60-second cap, record the earliest retry time and exit. A subsequent invocation respects that deadline.

## Environment variables

- `ASK_ASTRA_FILE`: Alternate path to the decision queue.
- `ABARPAY_DSH_STATE_DIR`: Alternate persistent state directory.
- `ABARPAY_DSH_TIMEOUT`: HTTPS connection timeout in seconds, default 30.

## Verification

```bash
scripts/notify-carlos Q-001 --preview   # no network or persistent state
uv run --with pytest --no-project python -m pytest -q scripts/tests
```

The isolated tests cover deduplication, concurrent execution, a crash after reservation, deferred 429 handling, and manual resolution. Carlos verifies real delivery to the private chat after pairing. [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage) · [Telegram getUpdates](https://core.telegram.org/bots/api#getupdates) · [Telegram getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo)
