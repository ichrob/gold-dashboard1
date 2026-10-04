const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("Bob.html", "utf8");
if (!html.trim()) throw new Error("Bob.html is empty");

const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (!scripts.length) throw new Error("No inline Bob script found");
scripts.forEach((code, i) => new vm.Script(code, { filename: `Bob-inline-${i + 1}.js` }));

const assets = ["Bob.html","server.py","backtest.py","sw.js","manifest.json","push_manager.js","degiro_assistant.js","test_bob.js"];
for (const file of assets) {
  if (!fs.existsSync(file) || fs.statSync(file).size === 0) throw new Error(`Missing/empty asset: ${file}`);
}

const manifest = JSON.parse(fs.readFileSync("manifest.json", "utf8"));
for (const key of ["name","short_name","start_url","display"]) {
  if (!(key in manifest)) throw new Error(`manifest.json missing required key: ${key}`);
}
if (!fs.readFileSync("manifest.json","utf8").includes("/icon.svg?v=3")) throw new Error("manifest must use bundled SVG icon");
if (fs.readFileSync("server.py","utf8").includes('body = json.dumps({"error": str(exc)')) throw new Error("public /api/live must not leak raw exception text");
if ((fs.readFileSync("Bob.html","utf8").match(/var liveBundleCache=null, liveBundleAt=0;/g)||[]).length !== 1) throw new Error("live bundle cache must have exactly one declaration");
if (fs.readFileSync("Bob.html","utf8").indexOf("var liveBundleCache=null, liveBundleAt=0;") > fs.readFileSync("Bob.html","utf8").indexOf("async function loadData")) throw new Error("live bundle cache must be declared before loadData");
if (fs.readFileSync("Bob.html","utf8").includes("Cannot access 'liveBundleCache' before initialization")) throw new Error("stale TDZ error text must not be present");
if (!fs.readFileSync("Bob.html","utf8").includes("BobDegiro.riskModel({spot:lastPrice,stop:sm.stop,riskEur:euro,fxUsdEur:fx,leverage:lev})")) throw new Error("risk calculator must use shared DEGIRO risk model");
if (!fs.readFileSync("sw.js","utf8").includes("/icon.svg?v=3")) throw new Error("service worker must use bundled SVG icon");
if (/icon-192\\.png|icon-512\\.png/.test(fs.readFileSync("Bob.html","utf8"))) throw new Error("Bob.html still references removed PNG icons");

console.log(`Bob JS/HTML/assets validation: OK (${scripts.length} inline script block)`);

if (fs.readFileSync("Bob.html","utf8").includes("liveHistoryCache")) throw new Error("obsolete live history cache state must not exist");

if (!fs.readFileSync("Bob.html","utf8").includes("!A.ready||!C.length||!Number.isFinite(A.at)")) throw new Error("signal direction must require ready analysis");
if (fs.readFileSync("Bob.html","utf8").includes("A.score=score; A.ready=ready;")) throw new Error("advanced analysis must not reference out-of-scope ready variable");
if (!fs.readFileSync("Bob.html","utf8").includes("A.ready=Boolean(C.length>=200&&A.e20!=null&&A.e50!=null&&A.e200!=null);")) throw new Error("advanced analysis readiness guard missing");
if (!fs.readFileSync("Bob.html","utf8").includes("const required=200;")) throw new Error("MTF must require full 200-bar history");
if (!fs.readFileSync("Bob.html","utf8").includes("timeframeScore(bars,tf)")) throw new Error("MTF freshness must be timeframe-aware");

if (!fs.readFileSync("server.py","utf8").includes('"xaus_is_spot": spot_source == "XAUS · live"')) throw new Error("spot provenance flag missing");
if (!fs.readFileSync("server.py","utf8").includes('"is_genuine_xauusd_spot": is_spot')) throw new Error("genuine spot metadata missing");
if (!fs.readFileSync("server.py","utf8").includes("Never promote technical/futures history to the XAU/USD spot field.")) throw new Error("synthetic spot fallback guard missing");
if (!fs.readFileSync("Bob.html","utf8").includes("REFERENZ · GC=F")) throw new Error("UI must distinguish futures fallback from XAU/USD spot");

if (!fs.readFileSync("Bob.html","utf8").includes("var C=[], lastPrice=0, A={}, lastMtfAt=0, liveFxUsdEur=null,")) throw new Error("live analysis/FX state must be hoisted");

if (!fs.readFileSync("server.py","utf8").includes("https://api.goldprice.dev/v1/spot/XAU-USD-SPOT")) throw new Error("spot endpoint fallback missing");

if (!fs.readFileSync("Bob.html","utf8").includes("navigator.serviceWorker.addEventListener(\"controllerchange\"")) throw new Error("service worker update reload guard missing");

if (!fs.readFileSync("Bob.html","utf8").includes("https://xaus.com/api/v1/spot")) throw new Error("browser live spot fallback missing");

if (!fs.readFileSync("Bob.html","utf8").includes("Math.abs(pct)>0.50")) throw new Error("spot/futures divergence must use absolute spread");
