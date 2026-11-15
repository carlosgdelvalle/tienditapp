"""v3 business templates: curated starting catalogs and fixed day tasks.

Applying a template is only allowed while the store has no products at all
(see POST /api/catalog/templates/apply). The tiendita template is a curated
subset of 28 items selected from
resources/catalogo-mx/tiendita/catalogo-incluir.csv; the curated codes and the
demo prices live here, the names/categories/observed prices are read from the
resource files at runtime. The full CSV (thousands of rows) is never embedded
nor inserted. If the resources folder is not deployed, the module keeps
working with the curated fallback metadata.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

BUSINESS_TYPES = (
    "tiendita",
    "tortilleria",
    "taqueria",
    "comida-corrida",
    "peluqueria",
    "estetica",
    "fondita",
    "otro",
)

# Aliases the Android onboarding may send; they map to the contract types.
BUSINESS_TYPE_ALIASES = {
    "tienda": "tiendita",
    "abarrotes": "tiendita",
    "tiendita-abarrotes": "tiendita",
    "miscelanea": "tiendita",
    "miscelanea-tiendita": "tiendita",
    "tortilleria-y-molino": "tortilleria",
    "taqueria-y-antojitos": "taqueria",
    "comida-corrida-y-cocina": "comida-corrida",
    "peluqueria-barberia": "peluqueria",
    "barberia": "peluqueria",
    "estetica-de-unas": "estetica",
    "unas": "estetica",
    "fondita": "fondita",
}

CATALOG_RESOURCES_DIR = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "catalogo-mx"
    / "tiendita"
)
CATALOG_FILE = "catalogo-incluir.csv"
RESUMEN_FILE = "resumen.json"

# Short user-facing categories for the resource families (chips in the app).
_CATEGORY_BY_FAMILY = {
    "Abarrotes y conservas": "Abarrotes",
    "Lácteos y huevo": "Lácteos",
    "Pan, galletas y tortillas": "Pan",
    "Botanas": "Botanas",
    "Bebidas sin alcohol": "Bebidas",
    "Dulces y chocolates": "Dulces",
    "Embutidos": "Embutidos",
    "Limpieza": "Limpieza",
    "Higiene básica": "Higiene",
    "Mascotas": "Mascotas",
    "Helados": "Helados",
    "Básicos domésticos": "Hogar",
    "Inventario previo": "Otros",
}


def _item(
    name: str,
    unit: str,
    price_cents: int,
    *,
    kind: str = "producto",
    category: str = "Productos",
    aliases: Iterable[str] = (),
    stock_milli: int = 12000,
    low_stock_milli: int = 5000,
    quick: bool = False,
    duration_minutes: int | None = None,
    unlimited_stock: bool | None = None,
    image_url: str | None = None,
) -> dict[str, Any]:
    """Normalize one template item. Services/dishes carry no inventory."""

    if unlimited_stock is None:
        unlimited_stock = kind != "producto"
    if unlimited_stock:
        stock_milli = 0
        low_stock_milli = 0
        quick = False
    return {
        "name": name,
        "unit": unit,
        "priceCents": int(price_cents),
        "kind": kind,
        "category": category,
        "aliases": list(aliases),
        "stockMilli": int(stock_milli),
        "lowStockMilli": int(low_stock_milli),
        "quick": bool(quick),
        "unlimitedStock": bool(unlimited_stock),
        "durationMinutes": duration_minutes,
        "imageUrl": image_url,
    }


# ---------------------------------------------------------------------------
# Tiendita: curated subset of the resource catalog
# ---------------------------------------------------------------------------
# Each entry: (código, nombre curado, unidad, precio demo, categoría de
# respaldo, aliases, stock, rápido, categoría forzada). Prices are replaced by
# the observed price in the CSV when the row has one.


def _tiendita_item(
    codigo: str,
    name: str,
    unit: str,
    demo_price_cents: int,
    category: str,
    aliases: Iterable[str],
    *,
    stock_milli: int = 12000,
    quick: bool = False,
    category_override: bool = False,
) -> dict[str, Any]:
    return {
        "codigo": codigo,
        "name": name,
        "unit": unit,
        "demoPriceCents": int(demo_price_cents),
        "category": category,
        "categoryOverride": bool(category_override),
        "aliases": list(aliases),
        "stockMilli": int(stock_milli),
        "quick": bool(quick),
    }


_TIENDITA_CURATED: tuple[dict[str, Any], ...] = (
    _tiendita_item("7501055320639", "Coca-Cola 600 ml (sin azúcar)", "pieza", 1800, "Bebidas", ["coca", "cocas", "coca cola", "refresco", "refrescos"], stock_milli=24000, quick=True),
    _tiendita_item("0003310536740", "Agua purificada 500 ml", "pieza", 1000, "Bebidas", ["agua", "agua purificada"], stock_milli=20000, quick=True),
    _tiendita_item("7500810029183", "Pan blanco Bimbo 620 g", "pieza", 4800, "Pan", ["pan", "pan blanco", "bimbo"], stock_milli=6000, quick=True),
    _tiendita_item("7501000111800", "Pan tostado clásico 210 g", "pieza", 3800, "Pan", ["pan tostado", "tostado"]),
    _tiendita_item("7503017439311", "Tostadas", "pieza", 2200, "Pan", ["tostada", "tostadas"], stock_milli=8000),
    _tiendita_item("0742832410908", "Tortillas de maíz (kg)", "kg", 2600, "Pan", ["tortilla", "tortillas", "maiz"], stock_milli=8000, quick=True),
    _tiendita_item("7500462841713", "Huevo fresco (kg)", "kg", 4500, "Lácteos", ["huevo", "huevos", "blanquillos"], stock_milli=10000, quick=True),
    _tiendita_item("0078742107530", "Leche entera 1 L", "pieza", 3100, "Lácteos", ["leche"], stock_milli=12000, quick=True),
    _tiendita_item("7501013610024", "Mantequilla sin sal 90 g", "pieza", 2990, "Lácteos", ["mantequilla"]),
    _tiendita_item("7501040082146", "Margarina sin sal 90 g", "pieza", 1490, "Lácteos", ["margarina"]),
    _tiendita_item("7501092112051", "Yogurt natural 1 kg", "pieza", 3800, "Lácteos", ["yogurt", "yogur"]),
    _tiendita_item("7501002203503", "Queso panela 400 g", "pieza", 5500, "Lácteos", ["queso", "queso panela"]),
    _tiendita_item("7501047700807", "Arroz súper extra 907 g", "pieza", 2000, "Abarrotes", ["arroz"], stock_milli=15000),
    _tiendita_item("7501047203445", "Frijol negro 907 g", "pieza", 3000, "Abarrotes", ["frijol", "frijoles"], stock_milli=15000),
    _tiendita_item("7501071308604", "Frijoles negros refritos 430 g", "pieza", 1825, "Abarrotes", ["frijoles refritos", "refritos"]),
    _tiendita_item("7501039120477", "Aceite de soya 946 ml", "pieza", 4200, "Abarrotes", ["aceite", "aceite de soya"], stock_milli=9000),
    _tiendita_item("7501404603123", "Harina de trigo 1 kg", "pieza", 2000, "Abarrotes", ["harina", "harina de trigo"], stock_milli=8000),
    _tiendita_item("7501045401423", "Atún en hojuelas 140 g", "pieza", 2050, "Abarrotes", ["atun", "atun en hojuelas"]),
    _tiendita_item("7501017003396", "Piña en almíbar 800 g", "pieza", 7200, "Abarrotes", ["pina", "pina en almibar"]),
    _tiendita_item("7501052474076", "Mermelada de fresa 470 g", "pieza", 4175, "Abarrotes", ["mermelada", "mermelada de fresa"]),
    _tiendita_item("7501047200734", "Haba pelada 500 g", "pieza", 6900, "Abarrotes", ["haba", "habas"]),
    _tiendita_item("7501439950018", "Sal de mesa 1 kg", "pieza", 1500, "Abarrotes", ["sal"], stock_milli=6000),
    _tiendita_item("7501003334329", "Aderezo de mayonesa 210 g", "pieza", 3200, "Abarrotes", ["mayonesa", "aderezo"]),
    _tiendita_item("7503008665729", "Mazapán", "pieza", 1200, "Dulces", ["mazapan"], stock_milli=10000),
    _tiendita_item("7501011167445", "Papas Sabritas 67 g", "pieza", 2200, "Botanas", ["papas", "sabritas", "papas fritas"], stock_milli=18000, quick=True),
    _tiendita_item("7502223776036", "Crema de cacahuate 425 g", "pieza", 7000, "Abarrotes", ["crema de cacahuate", "cacahuate"], category_override=True),
    _tiendita_item("7501057720345", "Salchicha vienesa 500 g", "pieza", 6090, "Embutidos", ["salchicha", "salchichas", "salchicha vienesa"]),
    _tiendita_item("7501026005688", "Jabón Zote", "pieza", 2300, "Limpieza", ["jabon", "zote", "jabon zote"], stock_milli=9000),
)

_TIENDITA_TASKS = (
    ("contar-inventario", "Contar inventario"),
    ("limpiar", "Limpiar"),
    ("revisar-caducidades", "Revisar caducidades"),
    ("acomodar-anaquel", "Acomodar anaquel"),
)


def _read_catalog_rows(path: Path, codes: set[str]) -> dict[str, dict[str, str]]:
    """Read only the curated rows of the (large) CSV, never the whole thing."""

    if not path.is_file():
        return {}
    rows: dict[str, dict[str, str]] = {}
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("codigo") or "").strip()
                if code in codes:
                    rows[code] = row
    except (OSError, csv.Error):
        return {}
    return rows


def _read_resumen(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _http_image_url(raw: str | None) -> str | None:
    """v3.1: only an http(s) URL from the resource CSV becomes an image.

    The curated rows carry an Open Food Facts image URL (CC BY-SA) in the
    'imagen' column; empty cells or anything that is not a real http(s) link
    stay as no image (NULL) so the app shows its category emoji fallback.
    """

    text = (raw or "").strip()
    if text.lower().startswith(("http://", "https://")):
        return text
    return None


def _observed_cents(raw: str | None) -> int | None:
    text = (raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if value <= 0:
        return None
    return int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@lru_cache(maxsize=4)
def _load_tiendita_catalog(directory: str) -> dict[str, Any]:
    base = Path(directory)
    codes = {entry["codigo"] for entry in _TIENDITA_CURATED}
    rows = _read_catalog_rows(base / CATALOG_FILE, codes)
    resumen = _read_resumen(base / RESUMEN_FILE)
    observed = 0
    matched = 0
    images = 0
    items: list[dict[str, Any]] = []
    for entry in _TIENDITA_CURATED:
        row = rows.get(entry["codigo"])
        price = entry["demoPriceCents"]
        category = entry["category"]
        image_url: str | None = None
        if row is not None:
            matched += 1
            observed_price = _observed_cents(row.get("precio_observado_mxn"))
            if observed_price is not None:
                price = observed_price
                observed += 1
            family = (row.get("familia_tiendita") or "").strip()
            if family and not entry["categoryOverride"]:
                category = _CATEGORY_BY_FAMILY.get(family, category)
            image_url = _http_image_url(row.get("imagen"))
            if image_url is not None:
                images += 1
        items.append(
            _item(
                entry["name"],
                entry["unit"],
                price,
                category=category,
                aliases=entry["aliases"],
                stock_milli=entry["stockMilli"],
                quick=entry["quick"],
                image_url=image_url,
            )
        )
    incluir_total = (
        resumen.get("catalogo", {}).get("decisiones", {}).get("incluir")
        if isinstance(resumen, dict)
        else None
    )
    return {
        "businessType": "tiendita",
        "items": items,
        "tasks": [{"key": key, "title": title} for key, title in _TIENDITA_TASKS],
        "source": {
            "directory": str(base),
            "catalogFile": CATALOG_FILE,
            "resumenFile": RESUMEN_FILE,
            "filesAvailable": bool(rows) or bool(resumen),
            "curatedItems": len(items),
            "matchedItems": matched,
            "observedPrices": observed,
            "imageUrls": images,
            "incluirTotal": incluir_total,
        },
    }


def tiendita_catalog(resources_dir: str | Path | None = None) -> dict[str, Any]:
    """Curated tiendita template, read from the resource folder when present."""

    directory = CATALOG_RESOURCES_DIR if resources_dir is None else Path(resources_dir)
    return _load_tiendita_catalog(str(directory))


# ---------------------------------------------------------------------------
# Other business types: 6-12 items and 3-5 fixed day tasks each
# ---------------------------------------------------------------------------

_OTHER_TEMPLATES: dict[str, dict[str, Any]] = {
    "tortilleria": {
        "items": [
            _item("Tortilla de maíz (kg)", "kg", 2600, category="Tortillas", aliases=["tortilla", "tortillas", "maiz"], stock_milli=40000, quick=True),
            _item("Tortilla de harina (kg)", "kg", 3200, category="Tortillas", aliases=["tortilla de harina", "harina"], stock_milli=15000),
            _item("Masa para tortillas (kg)", "kg", 1800, category="Tortillas", aliases=["masa", "masa de maiz"], stock_milli=20000),
            _item("Sopes", "pieza", 600, category="Antojitos", aliases=["sope", "sopes"], stock_milli=6000, quick=True),
            _item("Tlacoyos", "pieza", 700, category="Antojitos", aliases=["tlacoyo", "tlacoyos"], stock_milli=6000),
            _item("Quesadilla de comal", "pieza", 1500, category="Antojitos", aliases=["quesadilla", "quesadillas"], stock_milli=6000),
            _item("Gorditas", "pieza", 800, category="Antojitos", aliases=["gordita", "gorditas"], stock_milli=6000),
            _item("Tlayuda", "pieza", 3500, category="Antojitos", aliases=["tlayuda", "tlayudas"], stock_milli=4000),
        ],
        "tasks": [
            ("revisar-maquina", "Revisar la máquina"),
            ("limpiar-comal", "Limpiar el comal"),
            ("contar-costales", "Contar costales de maíz"),
            ("cuadrar-caja", "Cuadrar la caja"),
        ],
    },
    "taqueria": {
        "items": [
            _item("Taco al pastor", "pieza", 1500, kind="platillo", category="Tacos", aliases=["taco al pastor", "pastor", "taco de pastor"], duration_minutes=5, unlimited_stock=True),
            _item("Taco de suadero", "pieza", 1600, kind="platillo", category="Tacos", aliases=["suadero", "taco de suadero"], duration_minutes=5, unlimited_stock=True),
            _item("Taco de tripa", "pieza", 1700, kind="platillo", category="Tacos", aliases=["tripa", "taco de tripa"], duration_minutes=5, unlimited_stock=True),
            _item("Quesadilla de comal", "pieza", 2500, kind="platillo", category="Antojitos", aliases=["quesadilla", "quesadillas"], duration_minutes=8, unlimited_stock=True),
            _item("Gringa", "pieza", 3500, kind="platillo", category="Antojitos", aliases=["gringa", "gringas"], duration_minutes=10, unlimited_stock=True),
            _item("Refresco 600 ml", "pieza", 1800, category="Bebidas", aliases=["refresco", "refrescos", "coca"], stock_milli=12000),
            _item("Agua fresca 1 L", "pieza", 2000, kind="platillo", category="Bebidas", aliases=["agua fresca", "agua"], unlimited_stock=True),
            _item("Orden de tortillas", "pieza", 500, kind="platillo", category="Tacos", aliases=["tortillas", "orden de tortillas"], unlimited_stock=True),
        ],
        "tasks": [
            ("preparar-salsas", "Preparar salsa y tortillas"),
            ("limpiar-plancha", "Limpiar la plancha"),
            ("revisar-gas", "Revisar el gas"),
            ("contar-inventario", "Contar inventario"),
        ],
    },
    "comida-corrida": {
        "items": [
            _item("Comida corrida", "servicio", 8500, kind="platillo", category="Comida", aliases=["comida corrida", "corrida"], duration_minutes=30, unlimited_stock=True),
            _item("Sopa del día", "servicio", 3500, kind="platillo", category="Comida", aliases=["sopa", "sopa del dia"], unlimited_stock=True),
            _item("Guisado del día", "servicio", 4500, kind="platillo", category="Comida", aliases=["guisado", "guisado del dia"], unlimited_stock=True),
            _item("Tortillas", "pieza", 500, kind="platillo", category="Comida", aliases=["tortilla", "tortillas", "orden de tortillas"], unlimited_stock=True),
            _item("Agua fresca 1 L", "pieza", 2000, kind="platillo", category="Bebidas", aliases=["agua fresca", "agua"], unlimited_stock=True),
            _item("Postre del día", "servicio", 2500, kind="platillo", category="Postres", aliases=["postre", "postre del dia"], unlimited_stock=True),
            _item("Café de olla", "pieza", 1500, kind="platillo", category="Bebidas", aliases=["cafe", "cafe de olla"], unlimited_stock=True),
        ],
        "tasks": [
            ("cocinar-guiso", "Cocinar el guisado del día"),
            ("limpiar-mesas", "Limpiar mesas"),
            ("contar-inventario", "Contar inventario"),
            ("revisar-insumos", "Revisar insumos"),
        ],
    },
    "peluqueria": {
        "items": [
            _item("Corte de cabello", "servicio", 15000, kind="servicio", category="Servicios", aliases=["corte", "cortes", "corte de pelo", "corte de cabello"], duration_minutes=30),
            _item("Corte de niño", "servicio", 12000, kind="servicio", category="Servicios", aliases=["corte de nino", "corte para nino"], duration_minutes=30),
            _item("Arreglo de barba", "servicio", 8000, kind="servicio", category="Servicios", aliases=["barba", "arreglo de barba"], duration_minutes=20),
            _item("Corte y barba", "combo", 20000, kind="servicio", category="Combos", aliases=["corte y barba", "combo corte y barba"], duration_minutes=45),
            _item("Tinte", "servicio", 35000, kind="servicio", category="Servicios", aliases=["tinte", "tintes"], duration_minutes=90),
            _item("Peinado", "servicio", 10000, kind="servicio", category="Servicios", aliases=["peinado", "peinados"], duration_minutes=30),
            _item("Lavado de cabello", "servicio", 5000, kind="servicio", category="Servicios", aliases=["lavado", "lavado de cabello"], duration_minutes=15),
            _item("Depilación de cejas", "servicio", 4000, kind="servicio", category="Servicios", aliases=["cejas", "depilacion de cejas"], duration_minutes=15),
        ],
        "tasks": [
            ("preparar-estacion", "Preparar estación y desinfectar"),
            ("desinfectar-herramientas", "Desinfectar herramientas"),
            ("contar-productos", "Contar productos de venta"),
            ("revisar-agenda", "Revisar agenda del día"),
        ],
    },
    "estetica": {
        "items": [
            _item("Manicure", "servicio", 12000, kind="servicio", category="Uñas", aliases=["manicure", "manicura", "manicures", "sesion de manicure"], duration_minutes=45),
            _item("Pedicure", "servicio", 15000, kind="servicio", category="Uñas", aliases=["pedicure", "pedicura", "sesion de pedicure"], duration_minutes=60),
            _item("Uñas acrílicas", "servicio", 25000, kind="servicio", category="Uñas", aliases=["unas acrilicas", "acrilicas", "unas", "sesion de unas", "sesion"], duration_minutes=90),
            _item("Gelish", "servicio", 18000, kind="servicio", category="Uñas", aliases=["gelish", "gel semipermanente"], duration_minutes=60),
            _item("Depilación de cejas", "servicio", 5000, kind="servicio", category="Cejas", aliases=["cejas", "depilacion de cejas"], duration_minutes=20),
            _item("Maquillaje", "servicio", 20000, kind="servicio", category="Maquillaje", aliases=["maquillaje", "makeup"], duration_minutes=60),
            _item("Masaje facial", "servicio", 22000, kind="servicio", category="Facial", aliases=["masaje facial", "facial"], duration_minutes=45),
            _item("Depilación de piernas", "servicio", 18000, kind="servicio", category="Depilación", aliases=["depilacion de piernas"], duration_minutes=45),
        ],
        "tasks": [
            ("desinfectar-herramientas", "Desinfectar herramientas"),
            ("preparar-estacion", "Preparar estación y desinfectar"),
            ("contar-esmaltes", "Contar esmaltes y productos"),
            ("revisar-citas", "Revisar citas del día"),
        ],
    },
    "fondita": {
        "items": [
            _item("Platillo del día", "servicio", 7000, kind="platillo", category="Comida", aliases=["platillo del dia", "comida del dia"], unlimited_stock=True),
            _item("Pozole", "pieza", 9000, kind="platillo", category="Comida", aliases=["pozole"], unlimited_stock=True),
            _item("Tamales", "pieza", 2500, kind="platillo", category="Comida", aliases=["tamal", "tamales"], unlimited_stock=True),
            _item("Sopa del día", "servicio", 3000, kind="platillo", category="Comida", aliases=["sopa", "sopa del dia"], unlimited_stock=True),
            _item("Atole", "pieza", 1500, kind="platillo", category="Bebidas", aliases=["atole"], unlimited_stock=True),
            _item("Café de olla", "pieza", 1200, kind="platillo", category="Bebidas", aliases=["cafe", "cafe de olla"], unlimited_stock=True),
            _item("Agua fresca 1 L", "pieza", 2000, kind="platillo", category="Bebidas", aliases=["agua fresca", "agua"], unlimited_stock=True),
        ],
        "tasks": [
            ("cocinar-guiso", "Cocinar el guiso del día"),
            ("limpiar-mesas", "Limpiar mesas y cocina"),
            ("contar-inventario", "Contar inventario"),
            ("revisar-insumos", "Revisar insumos"),
        ],
    },
    "otro": {
        "items": [
            _item("Producto de la casa", "pieza", 5000, category="Productos", aliases=["producto de la casa"], stock_milli=10000),
            _item("Producto de temporada", "pieza", 6000, category="Productos", aliases=["producto de temporada"], stock_milli=8000),
            _item("Servicio básico", "servicio", 5000, kind="servicio", category="Servicios", aliases=["servicio", "servicio basico"], duration_minutes=30),
            _item("Servicio express", "servicio", 7000, kind="servicio", category="Servicios", aliases=["servicio express", "express"], duration_minutes=15),
            _item("Platillo del día", "servicio", 8000, kind="platillo", category="Comida", aliases=["platillo del dia", "platillo"], unlimited_stock=True),
            _item("Combo familiar", "combo", 15000, category="Combos", aliases=["combo", "combo familiar"], unlimited_stock=True),
        ],
        "tasks": [
            ("contar-inventario", "Contar inventario"),
            ("limpiar", "Limpiar"),
            ("abrir-caja", "Abrir y cerrar caja"),
        ],
    },
}


def canonical_business_type(raw: str | None) -> str | None:
    """Normalize the business type; returns None for unknown values."""

    if raw is None:
        return None
    value = raw.strip().lower()
    if not value:
        return None
    for accent, plain in (
        ("á", "a"),
        ("é", "e"),
        ("í", "i"),
        ("ó", "o"),
        ("ú", "u"),
        ("ü", "u"),
        ("ñ", "n"),
    ):
        value = value.replace(accent, plain)
    value = value.replace("_", "-").replace("/", "-").replace(" ", "-")
    while "--" in value:
        value = value.replace("--", "-")
    value = value.strip("-")
    if value in BUSINESS_TYPES:
        return value
    return BUSINESS_TYPE_ALIASES.get(value)


def business_template(
    business_type: str | None,
    resources_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return {businessType, items, tasks, source} or None if unknown."""

    canonical = canonical_business_type(business_type)
    if canonical is None:
        return None
    if canonical == "tiendita":
        return tiendita_catalog(resources_dir)
    template = _OTHER_TEMPLATES[canonical]
    return {
        "businessType": canonical,
        "items": [dict(item) for item in template["items"]],
        "tasks": [
            {"key": key, "title": title} for key, title in template["tasks"]
        ],
        "source": {
            "directory": None,
            "catalogFile": None,
            "resumenFile": None,
            "filesAvailable": False,
            "curatedItems": len(template["items"]),
            "matchedItems": len(template["items"]),
            "observedPrices": 0,
            "imageUrls": 0,
            "incluirTotal": None,
        },
    }
