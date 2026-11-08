# 2026-11-07 19:33 · diseño · copia del logo en alta resolución

- **PR / commits:** rama `assets/logo-alta-resolucion`; commit que agrega esta entrada.
- **Qué cambió:** se agrega `logo-alta-resolucion.png` en la raíz del repositorio. Es un PNG RGB de 6400 × 2132 píxeles y 3,332,240 bytes. No cambia la app ni sustituye el logo existente.
- **Por qué:** Carlos pidió una copia del logo principal en muy alta resolución, en la raíz del repo, con una URL para acceder a ella.
- **Evidencia:**
  ```text
  Pillow: Image.open(...).verify()
  PNG válido, 6400 × 2132, RGB.

  git hash-object logo-alta-resolucion.png
  668b1b857cbe678d0554f04779ac4c3539b8c7a6

  ./scripts/verificar.sh (entorno aislado con app/requirements.txt)
  Secretos: sin hallazgos con patrones mínimos; gitleaks no está instalado.
  Pruebas: 16 passed.
  VERIFICAR: OK
  ```
- **Riesgos abiertos:** el escaneo local de secretos no sustituye el escaneo completo de gitleaks en CI. La publicación en esta rama no modifica `main`.
- **Siguiente:** revisar el PR e integrar en `main` cuando se autorice.
