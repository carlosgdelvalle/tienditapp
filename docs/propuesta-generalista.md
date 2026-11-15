# Propuesta · Abarpay como solución general para negocios pequeños

Fecha: 2026-11-15 · Estado: propuesta para el dueño (no implementada).
Complemento: docs/benchmark-colombia.md (conocimiento de la app colombiana analizada).

## Objetivo

Hoy Abarpay está escrita como "caja de tiendita": productos, piezas/kilos, stock, fiado y tareas de tiendita. El dueño quiere que los mismos flujos (cobrar con PEY/efectivo/fiado, equipo con permisos, inventario, reportes, consola del dueño) sirvan para peluquerías/barberías, tortillerías, comidas corridas, taquerías, estéticas de uñas y una lista larga de negocios donde el dueño no siempre está físicamente.

## Supuestos "tiendita" detectados en el código

| Dónde | Hoy | Riesgo para otros negocios |
| --- | --- | --- |
| server/db.py | unit CHECK IN ('pieza','kg') | Un corte de pelo, una uña o un turno no son piezas ni kilos |
| server/db.py seed | Catálogo de 12 productos de abarrotes (Coca, Sabritas, Bimbo…) | Toda tienda nueva nace como tiendita |
| Android BUSINESS_TYPES | Tiendita, Abarrotes, Miscelánea, Fondita, Otro | No cubre la lista nueva de negocios |
| Android qtyText | "12 pza" / "0.5 kg" | No existe "1 servicio", "30 min", "1 sesión" |
| Android Home | "Tu tiendita", tareas fijas "Contar inventario", "Limpiar tienda" | Copia y tareas no aplican a otros rubros |
| Parser de voz | números + piezas/kilos | "dos cortes", "una sesión de uñas" |
| Consola | "Tiendita", tarjetas de stock/valor | Los servicios no tienen stock ni valor de inventario |
| Catálogo | No hay alta/edición de productos en app ni consola (solo seed + migraciones) | Cada negocio nuevo no puede crear su propio catálogo |

## Cambios propuestos

### 1. Modelo: "productos" → catálogo de artículos y servicios

- Ampliar unit a un texto libre controlado: pieza, kg, g, litro, servicio, sesión, turno, minuto, hora, paquete, combo (enum abierto en la base, validado por el servidor).
- unlimited_stock pasa a significar "no lleva inventario" (servicios, comidas preparadas al momento, taquería) — ya existe la columna, solo cambia la semántica y las etiquetas.
- Añadir duration_minutes INTEGER NULL para servicios (corte 30 min, uñas 60 min) — opcional, solo para reportes/tiempos; no implica agenda ni citas.
- Añadir CRUD de catálogo: POST/PATCH/DELETE /api/catalog (dueño) y editor en consola + app (nombre, precio, unidad, aliases, stock o sin límite, duración). Esta es la pieza que falta para que cualquier negocio sea autosuficiente.

### 2. Onboarding por tipo de negocio

- Ampliar BUSINESS_TYPES: Tiendita/Abarrotes, Miscelánea, Tortillería, Taquería, Comida corrida, Peluquería/Barbería, Estética de uñas, Fondita/Restaurante, Otro.
- Al elegir tipo, el servidor crea un catálogo semilla por tipo (solo en base nueva): ej. taquería → Taco, Quesadilla, Gringa, Refresco; peluquería → Corte de caballero, Corte de dama, Barba, Peinado; estética → Manicura, Pedicura, Uñas acrílicas; tortillería → ½ kg, 1 kg, 5 kg de tortilla; comida corrida → Comida corrida, ½ orden, Agua del día. El dueño puede editarlos después.
- Las tareas del día del Inicio del empleado también se derivan del tipo (tortillería: "Revisar la máquina", peluquería: "Preparar estación y desinfectar", taquería: "Preparar salsa y tortillas") con respaldo genérico (Contar inventario, Limpiar). Viven en el servidor por tipo de negocio, editables después.

### 3. Nomenclatura genérica (barrido de copia)

- "Tiendita de la Esquina" / "Tu tiendita" → "tu negocio" o el nombre elegido en onboarding (ya se guarda; solo falta usar la copia).
- "Productos" → "Artículos y servicios"; "Stock bajo" → "Inventario bajo" (solo cuando aplique); "pza/kg" → unidades según el artículo.
- Fiado: mantener la palabra (es entendida en MX) pero en UI genérica "Ventas a crédito (fiado)".
- PEY/CoDi, efectivo, tickets, equipo e invitaciones no cambian.

### 4. App (Android)

- Pantalla de cobro: igual de ágil, pero el catálogo muestra servicios sin controles de stock (usar unlimitedStock), y el selector de cantidad por presets se adapta a la unidad (servicio → 1, 2, 3; kg → 250 g/500 g/1 kg/2 kg; minuto → 30/60).
- Inventario: solo para artículos con inventario; los servicios no aparecen (o aparecen en una pestaña "Servicios" sin stock).
- Inicio dueño/empleado: tareas por tipo de negocio; la tarjeta "Stock bajo" se oculta si no hay artículos con inventario.
- Voz: extender parser a "dos cortes", "una sesión de uñas", "medio kilo de tortilla", "tres tacos" (alias por catálogo + unidades nuevas).
- Catálogo: pantalla "Artículos y servicios" en el dueño (ver/editar/crear) — v1 mínima: lista + alta/edición por formulario.

### 5. Consola

- Sección "Catálogo" con CRUD (nombre, precio, unidad, stock/sin límite, duración, aliases).
- Inventario: valor solo para artículos con stock; los servicios se listan aparte sin valor de inventario.
- Reportes: "Más vendido" ya es genérico; agregar desglose por tipo de unidad en el detalle.
- Copia: "Tu negocio" en lugar de tiendita; el tipo de negocio elegido se muestra junto a la foto.

### 6. Migración y datos existentes

- Todo aditivo: ampliar el CHECK de unit, nueva columna duration_minutes, tabla de plantillas de catálogo por tipo y tareas por tipo. La base de Render conserva sus 18 productos y ventas; los cambios de copia no tocan datos.

## Prioridades

- P0: unidades genéricas + semántica "sin inventario" para servicios; onboarding con tipos nuevos y catálogo semilla por tipo; barrido de copia "tiendita→negocio"; CRUD de catálogo (consola + dueño app); tareas por tipo.
- P1: voz para servicios/unidades nuevas; presets de cantidad por unidad; reportes por unidad.
- P2: agenda/citas (solo si el benchmark lo justifica), propinas, duración en reportes de productividad.

## Qué NO cambiar

- Flujo de cobro PEY/CoDi y regla "solo verde = entregar".
- Equipo, invitaciones por enlace/QR y permisos.
- Tickets de soporte y rastro de eventos PEY.
- Consola como centro del dueño con PIN.

## Decisiones para el dueño

1. ¿CRUD de catálogo primero en consola, en app o ambos? (propuesta: ambos, consola primero).
2. ¿Los catálogos semilla por tipo se aplican solo a negocios nuevos? (propuesta: sí).
3. ¿Tareas del día editables por el dueño en esta iteración o plantillas fijas por tipo? (propuesta: plantillas fijas por tipo, editables después).
4. ¿Mantener la marca "Abarpay" y el nombre demo "Tiendita de la Esquina" en pantallas de demostración, o renombrar la demo? (propuesta: renombrar demo a un negocio neutro, ej. "Mi negocio").


## Aprendizajes del benchmark (Treinta, Colombia/MX)

Fuente: docs/benchmark-colombia.md (13 capturas de una demo en vivo).

1. **Segmentar por naturaleza de la oferta, no por giro** (pantalla "¿Qué vende tu negocio?" → Productos / Servicios / Comida preparada y bebidas, multi-select). Es el cambio de mayor impacto: un interruptor por ítem (producto con inventario · servicio sin inventario · platillo) explica el resto de la app. Abarpay ya tiene el andamiaje en unlimited_stock.
2. **Giro vs canal en dos ejes**: giro (tiendita, tortillería, taquería, cafetería, peluquería/barbería, estética de uñas, papelería, ferretería, otro) + canal (mostrador, a domicilio, por catálogo/WhatsApp). La lista larga de 34 giros mezcla criterios y no incluye peluquería/barbería/uñas: el vertical nuevo del dueño es nuestra aportación, no del benchmark.
3. **Nomenclatura**: "negocio" (no tiendita), módulo "Inventario", disponibilidad "disponibles", cantidad "unidades"; "Controlar lo que me deben" en lugar de "fiado"; "Comprobante" + "N° Transacción" + "Pagado". El sustantivo de la pantalla de venta cambia a "Crear venta" (pago es un atributo).
4. **Onboarding**: numerado con "Omitir", metas multi-select como configuración del home, y CTA que dice qué va a pasar ("1 Crear venta · $20"). La confirmación dice qué cambió ("tu inventario fue actualizado") y ofrece **compartir comprobante** (imagen/PDF).
5. **Gastos** existen desde el plan básico de Treinta ("Ventas y gastos", "Crear mi primer gasto"); Abarpay hoy solo registra ingresos. Candidato P1 con dictado reusando el parser.
6. **No hay evidencia en las capturas** de inventario operativo, empleados, citas, propinas, caja ni catálogo de servicios; no sobreinvertir en agenda/citas por ahora.
7. **Conflicto a no copiar**: Treinta registra "Transferencia bancaria/SPEI" sin verificar; Abarpay mantiene la regla dura (solo apply_payment marca pagado).

## Decisiones adicionales para el dueño (benchmark)

5. ¿Adoptar la segmentación Productos / Servicios / Comida preparada y bebidas en el onboarding y en cada ítem del catálogo? (propuesta: sí, con la lista corta de giros en un solo paso).
6. ¿Añadir "Gastos" en esta iteración (registro simple + dictado) o dejarlo para después? (propuesta: después, como P1).
7. ¿Comprobante compartible (imagen/PDF) tras cada venta? (propuesta: P1; en PEY el QR ya cumple la función para el cliente).
