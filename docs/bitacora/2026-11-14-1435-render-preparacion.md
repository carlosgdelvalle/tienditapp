# 2026-11-14 14:35 · despliegue · Preparación de Render y respaldo SQLite

- **PR / commits:** rama `cdv/despliegue-render`; PR pendiente.
- **Qué cambió:** configuración final `render.yaml` para el backend `server/`,
  una instancia Python y disco de 1 GB en `/var/data`. El arranque exige una base
  existente. Guía de migración, validación, corte y reversión en
  `docs/despliegue-render.md`, enlazada desde el README del servidor.
- **Por qué:** alojar la demo independientemente del portátil y sus cambios de
  red, conservando SQLite, productos y operaciones existentes.
- **Evidencia:**
  ```text
  Validación de render.yaml contra https://render.com/schema/render.yaml.json
  Correcta.

  SQLite Connection.backup de server/data/abarpay.db a respaldo local ignorado
  integrity_check: ok; foreign_key_check: sin errores.
  17 productos; 11 ventas; 8 pagos; todas las tablas respaldadas.

  Arranque de create_app sobre una copia aislada del respaldo, sin cliente PEY
  /api/health, /api/bootstrap y /console: HTTP 200.
  Cantidades de filas de todas las tablas preservadas tras el arranque.

  ./scripts/verificar.sh
  16 passed; escaneo mínimo de secretos sin hallazgos (gitleaks no instalado).

  python -m pytest -q server/tests
  57 passed; FakePey SIMULADO, sin credenciales reales.

  Creación de servicio en el workspace Render autorizado
  HTTP 402: Payment information is required to complete this request.
  Lista de servicios posterior: vacía.

  GET local /api/health posterior
  HTTP 200, ok=true.
  ```
- **Riesgos abiertos:** falta método de pago en Render. No se ha creado servicio
  ni disco ni importado la base remota. El respaldo es preliminar; se necesita
  otro tras detener escrituras para el corte final. Falta verificar secretos,
  SSH, persistencia tras reinicio, webhook PEY y conexión Android al host final.
- **Siguiente:** completar facturación en Render, crear servicio en mantenimiento
  y disco, importar el respaldo final y verificar antes de habilitar la app.
