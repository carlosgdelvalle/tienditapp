# 2026-11-14 15:08 · despliegue · Backend y base migrados a Render

- **PR / commits:** rama `cdv/despliegue-render`; sin push ni merge.
- **Qué cambió:** servicio Python `abarpay-api` con URL HTTPS estable y disco
  persistente de 1 GB. Se migró la base local completa; Android 1.0.5 apunta a
  Render. `render.yaml` y la guía reflejan los recursos creados directamente.
- **Por qué:** conservar la demo, sus productos y operaciones sin depender de
  la conexión del portátil ni de direcciones temporales de Cloudflare.
- **Recursos:** workspace `tea-d8s3sf36sc1c73c0q6m0`, servicio
  `srv-dbsccfdg1s2s73eplcu0`, disco `dsk-dbscd3on74is739fkcp0` en `/var/data`,
  plan `0.5c-512mb`, Oregon, una instancia y un worker. Despliegues automáticos
  desactivados. Backend publicado desde `main`, SHA
  `f0ada025b3d8f3c1c92b601db6288261ae0106d0`.
- **Evidencia:**
  ```text
  render blueprints validate render.yaml --output json
  valid: true.

  Snapshot final por Connection.backup, con backend local detenido limpiamente
  SHA256: 42777649e3576032df9b706747a14f29ec3e935c033fabbb9b8f15a0a08b875f
  integrity_check: ok; foreign_key_check: sin errores.
  17 productos, 10 códigos, 11 ventas, 15 partidas, 8 pagos,
  26 movimientos, 2 clientes de fiado y 3 apuntes de fiado.

  Transferencia SFTP a disco montado y renombrado con servicio en mantenimiento
  Hash del archivo, esquema y SHA del contenido de cada tabla: idénticos.

  Deploy dep-dbscisqfngtc73cbnjq0
  live; /api/health, /api/bootstrap, /console y /api/reports/today HTTP 200.
  Consulta de ventas de consola con PIN existente: HTTP 200.

  Reinicio del servicio; instancia 6qrxd reemplazada por kttr9
  Esquema y datos de todas las tablas idénticos al snapshot después del reinicio.
  integrity_check y foreign_key_check correctos; secretos presentes sin imprimir.

  Android :app:assembleRelease --offline
  BUILD SUCCESSFUL; lint vital aprobado; firma APK válida.
  Package mx.abarpay.mobile, versionCode 8, versionName 1.0.5.
  DEX contiene https://abarpay-api.onrender.com y no el túnel anterior.
  APK SHA256: 63e0b00b41708092f7738a78c6581980414cba1b6b0de3bf87abf6c5f8fd08f2

  PEY → Test2 → Configuración, después de recargar
  URL del Webhook: https://abarpay-api.onrender.com/webhooks/pey.
  Secreto renovado por el usuario, guardado con entrada oculta y sincronizado
  por API al entorno de Render; readback coincide, sin mostrar valores.

  Deploy final dep-dbscr9c9v7es73cbksdg para cargar el secreto definitivo
  live; salud, catálogo (17), consola, reportes y ventas con PIN (11): HTTP 200.
  POST sin firma a /webhooks/pey: HTTP 401, rechazado sin registrar operaciones.

  Render Account settings → SSH Public Keys
  No authorized SSH keys. SSH posterior: Permission denied (publickey).
  ```
- **Validación previa conservada:** `./scripts/verificar.sh`: 16 pruebas y
  escaneo mínimo sin hallazgos; `server/tests`: 57 pruebas con FakePey SIMULADO.
  No se modificó la lógica del backend ni se repitieron esas suites durante el
  corte. Las verificaciones nuevas fueron configuración, importación, HTTP,
  persistencia y build de Android.
- **Riesgos abiertos:** autenticación de demo; no entrega real de webhook ni
  pago nuevo probado después del corte. APK generado en `dist/` ignorado; no
  instalado porque no había dispositivo conectado. Con disco hay una breve
  interrupción durante despliegues.
- **Siguiente:** instalar el APK 1.0.5 en los teléfonos que usaban el túnel y
  realizar, si se requiere, una prueba humana de pago real de $0.01 MXN.
