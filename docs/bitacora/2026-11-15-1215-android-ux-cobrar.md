# 2026-11-15 12:15 · android · UX de Cobrar

- **PR / commits:** cambio solo de Android integrado en `main` (agente flash android-cobrar-ux + integración del lead).
- **Qué cambió:** en Cobrar, feedback al agregar/quitar (vibración, tono, píldora animada, fila con acento y aviso «Deshacer» 4 s); carrito movido a una hoja inferior abierta desde la barra fija (conteo + total + «Ver carrito» + «Cobrar»); filas escaneables con emoji por categoría, precio a la derecha y stepper con píldora; chips de categoría y secciones stickyHeader con «Rápidos» primero. Versión 1.2.1 / code 13.
- **Por qué:** el dueño reportó que no quedaba claro cuándo se agrega un producto ni cuántos hay en el carrito, y que las filas del catálogo se veían todas iguales.
- **Evidencia:**
  ```text
  cd android && ./gradlew testDebugUnitTest assembleRelease → BUILD SUCCESSFUL (133 pruebas, 33 clases)
  dist/Abarpay-Android-1.2.1.apk → SHA256 032b525a730e7176d7c9c624571f796aab126c120d7b3f9bbedf38716c84ea7a, firma v2
  ```
- **Riesgos abiertos:** emoji por coincidencia de categoría (categorías nuevas caen a 📦); sonido/háptica dependen del dispositivo; resta probar en el Samsung real.
- **Siguiente:** instalar en el Samsung y verificar el flujo a mano.
