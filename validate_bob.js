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
if (!fs.readFileSync("sw.js","utf8").includes("/icon.svg?v=3")) throw new Error("service worker must use bundled SVG icon");
if (/icon-192\\.png|icon-512\\.png/.test(fs.readFileSync("Bob.html","utf8"))) throw new Error("Bob.html still references removed PNG icons");

console.log(`Bob JS/HTML/assets validation: OK (${scripts.length} inline script block)`);
