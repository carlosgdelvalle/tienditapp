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


# ---------------------------------------------------------------------------
# Inventory count parsing (v2)
# ---------------------------------------------------------------------------
# "coca colas de 600, 4, 5, 6… 12 piezas" -> Coca-Cola 600 ml with 12 pieces.
# The last explicit number for a product wins, numbers are spoken or written,
# pieces and kilograms both use qtyMilli (1000 = 1 pieza or 1 kg), and a
# product mentioned without a quantity comes back with qtyMilli = null so the
# app can ask for it.

_COUNT_WORD_VALUES: dict[str, Decimal] = {
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
    "veinte": Decimal(20),
}

_COUNT_SMALL_WORDS: dict[int, str] = {
    2: "dos",
    3: "tres",
    4: "cuatro",
    5: "cinco",
    6: "seis",
    7: "siete",
    8: "ocho",
    9: "nueve",
    10: "diez",
    11: "once",
    12: "doce",
    13: "trece",
    14: "catorce",
    15: "quince",
    16: "dieciseis",
    17: "diecisiete",
    18: "dieciocho",
    19: "diecinueve",
}

for _number, _word in _COUNT_SMALL_WORDS.items():
    _COUNT_WORD_VALUES[_word] = Decimal(_number)

for _number, _word in (
    (21, "veintiuno"),
    (22, "veintidos"),
    (23, "veintitres"),
    (24, "veinticuatro"),
    (25, "veinticinco"),
    (26, "veintiseis"),
    (27, "veintisiete"),
    (28, "veintiocho"),
    (29, "veintinueve"),
):
    _COUNT_WORD_VALUES[_word] = Decimal(_number)

_COUNT_TENS = (
    (30, "treinta"),
    (40, "cuarenta"),
    (50, "cincuenta"),
    (60, "sesenta"),
    (70, "setenta"),
    (80, "ochenta"),
    (90, "noventa"),
)

for _tens_number, _tens_word in _COUNT_TENS:
    _COUNT_WORD_VALUES[_tens_word] = Decimal(_tens_number)
    for _unit_number in range(1, 10):
        _COUNT_WORD_VALUES[
            f"{_tens_word} y {_COUNT_SMALL_WORDS.get(_unit_number, 'uno')}"
        ] = Decimal(_tens_number + _unit_number)

_COUNT_WORD_VALUES["cien"] = Decimal(100)
_COUNT_WORD_VALUES["ciento"] = Decimal(100)

_COUNT_NUMBER_ALTERNATION = "|".join(
    re.escape(word) for word in sorted(_COUNT_WORD_VALUES, key=len, reverse=True)
)
_COUNT_NUMBER_RE = re.compile(
    rf"(?<![a-z0-9])(?P<number>\d+(?:[.,]\d+)?|{_COUNT_NUMBER_ALTERNATION})(?![a-z0-9])",
    re.IGNORECASE,
)
# No leading "^": the regex is matched with a start position on the full text.
_COUNT_UNIT_AFTER_RE = re.compile(
    r"\s*(?:de\s+)?(?P<unit>kilos?|kilogramos?|kg|gramos?|grs?|g|"
    r"piezas?|pzas?|pza|unidades?)\b",
    re.IGNORECASE,
)
_COUNT_UNIT_BEFORE_RE = re.compile(
    r"(?P<unit>kilos?|kilogramos?|kg|gramos?|grs?|g|piezas?|pzas?|pza|unidades?)"
    r"\s+(?:(?:y|de)\s+)?$",
    re.IGNORECASE,
)
_COUNT_SIZE_UNIT_RE = re.compile(r"^(?:ml|mililitros?|litros?|l)\b", re.IGNORECASE)


def _count_unit_kind(unit: str | None) -> str | None:
    if not unit:
        return None
    normalized = normalize(unit)
    if normalized in {"kilo", "kilos", "kilogramo", "kilogramos", "kg"}:
        return "kg"
    if normalized in {"gramo", "gramos", "g", "gr", "grs"}:
        return "g"
    if normalized.startswith(("pieza", "pza", "unidad")):
        return "pieza"
    return None


def _count_number_value(raw: str) -> Decimal | None:
    raw = raw.strip()
    if not raw:
        return None
    if raw[0].isdigit():
        try:
            return Decimal(raw.replace(",", "."))
        except InvalidOperation:
            return None
    return _COUNT_WORD_VALUES.get(normalize(raw))


def _count_qty_milli(value: Decimal, unit_kind: str | None) -> int:
    if unit_kind == "g":
        return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    # One piece and one kilogram both map to 1000 milli.
    return int((value * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _is_count_size_reference(text: str, start: int, end: int) -> bool:
    """Skip package sizes such as "de 600" or "600 ml" in "coca colas de 600"."""

    before = text[:start].rstrip()
    after = text[end:].lstrip()
    if _COUNT_SIZE_UNIT_RE.match(after):
        return True
    if re.search(r"\bde$", before) and not _COUNT_UNIT_AFTER_RE.match(after):
        return (
            after == ""
            or after[0] in ",;.…"
            or after.startswith(("y ", "..."))
        )
    return False


def _count_product_mentions(
    text: str, aliases: list[tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    occupied = [False] * len(text)
    mentions: list[dict[str, Any]] = []
    for alias, product in aliases:
        # Plural aliases: "coca cola" also matches "coca colas" in a count.
        pattern = re.compile(
            rf"(?<![a-z0-9]){re.escape(alias)}(?:es|s)?(?![a-z0-9])"
        )
        for match in pattern.finditer(text):
            if any(occupied[match.start() : match.end()]):
                continue
            for index in range(match.start(), match.end()):
                occupied[index] = True
            mentions.append(
                {"product": product, "start": match.start(), "end": match.end()}
            )
    mentions.sort(key=lambda item: item["start"])
    return mentions


def _count_unit_after(text: str, position: int) -> str | None:
    match = _COUNT_UNIT_AFTER_RE.match(text, position)
    if match is None:
        return None
    return _count_unit_kind(match.group("unit"))


def _count_unit_before(text: str, position: int) -> str | None:
    match = _COUNT_UNIT_BEFORE_RE.search(text[:position])
    if match is None:
        return None
    return _count_unit_kind(match.group("unit"))


def parse_count(text: str, catalog: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Parse an inventory count phrase against the catalog.

    Returns {"items": [{productId, name, qtyMilli, unit}], "note": str | None}.
    qtyMilli is null when the phrase names a product without a quantity.
    """

    normalized = normalize(text or "")
    aliases = _catalog_alias_index(catalog)
    mentions = _count_product_mentions(normalized, aliases)

    assigned: dict[int, list[dict[str, Any]]] = {}
    for match in _COUNT_NUMBER_RE.finditer(normalized):
        value = _count_number_value(match.group("number"))
        if value is None or value <= 0:
            continue
        if _is_count_size_reference(normalized, match.start(), match.end()):
            continue
        best_index: int | None = None
        best_distance: int | None = None
        for index, mention in enumerate(mentions):
            if match.end() <= mention["start"]:
                distance = mention["start"] - match.end()
            elif match.start() >= mention["end"]:
                distance = match.start() - mention["end"]
            else:
                distance = 0
            if best_distance is None or distance < best_distance:
                best_index = index
                best_distance = distance
            elif distance == best_distance and mention["start"] >= match.end():
                # Tie: a number right before a product belongs to that product
                # ("tres cocas dos sabritas" -> 3 cocas, 2 sabritas).
                if best_index is None or mentions[best_index]["start"] < match.end():
                    best_index = index
        if best_index is not None:
            assigned.setdefault(best_index, []).append(
                {"value": value, "end": match.end()}
            )

    grouped: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for index, mention in enumerate(mentions):
        product = mention["product"]
        product_id = int(product["id"])
        if product_id not in grouped:
            grouped[product_id] = {"product": product, "qtyMilli": None}
            order.append(product_id)
        # The last explicit number for this mention wins.
        for token in assigned.get(index, []):
            unit_kind = _count_unit_after(normalized, token["end"])
            if unit_kind is None:
                unit_kind = _count_unit_before(normalized, token["end"])
            grouped[product_id]["qtyMilli"] = _count_qty_milli(
                token["value"], unit_kind
            )

    items: list[dict[str, Any]] = []
    for product_id in order:
        product = grouped[product_id]["product"]
        items.append(
            {
                "productId": product_id,
                "name": product.get("name", ""),
                "qtyMilli": grouped[product_id]["qtyMilli"],
                "unit": product.get("unit") or "pieza",
            }
        )

    missing = [item["name"] for item in items if item["qtyMilli"] is None]
    if not items:
        note: str | None = "No reconocí ningún producto. Intenta de nuevo."
    elif missing:
        note = "Falta la cantidad de " + ", ".join(missing) + ". Confirma la cantidad."
    else:
        note = None
    return {"items": items, "note": note}
