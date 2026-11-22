# 2026-11-21 21:18 · tenencia · recorrido del dueño PG (QR + primera venta en efectivo)

- PR / commits: rama cdv/integra-tenencia · server/business_pg.py, server/auth.py, server/auth_routes.py, server/runtime.py, server/requirements.txt, server/tests/test_runtime_pg.py
- Qué cambió: Rutas de negocio PG con RLS (catálogo, barcode/SKU por tenant, venta en efectivo idempotente y recibo) y SVG del QR en el reto. La venta en efectivo bloquea productos FOR UPDATE en orden, rechaza stock insuficiente y deriva un id de venta por tenant con UUIDv5 desde Idempotency-Key. Email/name de Auth0 se leen del claim con namespace https://abarpay.app/email y https://abarpay.app/name. /console sirve server/static/owner-console.html.
- Por qué: Recorrido del dueño (J-01/J-11 y B1/B2) sobre PostgreSQL con aislamiento RLS; la ruta de efectivo no toca apply_payment ni pey.
- Evidencia:

      python -m pytest -q server/tests/test_runtime_pg.py   # 10 passed (~2.5s)
      python -m pytest -q server/tests                       # 301 passed, 20 skipped

- Riesgos abiertos: Android (activación/escáner) pendiente; la consola del dueño la aporta el integrador (18c779c y 20c09a7).
- Siguiente: activación y escáner Android en archivo separado; verificación Chrome del integrador sobre el candidato anclado.
