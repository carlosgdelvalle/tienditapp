# 2026-11-14 16:30 · catálogo · Soporte de existencias sin límite

- **PR / commits:** rama `cdv/tacos-pastor-sin-limite`; pendiente de publicación.
- **Qué cambió:** bandera `unlimitedStock` en API, consola y Android; migración
  aditiva de SQLite con valor falso para productos existentes. Los artículos
  ilimitados muestran «Sin límite», no alteran el saldo al vender o cancelar,
  quedan fuera de alertas bajas y rechazan ajustes manuales. Las ventas y
  cancelaciones conservan sus movimientos de auditoría.
- **Por qué:** preparar Tacos de pastor con inventario sin límite sin sustituir
  ese comportamiento por un número artificialmente alto.
- **Evidencia:**
  ```text
  python -m pytest -q server/tests
  62 passed, 1 advertencia de deprecación de Starlette/httpx.
  Incluye migración repetida de esquema anterior, efectivo, fiado y PEY SIMULADO,
  webhook duplicado, cancelación, movimientos y alertas de stock.

  :app:testReleaseUnitTest --tests mx.abarpay.mobile.DomainTest
                          --tests mx.abarpay.mobile.RepositoryTest --offline
  BUILD SUCCESSFUL; 15 + 22 pruebas, cero fallos/errores/omitidas.
  Incluye etiqueta Sin límite y compatibilidad con API anterior sin la bandera.

  ./scripts/verificar.sh
  VERIFICAR: OK; gitleaks 8.30.1 sin filtraciones en 100 commits, 16 pruebas.
  El escaneo mínimo anterior confundía el identificador dsk- de Render con
  una clave sk-; se usó gitleaks, el mismo escáner de CI, sin debilitar el gate.
  ```
- **Riesgos abiertos:** solo implementación local; Render y el APK instalado
  todavía no incluyen este cambio. Falta el precio por taco solicitado al
  usuario para agregar el producto y sus alias. No se inventó ni publicó precio.
- **Siguiente:** completar catálogo al recibir el precio, generar APK y preparar
  publicación de la rama y despliegue respetando la autorización de Git.
