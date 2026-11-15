# Selección para tiendita de abarrotes mexicana

Usar **catalogo-incluir.csv** como repertorio de referencia, NO como inventario de una sola tienda ni lista de productos de alta rotación. **profeco-incluir.csv** aporta presentaciones y precios observados sin inventar UPC. Son filtros editoriales reproducibles, no validación universal del surtido.

## Criterios y archivos

Se admiten alimentos envasados, bebidas sin alcohol, pan/galletas/tortillas, botanas, dulces, abarrotes, conservas, lácteos/huevo, embutidos, higiene y limpieza básicas, alimento para mascotas y algunos consumibles domésticos. Helados, refrigerados y embutidos requieren equipo apropiado. Se preservan sabores, tamaños, códigos, nombres originales, precios, fechas y procedencia; se añade familia editorial sin sobrescribir la categoría fuente, que contiene errores.

- `*-incluir.csv`: repertorio propuesto para el caso de uso.
- `*-revisar.csv`: no se propone para cargar; descripción insuficiente, variantes especializadas, marca de supermercado, granel, volumen grande o producto sin señal suficiente. No significa producto inexistente ni imposible de vender.
- `*-excluir.csv`: medicamentos/suplementos, alcohol/tabaco, electrodomésticos, juguetes, material escolar, ropa deportiva, carnes/pescados frescos, preparación de comidas y nichos ajenos al alcance básico. Algunas tiendas sí venden estos artículos; se excluyen por alcance, no por prohibición general.
- `resumen.json`: conteos completos y categorías del subconjunto.
- `muestra-inicial.csv`, `muestra-segunda.csv`: muestras revisadas durante ajuste; `muestra-auditoria.csv`: muestra reproducible resultante. 30 filas por fuente/decisión (180 cada una), semilla 20261115. No son muestras de ventas.

Todos los 10 códigos previos permanecen en incluir por instrucción expresa, incluidos los cinco `demo_sintetico`. El nombre comercial no se toma como certificación del GTIN. No se crean nuevos precios ni se transfieren precios entre sabores/tamaños. Los 21 vínculos Profeco del conjunto completo siguen siendo los únicos vínculos revisados; el filtro no confirma ninguno nuevo. Las fechas de precio siguen siendo enero–marzo de 2026, NO noviembre. Véase README superior para licencias, fuentes y límites de descarga.

## Revisión de calidad realizada

Primera muestra (180 filas): entre las 60 inclusiones se detectaron **8 inclusiones fuera del criterio conservador** (dos nichos, cinco marcas de supermercado y un paquete de 32 rollos); se movieron a revisión. Hubo **7 errores de familia** en productos admisibles (por ejemplo pasta Colgate, mayonesa con jugo, gelatina con leche); se ajustó la prioridad del nombre sobre ingredientes/presentación. Entre las 60 exclusiones hubo **1 falsa exclusión clara**, el condimento Knorr Costilla Jugosa; se recuperó. Entre los 60 pendientes se recuperaron **14 omisiones claras** de productos básicos por variantes léxicas (crema dental, toallas femeninas, rastrillos, piña en almíbar, etc.). Lo que sigue en revisión no es un rechazo definitivo.

Segunda muestra de 60 inclusiones: se detectó **1 inclusión incorrecta** de pescado no en conserva (cubitos de atún) y **5 inclusiones para revisión** por línea especializada/marca de supermercado (dos Picard, Vitali, Nutrisa y Golden Hills). Se corrigieron las reglas. No se atribuye a estos conteos precisión estadística: son muestras usadas para ajustar, no un conjunto independiente de validación, y los límites editoriales admiten discusión. Pueden quedar falsas inclusiones y exclusiones; no se revisaron manualmente miles de filas.

## Reproducir y verificar

Desde raíz del repo: `python3 resources/catalogo-mx/scripts/filter_tiendita.py`.

La suma de las tres decisiones debe conservar todas las filas de cada fuente sin duplicar identificadores. Comparar cada campo fuente contra el CSV superior: debe mantenerse idéntico. El script no abre la base de datos, no toca la app ni despliega. Para reabastecimiento real revisar empaque, vigencia, proveedor, precio local y requisitos de almacenamiento.
