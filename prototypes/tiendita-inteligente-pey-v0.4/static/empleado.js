'use strict';
const $=selector=>document.querySelector(selector);
const money=c=>new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(Number(c)/100);
const safe=s=>String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&quot;'}[ch]));
let state={employee:sessionStorage.getItem('employee')||'',products:[],cart:{},sale:null,proposal:null,mode:'DEMO',test:false,notices:[],busy:false};
async function api(path,method='GET',data){
 const response=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});
 const json=await response.json();if(!response.ok)throw Error(json.detail||'Error del servidor');return json;
}
function msg(s,error=false){$('#message')?.replaceChildren(document.createTextNode(s));const e=$('#message');if(e)e.className=error?'error':'sub'}
async function refresh(){
 try{let data=await api('/api/employee/bootstrap');state.products=data.products;state.mode=data.config.pey_mode;state.test=data.config.one_cent_test;state.notices=data.notifications;$('#connection').textContent='● Conectado';return true}
 catch(e){$('#connection').textContent='● Sin servidor';msg(e.message,true);return false}
}
function loginScreen(){
 $('#app').innerHTML=`<h1>¿Quién va a cobrar?</h1><div class="card stack"><label>Empleado<select class="input" id="who"><option>Ana</option><option>Luis</option><option>María</option></select></label><label>PIN (sólo para servidor real)<input id="pin" class="input" inputmode="numeric" autocomplete="off" type="password" placeholder="PIN de empleado"></label><button class="button" id="login">Entrar a cobrar</button><p class="sub">En demostración se permite elegir un empleado sin autenticar. No uses datos reales.</p></div><div id="message"></div><div class="links"><a href="/">Administración del dueño</a></div>`;
 $('#login').onclick=async()=>{try{const who=$('#who').value;await api('/api/employee/login','POST',{name:who,pin:$('#pin').value});state.employee=who;sessionStorage.setItem('employee',who);await refresh();draw()}catch(e){msg(e.message,true)}};
}
function draw(){if(!state.employee)return loginScreen();if(state.sale)return drawSale();drawShop()}
function drawShop(){
 const cards=state.products.filter(p=>p.name.toLowerCase().includes(state.filter||'')).map(p=>{
 const q=state.cart[p.id]||0;
 return `<div class="card row"><div><strong>${safe(p.name)}</strong><div class="sub">${money(p.price_cents)} · ${p.available} disponibles</div></div><div class="quantity"><button data-id="${safe(p.id)}" data-delta="-1" aria-label="Quitar ${safe(p.name)}">−</button><b>${q}</b><button data-id="${safe(p.id)}" data-delta="1" aria-label="Agregar ${safe(p.name)}" ${q>=p.available?'disabled':''}>+</button></div></div>`}).join('');
 const total=state.products.reduce((sum,p)=>sum+(state.cart[p.id]||0)*p.price_cents,0);
 $('#app').innerHTML=`<div class="row"><div><h1>Hola, ${safe(state.employee)}</h1><span class="tag">${state.mode==='REAL'?'Cobros PEY reales':state.mode==='BLOQUEADO'?'PEY bloqueado':'Simulación'}</span></div><button class="button alt" style="width:auto" id="logout">Salir</button></div><div id="message"></div><section class="card stack"><h2>Toma el pedido</h2><textarea id="dictation" class="input" rows="2" placeholder="Ej.: dos aguas y un pan"></textarea><button id="microphone" class="button mic">🎤 Dictar pedido</button><button id="interpret" class="button alt">Interpretar pedido</button><small class="sub">La IA, si está configurada, propone productos; tú confirmas cantidades y precios.</small></section><section id="proposal"></section><input id="search" class="input" placeholder="Buscar producto…" value="${safe(state.filter||'')}">${cards}<section class="card stack"><div class="row"><strong>Carrito</strong><span class="big">${money(total)}</span></div>${state.test?'<p class="warn">Prueba: PEY cobrará $0.01; el valor comercial del carrito es independiente.</p>':''}<button id="sale" class="button" ${total<=0?'disabled':''}>Crear venta y cobrar</button></section><div class="links"><a href="/">Administración del dueño</a></div>`;
 $('#logout').onclick=async()=>{try{await api('/api/employee/logout','POST')}catch{}state.employee='';state.cart={};sessionStorage.removeItem('employee');loginScreen()};
 $('#microphone').onclick=startDictation;
 $('#interpret').onclick=interpret;
 $('#search').oninput=e=>{state.filter=e.target.value.toLowerCase();drawShop();$('#search').focus()};
 document.querySelectorAll('[data-id]').forEach(btn=>btn.onclick=()=>{const id=btn.dataset.id,p=state.products.find(x=>x.id===id),next=Math.max(0,(state.cart[id]||0)+Number(btn.dataset.delta));if(next<=p.available){state.cart[id]=next;drawShop()}});
 $('#sale').onclick=createSale;
 if(state.proposal)showProposal();
}
function showProposal(){
 const p=state.proposal,items=p.items.map(x=>`<li>${safe(x.name)}: ${x.qty} × ${money(x.price_cents)}</li>`).join('');
 const missing=p.unmatched.map(x=>`<span class="chip">${safe(x)}</span>`).join('');
 $('#proposal').innerHTML=`<section class="card"><h2>Revisa el pedido propuesto</h2><p class="sub">Interpretación: ${p.source==='OPENAI'?'OpenAI':'reglas locales'}</p><ul>${items||'<li>Sin productos reconocidos</li>'}</ul>${missing?`<p class="warn">Sin identificar: ${missing}. Agrégalos manualmente si corresponde.</p>`:''}<button class="button" id="accept-proposal" ${!p.items.length?'disabled':''}>Agregar al carrito</button><button class="button alt" id="discard-proposal">Descartar</button></section>`;
 $('#accept-proposal').onclick=()=>{for(const item of p.items){const product=state.products.find(x=>x.id===item.id);if(product)state.cart[item.id]=Math.min(product.available,(state.cart[item.id]||0)+item.qty)}state.proposal=null;drawShop()};
 $('#discard-proposal').onclick=()=>{state.proposal=null;drawShop()};
}
async function interpret(){try{state.proposal=await api('/api/cart/parse','POST',{text:$('#dictation').value});showProposal()}catch(e){msg(e.message,true)}}
function startDictation(){
 const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!Recognition){msg('Tu navegador no permite dictado aquí. Puedes escribir el pedido.',true);return}
 const r=new Recognition();r.lang='es-MX';r.interimResults=false;r.maxAlternatives=1;
 r.onresult=ev=>{$('#dictation').value=ev.results[0][0].transcript;interpret()};
 r.onerror=()=>msg('No se pudo escuchar. Usa el campo de texto.',true);
 r.start();msg('Escuchando…');
}
async function createSale(){
 if(state.busy)return;state.busy=true;
 try{const items=Object.entries(state.cart).filter(([,qty])=>qty>0).map(([id,qty])=>({id,qty}));
  const sale=await api('/api/sales','POST',{employee:state.employee,items});state.sale={...sale,status:'PENDIENTE'};
  state.cart={};drawSale();}
 catch(e){msg(e.message,true)}finally{state.busy=false}
}
function drawSale(){const s=state.sale;let paid=s.status==='PAGADA',testPaid=s.status==='PAGADA_PRUEBA',demo=s.status==='DEMO_PAGADA';
 $('#app').innerHTML=`<h1>Venta #${s.id}</h1><section class="card stack"><div class="sub">Valor de productos</div><strong>${money(s.amount_cents)}</strong><div class="sub">Importe solicitado a PEY</div><div class="big">${money(s.charged_cents)}</div>${state.test?'<div class="warn">MODO PRUEBA: cobrar un centavo real, no el valor del carrito.</div>':''}${paid?'<div class="good">✅ PAGO BANCARIO VERIFICADO. Entrega el producto.</div>':testPaid?'<div class="warn">✅ PEY CONFIRMÓ $0.01 DE PRUEBA. No está pagado el valor comercial del carrito.</div>':demo?'<div class="warn">SIMULACIÓN CONFIRMADA. NO SE RECIBIÓ DINERO.</div>':'<div class="warn">PENDIENTE DE PAGO. No entregues todavía.</div>'}<div id="qr-area"></div>${!paid&&!testPaid&&!demo?'<button id="qrbtn" class="button">Generar QR de cobro</button>':''}<button id="reset" class="button alt">Nueva venta</button><div id="message"></div></section>`;
 $('#reset').onclick=()=>{state.sale=null;state.proposal=null;drawShop()};
 if($('#qrbtn'))$('#qrbtn').onclick=requestQr;
 if(s.qr)showQr(s.qr);
}
async function requestQr(){
 if(state.mode==='REAL'&&!confirm('Se generará una solicitud de pago bancario real. ¿Continuar?'))return;
 try{const qr=await api(`/api/sales/${state.sale.id}/qr`,'POST');state.sale.qr=qr;drawSale();startPolling()}
 catch(e){msg(e.message,true)}
}
function showQr(qr){let el=$('#qr-area');if(!el)return;el.innerHTML=`${qr.qr_image?`<img class="qr" alt="QR ${qr.mode==='REAL'?'PEY real':'de prueba'}" src="data:image/png;base64,${qr.qr_image}">`:''}<div class="${qr.mode==='REAL'?'sub':'warn'}">${safe(qr.label)}</div>${qr.mode!=='REAL'?'<button class="button alt" id="confirm-demo">Simular pago (sin dinero)</button>':''}`;
 if($('#confirm-demo'))$('#confirm-demo').onclick=async()=>{try{await api(`/api/sales/${state.sale.id}/demo-confirm`,'POST');await pollStatus()}catch(e){msg(e.message,true)}};
}
let poller=null;
function startPolling(){if(poller)clearInterval(poller);poller=setInterval(pollStatus,3000)}
async function pollStatus(){if(!state.sale)return;
 try{const s=await api(`/api/sales/${state.sale.id}/status`);const before=state.sale.status;state.sale={...state.sale,...s};$('#connection').textContent='● Conectado';if(before!==s.status){drawSale();if(s.status==='PAGADA'||s.status==='PAGADA_PRUEBA'){if('speechSynthesis' in window){const u=new SpeechSynthesisUtterance(s.status==='PAGADA'?'Pago confirmado. Entrega el pedido.':'Pago de prueba confirmado.');u.lang='es-MX';speechSynthesis.speak(u)}clearInterval(poller);poller=null}else if(s.status==='DEMO_PAGADA'){clearInterval(poller);poller=null}}}
 catch(e){$('#connection').textContent='● Reintentando';}
}
window.addEventListener('online',()=>{refresh().then(draw);if(state.sale)pollStatus()});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js').catch(()=>{});
window.addEventListener('offline',()=>$('#connection').textContent='● Sin internet');
(async()=>{const ok=await refresh();if(!ok){loginScreen();return}loginScreen()})();
