# HANDOFF · Tienditapp · 2026-11-07 15:30 CST

Lo actualiza el integrador en cada hito. Es un reclamo pasado: si no cuadra con git, gana git.

## Objetivo inmediato
Entrega de la propuesta a las 16:00 (`docs/propuesta-4pm.md`) y primer pago real hecho desde la pantalla de la app.

## Estado verificado
- Pago real CoDi de $0.01 `PAID` a las 15:08 (tx `01M6VXE5HTXV66NPJCR1XY7T4A`), conciliado con pey.
- App en `app/`: 12 pruebas en verde; en local crea QR reales de pey y muestra el flujo completo (ver `docs/bitacora/2026-11-07-1530-a-app-mvp.md`).
- Integrado el prototipo independiente v0.4 mediante el [PR #3](https://github.com/carlosgdelvalle/tienditapp/pull/3), commit `fd9ac89`. CI de ese commit en verde; comprobación local `scripts/verificar.sh` aprobada (12 pruebas de la app principal).
- Prototipo v0.4: 15 pruebas aprobadas con PEY/OpenAI simulados y sintaxis JavaScript válida. Está en modo DEMO en `http://127.0.0.1:8765/` (dueño) y `/empleado`, con una copia migrada de la base demo v0.3. La app del MVP sigue en `app/`, según la decisión 0001.

## Identidad visual del MVP

- PR #5: logo oficial servido desde `assets/branding/`, integrado con el rediseño vigente de `main`. Validación local: 13 pruebas aprobadas y revisión visual con Playwright en 1440 × 1000 y 390 × 844; navegación, carrito, inventario y reportes sin errores. Véase `docs/bitacora/2026-11-07-1549-diseno-branding-mvp.md`.

## NO VERIFICADO
- Pago real desde la pantalla de la app (falta escanear un QR generado por la app).
- OpenAI en vivo (falta `OPENAI_API_KEY`; hoy usa el intérprete local y lo dice).
- Webhook en internet (falta URL HTTPS pública).

## Decisiones vigentes
`docs/decisiones/0001` (FastAPI), `0002` (alcance), `0003` (credenciales y pagos).

## No repetir
- No crear otra app en Next.js: el stack quedó en FastAPI (0001).
- La key de pey ya pasó por capturas y chats: rotarla al terminar el hackatón.

## Siguiente paso
Correr `uvicorn app.main:app --host 0.0.0.0 --port 8000`, cobrar una venta y que una persona pague $0.01 al QR de la pantalla.
