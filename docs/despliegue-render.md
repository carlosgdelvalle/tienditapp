# Backend de Abarpay en Render

Configuración para la demo: `server/` (FastAPI), una instancia Python y SQLite
en un disco persistente. Android consume la URL HTTPS pública; `/console` sirve
la consola del dueño. Se conserva el modelo de acceso de demostración descrito
en [la decisión 0005](decisiones/0005-v1-android-backend-consola.md).

## Instancia desplegada · 14-nov-2026

- API: <https://abarpay-api.onrender.com>
- Consola: <https://abarpay-api.onrender.com/console>
- [Servicio en Render](https://dashboard.render.com/web/srv-dbsccfdg1s2s73eplcu0).
- Workspace autorizado: `tea-d8s3sf36sc1c73c0q6m0`.
- Código del despliegue inicial desde `main`: `f0ada025b3d8f3c1c92b601db6288261ae0106d0`.

La instancia se creó directamente con MCP, Dashboard y API; no está gestionada
por un Blueprint. `render.yaml` representa su configuración final de referencia.
Actualizarlo si se cambian ajustes manualmente. Aplicarlo como un Blueprint nuevo
puede crear otro servicio: no hacerlo sin revisar el plan y la base que utilizará.

Se importó la base local con los 17 productos, 11 ventas, 8 pagos y el historial
de fiado e inventario. Se comprobó la igualdad del esquema y del contenido de
todas las tablas antes del arranque y después de un reinicio de la instancia.
El backend y el túnel locales quedaron detenidos; la base original se conserva
para recuperación. El APK 1.0.6 apunta a Render y admite inventario sin límite; requiere instalar esa versión
en los teléfonos que todavía tienen la dirección del túnel.

El webhook de la clave activa en PEY apunta a
`https://abarpay-api.onrender.com/webhooks/pey`. Su secreto de firma se renovó
durante el cambio de URL y se sincronizó al entorno de Render. La clave SSH usada
temporalmente para la transferencia se retiró al terminar la verificación.
La configuración del callback no sustituye una prueba de entrega real: no se
generaron cobros ni pagos durante la migración.

## Actualización de catálogo · 14-nov-2026

La rama `cdv/tacos-pastor-sin-limite` incorpora Tacos de pastor a $20.00 MXN por
pieza y el indicador de stock sin límite. La actualización agrega el producto
una vez a la base existente. El dictado «dos de pastor» produce dos piezas por
$40.00. Los demás productos conservan su seguimiento de existencias.

## Integración a main · 15-nov-2026

`main` integra Android **1.0.7 / code 10** con la **cancelación de cobros PEY
pendientes** (`pendingOnly=true`: concilia con PEY y rechaza con 409 si el pago
ya llegó; no revoca el QR bancario ni reembolsa). El servicio Render sigue en el
despliegue de la rama de tacos hasta un **redeploy manual** desde `main`;
`autoDeploy` permanece apagado y `render.yaml` ya apunta a `main` como referencia.
El APK instalado en el SM-A165M es 1.0.6; el release 1.0.7 está en `dist/`.

## Recursos

| Ajuste | Valor |
| --- | --- |
| Servicio | `abarpay-api`, Web Service, Python |
| Región | Oregon |
| Instancia | `0.5c-512mb`, una instancia, un worker |
| Disco | `disk`, 1 GB, montaje `/var/data` |
| Base | `ABARPAY_DB=/var/data/abarpay.db` |
| Build, desde la raíz del repo | `pip install -r server/requirements.txt` |
| Arranque | El comando de `render.yaml`; verifica que exista la base antes de arrancar Uvicorn |
| Salud | `/api/health` |
| Despliegues automáticos | Desactivados |

`render.yaml` documenta la configuración final. **No aplicarlo sobre un disco
vacío:** el arranque exige la base importada para evitar crear otro catálogo.
El archivo no incluye credenciales ni la base. La referencia de precio al
14-nov-2026 es USD 7/mes de cómputo + USD 0.25/mes por 1 GB, antes de impuestos
y consumos adicionales. Confirmar el importe en Render al contratar.

## Entorno

Mantener `MODO_DEMO=true` y `PEY_DEMO_CHARGE_CENTS=1`: los cobros de PEY son
dinero real, de **$0.01 MXN**, y los realiza una persona desde su banco.
Configurar `OWNER_PIN`, `PEY_API_KEY` y `PEY_WEBHOOK_SECRET` en el entorno del
servicio, sin pegarlos en chats, comandos, commits ni logs. El `.env` local no se
carga en Render (`ABARPAY_LOAD_DOTENV=0`).

## Primera migración

1. Crear el servicio temporalmente en mantenimiento: sin rutas de negocio,
   solo un servidor HTTP mínimo para comprobar conectividad y abrir SSH.
2. Adjuntar el disco de 1 GB en `/var/data` y comprobar el montaje por SSH.
   El disco está disponible en ejecución, no durante build o pre-deploy.
3. Preparar el canal SSH autorizado y el entorno del servidor.
4. Pausar el backend local durante el corte para que no haya dos escritores
   independientes. No borrar la base local ni cancelar ventas para migrar.
5. Crear el respaldo final con `sqlite3.Connection.backup`, incluyendo así
   las transacciones confirmadas que estén en WAL. No copiar solamente el
   archivo `.db` activo. Guardar el respaldo bajo `.local/backups/` (ignorado).
6. Comprobar `PRAGMA integrity_check` y `PRAGMA foreign_key_check`. Registrar
   SHA-256 y cantidades por tabla sin mostrar filas ni datos personales.
7. Transferir por SFTP/SSH al disco como `abarpay.db.incoming`. Comprobar el
   hash del archivo recibido y validar todas las tablas contra el respaldo.
8. Con el servicio aún en mantenimiento y sin conexiones SQLite abiertas,
   renombrar el archivo validado a `/var/data/abarpay.db`.
9. Aplicar el comando final de arranque y `/api/health` como health check.
   Desplegar manualmente; comprobar catálogo, consola y configuración PEY.
10. Reiniciar una vez el servicio y volver a comprobar que permanecen las
    ventas, pagos, productos y movimientos. No generar pagos de prueba
    automáticamente.
11. Configurar el webhook de PEY a `https://<servicio>.onrender.com/webhooks/pey`
    y el servidor del APK a la nueva URL pública. Verificar cada cambio por
    separado; un GET de salud no prueba la entrega de un webhook real.

## Respaldos y reversión

- Usar la API de backup de SQLite para respaldos consistentes. Descargar
  periódicamente una copia fuera del disco del servicio.
- No sustituir una base abierta ni restaurar a ciegas un snapshot del disco.
- Si falla el corte **antes de aceptar escrituras en Render**, conservarlo en
  mantenimiento y restablecer el backend local con su base original.
- Si Render ya recibió ventas o pagos, respaldarlo primero y conciliar esas
  operaciones antes de volver al backend local. No restaurar un respaldo
  anterior sobre transacciones nuevas.
- Solo los archivos bajo `/var/data` sobreviven a reinicios y despliegues.
  El disco limita el servicio a una instancia; los despliegues tienen una breve
  interrupción. Es suficiente para esta demo.

## Fuentes

- [FastAPI en Render](https://render.com/docs/deploy-fastapi)
- [Discos persistentes y transferencia por SSH](https://render.com/docs/disks)
- [Acceso SSH](https://render.com/docs/ssh)
- [Referencia de Blueprints](https://render.com/docs/blueprint-spec)
- [Precios](https://render.com/pricing)
