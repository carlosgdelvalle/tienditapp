# 2026-11-15 12:50 · v3.1/v3.2 · imágenes de producto, pagos de fiado y splash

- **PR / commits:** backend, consola y Android integrados en `main` (agentes flash en paralelo + integración del lead).
- **Qué cambió:**
  - v3.1 imágenes: `products.image_url` (migración idempotente), `imageUrl` en CRUD (https ≤ 500, 400 en español), plantilla tiendita con 26 URLs de Open Food Facts (degradación sin resources/), Coil 2.7.0 en la app (caché, placeholder/fallback emoji) y miniaturas de 48 px en la consola con sanitización.
  - v3.2 fiado: historial de entries por cliente (GET /api/fiado/customers/{id}/entries y GET /api/console/fiado/{id}), gate canFiado en abonos (403), «Liquidar saldo» y presets $50/$100 + historial en la app, fila expandible con Abonar/Liquidar/Historial en la consola, y fiadoCollectedCents en reportes/resumen.
  - Splash: video solo en el primer arranque tras instalar (Media3, mudo, tocar para saltar, máx. 5 s) e imagen de marca en cada arranque en frío; Theme.SplashScreen de Android 12 con logo y fondo de marca. Android 1.2.3 / code 15.
- **Por qué:** peticiones del dueño (fotos de productos, pagos de fiado visibles en app y consola, splash con video/intro).
- **Evidencia:**
  ```text
  /tmp/abar-venv2/bin/python -m pytest server/tests -q   → 183 passed
  ./scripts/verificar.sh                                 → VERIFICAR: OK (gitleaks sin fugas, 16 pruebas legacy)
  cd android && ./gradlew testDebugUnitTest assembleRelease → BUILD SUCCESSFUL (154 pruebas)
  dist/Abarpay-Android-1.2.3.apk                         → SHA256 35ab8c4174e3e5b53dbf7534c3cf3649e41e650859d6afae2cb144dd5add05d5, firma v2
  ```
- **Riesgos abiertos:** el video/intro se validan por código (no hay reproducción automática en Robolectric); las fotos OFF requieren red y pueden tardar en celular; la consola usa abonos con X-Employee-Id: 1 (dueño).
- **Siguiente:** redeploy Render, instalar 1.2.3 en el Samsung y probar video→imagen, abono/liquidación e imágenes.
