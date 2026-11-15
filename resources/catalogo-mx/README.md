# Catálogo de referencia México y cruce QQP

Corte de preparación: **15 de noviembre de 2026**. Recurso de datos, no migración ni actualización de la base activa. No se cambiaron precios, existencias, APK, servidor ni Render.

## Resultado

- 24,887 registros de Códigos de barras MX (versión de fuente 2026-11-12).
- 24,893 registros finales: se conservaron los 10 códigos existentes de Abarpay, 4 ya presentes y 6 agregados.
- Los 6 agregados son **Pay frutos rojos `7500810054888`** y los 5 códigos sintéticos `7500000000001`–`7500000000005`. Estos últimos NO son UPC reales certificados y están etiquetados `demo_sintetico`.
- 4,148 identidades de producto/presentación/marca/categoría Profeco, sin columna GTIN en la fuente.
- 516 candidatos por marca normalizada, cantidad/unidad y solapamiento de descripción. **No se asignan automáticamente como coincidencias.**
- 21 cruces revisados por correspondencia de descripción, marca y presentación. No son certificación GS1 ni prueba de que Profeco haya utilizado ese GTIN exacto. Revisar contra empaque si se usa en producción.

## Archivos

- `catalogo-integrado.csv`: códigos como texto, datos de origen, nombre/precio demo anterior separados, vínculo Profeco sólo para coincidencias revisadas, precio observado y fecha/ámbito.
- `profeco-productos.csv`: todas las identidades del subconjunto legible, con mediana/mínimo/máximo de precios, fecha y cantidad de observaciones.
- `cruces-candidatos.csv`: candidatos para revisión, NO lista de equivalencias. El precio pertenece al producto Profeco, no necesariamente al código candidato.
- `cobertura-existentes.csv`: verificación individual de los códigos existentes.
- `confirmaciones.json`: correspondencias revisadas por descripción, utilizadas por el generador.
- `raw/`: catálogo original, metadatos, licencia, snapshot mínimo de productos y manifiesto SHA-256 de los CSV Profeco utilizados.
- `scripts/build.py`: reconstruye los CSV desde fuentes/agrupados conservados. No abre ni escribe la base de la app.

## Precios, alcance y calidad

Profeco no permite unión por UPC porque sus CSV revisados no incluyen códigos. Se exige marca y cantidad/unidad compatibles; nombres ambiguos, sabores distintos, leche pasteurizada vs ultrapasteurizada y presentaciones distintas quedan sin precio asignado. No se usa similitud textual como prueba suficiente.

La mediana se calcula con observaciones de la **última fecha disponible de cada identidad**. Se prioriza CDMX/Estado de México en esa fecha; si no hay observaciones locales, se utiliza el conjunto nacional y se etiqueta así. No es precio vigente de noviembre, precio obligatorio, costo de adquisición ni precio de una tiendita particular. Los precios ya existentes se preservan como `precio_demo_existente_centavos`, sin presentarlos como verificados.

**Limitación real de descarga:** los RAR oficiales 2025 y 2026 descargados devolvieron error de archivo truncado al listar/extractar. No se rellenaron datos. Se utilizaron únicamente los cinco miembros 2026 extraídos sin error antes del miembro truncado: enero Q1/Q2, febrero Q1/Q2 y marzo Q1. Se excluyó marzo Q2 incompleto y no se usó 2025. El intervalo termina el 13 de marzo de 2026. Por ello, este resultado no representa todo QQP 2026. Los archivos fuente grandes permanecen en `/tmp/tienditapp-qqp/2026`; no se incorporan al repositorio (aprox. 1 GB); se conservan agregados y hashes para auditoría.

`comun_demo=True` significa **producto cruzado con el subconjunto Profeco**, el criterio práctico pedido para la demo; no mide ventas, frecuencia nacional ni participación de mercado. Todos los productos en `profeco-productos.csv` son el conjunto de referencia de "comunes"; sólo los vinculados de manera revisada reciben esa bandera en el catálogo GTIN.

El catálogo de códigos selecciona México o prefijo 750: eso no demuestra fabricación mexicana, venta actual o calidad de ficha. Tiene registros antiguos, nombres pobres y categorías heurísticas. Fecha de publicación no equivale a fecha de observación de todos los productos. No cargar indiscriminadamente estos 24 mil registros como inventario de una tienda. Revisar imágenes/licencias antes de mostrarlas; no se descargaron imágenes.

## Fuentes y reutilización

- https://github.com/Minepacman/codigos-barras-mx
- https://raw.githubusercontent.com/Minepacman/codigos-barras-mx/main/api/v1/version.json
- https://raw.githubusercontent.com/Minepacman/codigos-barras-mx/main/datos/catalogo-mx.csv
- https://datos.profeco.gob.mx/index.php
- https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar
- https://datos.profeco.gob.mx/docs/qqp/QQP_2025.rar

**Contiene información de Open Food Facts, disponible bajo la Open Database License (ODbL).** Conservar atribución y condiciones ODbL/DbCL del archivo `raw/LICENSE-DATOS.md`; las bases derivadas se distribuyen bajo ODbL. Las imágenes enlazadas tienen condiciones propias (CC BY-SA según fuente), no están incluidas. Profeco se atribuye como fuente de precios públicos; verificar condiciones aplicables antes de redistribución comercial. La licencia de los datos no relicencia el código de Abarpay.

## Reconstruir y verificar

```sh
python3 resources/catalogo-mx/scripts/build.py
# Opcional, si se dispone de los CSV íntegros originales:
python3 resources/catalogo-mx/scripts/build.py /tmp/tienditapp-qqp/2026
python3 resources/catalogo-mx/scripts/validate.py
```

El árbol principal tenía cambios activos de otra tarea: este trabajo sólo agregó `resources/catalogo-mx/`, sin cambiar de rama, commit, push o despliegue. La API pública bootstrap corroboró los 18 productos de la demo; los 10 códigos se leyeron de la base local y del registro `catalog-added.json`, no de la base remota (bootstrap no expone códigos).

## Selección editorial para tiendita

Ver `tiendita/README.md` y `tiendita/catalogo-incluir.csv`: subconjunto filtrado sin destruir estas fuentes. Los pendientes y excluidos permanecen separados, con motivos. No representa frecuencia real de venta.
