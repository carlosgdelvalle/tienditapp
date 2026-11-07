// Abarpay · cliente del teléfono. Los precios y el estado de pago los decide el servidor.
const $ = (id) => document.getElementById(id);
const peso = (c) => "$" + (c / 100).toLocaleString("es-MX", { minimumFractionDigits: c % 100 ? 2 : 0, maximumFractionDigits: 2 });
const S = { products: [], employees: [], empleado: null, carrito: new Map(), venta: null, poll: null, ownerPoll: null, desde: Date.now() / 1000, modoDemo: true };

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `Error ${r.status}`);
  return body;
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), 4500); }
function ir(vista) {
  document.querySelectorAll(".vista").forEach((v) => (v.hidden = v.id !== "v-" + vista));
  $("tabs").hidden = vista === "inicio" || vista === "qr" || vista === "pagado";
  $("atras").hidden = !["cobrar", "inventario", "mitienda"].includes(vista);
  document.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("activo", b.dataset.tab === vista));
  if (vista === "mitienda") cargarMiTienda();
  if (vista === "home") cargarHome();
  if (vista === "inventario") cargarInventario();
  window.scrollTo(0, 0);
}
async function cargarHome() {
  const [r, b] = await Promise.all([api("/api/reports/today"), api("/api/bootstrap")]);
  S.products = b.products;
  $("h-ventas").textContent = peso(r.totalCents);
  $("h-num").textContent = r.salesCount ? `${r.salesCount} ventas pagadas` : "Aún sin ventas hoy";
  $("h-stock").textContent = b.products.reduce((a, p) => a + p.stock, 0);
}
async function cargarInventario() {
  const b = await api("/api/bootstrap"); S.products = b.products;
  $("inv").innerHTML = b.products.map((p) => `<li><span>${p.name}<small>${peso(p.price_cents)}</small></span><b class="${p.stock <= 5 ? "bajo" : ""}">${p.stock}</b></li>`).join("");
}
function hablar(texto) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(texto); u.lang = "es-MX"; u.rate = 1;
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}

// ---------- Inicio ----------
async function init() {
  const b = await api("/api/bootstrap");
  Object.assign(S, { products: b.products, employees: b.employees, modoDemo: b.modoDemo });
  $("tienda").textContent = b.store;
  $("demo-banner").hidden = !b.modoDemo;
  $("ia").textContent = b.ia === "openai" ? "La IA de OpenAI arma el carrito con el catálogo de la tienda." : "IA no configurada: se usa el intérprete local del catálogo.";
  $("tienda").textContent = b.store;
  $("empleados").innerHTML = b.employees.map((e) => `<button data-emp="${e.id}">${e.name}<small>${e.role === "owner" ? "Dueña" : "Empleado"}</small></button>`).join("");
  $("rapidos").innerHTML = b.products.filter((p) => p.quick).map((p) => `<button data-prod="${p.id}">${p.name.replace(/ \(.+\)|\s\d.*$/, "")}<br><small>${peso(p.price_cents)}</small></button>`).join("");
}
$("empleados").addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-emp]"); if (!btn) return;
  S.empleado = S.employees.find((e) => e.id === +btn.dataset.emp);
  $("quien").textContent = S.empleado.name;
  hablar(""); // desbloquea el audio con el primer toque
  if (S.empleado.role === "owner") iniciarAvisosDueno();
  ir("home");
});

// ---------- Carrito ----------
function agregar(productId, qty) {
  S.carrito.set(productId, Math.max(0, (S.carrito.get(productId) || 0) + qty));
  if (!S.carrito.get(productId)) S.carrito.delete(productId);
  pintarCarrito();
}
function pintarCarrito() {
  let total = 0;
  $("carrito").innerHTML = [...S.carrito].map(([id, q]) => {
    const p = S.products.find((x) => x.id === id); total += p.price_cents * q;
    return `<li><span class="n">${p.name}</span><span class="q"><button data-menos="${id}" aria-label="Quitar uno">−</button>${q}<button data-mas="${id}" aria-label="Agregar uno">+</button></span><span class="p">${peso(p.price_cents * q)}</span></li>`;
  }).join("");
  $("total").textContent = peso(total);
  $("cobrar").disabled = total === 0;
  $("cobrar").textContent = total ? `Cobrar ${peso(total)}` : "Cobrar";
}
$("rapidos").addEventListener("click", (ev) => { const b = ev.target.closest("[data-prod]"); if (b) agregar(+b.dataset.prod, 1); });
$("carrito").addEventListener("click", (ev) => {
  const m = ev.target.closest("[data-mas]"), n = ev.target.closest("[data-menos]");
  if (m) agregar(+m.dataset.mas, 1); if (n) agregar(+n.dataset.menos, -1);
});

async function interpretar(texto) {
  $("escuche").hidden = false; $("escuche").textContent = `“${texto}”`;
  try {
    const r = await api("/api/cart/parse", { method: "POST", body: JSON.stringify({ text: texto }) });
    r.items.forEach((i) => agregar(i.productId, i.qty));
    $("unmatched").innerHTML = r.unmatched.map((u) => `<span>No encontré: ${u}</span>`).join("");
    if (r.warning) toast(r.warning);
  } catch (e) { toast(e.message); }
}
$("f-texto").addEventListener("submit", (ev) => { ev.preventDefault(); const t = $("texto").value.trim(); if (t) { interpretar(t); $("texto").value = ""; } });

// Dictado: Web Speech API del navegador (requiere HTTPS o localhost). El texto se interpreta en el servidor.
const Reco = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!Reco) { $("mic").title = "Este navegador no permite dictar; escribe la venta."; }
$("mic").addEventListener("pointerdown", () => {
  if (!Reco) return toast("Este navegador no permite dictar aquí. Escribe la venta o usa los botones.");
  const r = new Reco(); r.lang = "es-MX"; r.interimResults = false; r.maxAlternatives = 1;
  r.onresult = (e) => interpretar(e.results[0][0].transcript);
  r.onerror = (e) => toast(e.error === "not-allowed" ? "Permite el micrófono para dictar." : "No te escuché. Intenta otra vez.");
  r.onend = () => $("mic").classList.remove("oyendo");
  $("mic").classList.add("oyendo"); r.start(); S.reco = r;
});
["pointerup", "pointerleave"].forEach((t) => $("mic").addEventListener(t, () => S.reco && S.reco.stop()));

// ---------- Cobro ----------
$("cobrar").addEventListener("click", async () => {
  $("cobrar").disabled = true; $("cobrar").textContent = "Generando cobro…";
  try {
    const items = [...S.carrito].map(([productId, qty]) => ({ productId, qty }));
    const v = await api("/api/sales", { method: "POST", body: JSON.stringify({ employeeId: S.empleado.id, items }) });
    S.venta = v;
    $("qr-monto").textContent = peso(v.totalCents);
    $("qr-demo").hidden = v.chargedCents === v.totalCents;
    $("qr-demo").innerHTML = `Modo demo: se cobra <b>${peso(v.chargedCents)}</b>`;
    $("qr-img").src = v.qrImage; $("qr-estado").textContent = "Esperando pago…";
    ir("qr"); vigilar(v.saleId);
  } catch (e) { toast(e.message); pintarCarrito(); }
});
function vigilar(id) {
  clearInterval(S.poll);
  S.poll = setInterval(async () => {
    try {
      const s = await api(`/api/sales/${id}`);
      if (s.status === "paid") { clearInterval(S.poll); mostrarPagado(s); }
      else if (s.status === "expired") { clearInterval(S.poll); $("qr-estado").textContent = "El cobro venció o se canceló."; }
      else if (s.status === "por_conciliar") { clearInterval(S.poll); $("qr-estado").textContent = "Pago por revisar: " + (s.note || "") ; }
    } catch { $("qr-estado").textContent = "Sin conexión. Reintentando…"; }
  }, 2500);
}
function mostrarPagado(s) {
  $("voz-texto").textContent = `Pagado con Pey · ${S.empleado ? S.empleado.name : ""}`;
  $("r-cobrado").textContent = peso(s.chargedCents); $("r-total").textContent = peso(s.totalCents);
  $("r-tx").textContent = s.txId || "";
  ir("pagado"); hablar(`Ya te pagaron ${s.chargedCents === 1 ? "un centavo" : peso(s.chargedCents).replace("$", "") + " pesos"}`);
  if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
  S.desde = Math.max(S.desde, s.paidAt || 0);
  api("/api/bootstrap").then((b) => (S.products = b.products));
}
$("cancelar").addEventListener("click", async () => { clearInterval(S.poll); if (S.venta) await api(`/api/sales/${S.venta.saleId}/cancel`, { method: "POST" }); ir("cobrar"); pintarCarrito(); });
$("nueva").addEventListener("click", () => { S.carrito.clear(); S.venta = null; $("escuche").hidden = true; $("unmatched").innerHTML = ""; pintarCarrito(); ir("cobrar"); });

// ---------- Dueño: aviso de pagos de cualquier empleado ----------
function iniciarAvisosDueno() {
  clearInterval(S.ownerPoll);
  S.ownerPoll = setInterval(async () => {
    try {
      const pagos = await api(`/api/paid-since?ts=${S.desde}`);
      for (const p of pagos) {
        S.desde = Math.max(S.desde, p.paid_at);
        if (S.venta && p.id === S.venta.saleId) continue; // ya se anunció en este teléfono
        toast(`${p.employee} cobró ${peso(p.charged_cents)} (venta de ${peso(p.total_cents)})`);
        hablar(`${p.employee} cobró una venta`);
        if (!$("v-mitienda").hidden) cargarMiTienda();
      }
    } catch {}
  }, 3000);
}

// ---------- Mi tienda ----------
async function cargarMiTienda() {
  const r = await api("/api/reports/today");
  $("m-total").textContent = peso(r.totalCents);
  $("m-ventas").textContent = `${r.salesCount} ventas pagadas · cobrado por CoDi ${peso(r.chargedCents)}${r.modoDemo ? " (modo demo)" : ""}`;
  $("m-emp").innerHTML = r.byEmployee.map((e) => `<li><span>${e.name} · ${e.sales}</span><b>${peso(e.totalCents)}</b></li>`).join("");
  $("m-top").innerHTML = r.topProducts.map((t) => `<li><span>${t.name}</span><b>${t.qty}</b></li>`).join("");
  $("m-low").innerHTML = r.lowStock.map((p) => `<li><span>${p.name}</span><b class="bajo">${p.stock}</b></li>`).join("");
  $("m-pend").hidden = !r.porConciliar; $("m-pend").textContent = `${r.porConciliar} pago(s) por conciliar: revisa en pey antes de cerrar caja.`;
}
document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => ir(b.dataset.ir)));
document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => ir(b.dataset.tab)));
$("atras").addEventListener("click", () => ir("home"));

// ---------- Escáner con cámara (códigos de barras y foto de productos) ----------
const SC = { stream: null, timer: null, modo: "codigo", ultimo: "", bloqueado: false };
async function abrirScanner(modo) {
  SC.modo = modo; SC.ultimo = ""; SC.bloqueado = false;
  $("scanner").hidden = false; $("enlazar").hidden = true;
  $("scan-titulo").textContent = modo === "foto" ? "Foto de productos" : "Escanear código";
  $("scan-marco").classList.toggle("foto", modo === "foto");
  $("tomar-foto").hidden = modo !== "foto"; $("scan-manual").hidden = modo === "foto";
  $("scan-msg").textContent = modo === "foto" ? "Pon los productos en el mostrador y toma la foto." : "Apunta al código de barras del producto.";
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    $("scan-msg").textContent = "La cámara necesita HTTPS o localhost. Escribe el código abajo."; return;
  }
  try {
    SC.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    $("scan-video").srcObject = SC.stream; await $("scan-video").play();
  } catch (e) { $("scan-msg").textContent = "No pude abrir la cámara (" + e.name + "). Escribe el código abajo."; return; }
  if (modo === "codigo") iniciarLectura();
}
function cerrarScanner() {
  clearInterval(SC.timer);
  if (SC.stream) SC.stream.getTracks().forEach((t) => t.stop());
  SC.stream = null; $("scanner").hidden = true;
}
async function iniciarLectura() {
  if (!("BarcodeDetector" in window)) { $("scan-msg").textContent = "Este navegador no lee códigos con la cámara (usa Chrome). Escribe el código abajo."; return; }
  const det = new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "qr_code"] });
  SC.timer = setInterval(async () => {
    if (SC.bloqueado || $("scan-video").readyState < 2) return;
    try {
      const codes = await det.detect($("scan-video"));
      if (codes.length && codes[0].rawValue !== SC.ultimo) { SC.ultimo = codes[0].rawValue; buscarCodigo(SC.ultimo); }
    } catch {}
  }, 350);
}
async function buscarCodigo(code) {
  SC.bloqueado = true;
  try {
    const p = await api("/api/barcode/lookup", { method: "POST", body: JSON.stringify({ code }) });
    agregar(p.productId, 1); if (navigator.vibrate) navigator.vibrate(80);
    $("scan-msg").textContent = `Agregado: ${p.name}. Escanea el siguiente o cierra.`;
    setTimeout(() => { SC.bloqueado = false; SC.ultimo = ""; }, 1200);
  } catch (e) {
    if (e.message !== "Código sin enlazar") { $("scan-msg").textContent = e.message; SC.bloqueado = false; return; }
    $("enl-codigo").textContent = code; $("enlazar").hidden = false;
    $("enl-lista").innerHTML = S.products.map((p) => `<button data-enl="${p.id}">${p.name}</button>`).join("");
    $("scan-msg").textContent = "Este código es nuevo: enlázalo una vez y la próxima se agrega solo.";
  }
}
$("enl-lista").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-enl]"); if (!b) return;
  const code = $("enl-codigo").textContent;
  const p = await api("/api/barcode/link", { method: "POST", body: JSON.stringify({ code, productId: +b.dataset.enl }) });
  agregar(p.productId, 1); $("enlazar").hidden = true;
  $("scan-msg").textContent = `Enlazado y agregado: ${p.name}.`;
  setTimeout(() => { SC.bloqueado = false; SC.ultimo = ""; }, 1200);
});
$("scan-manual").addEventListener("submit", (ev) => { ev.preventDefault(); const c = $("scan-codigo").value.trim(); if (c) { buscarCodigo(c); $("scan-codigo").value = ""; } });
$("tomar-foto").addEventListener("click", async () => {
  const v = $("scan-video"); if (!v.videoWidth) return toast("La cámara aún no está lista.");
  const cv = document.createElement("canvas"); const k = Math.min(1, 1024 / v.videoWidth);
  cv.width = v.videoWidth * k; cv.height = v.videoHeight * k; cv.getContext("2d").drawImage(v, 0, 0, cv.width, cv.height);
  $("scan-msg").textContent = "Reconociendo productos…";
  try {
    const r = await api("/api/cart/photo", { method: "POST", body: JSON.stringify({ image: cv.toDataURL("image/jpeg", 0.8).split(",")[1] }) });
    r.items.forEach((i) => agregar(i.productId, i.qty));
    $("unmatched").innerHTML = r.unmatched.map((u) => `<span>No reconocí: ${u}</span>`).join("");
    cerrarScanner(); toast(r.items.length ? "Productos agregados desde la foto. Revisa antes de cobrar." : "No reconocí productos del catálogo.");
  } catch (e) { $("scan-msg").textContent = e.message; }
});
$("abrir-scan").addEventListener("click", () => abrirScanner("codigo"));
$("abrir-foto").addEventListener("click", () => abrirScanner("foto"));
$("cerrar-scan").addEventListener("click", cerrarScanner);

init().catch((e) => toast("No pude cargar la tienda: " + e.message));
