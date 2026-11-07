"""Convierte una venta dictada o escrita en un carrito del catálogo.

Con OPENAI_API_KEY usa OpenAI con salida estructurada: el modelo solo elige productId
de la lista que recibe y la cantidad. Los precios siempre salen de la base de datos.
Sin key, usa un intérprete local (palabras y alias) y lo reporta como engine="local".
"""
import json
import os
import re
import unicodedata

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # confirmar el ID con los mentores

NUMBERS = {
    "un": 1, "una": 1, "uno": 1, "unas": 1, "unos": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "media docena": 6,
    "docena": 12,
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _catalog_rows(conn):
    return [dict(r) for r in conn.execute("SELECT id, name, aliases, price_cents FROM products")]


def _to_items(pairs, catalog):
    by_id = {p["id"]: p for p in catalog}
    merged: dict[int, int] = {}
    for pid, qty in pairs:
        if pid in by_id and qty > 0:
            merged[pid] = merged.get(pid, 0) + qty
    return [
        {"productId": pid, "name": by_id[pid]["name"], "qty": q, "unitPriceCents": by_id[pid]["price_cents"]}
        for pid, q in merged.items()
    ]


def parse_local(text: str, catalog: list[dict]) -> dict:
    chunks = [c.strip() for c in re.split(r",|\by\b|\bmas\b|\bmás\b|\+", _norm(text)) if c.strip()]
    pairs, unmatched = [], []
    for chunk in chunks:
        qty = 1
        m = re.match(r"^(\d+)\s+(.*)$", chunk)
        if m:
            qty, chunk = int(m.group(1)), m.group(2)
        else:
            for word, n in sorted(NUMBERS.items(), key=lambda kv: -len(kv[0])):
                if chunk.startswith(word + " ") or chunk == word:
                    qty, chunk = n, chunk[len(word):].strip()
                    break
        best = None
        for p in catalog:
            names = [_norm(p["name"])] + [_norm(a) for a in json.loads(p["aliases"])]
            for a in names:
                if re.search(rf"\b{re.escape(a)}\b", chunk) and (best is None or len(a) > best[1]):
                    best = (p["id"], len(a))
        if best:
            pairs.append((best[0], qty))
        elif chunk:
            unmatched.append(chunk)
    return {"items": _to_items(pairs, catalog), "unmatched": unmatched, "engine": "local"}


def parse_openai(text: str, catalog: list[dict]) -> dict:
    from openai import OpenAI

    client = OpenAI()
    listing = [{"productId": p["id"], "name": p["name"], "aliases": json.loads(p["aliases"])} for p in catalog]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"productId": {"type": "integer"}, "qty": {"type": "integer"}},
                "required": ["productId", "qty"]}},
            "unmatched": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["items", "unmatched"],
    }
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {"name": "carrito", "schema": schema, "strict": True}},
        messages=[
            {"role": "system", "content": (
                "Eres la caja de una tiendita mexicana. Convierte lo que dicta el empleado en un carrito. "
                "Usa SOLO productId de este catálogo. Si un producto no está o es ambiguo, ponlo en unmatched "
                "con las palabras del empleado. No inventes productos ni precios.\nCatálogo: "
                + json.dumps(listing, ensure_ascii=False))},
            {"role": "user", "content": text},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    pairs = [(i["productId"], i["qty"]) for i in data.get("items", [])]
    return {"items": _to_items(pairs, catalog), "unmatched": data.get("unmatched", []), "engine": "openai"}


def parse_cart(conn, text: str) -> dict:
    catalog = _catalog_rows(conn)
    if os.getenv("OPENAI_API_KEY"):
        try:
            return parse_openai(text, catalog)
        except Exception as e:  # la venta no se cae si la IA falla: se avisa y se usa el local
            result = parse_local(text, catalog)
            result["engine"] = "local"
            result["warning"] = f"OpenAI no respondió ({type(e).__name__}); se usó el intérprete local"
            return result
    return parse_local(text, catalog)


class VisionUnavailable(Exception):
    """No hay OPENAI_API_KEY: el reconocimiento por foto no está disponible."""


def parse_photo(conn, image_b64: str) -> dict:
    """Foto del mostrador → carrito. Solo con OpenAI; sin key no se inventa nada."""
    if not os.getenv("OPENAI_API_KEY"):
        raise VisionUnavailable("Falta OPENAI_API_KEY para reconocer productos por foto")
    from openai import OpenAI

    catalog = _catalog_rows(conn)
    listing = [{"productId": p["id"], "name": p["name"]} for p in catalog]
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "items": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"productId": {"type": "integer"}, "qty": {"type": "integer"}},
                "required": ["productId", "qty"]}},
            "unmatched": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["items", "unmatched"],
    }
    resp = OpenAI().chat.completions.create(
        model=os.getenv("OPENAI_VISION_MODEL", OPENAI_MODEL),
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {"name": "carrito", "schema": schema, "strict": True}},
        messages=[
            {"role": "system", "content": (
                "Eres la caja de una tiendita mexicana. Identifica los productos visibles en la foto del mostrador "
                "y cuántos hay de cada uno. Usa SOLO productId de este catálogo; lo que no reconozcas con seguridad "
                "va a unmatched. No inventes productos ni precios.\nCatálogo: " + json.dumps(listing, ensure_ascii=False))},
            {"role": "user", "content": [
                {"type": "text", "text": "¿Qué productos hay en el mostrador?"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_b64}},
            ]},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    pairs = [(i["productId"], i["qty"]) for i in data.get("items", [])]
    return {"items": _to_items(pairs, catalog), "unmatched": data.get("unmatched", []), "engine": "openai-vision"}
