# Abarpay · Benchmark de la app colombiana (Treinta)

> **Estado:** lectura de solo lectura de `Benchmarking/`, 15-nov-2026. Documento de trabajo para el equipo; no es una decisión. Las decisiones viven en `docs/decisiones/`.
> **Qué se hizo:** se abrieron las 13 imágenes con la herramienta de lectura de imagen (no se ejecutó la app ni se navegó su sitio). Todo lo que sigue sale de lo visible en los archivos; cuando algo se infiere, se marca como **inferencia**.

## 0. Ficha de la evidencia

- Carpeta: `Benchmarking/` — **13 archivos**: 11 capturas grandes (`1206×2622`, PNG con contenido JPEG) y 2 miniaturas (`281×612`, JPEG).
- Todas las grandes traen la píldora **LIVE** y `5G` en la barra de estado, y horas 11:56–11:59. **Inferencia fuerte:** son cuadros de una grabación de pantalla de una demostración en vivo, no capturas limpias del App Store. Eso explica el blur del fondo y los cortes a media pantalla.
- El comprobante de `DC03293E` fecha **14 de noviembre**: coincide con la sesión de captura.
- App identificada: **Treinta** (la propia app se nombra en `7B1837AC` — "¿Qué te gustaría lograr con **Treinta**?" — y en `30175AD7` — "conoce **Treinta** con más detalle"). Es la referencia colombiana de gestión para pequeños negocios. El build capturado, sin embargo, ofrece **SPEI** como método de pago (`D9D6CC98`), riel mexicano: **inferencia** de que es Treinta México o un demo localizado a MX. Importa: no copiar rieles colombianos, el benchmark es de producto, no de pagos.
- Precios en `$` **sin moneda explícita** (`7E8B9F86`, `30175AD7`, recibos). No usar esas cifras en láminas del pitch.
- Leyenda de citas: cada código es el **prefijo único** del nombre del archivo en `Benchmarking/`; el nombre completo está en la tabla de §1.

**Ninguna imagen es ilegible ni ajena a la app.** Las dos miniaturas (`D90EB492`, `DC03293E`) son pequeñas: se leen los textos principales y los importes, pero el fondo está desenfocado a propósito.

## 1. Inventario de pantallas observadas

| Código | Archivo | Pantalla | Qué se ve | Valor para Abarpay |
|---|---|---|---|---|
| A1 | `30175AD7-B4EB-4121-A738-92A56A552976.png` | Paywall · comparativa de planes | "Conoce las diferencias entre planes": columnas **BÁSICO** (✗) y **PRO** (✓, corona). PRO incluye: sitio web con IA, mejora de fotos con IA, lectura de facturas con IA, uso desde computadora, facturación electrónica. En ambos planes: registro de ventas y gastos, comprobantes, registro de inventario, tienda virtual sencilla, cotizaciones ilimitadas. CTA "Comprar ahora" | Cómo empaquetar gratis vs Pro; lista de funciones que un negocio chico espera |
| A2 | `3E1205B3-7E38-4EDB-B89B-4DF864BD1DDA.png` | Onboarding · catálogo de giros (continuación) | Artículos deportivos · Agricultura y ganadería · Productos de aseo y limpieza · Vape, tabaquería y smoke shop · **Venta por catálogo** · Juguetería | Ver §2.4: la lista mezcla giro con canal |
| A3 | `77EF564B-7E49-44E5-AC7C-5A4D4B893FA5.png` | Onboarding · "¿Cuál es la categoría de tu negocio?" | Buscador "Busca por categoría" + tarjetas de 2 columnas con emoji, título y una línea de descripción: Ropa y calzado · Artículos de belleza · Tiendas de regalos · Accesorios y bisutería | Patrón de selección de giro reutilizable y baratísimo de implementar |
| A4 | `7B1837AC-6D11-4460-B7B8-B4AC675C17A5.png` | Onboarding · metas del dueño | Barra de progreso (~50 %) + "Omitir" + selección múltiple: Organizar mis ventas y gastos · **Controlar lo que me deben** · Vender online sin depender de apps de terceros · Gestionar mejor mi inventario · Ver estadísticas avanzadas | Convierte el onboarding en configuración del producto; "lo que me deben" es la forma neutral de decir fiado |
| A5 | `7E8B9F86-E415-44E0-83B8-25B534DDA62E.png` | Onboarding · resultado + oferta | "¡Listo! Estas son las funciones para ti" con 3 tarjetas: **Tickets y comandas**, Ventas y gastos, Inventario. Abajo: "¡Te activamos 80% dto!" con contador 2d 23h 57m 40s; Plan Básico vs **Pro con IA**; Mensual $79.80 (tachado $399) / Trimestral $239.78 (tachado $1,198.90, "Recomendado") | Las 3 funciones resumen el producto; el contador es growth, no producto |
| A6 | `93B225C3-5378-4057-ACE2-E48C6B2ECE6E.png` | Onboarding · catálogo de giros | Heladería, jugos y postres · Variedades y bazares · Artesanías y manualidades · Floristería y vivero · Agua, hielo y gas · Artículos religiosos y esotéricos | — |
| A7 | `AA76430D-A963-472C-A0E3-2D676FB6F6C1.png` | Onboarding · catálogo de giros | Entretenimiento y ocio · **Cafetería** · Licorería · **Bar** · **Restaurante o comida rápida** · Tienda naturista y/o suplementos | Los giros de comida existen pero **sin** flujo de comanda visible |
| A8 | `B808B64D-C121-4BED-AEE0-B842914CF94B.png` | Onboarding · catálogo de giros | Tienda de mascotas · Ferretería y construcción · Artículos para el hogar · **Industria o manufactura** · Insumos agropecuarios · **Panadería y Repostería** | — |
| A9 | `D8153C70-099A-4FD8-AF5C-65FB332E93E7.png` | Onboarding · **"¿Qué vende tu negocio?"** | Selección múltiple: **Productos** ("cualquier tipo de artículo físico") · **Servicios** ("soluciones, atención o asesorías personalizadas") · **Comida preparada y bebidas** ("restaurantes, panaderías, cafés, bares"). Copy: "Adaptaremos Treinta a tu negocio" | **La pantalla más valiosa del set**: segmenta producto por naturaleza de la oferta, no por industria |
| A10 | `D9A0CEB0-9431-444A-B27C-59F82703AD19.png` | Onboarding · catálogo de giros | Tienda de abarrotes · **Minimercado** · **Distribuidora / Mayorista** · Salchichonería · **Carnicería** · Electrónica e informática | — |
| A11 | `D9D6CC98-0105-4A7C-9E9A-7FB109C3024B.png` | Primera venta guiada | "**Paso 2 de 3**" · "¡Listo! creaste un producto, ahora registra tu primera venta". Tarjeta: Kitkat, **"9 disponibles"**, $20, stepper − 1 +. "Selecciona el método de pago*": **Efectivo · Tarjeta · Transferencia bancaria · Otro · SPEI**. CTA fijo abajo: "**1 Crear venta · $20 · ›**". Header: avatar, "**Tiendita de Carlos** ⌄", ayuda (?) y campana | Onboarding que termina en una venta real; CTA que muestra cantidad y total |
| A12 | `D90EB492-13C4-43D1-8CCE-66DBA77DE452_4_5005_c.jpeg` | Confirmación post-venta | Hoja inferior: "**¡Bien hecho!** Se registró tu primera venta y **tu inventario fue actualizado**". Kitkat $20 · **"9 unidades"**. "Ahora descarga y comparte el comprobante con tu cliente." Botones: "Descargar comprobante" / "Crear mi primer gasto". Fondo: panel "Tu negocio hoy" con cifras (una en verde, una en rojo; **borroso**) | Enseña qué cambió en el negocio, no solo "listo" |
| A13 | `DC03293E-6F94-4081-A7EF-D1E20CA8CF79_4_5005_c.jpeg` | Vista previa de comprobante | "Así se verá tu comprobante — Compártelo con tu cliente en segundos." Encabezado con **nombre del negocio, dirección, teléfono, correo**; campos Fecha 14 de noviembre 11:59, Vendedor, **Estado: Pagado**, **N° Transacción: 1**; tabla Productos / Cant. / Precio Unit. / Valor; Kitkat 1 $20 $20; Total $20. Acciones: "Compartir como imagen" / "Compartir como PDF" | Comprobante como objeto compartible: sirve al cliente y al dueño ausente |

### Lo que **no** aparece en las 13 capturas

Importante para no sobreinterpretar (y para pedir más evidencia, §4):

- **Inventario operativo**: no hay pantalla de lista de productos/existencias, ni de alta de producto, ni de conteo. Solo la palabra "Inventario" como tarjeta y la frase "tu inventario fue actualizado" (`A5`, `A12`).
- **Empleados / permisos / turnos**: cero pantallas.
- **Citas / agenda / disponibilidad de servicios**: cero pantallas (aunque el negocio objetivo del pedido sea peluquería/barbería).
- **Propinas**: cero menciones.
- **Caja / corte de caja / arqueo**: cero pantallas (solo el método "Efectivo").
- **Catálogo de servicios con precio y duración**: cero pantallas. "Servicios" solo existe como opción de onboarding (`A9`) y como "cotizaciones ilimitadas" en el plan (`A1`).
- **Reportes / estadísticas**: solo como meta elegible "Ver estadísticas avanzadas" (`A4`) y un panel "Tu negocio hoy" desenfocado (`A12`).
- **Clientes / fiado**: solo como meta "Controlar lo que me deben" (`A4`).
- **Home completo**: nunca se ve sin blur. **Inferencia:** el flujo demostrado es solo el "primer uso" (onboarding → primera venta → comprobante).

## 2. Conceptos y nomenclatura

### 2.1 Cómo nombra Treinta lo que en Abarpay hoy es "tiendita"

| Concepto Abarpay hoy (dónde vive) | Cómo lo dice Treinta | Evidencia | Comentario |
|---|---|---|---|
| "Tiendita de la Esquina" / `STORE_NAME` / "Activo en la tienda" | **"negocio"** como categoría; el nombre es un dato del usuario ("Tiendita de Carlos") y el panel es **"Tu negocio hoy"** | `A12`, `A11`, `A13`; copy "Inteligencia Artificial en **tu negocio**" en `A1`; "Adaptaremos Treinta a **tu negocio**" en `A9` | Treinta usa "tiendita" solo porque el usuario la llamó así. Abarpay podría hacer lo mismo: el genérico es "negocio", el nombre es del dueño |
| "producto" / catálogo con `productId` | **"Producto"** sigue existiendo, pero es **una de tres naturalezas** de lo que vende el negocio: *Productos · Servicios · Comida preparada y bebidas* | `A9`, `A11` ("creaste un producto"), `A1` ("Registro de inventario") | No renombra el producto: lo especializa. Servicios y comida dejan de ser "productos raros" y pasan a ser tipos de oferta |
| "stock" / `stock_milli` / "existencias" / "inventario" | **"Inventario"** (módulo) · **"disponibles"** (badge de la tarjeta) · **"unidades"** (confirmación y comprobante) | `A5` (tarjeta Inventario), `A1` ("Registro de inventario"), `A11` ("9 disponibles"), `A12` ("9 unidades"), `A13` ("Cant.") | Tres palabras para tres cosas: módulo, disponibilidad y cantidad vendida. La jerga técnica nunca se muestra |
| "unidad" = `pieza` / `kg` (seed de `server/db.py`) | No hay selector de unidad visible; el recibo dice **"Cant."** | `A13` | Treinta evita el problema de las unidades; Abarpay ya lo resolvió con `pieza`/`kg`. Ojo: tortillería y comida corrida necesitan kg/pieza y Treinta no lo muestra |
| "fiado" / "cliente del fiado" / `can_fiado` | **"Controlar lo que me deben"** — sin la palabra "fiado" | `A4` | Nomenclatura neutral y orientada al dueño. "Fiado" es correcto en tiendita; en barbería suena raro |
| "cobrar" / "cobro" (verbos de la app Android) | **"registrar / crear venta"** y "método de pago" como atributo de la venta | `A11` ("Crear venta", "Selecciona el método de pago*"), `A4` ("Organizar mis ventas") | Abarpay nace pago-primero ("cobrar"); el negocio general piensa venta-primero. No hay que cambiar el flujo, pero sí el sustantivo de la pantalla |
| "ticket" / "folio" / `ticketCode` | **"Comprobante"**, y el folio se llama **"N° Transacción"**; el estado se dice **"Pagado"** | `A12` ("Descargar comprobante"), `A13` | Mismo objeto, nombre más de negocio que de sistema |
| — (no existe) | **"Gastos"**: "Ventas y gastos", "Crear mi primer gasto" | `A4`, `A5`, `A1`, `A12` | Abarpay solo registra ingresos; Treinta asume egresos desde el día 1 |
| — (no existe) | **"Cotizaciones"** (ilimitadas, incluidas en Básico) | `A1` | Puente natural hacia servicios: cotizar antes de cobrar |
| — (no existe) | **"Tienda virtual sencilla"** y "Vender online sin depender de apps de terceros" | `A1`, `A4` | Fuera del alcance del MVP de Abarpay, pero es el gancho "dueño ausente" |
| — (no existe) | **"Facturación electrónica"** (solo PRO) | `A1` | No aplica: Abarpay no toca datos fiscales |
| Métodos: efectivo / PEY (CoDi) / fiado | **Efectivo · Tarjeta · Transferencia bancaria · Otro · SPEI** | `A11` | Treinta registra la transferencia sin verificarla; Abarpay solo marca pagada con `apply_payment` (regla dura 3). Conflicto a resolver, ver §4 |
| "Tiendita…" en planes | **"Básico" vs "PRO"**, "Pro con IA", "Recomendado" | `A1`, `A5` | Coincide con el "Plan Pro para el tendero" que ya está en `docs/modelo-de-negocio.md` §6 |

### 2.2 Convenciones de copy que sí valen

- **Segunda persona, cero tecnicismos, celebración corta:** "¡Listo!", "¡Bien hecho!", "Puedes ajustar la cantidad que necesites". Mismo tono que ya usa Abarpay ("Bienvenido a Abarpay", "Cobro en efectivo registrado"); no hay que inventar tono nuevo.
- **Numerar el onboarding**: "Paso 2 de 3" + barra de progreso + "Omitir" (`A4`, `A11`). El usuario siempre sabe cuánto falta y puede saltarse.
- **El botón dice lo que va a pasar y cuánto cuesta**: "1 Crear venta · $20" (`A11`). No es un "Continuar" genérico.
- **La confirmación dice qué cambió**: "tu inventario fue actualizado" + la nueva cantidad (`A12`).
- **Nada de jerga de inventario**: nunca aparece "stock", "SKU", "existencia", "merma".
- **El comprobante es una vista previa, no un PDF a ciegas**: "Así se verá tu comprobante" (`A13`).

### 2.3 Secuencia de onboarding observada

`A3` categoría del negocio (buscador + grid) → `A9` ¿qué vende? (Productos/Servicios/Comida) → `A4` ¿qué quieres lograr? (metas, multi-select, "Omitir") → `A5` resumen de funciones + **paywall** → `A11` crear producto y **primera venta** → `A12` confirmación + comprobante.

**Observación incómoda pero útil:** el paywall aparece **antes** de la primera venta (`A5`), y el descuento con contador (`2d 23h 57m 40s`) es presión comercial. Para el demo de Abarpay eso sería contraproducente (regla dura 6: lo simulado se etiqueta; nada de urgencia falsa). El *orden* sí sirve: giro → oferta → metas → valor → primera venta → comprobante.

### 2.4 El catálogo de giros: cuántos y cómo

En las 6 capturas de grid se ven **34 giros** (más tarjetas cortadas): Ropa y calzado, Artículos de belleza, Tiendas de regalos, Accesorios y bisutería, Artículos deportivos, Agricultura y ganadería, Productos de aseo y limpieza, Vape/tabaquería/smoke shop, Venta por catálogo, Juguetería, Heladería/jugos/postres, Variedades y bazares, Artesanías y manualidades, Floristería y vivero, Agua/hielo y gas, Artículos religiosos y esotéricos, Entretenimiento y ocio, Cafetería, Licorería, Bar, Restaurante o comida rápida, Tienda naturista y/o suplementos, Tienda de mascotas, Ferretería y construcción, Artículos para el hogar, Industria o manufactura, Insumos agropecuarios, Panadería y Repostería, Tienda de abarrotes, Minimercado, Distribuidora/Mayorista, Salchichonería, Carnicería, Electrónica e informática.

**Crítica:** la lista mezcla **giro** (Cafetería, Carnicería), **surtido** (Salchichonería), **canal** (Venta por catálogo, Distribuidora/Mayorista) y **modelo de producción** (Industria o manufactura). Para Abarpay conviene separar ejes (§3.2). Dato relevante: **en las 6 capturas no hay "Peluquería", "Barbería", "Estética" ni "Uñas"**; lo más cercano es "Artículos de belleza", que es venta de producto, no servicio. El vertical que pide el dueño **no está cubierto por el benchmark**.

## 3. Ideas aplicables a Abarpay

Ordenadas de mayor a menor impacto esperado para "generalizar sin reescribir".

### 3.1 Segmentar por naturaleza de la oferta, no por industria (`A9`)

La idea más rentable del benchmark. En lugar de un menú gigante de giros, Treinta pregunta: **¿Productos, Servicios, Comida preparada y bebidas?** (multi-select) y promete "adaptaremos Treinta a tu negocio". Un solo interruptor explica el resto de la app.

Encaje con Abarpay: el andamiaje ya existe. `server/db.py` tiene `unlimited_stock` para "productos que no se descuentan", que es exactamente un servicio. Propuesta concreta:

- `store_settings.offer_kinds` (multi-select) — valores `producto`, `servicio`, `comida`.
- En el catálogo, `kind` por ítem: `producto` (descuenta inventario) · `servicio` (`unlimited_stock = 1`, sin alerta de resurtido) · `platillo` (sin inventario o con receta, para después).
- La consola y el home cambian **sustantivos**, no pantallas: "Productos/Ventas" → "Servicios/Cobros" para peluquería.
- Para el pitch: "la misma app sirve para tiendita, taquería y barbería" es una afirmación que este benchmark respalda.

### 3.2 Catálogo de giros en dos ejes + buscador (`A3`, `A6`, `A7`, `A8`, `A10`, `A2`)

Copiar el patrón visual (tarjetas 2 columnas, emoji, una línea de descripción, buscador arriba), pero **no la lista**: separar

1. **Giro** (qué es el negocio): abarrotes/minisúper, tortillería, taquería, comida corrida, cafetería, panadería, peluquería, barbería, estética de uñas, papelería, ferretería, otro.
2. **Canal** (cómo vende): mostrador, a domicilio, por catálogo/whatsapp.

Ventaja adicional: 8–10 giros en una sola pantalla caben sin scroll y el demo se ve corto. El giro elegido puede preseleccionar productos de ejemplo (tortillas por kg, corte de cabello, comida corrida) — hoy el seed de `server/db.py` está 100 % tiendita.

### 3.3 Las metas del dueño como configuración (`A4`)

"¿Qué te gustaría lograr?" con multi-select y **"Omitir"** es un truco de personalización barato: guardas 3–5 booleanos y ajustas qué tarjetas muestras en el home/consola. Mapeo directo con Abarpay:

| Meta de Treinta | Función de Abarpay que ya existe |
|---|---|
| Organizar mis ventas y gastos | `/api/reports/today`, consola (gastos **no** existen: ver §3.8) |
| Controlar lo que me deben | `GET /api/console/fiado` |
| Gestionar mejor mi inventario | `/api/inventory`, conteo por voz |
| Vender online / desde la computadora | Consola web (lo único que Abarpay ya tiene y Treinta cobra en PRO) |
| Ver estadísticas avanzadas | Reportes de la consola |

Para el pitch: "el onboarding no es un formulario, es la configuración del producto".

### 3.4 Primera venta guiada con pasos y CTA que muestra el total (`A11`)

- "Paso 2 de 3" + producto semilla + stepper de cantidad + **método de pago obligatorio** + CTA fijo con **cantidad y total**.
- Abarpay ya puede hacer esto con su flujo de carrito/dictado; lo que falta es el **hilo numerado** que lleva de "crear producto" a "primera venta" a "comprobante". Es barato y hace que el demo se sienta terminado.
- Cuidado: en Abarpay la venta no debe quedar "pagada" por elegir un método (regla dura 3). El paso puede ser "elegir cómo cobras" y el estado real lo pone `apply_payment`.

### 3.5 La confirmación dice qué cambió + siguiente acción (`A12`)

Hoy Abarpay termina una venta en efectivo con un mensaje ("Cobro en efectivo registrado"). Treinta muestra: **hecho**, qué se actualizó (inventario, con la nueva cantidad en unidades) y **dos salidas**: descargar comprobante / crear gasto. Es la pantalla que más confianza genera al dueño que no está presente.

Propuesta: al confirmar venta, mostrar de forma concreta "Coca-Cola: 24 → 23" (o "Servicio: sin inventario"), "Fiado de Juan: $180", y botón "Compartir comprobante". Todo eso ya está en la base (`stock_milli`, `fiado_entries`, `ticketCode`); es UI, no negocio nuevo.

### 3.6 Comprobante compartible como imagen/PDF con vista previa (`A12`, `A13`)

Campos que Treinta incluye y Abarpay debería tener: nombre del negocio, dirección, teléfono, correo, fecha/hora, **vendedor**, **estado Pagado**, **N° de transacción**, líneas con Cant./Precio Unit./Valor, total. Acciones: **compartir como imagen** y **como PDF**.

Por qué importa para el dueño ausente: el comprobante es la prueba que el empleado le manda al dueño por WhatsApp y la que el cliente se lleva. Es también evidencia anti-robo. Implementación Android: dibujar a Bitmap/PNG (sin dependencias nuevas) y compartir por `Intent`; PDF después.

### 3.7 Enseñar disponibilidad en unidades, no existencias técnicas (`A11`, `A12`)

"9 disponibles" en la tarjeta y "9 unidades" en la confirmación. Abarpay guarda `stock_milli` (miles de unidad, porque hay kg); mostrar eso al usuario es un error. Regla de UI propuesta: producto por pieza → "9 disponibles"; por kg → "9 kg disponibles"; servicio → "Servicio" (sin número). En la consola: "quedan 3" con el mismo formato, no "3000".

### 3.8 Gastos rápidos: el hueco más claro frente al benchmark (`A4`, `A5`, `A1`, `A12`)

Treinta pone "Ventas **y gastos**" en todas sus pantallas de valor y ofrece "Crear mi primer gasto" como siguiente paso natural. Abarpay no registra egresos. Para los giros nuevos el gasto es real: insumos de uñas, carne para la taquería, luz/renta de barbería.

Idea de bajo costo y muy "Abarpay": **dictar el gasto** con el mismo `server/parser.py` (que hoy solo elige `productId` del catálogo). "Gasté 350 en jitomate" → monto + categoría de gasto sugerida, **monto al usuario confirmarlo**; nunca precios de la IA en una venta (la regla dura 5 se mantiene porque un gasto no cobra). Si no cabe en el MVP, dejarlo como camino de 2 líneas en el pitch, no en la lámina como hecho.

### 3.9 Métodos de pago como grid, incluida transferencia (`A11`)

Treinta: Efectivo · Tarjeta · Transferencia bancaria · Otro · SPEI. Abarpay: efectivo / PEY / fiado. Para el negocio general, **"transferencia" es el método más común después del efectivo** y hoy no tiene dónde registrarse.

**Cuidado con la regla dura 3:** Treinta deja crear la venta como pagada con solo elegir "transferencia". Abarpay no puede copiar eso. Alternativa compatible: método `transferencia` registrado como **"por conciliar"** (ya existe ese estado en la app: "Cobro por revisar"), con captura del comprobante y confirmación explícita del dueño en la consola. Eso convierte una tentación en una ventaja: "el dueño ausente ve qué transferencias están sin confirmar".

### 3.10 Vocabulario por giro en el sustantivo de la venta (`A5`)

"**Tickets y comandas**" como tarjeta de función demuestra que Treinta adapta el sustantivo al vertical de comida. Para Abarpay, un mapa pequeño y configurable por `offer_kinds`:

| Giro | Sustantivo de la venta | Línea de catálogo |
|---|---|---|
| abarrotes/minisúper | Venta / Ticket | Productos |
| tortillería | Venta | Productos por kg |
| taquería / comida corrida | **Comanda** | Platillos |
| peluquería / barbería / uñas | **Servicio** | Servicios |
| ferretería / papelería | Venta / Ticket | Productos |

Un solo diccionario de etiquetas; cero pantallas nuevas.

### 3.11 Empaquetado Básico vs PRO: qué sí y qué no copiar (`A1`, `A5`)

- **Sí copiar el formato:** tabla de dos columnas con ✓/✗ por función y un "Recomendado" en el plan que quieres vender. Abarpay ya tiene "Plan Pro para el tendero" en `docs/modelo-de-negocio.md` §6 y le falta esta representación.
- **Sí tomar nota de qué va a gratis:** ventas, gastos, comprobantes, inventario, cotizaciones y tienda virtual están en el plan básico. Lo que Treinta cobra es **IA, facturación y computadora**. Para Abarpay: cobrar **multi-usuario/empleados, reportes avanzados y alertas de resurtido** es coherente con la sección 6 del modelo de negocio.
- **No copiar:** contador de oferta ("2d 23h 57m 40s"), precios tachados y "80% dto". En un hackatón con demo pública, la urgencia falsa choca con la regla dura 6 y con "cero datos de terceros". Si se muestra la comparativa en una lámina, etiquetarla como referencia externa.

### 3.12 Lo que Treinta ya tiene y Abarpay no (y qué tanto vale)

| Capacidad de Treinta | Evidencia | ¿Vale para Abarpay? | Costo estimado |
|---|---|---|---|
| Registro de **gastos** | `A4`, `A5`, `A1`, `A12` | Sí, alto: cierra el ciclo del negocio y habilita "dictar gasto" | M |
| **Comprobante** compartible imagen/PDF | `A12`, `A13` | Sí, alto: prueba para el dueño ausente | S |
| **Cotizaciones** de servicios | `A1` | Medio: útil para uñas/barbería (presupuesto antes de cobrar) | M |
| **Transferencia** como método | `A11` | Sí, medio: hoy no existe; exigir conciliación | S |
| **Tienda virtual** sencilla | `A1`, `A4` | Bajo para el MVP; alto para el relato de fase 2 | L |
| **Uso desde computadora** | `A1` | Abarpay **ya lo tiene** (consola web) y Treinta lo cobra en PRO | — |
| **IA**: lectura de facturas, fotos, sitio web | `A1` | Bajo/medio: Abarpay ya usa OpenAI para dictado; "dictar gasto" es la extensión natural | M |
| **Facturación electrónica** | `A1` | No: regla dura 7 | — |
| **Dashboard "Tu negocio hoy"** | `A12` (borroso) | Sí, bajo costo: la consola ya calcula cobrado hoy y fiado | S |
| Citas, propinas, caja, empleados | **No aparecen** | Desconocido: son justo lo que falta para peluquería | — (ver §4) |

### 3.13 Detalles de UI/UX reutilizables (sin copiar la marca)

1. **CTA fijo inferior con resumen** "1 · Crear venta · $20 ›" (`A11`): el usuario nunca se pregunta cuánto va a pasar.
2. **Stepper − 1 +** grande y a la derecha del precio (`A11`): mejor que teclear cantidades.
3. **Hoja inferior (bottom sheet) para confirmar y para el comprobante** (`A12`, `A13`): no saca al usuario del contexto.
4. **Tarjetas con emoji + una línea de descripción** (`A3`, `A6`–`A10`): identificación instantánea, cero iconografía propia.
5. **"Omitir" siempre visible** en onboarding (`A4`) y **barra de progreso** (`A4`, `A11`).
6. **Badge de disponibilidad en la tarjeta del producto** (`A11`): evita vender lo que no hay.
7. **Vista previa del comprobante antes de compartir** (`A13`): "así se verá".
8. **Header con nombre del negocio, ayuda (?) y campana** (`A11`): el "dueño ausente" reconoce su negocio desde la primera pantalla.

## 4. Preguntas y dudas

1. **¿Cuál es el primer giro después de tiendita?** El benchmark no muestra peluquería/barbería en su catálogo (34 giros visibles, ninguno de servicio de persona). Si el dueño quiere peluquería/barbería primero, el benchmark **no sirve** para ese vocabulario: hay que preguntar a alguien del giro o pedir capturas de una app de agenda.
2. **¿"Fiado" se queda?** Treinta evita la palabra ("controlar lo que me deben"). En barbería "fiado" suena a tiendita. Decisión de vocabulario pendiente: "lo que me deben" / "crédito" / "fiado".
3. **¿Se acepta "transferencia" como método sin verificación?** Treinta sí; la regla dura 3 de Abarpay lo prohíbe. Propuesta: método "transferencia (por conciliar)" + confirmación del dueño. Necesita OK del integrador porque toca `server/payments.py` (**aviso obligatorio al integrador** según AGENTS.md).
4. **¿Los servicios requieren agenda/citas o basta cobrar el servicio?** Las capturas no muestran citas. Si peluquería necesita agenda, es un módulo nuevo (calendario, recordatorios) y no está respaldado por este benchmark.
5. **¿Propinas y caja entran?** No hay una sola pantalla de propina ni de corte de caja en las 13 capturas. ¿Se requieren para "dueño ausente" (arqueo por empleado) o se resuelven con el reporte diario que ya existe?
6. **¿Gastos entran al MVP?** Treinta los pone en el plan básico; Abarpay no los tiene. Si entran, ¿con foto de ticket (IA) o dictado? ¿Quién los captura, el dueño o el empleado (permisos)?
7. **¿De dónde sacamos más evidencia?** Este set es solo onboarding + primera venta + comprobante, y todo con el fondo desenfocado. Faltan capturas de home, inventario, clientes/fiado, reportes, empleados y caja. Sin ellas, cualquier afirmación sobre "cómo lo hace Treinta" en esas áreas es especulación.
8. **¿Moneda y país del build?** El recibo dice `$` sin moneda y los métodos incluyen **SPEI** (México), aunque la app sea colombiana. Confirmar que el benchmark es de producto, no de rieles de pago; los precios ($79.80/mes, $239.78/trimestre) no son comparables con MXN sin fuente.
9. **¿Se cita Treinta en láminas del pitch?** Si sí, con nombre y como referencia externa, y sin replicar precios ni descuentos. La comparación honesta ("esto ya existe y esto hacemos distinto: cobro CoDi verificado + dictado") es más fuerte que copiar su paywall.
10. **¿Cómo se llama el giro en el código?** `store_settings.business_type` hoy es texto libre y `DEFAULT_BUSINESS_TYPE = ""` (`server/db.py`). Pasar a catálogo cerrado + `offer_kinds` toca `db.py` y el contrato v2: coordinar con quien esté editando `docs/v2-contract.md` (hay cambios sin commitear en el árbol).

---

**Archivos leídos (13/13):** `30175AD7-B4EB-4121-A738-92A56A552976.png`, `3E1205B3-7E38-4EDB-B89B-4DF864BD1DDA.png`, `77EF564B-7E49-44E5-AC7C-5A4D4B893FA5.png`, `7B1837AC-6D11-4460-B7B8-B4AC675C17A5.png`, `7E8B9F86-E415-44E0-83B8-25B534DDA62E.png`, `93B225C3-5378-4057-ACE2-E48C6B2ECE6E.png`, `AA76430D-A963-472C-A0E3-2D676FB6F6C1.png`, `B808B64D-C121-4BED-AEE0-B842914CF94B.png`, `D8153C70-099A-4FD8-AF5C-65FB332E93E7.png`, `D90EB492-13C4-43D1-8CCE-66DBA77DE452_4_5005_c.jpeg`, `D9A0CEB0-9431-444A-B27C-59F82703AD19.png`, `D9D6CC98-0105-4A7C-9E9A-7FB109C3024B.png`, `DC03293E-6F94-4081-A7EF-D1E20CA8CF79_4_5005_c.jpeg`. (Son los 13 archivos de `Benchmarking/`; se abrieron todos.)
