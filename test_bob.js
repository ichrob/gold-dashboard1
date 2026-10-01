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
    window: { addEventListener: (event, handler) => { if (event === "load") Promise.resolve().then(handler); } },
    setTimeout: () => 0,
    clearTimeout: () => {},
    setInterval: () => 0,
    clearInterval: () => {},
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
assert(bobSource.includes("live spot price is the primary heartbeat of Bob."));
assert(bobSource.includes("Secondary spot/futures"));
assert(bobSource.includes("DEGIRO-Produktprüfung"));
assert(bobSource.includes("checkDgProduct()"));
assert(bobSource.includes("maybePushAnalysisAlerts()"));
assert(bobSource.includes("LIVE-PREIS · TECHNIK WARTET"));
assert(bobSource.includes("var liveBundleCache=null, liveBundleAt=0;"));
assert(bobSource.indexOf("var liveBundleCache=null, liveBundleAt=0;") < bobSource.lastIndexOf("loadData();"));
const sensitiveGate = serverSource.indexOf('protected_api_path = path in ("/api/live", "/api/mtf", "/api/degiro/enrich")');
assert(sensitiveGate >= 0);
assert(sensitiveGate < serverSource.indexOf('if path == "/api/live":'));
assert(sensitiveGate < serverSource.indexOf('if path == "/api/mtf":'));
assert(sensitiveGate < serverSource.indexOf('if path == "/api/degiro/enrich":'));
assert(serverSource.includes('self.send_response(401)'));
assert(!serverSource.includes('WWW-Authenticate')); // HTML login replaces native browser challenge
assert(serverSource.includes('"xaus_is_spot": spot_source == "XAUS · live"'));
assert(serverSource.includes('"is_genuine_xauusd_spot": is_spot'));
assert(serverSource.includes('Never promote technical/futures history to the XAU/USD spot field.'));
assert(serverSource.includes('"source": (spot_source or "keine Spotquelle") + " + Yahoo Finance GC=F technische Referenz"'));
assert(serverSource.includes("script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"));
assert(serverSource.includes("worker-src 'self' blob:"));
assert(serverSource.includes('"script-src \'self\' \'unsafe-inline\' https://cdn.jsdelivr.net; "'));
assert(serverSource.includes('if len(values) < period + 2:\n        return None'));
assert(serverSource.includes('reason":"zu wenig Historie für RSI"'));

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

  const htmlSource = fs.readFileSync("Bob.html", "utf8");
  const scoreBlock = htmlSource.slice(htmlSource.indexOf(" let pts=0,max=0,details=[];"),htmlSource.indexOf(" const atrPct=",htmlSource.indexOf(" let pts=0,max=0,details=[];")));
  const scoring = vm.runInNewContext(scoreBlock + "\n({pts,max,weights:w})", {
    currentRegime:()=>"TREND", getMtfState:()=>({overall:"LONG"}),
    fibonacciModel:()=>({valid:false}), A:{e20:3,e50:2,e200:1,macd:2,sig:1,R:60,at:10},
    p:4000,b:{mid:3900},st:60
  });
  assert(Number.isFinite(scoring.pts));
  assert(scoring.max>0);
  assert.strictEqual(Object.values(scoring.weights).reduce((a,b)=>a+b,0),100);
  const degiro = {};
  const degiroContext = { window: degiro };
  vm.createContext(degiroContext);
  vm.runInContext(fs.readFileSync("degiro_assistant.js", "utf8"), degiroContext, { filename: "degiro_assistant.js" });
  const detail = degiro.BobDegiro.detailScreenshotData("Kursdaten\nGeld € 24,81 Brief € 24,82\nGeld Vol. 10K Brief Vol. 10K\n30/09/2026 21:43\nSymbol | ISIN DE000FG4JXV7\nEUR", "DE000FG4JXV7");
  assert.strictEqual(detail.ok,true);
  assert.strictEqual(detail.bid,24.81);assert.strictEqual(detail.ask,24.82);
  assert.strictEqual(detail.spread,"0.01");assert.strictEqual(detail.price,"24.82");
  assert.strictEqual(detail.sourceTime,"30/09/2026 21:43");
  assert.strictEqual(detail.leverage,""); // chart points and account balance are not leverage
  assert.strictEqual(degiro.BobDegiro.detailScreenshotData("DE000PJ9NCK0\nGeld 3,00 Brief 3,01", "DE000FG4JXV7").ok,false);
  assert.strictEqual(degiro.BobDegiro.detailScreenshotData("DE000FG4JXV7 DE000PJ9NCK0", "DE000FG4JXV7").ok,false);
  assert.strictEqual(degiro.BobDegiro.detailScreenshotData("Geld 3,00 Brief 3,01", "DE000FG4JXV7").ok,false);
  assert.strictEqual(degiro.BobDegiro.detailScreenshotData("DE000FG4JXV7 EUR Geld 4,00 Brief 3,00", "DE000FG4JXV7").ok,false);
  const header=degiro.BobDegiro.detailScreenshotData("SG Gold Turbo Classic Put BAR\n@ 4460 BP 4460 Bv 10\n18/12/2026 LV 14.01\nSCG | DE000FG4JXV7 | EUR\n€24,68 +1,97", "DE000FG4JXV7");
  assert.strictEqual(header.direction,"SHORT");assert.strictEqual(header.ko,"4460");assert.strictEqual(header.leverage,"14.01");assert.strictEqual(header.price,"24.68");
  assert.strictEqual(header.sourceTime,""); // expiry is never a quote time
  assert(degiro.BobDegiro.missingProductData({isin:"DE000FG4JXV7",productDirection:"SHORT",price:24.82,leverage:14.01,ko:4460,spread:0.01}).includes("bestätigte aktuelle Kursdaten mit Zeitstempeln"));
  const calc = degiro.BobDegiro.riskModel({ spot: 4000, stop: 3980, riskEur: 5, fxUsdEur: 0.92, leverage: 5 });
  assert.strictEqual(calc.ok, true);
  assert(Math.abs(calc.maxLossUsd - (5 / 0.92)) < 1e-12);
  assert(calc.approxNotionalEur > 0);
  const fit = degiro.BobDegiro.evaluateProduct({spot:4000,ko:3900,leverage:5,spread:1,direction:"LONG",productDirection:"LONG"});
  assert.strictEqual(fit.ok,true);
  assert.strictEqual(fit.fit,true);
  assert(fit.koDistancePct > 0);
  const mismatch = degiro.BobDegiro.evaluateProduct({spot:4000,ko:4100,leverage:5,direction:"LONG",productDirection:"SHORT"});
  assert.strictEqual(mismatch.fit,false);
  assert(calc.marginEur > 0);
  assert.strictEqual(degiro.BobDegiro.riskModel({ spot: 4000, stop: 4000, riskEur: 5, fxUsdEur: 0.92, leverage: 5 }).ok, false);
  const shortCalc = degiro.BobDegiro.riskModel({ spot: 4000, stop: 4020, riskEur: 5, fxUsdEur: 0.92, leverage: 5, ko: 4100 });
  assert.strictEqual(shortCalc.ok, true);
  assert(shortCalc.approxNotionalEur > 0);
  assert(shortCalc.warnings.some(w => w.includes("KO-Level") ) === false);
  const longKo = degiro.BobDegiro.riskModel({ spot: 4000, stop: 3980, riskEur: 5, fxUsdEur: 0.92, leverage: 5, ko: 4010 });
  assert(longKo.warnings.some(w => w.includes("KO-Level")));
  const tightKo = degiro.BobDegiro.riskModel({ spot: 4000, stop: 3980, riskEur: 5, fxUsdEur: 0.92, leverage: 5, ko: 3950 });
  assert(tightKo.warnings.some(w => w.includes("unter 2%")));
  const strongLong = degiro.BobDegiro.technicalQuality({direction:"LONG",trend:"LONG",trend2:"LONG",mtf:"LONG",rsi:60,hist:1,adx:30,momentum:1});
  assert(strongLong.score > 80);
  const weakLong = degiro.BobDegiro.technicalQuality({direction:"LONG",trend:"LONG",trend2:"LONG",mtf:"LONG",rsi:72,hist:1,adx:22,momentum:-1});
  assert(weakLong.score < strongLong.score);
  assert(weakLong.reasons.some(x => x.includes("Momentum widerspricht")));
  const conflictedProduct = degiro.BobDegiro.evaluateProduct({spot:4000,ko:3800,leverage:4,direction:"LONG",productDirection:"LONG",trend:"SHORT",trend2:"SHORT",mtf:"SHORT",rsi:80,hist:-1,adx:10,momentum:-1});
  assert(conflictedProduct.conflictCount >= 3);
  assert(conflictedProduct.warnings.some(w => w.includes("Mehrere technische Signale")));
  assert(conflictedProduct.confidence <= conflictedProduct.setupScore);
  const conflictedLong = degiro.BobDegiro.technicalQuality({direction:"LONG",trend:"SHORT",trend2:"SHORT",mtf:"SHORT",rsi:80,hist:-1,adx:10});
  assert(conflictedLong.score < 30);
  const neutralQuality = degiro.BobDegiro.technicalQuality({direction:"NEUTRAL",trend:"LONG",mtf:"SHORT",rsi:60,hist:1,adx:30});
  assert.strictEqual(neutralQuality.score, 50);
  assert(strongLong.reasons.some(x => x.includes("MTF")));
  assert(conflictedLong.reasons.some(x => x.includes("widerspricht")));
  const ranked = degiro.BobDegiro.rankProducts([
    {name:"Long A", productDirection:"LONG", spot:4000, ko:3800, leverage:4, spread:0.5},
    {name:"Long B", productDirection:"LONG", spot:4000, ko:3990, leverage:8, spread:1},
    {name:"Short C", productDirection:"SHORT", spot:4000, ko:4100, leverage:5, spread:0.5},
    {name:"Long D", productDirection:"LONG", spot:4000, ko:3700, leverage:5, spread:0.5}
  ], {direction:"LONG", atr:20, spot:4000});
  assert.strictEqual(ranked.candidates.length, 2);
  assert.strictEqual(ranked.candidates[0].name, "Long A");
  assert(ranked.candidates.every(p => p.productDirection === "LONG"));
  const neutralRank = degiro.BobDegiro.rankProducts([{name:"Long A",productDirection:"LONG",spot:4000,ko:3800,leverage:4,spread:0.5},{name:"Short C",productDirection:"SHORT",spot:4000,ko:4100,leverage:5,spread:0.5}], {direction:"NEUTRAL",atr:20,spot:4000});
  assert.strictEqual(neutralRank.tradeable, false);
  assert.strictEqual(neutralRank.candidates.length, 0);
  const gated = degiro.BobDegiro.rankProducts([{name:"Long Weak",productDirection:"LONG",spot:4000,ko:3800,leverage:4,spread:0.5}], {direction:"LONG",atr:20,spot:4000,trend:"SHORT",trend2:"SHORT",mtf:"SHORT",rsi:80,hist:-1,adx:10,momentum:-1});
  assert.strictEqual(gated.tradeable, false);
  assert(gated.gateReason.includes("Technischer Konsens"));
  const parsed = degiro.BobDegiro.parseScreenshotCandidates("Gold Turbo LONG ISIN DE000ABC1234 Hebel 5x KO 3900\nGold Turbo SHORT ISIN DE000XYZ9876 Hebel 4x KO 4100");
  assert.strictEqual(parsed.length, 2);
  assert.strictEqual(parsed[0].isin, "DE000ABC1234");
  assert.strictEqual(parsed[0].direction, "LONG");
  assert.strictEqual(parsed[1].isin, "DE000XYZ9876");
  assert.strictEqual(parsed[1].direction, "SHORT");
  const parsedTight = degiro.BobDegiro.parseScreenshotCandidates("Gold LONG DE000ABC1234\nGold SHORT DE000XYZ9876");
  assert.strictEqual(parsedTight[0].direction, "LONG");
  assert.strictEqual(parsedTight[1].direction, "SHORT");
  const multi = degiro.BobDegiro.parseScreenshotCandidates("Gold Turbo LONG\nISIN DE000ABC1234\nHebel 5x\nKO 3900\nProduktkurs 12,34\nGold Turbo SHORT\nISIN DE000XYZ9876\nHebel 4x\nKO 4100\nProduktkurs 9,87");
  assert.strictEqual(multi[0].leverage,"5");
  assert.strictEqual(multi[0].ko,"3900");
  assert.strictEqual(multi[0].price,"12.34");
  assert.strictEqual(multi[0].direction,"LONG");
  assert.strictEqual(multi[1].leverage,"4");
  assert.strictEqual(multi[1].ko,"4100");
  assert.strictEqual(multi[1].price,"9.87");
  assert.strictEqual(multi[1].direction,"SHORT");
  const repeated = degiro.BobDegiro.parseScreenshotCandidates("Gold LONG DE000ABC1234\n\nGold LONG DE000ABC1234 Hebel 5x KO 3900");
  assert.strictEqual(repeated.length,1);
  assert.strictEqual(repeated[0].ko,"3900");
  const many = degiro.BobDegiro.parseScreenshotCandidates(Array.from({length:8},(_,i)=>"Gold LONG DE000ABC123"+i+" Hebel 5x KO 3900").join("\n"));
  assert.strictEqual(many.length,8);
  assert(fs.readFileSync("degiro_assistant.js", "utf8").includes("dgCentralShot"));
  const screenRow=degiro.BobDegiro.ocrExtract("Gold Turbo Mini Call BAR 3539 BP 3503.93 Bv 10 | DE000FA06UL6");
  assert.strictEqual(screenRow.ko,"3539");
  assert.strictEqual(screenRow.leverage,"");
  assert.strictEqual(screenRow.price,"");
  assert.strictEqual(degiro.BobDegiro.ocrExtract("Gold Long SL\n3978.9026 STR 3978.9026 R 10 | DE000PJ9NCK0").ko,"3978.9026");
  assert(degiro.BobDegiro.validIsin("DE000FC1CHB7"));
  assert(!degiro.BobDegiro.validIsin("DEOOOFC1CHB7"));
  assert(!degiro.BobDegiro.validIsin("DEOOOPJONB98"));
  assert.strictEqual(degiro.BobDegiro.normalizeOcrIsin("DEOOOFC1CHB7").isin,"DE000FC1CHB7");
  assert.strictEqual(degiro.BobDegiro.normalizeOcrIsin("DEOOOFC1CHB7").originalIsin,"DEOOOFC1CHB7");
  assert.strictEqual(degiro.BobDegiro.normalizeOcrIsin("DEOOOFG5GUTO").isin,"DE000FG5GUT0");
  assert.strictEqual(degiro.BobDegiro.normalizeOcrIsin("DEOOOPJINCKO").isin,"DEOOOPJINCKO");
  assert.strictEqual(degiro.BobDegiro.normalizeOcrIsin("DEOOOPJONB98").isin,"DEOOOPJONB98");
  assert.strictEqual(degiro.BobDegiro.normalizeOcrIsin("DE000FC1CHB7").originalIsin,"");

  const reread=degiro.BobDegiro.recoverOcrIsins("DEOOOPJINCKO\nDEOOOPJONB98","R10DE000PJ9NCK0\nR10DE000PJ9NB98");
  assert.strictEqual(reread.text,"DE000PJ9NCK0\nDE000PJ9NB98");
  assert.strictEqual(reread.corrections.DE000PJ9NCK0,"DEOOOPJINCKO");
  assert.strictEqual(degiro.BobDegiro.recoverOcrIsins("DEOOOPJONB98","39919013R10DEC00PJ9NB98").text,"DE000PJ9NB98");
  assert.strictEqual(degiro.BobDegiro.recoverOcrIsins("DEOOOPJONB98","DE000PJ9NB99").text,"DEOOOPJONB98");
  assert.strictEqual(degiro.BobDegiro.recoverOcrIsins("DEOOOPJINCKO","DE000PG0XK25").text,"DEOOOPJINCKO");
  assert.strictEqual(degiro.BobDegiro.recoverOcrIsins("DE000FC1CHB7","DE000PJ9NCK0").text,"DE000FC1CHB7");
  assert.strictEqual(degiro.BobDegiro.recoverOcrIsins("DEOOOPJINCKO","").text,"DEOOOPJINCKO");

  const rows=new Map(),statuses=new Map();
  degiroContext.document={querySelector:selector=>{if(!rows.has(selector))rows.set(selector,{value:"OLD",checked:true});return rows.get(selector);},getElementById:id=>{if(!statuses.has(id))statuses.set(id,{textContent:"OLD"});return statuses.get(id);}};
  degiro.BobDegiro.populateCandidateRows([{name:"First",isin:"DE000FC1CHB7",price:"12"},{name:"Second",isin:"DE000PG0XK25",price:"20"}]);
  degiro.BobDegiro.populateCandidateRows([{name:"Replacement",isin:"DEOOOPJINCKO",price:"",leverage:""}]);
  const field=(key,i)=>rows.get('[data-dg="'+key+'"][data-i="'+i+'"]');
  assert.strictEqual(field("price",1).value,"");
  assert.strictEqual(field("name",2).value,"");
  assert.strictEqual(field("isin",2).value,"");
  assert.strictEqual(field("confirmed",1).checked,false);
  assert(statuses.get("dgOcrStatus1").textContent.includes("ISIN unsicher"));
  assert.strictEqual(statuses.get("dgOcrStatus2").textContent,"Wartet auf Screenshot.");
  delete degiroContext.document;

  const ten=degiro.BobDegiro.parseScreenshotCandidates(Array.from({length:10},(_,i)=>"Gold Call BAR 3900 | DE000ABC12"+String(i).padStart(2,"0")).join("\n"));
  assert.strictEqual(ten.length,10);
  const strongCtx={direction:"LONG",atr:20,spot:4000,trend:"LONG",trend2:"LONG",mtf:"LONG",rsi:60,hist:1,adx:30,momentum:1};
  const completeProduct={name:"Synthetic Gold",isin:"DE000FC1CHB7",productDirection:"LONG",spot:4000,ko:3500,leverage:4,price:12,spread:0};
  assert(degiro.BobDegiro.rankProducts([completeProduct],strongCtx).tradeable);
  const now=Date.now(),quoted={...completeProduct,isinConfirmed:true,quote:{found:true,eligible:true,tradingEndAt:new Date(now+60000).toISOString(),marketOpen:true,currency:"EUR",isin:completeProduct.isin,quoteAt:new Date(now-1000).toISOString(),bidAt:new Date(now-1000).toISOString(),askAt:new Date(now-1000).toISOString(),leverageAt:new Date(now-1000).toISOString(),snapshotAt:new Date(now-1000).toISOString(),price:12,leverage:4,ko:3500,spread:0,direction:"LONG"}};
  const freshCtx={...strongCtx,requireFreshQuotes:true,spotFresh:true,now};
  assert(degiro.BobDegiro.rankProducts([quoted],freshCtx).tradeable);
  // Synthetic acceptance cases: a direction label must never hide a breached KO barrier.
  for(const ko of [4000,4100]){
    const breached={...quoted,ko,quote:{...quoted.quote,ko}};
    assert(!degiro.BobDegiro.rankProducts([breached],freshCtx).tradeable,"LONG KO at/above spot must be excluded");
  }
  const shortCtx={...freshCtx,direction:"SHORT",trend:"SHORT",trend2:"SHORT",mtf:"SHORT",rsi:40,hist:-1,momentum:-1};
  const short={...quoted,productDirection:"SHORT",ko:4500,quote:{...quoted.quote,direction:"SHORT",ko:4500}};
  assert(degiro.BobDegiro.rankProducts([short],shortCtx).tradeable);
  assert(!degiro.BobDegiro.rankProducts([quoted],shortCtx).tradeable);
  for(const ko of [4000,3500]){
    const breached={...short,ko,quote:{...short.quote,ko}};
    assert(!degiro.BobDegiro.rankProducts([breached],shortCtx).tradeable,"SHORT KO at/below spot must be excluded");
  }

  assert(!degiro.BobDegiro.rankProducts([quoted],{...freshCtx,spotFresh:false}).tradeable);
  assert(degiro.BobDegiro.quoteTiming(quoted.quote,now).fresh);
  assert.strictEqual(degiro.BobDegiro.quoteTiming(quoted.quote,now).ageSeconds,1);
  assert(!degiro.BobDegiro.quoteTiming(quoted.quote,now+61000).fresh);
  for(const key of ["bidAt","askAt","leverageAt","snapshotAt"]){
   for(const val of ["",new Date(now-61000).toISOString(),new Date(now+6000).toISOString()]){
    const bad={...quoted,quote:{...quoted.quote,[key]:val}};
    assert(!degiro.BobDegiro.rankProducts([bad],freshCtx).tradeable);
   }
  }

  for(const p of [completeProduct,{...quoted,isinConfirmed:false},{...quoted,price:13},{...quoted,quote:{...quoted.quote,quoteAt:new Date(now-61000).toISOString()}},{...quoted,quote:{...quoted.quote,quoteAt:new Date(now+6000).toISOString()}},{...quoted,quote:{...quoted.quote,isin:"DE000PJ9NCK0"}}])assert(!degiro.BobDegiro.rankProducts([p],freshCtx).tradeable);
  assert(degiro.BobDegiro.rankProducts([{...quoted,quote:{...quoted.quote,quoteAt:new Date(now-61000).toISOString()}},quoted],freshCtx).tradeable);

  for(const key of ["price","leverage","ko","spread"]){const missing={...completeProduct,[key]:""};assert(!degiro.BobDegiro.rankProducts([missing],strongCtx).tradeable);}
  assert(!degiro.BobDegiro.rankProducts([{...completeProduct,isin:"DEOOOFC1CHB7"}],strongCtx).tradeable);



  assert(fs.readFileSync("degiro_assistant.js", "utf8").includes("/ocr-assets/v5/tesseract.min.js"));
  assert(fs.readFileSync("degiro_assistant.js", "utf8").includes("/api/degiro/enrich"));
  assert(serverSource.includes("/api/degiro/enrich"));
  assert(serverSource.includes("product_quotes.get_quote"));


  assert(degiro.BobDegiro.supplementaryHint(["Hebel"]).includes("Produktübersicht"));
  assert(degiro.BobDegiro.supplementaryHint(["Produktkurs"]).includes("Geld, Brief"));
  assert(degiro.BobDegiro.screenshotTimeLabel({sourceTime:"30/09/2026 21:43"}).includes("Aktualität nicht verifiziert"));
  assert(degiro.BobDegiro.screenshotTimeLabel({}).includes("Kurszeit fehlt"));
  const prior=degiro.BobDegiro.mergeScreenshotEvidence(null,{price:"24.82",bid:24.81,ask:24.82,spread:"0.01",sourceTime:"30/09/2026 21:43",currency:"EUR"},"quotes.jpg");
  const staticOnly=degiro.BobDegiro.mergeScreenshotEvidence(prior,{price:"",bid:null,ask:null,spread:"",sourceTime:"",currency:"",leverage:"14.01"},"details.jpg");
  assert.strictEqual(staticOnly.sourceTime,prior.sourceTime);
  assert.strictEqual(staticOnly.bid,24.81);
  assert.strictEqual(staticOnly.evidence.Geld.source,"quotes.jpg");
  assert.strictEqual(staticOnly.clearSpread,false);
  const replacement=degiro.BobDegiro.mergeScreenshotEvidence(prior,{price:"24.68",bid:null,ask:null,spread:"",sourceTime:""},"new.jpg");
  assert.strictEqual(replacement.clearSpread,true);
  assert.strictEqual(replacement.evidence.Geld,undefined);
  assert.strictEqual(replacement.sourceTime,"");
  assert.strictEqual(degiro.BobDegiro.manualProductMissing({}).length,5);
  assert.strictEqual(degiro.BobDegiro.manualProductMissing({isin:"DE000FG4JXV7",price:24.82,leverage:14.01,ko:4460,spread:0}).length,0);
  assert(degiro.BobDegiro.manualProductMissing({isin:"DE000FG4JXV7",price:24.82,leverage:14.01,ko:0,spread:""}).includes("KO-Schwelle"));
  assert.strictEqual(degiro.BobDegiro.escapeHtml('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  console.log("Bob push + DEGIRO tests: OK");
})().catch(err => { console.error(err); process.exit(1); });
