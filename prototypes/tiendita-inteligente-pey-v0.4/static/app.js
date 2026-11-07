'use strict';
const $=s=>document.querySelector(s), fmt=c=>new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(c/100);
const emoji=id=>({leche:'🥛',pan:'🍞',huevo:'🥚',agua:'💧',refresco:'🥤',arroz:'🍚',cafe:'☕',yogur:'🍦'})[id]||'📦';
const esc=s=>String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let state={data:null,online:false,tab:'inicio',role:localStorage.getItem('role')||'Dueño',search:'',cart:JSON.parse(localStorage.getItem('cart')||'{}'),activeSale:null,qr:null};
let toastTime=0;
let reportV05=null, assistantV05=null, scannerV05=null, cameraV05=null;
let ownerSoundEnabled=false, lastSoundNoticeId=0;
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');clearTimeout(toastTime);toastTime=setTimeout(()=>el.classList.remove('show'),3800)}
async function api(path,opts={}){
  const headers={'Content-Type':'application/json',...(opts.headers||{})};
  let key=sessionStorage.getItem('tiendita_operator_key');
  if(key)headers['x-tiendita-operator-key']=key;
  let response=await fetch(path,{...opts,headers});
  if(response.status===401){
    const input=prompt('PEY REAL · Introduce el token seguro del operador (no la API key de PEY):');
    if(!input)throw Error('Acceso de operador requerido');
    sessionStorage.setItem('tiendita_operator_key',input);
    headers['x-tiendita-operator-key']=input;
    response=await fetch(path,{...opts,headers});
  }
  let data={};try{data=await response.json()}catch(e){}
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:`Error HTTP ${response.status}`);
  return data;
}
async function reload(silent=false){try{const data=await api('/api/bootstrap');state.data=data;state.online=true;if(data.config.pey_mode!=='REAL')localStorage.setItem('snapshot',JSON.stringify(data));else localStorage.removeItem('snapshot');$('#net-state').textContent='● Conectado';$('#net-state').className='pill';$('#connection-note').hidden=true;$('#payment-mode').textContent=`Cobros: ${data.config.pey_mode}`;if(!silent)render()}catch(e){state.online=false;$('#net-state').textContent='● Sin servidor';$('#net-state').className='pill offline';$('#connection-note').hidden=false;const cache=localStorage.getItem('snapshot');if(cache&&!state.data)try{state.data=JSON.parse(cache)}catch(err){}if(!silent)render()}}
function saveCart(){localStorage.setItem('cart',JSON.stringify(state.cart))}
function btn(label,action,cls='secondary',extra=''){return `<button class="button ${cls}" data-action="${action}" ${extra}>${label}</button>`}
function header(title,caption=''){return `<div class="hero"><div class="eyebrow">Sucursal Centro · ${esc(state.role)}</div><h1>${title}</h1>${caption?`<p>${caption}</p>`:''}</div>`}
function statusTag(s){const x={PENDIENTE:'Pendiente de pago',PAGADA:'Pago PEY verificado',PAGADA_PRUEBA:'PEY prueba $0.01 (real)',DEMO_PAGADA:'Pago DEMO (simulado)',CANCELADA:'Cancelada',FIADA:'Fiado · por cobrar',RECIBIDO:'Recibido',REVISAR_PEY:'Verificar en PEY',INICIANDO:'Creando cobro'};return `<span class="tag ${s==='PENDIENTE'?'warn':''}">${x[s]||esc(s)}</span>`}
function home(){const d=state.data;const exp=d.products.filter(p=>p.next_expiry&&new Date(p.next_expiry+'T23:59')-new Date()<7*86400000);const low=d.products.filter(p=>p.qty<=p.min_qty);
let cards=`<div class="grid"><div class="card"><div class="sub">💰 Ingresos comerciales PEY</div><div class="stat">${fmt(d.totals.sales_cents)}</div><div class="stat-caption">No incluye simulaciones ni cobros de prueba</div></div><div class="card"><div class="sub">✅ Ventas completadas</div><div class="stat">${d.totals.sales_count}</div><div class="stat-caption">Excluye pruebas y simulaciones</div></div><div class="card"><div class="sub">📒 Fiado pendiente</div><div class="stat">${fmt(d.totals.credit_outstanding_cents||0)}</div><div class="stat-caption">Deuda, NO ingreso cobrado</div></div><div class="card"><div class="sub">⚠️ Productos bajos</div><div class="stat">${d.totals.low_stock}</div><div class="stat-caption">Requieren atención</div></div><div class="card"><b>🧪 Pruebas bancarias</b><div class="stat">${fmt(d.totals.test_pey_receipts_cents||0)}</div><div class="stat-caption">Centavos recibidos en PEY; no venta comercial</div></div><div class="card"><b>🧪 Ventas simuladas</b><div class="stat">${d.totals.demo_sales_count||0}</div><div class="stat-caption">Sin dinero transferido</div></div></div>`;
return header('Tu tienda, bajo control','Desde tu celular: mercancía, ventas y avisos importantes.')+cards+`<div class="cards"><div class="card">${btn('📊 Corte del día','tab:corte','secondary full')}</div><div class="card">${btn('💬 Consultar mi negocio','tab:asesor','secondary full')}</div><div class="card">${btn(ownerSoundEnabled?'🔊 Avisos de voz activados':'🔇 Activar avisos de voz','toggle-sound','secondary full')}</div></div>`+`<div class="section-head"><h2>¿Qué necesitas hacer?</h2></div><div class="cards"><div class="card gap12"><div class="big">🛒 Atender una venta</div><div class="sub">Agrega productos, pide un QR y verifica el resultado.</div>${btn('Empezar venta →','tab:vender','dark full')}</div><div class="card gap12"><div class="big">📦 Ver qué pedir</div><div class="sub">Existencias bajas y cantidad sugerida para reponer.</div>${btn('Revisar inventario →','tab:inventario','secondary full')}</div></div>`+
`<div class="section-head"><h2>Lo que necesita tu atención</h2></div>${low.slice(0,3).map(p=>`<div class="card list-row row"><div><b>${emoji(p.id)} ${esc(p.name)}</b><div class="sub">Quedan ${p.qty} · Recomendamos pedir ${p.recommended}</div></div><span class="tag warn">Bajo</span></div>`).join('')||'<div class="good">Sin productos bajos.</div>'}${exp.length?`<div class="alert">🕒 ${exp.length} producto(s) con fecha de caducidad dentro de 7 días. Revisa la sección Inventario.</div>`:''}`+
`<div class="section-head"><h2>Últimas ventas</h2></div><div class="card">${d.sales.slice(0,4).map(s=>`<div class="list-row row"><div><b>#${s.id} · ${fmt(s.amount_cents)}</b><div class="sub">${esc(s.employee)} · ${esc(s.created_at.slice(0,16))}</div></div>${statusTag(s.status)}</div>`).join('')||'<div class="empty">Aún no hay ventas.</div>'}</div>`}
function sell(){const list=state.data.products.filter(p=>p.name.toLowerCase().includes(state.search.toLowerCase())||p.category.toLowerCase().includes(state.search.toLowerCase()));const items=Object.entries(state.cart).filter(([,q])=>q>0).map(([id,qty])=>({p:state.data.products.find(x=>x.id===id),qty})).filter(x=>x.p);const total=items.reduce((a,x)=>a+x.p.price_cents*x.qty,0);
return header('Atender una venta','Paso 1: selecciona los productos del cliente.')+`<div class="card">${btn('▦ Escanear código de barras','scan-barcode','secondary full')}<div class="sub">También puedes introducir el código manualmente.</div></div><input id="product-search" class="filter" type="search" value="${esc(state.search)}" placeholder="🔎 Busca leche, café, agua…" aria-label="Buscar productos"/>`+`<div class="cards">${list.map(p=>`<div class="card row"><div class="product"><div class="emoji">${emoji(p.id)}</div><div><div class="product-title">${esc(p.name)}</div><div class="price">${fmt(p.price_cents)}</div><div class="stock">Disponibles: <b>${p.available}</b></div></div></div><div class="qtybar"><button aria-label="Quitar ${esc(p.name)}" data-action="minus:${p.id}">−</button><strong>${state.cart[p.id]||0}</strong><button aria-label="Agregar ${esc(p.name)}" data-action="plus:${p.id}">+</button></div></div>`).join('')}</div>`+`<div class="cart-summary"><div class="row"><div><b>${items.reduce((a,x)=>a+x.qty,0)} productos</b><div style="font-size:24px;font-weight:800">${fmt(total)}</div></div>${btn('Crear venta →','create-sale','secondary',` ${total<=0?'disabled':''}`)}</div><div style="font-size:12px;opacity:.83;margin-top:6px">${state.online?'La venta reservará existencias. El cobro se confirma después.':'Sin conexión: el carrito queda guardado en este celular.'}</div></div>`}
function inventory(){const prods=state.data.products;return header('Inventario sin complicaciones','Lo que tienes, lo que se acaba y cuánto pedir.')+`<div class="alert">💡 Sugerencias ilustrativas: mínimo deseado + ventas diarias estimadas × días de entrega − existencias. El dueño decide.</div>`+
`<div class="gap12">${prods.map(p=>`<div class="card"><div class="row topalign"><div class="product"><div class="emoji">${emoji(p.id)}</div><div><div class="product-title">${esc(p.name)}</div><div class="stock">Existencias <b>${p.qty}</b> · Mínimo ${p.min_qty}</div>${p.next_expiry?`<div class="sub">🕒 Próxima caducidad: ${p.next_expiry}</div>`:''}</div></div>${p.qty<=p.min_qty?'<span class="tag warn">Reponer</span>':'<span class="tag">Bien</span>'}</div><div class="line"></div><div class="row"><div class="sub">Sugerencia: <b>${p.recommended} unidades</b></div>${btn('Pedir '+(p.recommended||1),'order:'+p.id,'secondary')}</div></div>`).join('')}</div>`}
function purchases(){const d=state.data;return header('Pedidos y recepciones','Del proveedor al estante, con registro de quién recibió.')+`<div class="card"><h2 style="margin-top:0">Pedidos al proveedor</h2>${d.purchases.map(p=>`<div class="list-row"><div class="row"><div><div class="product-title">#${p.id} · ${esc(p.product_name)}</div><div class="sub">Solicitado: ${p.qty_requested} · Proveedor: ${esc(p.supplier)}</div><div class="sub">Recibido: ${p.qty_received}</div></div>${statusTag(p.status)}</div>${p.status==='PENDIENTE'?`<div class="topgap">${btn('📥 Registrar recepción','receive:'+p.id,'dark')}</div>`:''}</div>`).join('')||'<div class="empty">Aún no hay pedidos. Crea uno desde Inventario.</div>'}</div>`}
function notices(){const d=state.data;const isOwner=state.role==='Dueño';const list=d.notifications.filter(n=>isOwner?n.role==='dueno':n.role==='empleado');return header(isOwner?'Tus avisos':'Avisos de venta','Todo en un lugar, sin tener que llamar a la tienda.')+`<div class="card">${list.map(n=>`<div class="list-row"><div class="product-title">🔔 ${esc(n.message)}</div><div class="sub">${esc(n.created_at.replace('T',' ').slice(0,16))}</div></div>`).join('')||'<div class="empty">No hay avisos todavía.</div>'}</div>`+`<div class="alert">Los SMS y notificaciones push fuera de la app requieren un proveedor adicional y autorización. Esta versión muestra avisos en la aplicación.</div>`}
function credits(){const d=state.data;const total=d.totals.credit_outstanding_cents||0;const live=d.config.pey_mode==='REAL';
return header('Fiados de confianza','Registra a quién le fiamos, cuánto debe y solicita abonos.')+
`<div class="alert">🧾 FIADO ≠ PAGO. La deuda solo se reduce con confirmación firmada de PEY o con una simulación etiquetada DEMO. El cliente no necesita instalar esta app.</div>`+
`<div class="card"><div class="sub">Por cobrar a clientes</div><div class="stat">${fmt(total)}</div>${btn('＋ Registrar cliente','new-client','dark')}</div>`+
`<div class="section-head"><h2>Clientes</h2></div><div class="gap12">${d.clients.map(c=>`<div class="card"><div class="row"><div><div class="product-title">👤 ${esc(c.name)}</div><div class="sub">Límite acordado ${fmt(c.credit_limit_cents)}</div><div class="sub">Saldo por cobrar: <b>${fmt(c.balance_cents)}</b></div></div>${c.balance_cents>0?btn('Solicitar abono','collect:'+c.id,'secondary'):'<span class="tag">Al corriente</span>'}</div></div>`).join('')||'<div class="empty">Sin clientes</div>'}</div>`+
`<div class="section-head"><h2>Solicitudes de abono</h2></div><div class="card">${d.payment_requests.map(r=>`<div class="list-row"><div class="row"><div><b>#${r.id} · ${esc(r.client_name)}</b><div class="sub">${fmt(r.amount_cents)} · ${r.status==='PENDIENTE'?'Por confirmar':(r.status==='PAGADA'?'Pago PEY confirmado':(r.status==='REVISAR_PEY'?'Revisar PEY':r.status))}</div></div>${r.status==='PENDIENTE'?btn('Ver solicitud','show-collect:'+r.id,'secondary'):statusTag(r.status)}</div></div>`).join('')||'<div class="empty">Aún no hay solicitudes.</div>'}</div>`;
}
function newClientModal(){showModal(`<div class="eyebrow">Fiado · Registro interno</div><h2>Nuevo cliente</h2><label>Nombre<input id="client-name" class="input" maxlength="100" placeholder="Nombre del cliente"></label><p class="sub">Celular (10 dígitos; necesario solo para CoDi Push real)<input id="client-phone" class="input" inputmode="tel" maxlength="10" placeholder="5512345678"></p><p class="sub">Límite autorizado en pesos<input id="client-limit" class="input" type="number" min="1" max="100000" value="500"></p>${btn('Guardar cliente de prueba','save-client','dark full')}`)}
async function saveClient(){const name=$('#client-name').value.trim(),phone=$('#client-phone').value.trim(),v=Number($('#client-limit').value);if(name.length<2||!Number.isFinite(v)||v<=0)return toast('Verifica nombre y límite');try{await api('/api/clients',{method:'POST',body:JSON.stringify({name,phone,credit_limit_cents:Math.round(v*100)})});await reload(true);hideModal();state.tab='fiados';render();toast('Cliente agregado (registro DEMO)')}catch(e){toast(e.message)}}
async function creditSale(){if(!state.activeSale)return;const id=Number($('#credit-client')?.value);if(!id)return toast('Selecciona un cliente registrado');try{await api(`/api/sales/${state.activeSale}/credit`,{method:'POST',body:JSON.stringify({client_id:id})});await reload(true);showModal(`<div class="eyebrow">FIADO REGISTRADO</div><h2>📒 Venta entregada a crédito</h2><div class="alert">La mercancía salió del inventario, pero NO hemos recibido dinero. El cliente ahora tiene saldo pendiente.</div>${btn('Ver fiados','tab:fiados','dark full')}`);render()}catch(e){toast(e.message)}}
function collectModal(id){
 const c=state.data.clients.find(x=>x.id===id);
 if(!c||c.balance_cents<=0)return toast('Sin deuda pendiente');
 const live=state.data.config.pey_mode==='REAL';
 showModal(`<div class="eyebrow">Solicitud de abono · ${live?'PEY real':'DEMO'}</div><h2>Solicitar abono</h2><p>${esc(c.name)} debe <b>${fmt(c.balance_cents)}</b></p>
 <label>Solicitar (pesos)<input class="input" id="collect-amount" type="number" min="0.01" max="${c.balance_cents/100}" step="0.01" value="${(c.balance_cents/100).toFixed(2)}" /></label>
 <label>Método de cobro<select id="collect-method" class="input"><option value="QR">QR CoDi (enlace para mostrar el QR)</option><option value="PUSH">CoDi Push al celular del cliente</option></select></label>
 <div class="alert">${live?'PEY enviará una solicitud bancaria REAL al elegir CoDi Push. Verifica el importe y el número del cliente.':'MODO DEMO: no cobrará ni enviará notificaciones externas.'}</div>
 ${btn(live?'Solicitar cobro con PEY':'Crear solicitud DEMO','make-collect:'+c.id,'dark full')}`)
}
async function makeCollect(id){
 const amount=Number($('#collect-amount').value),method=$('#collect-method').value;
 if(!Number.isFinite(amount)||amount<=0)return toast('Monto inválido');
 const live=state.data.config.pey_mode==='REAL';
 if(live&&!confirm('Vas a crear una solicitud bancaria REAL mediante PEY. ¿Continuar?'))return;
 try{const r=await api(`/api/clients/${id}/payment-requests`,{method:'POST',body:JSON.stringify({amount_cents:Math.round(amount*100),method})});
 state.demoRequest=r;await reload(true);displayCollect(r);
 }catch(e){toast(e.message)}
}
function displayCollect(r){
 const real=r.mode==='REAL',img=r.qr_image?`<img class="qr-img" src="data:image/png;base64,${r.qr_image}" alt="${real?'QR de cobro CoDi':'QR demo'}">`:'';
 showModal(`<div class="eyebrow">${real?'PEY REAL · ESPERANDO PAGO':'SIMULACIÓN DEMO'} · ABONO #${r.id}</div>
 <h2>Solicitar ${fmt(r.amount_cents)}</h2>${img}
 <div class="${real?'alert':'demo-watermark'}">${esc(r.message||'No equivale a pago recibido')}</div>
 ${r.link?`<label class="sub">Enlace de solicitud ${r.method==='PUSH'?'(estado)':'(QR para otro equipo)'}<input id="collect-link" class="input" readonly value="${esc(r.link)}"></label>
 <div class="topgap">${btn('Copiar enlace','copy-collect','secondary full')}</div>`:''}
 ${real?'<p class="sub">El fiado NO cambia hasta recibir un webhook bancario firmado. La app actualiza los avisos al confirmar.</p>':`<div class="topgap">${btn('Simular abono recibido','confirm-collect:'+r.id,'dark full')}</div>`}
 <p class="sub">Enlaces locales sólo son visibles en la misma red Wi-Fi. Para compartir fuera, se requiere alojamiento HTTPS público.</p>`)
}
function showCollect(id){
 const r=state.data.payment_requests.find(x=>x.id===id);if(!r)return;
 const link=window.location.origin+'/p/'+r.token;
 const real=(r.pey_method||'').startsWith('REAL_');
 showModal(`<div class="eyebrow">ABONO #${id} · ${real?'PEY':'DEMO'}</div><h2>${fmt(r.amount_cents)}</h2>
 <div class="${real?'alert':'demo-watermark'}">${real?'Pendiente hasta confirmación firmada de PEY':'Enlace NO pagable'}</div>
 <input id="collect-link" readonly class="input" value="${esc(link)}">${btn('Copiar enlace','copy-collect','secondary full')}
 ${real?'':btn('Simular abono recibido','confirm-collect:'+id,'dark full')}`)
}
async function confirmCollect(id){
 try{await api(`/api/payment-requests/${id}/demo-confirm`,{method:'POST'});
 await reload(true);hideModal();state.tab='fiados';render();toast('Abono SIMULADO registrado; no hubo dinero real')
 }catch(e){toast(e.message)}
}
function cashReport(){const r=reportV05;return header('Corte del día','Ingresos cobrados, separados de pruebas, simulaciones y fiados.')+(r?`<div class="cards"><div class="card"><b>Ventas comerciales: ${fmt(r.commercial_cents)}</b><p>${r.paid_count} ventas pagadas</p></div><div class="card"><b>PEY pruebas: ${fmt(r.test_cents)}</b><p>${r.test_count} cobros reales de prueba</p></div><div class="card"><b>Simulaciones: ${fmt(r.simulated_cents)}</b></div><div class="card"><b>Fiados registrados: ${fmt(r.credit_cents)}</b></div><div class="card"><b>Pendientes: ${r.pending_count}</b><p>Revisar: ${r.uncertain_count}</p></div></div><div class="card"><h3>Por empleado (solo ventas comerciales)</h3>${r.employees.map(x=>`<p>${esc(x.name)}: ${fmt(x.commercial_cents)} · ${x.sales} ventas</p>`).join('')||'<p>Sin cobros comerciales</p>'}</div><p class="sub">${esc(r.note)}</p>`:'<div class="card">Presiona Consultar para cargar el corte.</div>')+btn('Consultar corte de hoy','load-corte','dark full')}
function businessAssistant(){return header('Pregúntale a tu tienda','Consultas locales de solo lectura, sin servicios de pago.')+`<div class="card"><label for="ask-question">Tu pregunta</label><input class="filter" id="ask-question" maxlength="250" placeholder="¿Qué productos debo reponer?"/><p class="sub">Ejemplos: ¿Cuánto vendí hoy? · ¿Cuánto me deben de fiado? · ¿Qué ventas están pendientes?</p>${btn('Consultar','ask-business','dark full')}${assistantV05?`<div class="alert" role="status"><b>Respuesta:</b> ${esc(assistantV05.answer)}<p class="sub">Fuente: ${esc(assistantV05.source)}</p></div>`:''}</div>`}
async function loadDailyClose(){try{reportV05=await api('/api/reports/daily-close');render()}catch(e){toast(e.message)}}
async function askBusiness(){const question=$('#ask-question')?.value?.trim();if(!question)return toast('Escribe una pregunta');try{assistantV05=await api('/api/assistant/ask',{method:'POST',body:JSON.stringify({question})});render()}catch(e){toast(e.message)}}
function stopBarcodeCamera(){if(scannerV05){clearInterval(scannerV05);scannerV05=null}if(cameraV05){cameraV05.getTracks().forEach(x=>x.stop());cameraV05=null}}
function openBarcode(){showModal(`<h2>Escanear código de barras</h2><p>Usa cámara compatible o escribe el código. Un código desconocido requiere elegir un producto del catálogo.</p><video id="barcode-video" autoplay muted playsinline style="width:100%;max-height:240px"></video><input class="filter" id="barcode-manual" placeholder="Código EAN / UPC" autocomplete="off"/>${btn('Buscar código','barcode-find','dark full')}<p id="barcode-message" class="sub" role="status"></p><div id="barcode-link-area"></div>`);startBarcodeCamera()}
async function startBarcodeCamera(){if(!navigator.mediaDevices?.getUserMedia||!('BarcodeDetector' in window)){if($('#barcode-message'))$('#barcode-message').textContent='Cámara no compatible. Ingresa el código manualmente.';return}try{cameraV05=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'},audio:false});const video=$('#barcode-video');if(!video){stopBarcodeCamera();return}video.srcObject=cameraV05;await video.play();const detector=new BarcodeDetector({formats:['ean_13','ean_8','upc_a','upc_e','code_128']});scannerV05=setInterval(async()=>{try{if(video.readyState<2)return;const codes=await detector.detect(video);if(codes.length){const code=codes[0].rawValue;stopBarcodeCamera();$('#barcode-manual').value=code;await findBarcode(code)}}catch(e){}},650)}catch(e){if($('#barcode-message'))$('#barcode-message').textContent='Sin permiso de cámara. Escribe el código.'}}
async function findBarcode(value){const code=(value||$('#barcode-manual')?.value||'').trim();if(!/^[a-zA-Z0-9]{6,64}$/.test(code))return toast('Introduce un código válido');try{const p=await api('/api/barcodes/lookup',{method:'POST',body:JSON.stringify({code})});changeQty(p.id,1);stopBarcodeCamera();hideModal();toast('Agregado: '+p.name)}catch(e){if(!e.message.includes('sin asociar'))return toast(e.message);stopBarcodeCamera();$('#barcode-message').textContent='Código nuevo: selecciona el producto correspondiente.';$('#barcode-link-area').innerHTML=state.data.products.map(p=>btn(esc(p.name),'barcode-link:'+code+':'+p.id,'secondary full')).join('')}}
async function linkBarcode(code,id){try{const p=await api('/api/barcodes/link',{method:'POST',body:JSON.stringify({code,product_id:id})});changeQty(p.id,1);hideModal();toast('Código asociado y producto agregado')}catch(e){toast(e.message)}}
function render(){if(!state.data){$('#screen').innerHTML='<div class="empty">Sin datos iniciales. Abre la aplicación una vez con el servidor disponible.</div>';return}$('.nav.active')?.classList.remove('active');$(`.nav[data-tab="${state.tab}"]`)?.classList.add('active');$('#role').value=state.role;let f={inicio:home,vender:sell,inventario:inventory,pedidos:purchases,avisos:notices,fiados:credits,corte:cashReport,asesor:businessAssistant}[state.tab]||home;$('#screen').innerHTML=f()}
function showModal(html){$('#modal').innerHTML=`<div class="modal"><button class="button ghost" style="float:right" data-action="close">✕</button>${html}</div>`;$('#modal').hidden=false}
let qrStatusPoller=null;
function stopQrStatusPolling(){if(qrStatusPoller){clearInterval(qrStatusPoller);qrStatusPoller=null}}
function hideModal(){stopBarcodeCamera();stopQrStatusPolling();$('#modal').hidden=true;$('#modal').innerHTML=''}
function watchQrPayment(saleId){
 stopQrStatusPolling();
 let checking=false;
 qrStatusPoller=setInterval(async()=>{
  if(checking||state.activeSale!==saleId)return;
  checking=true;
  try{
   const p=await api('/api/sales/'+saleId+'/status');
   if(p.status==='PAGADA'||p.status==='PAGADA_PRUEBA'){
    stopQrStatusPolling();
    await reload(true);
    showModal('<div class="eyebrow">PEY · Pago confirmado</div><h2>✅ '+(p.status==='PAGADA_PRUEBA'?'Cobro de prueba verificado':'Cobro real verificado')+'</h2><p class="big receipt">'+fmt(p.charged_cents)+'</p><p class="sub">Confirmado por PEY; referencia: '+esc(p.transaction_id||'')+'</p>'+(p.status==='PAGADA_PRUEBA'?'<div class="alert">Este pago de $0.01 es una prueba. No cubre el total comercial del carrito.</div>':'')+btn('Ver mi tienda','tab:inicio','dark full'));
    state.tab='inicio';render();
   }else{
    const label=document.getElementById('qr-payment-status');
    if(label)label.textContent=p.status==='PENDIENTE'?'Esperando pago; consultando la confirmación de PEY…':'Pendiente de revisión: '+p.status;
    if(p.status!=='PENDIENTE')stopQrStatusPolling();
   }
  }catch(e){const label=document.getElementById('qr-payment-status');if(label)label.textContent='Sin confirmación disponible; no asumas que se pagó.'}
  finally{checking=false}
 },3000);
}
async function createSale(){if(!state.online){toast('Sin conexión: el carrito está guardado. Reconecta antes de cobrar.');return}const items=Object.entries(state.cart).filter(([,q])=>q>0).map(([id,qty])=>({id,qty}));if(!items.length)return;
try{const r=await api('/api/sales',{method:'POST',body:JSON.stringify({items,employee:state.role==='Dueño'?'Dueño':state.role})});state.activeSale=r.id;state.cart={};saveCart();await reload(true);showModal(`<div class="eyebrow">Venta #${r.id}</div><h2>Listo para cobrar</h2><h1>${fmt(r.amount_cents)}</h1><p class="sub">El pedido está reservado, pero todavía NO se ha pagado.</p>${btn('Mostrar QR de cobro','make-qr','dark full')}${state.data.config.evaluator_demo?'':'<div class="topgap">'+btn('Solicitar CoDi Push al celular','make-push','secondary full')+'</div>'}<p class="sub">El siguiente paso requiere conexión con el servidor.</p>${!state.data.config.evaluator_demo&&state.data.clients?.length?`<div class="line"></div><h3>O anotar a fiado</h3><select id="credit-client" class="input">${state.data.clients.map(c=>`<option value="${c.id}">${esc(c.name)} · debe ${fmt(c.balance_cents)}</option>`).join('')}</select><div class="topgap">${btn('📒 Fiar esta venta','credit-sale','secondary full')}</div>`:''}`);render()}catch(e){toast(e.message)}}
async function createQr(){
 if(!state.activeSale)return;
 const real=state.data.config.pey_mode==='REAL';
 if(real&&!confirm('Vas a solicitar un QR bancario REAL a PEY. ¿Continuar?'))return;
 try{
 const r=await api(`/api/sales/${state.activeSale}/qr`,{method:'POST'});
 state.qr=r;
 showModal(`<div class="eyebrow">${real?'PEY / CoDi REAL':'MODO DEMO'}</div>
 <h2>${real?'Escanea para pagar':'QR de prueba (NO cobrar)'}</h2>
 <div class="big receipt">${fmt(r.amount_cents)}</div>
 <img class="qr-img" src="data:image/png;base64,${r.qr_image}" alt="${real?'QR de cobro CoDi':'QR DEMO'}"/>
 <div class="${real?'good':'demo-watermark'}">${esc(r.label)}</div>
 ${real?'<p id="qr-payment-status" class="sub" role="status" aria-live="polite">Esperando pago y verificación de PEY…</p>':btn('✅ Simular confirmación','demo-pay','dark full')}`);
 if(real)watchQrPayment(state.activeSale);
 await reload(true)
 }catch(e){toast(e.message)}
}
async function createPush(){
 if(!state.activeSale)return;
 const phone=prompt('Celular del cliente con CoDi: 10 dígitos (sin 52):');
 if(phone===null)return;
 if(!/^[0-9]{10}$/.test(phone))return toast('Deben ser exactamente 10 dígitos');
 const real=state.data.config.pey_mode==='REAL';
 if(real&&!confirm('Esto enviará una solicitud bancaria REAL al número '+phone+'. ¿Continuar?'))return;
 try{
 const r=await api(`/api/sales/${state.activeSale}/push`,{method:'POST',body:JSON.stringify({phone})});
 showModal(`<div class="eyebrow">${real?'PEY CoDi PUSH':'PUSH SIMULADO'}</div><h2>Solicitud enviada / preparada</h2>
 <div class="big receipt">${fmt(r.amount_cents)}</div><div class="${real?'alert':'demo-watermark'}">${esc(r.label)}</div>
 ${real?'<p class="sub">Espera el webhook firmado. El pago sigue PENDIENTE.</p>':btn('Simular pago','demo-pay','dark full')}`);
 await reload(true)
 }catch(e){toast(e.message)}
}
async function demoPay(){try{const r=await api(`/api/sales/${state.activeSale}/demo-confirm`,{method:'POST'});await reload(true);showModal(`<div class="eyebrow">SIMULACIÓN COMPLETADA</div><h2>✅ Venta de prueba registrada</h2><p class="sub">Se actualizaron inventario y avisos dentro de la app.</p><div class="demo-watermark">NO HUBO TRANSFERENCIA BANCARIA REAL</div>${btn('Volver al inicio','tab:inicio','dark full')}`);render()}catch(e){toast(e.message)}}
function orderModal(id){const p=state.data.products.find(x=>x.id===id);showModal(`<div class="eyebrow">Pedido sugerido</div><h2>${esc(p.name)}</h2><p>Existencias: <b>${p.qty}</b>. Pedir sugerido: <b>${p.recommended}</b>.</p><label>Cantidad que quieres pedir<input class="input" id="order-qty" inputmode="numeric" type="number" min="1" max="10000" value="${p.recommended||1}"></label><p class="sub">Proveedor<input class="input" id="supplier" value="Proveedor local" maxlength="90"/></p>${btn('Confirmar pedido','confirm-order:'+id,'dark full')}`)}
async function confirmOrder(id){let q=Number($('#order-qty').value),supplier=$('#supplier').value.trim()||'Proveedor local';if(!Number.isInteger(q)||q<1)return toast('Indica una cantidad válida');try{await api('/api/purchases',{method:'POST',body:JSON.stringify({product_id:id,quantity:q,supplier})});await reload(true);hideModal();state.tab='pedidos';render();toast('Pedido registrado')}catch(e){toast(e.message)}}
function receiveModal(id){const p=state.data.purchases.find(x=>x.id===id);showModal(`<div class="eyebrow">Recepción de proveedor</div><h2>Pedido #${id}</h2><p><b>${esc(p.product_name)}</b> · Solicitado ${p.qty_requested}</p><label>Cantidad que llegó<input id="receive-qty" class="input" type="number" min="1" max="10000" value="${p.qty_requested}"></label><p class="sub">Caducidad (si aplica)<input id="expiry" class="input" type="date"/></p>${btn('Confirmar entrada a inventario','confirm-receive:'+id,'dark full')}`)}
async function confirmReceive(id){const quantity=Number($('#receive-qty').value),expiry=$('#expiry').value||null;if(!Number.isInteger(quantity)||quantity<1)return toast('Cantidad inválida');try{await api(`/api/purchases/${id}/receive`,{method:'POST',body:JSON.stringify({quantity,expiry,employee:state.role})});await reload(true);hideModal();render();toast('Inventario actualizado y dueño avisado')}catch(e){toast(e.message)}}
function changeQty(id,delta){const p=state.data.products.find(x=>x.id===id);const next=Math.max(0,(state.cart[id]||0)+delta);if(delta>0&&next>p.available)return toast('No hay más unidades disponibles');state.cart[id]=next;saveCart();render()}
function action(act){if(act==='load-corte'){loadDailyClose();return}if(act==='ask-business'){askBusiness();return}if(act==='scan-barcode'){openBarcode();return}if(act==='barcode-find'){findBarcode();return}if(act.startsWith('barcode-link:')){const p=act.split(':');linkBarcode(p[1],p[2]);return}if(act==='toggle-sound'){ownerSoundEnabled=!ownerSoundEnabled;lastSoundNoticeId=state.data?.notifications?.[0]?.id||0;toast(ownerSoundEnabled?'Avisos de voz habilitados mientras esta página esté abierta':'Avisos de voz desactivados');render();return}if(act==='close')return hideModal();if(act.startsWith('tab:')){state.tab=act.split(':')[1];hideModal();render();window.scrollTo({top:0,behavior:'smooth'});return}if(act.startsWith('plus:'))return changeQty(act.split(':')[1],1);if(act.startsWith('minus:'))return changeQty(act.split(':')[1],-1);if(act==='create-sale')return createSale();if(act==='make-qr')return createQr();if(act==='make-push')return createPush();if(act==='demo-pay')return demoPay();if(act==='new-client')return newClientModal();if(act==='save-client')return saveClient();if(act==='credit-sale')return creditSale();if(act.startsWith('collect:'))return collectModal(Number(act.split(':')[1]));if(act.startsWith('make-collect:'))return makeCollect(Number(act.split(':')[1]));if(act.startsWith('show-collect:'))return showCollect(Number(act.split(':')[1]));if(act.startsWith('confirm-collect:'))return confirmCollect(Number(act.split(':')[1]));if(act==='copy-collect'){const x=$('#collect-link');x?.select();if(navigator.clipboard?.writeText){navigator.clipboard.writeText(x.value).then(()=>toast('Enlace copiado')).catch(()=>toast('Selecciona y copia el enlace'));}else{toast('Selecciona y copia el enlace');}return;}if(act.startsWith('order:'))return orderModal(act.split(':')[1]);if(act.startsWith('confirm-order:'))return confirmOrder(act.split(':')[1]);if(act.startsWith('receive:'))return receiveModal(Number(act.split(':')[1]));if(act.startsWith('confirm-receive:'))return confirmReceive(Number(act.split(':')[1]))}
document.addEventListener('click',e=>{const button=e.target.closest('[data-action],[data-tab]');if(button)action(button.dataset.action||`tab:${button.dataset.tab}`)});
document.addEventListener('input',e=>{if(e.target.id==='product-search'){const pos=e.target.selectionStart;state.search=e.target.value;render();const input=$('#product-search');input.focus();input.setSelectionRange(pos,pos)}});
$('#role').addEventListener('change',e=>{state.role=e.target.value;localStorage.setItem('role',state.role);render()});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js').catch(()=>{});
reload();setInterval(async()=>{if(document.visibilityState==='visible'){const current=state.data?.notifications?.[0]?.id;await reload(true);if(state.online&&current&&state.data.notifications[0]?.id!==current){toast('🔔 Hay un nuevo aviso');const n=state.data.notifications.find(n=>n.role==='dueno'&&n.id>current&&(/PEY confirmado|PEY PRUEBA REAL/.test(n.message)));if(ownerSoundEnabled&&state.role==='Dueño'&&n&&n.id>lastSoundNoticeId&&'speechSynthesis' in window){lastSoundNoticeId=n.id;const msg=new SpeechSynthesisUtterance('Abarpay: pago bancario verificado');msg.lang='es-MX';speechSynthesis.speak(msg)}}if(!$('#modal').hidden)return;render()}},6000);
