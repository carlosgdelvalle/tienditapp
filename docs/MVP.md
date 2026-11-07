# MVP · Abarpay v0.1

Versión fija para revisión: tag `mvp-v0.1` y rama `mvp` (commit `57c480a`). La app vive en [`app/`](../app/README.md).

## Qué es

La app del MVP de Abarpay (Python/FastAPI + SQLite + HTML/JS). Recorrido completo: el empleado escribe o dicta la venta, el servidor calcula el total con el catálogo, pide el QR a pey, espera el pago conciliando con pey, avisa en voz alta (también al dueño) y actualiza inventario y corte del día.

## Cómo correrla

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
cp .env.example .env      # PEY_API_KEY obligatoria; OPENAI_API_KEY opcional
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m pytest -q app/tests
```

Detalle en [`app/README.md`](../app/README.md). Reglas del repo en [`AGENTS.md`](../AGENTS.md).

## Evidencia

- `pytest app/tests`: 12 passed (pey simulado, etiquetado SIMULADO). CI de GitHub en verde.
- `GET /transaction/api-key` con la key nueva: HTTP 200.
- Pago real por CoDi de $0.01: tx `01M6VXE5HTXV66NPJCR1XY7T4A`, `PAID` a las 15:08 (QR creado por API y conciliado).
- La app creó QR reales de pey desde su pantalla (ventas de $58 que cobran $0.01 en modo demo).

## Pendiente (no verificado)

- Un pago real hecho al QR generado por la pantalla de la app.
- OpenAI en vivo: sin `OPENAI_API_KEY`, el dictado usa el intérprete local y la pantalla lo dice.
- Webhook en internet: implementado con firma Standard Webhooks; falta URL HTTPS pública.

## Qué revisar (para los agentes del equipo)

1. `app/main.py` → `apply_payment`: que una venta solo pase a pagada una vez, con monto exacto, y que el inventario no se descuente dos veces.
2. `app/pey.py` → `verify_webhook`: firma, tolerancia de tiempo y formato `v1,`.
3. `app/parse.py`: que los precios nunca salgan de la IA y que lo que no está en el catálogo vaya a `unmatched`.
4. `app/static/app.js`: que nunca se muestre un monto distinto del cobrado y que "pagado" solo dependa del servidor.
5. Seguridad: ninguna credencial en el código; `.env` ignorado.

Hallazgos: abran un issue o un PR contra `main` con evidencia (comando y resultado). La rama `mvp` y el tag `mvp-v0.1` quedan fijos para comparar.
