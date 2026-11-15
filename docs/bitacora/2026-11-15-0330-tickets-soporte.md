# 2026-11-15 03:30 · tickets · cobros no confirmados dejan de ser alarma

- **PR / commits:** cambios de backend, consola y Android integrados en `main` (tres agentes en paralelo con alcances disjuntos + integración del lead).
- **Qué cambió:** los cobros PEY pendientes/por conciliar dejan de ser una tarjeta de alarma en el teléfono. La app muestra «Cobrado hoy» en su lugar y, solo en una venta PEY `por_conciliar`, ofrece «Reportar problema» → crea un ticket en la base propia (`support_tickets`). La consola lista los tickets (abrir/resolver) y añade el rastro «Eventos PEY» con ventas de cualquier estado. Expired/canceled siguen como estados normales.
- **Por qué:** decisión del dueño: sin marca verde el cliente no recibe el producto; la acción realista es dejar un ticket para que Abarpay rastree el caso, no resolverlo desde el teléfono.
- **Evidencia:**
  ```text
  /tmp/abar-venv2/bin/python -m pytest server/tests -q   → 118 passed
  ./scripts/verificar.sh                                 → VERIFICAR: OK (gitleaks sin fugas, 16 pruebas legacy)
  cd android && ./gradlew testDebugUnitTest assembleRelease → BUILD SUCCESSFUL (96 pruebas)
  dist/Abarpay-Android-1.1.0.apk                         → SHA256 04bff35e2144c46697979fde518d4d9de283f705bafe1899428ea965522c2ffe, firma v2
  ```
- **Riesgos abiertos:** un ticket general (sin venta) no persiste quién lo reportó (el listado lo deriva del vendedor de la venta); se documentó en el contrato. La prueba en dispositivo cubrió la tarjeta «Cobrado hoy»; el botón «Reportar problema» está cubierto por Robolectric.
- **Siguiente:** redeploy Render desde `main`, reinstalar el APK y verificar las dos secciones nuevas de la consola.
