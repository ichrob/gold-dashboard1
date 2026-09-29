const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("Bob.html", "utf8");
if (!html.trim()) throw new Error("Bob.html is empty");

const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (!scripts.length) throw new Error("No inline Bob script found");
scripts.forEach((code, i) => new vm.Script(code, { filename: `Bob-inline-${i + 1}.js` }));

const assets = ["Bob.html","server.py","backtest.py","sw.js","manifest.json","icon-192.png","icon-512.png","push_manager.js","degiro_assistant.js","test_bob.js"];
for (const file of assets) {
  if (!fs.existsSync(file) || fs.statSync(file).size === 0) throw new Error(`Missing/empty asset: ${file}`);
}

const manifest = JSON.parse(fs.readFileSync("manifest.json", "utf8"));
for (const key of ["name","short_name","start_url","display"]) {
  if (!(key in manifest)) throw new Error(`manifest.json missing required key: ${key}`);
}

console.log(`Bob JS/HTML/assets validation: OK (${scripts.length} inline script block)`);
