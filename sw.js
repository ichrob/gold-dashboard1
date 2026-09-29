const CACHE_VERSION = "bob-shell-v8";

self.addEventListener("install", event => { self.skipWaiting(); });
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("bob-") && key !== CACHE_VERSION).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

function safeJson(event) {
  try { return event.data ? event.data.json() : {}; }
  catch (_) { return { title: "Bob", body: event.data ? event.data.text() : "Neue Benachrichtigung" }; }
}

self.addEventListener("push", event => {
  const data = safeJson(event);
  const title = data.title || "Bob";
  const options = {
    body: data.body || "",
    icon: data.icon || "/icon.svg?v=3",
    badge: data.badge || "/icon.svg?v=3",
    tag: data.tag || "bob",
    renotify: Boolean(data.renotify),
    requireInteraction: Boolean(data.requireInteraction),
    data: { url: data.url || "/", kind: data.kind || "general", signalId: data.signalId || null }
  };
  event.waitUntil(self.registration.showNotification(title, options));
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
});

// Network-first prevents an old Bob shell from surviving a deployment.
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response && response.ok && (url.pathname === "/" || url.pathname.endsWith("Bob.html") || url.pathname.endsWith(".js"))) {
      const copy = response.clone();
      caches.open(CACHE_VERSION).then(cache => cache.put(event.request, copy)).catch(() => {});
    }
    return response;
  }).catch(() => caches.match(event.request).then(r => r || caches.match("/Bob.html"))));
});
