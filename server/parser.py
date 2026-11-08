"""Local Spanish text parser for the Abarpay cart.

The parser always works without OpenAI. It understands pieces, kilograms,
grams, fractions, decimals and the usual Mexican shorthand used by the demo
(`medio kilo`, `1/2 kg`, `250 gramos`, `dos coches`). Prices are never taken
from the text: the caller passes catalog rows and the returned item totals are
computed from the database price.
"""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

_WORD_NUMBERS: dict[str, Decimal] = {
    "media docena": Decimal(6),
    "docena": Decimal(12),
    "tres cuartos": Decimal("0.75"),
    "un cuarto": Decimal("0.25"),
    "cuarto": Decimal("0.25"),
    "medio": Decimal("0.5"),
    "media": Decimal("0.5"),
    "un": Decimal(1),
    "una": Decimal(1),
    "uno": Decimal(1),
    "unas": Decimal(1),
    "unos": Decimal(1),
    "dos": Decimal(2),
    "tres": Decimal(3),
    "cuatro": Decimal(4),
    "cinco": Decimal(5),
    "seis": Decimal(6),
    "siete": Decimal(7),
    "ocho": Decimal(8),
    "nueve": Decimal(9),
    "diez": Decimal(10),
}

# Longest first so "media docena" wins over "media" and "un cuarto" over "un".
_WORD_PATTERN = "|".join(
    re.escape(word) for word in sorted(_WORD_NUMBERS, key=len, reverse=True)
)

_UNIT_GROUP = (
    r"kilos?|kilogramos?|kg|gramos?|grs?|g|miligramos?|mili|"
    r"piezas?|pzas?|pza|unidades?|litros?|l"
)
_UNIT_RE = re.compile(rf"^(?P<unit>{_UNIT_GROUP})\b", re.IGNORECASE)
_NUMBER_RE = re.compile(
    r"^(?P<number>\d+/\d+|\d+(?:[.,]\d+)?(?:\s+\d+/\d+)?)\s*(?P<unit>"
    + _UNIT_GROUP
    + r")?\b\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_WORD_RE = re.compile(
    rf"^(?P<word>{_WORD_PATTERN})\b\s*(?:de\s+)?(?P<unit>{_UNIT_GROUP})?\b\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"\s*(?:,(?!\d)|;|\+|(?<!\w)(?:y|mas|con)(?!\w))\s*", re.IGNORECASE)
_CONNECTOR_RE = re.compile(r"^(?:de|del|la|el|los|las)\s+", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, strip accents and collapse whitespace for matching."""

    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def line_total_cents(unit_price_cents: int, qty_milli: int) -> int:
    """round(unitPriceCents * qtyMilli / 1000), half up for positive money."""

    return (int(unit_price_cents) * int(qty_milli) + 500) // 1000


def _decimal_number(raw: str) -> Decimal | None:
    raw = raw.strip().replace(",", ".")
    try:
        if " " in raw:
            whole, fraction = raw.split(None, 1)
            return Decimal(whole) + _fraction(fraction)
        return _fraction(raw)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def _fraction(raw: str) -> Decimal:
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        if int(denominator) == 0:
            raise ZeroDivisionError
        return Decimal(int(numerator)) / Decimal(int(denominator))
    return Decimal(raw)


def _unit_kind(unit: str | None) -> str | None:
    if not unit:
        return None
    unit = normalize(unit)
    if unit.startswith("kilo") or unit == "kg":
        return "kg"
    if unit in {"g", "gr", "grs", "gramo", "gramos"}:
        return "g"
    if unit.startswith("mili"):
        return "milli"
    if unit.startswith(("pieza", "pza", "unidad", "litro")) or unit == "l":
        return "count"
    return None


def _qty_from_parts(value: Decimal, unit_kind: str | None) -> int:
    if unit_kind == "kg":
        return int((value * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if unit_kind in {"g", "milli"}:
        return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    # No explicit unit: one "unit" of the product (one piece or one kg).
    return int((value * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _split_quantity(chunk: str) -> tuple[int, str, bool]:
    """Return (qty_milli, rest, had_quantity) for one text chunk."""

    chunk = chunk.strip()
    if not chunk:
        return 1000, "", False

    match = _NUMBER_RE.match(chunk)
    if match:
        value = _decimal_number(match.group("number"))
        if value is not None and value > 0:
            unit = match.group("unit")
            rest = match.group("rest").strip()
            return _qty_from_parts(value, _unit_kind(unit)), rest, True

    match = _WORD_RE.match(chunk)
    if match:
        word = normalize(match.group("word"))
        value = _WORD_NUMBERS.get(word)
        if value is not None:
            unit = match.group("unit")
            rest = match.group("rest").strip()
            # "un cuarto de kilo de tortillas" leaves "de kilo..." only if
            # the optional unit was not consumed; normalize that away.
            if not unit:
                second = _UNIT_RE.match(rest)
                if second:
                    unit = second.group("unit")
                    rest = rest[second.end() :].strip()
            return _qty_from_parts(value, _unit_kind(unit)), rest, True

    return 1000, chunk, False


def _catalog_alias_index(catalog: Iterable[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    aliases: list[tuple[str, dict[str, Any]]] = []
    for product in catalog:
        names = [product.get("name", "")]
        raw_aliases = product.get("aliases") or []
        if isinstance(raw_aliases, str):
            try:
                raw_aliases = json.loads(raw_aliases)
            except (TypeError, ValueError):
                raw_aliases = []
        if isinstance(raw_aliases, list):
            names.extend(str(alias) for alias in raw_aliases)
        for name in names:
            normalized = normalize(str(name))
            if normalized:
                aliases.append((normalized, product))
    # Longest alias wins, so "coca cola" beats "coca" and "pan bimbo" beats "pan".
    aliases.sort(key=lambda pair: len(pair[0]), reverse=True)
    return aliases


def _match_product(text: str, aliases: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    for alias, product in aliases:
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, text):
            return product
    return None


def _clean_rest(rest: str) -> str:
    rest = _CONNECTOR_RE.sub("", rest.strip())
    return rest.strip(" .")


def parse_text(text: str, catalog: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Parse free text against catalog rows loaded from SQLite.

    Catalog rows need at least `id`, `name`, `aliases`, `unit`,
    `price_cents`.
    """

    normalized = normalize(text or "")
    chunks = [chunk.strip() for chunk in _SPLIT_RE.split(normalized) if chunk.strip()]
    aliases = _catalog_alias_index(catalog)

    pairs: list[tuple[int, int]] = []
    unmatched: list[str] = []

    for chunk in chunks:
        qty_milli, rest, had_quantity = _split_quantity(chunk)
        rest = _clean_rest(rest)
        product = _match_product(rest, aliases) if rest else None
        if product is None and rest != chunk:
            # Be forgiving if the quantity parser consumed a word that is also
            # part of the product alias ("dos cocas" is already covered, but
            # this helps with unusual phrasings).
            product = _match_product(chunk, aliases)
        if product is None or qty_milli <= 0:
            label = rest or chunk
            if label:
                unmatched.append(label)
            continue
        pairs.append((int(product["id"]), qty_milli))

    by_id = {int(product["id"]): product for product in catalog}
    merged: dict[int, int] = {}
    order: list[int] = []
    for product_id, qty_milli in pairs:
        if product_id not in merged:
            order.append(product_id)
            merged[product_id] = 0
        merged[product_id] += qty_milli

    items: list[dict[str, Any]] = []
    for product_id in order:
        product = by_id[product_id]
        qty_milli = merged[product_id]
        unit_price = int(product["price_cents"])
        items.append(
            {
                "productId": product_id,
                "name": product["name"],
                "qtyMilli": qty_milli,
                "unit": product["unit"],
                "unitPriceCents": unit_price,
                "lineTotalCents": line_total_cents(unit_price, qty_milli),
            }
        )

    return {"items": items, "unmatched": unmatched, "engine": "local"}
