self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {
    data = { title: "Bob", body: event.data ? event.data.text() : "Neue Benachrichtigung" };
  }
  const title = data.title || "Bob";
  const options = {
    body: data.body || "",
    icon: data.icon || "",
    badge: data.badge || "",
    tag: data.tag || "bob",
    data: data.url || "/"
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = event.notification.data || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      const existing = list.find(client => "focus" in client);
      if (existing) return existing.focus();
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});