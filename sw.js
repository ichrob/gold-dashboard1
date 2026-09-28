const CACHE_VERSION = "bob-icons-v2";
self.addEventListener("install", event => { self.skipWaiting(); });
self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {
    data = { title: "Bob", body: event.data ? event.data.text() : "Neue Benachrichtigung" };
  }
  const title = data.title || "Bob";
  const options = { body: data.body || "", icon: data.icon || "/icon.svg?v=2", badge: data.badge || "/icon.svg?v=2", tag: data.tag || "bob", data: data.url || "/" };
  event.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = event.notification.data || "/";
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
    const existing = list.find(client => "focus" in client);
    if (existing) return existing.focus();
    if (clients.openWindow) return clients.openWindow(target);
  }));
});