// GAP-017: sólo cachear el shell estático; nunca APIs, recibos ni datos bancarios.
const CACHE='abarpay-v06-shell';
const CORE=['/','/empleado','/static/styles.css','/static/app.js','/static/empleado.js','/static/empleado.css','/static/empleado.webmanifest','/manifest.webmanifest','/static/icon-192.png','/static/icon-512.png','/branding/logo.jpeg','/static/abarpay-icon.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE&&(k.startsWith('tiendita-')||k.startsWith('abarpay-'))).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);
  if(url.origin!==self.location.origin||!CORE.includes(url.pathname))return;
  event.respondWith(fetch(event.request).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE).then(c=>c.put(event.request,copy));}return response}).catch(()=>caches.match(event.request)));
});
