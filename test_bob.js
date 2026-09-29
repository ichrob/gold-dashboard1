const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

function loadPush() {
  const store = new Map();
  let permission = "default";
  let registrationCalls = 0;
  let pushSubscription = null;
  const fetchCalls = [];
  const serviceWorkerRegistration = {
    update: async () => {},
    pushManager: {
      getSubscription: async () => pushSubscription,
      subscribe: async () => {
        pushSubscription = {
          toJSON: () => ({
            endpoint: "https://push.example/sub/test",
            keys: { p256dh: "p256dh", auth: "auth" }
          })
        };
        return pushSubscription;
      }
    },
    showNotification: async (title, options) => {
      serviceWorkerRegistration.lastNotification = { title, options };
    }
  };
  const context = {
    window: {},
    localStorage: {
      getItem: key => store.has(key) ? store.get(key) : null,
      setItem: (key, value) => store.set(key, value)
    },
    Notification: {
      get permission() { return permission; },
      requestPermission: async () => { permission = "granted"; return permission; }
    },
    navigator: {
      serviceWorker: {
        register: async () => { registrationCalls += 1; return serviceWorkerRegistration; },
        ready: Promise.resolve(serviceWorkerRegistration)
      }
    },
    fetch: async (url, options={}) => {
      fetchCalls.push({url, options});
      if (url === "/api/push/vapid-public-key") return { ok: false, status: 404, json: async () => ({ error: "Push-Service disabled in free mode" }) };
      if (url === "/api/push/subscribe") return { ok: false, status: 404, json: async () => ({ error: "Push-Service disabled in free mode" }) };
      if (url === "/api/push/send") return { ok: false, status: 404, json: async () => ({ error: "Push-Service disabled in free mode" }) };
      throw new Error("Unexpected fetch: " + url);
    }
  };
  context.window.Notification = context.Notification;
  context.window.navigator = context.navigator;
  context.window.fetch = context.fetch;
  context.window.isSecureContext = true;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("push_manager.js", "utf8"), context, { filename: "push_manager.js" });
  return { context, store, serviceWorkerRegistration, fetchCalls, get registrationCalls() { return registrationCalls; } };
}

const serverSource = fs.readFileSync("server.py", "utf8");
const bobSource = fs.readFileSync("Bob.html", "utf8");
const renderSource = fs.readFileSync("render.yaml", "utf8");
assert.strictEqual((serverSource.match(/def build_live_bundle\(\):/g) || []).length, 1);
assert(bobSource.includes("Live XAU/USD must be rendered independently from technical history."));
assert(bobSource.includes("LIVE-PREIS · TECHNIK WARTET"));
assert(bobSource.includes("var liveBundleCache=null, liveBundleAt=0;"));
assert(bobSource.indexOf("var liveBundleCache=null, liveBundleAt=0;") < bobSource.lastIndexOf("loadData();"));
assert(serverSource.indexOf('if path == "/api/live":') < serverSource.indexOf('auth = self.headers.get("Authorization", "")'));

assert(renderSource.includes("plan: free"));
assert(!renderSource.includes("type: cron"));
assert(!renderSource.includes("type: worker"));
assert((serverSource.match(/if path == "\/api\/live":/g) || []).length === 1);
assert((serverSource.match(/if path == "\/sw\.js"/g) || []).length === 1);
assert((serverSource.match(/if path == "\/manifest\.json"/g) || []).length === 1);
assert(!/icon-192\\.png|icon-512\\.png/.test(fs.readFileSync("manifest.json","utf8")));
assert(fs.readFileSync("manifest.json","utf8").includes("/icon.svg?v=3"));



(async () => {
  const p = loadPush();
  assert.strictEqual(p.context.window.BobPush.state().registered, false);
  const state = await p.context.window.BobPush.enable();
  assert.strictEqual(state.registered, true);
  assert.strictEqual(state.serverRegistered, false);
  assert.strictEqual(p.registrationCalls, 1);
  assert(p.fetchCalls.some(call => call.url === "/api/push/vapid-public-key"));
  p.context.window.BobPush.set("general", true);
  assert.strictEqual(p.context.window.BobPush.allowed("general"), true);
  p.context.window.BobPush.set("trade", true);
  assert.strictEqual(p.context.window.BobPush.allowed("trade"), false);
  p.context.window.BobPush.setActiveTrade(true);
  assert.strictEqual(p.context.window.BobPush.allowed("trade"), true);
  const emitted = await p.context.window.BobPush.emit("trade", "Test", "Body", { signalId: "t1" });
  assert.strictEqual(emitted, true);
  assert.strictEqual(p.fetchCalls.some(call => call.url === "/api/push/send"), false);
  assert.strictEqual(p.serviceWorkerRegistration.lastNotification.title, "Test");

  const degiro = {};
  const degiroContext = { window: degiro };
  vm.createContext(degiroContext);
  vm.runInContext(fs.readFileSync("degiro_assistant.js", "utf8"), degiroContext, { filename: "degiro_assistant.js" });
  const calc = degiro.BobDegiro.riskModel({ spot: 4000, stop: 3980, riskEur: 5, fxUsdEur: 0.92, leverage: 5 });
  assert.strictEqual(calc.ok, true);
  assert(Math.abs(calc.maxLossUsd - (5 / 0.92)) < 1e-12);
  assert(calc.approxNotionalEur > 0);
  assert(calc.marginEur > 0);
  assert.strictEqual(degiro.BobDegiro.riskModel({ spot: 4000, stop: 4000, riskEur: 5, fxUsdEur: 0.92, leverage: 5 }).ok, false);

  console.log("Bob push + DEGIRO tests: OK");
})().catch(err => { console.error(err); process.exit(1); });
