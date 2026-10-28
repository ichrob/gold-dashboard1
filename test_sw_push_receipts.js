"use strict";
// Standalone service-worker regression: real click only, durable retry after
// HTTP 503/202, distinct show/click claims, no synthetic handset receipt.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class FakeResponse {
  constructor(text) { this.body = text; }
  async json() { return JSON.parse(this.body); }
}
class FakeCache {
  constructor() { this.items = new Map(); }
  toKey(key) { return typeof key === "string" ? key : new URL(key.url).pathname; }
  async put(key, response) { this.items.set(this.toKey(key), response); }
  async match(key) { return this.items.get(this.toKey(key)); }
  async keys() { return [...this.items.keys()].map(key => ({url:"https://bob.example"+key})); }
  async delete(key) { return this.items.delete(this.toKey(key)); }
}
async function main() {
  const listeners = {}, cachesMap = new Map(), requests = [], notifications = [];
  let status = 503;
  const caches = {
    async open(name) {
      if (!cachesMap.has(name)) cachesMap.set(name, new FakeCache());
      return cachesMap.get(name);
    },
    async keys() { return [...cachesMap.keys()]; },
    async delete(name) { return cachesMap.delete(name); }
  };
  const self = {
    addEventListener(name, handler) { listeners[name] = handler; },
    skipWaiting() {},
    clients: {claim: async () => {}},
    registration: {
      async showNotification(title, options) {notifications.push({title, options});},
      async getNotifications() { return []; }
    }
  };
  const clients = {
    async matchAll() { return []; },
    async openWindow() {}
  };
  const fetch = async (path, opts) => {
    assert.equal(path, "/api/push/device-receipt");
    assert.equal(opts.credentials, "omit");
    assert.equal(opts.method, "POST");
    const body = JSON.parse(opts.body);
    assert.equal(Object.keys(body).sort().join(","),
                 "receiptExpiry,receiptId,receiptProof,receiptState");
    requests.push(body);
    return {status, json:async () => ({stored:status===200})};
  };
  vm.runInNewContext(fs.readFileSync("sw.js","utf8"), {
    self, clients, caches, fetch, Response:FakeResponse,
    URL, Date, Promise, Number, String, JSON, Boolean, console
  }, {filename:"sw.js"});
  assert.equal(typeof listeners.push, "function");
  assert.equal(typeof listeners.notificationclick, "function");
  const settings = await caches.open("bob-push-settings");
  await settings.put("/__bob_push_preferences__", new FakeResponse('{"general":true,"trade":false}'));
  const proof = {receiptId:"a".repeat(32),receiptProof:"b".repeat(64),
                 receiptExpiry:Math.floor(Date.now()/1000)+86400, kind:"general"};
  let pushWait;
  listeners.push({
    data:{json:()=>({title:"Bob",body:"Test message in mock only",data:proof})},
    waitUntil(promise){pushWait=promise;}
  });
  await pushWait;
  assert.equal(notifications.length,1);
  assert.equal(notifications[0].options.actions[0].action, "receipt-confirm");
  assert(requests.every(r=>r.receiptState==="show-resolved"),
    "Browser show must never fabricate a click");
  const queue = await caches.open("bob-push-receipt-queue-v1");
  assert.equal((await queue.keys()).length,1, "503 keeps show receipt for retry");

  let clickWait, closed=false, opened=false;
  const notification = {
    data: {...proof},
    close() {closed=true; this.data=null;}
  };
  listeners.notificationclick({
    action:"receipt-confirm", notification,
    waitUntil(promise){clickWait=promise;}
  });
  await clickWait;
  assert(closed);
  assert.equal((await queue.keys()).length,2, "503 keeps actual click receipt");
  assert(requests.some(r=>r.receiptState==="clicked"));
  assert(!opened, "Acknowledgement action must not navigate");

  status=202;
  let activateWait;
  listeners.activate({waitUntil(p){activateWait=p;}});
  await activateWait;
  assert.equal((await queue.keys()).length,2, "Old 202 queued response is not durable");
  status=200;
  listeners.activate({waitUntil(p){activateWait=p;}});
  await activateWait;
  assert.equal((await queue.keys()).length,0, "200 + stored:true clears queue");
  assert(requests.some(r=>r.receiptState==="show-resolved"));
  assert(requests.some(r=>r.receiptState==="clicked"));

  // Expired proof cannot be retroactively turned into a receipt.
  const prev=requests.length;
  let staleWait;
  listeners.notificationclick({
    action:"receipt-confirm",
    notification:{data:{...proof,receiptExpiry:1},close(){}},
    waitUntil(p){staleWait=p;}
  });
  await staleWait;
  assert.equal(requests.length,prev);
  console.log("push worker receipts: durable show/click retries, privacy, expiry OK");
}
main().catch(error => {console.error(error);process.exitCode=1;});
