# 2026-11-07 15:49 CDMX · diseño · Logo oficial en el MVP Abarpay

- **PR / commits:** [#5](https://github.com/carlosgdelvalle/tienditapp/pull/5), rama `design/abarpay-branding-mvp`.
- **Qué cambió:** el encabezado muestra el JPEG oficial desde `/branding/logo.jpeg`, servido directamente desde `assets/branding/`. Se resuelven los conflictos con el rediseño `fbe56e2` conservando sus tokens, pantallas, botón de regreso, navegación inferior y un único identificador `tienda`. El encabezado blanco y el tamaño adaptable permiten utilizar el logo original sin editarlo.
- **Por qué:** integrar la identidad oficial de la rama solicitada sobre la interfaz vigente, evitando sustituir las pantallas nuevas por la versión anterior.
- **Evidencia:**
  ```text
  ./scripts/verificar.sh -> patrones mínimos sin hallazgos; 13 passed; VERIFICAR: OK
  node --check app/static/app.js -> exit 0
  Test nuevo: portada con navegación e IDs únicos; logo JPEG idéntico al recurso oficial.
  Playwright Chromium: http://127.0.0.1:8877/, 1440x1000 y 390x844.
  Título Abarpay, contenido visible y logo cargado en ambos tamaños.
  Lupita -> inicio -> cobrar -> producto rápido -> carrito $18 -> inventario (12 productos) -> reportes.
  Sin errores/advertencias de consola ni desbordamiento horizontal.
  Capturas de inicio y carrito verificadas visualmente en ambos tamaños.
  ```
  El plugin Browser no está disponible; se reutilizó Playwright instalado y un servidor con base temporal y claves vacías. Capturas locales en `/tmp/abarpay-branding-qa/`, fuera del repositorio.
- **Riesgos abiertos:** el dictado por micrófono y el pago bancario real no forman parte de esta validación visual. No se modificó la lógica de pagos.
- **Siguiente:** comprobar la presentación en los teléfonos que se utilizarán para el pitch.
