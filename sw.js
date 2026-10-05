const CACHE_VERSION = "bob-shell-v16";

self.addEventListener("install", event => { self.skipWaiting(); });
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("bob-") && key !== CACHE_VERSION && key !== "bob-push-settings").map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

function safeJson(event) {
  try { return event.data ? event.data.json() : {}; }
  catch (_) { return { title: "Bob", body: event.data ? event.data.text() : "Neue Benachrichtigung" }; }
}

self.addEventListener("push", event => {
  const data = safeJson(event);
  const details = data.data || data;
  const title = data.title || "Bob";
  const options = {
    body: data.body || "",
    icon: data.icon || "/icon.svg?v=3",
    badge: data.badge || "/icon.svg?v=3",
    tag: data.tag || "bob",
    renotify: Boolean(data.renotify),
    requireInteraction: Boolean(data.requireInteraction),
    data: { url: details.url || "/", kind: details.kind || "general", signalId: details.signalId || null }
  };
  event.waitUntil((async()=>{
    if(Number.isFinite(details.expiresAt)&&Date.now()>=details.expiresAt)return;
    if(details.kind==='general'){
      const cache=await caches.open('bob-push-settings'),response=await cache.match('/__bob_push_preferences__');
      if(!(response&&(await response.json()).general))return;
    }
    if(details.kind==='trade'){
      const cache=await caches.open('bob-push-settings');
      const response=await cache.match('/__bob_push_preferences__');
      const prefs=response?await response.json():{};
      if(!prefs.trade||(!details.test&&!prefs.activeTrade))return;
      if(!details.test&&details.tradeId&&details.tradeId!==prefs.tradeId)return;
    }
    if(String(details.kind||'').startsWith('product-')){
      const cache=await caches.open('bob-push-settings');
      const response=await cache.match('/__bob_push_preferences__');
      const prefs=response?await response.json():{};
      if(prefs.general!==true||!Number.isFinite(details.expiresAt)||Date.now()>=details.expiresAt)return;
    }
    await self.registration.showNotification(title, options);
  })());
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
    const existing = list.find(client => "focus" in client);
    if (existing) {
      existing.postMessage({ type: "BOB_PUSH_CLICK", data: event.notification.data || {} });
      return existing.focus();
    }
    if (clients.openWindow) return clients.openWindow(target);
  }));
});

self.addEventListener("message", event => {
  if (event.data && event.data.type === "BOB_SKIP_WAITING") self.skipWaiting();
  if(event.data?.type==='BOB_PUSH_PREFERENCES')event.waitUntil((async()=>{
    const cache=await caches.open('bob-push-settings');
    const general=event.data.general===true,trade=event.data.trade===true,activeTrade=event.data.activeTrade===true;
    await cache.put('/__bob_push_preferences__',new Response(JSON.stringify({general,trade,activeTrade,tradeId:event.data.tradeId||null})));
    if(!trade||!activeTrade){const notices=await self.registration.getNotifications();notices.filter(n=>n.data?.kind==='trade').forEach(n=>n.close());}
    if(!general){const notifications=await self.registration.getNotifications({tag:'bob-product-selection'});notifications.forEach(n=>n.close());}
  })());
});

// Network-only for the Bob application shell: never let an older service-worker
// cache mask a newly deployed HTML/JS build. API calls are also network-only.
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  const isApi = url.pathname.startsWith("/api/");
  const isShell = url.pathname === "/" || url.pathname.endsWith("/Bob.html") || url.pathname.endsWith(".js") || url.pathname.endsWith(".css");
  if (!isApi && !isShell) return;
  event.respondWith(fetch(event.request, {cache:"no-store"}).catch(() => {
    if (isApi) {
      return new Response(JSON.stringify({error:"Bob API temporarily unreachable"}), {
        status: 503,
        headers: {"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"}
      });
    }
    return new Response("<!doctype html><meta charset=\"utf-8\"><title>Bob wird aktualisiert</title><body style=\"font-family:sans-serif;padding:24px\">Bob wird gerade aktualisiert. Bitte kurz neu laden.</body>", {
      status: 503,
      headers: {"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store"}
    });
  }));
});
