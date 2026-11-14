# 2026-11-14 17:25 · despliegue · Tacos de pastor publicados

- **Autorización:** Carlos aprobó el push de la rama, el despliegue en Render
  y la instalación del APK nuevo.
- **Código:** `cdv/tacos-pastor-sin-limite`, revisión de aplicación
  `3d17b13dd39e8a8d33808601e7ec3f60e357d2ae`. Sin merge a `main`.
- **Despliegue:** `dep-dbseq33bc2fs73bcbekg`, estado `live`, en el servicio
  existente `abarpay-api`, con el mismo disco y base persistentes.
- **Respaldo:** antes de cargar la aplicación se generó mediante SQLite backup
  API `/var/data/backups/before-pastor-3d17b13.db`; integridad verificada en el
  log del servidor. El comando normal de Uvicorn quedó restaurado para futuros
  despliegues, sin reiniciar otra vez.
- **Verificación pública:**
  - Salud correcta; catálogo de 18 productos.
  - Producto 18 «Tacos de pastor»: `priceCents=2000`, `unlimitedStock=true`.
  - Los 17 productos anteriores conservan todos sus campos y stock limitado.
  - Las 14 ventas previas y los datos de fiado son idénticos a la lectura antes
    de desplegar.
  - «dos de pastor» y «2 tacos de pastor»: 2 piezas, total de 4000 centavos.
  - El producto ilimitado no aparece en alertas de stock bajo.
- **Android:** APK firmado 1.0.6 / código 9 instalado con `adb install -r` en
  Samsung SM-A165M (`Success`). Hash de entrega verificado contra el build:
  `eb06c6a969a6b90788335fefa230be108d9f5c305c96677866aa5627e3b3fdd7`.
- **Límites:** las consultas de comprobación no crearon ventas ni pagos reales.
  Las reglas de efectivo, fiado, PEY SIMULADO y cancelaciones sin consumir stock
  se validaron previamente en pruebas aisladas, no con ventas artificiales sobre
  la base activa.
