# Diseño de interfaz · Abarpay

Maquetas visuales recibidas por el equipo el 7 de noviembre de 2026. Se organizan por pantallas, recorridos y sistema de diseño para facilitar su consulta durante el desarrollo y la preparación del pitch.

Las imágenes utilizan la marca **Abarpay**, con violeta, lavanda y acentos verdes. Son referencias de diseño: montos, existencias, porcentajes, folios y códigos QR son ilustrativos; la pantalla de cobro exitoso no acredita una transacción real. El alcance del MVP se consulta en la [decisión 0002](../decisiones/0002-alcance-mvp.md).

## Pantallas

Todas las imágenes de esta sección tienen 1086 × 1448 píxeles.

| Imagen | Contenido |
| --- | --- |
| [Inicio](pantallas/inicio.jpeg) | Accesos a cobro con PEY, ventas e inventario; resumen diario. |
| [Cobro con QR de PEY](pantallas/cobro-qr-pey.jpeg) | QR, importe a cobrar y opción para ingresar otro monto. |
| [Cobro exitoso](pantallas/cobro-exitoso.jpeg) | Confirmación visual, importe, folio y acciones para compartir comprobante o iniciar otro cobro. |
| [Ventas](pantallas/ventas.jpeg) | Filtros por periodo, total e historial de ventas. |
| [Inventario](pantallas/inventario.jpeg) | Búsqueda, catálogo, precios, existencias y alta de productos. |
| [Reportes](pantallas/reportes.jpeg) | Ventas del periodo, gráfica, número de ventas, ticket promedio y acceso a productos más vendidos. |
| [Ajustes](pantallas/ajustes.jpeg) | Datos de la tienda, métodos de cobro, usuarios, notificaciones y ayuda. |

## Recorridos

| Imagen | Contenido | Dimensiones |
| --- | --- | --- |
| [Cobro, inventario y reportes](flujos/cobro-inventario-reportes.jpeg) | Tres secuencias: importe → QR → confirmación; alta de producto → confirmación → inventario; selección de periodo → resultados → detalle. | 1600 × 533 |

## Sistema de diseño

| Imagen | Contenido | Dimensiones |
| --- | --- | --- |
| [Fundamentos visuales](sistema-diseno/fundamentos-visuales.jpeg) | Paleta, referencias tipográficas, escala de texto, iconos, estados, introducción inicial, autenticación y componentes. | 1600 × 533 |
| [Componentes de interfaz](sistema-diseno/componentes-interfaz.jpeg) | Botones y estados, pestañas, campos, tarjetas, listas, controles, etiquetas y avatares. | 1600 × 800 |

Estas láminas son referencias rasterizadas; no incluyen fuentes tipográficas, iconos individuales ni componentes implementados.

## Organización y procedencia

Los archivos llegaron a `assets/mockup/` con nombres de exportación de WhatsApp. Se conservaron los JPEG originales, sin recomprimir ni modificar su contenido, y se renombraron según lo que muestran.

Había **13 archivos y 10 imágenes distintas**. Las copias con sufijo `(1)` de `15.30.22`, `15.30.23` y `15.30.25` eran idénticas a sus correspondientes originales, comprobado mediante SHA-256. Cada pareja se consolidó en una imagen. Los archivos de `15.30.34` y `15.30.35` con y sin `(1)` sí contienen diseños diferentes y se conservan por separado.

La ubicación `docs/diseno/` reúne material de referencia del producto. Los recursos de marca están en [`assets/branding/`](../../assets/branding/), las láminas del pitch en [`presentacion/`](../../presentacion/README.md) y la interfaz ejecutable en [`app/static/`](../../app/static/).
