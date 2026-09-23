const CACHE='yazory-static-v3';
const SHELL=['/static/style.css','/static/pages.js','/static/mobile-app.js','/static/favicon-192.png','/static/apple-touch-icon.png','/static/pwa-icon-512.png','/static/yazory-logo-corrected.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))));self.clients.claim();});
self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==location.origin)return;
  // Private HTML, portals, APIs, payments, and form submissions stay network-only.
  if(request.mode==='navigate')return;
  if(url.pathname.startsWith('/static/')){
    // Styles and scripts must follow deployments. A cached older stylesheet
    // can leave newly rendered forms and navigation without their layout.
    if(request.destination==='style'||request.destination==='script'){
      event.respondWith(fetch(request).then(response=>{
        if(response.ok&&response.type==='basic'){
          const copy=response.clone();
          event.waitUntil(caches.open(CACHE).then(cache=>cache.put(request,copy)));
        }
        return response;
      }).catch(()=>caches.match(request)));
      return;
    }
    event.respondWith(caches.match(request).then(cached=>cached||fetch(request).then(response=>{if(!response.ok||response.type!=='basic')return response;const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(request,copy));return response;})));
  }
});
