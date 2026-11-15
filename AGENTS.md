# AGENTS.md · Abarpay

Manual único para cualquier agente (Codex, Claude, ChatGPT) y para las personas del equipo. Si algo aquí choca con otro archivo, gana este, salvo las decisiones vigentes de `docs/decisiones/`, que ganan sobre todo.

## Qué es esto

Abarpay: cobros CoDi verificados, ventas e inventario para la tiendita de barrio, desde el teléfono. Hackatón DevDay Exchange CDMX, con pey (API de CoDi) y OpenAI. Entrega final: domingo 8-nov-2026, 13:00 CDMX, por correo a hola@aibuilders.lat. Producto completo en [`README.md`](README.md).

## Mapa de ruteo

| Necesitas | Ruta | Regla |
|---|---|---|
| Correr la app y el demo | `server/README.md` y `docs/despliegue-render.md` | El `.env` nunca se sube; la demo pública vive en Render |
| Lógica de pagos (la única que marca una venta pagada) | `server/payments.py` → `apply_payment` | Cambios aquí requieren prueba nueva en `server/tests/` y aviso al integrador |
| Cliente de pey y firma de webhooks | `server/pey.py` | Base `https://api.pey.mx`; montos en pesos hacia pey, en centavos adentro |
| Dictado → carrito | `server/parser.py` | Solo se elige `productId` del catálogo; los precios salen de la base, nunca de la IA |
| Esquema y catálogo demo | `server/db.py` | Catálogo ficticio; la base **activa** vive en el disco de Render, la local es de desarrollo |
| Pantallas del teléfono | `android/app/src/main/java/mx/abarpay/mobile/` | Español, verbos simples, sin tecnicismos |
| Consola del dueño | `server/static/console.html` → `/console` | Vanilla HTML/CSS/JS; PIN demo en header `X-Owner-Pin` |
| Despliegue público | `docs/despliegue-render.md` | Render `abarpay-api`, disco persistente `/var/data`, `autoDeploy` apagado |
| Qué se decidió | `docs/decisiones/` | Solo se agrega. Cambiar una decisión = PR con OK de la mesa |
| Estado del equipo | `HANDOFF.md` | Lo actualiza el integrador en cada hito; es un reclamo, verifícalo contra git |
| Horarios y recortes | `docs/plan-entrega.md` | El pago real y la confirmación verificada no se recortan |
| Propuesta, modelo de negocio, boceto | `docs/` | Cifras sin fuente no van a láminas |
| Láminas del pitch | `presentacion/` | En orden numérico |
| Prototipo de referencia (Ricardo) | `prototypes/tiendita-inteligente-pey-v0.3/` | Referencia; no es la app del MVP |
| Qué pasó en cada PR | `docs/bitacora/` | Una entrada por PR; no se editan |

## Reglas duras

1. **Credenciales solo en `.env`** (ignorado por git) y en variables de entorno del servidor. Nunca en código, capturas, logs ni chats. Si una key se filtra, se rota: borrar el archivo no basta.
2. **Cada pago de prueba es dinero real** (pey no tiene sandbox). Monto: `$0.01 MXN`. Lo hace una persona desde su app bancaria. Ningún script ni agente paga.
3. **Una venta solo pasa a pagada** en `apply_payment`, con un webhook de firma válida o con la conciliación contra `GET /transaction/codi/qr/{id}`. La pantalla del cliente y el QR no prueban nada.
4. **Nunca se muestra un monto distinto del cobrado.** En modo demo la pantalla dice "Modo demo: se cobra $0.01".
5. **Precios del catálogo en la base**, nunca del cliente ni de la IA.
6. **Lo simulado se etiqueta SIMULADO** (las pruebas usan un `FakePey` marcado así).
7. **Cero datos de terceros.**
8. **Nada está "listo" sin evidencia** en el PR.
9. **La base activa de la demo vive en el disco de Render** (`/var/data/abarpay.db`). La base local (`server/data/`) es solo para desarrollo; no tratarla como activa ni restaurarla encima de transacciones nuevas.

## Cómo se trabaja

1. Rama por tarea, PR chico contra `main`.
2. `./scripts/verificar.sh` en verde antes del PR (lo mismo corre la CI).
3. Entrada en `docs/bitacora/` en el mismo PR (copia `_plantilla.md`).
4. No edites `HANDOFF.md` salvo que seas el integrador.
5. El servicio de Render tiene `autoDeploy` apagado: **un merge a `main` no lo despliega**. Coordinar el redeploy manual y registrarlo en [`docs/worklog.md`](docs/worklog.md).

## Comandos

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt -r server/requirements-dev.txt
cp .env.example .env  # PEY_API_KEY, PEY_WEBHOOK_SECRET, MODO_DEMO, OWNER_PIN
ABARPAY_LOAD_DOTENV=1 ABARPAY_DB=server/data/abarpay.db MODO_DEMO=true \
  uvicorn server.main:app --host 0.0.0.0 --port 8000
python -m pytest -q server/tests
./scripts/verificar.sh

# Android: JDK 17/21, Android SDK 35, Gradle 8.13
cd android && ./gradlew testDebugUnitTest assembleRelease
```

El demo público corre en Render (`https://abarpay-api.onrender.com`); los pasos de despliegue, respaldo y reversión están en [`docs/despliegue-render.md`](docs/despliegue-render.md).
