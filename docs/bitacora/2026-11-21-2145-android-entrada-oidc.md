# 2026-11-21 21:45 · tenencia · entrada Android del dueño y OIDC configurable

- PR / commits: rama cdv/integra-tenencia · OwnerQrApprovalScreen.kt, MainActivity.kt, OwnerQrApprovalScreenTest.kt, android/app/build.gradle.kts
- Qué cambió: Entrada visible "Consola" en el encabezado (solo con configuración pública completa). El primer "Entrar" lanza OwnerAuth.beginSignIn() con progreso y reintento si el navegador vuelve sin retorno; el retorno OIDC se atiende en onCreate y onNewIntent y expone authRevision/authError para que la pantalla retome membresías, alta o escáner. BuildConfig del dueño (OWNER_API_BASE_URL, AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_AUDIENCE) configurables por -P o entorno, con callback {applicationId}://oidc/callback documentado.
- Por qué: Completar el lanzamiento de la primera corrida y el recorrido J-01/J-11 sin bloquear la demo.
- Evidencia:

      ./gradlew testDebugUnitTest --tests mx.abarpay.mobile.OwnerQrApprovalTest --tests mx.abarpay.mobile.OwnerQrApprovalScreenTest  # BUILD SUCCESSFUL

- Riesgos abiertos: prueba física B2 y OIDC real pendientes.
- Siguiente: pin del integrador y validación en dispositivo.
