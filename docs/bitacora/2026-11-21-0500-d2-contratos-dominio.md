# 2026-11-21 05:00 · d2 · contratos de dominio congelados

- **PR / commits:** paquete D2 · rama `cdv/plan-produccion-dsh`
- **Qué cambió:** Se congelan cuatro contratos de dominio — tenencia, banca/CoDi, diario offline y métricas — en `docs/produccion/contracts/`, más el inventario de rutas y eventos (`routes.md`). `02-contratos-y-tenencia.md` enlaza los cuatro contratos.
- **Por qué:** Base contractual para I1/I2/I3 y los hitos M. El único punto que marca una venta PEY pagada sigue siendo `apply_payment` en `server/payments.py`; una venta de contado usa `paid_cash` y el fiado `credit`.
- **Evidencia:**
  ```text
  d2-verifier (deepseek-account/deepseek-v4-pro @ high) = PASS sobre 6656f1e
  paid_pey solo en apply_payment (payments.py:222)
  firma HMAC igual a pey.py (tolerancia 300 s)
  QR sin campo destinatario -> cuenta de la API key
  webhook duplicado absorbido (webhook_events.webhook_id PK)
  ```
- **Riesgos abiertos:** los contratos describen PostgreSQL/RLS como destino (I1); el demo actual es SQLite. Sin Postgres de desarrollo local aún para ensayar la migración.
- **Siguiente:** abrir I1 (tenencia) cuando se disponga de PostgreSQL de desarrollo.
