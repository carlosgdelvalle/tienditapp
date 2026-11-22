# 2026-11-22 13:40 · Android · Cobrar directo y borrador del carrito

- Rama / commits: `main` · `android/app/src/main/java/mx/abarpay/mobile/MainActivity.kt`, `HomeScreens.kt`, `ShopViewModel.kt`, pruebas `AppUiTest.kt` y `CartDraftPersistenceTest.kt`.
- Qué cambió: **Cobrar ahora** en Inicio y la pestaña **Cobrar** vuelven a abrir la vista Cobrar directamente. Se elimina el selector intermedio que introdujo `fef90d3`. La caja vinculada conserva su entrada propia en **Inicio → Herramientas → Caja en efectivo de la tienda**. El carrito de Cobrar se guarda en `development_session` (`cart_draft_v1`) al agregar, quitar o dictar productos, se restaura al reabrir el proceso y se borra al iniciar otro cobro o dejar el carrito vacío.
- Por qué: el selector añadía un paso a un flujo que ya funcionaba y obligaba a elegir entre dos cajas antes de ver el catálogo. Carlos lo reportó como regresión.
- Evidencia:

      ./gradlew testDebugUnitTest                 # 178 pruebas
      ./gradlew assembleRelease                   # APK firmado
      ./gradlew assembleDebug -PABARPAY_DEVICE_TEST=true && adb install -r ...

- Riesgos abiertos: la prueba física en el Samsung queda pendiente porque el teléfono está bloqueado con PIN. El borrador del carrito no reconcilia productos eliminados del catálogo; se conservan y el total los ignora.
