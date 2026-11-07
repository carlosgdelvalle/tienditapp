# Abarpay · Plan de entrega

Hoy sábado 7-nov, de 14:20 a 16:00 (en el venue), y del sábado en la noche al domingo 8-nov a las 13:00 (entrega final por correo).

Regla del plan: cada punto se da por cerrado con evidencia (captura, URL o comando con su resultado), no con "ya quedó".

## Bloque 1 · Hasta las 16:00 (en el venue)

| Hora | Qué | Quién | Evidencia de cerrado |
|---|---|---|---|
| 14:20-14:35 | Kickoff de 15 min: confirmar las 3 decisiones (solo tienditas · la IA propone el carrito por dictado · demo con pago real de $0.01), el stack y los dueños de cada bloque | Toda la mesa | Lista de nombres por bloque en el chat del equipo |
| 14:35-14:50 | Probar la nueva key de pey: `GET https://api.pey.mx/transaction/api-key` con `Authorization: Bearer <key>` | Bloque A | Captura con respuesta 200 (sin mostrar la key) |
| 14:35-14:50 | Repo: primer commit solo con `.gitignore` (`.env*`, `!.env.example`) y `.env.example` sin valores | Bloque D (Carlos) | Link al commit |
| 14:50-15:20 | Dar de alta una CLABE pre-autorizada en `portal.pey.mx`, vincular la key y crear un QR de $0.01 con `POST /codi/qr` (con `metadata.saleId`) | Bloque A | `id` y `qrString` devueltos, y QR visible |
| 14:50-15:20 | Deploy vacío con URL HTTPS pública y el webhook registrado en el portal de pey apuntando a `/api/webhooks/pey` | Bloque D | URL que responde 200 y captura de la configuración del webhook |
| 14:50-15:40 | Prompt de dictado → carrito con un catálogo de 30 productos, probado con 10 frases | Bloque B | Tabla de 10 frases con el resultado de cada una (meta ≥ 9/10) |
| 15:20-15:45 | **Primer pago real:** un integrante paga $0.01 al QR desde su app bancaria. Revisar que llegue el webhook (logs de pey) y que `GET /transaction/codi/qr/{id}` muestre el pago | Bloque A + quien paga | Captura del log del webhook y de la transacción `PAID` |
| 15:30-15:55 | Llenar la tabla "Estado" de `propuesta-4pm.md` con lo que de verdad pasó y revisar el texto | Eduardo + Luis | Documento con la tabla actualizada |
| **16:00** | **Entregar la propuesta** | Eduardo + Luis | Confirmación de envío |

Si a las 15:45 no hay pago real, la propuesta lo dice tal cual en la tabla de estado. No se maquilla.

## Bloque 2 · Sábado en la noche (remoto)

| Meta | Dueño | Evidencia |
|---|---|---|
| Webhook con firma verificada, deduplicación por `webhook-id`, monto validado y venta → `paid` + inventario en una sola transacción | A | Pruebas pasando (firma inválida → 401, duplicado sin doble descuento, monto distinto queda pendiente) |
| Respaldo: si el webhook no llega en 30 s, el servidor concilia con `GET /transaction/codi/qr/{id}` | A | Prueba con el webhook apagado y venta conciliada |
| Cobro incierto: si `POST /codi/qr` no responde, la venta queda "por conciliar" y no se crea otro QR en automático | A | Prueba con timeout simulado (etiquetado como prueba) |
| Pantallas Cobrar (dictado + botones rápidos), QR (con aviso "Modo demo: se cobra $0.01") y Pagado (verde + voz) | C | Video corto en un celular real |
| Aviso en dos teléfonos (empleado y dueño) | C | Video con los dos teléfonos hablando |
| Mi tienda: total del día, por empleado, por resurtir | C | Captura con datos de ventas reales de prueba |
| Guion de 3 minutos y deck | E | Borrador compartido |

## Bloque 3 · Domingo 8-nov

| Hora | Qué | Evidencia |
|---|---|---|
| 09:00 | **Congelamiento.** No entran funciones nuevas, solo bugs | Mensaje en el chat |
| 09:00-10:30 | Ensayo del demo 3 veces de punta a punta con pagos reales de $0.01 | 3 transacciones `PAID` en pey |
| 10:30-11:00 | Grabar el video de respaldo con un pago real | Archivo de video |
| 11:00-11:45 | Verificar el repo: `git log -p \| grep -iE "whsec_\|sk-\|Bearer "` sin resultados, README con instrucciones para correrlo | Resultado del comando pegado |
| **12:00** | **Entrega final** por correo a `hola@aibuilders.lat`: nombre, integrantes, link al repo, URL del deploy, video y deck | Captura del correo enviado |
| 13:00 | Cierre oficial (una hora de colchón) | — |

## Qué se recorta si vamos tarde (en este orden)

1. Aviso en el segundo teléfono (queda solo el teléfono de quien cobra).
2. Mi tienda (queda solo el inventario actualizado en la pantalla Pagado).
3. Dictado por voz (queda el texto escrito con IA y los botones rápidos).

Lo que **no** se recorta nunca: el pago real de $0.01 y la confirmación verificada.
