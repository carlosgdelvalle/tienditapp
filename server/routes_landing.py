"""FastAPI router for the public landing page (pre-launch, F-12).

Serves the three CTA destinations required by docs/produccion/06-landing-y-comercial.md:

  GET /empezar      honest waiting-list state (self-service sign-up not yet open)
  GET /entrar       owner QR access challenge start (design; PIN console today)
  GET /apk-piloto   pilot APK status (unavailable; NEVER serves a file)

register(app) is the only wiring this module needs. It is added in
server/main.py next to the other register_* calls in create_app:

    from .routes_landing import register as register_landing_routes
    ...
    register_landing_routes(app)

The coordinator also points the root route at server/static/landing.html by
replacing the / -> /console redirect in server/main.py with
routes_landing.landing_page_response(request) (see the helper at the bottom).

Truthfulness rules (06 / d3-comercial) are honored exactly:

* The pilot APK is never served as a file. There is no signed, hashed build
  yet, so /apk-piloto returns only the "unavailable" state and an interest
  CTA. No temporary URL, debug file, or unsigned/hash-less binary is ever
  returned from this module.
* /empezar does not present self-service sign-up as available; it shows an
  honest waiting list and records interest (in memory, SIMULADO) using only
  permitted attribution fields. No email, name, phone, CLABE or token is
  collected.
* /entrar starts the QR access challenge (F-11) but labels the approval flow
  as "in preparation" and points to the working owner console (/console, PIN
  today) rather than simulating a QR session that does not exist yet.
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Interest types accepted by /empezar and recorded by /api/landing/interest.
# Each maps a commercial interest (not a plan activation or revenue).
INTEREST_LABELS: dict[str, str] = {
    "": "Empezar gratis",
    "apk": "Solicitar el APK piloto",
    "control": "Me interesa Control",
    "formalizacion": "Me interesa el piloto (Formalización)",
    "dossier": "Me interesa el expediente (dossier financiero)",
    "reposicion": "Me interesa el piloto (reposición)",
}

# UTM keys considered permitted for attribution. Nothing else is stored.
PERMITTED_UTMS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")

# Pilot APK metadata. Every field is explicitly unavailable until a signed,
# hashed build exists. None of these fields is ever served as a file.
APK_PILOT: dict[str, Any] = {
    "available": False,
    "version": None,
    "version_code": None,
    "build_date": None,
    "source_revision": None,
    "sha256": None,
    "signature": None,
    "min_api": None,
    "notes": None,
}

# In-memory interest ledger (SIMULADO). Persisted nowhere and never used to
# compute revenue. Only permitted attribution fields are stored.
_INTEREST_LEDGER: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# HTML shell (small, accessible, consistent with the landing page)
# ---------------------------------------------------------------------------

_SHELL_CSS = """
:root{--ink:#16202b;--ink-soft:#3a4753;--bg:#fff;--bg-soft:#f4f6f8;
--line:#d7dde3;--brand:#0b6e4f;--brand-dark:#085239;--muted:#57616c;
--warn-bg:#fff6e5;--warn-line:#e0b25c;--warn-ink:#6b4a00;--focus:#1f6fd0;--radius:10px;}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
color:var(--ink);background:var(--bg);font-size:1rem;line-height:1.6;
-webkit-font-smoothing:antialiased}
a{color:var(--brand-dark)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:3px}
.wrap{max-width:780px;margin:0 auto;padding:2rem 1rem 3rem}
.skip-link{position:absolute;left:0;top:-3rem;background:var(--ink);color:#fff;
padding:.65rem 1rem;z-index:100;text-decoration:none;font-weight:600}
.skip-link:focus{top:0}
header.site{background:var(--bg);border-bottom:1px solid var(--line)}
header.site .nav{max-width:780px;margin:0 auto;padding:.9rem 1rem;display:flex;
align-items:center;gap:.75rem;min-height:3.5rem}
.brand{font-weight:800;font-size:1.15rem;color:var(--ink);text-decoration:none;
margin-right:auto;display:inline-flex;align-items:center;gap:.5rem}
.brand .mark{display:inline-flex;align-items:center;justify-content:center;
width:1.7rem;height:1.7rem;border-radius:6px;background:var(--brand);color:#fff;
font-weight:800}
h1{font-size:clamp(1.6rem,4vw,2.2rem);line-height:1.15;margin:0 0 .75rem}
p.lede{color:var(--ink-soft);font-size:1.06rem;margin:0 0 1.25rem;max-width:40rem}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;
min-height:3rem;padding:.75rem 1.25rem;border-radius:var(--radius);font-size:1rem;
font-weight:700;text-decoration:none;border:1.5px solid transparent;cursor:pointer}
.btn-primary{background:var(--brand);color:#fff}
.btn-primary:hover{background:var(--brand-dark);color:#fff}
.btn-secondary{background:#fff;color:var(--brand-dark);border-color:var(--brand)}
.btn-secondary:hover{background:var(--bg-soft)}
.note{border-left:3px solid var(--brand);background:#eef6f1;padding:.75rem 1rem;
border-radius:0 var(--radius) var(--radius) 0;color:var(--ink-soft);font-size:.95rem;margin:1rem 0}
.note-warn{border-left-color:var(--warn-line);background:var(--warn-bg)}
.box{border:1px solid var(--line);border-radius:var(--radius);background:#fff;
padding:1.25rem 1.2rem;margin:1rem 0}
.box.unavailable{background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn-ink);font-weight:600}
label{display:block;font-weight:700;margin:.75rem 0 .3rem}
.tag{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:.04em;
text-transform:uppercase;color:#6b4a00;background:var(--warn-bg);border:1px solid var(--warn-line);
border-radius:5px;padding:.1rem .45rem}
.code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:1.5rem;
font-weight:800;letter-spacing:.2em;background:var(--bg-soft);border:1px dashed var(--ink-soft);
border-radius:8px;padding:.6rem 1rem;display:inline-block}
.muted{color:var(--muted);font-size:.9rem}
.ul{list-style:none;padding:0;margin:1rem 0;display:grid;gap:.5rem}
.ul li{display:flex;gap:.6rem;padding:.5rem .7rem;border:1px solid var(--line);border-radius:8px;background:#fff}
.ul .f{flex:0 0 9.5rem;font-weight:700;color:var(--muted)}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important}}
"""


def _page(
    title: str,
    body: str,
    *,
    route: str = "/",
    variant: str = "full",
) -> HTMLResponse:
    """Wrap body in a minimal accessible shell with the analytics hook."""
    html = (
        "<!doctype html><html lang='es-MX'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta name='color-scheme' content='light'>"
        f"<title>{title}</title><style>{_SHELL_CSS}</style></head>"
        f"<body data-variant='{variant}' data-route='{route}'>"
        "<a class='skip-link' href='#contenido'>Saltar al contenido</a>"
        "<header class='site'><nav class='nav' aria-label='Navegación'>"
        "<a class='brand' href='/'><span class='mark' aria-hidden='true'>A</span><span>Abarpay</span></a>"
        "<a class='btn btn-secondary' href='/' style='min-height:2.6rem;padding:.4rem 1rem'>Volver a la página</a>"
        "</nav></header>"
        f"<main id='contenido'><div class='wrap'>{body}</div></main>"
        + _analytics_script(route, variant)
        + "</body></html>"
    )
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


def _analytics_script(route: str, variant: str) -> str:
    """Consent-respecting funnel hooks. Only permitted fields are collected."""
    return (
        "<script>(function(){var endpoint=window.__ABARPAY_ANALYTICS_URL__||null;"
        f"var route={route!r},variant={variant!r};"
        "function utm(){var p=new URLSearchParams(location.search),o={};"
        "['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(function(k){"
        "var v=p.get(k);if(v)o[k]=v;});return o;}"
        "function track(n,f){var pl={event:n,id:'evt-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,9),"
        "ts:new Date().toISOString(),route:route,variant:variant,campaign:utm().utm_campaign||null,actor:null};"
        "for(var k in f)pl[k]=f[k];"
        "if(!endpoint){return;}try{if(navigator.sendBeacon){navigator.sendBeacon(endpoint,new Blob([JSON.stringify(pl)],{type:'application/json'}));}"
        "else{fetch(endpoint,{method:'POST',body:JSON.stringify(pl),keepalive:true,headers:{'Content-Type':'application/json'}});}}catch(e){} }"
        "track('landing_view',{utms:utm(),device:(matchMedia('(max-width:720px)').matches?'mobile':'desktop'),date:new Date().toISOString().slice(0,10)});"
        "document.addEventListener('click',function(e){var el=e.target&&e.target.closest?e.target.closest('[data-cta]'):null;"
        "if(!el)return;track('cta_click',{cta:el.getAttribute('data-cta'),destination:el.getAttribute('href')||null});},true);"
        "})();</script>"
    )


# ---------------------------------------------------------------------------
# CTA destination pages
# ---------------------------------------------------------------------------


def _empezar_page(interest: str, request: Request) -> HTMLResponse:
    label = INTEREST_LABELS.get(interest, INTEREST_LABELS[""])

    if interest == "control":
        body = (
            "<h1>Me interesa Control</h1>"
            "<p class='lede'>Control cuesta <strong>MXN 149 por tienda al mes</strong> y se cobra "
            "manualmente, fuera de esta página. No existe cargo automático desde la landing.</p>"
        )
    elif interest == "formalizacion":
        body = (
            "<h1>Me interesa el piloto de Formalización</h1>"
            "<p class='lede'>El piloto guiado de tres meses cuesta <strong>MXN 399 al mes durante 3 meses</strong>, "
            "sin renovación automática y con contador externo pagado aparte. Hoy sólo registramos interés; no hay cargo.</p>"
        )
    elif interest == "dossier":
        body = (
            "<h1>Me interesa el expediente financiero</h1>"
            "<p class='lede'>Es una investigación futura. No está incluido en los planes ni tiene precio o "
            "disponibilidad confirmados. Hoy sólo registramos interés.</p>"
        )
    elif interest == "reposicion":
        body = (
            "<h1>Me interesa el piloto de reposición</h1>"
            "<p class='lede'>La función de pedido y recepción de mercancía está en preparación. "
            "Registra tu interés y te avisaremos cuando esté disponible.</p>"
        )
    elif interest == "apk":
        body = (
            "<h1>Solicitar el APK piloto</h1>"
            "<p class='lede'>El APK piloto aún no está publicado. Déjanos tu interés y te avisaremos "
            "cuando exista una versión firmada y verificada, con su versión, SHA-256 y notas.</p>"
        )
    else:
        body = (
            "<h1>Empezar gratis</h1>"
            "<p class='lede'>El plan Gratis cuesta <strong>MXN 0</strong> e incluye caja, catálogo, "
            "inventario básico, registro de ventas, CoDi sin recargo de Abarpay, historial y exportación.</p>"
        )

    # Preserve permitted campaign/UTM attribution as hidden fields so the
    # interest POST carries them along (rule: store campaign/UTM on events).
    hidden = f"<input type='hidden' name='interest' value='{interest}'>"
    for key in PERMITTED_UTMS:
        value = request.query_params.get(key)
        if value:
            hidden += f"<input type='hidden' name='{key}' value='{_escape_attr(value)}'>"

    body += (
        "<div class='box'><p class='muted' style='margin:0'><strong>Estado:</strong> el alta "
        "autoservicio todavía no está abierto. Estamos en lista de espera. Al abrir, podrás "
        "crear tu tienda.</p></div>"
        "<form method='post' action='/api/landing/interest'>"
        f"{hidden}"
        "<button type='submit' class='btn btn-primary' data-cta='registrar-interes'>Registrar interés</button>"
        "</form>"
        "<p class='note'>La web no procesa cargos automáticos. Un clic en «Me interesa» no genera un cobro "
        "ni cuenta como ingreso. No te pedimos correo, teléfono ni datos bancarios; sólo registramos tu "
        "interés y la campaña de origen, en memoria y marcado como SIMULADO.</p>"
    )
    return _page(f"{label} · Abarpay", body, route="/empezar")


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _entrar_page() -> HTMLResponse:
    code = secrets.token_hex(3).upper()[:6]
    body = (
        "<h1>Entrar a mi tienda</h1>"
        "<p class='lede'>Escanea el QR con la app del dueño, revisa la tienda y el navegador, y aprueba o "
        "rechaza el acceso. Si la cámara no funciona, usa el código manual.</p>"
        "<div class='box'><p class='muted' style='margin:0'><strong>Estado:</strong> la aprobación por QR "
        "desde la app del dueño está en preparación. Hoy la consola del dueño usa un PIN.</p></div>"
        "<div class='box'>"
        "<p><span class='tag'>En preparación</span></p>"
        "<p style='margin:.5rem 0 .25rem'><strong>Código manual</strong> (vence en 5 minutos)</p>"
        f"<span class='code'>{code}</span>"
        "<p class='muted'>El código vence y no se reutiliza; si caduca, se genera otro.</p>"
        "</div>"
        "<p><a class='btn btn-secondary' href='/console' data-cta='entrar-consola-pin'>Entrar a la consola con PIN</a></p>"
        "<p class='note note-warn'>Un código expirado, reutilizado o aprobado desde otra cuenta se rechaza con "
        "un mensaje claro. La cámara necesita permiso; el código manual es la alternativa sin cámara.</p>"
    )
    return _page("Entrar a mi tienda · Abarpay", body, route="/entrar")


def _apk_page() -> HTMLResponse:
    fields = (
        ("Versión", "No publicado"),
        ("Fecha", "No publicado"),
        ("Revisión fuente", "No publicado"),
        ("SHA-256", "No publicado"),
        ("Firma", "No publicado"),
        ("Compatibilidad", "No publicado"),
        ("Notas", "No publicado"),
        ("Instrucciones", "No publicado"),
    )
    rows = "".join(
        f"<li><span class='f'>{k}</span><span class='muted'>{v}</span></li>" for k, v in fields
    )
    body = (
        "<h1>APK piloto</h1>"
        "<p class='lede'>El piloto se instala con un APK firmado. Antes de descargar, revisa la versión, "
        "el SHA-256 y las notas. La actualización conserva los datos locales autorizados.</p>"
        "<div class='box unavailable'>El APK piloto aún no está publicado. Déjanos tu interés y te "
        "avisaremos cuando exista una versión firmada y verificada.</div>"
        f"<ul class='ul'>{rows}</ul>"
        "<p><a class='btn btn-primary' href='/empezar?interes=apk' data-cta='solicitar-apk'>Solicitar el APK piloto</a></p>"
        "<p class='note note-warn'>Nunca distribuimos un archivo sin firma ni hash. Un enlace temporal, un "
        "archivo de depuración o un binario cuya firma no coincide con el dominio del producto no es una "
        "descarga válida.</p>"
    )
    return _page("APK piloto · Abarpay", body, route="/apk-piloto")


# ---------------------------------------------------------------------------
# register(app)
# ---------------------------------------------------------------------------


def register(app: Any) -> None:
    api = APIRouter(prefix="/api/landing")

    @api.post("/interest")
    async def record_interest(request: Request) -> Any:
        """Record a commercial interest in memory (SIMULADO).

        Reads the urlencoded body without python-multipart. Only permitted
        fields are stored: interest type and permitted UTMs, plus variant and
        timestamp. The optional note field is never read, to keep the ledger
        free of personal data.
        """

        from urllib.parse import parse_qs

        raw = await request.body()
        form = parse_qs(raw.decode("utf-8", "replace"))
        first = lambda key: (form.get(key) or [""])[0]
        interest = first("interest").strip()[:40]
        if interest not in INTEREST_LABELS:
            interest = ""
        utms = {
            key: first(key)
            for key in PERMITTED_UTMS
            if first(key)
        }
        entry = {
            "interest": interest or "empezar",
            "utms": utms,
            "variant": "full",
            "at": time.time(),
            "simulado": True,
        }
        _INTEREST_LEDGER.append(entry)
        return {
            "ok": True,
            "simulado": True,
            "state": "waiting-list",
            "message": "Interés registrado (SIMULADO, en memoria). Te avisaremos cuando el alta esté disponible.",
        }

    @app.get("/empezar", include_in_schema=False)
    def empezar(request: Request, interes: str = "") -> HTMLResponse:
        return _empezar_page((interes or "").strip(), request)

    @app.get("/entrar", include_in_schema=False)
    def entrar(request: Request) -> HTMLResponse:
        return _entrar_page()

    @app.get("/apk-piloto", include_in_schema=False)
    def apk_piloto(request: Request) -> HTMLResponse:
        # No file is ever served. This route only explains the unavailable
        # state and links to the interest form.
        return _apk_page()

    app.include_router(api)


def landing_page_response(request: Request) -> FileResponse:
    """Serve server/static/landing.html.

    The coordinator uses this for the root route, which currently redirects to
    /console in server/main.py.
    """

    static_dir = Path(
        getattr(getattr(request.app.state, "settings", None), "static_dir", None)
        or STATIC_DIR
    )
    page = static_dir / "landing.html"
    if not page.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Página de inicio no instalada")
    return FileResponse(page, media_type="text/html", headers={"Cache-Control": "no-store"})
