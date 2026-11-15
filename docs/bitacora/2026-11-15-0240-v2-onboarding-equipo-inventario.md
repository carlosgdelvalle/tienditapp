# 2026-11-15 02:40 · v2 · onboarding, equipo e inventario

- **PR / commits:** cambios v2 de backend, Android y consola integrados en `main` (sin PR separado; tres agentes en paralelo con alcances disjuntos + integración del lead).
- **Qué cambió:** onboarding del dueño (metas, nombre, nombre/tipo del negocio y foto), equipo con invitaciones por enlace y QR con permisos por empleado (vender, fiado, inventario; reportes solo dueño), inventario por voz («coca colas de 600… 4, 5, 6… 12 piezas» → 12 pza), módulo de inventario completo en la consola (niveles, valor, última persona en actualizar), encabezado compacto e Inicio informativo. Android 1.1.0 / code 11.
- **Por qué:** petición directa del dueño; contrato en [docs/v2-contract.md](../v2-contract.md) con las decisiones confirmadas (multi-dispositivo con token, valor = precio × existencias, base nueva solo dueño, foto en consola, gate fake de reportes, redeploy Render).
- **Evidencia:**
  ```text
  /tmp/abar-venv2/bin/python -m pytest server/tests -q   → 110 passed
  ./scripts/verificar.sh                                 → VERIFICAR: OK (gitleaks sin fugas, 16 pruebas legacy)
  cd android && ./gradlew testDebugUnitTest assembleRelease → BUILD SUCCESSFUL (87 pruebas)
  dist/Abarpay-Android-1.1.0.apk                         → SHA256 f300baace8810a603a77e92d61ba8f728491c9ea78a7fac541555deeeae7f7c2, firma v2
  Smoke local v2 (puerto 8010)                           → perfil, inventario value/set, voz 12 pza, invitación crear/aceptar, reportes 403 empleado, assetlinks 200
  ```
- **Riesgos abiertos:** identidad y tokens son de demostración (sin autenticación real); la foto solo acepta JPEG ≤ 5 MB; el conteo por voz depende del reconocimiento de voz del teléfono; el filtro «stock bajo» de la consola usa el summary hasta exponer `lowStockMilli` en `/api/inventory`; Render requiere redeploy manual y el APK debe instalarse en los teléfonos.
- **Siguiente:** commit/push a `main`, redeploy Render desde `main`, instalar 1.1.0 en el Samsung y correr los flujos en el dispositivo.
