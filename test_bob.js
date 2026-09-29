const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

function loadPush() {
  const store = new Map();
  let permission = "default";
  let registrationCalls = 0;
  const serviceWorkerRegistration = {
    update: async () => {},
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
    }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("push_manager.js", "utf8"), context, { filename: "push_manager.js" });
  return { context, store, serviceWorkerRegistration, get registrationCalls() { return registrationCalls; } };
}

(async () => {
  const p = loadPush();
  assert.strictEqual(p.context.window.BobPush.state().registered, false);
  const state = await p.context.window.BobPush.enable();
  assert.strictEqual(state.registered, true);
  assert.strictEqual(p.registrationCalls, 1);
  p.context.window.BobPush.set("general", true);
  assert.strictEqual(p.context.window.BobPush.allowed("general"), true);
  p.context.window.BobPush.set("trade", true);
  assert.strictEqual(p.context.window.BobPush.allowed("trade"), false);
  p.context.window.BobPush.setActiveTrade(true);
  assert.strictEqual(p.context.window.BobPush.allowed("trade"), true);
  const emitted = await p.context.window.BobPush.emit("trade", "Test", "Body", { signalId: "t1" });
  assert.strictEqual(emitted, true);
  assert.strictEqual(p.serviceWorkerRegistration.lastNotification.title, "Test");

  const degiro = {};
  const degiroContext = { window: degiro };
  vm.createContext(degiroContext);
  vm.runInContext(fs.readFileSync("degiro_assistant.js", "utf8"), degiroContext, { filename: "degiro_assistant.js" });
  const calc = degiro.BobDegiro.riskModel({
    spot: 4000, stop: 3980, riskEur: 5, fxUsdEur: 0.92, leverage: 5
  });
  assert.strictEqual(calc.ok, true);
  assert(Math.abs(calc.maxLossUsd - (5 / 0.92)) < 1e-12);
  assert(calc.approxNotionalEur > 0);
  assert(calc.marginEur > 0);
  assert.strictEqual(degiro.BobDegiro.riskModel({
    spot: 4000, stop: 4000, riskEur: 5, fxUsdEur: 0.92, leverage: 5
  }).ok, false);

  console.log("Bob push + DEGIRO tests: OK");
})().catch(err => { console.error(err); process.exit(1); });
