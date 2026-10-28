const CACHE_VERSION = "bob-shell-v27";
const RECEIPT_CACHE = "bob-push-receipt-queue-v1";

self.addEventListener("install", event => { self.skipWaiting(); });
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith("bob-") && key !== CACHE_VERSION && key !== "bob-push-settings" && key !== RECEIPT_CACHE).map(key => caches.delete(key)));
    await self.clients.claim();
    await flushQueuedReceipts();
  })());
});

// Browser showNotification() success is NOT proof of the Android notification
// tray; only a real notificationclick may create a clicked receipt. Cache
// transient failures so a click is not lost merely because the network is down.
function validReceipt(details, receiptState) {
  const id = details?.receiptId, proof = details?.receiptProof, exp = details?.receiptExpiry;
  if (typeof id !== 'string' || !/^[0-9a-f]{32}$/.test(id) ||
      typeof proof !== 'string' || !/^[0-9a-f]{64}$/.test(proof) ||
      !Number.isSafeInteger(exp) || exp * 1000 < Date.now() ||
      !['show-resolved', 'clicked'].includes(receiptState)) return null;
  return {receiptId:id, receiptExpiry:exp, receiptProof:proof, receiptState};
}
function receiptKey(receipt) {
  return '/__bob_pending_push_receipt__/' + receipt.receiptId + '/' + receipt.receiptState;
}
async function persistReceipt(receipt) {
  try {
    const response = await fetch('/api/push/device-receipt', {
      method:'POST', credentials:'omit', cache:'no-store',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(receipt)
    });
    if (response.status !== 200) return false; // 202 was only queued: do not discard
    const result = await response.json();
    return result?.stored === true;
  } catch (_) { return false; }
}
async function flushQueuedReceipts(cache = null) {
  try {
    cache = cache || await caches.open(RECEIPT_CACHE);
    const keys = await cache.keys();
    // Strictly bounded work and storage: never block push delivery indefinitely.
    for (const key of keys.slice(0, 8)) {
      try {
        const saved = await cache.match(key);
        const raw = saved && await saved.json();
        const receipt = validReceipt(raw, raw?.receiptState);
        if (!receipt || (await persistReceipt(receipt))) await cache.delete(key);
      } catch (_) { await cache.delete(key); }
    }
    // If storage was unavailable for a long period, bound to 128 small claims.
    if (keys.length > 128) {
      for (const key of keys.slice(0, keys.length - 128)) await cache.delete(key);
    }
  } catch (_) { /* Missing storage is not a confirmed delivery. */ }
}
async function reportPushReceipt(details, receiptState) {
  const receipt = validReceipt(details, receiptState);
  if (!receipt) return;
  let cache = null;
  try {
    cache = await caches.open(RECEIPT_CACHE);
    await cache.put(receiptKey(receipt), new Response(JSON.stringify(receipt)));
  } catch (_) { /* Still try the network without claiming persistence. */ }
  if (await persistReceipt(receipt) && cache) {
    try { await cache.delete(receiptKey(receipt)); } catch (_) {}
  }
  if (cache) await flushQueuedReceipts(cache);
}

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
    icon: data.icon || "/icon.svg?v=4",
    badge: data.badge || "/icon.svg?v=4",
    tag: data.tag || "bob",
    renotify: Boolean(data.renotify),
    actions: [{action:"receipt-confirm", title:"Empfang bestätigen"}],
    requireInteraction: Boolean(data.requireInteraction),
    data: { url: details.url || "/", kind: details.kind || "general", signalId: details.signalId || null, tradeId:details.tradeId||null, riskOnly:details.riskOnly===true, expiresAt:details.expiresAt, receiptId:details.receiptId, receiptExpiry:details.receiptExpiry, receiptProof:details.receiptProof }
  };
  event.waitUntil((async()=>{
    if(Number.isFinite(details.expiresAt)&&Date.now()>=details.expiresAt)return;
    if(details.riskOnly===true){
      const cache=await caches.open('bob-push-settings'),response=await cache.match('/__bob_push_preferences__');
      if(!Number.isFinite(details.expiresAt)||!response)return;
      const preferences=await response.json();
      if((details.kind==='general'?(preferences.riskMarket??preferences.risk):preferences.risk)!==true)return;
    }
    if(details.kind==='general'){
      const cache=await caches.open('bob-push-settings'),response=await cache.match('/__bob_push_preferences__');
      if(!(response&&(await response.json()).general))return;
    }
    if(details.kind==='trade'){
      const cache=await caches.open('bob-push-settings');
      const response=await cache.match('/__bob_push_preferences__');
      const prefs=response?await response.json():{};
      if(details.tradeId&&await cache.match('/__bob_closed_trade__/'+encodeURIComponent(details.tradeId)))return;
      if(!prefs.trade)return;
      // Server-journal plans are shared across this private Bob account.
      // Keep the device opt-out and protect a different locally active trade.
      const journal=details.journalManaged===true&&typeof details.tradeId==='string'&&!!details.tradeId;
      if(!details.test&&!journal&&!prefs.activeTrade)return;
      if(!details.test&&details.tradeId&&details.tradeId!==prefs.tradeId&&(!journal||prefs.activeTrade))return;
    }
    if(String(details.kind||'').startsWith('product-')){
      const cache=await caches.open('bob-push-settings');
      const response=await cache.match('/__bob_push_preferences__');
      const prefs=response?await response.json():{};
      if(prefs.general!==true||!Number.isFinite(details.expiresAt)||Date.now()>=details.expiresAt)return;
    }
    await self.registration.showNotification(title, options);
    await reportPushReceipt(details, 'show-resolved');
  })());
});

self.addEventListener("notificationclick", event => {
  // Snapshot the notification metadata BEFORE close() or a browser navigation.
  const details = event.notification.data || {};
  const target = details.url || "/";
  event.notification.close();
  event.waitUntil(Promise.all([
    reportPushReceipt(details, "clicked"),
    // A dedicated acknowledgement action should not unexpectedly open Bob;
    // a normal notification tap retains the existing navigation behavior.
    event.action === "receipt-confirm" ? Promise.resolve() :
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      const existing = list.find(client => "focus" in client);
      if (existing) {
        existing.postMessage({ type: "BOB_PUSH_CLICK", data: details });
        return existing.focus();
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  ]));
});

self.addEventListener("message", event => {
  if (event.data && event.data.type === "BOB_SKIP_WAITING") self.skipWaiting();
  if(event.data?.type==='BOB_PUSH_PREFERENCES')event.waitUntil((async()=>{
    await flushQueuedReceipts();
    const cache=await caches.open('bob-push-settings');
    const general=event.data.general===true,trade=event.data.trade===true,activeTrade=event.data.activeTrade===true;
    await cache.put('/__bob_push_preferences__',new Response(JSON.stringify({general,trade,activeTrade,risk:event.data.risk===true,riskMarket:(event.data.riskMarket??event.data.risk)===true,tradeId:event.data.tradeId||null})));
    {const notices=await self.registration.getNotifications();notices.filter(n=>n.data?.riskOnly===true&&(n.data.kind==='general'?(event.data.riskMarket??event.data.risk)!==true:event.data.risk!==true)).forEach(n=>n.close());}
    if(!trade||!activeTrade){const notices=await self.registration.getNotifications();notices.filter(n=>n.data?.kind==='trade').forEach(n=>n.close());}
    if(!general){const notifications=await self.registration.getNotifications({tag:'bob-product-selection'});notifications.forEach(n=>n.close());}
  })());
  if(event.data?.type==='BOB_TRADE_CLOSED'&&typeof event.data.tradeId==='string')event.waitUntil((async()=>{
    const cache=await caches.open('bob-push-settings');
    const id=event.data.tradeId;
    await cache.put('/__bob_closed_trade__/'+encodeURIComponent(id),new Response('closed'));
    const notices=await self.registration.getNotifications();
    notices.filter(n=>n.data?.kind==='trade'&&n.data.tradeId===id).forEach(n=>n.close());
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
