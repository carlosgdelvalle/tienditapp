# codigos-barras-mx

Catálogo libre de códigos de barras (EAN-13 / UPC-A / EAN-8) de productos que se venden en
México, pensado para puntos de venta de tiendas de abarrotes como el desarrollado por mi 
[Punto-Ventas](https://github.com/Minepacman/Punto-Ventas). Se construye automáticamente a
partir de [Open Food Facts](https://world.openfoodfacts.org) y sus proyectos hermanos
(Open Beauty Facts, Open Pet Food Facts, Open Products Facts), más una lista curada a mano en
`extra/manual.csv`. Se actualiza cada semana.

> Contiene información de Open Food Facts, disponible bajo la Open Database License (ODbL).

## Qué hay

| Archivo | Contenido |
|---|---|
| `datos/catalogo-mx.csv` | Catálogo completo (UTF-8, encabezado, ~25 000 productos, ~3.5 MB) |
| `datos/catalogo-mx.jsonl` | Lo mismo, un objeto JSON por línea |
| `api/v1/NNN.json` | 1000 fragmentos pequeños (~6 KB) para consultar un código sin bajar todo |
| `api/v1/version.json` | Fecha, conteos por fuente/categoría y sha256 de los archivos completos |
| `extra/manual.csv` | Correcciones y altas hechas a mano (prioridad máxima al combinar) |
| Releases | `catalogo-mx.csv.gz`, `catalogo-mx.jsonl.gz`, `version.json`, `SHA256SUMS.txt` |

### Columnas

| Columna | Descripción |
|---|---|
| `codigo` | Código normalizado: 13 dígitos (EAN-13; los UPC-A llevan un `0` al frente) u 8 (EAN-8). Dígito de control verificado; los inválidos se descartan. |
| `nombre` | Nombre del producto (se prefiere el nombre en español). |
| `marca` | Primera marca declarada. |
| `cantidad` | Número (vacío/`null` si no se pudo deducir). |
| `unidad` | `g`, `kg`, `mg`, `ml`, `cl`, `l`, `oz`, `fl oz`, `lb`, `pz`. |
| `contenido` | Texto original de la cantidad ("6 x 355 ml"). |
| `categoria` | Departamento: Bebidas, Botanas, Lácteos, Panadería, Abarrotes, Limpieza, Higiene personal, Dulces, Enlatados, Congelados, Carnes y embutidos, Mascotas, Bebés, Otros. |
| `imagen` | URL de la miniatura frontal (200 px) en los servidores de Open Food Facts. Solo la URL. |
| `fuente` | `off`, `obf`, `opff`, `opf` o `manual`. |
| `actualizado` | Fecha de la última modificación en la fuente (AAAA-MM-DD). |

## Cómo usarlo

### Descargar todo el catálogo (recomendado para el punto de venta)

El Release más reciente siempre está en estas URLs fijas:

```
https://github.com/Minepacman/codigos-barras-mx/releases/latest/download/catalogo-mx.csv.gz
https://github.com/Minepacman/codigos-barras-mx/releases/latest/download/catalogo-mx.jsonl.gz
https://github.com/Minepacman/codigos-barras-mx/releases/latest/download/version.json
https://github.com/Minepacman/codigos-barras-mx/releases/latest/download/SHA256SUMS.txt
```

Para saber si hay versión nueva sin descargar todo, compara `fecha` o los `sha256` de `version.json`.
Los archivos sin comprimir también están en el repositorio:

```
https://raw.githubusercontent.com/Minepacman/codigos-barras-mx/main/datos/catalogo-mx.csv
https://cdn.jsdelivr.net/gh/Minepacman/codigos-barras-mx@main/datos/catalogo-mx.csv
```

### Consultar un solo código (fragmentos `api/v1`)

Algoritmo:

1. Normaliza el código: quita todo lo que no sea dígito; si tiene 12 dígitos (UPC-A) antepón `0`;
   si tiene 8, déjalo así. Comprueba el dígito de control si quieres ahorrarte la consulta.
2. Toma los **últimos 3 dígitos** del código normalizado: ese es el nombre del fragmento.
3. Descarga `api/v1/<esos 3 dígitos>.json` y busca el código completo como clave del objeto.

Ejemplo con la Coca-Cola de 355 ml, código `7501055300075` → fragmento `075`:

```
https://cdn.jsdelivr.net/gh/Minepacman/codigos-barras-mx@main/api/v1/075.json
https://raw.githubusercontent.com/Minepacman/codigos-barras-mx/main/api/v1/075.json
```

```json
{
  "7501055300075": {
    "nombre": "Coca-Cola", "marca": "Coca-Cola", "cantidad": 355, "unidad": "ml",
    "contenido": "355 ml", "categoria": "Bebidas",
    "imagen": "https://images.openfoodfacts.org/images/products/750/105/530/0075/front_fr.25.200.jpg",
    "fuente": "off", "actualizado": "2026-03-13"
  },
  "...": {}
}
```

Otro ejemplo: Coca-Cola Light 600 ml, `7501055305339` → `api/v1/339.json` →
`{"nombre": "Coca Cola Light 600", "cantidad": 600, "unidad": "ml", ...}`.
Si el código no es clave del objeto, el producto no está en el catálogo (el fragmento siempre
existe: hay 1000, de `000` a `999`).

jsDelivr cachea `@main` hasta 12 h; `raw.githubusercontent.com` unos 5 min. Para fijar una
versión concreta usa la etiqueta del Release: `…/codigos-barras-mx@v2026-11-12/api/v1/075.json`.

### Desde la línea de comandos

```sh
curl -sL https://cdn.jsdelivr.net/gh/Minepacman/codigos-barras-mx@main/api/v1/075.json | python3 -c \
  "import json,sys; print(json.load(sys.stdin).get('7501055300075'))"
```

## Calendario de actualización

El flujo `actualizar.yml` corre cada **lunes a las 09:00 UTC** (también a mano desde la pestaña
Actions). Descarga los productos de México, regenera `datos/` y `api/`, corre las pruebas, hace
commit si algo cambió y publica un Release `vAAAA-MM-DD` con los archivos comprimidos y sus
checksums.

## Cómo se obtiene la información

- **Open Food Facts** publica a diario una exportación Parquet en Hugging Face
  (`openfoodfacts/product-database`, ~8 GB). `scripts/descargar.py` la consulta **a distancia con
  DuckDB** (peticiones HTTP por rangos contra la URL firmada del CDN, resuelta una sola vez para no
  agotar el límite de 3000 resoluciones/5 min de Hugging Face), filtrando por `countries_tags` ∋
  `en:mexico` **o** código con prefijo GS1 `750` (México): 27 884 filas, frente a las 18 607 que
  devuelve la búsqueda por país. Medido: ~4 minutos y ~7 GB transferidos (los grupos de filas del
  Parquet son de solo 1024 filas, así que la proyección de columnas apenas ahorra transferencia).
  Es rápido y no toca los servidores de OFF, pero no es ligero en bytes; en el runner de GitHub
  es aceptable una vez por semana. Los productos de belleza y de mascotas salen de los Parquet
  `beauty` (68 MB) y `petfood` (8 MB) igual.
- **Open Products Facts** no tiene Parquet: se usa la API de búsqueda paginada, con pausas de
  6.5 s entre peticiones (límite público de 10 búsquedas por minuto) y el User-Agent
  `PuntoDeVenta-Catalogo/1.0 (https://github.com/Minepacman/codigos-barras-mx)`.
  Esa misma API es el respaldo automático si el Parquet falla, y la opción de poco ancho de banda
  (`--estrategia busqueda`: 187 páginas de 100, unos 20 minutos, pocos MB; solo trae los productos
  etiquetados con México).
- Se descartan productos marcados obsoletos, sin nombre o con código inválido (por ejemplo los
  códigos internos de tienda que empiezan con `2`).
- Se deduplica por código con prioridad `manual` > `off` > `obf` > `opff` > `opf`; a igual
  fuente gana el más reciente.
- La categoría sale de `categories_tags` de OFF (`scripts/catalogo/categorias.py`); la mayoría de
  los productos mexicanos no tienen etiquetas, así que si no deciden se deduce de las palabras del
  nombre ("leche" → Lácteos, "detergente" → Limpieza…). Es una heurística: corrige lo que veas
  mal en `extra/manual.csv`.

### Fuentes revisadas y descartadas

| Fuente | Por qué no |
|---|---|
| GS1 México | No tiene API ni descarga pública. |
| UPCitemdb, Go-UPC, Barcode Lookup | De pago o con muy poca cobertura de México; licencias que no permiten redistribuir. |
| PROFECO "Quién es Quién en los Precios" (datos.gob.mx) | Sus tablas traen producto, presentación, marca y precio pero **no códigos de barras**. |
| Wikidata (propiedad P3962, GTIN) | Licencia CC0, pero solo ~3 000 GTIN en total y 1 con prefijo 750. |

## Cómo contribuir

1. **Lo mejor: en Open Food Facts.** Da de alta o corrige el producto en
   [world-es.openfoodfacts.org](https://world-es.openfoodfacts.org) o con la app móvil, marcando
   México como país. Así lo aprovecha todo el mundo y aquí llega en la siguiente actualización
   semanal.
2. **Aquí, con un PR a `extra/manual.csv`.** Mismas columnas que el catálogo; las filas de este
   archivo ganan sobre cualquier fuente. Las líneas que empiezan con `#` se ignoran. Ejemplo:

   ```csv
   codigo,nombre,marca,cantidad,unidad,contenido,categoria,imagen,fuente,actualizado
   # Coca-Cola retornable de vidrio
   7501055300075,Coca-Cola 355 ml,Coca-Cola,355,ml,355 ml,Bebidas,,manual,2026-11-12
   # Bimbo Pan Blanco Grande (corrección de categoría)
   7501000111541,Pan Blanco Grande,Bimbo,680,g,680 g,Panadería,,manual,2026-11-12
   ```

   El flujo `validar.yml` revisa cada PR: dígito de control, columnas, categoría válida,
   duplicados y fecha `AAAA-MM-DD`. Localmente: `python scripts/validar_manual.py`.

## Ejecutar en local

```sh
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                                # pruebas de normalización, categorías, manual
python scripts/descargar.py --salida build/crudo   # ~5 min; usa --estrategia busqueda si el Parquet falla
python scripts/generar.py                          # escribe datos/ y api/v1/
python scripts/empaquetar.py                       # build/release/*.gz + SHA256SUMS.txt
```

Dependencias: solo `duckdb`, `requests` y `pytest` (fijadas en `requirements.txt`).
Opcional: la variable `HF_TOKEN` (token de Hugging Face) amplía los límites de descarga del Parquet.

## Licencias

- **Datos** (`datos/`, `api/`, `extra/`): [Open Database License (ODbL) 1.0](LICENSE-DATOS.md)
  para la base de datos y Database Contents License (DbCL) 1.0 para su contenido, igual que
  Open Food Facts. Al reutilizarlos conserva la atribución:
  *"Contiene información de Open Food Facts, disponible bajo la Open Database License (ODbL)"*.
  Si publicas una base de datos derivada debe ser también ODbL (cláusula compartir-igual).
- **Imágenes**: no se redistribuyen; aquí solo hay URLs. Las fotos siguen en Open Food Facts bajo
  CC BY-SA 3.0 y son de sus fotógrafos.
- **Scripts y flujos** (`scripts/`, `tests/`, `.github/`): [GPL-3.0](LICENSE), igual que Punto-Ventas.
