import os
import base64
import hmac
import json
import math
import time
import threading
import bob_auth
import auto_collection
import ocr_assets
import product_quotes
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

USER = os.environ.get("BOB_USER", "")
PASSWORD = os.environ.get("BOB_PASSWORD", "")
PUSH_SERVICE_URL = os.environ.get("PUSH_SERVICE_URL", "")
PUSH_SERVICE_TOKEN = os.environ.get("PUSH_SERVICE_TOKEN", "")
SIGNAL_WORKER_TOKEN = os.environ.get("SIGNAL_WORKER_TOKEN", "")
FIB_MONITOR_HEALTH = {"configured": bool(PUSH_SERVICE_URL and PUSH_SERVICE_TOKEN), "status": "starting", "lastCheckedAt": None, "lastSuccessAt": None}

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "Bob.html"
SW_PATH = BASE_DIR / "sw.js"
MANIFEST_PATH = BASE_DIR / "manifest.json"
ICON_PATH = BASE_DIR / "icon.svg"

# Load static shell assets once at startup. The request handler serves these
# bytes directly; keeping the load explicit prevents runtime NameError failures.
HTML = HTML_PATH.read_bytes() if HTML_PATH.exists() else b""
HTML = HTML.replace(b"</body>", auto_collection.PANEL.encode('utf-8')+b"</body>")
SW = SW_PATH.read_bytes() if SW_PATH.exists() else None
MANIFEST = MANIFEST_PATH.read_bytes() if MANIFEST_PATH.exists() else None
ICON = ICON_PATH.read_bytes() if ICON_PATH.exists() else None
# Runtime-module fallback: Render must serve these two browser modules even if
# the deployed filesystem snapshot omits an untracked/static file. Keeping the
# source embedded here makes the JS delivery independent of that filesystem edge case.
PUSH_MANAGER_JS = "/* Bob Push Manager: browser notification + optional server Web Push registration. */\n(function(){\n  const KEY=\"bobPushV1\", LEGACY=\"goldScannerPush\";\n  const PUSH_API=\"/api/push\";\n  const defaults={registered:false,serverRegistered:false,general:false,trade:false,activeTrade:false};\n  function read(){\n    try{\n      const raw=localStorage.getItem(KEY);\n      if(raw)return {...defaults,...JSON.parse(raw)};\n      const old=localStorage.getItem(LEGACY);\n      if(old)return {...defaults,...JSON.parse(old)};\n    }catch(_){}\n    return {...defaults};\n  }\n  function save(s){const next={...defaults,...s};try{localStorage.setItem(KEY,JSON.stringify(next));}catch(_){}return next;}\n  function b64ToBytes(value){\n    const pad=\"=\".repeat((4-(value.length%4))%4);\n    const raw=atob(value.replace(/-/g,\"+\").replace(/_/g,\"/\")+pad);\n    return Uint8Array.from(raw,c=>c.charCodeAt(0));\n  }\n  async function registerServerPush(reg){\n    try{\n      const keyRes=await fetch(PUSH_API+\"/vapid-public-key\",{cache:\"no-store\"});\n      if(!keyRes.ok)throw new Error(\"VAPID-Key konnte nicht geladen werden.\");\n      const {publicKey}=await keyRes.json();\n      if(!publicKey)throw new Error(\"VAPID-Key fehlt.\");\n      if(!reg.pushManager)return false;\n      // Recreate the browser subscription with the current VAPID public key.\n      // This repairs subscriptions created with a previous VAPID key after a\n      // server-side key rotation or a recreated push database.\n      let sub=await reg.pushManager.getSubscription();\n      if(sub){\n        try{\n          await fetch(PUSH_API+\"/unsubscribe\",{\n            method:\"POST\",\n            headers:{\"Content-Type\":\"application/json\"},\n            body:JSON.stringify({endpoint:sub.endpoint})\n          });\n        }catch(_){}\n        try{await sub.unsubscribe();}catch(_){}\n        sub=null;\n      }\n      sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(publicKey)});\n      const res=await fetch(PUSH_API+\"/subscribe\",{\n        method:\"POST\",\n        headers:{\"Content-Type\":\"application/json\"},\n        body:JSON.stringify({subscription:sub.toJSON()})\n      });\n      if(!res.ok)throw new Error(\"Push-Subscription konnte nicht gespeichert werden.\");\n      return true;\n    }catch(_){return false;}\n  }\n  async function enable(){\n    if(!(\"Notification\" in window))throw new Error(\"Web-Benachrichtigungen werden von diesem Browser nicht unterstützt.\");\n    const p=await Notification.requestPermission();\n    if(p!==\"granted\")throw new Error(\"Benachrichtigungen wurden nicht freigegeben.\");\n    let serverRegistered=false;\n    if(\"serviceWorker\" in navigator){\n      const reg=await navigator.serviceWorker.register(\"/sw.js\",{updateViaCache:\"none\"});\n      try{await reg.update();}catch(_){}\n      serverRegistered=await registerServerPush(reg);\n    }\n    return save({...read(),registered:true,serverRegistered});\n  }\n  function state(){return read();}\n  function allowed(kind){\n    const s=read();\n    return s.registered&&Notification.permission===\"granted\"&&s[kind]===true&&(kind!==\"trade\"||s.activeTrade===true);\n  }\n  async function emit(kind,title,body,data={}){\n    const testTrade=kind===\"trade\"&&data&&data.test===true;\n    if(testTrade){\n      const s=read();\n      if(!(s.registered&&Notification.permission===\"granted\"&&s.trade===true))return false;\n    }else if(!allowed(kind))return false;\n    const tag=\"bob-\"+kind+\"-\"+(data.signalId||\"current\");\n    const payload={title,body,data:{...data,url:data.url||\"/\",kind,signalId:data.signalId||null},tag};\n    let serverSent=false;\n    if(read().serverRegistered){\n      try{\n        const res=await fetch(\"/api/push/send\",{\n          method:\"POST\",\n          headers:{\"Content-Type\":\"application/json\"},\n          body:JSON.stringify(payload)\n        });\n        if(res.ok){\n          const result=await res.json().catch(()=>null);\n          serverSent=Boolean(result&&result.sent>0);\n          if(result&&result.vapidReset){\n            const reg=await navigator.serviceWorker.ready;\n            serverSent=await registerServerPush(reg);\n            if(serverSent){\n              const retry=await fetch(\"/api/push/send\",{\n                method:\"POST\",\n                headers:{\"Content-Type\":\"application/json\"},\n                body:JSON.stringify(payload)\n              });\n              if(retry.ok){\n                const retryResult=await retry.json().catch(()=>null);\n                serverSent=Boolean(retryResult&&retryResult.sent>0);\n              }\n            }\n          }\n        }\n      }catch(_){}\n    }\n    if(serverSent)return true;\n    const options={body,tag,data:{url:data.url||\"/\",kind,signalId:data.signalId||null},renotify:false};\n    try{\n      if(\"serviceWorker\" in navigator){\n        const reg=await navigator.serviceWorker.ready;\n        await reg.showNotification(title,options);\n        return true;\n      }\n      new Notification(title,options);\n      return true;\n    }catch(_){return false;}\n  }\n  function set(kind,value){return save({...read(),[kind]:Boolean(value)});}\n  function setActiveTrade(value){return set(\"activeTrade\",value);}\n  window.BobPush={state,save,enable,allowed,emit,set,setActiveTrade};\n})();"
DEGIRO_ASSISTANT_JS = '/* Local, user-entered evidence only. No portal requests or order execution. */\n(function(){\nconst number=v=>v!==null&&v!==undefined&&String(v).trim()!==\'\'&&Number.isFinite(Number(String(v).replace(\',\',\'.\')))?Number(String(v).replace(\',\',\'.\')):null;\nconst time=v=>typeof v===\'string\'&&/T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})$/.test(v)?Date.parse(v):NaN;\nconst fresh=(v,now,seconds)=>Number.isFinite(time(v))&&now>=time(v)&&now-time(v)<=seconds*1000;\nconst escape=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\nfunction assess(p,r,bundle,now=Date.now()){\n const out={eligible:false,tradeable:false,estimated:false,reasons:[],quote:null,ko:null,distanceUsd:null,distancePct:null};\n const fail=s=>out.reasons.push(s);\n if(!r)return out;\n if(!window.BobDegiro.validIsin(p.isin)||!p.isinConfirmed||r.isin!==p.isin){fail(\'ISIN und Produktzuordnung bestätigen\');return out;}\n if(![\'LONG\',\'SHORT\'].includes(p.productDirection)){fail(\'Produktrichtung fehlt\');return out;}\n const meta=p.quote?.isin===p.isin&&p.quote?.productVerified?p.quote.metadata:null;\n if(meta&&((Number(meta.status)&(2|8|16|32))||meta.direction&&meta.direction!==p.productDirection)){fail(\'Emittent meldet inaktives Produkt oder widersprüchliche Richtung\');return out;}\n const bid=number(r.bid),ask=number(r.ask);\n if(![\'Stuttgart\',\'Onvista\'].includes(r.source)||!r.venue||!/^https:\\/\\//.test(r.url||\'\')||!r.paired||!r.reviewed||!fresh(r.quoteAt,now,1800)||!(bid>0&&ask>=bid))fail(\'Geld/Brief als geprüftes Paar derselben Quelle und desselben Handelsplatzes mit Quellenzeit (höchstens 30 Minuten) ergänzen\');\n else out.quote={bid,ask,spread:ask-bid,source:r.source,venue:r.venue,url:r.url,at:r.quoteAt,liveVerified:false};\n const evidence=(r.barriers||[]).filter(x=>number(x.value)>0&&x.isin===p.isin&&x.currency===\'USD\'&&x.source&&/^https:\\/\\//.test(x.url||\'\')&&x.confirmed&&fresh(x.at,now,86400)&&Number.isFinite(time(x.validUntil))&&time(x.validUntil)>now&&time(x.validUntil)-time(x.at)<=86400000);\n if(evidence.length!==(r.barriers||[]).length||!evidence.length)fail(\'Jede KO-Schwelle braucht ISIN, USD, Quelle, Quellenzeit und bestätigte aktuelle Gültigkeit\');\n else{\n  const values=evidence.map(x=>number(x.value)),lo=Math.min(...values),hi=Math.max(...values);\n  if(hi-lo>1+1e-9)fail(\'KO-Widerspruch größer als 1 USD: Berechnung ausgesetzt\');\n  else out.ko={value:p.productDirection===\'SHORT\'?lo:hi,differenceUsd:hi-lo,evidence};\n }\n const state=window.BobDegiro.screenshotCurrentState(p,bundle,now);\n const gold=state.basis;\n out.basis=gold;out.basisLabel=state.rows[0]?.text||\'\';\n if(gold===null)fail(\'Aktueller passender Basiswert fehlt; Future und Spot bleiben getrennt\');\n if(out.ko&&gold!==null){\n  out.distanceUsd=(out.ko.value-gold)*(p.productDirection===\'SHORT\'?1:-1);\n  out.distancePct=out.distanceUsd/gold*100;\n  if(out.distanceUsd<=0)fail(\'Aktueller Basiswert an oder jenseits der gewählten KO-Schwelle; historische KO-Berührung zusätzlich prüfen\');\n }\n const m=p.quote?.productVerified&&p.quote?.productModel?.verifiedSimpleTurbo?p.quote.productModel:null;\n const c=p.quote?.calculatedProduct,fx=number(c?.usdEur),ratio=number(m?.ratio),strike=number(m?.strike);\n // Require issuer-verified terms and fresh FX. An entered barrier never modifies them.\n if(!m||m.isin!==p.isin||m.underlying!==\'XAU/USD\'||m.direction!==p.productDirection||!(ratio>0&&strike>0&&fx>0)||!fresh(c?.fxDataAt,now,60)||!fresh(c?.fxEffectiveAt,now,60)||!Number.isFinite(time(m.tradingEndAt))||now>time(m.tradingEndAt))fail(\'Für die Preisschätzung fehlen bestätigte Spot-Produktbedingungen oder aktueller USD→EUR-Kurs\');\n else if(out.quote&&out.ko&&out.distanceUsd>0&&gold!==null){\n  if(Math.abs(number(m.ko)-out.ko.value)>1+1e-9){fail(\'Emittentenmodell und gewählte KO-Schwelle widersprechen sich um mehr als 1 USD\');return out;}\n  const currentTimes=[bundle?.spots?.spot_price_as_of,c.fxDataAt,c.fxEffectiveAt].map(time);\n  if(currentTimes.some(x=>!Number.isFinite(x))||Math.max(...currentTimes)-Math.min(...currentTimes)>15000){fail(\'Aktueller Gold-/FX-Zeitversatz größer als 15 Sekunden\');return out;}\n  const g0=number(r.goldReference),f0=number(r.fxReference);\n  const stamps=[r.quoteAt,r.goldAt,r.fxAt].map(time);\n  if(!(g0>0&&f0>0)||stamps.some(x=>!Number.isFinite(x))||Math.max(...stamps)-Math.min(...stamps)>5000||stamps.some(x=>x>now)||!r.referenceConfirmed||!/^https:\\/\\//.test(r.goldUrl||\'\')||!/^https:\\/\\//.test(r.fxUrl||\'\'))fail(\'Gold- und FX-Referenz zum Kursnachweis fehlen (Zeitversatz höchstens 5 Sekunden)\');\n  else if((m.direction===\'SHORT\'&&(g0>=out.ko.value||gold>=strike))||(m.direction===\'LONG\'&&(g0<=out.ko.value||gold<=strike)))fail(\'Referenz oder aktueller Basiswert überschreitet KO-/Strike-Grenze\');\n  else{\n   const change=(m.direction===\'LONG\'?1:-1)*ratio*((gold-strike)*fx-(g0-strike)*f0);\n   const estimatedBid=bid+change,estimatedAsk=ask+change;\n   if(!(estimatedBid>0&&estimatedAsk>=estimatedBid))fail(\'Berechneter Produktpreis unplausibel\');\n   else{out.estimated=true;out.estimate={bid:estimatedBid,ask:estimatedAsk,leverage:gold*fx*ratio/estimatedAsk,referenceAt:r.quoteAt,fxAt:c.fxDataAt,formula:\'P = P₀ + Richtung × Verhältnis × [(Gold − Strike) × FX − (Gold₀ − Strike) × FX₀]\'};}\n  }\n }\n return out;\n}\nfunction render(state){\n if(!state.quote&&!state.ko&&!state.reasons.length)return \'\';\n const q=state.quote,k=state.ko,e=state.estimate;\n return \'<div class="small" style="padding:10px;border:1px solid #dbe4f0;border-radius:12px"><b>Kombinierte, bedingte Bewertung</b>\'+\n (q?\'<div>Kursnachweis: \'+escape(q.source)+\' · \'+escape(q.venue)+\' · Geld \'+q.bid.toFixed(4)+\' / Brief \'+q.ask.toFixed(4)+\' EUR · Spread \'+q.spread.toFixed(4)+\' EUR · \'+escape(q.at)+\'</div>\':\'\')+\n (state.basis!==null&&state.basis!==undefined?\'<div>\'+escape(state.basisLabel)+\'</div>\':\'\')+\n (k?\'<div>Konservative KO-Schwelle: \'+k.value.toFixed(4)+\' USD · Quellenabweichung \'+k.differenceUsd.toFixed(4)+\' USD\'+(state.distanceUsd!==null?\' · Abstand \'+state.distanceUsd.toFixed(2)+\' USD / \'+state.distancePct.toFixed(2)+\'%\':\'\')+\'</div>\'+k.evidence.map(x=>\'<div>KO-Nachweis: \'+escape(x.source)+\' · \'+escape(x.at)+\' · bestätigt gültig bis \'+escape(x.validUntil)+\'</div>\').join(\'\'):\'\')+\n (e?\'<div><b>Schätzung, keine SG-Quotierung:</b> Geld ≈ \'+e.bid.toFixed(4)+\' / Brief ≈ \'+e.ask.toFixed(4)+\' EUR · Hebel ≈ \'+e.leverage.toFixed(2)+\'× · FX-Zeit \'+escape(e.fxAt)+\'</div><div>\'+escape(e.formula)+\'</div>\':\'\')+\n state.reasons.map(x=>\'<div>Offen: \'+escape(x)+\'</div>\').join(\'\')+\n \'<div>Keine Live-Freigabe oder automatische Ranglistenaufnahme. Schätzfehler, Preisaufschlag und zwischenzeitliche KO-Berührung unbestätigt. Tatsächlichen DEGIRO-Geld-/Briefkurs vor einer Entscheidung prüfen.</div></div>\';\n}\nfunction form(i){\n const field=(key,label)=>\'<label class="small" style="display:block">\'+label+\'<input data-combined="\'+key+\'" style="width:100%"></label>\';\n return \'<details><summary>Stuttgart / Onvista: manuellen Nachweis ergänzen</summary><div class="small">Alle Zeiten aus der Quelle, mit Sekunden und Zeitzone, z. B. 2026-10-02T08:31:00+02:00. Abrufzeit ersetzt keine Kurszeit. Eingaben bleiben nur in diesem geöffneten Tab.</div><select data-combined="source"><option>Stuttgart</option><option>Onvista</option></select>\'+\n [[\'venue\',\'Handelsplatz (z. B. SG OTC oder Stuttgart)\'],[\'url\',\'Link zum Kursnachweis\'],[\'bid\',\'Geld EUR\'],[\'ask\',\'Brief EUR\'],[\'quoteAt\',\'Gemeinsame Quellenzeit des Geld-/Briefpaars\'],[\'ko1\',\'KO 1 USD\'],[\'koSource1\',\'KO 1 Quelle\'],[\'koUrl1\',\'KO 1 Quellenlink\'],[\'koAt1\',\'KO 1 Quellenzeit\'],[\'koUntil1\',\'KO 1 bestätigt gültig bis\'],[\'ko2\',\'KO 2 USD (optional)\'],[\'koSource2\',\'KO 2 Quelle\'],[\'koUrl2\',\'KO 2 Quellenlink\'],[\'koAt2\',\'KO 2 Quellenzeit\'],[\'koUntil2\',\'KO 2 bestätigt gültig bis\'],[\'goldReference\',\'Gold USD zum Kursnachweis (optional für Schätzung)\'],[\'goldAt\',\'Quellenzeit Gold-Referenz\'],[\'goldUrl\',\'Link Gold-Referenz\'],[\'fxReference\',\'USD→EUR zum Kursnachweis\'],[\'fxAt\',\'Quellenzeit FX-Referenz\'],[\'fxUrl\',\'Link FX-Referenz\']].map(x=>field(...x)).join(\'\')+\n \'<label class="small"><input data-combined="reviewed" type="checkbox"> ISIN, Geld-/Briefpaar, Quellen und KO-Gültigkeitsangaben am Original geprüft; zulässige persönliche Nutzung bestätigt</label><label class="small"><input data-combined="referenceConfirmed" type="checkbox"> Gold-/FX-Referenzen am Original geprüft</label><button data-combined-save="\'+i+\'">Nachweis bedingt auswerten</button><button data-combined-clear="\'+i+\'">Nachweis entfernen</button><div class="small">Keine erfundenen Zeiten oder Gültigkeitsintervalle eintragen. Nicht belegbare Felder leer lassen; Bob zeigt sie als offen.</div></details><div id="dgCombinedState\'+i+\'"></div>\';\n}\nwindow.BobCombined={assess,render,form,time};\n})();\n\n/* Bob DEGIRO assistant: deterministic risk math, product-fit checks and Top-3 ranking. No order execution. */\n(function(){\nfunction n(v){if(v===null||v===undefined||String(v).trim()==="")return null;const x=Number(v);return Number.isFinite(x)?x:null;}\nfunction validIsin(value){\n const isin=String(value||"").trim().toUpperCase();\n if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))return false;\n // Repeated O in the common DE000 prefix is an ambiguous OCR reading, even\n // when a coincidental checksum passes. Require a visual correction.\n if(/^DE(?=[0O]{3})(?=[0O]{0,2}O)/.test(isin))return false;\n const digits=isin.split("").map(c=>/[A-Z]/.test(c)?String(c.charCodeAt(0)-55):c).join("");\n let sum=0;\n for(let i=digits.length-1,double=false;i>=0;i--,double=!double){let x=Number(digits[i]);if(double)x*=2;sum+=x>9?x-9:x;}\n return sum%10===0;\n}\nfunction normalizeOcrIsin(value){\n const original=String(value||"").trim().toUpperCase();\n if(validIsin(original))return{isin:original,originalIsin:""};\n // German WKN excludes I/O. Only substitute those confusable glyphs,\n // only for DE000-style identifiers, and accept only a valid checksum.\n // Never infer other digits (such as 9) from an ambiguous OCR character.\n if(!/^DE[0O]{3}[A-Z0-9]{7}$/.test(original))return{isin:original,originalIsin:""};\n const candidate="DE000"+original.slice(5).replace(/O/g,"0").replace(/I/g,"1");\n return validIsin(candidate)?{isin:candidate,originalIsin:original}:{isin:original,originalIsin:""};\n}\nfunction koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}\nfunction directionOf(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null)return null;return ko<spot?"LONG":ko>spot?"SHORT":null;}\nfunction riskModel(p){const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);if(spot===null||stop===null||riskEur===null||riskEur<=0)return{ok:false,reason:"Ungültige Eingabedaten für Risiko."};if(fx===null||fx<=0)return{ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};const dist=Math.abs(spot-stop);if(dist<=0)return{ok:false,reason:"Stop-Distanz ist null."};const maxLossUsd=riskEur/fx,approxNotionalUsd=maxLossUsd/(dist/spot),approxNotionalEur=approxNotionalUsd*fx,marginEur=approxNotionalEur/lev,ko=n(p.ko),koPct=koDistancePct(spot,ko),warnings=[];if(ko!==null&&((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");return{ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};}\nfunction technicalQuality(ctx={}){const d=String(ctx.direction||"NEUTRAL").toUpperCase();if(d==="NEUTRAL")return{score:50,reasons:["Kein eindeutiges Richtungsszenario."]};let score=50,reasons=[];const side=v=>{const x=String(v||"").toUpperCase();return x.includes("LONG")||x.includes("BULL")||x.includes("UP")?"LONG":x.includes("SHORT")||x.includes("BEAR")||x.includes("DOWN")?"SHORT":""};const trend=side(ctx.trend),trend2=side(ctx.trend2),mtf=side(ctx.mtf),rsi=Number(ctx.rsi),hist=Number(ctx.hist),adx=Number(ctx.adx),momentum=Number(ctx.momentum);if(trend===d){score+=12;reasons.push("EMA-Trend bestätigt.");}else if(trend&&trend!==d){score-=12;reasons.push("EMA-Trend widerspricht.");}if(trend2===d){score+=10;reasons.push("Langfristtrend bestätigt.");}else if(trend2&&trend2!==d){score-=10;reasons.push("Langfristtrend widerspricht.");}if(mtf===d){score+=15;reasons.push("MTF bestätigt.");}else if(mtf&&mtf!==d){score-=15;reasons.push("MTF widerspricht.");}if(Number.isFinite(rsi)){const support=(d==="LONG"&&rsi>=55&&rsi<=65)||(d==="SHORT"&&rsi>=35&&rsi<=45);const broad=(d==="LONG"&&rsi>=50&&rsi<70)||(d==="SHORT"&&rsi<=50&&rsi>30);if(support){score+=10;reasons.push("RSI liegt im günstigen Trendbereich.");}else if(broad){score+=5;reasons.push("RSI unterstützt die Richtung.");}else if((d==="LONG"&&rsi>75)||(d==="SHORT"&&rsi<25)){score-=10;reasons.push("RSI zeigt erhöhtes Überdehnungsrisiko.");}}if(Number.isFinite(hist)){const h=hist>0?"LONG":hist<0?"SHORT":"";if(h===d){score+=10;reasons.push("MACD-Histogramm bestätigt.");}else if(h&&h!==d){score-=10;reasons.push("MACD-Histogramm widerspricht.");}}if(Number.isFinite(adx)){if(adx>=30){score+=7;reasons.push("ADX zeigt einen starken Trend.");}else if(adx>=20){score+=3;reasons.push("ADX bestätigt vorhandene Trendstärke.");}else if(adx<15){score-=5;reasons.push("ADX zeigt wenig Trendstärke.");}}if(Number.isFinite(momentum)){const m=momentum>0?"LONG":momentum<0?"SHORT":"";if(m===d){score+=8;reasons.push("Momentum bestätigt.");}else if(m&&m!==d){score-=8;reasons.push("Momentum widerspricht.");}}return{score:Math.max(0,Math.min(100,Math.round(score))),reasons};}\nconst futureIsins=new Set(["DE000FG309G0"]);\nfunction isFutureProduct(p){return p.underlyingType==="FUTURE"||p.quote?.metadata?.underlyingType==="FUTURE"||futureIsins.has(String(p.isin||"").trim().toUpperCase());}\nfunction futureResearchText(x,now=Date.now()){\n const r=x.futureResearch;if(!r)return "";\n const at=v=>typeof v==="string"&&!Number.isNaN(Date.parse(v))?new Date(v).toLocaleString():"unbekannt";\n let text=" · FUTURES-RECHERCHE "+r.contract;\n if(Number.isFinite(r.bid)&&Number.isFinite(r.ask))text+=" · Geld "+r.bid+" / Brief "+r.ask+" EUR · Geldzeit "+at(r.bidAt)+" · Briefzeit "+at(r.askAt);\n if(r.underlyingPriceUsd)text+=" · Futures-Basiswert "+r.underlyingPriceUsd+" USD · Basiswertzeit "+at(r.underlyingAt)+" (verzögert oder Echtzeitstatus unbestätigt)";\n const c=r.calculatedFuture;\n if(c){\n  const age=(now-Date.parse(c.priceAt))/1000,refAge=(now-Date.parse(c.referenceAt))/1000;\n  if(c.available&&Number.isFinite(c.priceUsd)&&c.priceUsd>0&&age>=0&&age<=60&&refAge>=0&&refAge<=1800){\n   text+=" · BERECHNETER FUTURE-KURS: "+Number(c.priceUsd).toFixed(2)+" USD · "+(c.proxySource||"Investing.com CFD")+"-Kurszeit "+at(c.priceAt)+" ("+Math.ceil(age)+" s alt) · echter GCZ26-Referenzkurs "+c.referencePriceUsd+" USD von "+at(c.referenceAt)+" · Zeitversatz "+c.alignmentSeconds+" s"+(c.proxyReferenceKind==="linear-interpolation"?" (Quellenreferenz zeitlich interpoliert)":"")+" · Formel: "+c.formula+" · "+c.note;\n  }else{\n   const reasons=[];\n   if(c.available){\n    if(!Number.isFinite(age)||age<0)reasons.push("Schätzungszeit fehlt oder liegt in der Zukunft");\n    else if(age>60)reasons.push("Schätzung "+Math.ceil(age)+" s alt (höchstens 60 s)");\n    if(!Number.isFinite(refAge)||refAge<0)reasons.push("Future-Referenzzeit fehlt oder liegt in der Zukunft");\n    else if(refAge>1800)reasons.push("Future-Referenz "+Math.ceil(refAge/60)+" min alt (höchstens 30 min)");\n   }\n   text+=" · Berechneter Future-Kurs: "+(c.available?"ausgesetzt – "+(reasons.join("; ")||"Kurs nicht verwendbar")+" · Schätzungszeit "+at(c.priceAt):c.reason||"noch nicht verfügbar");\n  }\n  const collection=c.collection;\n  if(collection){\n   const sourceAge=(now-Date.parse(collection.lastAt))/1000;\n   text+=" · "+(c.proxyKind==="gold-api-spot"?"Gold-Spot":"CFD")+"-Erfassung: "+collection.sampleCount+" Beobachtungen über "+Math.floor(collection.coveredSeconds/60)+" min · letzter Quellenzeitpunkt "+at(collection.lastAt)+" · "+(Number.isFinite(sourceAge)&&sourceAge>=0&&sourceAge<=60?"frisch":"nicht aktuell")+(Number.isFinite(c.referenceAgeSeconds)?" · Future-Referenz "+Math.ceil(c.referenceAgeSeconds/60)+" min alt":"");\n   if(Number.isFinite(collection.largestGapSeconds))text+=" · größte Erfassungslücke "+collection.largestGapSeconds+" s";\n   if(Number.isFinite(collection.continuousSeconds))text+=" · jüngster zusammenhängender Abschnitt "+Math.floor(collection.continuousSeconds/60)+" min (Lücken höchstens "+collection.maxGapSeconds+" s)";\n  }\n  text+=" · "+qualityText(c.validation,"USD");\n  if(c.sourceStatus)text+=" · Quellenstatus: "+c.sourceStatus;\n  if(c.storageStatus)text+=" · "+c.storageStatus;\n  if(c.proxyKind==="gold-api-spot")text+=" · Spot dient ausschließlich der Kursschätzung; Richtung und MTF stammen weiterhin vom exakten GCZ26-Kontrakt";\n  for(const alternative of c.alternatives||[])if(alternative.proxyKind!==c.proxyKind&&!alternative.available)text+=" · "+(alternative.proxyKind==="gold-api-spot"?"Spot-Ersatz":"Investing.com CFD")+": "+(alternative.sourceStatus||alternative.reason||"noch nicht verfügbar");\n }\n if(r.indicativeLeverage)text+=" · Recherche-Hebel ca. "+Number(r.indicativeLeverage).toFixed(2)+"× · KO-Abstand zum verzögerten Basiswert ca. "+Number(r.indicativeKoDistancePct).toFixed(2)+"% · Näherung mit verzögertem Basiswert";\n const analysis=r.contractAnalysis;\n if(analysis)text+=" · Eigene Kontraktanalyse: "+(analysis.available?analysis.direction+" · 5m/15m/1h/4h · "+Object.entries(analysis.blocks||{}).map(([k,v])=>k+": "+v).join(" · ")+" · "+analysis.source:analysis.reason||"Historie wird geladen");\n return text+" · "+r.estimateNote;\n}\nfunction productEstimateText(x,now=Date.now()){\n const c=x.calculatedProduct;if(!c)return "";\n const age=(now-Date.parse(c.priceAt))/1000,refAge=(now-Date.parse(c.referenceAt))/1000;\n const times=[c.goldAt,c.fxDataAt,c.fxEffectiveAt].map(t=>(now-Date.parse(t))/1000);\n if(c.available&&Number.isFinite(c.priceEur)&&c.priceEur>0&&age>=0&&age<=60&&refAge>=0&&refAge<=1800&&times.every(t=>Number.isFinite(t)&&t>=0&&t<=60)){\n  return " · BERECHNETER PRODUKTKURS: ca. "+Number(c.priceEur).toFixed(2)+" EUR (Brief-Schätzung) · Geld-Schätzung "+Number(c.bidEur).toFixed(2)+" EUR · Daten "+Math.ceil(age)+" s alt · bestätigter Produkt-Referenzkurs vom "+new Date(c.referenceAt).toLocaleString()+" · "+c.formula+" · "+c.note+" · "+qualityText(c.validation,"EUR")+" · Keine Live-Handelsfreigabe.";\n }\n return " · Berechneter Produktkurs: "+(c.available?"veraltet – Aktualisierung erforderlich":c.reason||"kein verifiziertes Modell verfügbar");\n}\nfunction qualityText(v,unit){\n if(!v)return "Genauigkeitsmessung startet";\n if(!v.ready){\n  const span=n(v.observedSpanSeconds)??Math.min(n(v.bid?.observedSpanSeconds)||0,n(v.ask?.observedSpanSeconds)||0);\n  let text="Genauigkeit noch nicht ausreichend gemessen · "+(v.sampleCount||0)+"/"+(v.minSamples||20)+" passende Vergleiche · Messzeitraum "+Math.floor(span/60)+"/10 min"+(v.horizonBucket?" · Referenzabstand "+v.horizonBucket:"");\n  if(v.sampleCount>0&&Number.isFinite(v.maxAbsoluteError))text+=" · bisher maximale Abweichung "+v.maxAbsoluteError.toFixed(unit==="EUR"?4:2)+" "+unit+" (vorläufig)";\n  for(const s of v.horizonSummaries||[]){\n   text+=" · Messgruppe "+s.horizonBucket+": "+s.sampleCount+" Vergleiche";\n   if(s.sampleCount>0&&Number.isFinite(s.meanAbsoluteError)&&Number.isFinite(s.maxAbsoluteError))text+=" · mittlere absolute Abweichung "+s.meanAbsoluteError.toFixed(2)+" "+unit+", maximal "+s.maxAbsoluteError.toFixed(2)+" "+unit+" (vorläufig)";\n  }\n  return text;\n }\n const error=n(v.maxAbsoluteError)??Math.max(n(v.bid?.maxAbsoluteError)||0,n(v.ask?.maxAbsoluteError)||0);\n return v.sampleCount+" Vergleiche · bisher maximale Abweichung "+Number(error).toFixed(unit==="EUR"?4:2)+" "+unit+" · zukünftige Fehler können größer sein";\n}\nfunction freshTimes(times,now,maxAge=60){\n const parsed=times.map(t=>typeof t==="string"&&/(?:Z|[+-]\\d{2}:\\d{2})$/.test(t)?Date.parse(t):NaN);\n return parsed.length>0&&parsed.every(t=>Number.isFinite(t)&&now>=t&&now-t<=maxAge*1000);\n}\n// Read-only assessment: never fills ranking inputs or renews source times.\nfunction screenshotCurrentState(p,bundle,now=Date.now()){\n const out={eligible:false,liveVerified:false,rows:[],basis:null,koDistancePct:null,leverage:null};\n if(!validIsin(p.isin)||p.isinConfirmed!==true){out.rows.push({label:\'Produktzuordnung\',text:\'ISIN und erkannte Werte am Original bestätigen\'});return out;}\n const q=p.quote?.isin===p.isin?p.quote:null,shot=p.snapshot?.isin===p.isin?p.snapshot:null;\n const meta=q?.productVerified?q.metadata:null;\n const model=q?.productVerified&&q.productModel?.isin===p.isin?q.productModel:null;\n const future=isFutureProduct(p)||/\\bFUTURE\\b/i.test(p.name||shot?.name||\'\');\n const side=meta?.direction||shot?.direction||p.productDirection,ko=n(meta?.ko)??n(shot?.ko)??n(p.ko);\n let basis=null,basisLabel=\'\',basisAt=null;\n if(future){\n  const r=q?.futureResearch,c=r?.calculatedFuture;\n  if(meta?.underlyingType===\'FUTURE\'&&meta.contract&&meta.contract===r?.contract&&r.contract===c?.contract&&c.available&&n(c.priceUsd)>0&&freshTimes([c.priceAt],now)&&freshTimes([c.referenceAt],now,1800)){\n   basis=n(c.priceUsd);basisAt=c.priceAt;basisLabel=\'Berechneter \'+r.contract+\'-Kurs (Schätzung, keine Börsen-Echtzeit)\';\n  }else if(meta?.underlyingType===\'FUTURE\'&&meta.contract===r?.contract&&r?.underlyingDataState===\'realtime\'&&n(r.underlyingPriceUsd)>0&&freshTimes([r.underlyingAt],now)){\n   basis=n(r.underlyingPriceUsd);basisAt=r.underlyingAt;basisLabel=\'Datierter \'+r.contract+\'-Basiswert\';\n  }\n }else{\n  const spots=bundle?.spots,age=n(spots?.xaus_age_seconds),fetched=n(bundle?.fetched_at),elapsed=fetched===null?null:now/1000-fetched;\n  const confirmedSpot=meta?.underlyingType===\'SPOT\'&&meta.underlying===\'XAU/USD\'||model?.verifiedSimpleTurbo&&model.underlying===\'XAU/USD\';\n  // Undifferentiated "Gold" is a scenario, not verified spot identity.\n  const scenario=!meta||meta.underlyingType===\'SPOT\';\n  const spotScenario=confirmedSpot||scenario&&/\\bGOLD\\b|XAU/i.test(p.name||shot?.name||\'\');\n  if(spotScenario&&spots?.is_genuine_xauusd_spot===true&&!spots.spot_error&&n(spots.xaus)>0&&age!==null&&age>=0&&elapsed!==null&&elapsed>=0&&age+elapsed<=60&&freshTimes([spots.spot_price_as_of],now)){\n   basis=n(spots.xaus);basisAt=spots.spot_price_as_of;\n   basisLabel=confirmedSpot?\'Aktueller XAU/USD-Spot\':\'Gold-Spot-Szenario; Produktbasiswert noch zu bestätigen\';\n  }\n }\n out.basis=basis;\n out.rows.push({label:\'Basiswert / Datenzeit\',text:basis===null?(future?\'Passender, datierter Future-Kontrakt fehlt; kein Spot-Ersatz\':\'Aktueller bestätigter Gold-Spotkurs oder Basiswertzuordnung fehlt\'):basisLabel+\' · \'+basis.toFixed(2)+\' USD · Quellenzeit \'+basisAt});\n if(basis!==null&&ko>0&&[\'LONG\',\'SHORT\'].includes(side)){\n  const signed=(side===\'LONG\'?basis-ko:ko-basis)/basis*100;out.koDistancePct=signed;\n  out.rows.push({label:\'Abstand zur angegebenen KO-Schwelle\',text:(signed<=0?\'Basiswert an / jenseits der angegebenen Schwelle\':\'Puffer \'+signed.toFixed(2)+\'%\')+\' · KO \'+ko+\' USD · \'+(future?\'Basiswert geschätzt; \':\'\')+\'Aktualität und USD-Einheit der KO-Schwelle gesondert bestätigen; kein Nachweis eines vergangenen KO-Ereignisses\'});\n }else out.rows.push({label:\'KO-Abstand\',text:\'Basiswert, Richtung oder KO-Schwelle fehlen / sind nicht zugeordnet\'});\n const c=q?.calculatedProduct;\n if(model?.verifiedSimpleTurbo&&model.underlying===\'XAU/USD\'&&!future&&c?.available&&c.direction===model.direction&&c.ratio===model.ratio&&c.strikeUsd===model.strike&&meta?.ko===model.ko&&n(c.goldUsd)>0&&n(c.usdEur)>0&&n(c.ratio)>0&&n(c.askEur)>0&&freshTimes([c.priceAt,c.goldAt,c.fxDataAt,c.fxEffectiveAt],now)&&freshTimes([c.referenceAt],now,1800)&&Number.isFinite(Date.parse(model.tradingEndAt))&&now<=Date.parse(model.tradingEndAt)){\n  out.leverage=n(c.goldUsd)*n(c.usdEur)*n(c.ratio)/n(c.askEur);\n  out.rows.push({label:\'Berechneter Hebel\',text:out.leverage.toFixed(2)+\'× · geschätzter Brief \'+Number(c.askEur).toFixed(4)+\' EUR · Näherung mit Delta ±1; kein Emittentenhebel · \'+qualityText(c.validation,\'EUR\')});\n }else if(q&&currentQuote(p,now)&&n(q.leverage)>0){\n  out.leverage=n(q.leverage);out.rows.push({label:\'Hebel\',text:out.leverage.toFixed(2)+\'× · \'+(q.leverageEstimated?\'rechnerische Näherung\':\'datierter Emittentenwert\')});\n }else{\n  const r=q?.futureResearch,times=[basisAt,r?.bidAt,r?.askAt,r?.fxDataAt,r?.fxEffectiveAt].map(Date.parse);\n  if(future&&basis!==null&&r?.marketOpen&&now<=Date.parse(r.tradingEndAt)&&n(r.bid)>0&&n(r.ask)>=n(r.bid)&&n(r.ratio)>0&&n(r.usdEur)>0&&freshTimes([r.bidAt,r.askAt,r.fxDataAt,r.fxEffectiveAt],now)&&Math.max(...times)-Math.min(...times)<=15000){\n   out.leverage=basis*r.usdEur*r.ratio/r.ask;\n   out.rows.push({label:\'Berechneter Hebel\',text:out.leverage.toFixed(2)+\'× · Future-Basiswert × USD/EUR × Bezugsverhältnis / datierter Briefkurs · \'+basisLabel+\' · Näherung, kein Emittentenhebel\'});\n  }else out.rows.push({label:\'Aktueller Hebel / Produktkurs\',text:\'Frischer Produktbrief und FX oder bestätigtes Berechnungsmodell fehlen. LV aus dem Produktnamen und alter Screenshot-Brief werden nicht als aktuell übernommen\'});\n }\n const status=manualSnapshotStatus(p,shot,now),spread=shot?.currency===\'EUR\'&&n(shot.bid)>0&&n(shot.ask)>=n(shot.bid)?shot.ask-shot.bid:null;\n out.rows.push({label:\'Produktkurse / Nachweise\',text:(spread===null?\'Kein vollständiges Kursbild\':\'Screenshot-Spread \'+spread.toFixed(4)+\' EUR (\'+(spread/shot.ask*100).toFixed(3)+\'% des Briefs) · \'+(shot.sourceTime||\'Quellenzeit nicht vollständig belegt\'))+\' · \'+(status.complete?\'vollständige Momentaufnahme, keine Live-Verifizierung\':status.reasons.join(\'; \'))});\n const ke=meta?.koEvidence;\n if(ke?.state===\'issuer_reported\'&&ke.currency===\'USD\'&&n(ke.value)>0&&n(ke.value)===n(meta.ko)&&typeof ke.updatedAtRaw===\'string\'&&ke.updatedAtRaw){\n  out.rows.push({label:\'SG-KO-Nachweis\',text:ke.value+\' USD · Emittenten-Aktualisierung \'+ke.updatedAtRaw+(ke.timezoneKnown===true?\'\':\' (Zeitzone nicht angegeben)\')+\' · Abruf \'+(ke.retrievedAt||\'nicht belegt\')+\' · \'+(freshTimes([ke.retrievedAt],now)?\'gerade abgerufene Emittentenangabe\':\'Abruf nicht mehr frisch\')+\'; Gültigkeitszeitraum und Geld-/Briefkurse dadurch nicht bestätigt\'});\n }\n return out;\n}\nfunction renderScreenshotCurrentState(p,bundle,now=Date.now()){\n const state=screenshotCurrentState(p,bundle,now);\n return \'<div class="small" style="margin-top:8px;padding:8px;background:#f4f7fb;border-radius:8px"><b>Berechneter Zustand / offene Nachweise</b>\'+state.rows.map(r=>\'<div style="margin-top:5px"><b>\'+esc(r.label)+\':</b> \'+esc(r.text)+\'</div>\').join(\'\')+\'<div style="margin-top:5px">Teilbewertung / Szenario. Keine zusätzliche Live-Freigabe; Quellenzeiten werden durch die Berechnung nicht erneuert.</div></div>\';\n}\nfunction conditionalCandidate(p,context={},now=Date.now()){\n const q=p.quote,fail=reason=>({ok:false,isin:p.isin,reason,scope:isFutureProduct(p)?q?.futureResearch?.contract||q?.metadata?.contract||"FUTURE":"XAU/USD",direction:isFutureProduct(p)?q?.futureResearch?.direction:q?.productModel?.direction||q?.direction||p.productDirection});\n if(!q||q.isin!==p.isin||!validIsin(p.isin)||p.isinConfirmed!==true)return fail("ISIN oder Produktidentität nicht bestätigt");\n let basis,ask,bid,ko,strike,ratio,fx,errorPrice=0,errorBasis=0,scope,ctx,quality,priceKind,at;\n if(isFutureProduct(p)){\n  const r=q.futureResearch,c=r?.calculatedFuture,a=r?.contractAnalysis;\n  if(!q.productVerified||q.metadata?.underlyingType!=="FUTURE"||q.metadata.contract!==r?.contract||r?.contract!==c?.contract||r?.contract!==a?.contract)return fail("Futures-Kontrakt nicht vollständig bestätigt");\n  if(!c.available||!c.validation?.ready||c.validation.sampleCount<20)return fail("Future-Schätzung: Genauigkeit noch nicht ausreichend gemessen");\n  if(!a.available||!["LONG","SHORT"].includes(a.direction)||a.technicalSourceFamilies!==1||!Object.values(a.frames||{}).every(f=>f.available)||Object.keys(a.frames||{}).length!==4||!freshTimes([a.checkedAt],now,180)||!Number.isFinite(Date.parse(a.expiresAt))||now>Date.parse(a.expiresAt))return fail("ABWARTEN: eigene Kontrakt-MTF fehlt, ist uneinheitlich oder veraltet");\n  if(!r.marketOpen||!Number.isFinite(Date.parse(r.tradingEndAt))||now>Date.parse(r.tradingEndAt)||!freshTimes([r.bidAt,r.askAt,r.fxDataAt,r.fxEffectiveAt,c.priceAt],now)||!freshTimes([c.referenceAt],now,1800))return fail("Future-, Produkt- oder FX-Daten nicht aktuell");\n  const times=[r.bidAt,r.askAt,r.fxDataAt,r.fxEffectiveAt,c.priceAt].map(Date.parse);\n  if(Math.max(...times)-Math.min(...times)>15000)return fail("Future- und Produktdaten zeitlich zu weit auseinander");\n  basis=n(c.priceUsd);ask=n(r.ask);bid=n(r.bid);ko=n(r.ko);strike=n(r.strike);ratio=n(r.ratio);fx=n(r.usdEur);errorBasis=n(c.comparisonErrorUsd);\n  if(!(errorBasis>=Math.max(.1,n(c.validation.maxAbsoluteError)||0)))return fail("Gemessene Future-Abweichung fehlt");\n  if(r.direction!==a.direction)return fail("Produkt passt nicht zum eigenen Futures-Szenario");\n  const timing=n(a.frames[\'5m\'].ema20);\n  if(timing===null||a.direction==="LONG"&&basis-errorBasis<=timing||a.direction==="SHORT"&&basis+errorBasis>=timing)return fail("ABWARTEN: berechnete Kursspanne bestätigt das Kontrakt-Timing nicht eindeutig");\n  scope=r.contract;priceKind="Bestätigter Produktkurs · berechneter Basiswert";quality=c.validation;at=c.priceAt;\n  ctx={direction:a.direction,trend:a.frames[\'1h\'].trend,trend2:a.frames[\'1h\'].ema50>a.frames[\'1h\'].ema200?"LONG":"SHORT",mtf:a.direction,rsi:a.rsi,hist:a.macdHistogram,momentum:a.macdHistogram,atr:a.atr};\n }else if(currentQuote(p,now)){\n  if(!context.spotFresh||!["LONG","SHORT"].includes(context.direction))return fail("ABWARTEN: Spot-Szenario oder aktueller Goldpreis fehlen");\n  basis=n(context.spot);ask=n(q.ask);bid=n(q.bid);ko=n(q.ko);scope="XAU/USD";ctx=context;at=q.quoteAt;\n  priceKind="Bestätigter Emittentenkurs";\n }else{\n  const c=q.calculatedProduct,m=q.productModel;\n  if(!q.productVerified||!m?.verifiedSimpleTurbo||m.isin!==p.isin||m.underlying!=="XAU/USD"||!c?.available||!c.validation?.ready||c.validation.sampleCount<20)return fail("Produktschätzung: Referenz oder ausreichende Genauigkeitsmessung fehlen");\n  if(!context.spotFresh||!["LONG","SHORT"].includes(context.direction)||!freshTimes([c.priceAt,c.goldAt,c.fxDataAt,c.fxEffectiveAt],now)||!freshTimes([c.referenceAt],now,1800)||!Number.isFinite(Date.parse(m.tradingEndAt))||now>Date.parse(m.tradingEndAt))return fail("ABWARTEN: aktuelle Daten oder Spot-Szenario fehlen");\n  if(c.direction!==m.direction||c.ratio!==m.ratio||c.strikeUsd!==m.strike||q.metadata?.ko!==m.ko)return fail("Produktbedingungen passen nicht zum Berechnungsmodell");\n  basis=n(c.goldUsd);ask=n(c.askEur);bid=n(c.bidEur);ko=n(m.ko);strike=n(m.strike);ratio=n(m.ratio);fx=n(c.usdEur);errorPrice=n(c.comparisonErrorEur);\n  const measured=Math.max(.01,n(c.validation.bid?.maxAbsoluteError)||0,n(c.validation.ask?.maxAbsoluteError)||0);\n  if(!(errorPrice>=measured))return fail("Gemessene Produktabweichung fehlt");\n  scope="XAU/USD";ctx=context;quality=c.validation;priceKind="Berechneter Produktkurs";at=c.priceAt;\n }\n if(!(basis>0&&ask>0&&bid>0&&ask>=bid&&ko>0&&ask>errorPrice&&basis>errorBasis))return fail("Unvollständige Preise oder zu große beobachtete Abweichung");\n const direction=isFutureProduct(p)?q.futureResearch.direction:q.productModel?.direction||q.direction;\n if((errorPrice>0||errorBasis>0)&&(!(ratio>0&&fx>0&&strike>0)||direction==="LONG"&&basis-errorBasis<=strike||direction==="SHORT"&&basis+errorBasis>=strike))return fail("Berechnungsparameter fehlen oder Finanzierungsschwelle innerhalb der Spanne erreicht");\n const lev=(u,price)=>ratio>0&&fx>0?u*fx*ratio/price:n(q.leverage);\n const evaluations=[];\n for(const u of [basis-errorBasis,basis+errorBasis])for(const price of [ask-errorPrice,ask+errorPrice]){\n  const e=evaluateProductCore({...p,...ctx,spot:u,ko,price,productDirection:direction,leverage:lev(u,price),spread:ask-bid+2*errorPrice});\n  if(!e.ok||!e.fit||e.direction!==ctx.direction||e.setupScore<35||e.conflictCount>=3)return fail("ABWARTEN: Passung oder KO-Puffer innerhalb der beobachteten Fehlerspanne nicht stabil");\n  evaluations.push(e);\n }\n return {ok:true,isin:p.isin,name:p.name||p.isin,scope,direction:ctx.direction,priceKind,\n  price:ask,priceError:errorPrice,basis,basisError:errorBasis,quality,at,\n  scoreLow:Math.min(...evaluations.map(e=>e.score)),scoreHigh:Math.max(...evaluations.map(e=>e.score)),\n  leverageLow:Math.min(...evaluations.map(e=>e.leverage)),leverageHigh:Math.max(...evaluations.map(e=>e.leverage)),\n  koDistanceMinPct:Math.min(...evaluations.map(e=>e.koDistancePct)),spreadWorst:ask-bid+2*errorPrice};\n}\nfunction rankConditional(products,context={}){\n const now=context.now??Date.now(),groups=new Map(),excluded=[];\n for(const p of products){\n  if(!p.quote){if(p.isin&&p.isinConfirmed)excluded.push({isin:p.isin,scope:isFutureProduct(p)?"FUTURE":"XAU/USD",direction:p.productDirection,reason:"Produktdaten fehlen"});continue;}\n  const c=conditionalCandidate(p,context,now);\n  if(!c.ok){excluded.push(c);continue;}\n  const key=c.scope+" · "+c.direction;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(c);\n }\n const results=Array.from(groups,([scope,candidates])=>{\n  candidates.sort((a,b)=>b.scoreLow-a.scoreLow);\n  const best=candidates[0],unresolved=excluded.some(c=>(c.scope===best.scope||c.scope==="FUTURE"&&best.scope!=="XAU/USD")&&(!c.direction||c.direction===best.direction)),unique=!unresolved&&(candidates.length===1||best.scoreLow>Math.max(...candidates.slice(1).map(c=>c.scoreHigh))+2);\n  return {scope,candidates,favorite:unique?best:null,reason:unique?"Bedingter Favorit unter ausreichend geprüften Kandidaten – aktuellen DEGIRO-Briefkurs vor Einstieg prüfen":"ABWARTEN: Vergleichsdaten fehlen oder kein eindeutiger Favorit innerhalb der beobachteten Fehlerspannen"};\n });\n return {groups:results,excluded,tradeable:false,needsDegiroCheck:true};\n}\nfunction renderConditional(result){\n const rows=result.groups.map(g=>\'<div style="margin-top:10px"><b>\'+esc(g.scope)+\' · \'+(g.favorite?\'Bedingter Favorit: \'+esc(g.favorite.isin):\'ABWARTEN\')+\'</b><div class="small">\'+esc(g.reason)+\'</div>\'+g.candidates.slice(0,3).map(c=>\'<div class="small" style="margin-top:8px"><b>\'+esc(c.isin)+\'</b> · \'+esc(c.priceKind)+\' · Kurs ca. \'+c.price.toFixed(2)+\' EUR\'+(c.priceError?\' · Vergleichsspanne ±\'+c.priceError.toFixed(4)+\' EUR\':\'\')+\' · Basiswert \'+c.basis.toFixed(2)+\' USD\'+(c.basisError?\' ±\'+c.basisError.toFixed(2)+\' USD\':\'\')+\'<br>Technische Passung \'+c.scoreLow+\'–\'+c.scoreHigh+\'/100 · Hebel ca. \'+c.leverageLow.toFixed(2)+\'–\'+c.leverageHigh.toFixed(2)+\'× · KO-Abstand mindestens \'+c.koDistanceMinPct.toFixed(2)+\'% innerhalb der Vergleichsspanne · Datenzeit \'+esc(new Date(c.at).toLocaleTimeString())+(c.quality?\'<br>\'+esc(qualityText(c.quality,c.priceError?\'EUR\':\'USD\')):\'\')+\'</div>\').join(\'\')+\'</div>\').join(\'\');\n const waiting=result.excluded.map(x=>\'<div class="small">\'+esc(x.isin)+\' · \'+esc(x.reason)+\'</div>\').join(\'\');\n return \'<div style="padding:14px;background:#fff;border:1px solid #dbe4f0;border-radius:15px"><b>Bedingter Produktvergleich</b><div class="small">Unterschiedliche Basiswerte werden getrennt bewertet. Beobachtete Fehlerspannen sind keine garantierten Grenzen.</div>\'+(rows||\'<div class="warning">ABWARTEN – noch kein ausreichend geprüfter Kandidat.</div>\')+waiting+\'<div class="small" style="margin-top:9px">Vor Einstieg den aktuellen DEGIRO-Briefkurs und die Produktbedingungen prüfen. Keine automatische Handelsfreigabe.</div></div>\';\n}\nfunction evaluateProduct(p){if(isFutureProduct(p))return{ok:false,fit:false,score:0,reasons:["Gold-Future benötigt eigene Basiswertdaten und Trendprüfung; keine XAU/USD-Spot-Freigabe."],warnings:[]};return evaluateProductCore(p);}\nfunction evaluateProductCore(p){const spot=n(p.spot),ko=n(p.ko),lev=Math.max(1,n(p.leverage)||1),spread=Math.max(0,n(p.spread)||0),atr=n(p.atr),requested=String(p.direction||"NEUTRAL").toUpperCase(),productDirection=String(p.productDirection||directionOf(spot,ko)||"").toUpperCase(),reasons=[],warnings=[];if(spot===null||spot<=0)return{ok:false,fit:false,score:0,reasons:["Kein gültiger XAU/USD-Preis."],warnings:[]};if(!productDirection||!["LONG","SHORT"].includes(productDirection))reasons.push("Richtung des Produkts fehlt.");if(requested!=="NEUTRAL"&&productDirection&&requested!==productDirection)reasons.push("Produkt-Richtung passt nicht zum aktuellen Bob-Szenario.");if(ko!==null&&((productDirection==="LONG"&&ko>=spot)||(productDirection==="SHORT"&&ko<=spot)))return{ok:false,fit:false,score:0,reasons:["KO-Level liegt am oder jenseits des aktuellen Goldpreises – Produkt gesperrt."],warnings:[]};if(ko===null)warnings.push("KO-Level fehlt – KO-Abstand kann nicht geprüft werden.");const koPct=koDistancePct(spot,ko),koDistance=ko===null?null:Math.abs(spot-ko),atrMultiple=koDistance!==null&&atr!==null&&atr>0?koDistance/atr:null;if(koPct!==null&&koPct<2)warnings.push("KO-Abstand unter 2%.");if(koPct!==null&&koPct<1)warnings.push("KO-Abstand unter 1% – sehr enger Puffer.");if(atrMultiple!==null&&atrMultiple<1.5)warnings.push("KO-Puffer kleiner als 1,5 ATR.");if(atrMultiple!==null&&atrMultiple<1)warnings.push("KO-Puffer kleiner als 1 ATR – sehr eng.");if(lev>10)warnings.push("Hebel über 10× – sehr hohe Empfindlichkeit.");if(spread>0)reasons.push("Spread wurde berücksichtigt.");let productScore=100;if(requested!=="NEUTRAL"&&productDirection!==requested)productScore-=60;if(!productDirection)productScore-=20;if(ko===null)productScore-=20;if(koPct!==null&&koPct<2)productScore-=20;if(koPct!==null&&koPct<1)productScore-=20;if(atrMultiple!==null&&atrMultiple<1.5)productScore-=15;if(atrMultiple!==null&&atrMultiple<1)productScore-=20;if(lev>10)productScore-=15;if(spread>0)productScore-=Math.min(10,spread);const quality=technicalQuality(p);const score=Math.round(productScore*0.45+quality.score*0.55);const fit=productScore>=60&&!reasons.some(x=>x.includes("passt nicht"));const conflictCount=quality.reasons.filter(x=>x.includes("widerspricht")).length;const confirmationCount=quality.reasons.filter(x=>x.includes("bestätigt")||x.includes("unterstützt")||x.includes("günstigen")||x.includes("Momentum")).length;if(conflictCount>=3){warnings.push("Mehrere technische Signale widersprechen der Richtung.");}if(requested!=="NEUTRAL"&&quality.score<35){warnings.push("Setup-Qualität sehr niedrig – kein starker technischer Konsens.");}const confidence=Math.max(0,Math.min(100,Math.round(quality.score-(conflictCount*5))));return{ok:true,fit,score:Math.max(0,Math.round(score)),direction:productDirection,koDistancePct:koPct,koDistance,atrMultiple,leverage:lev,reasons:reasons.concat(quality.reasons),warnings,productScore,setupScore:quality.score,confidence,conflictCount,confirmationCount};}\nfunction quoteTiming(q,now=Date.now()){\n const fields=q?[q.quoteAt,q.bidAt,q.askAt,q.leverageAt,q.snapshotAt]:[];\n if(q?.leverageKind==="calculated-gearing")fields.push(q.spotAt,q.fxAt,q.fxDataAt,q.fxEffectiveAt);\n const times=fields.map(v=>typeof v==="string"&&/(?:Z|[+-]\\d{2}:\\d{2})$/.test(v)?Date.parse(v):NaN);\n const ages=times.map(t=>now-t),age=ages.length?Math.max(...ages):NaN;\n const fresh=ages.length===(q?.leverageKind==="calculated-gearing"?9:5)&&ages.every(x=>Number.isFinite(x)&&x>=-5000&&x<=60000)&&now<=Date.parse(q.tradingEndAt);\n return{fresh,ageSeconds:Number.isFinite(age)?Math.max(0,Math.ceil(age/1000)):null};\n}\nfunction currentQuote(p,now=Date.now()){\n const q=p.quote;\n return !isFutureProduct(p)&&!!q&&q.priceKind!=="calculated"&&q.found&&q.eligible===true&&q.marketOpen&&quoteTiming(q,now).fresh&&q.currency==="EUR"&&q.isin===String(p.isin||"").toUpperCase()&&validIsin(p.isin)&&q.price===p.price&&q.leverage===p.leverage&&q.ko===p.ko&&q.spread===p.spread&&q.direction===p.productDirection&&p.isinConfirmed===true;\n}\nfunction rankProducts(products,context={}){const scenario=String(context.direction||"NEUTRAL").toUpperCase();if(scenario==="NEUTRAL")return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Momentum ist NEUTRAL – Bob empfiehlt kein DEGIRO-Produkt."};if(context.requireFreshQuotes&&context.spotFresh!==true)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Goldpreis veraltet oder Kurszeit unbekannt – aktuelle Rangliste gesperrt."};const valid=(products||[]).map((p,i)=>Object.assign({_index:i},p)).filter(p=>String(p.name||p.isin||"").trim()&&n(p.spot)>0&&(!context.requireFreshQuotes||currentQuote(p,context.now??Date.now()))).map(p=>Object.assign(p,{evaluation:evaluateProduct(Object.assign({},p,context))})).filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.direction===scenario).sort((a,b)=>b.evaluation.score-a.evaluation.score);if(context.requireFreshQuotes&&!valid.length)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Keine passenden, bestätigten Produkte mit höchstens 60 Sekunden alten Emittentenkursen für eine Live-Rangliste. Screenshot-Momentaufnahmen werden getrennt geprüft. ISIN unter Details prüfen; veraltete oder fehlende Daten sind gesperrt."};const best=valid[0]?.evaluation;const setupGate=!!best&&(best.setupScore>=35&&best.conflictCount<3);const p=valid[0];const complete=!!p&&n(p.price)>0&&n(p.leverage)>=1&&n(p.ko)>0&&n(p.spread)!==null&&n(p.spread)>=0&&(!p.isin||validIsin(p.isin));return{scenario,candidates:valid.slice(0,4),total:valid.length,tradeable:setupGate&&complete,gateReason:!setupGate?"Technischer Konsens zu schwach oder zu widersprüchlich – kein Favorit.":!complete?"Produktdaten unvollständig oder ISIN ungültig – Kurs, Hebel, KO und Spread unter Details prüfen und ergänzen.":""};}\nfunction scenario(){if(window.BobSession?.expired())return "NEUTRAL";const s=typeof window.confirmedSignalDirection==="function"?window.confirmedSignalDirection():null;if(s&&["LONG","SHORT","NEUTRAL"].includes(String(s).toUpperCase()))return String(s).toUpperCase();const t=String(document.getElementById("signal")?.textContent||"").toUpperCase();return t.includes("LONG")?"LONG":t.includes("SHORT")?"SHORT":"NEUTRAL";}\nfunction spot(){const x=n(window.lastPrice);if(x)return x;const m=String(document.getElementById("price")?.textContent||"").match(/[0-9]+(?:[.,][0-9]+)?/);return m?n(m[0].replace(",",".")):null;}\nfunction atr(){return n(window.A?.at)||n(window.A?.atr)||null;}\nfunction esc(s){return String(s).replace(/[&<>"\']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;","\'":"&#39;"}[c]));}\nlet ocrLoader=null,ocrWorkerPromise=null,ocrQueue=Promise.resolve();\nfunction ocrTimeout(promise,ms,message){\n let timer;\n return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(message)),ms);})]).finally(()=>clearTimeout(timer));\n}\nfunction loadOcr(){\n if(typeof window==="undefined")return Promise.reject(new Error("Browser erforderlich."));\n if(window.Tesseract)return Promise.resolve(window.Tesseract);\n if(ocrLoader)return ocrLoader;\n ocrLoader=new Promise((resolve,reject)=>{\n  const s=document.createElement("script");\n  s.src="/ocr-assets/v5/tesseract.min.js";\n  s.onload=()=>window.Tesseract?resolve(window.Tesseract):reject(new Error("OCR-Bibliothek konnte nicht geladen werden."));\n  s.onerror=()=>{ocrLoader=null;s.remove();reject(new Error("OCR-Bibliothek konnte nicht geladen werden. Bitte erneut versuchen."));};\n  document.head.appendChild(s);\n });\n ocrLoader=ocrTimeout(ocrLoader,30000,"OCR-Bibliothek konnte nicht innerhalb von 30 Sekunden geladen werden").catch(e=>{ocrLoader=null;throw e;});\n return ocrLoader;\n}\nasync function loadOcrWorker(statusId){\n if(ocrWorkerPromise)return ocrWorkerPromise;\n const T=await loadOcr();\n const status=document.getElementById(statusId||"");\n if(status)status.textContent="📦 OCR-Engine wird gestartet …";\n const initializing=T.createWorker("eng",1,{\n  workerPath:"/ocr-assets/v5/worker.min.js",\n  langPath:"/ocr-assets/v5",\n  corePath:"/ocr-assets/v5",\n  workerBlobURL:false,\n  logger:m=>{\n   const s=document.getElementById(statusId||"");\n   if(!s||!m)return;\n   if(m.status==="loading language traineddata")s.textContent="📦 OCR-Sprachdaten werden geladen …";\n   else if(m.status==="recognizing text"&&m.progress)s.textContent="📷 OCR "+Math.round(m.progress*100)+"%";\n  }\n });\n ocrWorkerPromise=ocrTimeout(initializing,60000,"OCR-Engine konnte nicht innerhalb von 60 Sekunden gestartet werden").catch(e=>{ocrWorkerPromise=null;initializing.then(w=>w.terminate()).catch(()=>{});throw e;});\n return ocrWorkerPromise;\n}\nasync function prepareOcrImage(file,statusId,isinPass=false){\n const status=document.getElementById(statusId||"");\n try{\n  const bitmap=await createImageBitmap(file);\n  const maxSide=isinPass?3200:1800,scale=Math.min(isinPass?2:1,maxSide/Math.max(bitmap.width,bitmap.height),Math.sqrt(4500000/(bitmap.width*bitmap.height)));\n  const canvas=document.createElement("canvas");canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));\n  const ctx=canvas.getContext("2d",{alpha:false});if(isinPass)ctx.imageSmoothingEnabled=false;ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();\n  if(status)status.textContent="🖼️ Screenshot für OCR optimiert …";\n  return await new Promise((resolve,reject)=>canvas.toBlob(x=>x?resolve(x):reject(new Error("Bildaufbereitung fehlgeschlagen")),isinPass?"image/png":"image/jpeg",0.86));\n }catch(e){return file;}\n}\nfunction recoverOcrIsins(primary,secondary){\n const candidates=Array.from(new Set((String(secondary||"").toUpperCase().match(/DE[0OCD]{3}[A-Z0-9]{6}[0-9](?![A-Z0-9])/g)||[]).map(x=>"DE000"+x.slice(5)).filter(validIsin))),corrections={};\n const text=String(primary||"").replace(/\\bDE[0O]{3}[A-Z0-9]{7}\\b/g,raw=>{\n  if(validIsin(normalizeOcrIsin(raw).isin))return raw;\n  const matches=candidates.filter(candidate=>{\n   let differences=0;\n   for(let i=0;i<12;i++){if(raw[i]===candidate[i])continue;\n    if(i>=2&&i<5&&raw[i]==="O"&&candidate[i]==="0")continue;\n    if(i>=5&&((raw[i]==="O"&&/[09]/.test(candidate[i]))||(raw[i]==="I"&&/[19]/.test(candidate[i])))){differences++;continue;}\n    return false;\n   }\n   return differences>0&&differences<=2;\n  });\n  if(matches.length!==1)return raw;\n  corrections[matches[0]]=raw;return matches[0];\n });\n return{text,corrections};\n}\nfunction recognizeOcr(file,statusId){\n const job=ocrQueue.then(async()=>{\n  const worker=await loadOcrWorker(statusId);\n  const prepared=await prepareOcrImage(file,statusId);\n  let result;\n  try{\n   result=await ocrTimeout(worker.recognize(prepared),45000,"OCR-Zeitüberschreitung nach 45 Sekunden");\n  }catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});throw e;}\n  if(parseScreenshotCandidates(result.data.text||"").some(x=>!validIsin(x.isin))){\n   let secondaryFailed=false;\n   try{\n    const status=document.getElementById(statusId||"");if(status)status.textContent="🔎 Unsichere ISINs werden mit einem zweiten Lesedurchgang geprüft …";\n    const enlarged=await prepareOcrImage(file,statusId,true);\n    await worker.setParameters({tessedit_pageseg_mode:"11",tessedit_char_whitelist:"0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"});\n    const second=await ocrTimeout(worker.recognize(enlarged),45000,"ISIN-Zweitlesung nach 45 Sekunden beendet");\n    const recovered=recoverOcrIsins(result.data.text,second.data.text);\n    result.data.text=recovered.text;result.data.isinRecoveries=recovered.corrections;\n   }catch(e){secondaryFailed=true;ocrWorkerPromise=null;await worker.terminate().catch(()=>{});console.warn("[BOB] ISIN-Zweitlesung",e&&e.message?e.message:e);}\n   finally{try{if(!secondaryFailed)await worker.setParameters({tessedit_pageseg_mode:"3",tessedit_char_whitelist:""});}catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});}}\n  }\n  return result;\n });\n ocrQueue=job.catch(()=>{});\n return job;\n}\nfunction ocrExtract(text){\n const raw=String(text||"").replace(/\\r/g," ");\n const upper=raw.toUpperCase();\n const ident=normalizeOcrIsin((raw.match(/\\b[A-Z]{2}[A-Z0-9]{10}\\b/)||[])[0]||"");\n const isin=ident.isin;\n const levMatch=raw.match(/\\b(?:HEBEL|LEVERAGE)\\s*[:=]?\\s*(\\d+(?:[.,]\\d+)?)\\s*(?:[X×]\\b)?|\\b(\\d+(?:[.,]\\d+)?)\\s*[X×](?![A-Z0-9])/i);\n const lev=levMatch?(levMatch[1]||levMatch[2]||""):"";\n const ko=(raw.match(/\\b(?:KO|KNOCK[- ]?OUT|BARRIERE|BARRIER|BAR|SL)\\b\\s*[:=]?\\s*([0-9]{3,6}(?:[.,][0-9]+)?)/i)||[])[1]||"";\n const spread=(raw.match(/(?:SPREAD|GELD\\s*\\/\\s*BRIEF|BID\\s*\\/\\s*ASK)\\s*[:=]?\\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";\n const price=(raw.match(/(?:PRODUKTKURS|PRODUKTPREIS|KURS|PREIS|PRICE|QUOTE)\\s*[:=]?\\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";\n const direction=upper.includes("SHORT")||upper.includes("PUT")?"SHORT":(upper.includes("LONG")||upper.includes("CALL")?"LONG":"");\n const lines=raw.split(/\\n+/).map(x=>x.trim()).filter(Boolean);\n const nameLine=lines.find(x=>/GOLD|XAU|TURBO|KNOCK|CALL|PUT/i.test(x)&&x.length<100)||"";\n return {isin,originalIsin:ident.originalIsin,leverage:lev.replace(",","."),ko:ko.replace(",","."),spread:spread.replace(",","."),price:price.replace(",","."),direction,name:nameLine};\n}\nconst combinedReferences=new Map();\nconst productQuotes=new Map(),futureResearchQuotes=new Map(),pendingQuotes=new Set(),detailScreenshots=new Map(),rowVersions=new Map();\nfunction populateCandidateRows(items){\n // Replacing a screenshot must not retain prices, confirmation or surplus products.\n for(let i=1;i<=12;i++){\n  const x=items[i-1],values=x?{name:x.name||x.isin,isin:x.isin,dir:x.direction,price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread}:{};\n  for(const k of ["name","isin","dir","price","lev","ko","spread"]){const el=document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\');if(el)el.value=values[k]??"";}\n  productQuotes.delete(i);futureResearchQuotes.delete(i);detailScreenshots.delete(i);rowVersions.set(i,(rowVersions.get(i)||0)+1);\n  const upload=document.getElementById("dgDetailShot"+i);if(upload)upload.value="";\n  const confirmed=document.querySelector(\'[data-dg="confirmed"][data-i="\'+i+\'"]\');if(confirmed)confirmed.checked=false;\n  const status=document.getElementById("dgOcrStatus"+i),research=document.getElementById("dgResearch"+i);\n  if(research)research.textContent="🌐 Zusatzdaten: warten auf ISIN.";\n  if(status)status.textContent=!x?"Wartet auf Screenshot.":!validIsin(x.isin)?"⚠️ ISIN unsicher: "+(x.isin||"nicht erkannt")+". Bitte direkt am Screenshot korrigieren; Produkt bleibt gesperrt.":x.ocrRecovery?"⚠️ OCR-Zweitlesung: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Am Screenshot prüfen und bestätigen.":x.originalIsin?"⚠️ OCR normalisiert: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Bitte am Screenshot prüfen.":"✅ Aus Screenshot erkannt – ISIN am Screenshot prüfen und bestätigen.";\n }\n}\n\nasync function enrichProduct(i){\n const field=k=>document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\');\n const isin=(field("isin")?.value.trim()||"").toUpperCase(),meta=document.getElementById("dgResearch"+i);\n if(!isin)return;\n if(!validIsin(isin)){productQuotes.delete(i);futureResearchQuotes.delete(i);if(meta)meta.textContent="ISIN-Prüfziffer ungültig: bitte am Screenshot korrigieren.";return;}\n if(pendingQuotes.has(i))return;\n pendingQuotes.add(i);\n const version=rowVersions.get(i)||0;\n try{\n  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),35000);\n  let res;try{res=await fetch("/api/degiro/enrich?isin="+encodeURIComponent(isin),{cache:"no-store",signal:ctl.signal});}finally{clearTimeout(timer);}\n  if(!res.ok)throw Error("Produktrecherche nicht verfügbar");\n  const x=await res.json();\n  if((rowVersions.get(i)||0)!==version||(field("isin")?.value.trim()||"").toUpperCase()!==isin)return;\n  productQuotes.delete(i);\n  futureResearchQuotes.delete(i);\n  if(x.isin===isin&&(x.futureResearch||!x.found&&x.calculatedProduct))futureResearchQuotes.set(i,x);\n  if(x.isin===isin&&x.productVerified&&x.metadata?.underlyingType==="FUTURE")futureIsins.add(isin);\n  if(x.isin===isin&&x.productVerified&&x.metadata){\n   if(["LONG","SHORT"].includes(x.metadata.direction)&&field("dir"))field("dir").value=x.metadata.direction;\n   if(n(x.metadata.ko)>0&&field("ko"))field("ko").value=x.metadata.ko;\n  }\n  if(x.found&&x.isin===isin){\n   productQuotes.set(i,x);\n   for(const [key,val] of Object.entries({price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread,dir:x.direction})){if(field(key))field(key).value=val;}\n   if(meta)meta.innerHTML="🌐 "+esc(x.source)+" · Geld "+esc(x.bid)+" / Brief "+esc(x.ask)+" EUR · Spread "+esc(x.spread)+" EUR ("+esc(x.spreadPct)+"%) · Hebel "+esc(Number(x.leverage).toFixed(2))+"×"+(x.leverageEstimated?" (rechnerische Näherung)":"")+" · Kurszeit "+esc(new Date(x.quoteAt).toLocaleString())+" · "+\'<span id="dgQuoteState\'+i+\'">\'+(x.eligible?"aktuell":"GESPERRT: "+esc(x.reason))+\'</span>\'+". Ausführbarer DEGIRO-Kurs kann abweichen."+(x.leverageNote?" "+esc(x.leverageNote):"")+ \'<span id="dgCalculatedState\'+i+\'">\'+esc(productEstimateText(x))+\'</span>\';\n  }else if(meta){\n   const info=x.productVerified&&x.metadata;\n   meta.textContent="🌐 "+(x.source?x.source+" · ":"")+(info?"ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · ":"")+(x.reason||"Keine verlässlich datierten Emittentenkurse verfügbar")+futureResearchText(x)+productEstimateText(x)+". Produkt für aktuelle Rangliste gesperrt.";\n  }\n }catch(e){productQuotes.delete(i);futureResearchQuotes.delete(i);if(meta)meta.textContent="🌐 Recherche nicht erreichbar: Produkt für aktuelle Rangliste gesperrt.";}\n finally{pendingQuotes.delete(i);rankUI();}\n}\n// Only explicitly labelled source timestamps count. Never use upload/device time.\nfunction sourceTimestamp(value){\n const m=String(value||\'\').trim().match(/^(\\d{2})[/.](\\d{2})[/.](\\d{4})\\s+(\\d{2}):(\\d{2}):(\\d{2})\\s*(Z|UTC|CET|CEST|[+-]\\d{2}:?\\d{2})$/i);\n if(!m)return null;\n const [,dd,mm,yy,hh,mi,ss,zone]=m,parts=[+yy,+mm,+dd,+hh,+mi,+ss];\n const local=Date.UTC(+yy,+mm-1,+dd,+hh,+mi,+ss),date=new Date(local);\n if(date.getUTCFullYear()!==parts[0]||date.getUTCMonth()+1!==parts[1]||date.getUTCDate()!==parts[2]||+hh>23||+mi>59||+ss>59)return null;\n const z=zone.toUpperCase();let offset=0;\n if(z===\'CET\')offset=60;else if(z===\'CEST\')offset=120;\n else if(z!==\'Z\'&&z!==\'UTC\'){const p=z.match(/^([+-])(\\d{2}):?(\\d{2})$/);if(+p[2]>14||+p[3]>59||+p[2]===14&&+p[3]!==0)return null;offset=(+p[2]*60+ +p[3])*(p[1]===\'-\'?-1:1);}\n return new Date(local-offset*60000).toISOString();\n}\nfunction screenshotTimes(raw){\n const out={};\n for(const [key,label] of Object.entries({quote:\'Kurszeit|Kursstand|Quote time\',bid:\'Geldzeit|Bid time\',ask:\'Briefzeit|Ask time\',leverage:\'Hebelzeit|Leverage time\',ko:\'KO-Zeit|KO time\'})){\n  const matches=Array.from(String(raw).matchAll(new RegExp(\'(?:^|\\\\n)\\\\s*(?:\'+label+\')\\\\s*[:=]?\\\\s*([^\\\\n]+)\',\'gi\')));\n  // Multiple conflicting labels are ambiguous. A minute-only time cannot prove 60s.\n  out[key]=matches.length===1?{present:true,text:matches[0][1].trim(),at:sourceTimestamp(matches[0][1])}:{present:matches.length>0,text:\'\',at:null};\n }\n return out;\n}\nfunction evidenceTiming(e,now=Date.now()){\n const at=e?.at,parsed=typeof at===\'string\'&&/(?:Z|[+-]\\d{2}:\\d{2})$/.test(at)?Date.parse(at):NaN;\n const age=now-parsed;\n return{fresh:Number.isFinite(age)&&age>=0&&age<=60000,ageSeconds:Number.isFinite(age)?Math.ceil(age/1000):null};\n}\nfunction fieldSourceTime(x,key){\n const field={Geld:\'bid\',Brief:\'ask\',Hebel:\'leverage\',KO:\'ko\'}[key];\n if(x.times?.[field]?.present)return x.times[field].at;\n return [\'Geld\',\'Brief\',\'Kurs\',\'Spread\'].includes(key)?x.times?.quote?.at||null:null;\n}\nfunction manualSnapshotStatus(p,x,now=Date.now()){\n const reasons=[],e=x?.evidence||{};\n if(isFutureProduct(p))reasons.push(p.quote?.futureResearch?.contractAnalysis?.available?"Gold-Future: Kontraktanalyse vorhanden; bedingten Vergleich beachten. Keine Spot-Freigabe":"Gold-Future: eigene Basiswertdaten und Trendprüfung erforderlich; keine Spot-Freigabe");\n if(!x||x.isin!==String(p.isin||\'\').trim().toUpperCase()||!validIsin(p.isin))reasons.push(\'Bildidentität nicht bestätigt\');\n if(p.isinConfirmed!==true)reasons.push(\'Erkannte Werte und Quellenzeiten am Original bestätigen\');\n if(x?.currency!==\'EUR\'||!(n(x?.bid)>0)||!(n(x?.ask)>=n(x?.bid)))reasons.push(\'Geld und Brief in EUR fehlen\');\n const pairs={Geld:x?.bid,Brief:x?.ask,Spread:p.spread,Hebel:p.leverage,KO:p.ko};\n for(const [key,value] of Object.entries(pairs)){\n  if(n(value)===null||n(e[key]?.value)!==n(value)||!evidenceTiming(e[key],now).fresh)reasons.push(key+\': eigener Zeitnachweis fehlt oder älter als 60 Sekunden\');\n }\n if(n(p.price)!==n(x?.ask)||!(n(p.leverage)>=1)||!(n(p.ko)>0)||n(p.spread)===null||Math.abs(n(p.spread)-(n(x?.ask)-n(x?.bid)))>0.000001)reasons.push(\'Produktwerte unvollständig oder widersprüchlich\');\n if(x?.delayed)reasons.push(\'Bild weist auf verzögerte Kurse hin\');\n return{complete:reasons.length===0,reasons,liveVerified:false};\n}\nfunction rankManualSnapshots(products,context={}){\n const scenario=String(context.direction||\'NEUTRAL\').toUpperCase(),now=context.now??Date.now();\n if(![\'LONG\',\'SHORT\'].includes(scenario)||context.spotFresh!==true)return{candidates:[],total:0,liveVerified:false};\n const candidates=(products||[]).filter(p=>p.productDirection===scenario&&!currentQuote(p,now)&&manualSnapshotStatus(p,p.snapshot,now).complete)\n  .map(p=>({...p,evaluation:evaluateProduct({...p,...context})}))\n  .filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.setupScore>=35&&p.evaluation.conflictCount<3)\n  .sort((a,b)=>b.evaluation.score-a.evaluation.score);\n return{candidates,total:candidates.length,liveVerified:false};\n}\nfunction productUploadCards(products,direction,now=Date.now()){\n const cards=(products||[]).map((p,z)=>({p,i:z+1})).filter(({p})=>p.name||p.isin);\n cards.sort((a,b)=>Number(b.p.productDirection===direction)-Number(a.p.productDirection===direction));\n if(!cards.length)return \'<div class="small">Zuerst eine DEGIRO-Produktliste hochladen. Danach erscheint für jedes erkannte Produkt ein eigener Bild-Upload.</div>\';\n const requested=cards.filter(({p})=>needsDirectionalData(p,direction));\n const requestHtml=requested.length?\'<div style="padding:10px;border:1px solid #e1e7f0;border-radius:12px;margin-bottom:10px"><b>Weitere Screenshots benötigt · \'+esc(direction)+\'</b>\'+requested.map(({p,i})=>\'<div class="small" style="margin-top:6px"><b>ISIN \'+esc(p.isin||\'unklar\')+\'</b> · \'+esc(Array.from(new Set([...missingProductData(p),...manualSnapshotStatus(p,p.snapshot,now).reasons])).join(\' · \'))+\' <button data-detail-upload="\'+i+\'">Bilder ergänzen</button></div>\').join(\'\')+\'</div>\':\'\';\n return requestHtml+\'<b>📷 Gespeicherte Produkte · Bilder ergänzen</b><div class="small">\'+([\'LONG\',\'SHORT\'].includes(direction)?\'Passende \'+esc(direction)+\'-Produkte stehen zuerst.\':\'ABWARTEN: Bilder können ergänzt werden; es gibt keine Produktempfehlung.\')+\'</div>\'+cards.map(({p,i})=>{\n  const state=manualSnapshotStatus(p,p.snapshot,now),live=currentQuote(p,now),issuerData=currentQuote({...p,isinConfirmed:true},now);\n  const missing=issuerData?(p.isinConfirmed?[]:["ISIN und Produktzuordnung am Original bestätigen"]):live||state.complete?[]:Array.from(new Set([...missingProductData(p),...state.reasons]));\n  return \'<div style="margin-top:8px;padding:10px;background:#fff;border:1px solid #e1e7f0;border-radius:12px"><b>\'+esc(p.isin||p.name)+\'</b> · \'+esc(p.productDirection||\'Richtung unklar\')+\n   \'<div class="small">\'+esc(p.name||\'\')+\'</div><div class="small">\'+(issuerData?\'Datierte Emittentendaten vorhanden; \'+(p.isinConfirmed?\'DEGIRO-Ausführungskurs prüfen.\':\'ISIN und Produktzuordnung am Original bestätigen.\'):state.complete?\'Zeitlich vollständige Momentaufnahme · keine Live-Freigabe.\':\'Fehlt / prüfen: \'+esc(missing.join(\' · \')))+\'</div>\'+\n   \'<div class="small">Zwei Screenshots pro ISIN möglich: Kursbild und Produktdetails gemeinsam auswählen oder nacheinander ergänzen. Beide müssen die ISIN zeigen.</div><button data-detail-upload="\'+i+\'">Screenshots für dieses Produkt hinzufügen</button> <button data-card-research="\'+i+\'">Internetrecherche erneut prüfen</button><label class="small" style="display:block"><input data-card-confirm="\'+i+\'" type="checkbox" \'+(p.isinConfirmed?\'checked\':\'\')+\'> ISIN, Werte und Quellenzeiten am Original geprüft</label>\'+\n   screenshotSummary(p.snapshot)+renderScreenshotCurrentState(p,window.liveBundleCache,now)+\'<div class="small">\'+esc(document.getElementById(\'dgOcrStatus\'+i)?.textContent||\'\')+\'</div><div class="small">\'+esc(supplementaryHint(missing))+\'</div></div>\';\n }).join(\'\');\n}\nconst IDENTITY_KEY=\'bobDegiroIdentitiesV1\';\nfunction saveIdentities(){\n try{const items=[];for(let i=1;i<=12;i++){const read=k=>document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\')?.value||\'\';if(validIsin(read(\'isin\')))items.push({isin:read(\'isin\').toUpperCase(),name:read(\'name\'),direction:read(\'dir\')});}localStorage.setItem(IDENTITY_KEY,JSON.stringify(items));}catch(_){}\n}\nfunction loadIdentities(){\n try{const items=JSON.parse(localStorage.getItem(IDENTITY_KEY)||\'[]\');return Array.isArray(items)?items.filter(x=>x&&validIsin(x.isin)).slice(0,12).map(x=>({isin:x.isin,name:String(x.name||x.isin),direction:[\'LONG\',\'SHORT\'].includes(x.direction)?x.direction:\'\'})):[];}catch(_){return [];}\n}\nfunction needsDirectionalData(p,direction){\n return [\'LONG\',\'SHORT\'].includes(direction)&&p.productDirection===direction&&!currentQuote({...p,isinConfirmed:true})&&!manualSnapshotStatus(p,p.snapshot).complete;\n}\n\nfunction detailScreenshotData(text,expectedIsin){\n const raw=String(text||""),ids=Array.from(new Set(parseScreenshotCandidates(raw).map(x=>x.isin)));\n if(!validIsin(expectedIsin))return{ok:false,reason:"Bitte zuerst die ISIN dieses Produkts am Screenshot prüfen und korrigieren."};\n if(ids.length!==1||ids[0]!==expectedIsin)return{ok:false,reason:ids.length?"Der Screenshot gehört nicht eindeutig zu "+expectedIsin+". Bitte nur dieses Produkt mit sichtbarer ISIN hochladen.":"ISIN im Zusatzbild fehlt. Bitte die ISIN zusammen mit den Produktdaten zeigen."};\n const x=ocrExtract(raw.replace(/(\\bBAR\\s*\\n)[@©●•®]\\s*(?=[0-9])/gi,"$1"));\n if(!x.price){const top=raw.match(/(?:^|\\n)\\s*€\\s*([0-9]+(?:[.,][0-9]+)?)\\b/);if(top)x.price=top[1].replace(",",".");}\n const amount=label=>{const m=raw.match(new RegExp("\\\\b(?:"+label+")(?!\\\\s*(?:Vol|Volumen))\\\\s*[:=]?\\\\s*(?:€|EUR)?\\\\s*([0-9]+(?:[.,][0-9]+)?)","i"));return m?Number(m[1].replace(",",".")):null;};\n const bid=amount("Geld|Bid"),ask=amount("Brief|Ask");\n if((bid!==null&&bid<=0)||(ask!==null&&ask<=0)||(bid!==null&&ask!==null&&ask<bid))return{ok:false,reason:"Geld-/Briefkurse widersprüchlich gelesen. Bitte ein schärferes Bild hochladen."};\n const stamp=(raw.match(/\\b\\d{2}[/.]\\d{2}[/.]\\d{4}\\s+\\d{2}:\\d{2}(?::\\d{2})?\\b/)||[])[0]||"";\n const currency=/\\bEUR\\b|€/.test(raw)?"EUR":"";\n if(bid!==null&&ask!==null&&currency==="EUR"){x.price=String(ask);x.spread=String(Math.round((ask-bid)*1000000)/1000000);}\n if(!x.leverage){const lv=raw.match(/\\bLV\\s+(\\d+(?:[.,]\\d+)?)/i);if(lv)x.leverage=lv[1].replace(",",".");}\n return{ok:true,...x,bid,ask,currency,sourceTime:stamp,times:screenshotTimes(raw),delayed:/verzögert|delayed/i.test(raw)};\n}\nasync function readScreenshot(i,file){\n const status=document.getElementById("dgOcrStatus"+i),field=k=>document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\');\n if(!file)return;\n const expected=(field("isin")?.value||"").trim().toUpperCase(),version=(rowVersions.get(i)||0)+1;rowVersions.set(i,version);\n if(status)status.textContent="📷 Zusatzbild für "+expected+" wird kostenlos im Browser gelesen …";\n try{\n  const result=await recognizeOcr(file,"dgOcrStatus"+i);\n  if((rowVersions.get(i)||0)!==version||(field("isin")?.value||"").trim().toUpperCase()!==expected)return;\n  const x=detailScreenshotData(result.data.text,expected);\n  if(!x.ok){if(status)status.textContent="⚠️ "+x.reason;return;}\n  productQuotes.delete(i);\n  for(const [k,v] of Object.entries({dir:x.direction,price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread})){if(v!==""&&v!==null&&v!==undefined&&field(k))field(k).value=v;}\n  const merged=mergeScreenshotEvidence(detailScreenshots.get(i),x,file.name);\n  if(merged.clearSpread&&field("spread"))field("spread").value="";\n  detailScreenshots.set(i,merged);if(field("confirmed"))field("confirmed").checked=false;\n  if(status)status.textContent="✅ Zusatzbild zugeordnet. Gelesene Werte unter Details am Screenshot prüfen. "+(merged.sourceTime?"Kurszeit im Bild: "+merged.sourceTime:"Kurszeit im Bild fehlt.");\n  const meta=document.getElementById("dgResearch"+i);if(meta)meta.textContent="📷 DEGIRO-Momentaufnahme · "+(merged.bid!==null?"Geld "+merged.bid+" / Brief "+(merged.ask??"fehlt")+" "+merged.currency+" · ":"")+"keine laufenden Live-Daten. Fehlende oder nicht verlässlich datierte Werte bleiben für die aktuelle Rangliste gesperrt.";\n  rankUI();\n }catch(e){if((rowVersions.get(i)||0)!==version)return;if(status)status.textContent="⚠️ Zusatzbild konnte nicht gelesen werden. Bitte erneut versuchen oder die Angaben unter Details ergänzen.";}\n}\nfunction mergeScreenshotEvidence(previous,x,source){\n previous=previous||{};\n const evidence={...(previous.evidence||{})};\n const hasQuote=n(x.price)!==null||x.bid!==null&&x.bid!==undefined||x.ask!==null&&x.ask!==undefined;\n // Keep the original quote\'s timestamp when adding only static product details.\n const merged={...previous,...x,evidence,clearSpread:false};\n if(!hasQuote){for(const key of ["bid","ask","currency","sourceTime","delayed"])merged[key]=previous[key]??x[key];}\n else {for(const key of ["Kurs","Geld","Brief","Spread"])delete evidence[key];merged.clearSpread=n(x.spread)===null;}\n for(const [key,value] of Object.entries({Richtung:x.direction,Kurs:x.price,Hebel:x.leverage,KO:x.ko,Geld:x.bid,Brief:x.ask,Spread:x.spread})){if(value!==""&&value!==null&&value!==undefined)evidence[key]={value,source,at:fieldSourceTime(x,key)};}\n if(hasQuote&&evidence.Spread){const times=[evidence.Geld?.at,evidence.Brief?.at];evidence.Spread.at=times.every(Boolean)?times.sort()[0]:null;}\n for(const [key,field] of Object.entries({Kurs:"price",Hebel:"leverage",KO:"ko",Spread:"spread",Richtung:"direction"})){merged[field]=evidence[key]?.value??"";}\n return merged;\n}\nfunction supplementaryHint(missing){\n const identity=missing.includes("eindeutige ISIN");\n const staticFields=missing.some(v=>["Produktrichtung","Hebel","KO-Schwelle"].includes(v));\n const quotes=missing.some(v=>["Produktkurs","Geld-/Briefkurse für den Spread","bestätigte aktuelle Kursdaten mit Zeitstempeln"].includes(v));\n return (identity?"Bitte ein Bild mit eindeutig sichtbarer ISIN hochladen. ":"")+(staticFields?"Bitte Produktübersicht mit Richtung, Hebel und KO-Schwelle ergänzen. Für Hebel und KO sind eigene datierte Quellen erforderlich; ein neues Kursbild erneuert sie nicht. ":"")+(quotes?"Bitte Kursdatenbild mit ISIN, Geld, Brief und ausdrücklich zugeordneter Kurszeit (Datum, Sekunden, Zeitzone) ergänzen. Uploadzeit zählt nicht. ":"")+"Erkannte Werte bitte am Original prüfen.";\n}\nfunction screenshotTimeLabel(x){\n const e=x?.evidence?.Geld;\n if(e?.at){const t=evidenceTiming(e);return \'Kursquelle: \'+e.at+\' · \'+(t.fresh?\'höchstens 60 Sekunden alt\':t.ageSeconds===null?\'Zeit unklar\':t.ageSeconds+\' s alt / gesperrt\')+\' · Momentaufnahme, keine Live-Verifizierung.\';}\n return x?.sourceTime?\'Kursstand im Bild: \'+x.sourceTime+\' · Aktualität nicht verifiziert. Vollständige, ausdrücklich zugeordnete Kurszeit mit Sekunden und Zeitzone erforderlich.\':\'Kurszeit fehlt – Aktualität nicht prüfbar. Kein Live-Kurs.\';\n}\nfunction screenshotSummary(x){\n if(!x)return "";\n const rows=Object.entries(x.evidence||{}).map(([key,e])=>{const t=evidenceTiming(e);return \'<tr><td>\'+esc(key)+\'</td><td>\'+esc(e.value)+\'</td><td>\'+esc(e.source)+\'</td><td>\'+esc(e.at||\'Zeit / Zeitzone fehlt\')+(key===\'Richtung\'?\'\':\' · \'+esc(t.ageSeconds===null?\'gesperrt\':t.ageSeconds+\' s · \'+(t.fresh?\'≤ 60 s\':\'gesperrt\')))+\'</td></tr>\';}).join("");\n return \'<div class="small"><b>Erkannte Angaben – bitte prüfen</b><table style="width:100%"><thead><tr><th>Angabe</th><th>Wert</th><th>Bildquelle</th><th>Quellenzeit</th></tr></thead><tbody>\'+rows+\'</tbody></table>\'+esc(screenshotTimeLabel(x))+\'</div>\';\n}\nfunction manualProductMissing(p){\n const missing=[];\n if(!validIsin(p.isin))missing.push("gültige ISIN");\n if(!(n(p.price)>0))missing.push("Produktkurs");\n if(!(n(p.leverage)>=1))missing.push("Hebel");\n if(!(n(p.ko)>0))missing.push("KO-Schwelle");\n if(n(p.spread)===null||n(p.spread)<0)missing.push("Spread");\n return missing;\n}\nfunction missingProductData(p){\n const missing=[];\n if(!validIsin(p.isin))missing.push("eindeutige ISIN");\n if(!["LONG","SHORT"].includes(p.productDirection))missing.push("Produktrichtung");\n if(!(n(p.price)>0))missing.push("Produktkurs");\n if(!(n(p.leverage)>=1))missing.push("Hebel");\n if(!(n(p.ko)>0))missing.push("KO-Schwelle");\n if(n(p.spread)===null||n(p.spread)<0)missing.push("Geld-/Briefkurse für den Spread");\n if(!currentQuote(p))missing.push("bestätigte aktuelle Kursdaten mit Zeitstempeln");\n return missing;\n}\nfunction parseScreenshotCandidates(text){\n const raw=String(text||"").replace(/\\r/g,"");\n const matches=Array.from(raw.matchAll(/\\b[A-Z]{2}[A-Z0-9]{10}\\b/g));\n const starts=matches.map((m,i)=>{\n  const lineStart=raw.lastIndexOf("\\n",m.index-1)+1;\n  const lower=i?matches[i-1].index+matches[i-1][0].length:0;\n  const preceding=raw.slice(lower,lineStart);\n  const headings=Array.from(preceding.matchAll(/(?:^|\\n)([^\\n]*(?:GOLD|XAU|TURBO)[^\\n]*(?:LONG|SHORT|CALL|PUT)[^\\n]*)/gi));\n  const heading=headings[headings.length-1];\n  return heading?lower+heading.index+(heading[0].startsWith("\\n")?1:0):(i?lineStart:0);\n });\n const hits=[];\n matches.forEach((m,i)=>{\n  const x=ocrExtract(raw.slice(starts[i],i+1<matches.length?starts[i+1]:raw.length));\n  const ident=normalizeOcrIsin(m[0]);x.isin=ident.isin;x.originalIsin=ident.originalIsin;\n  const existing=hits.find(v=>v.isin===x.isin);\n  if(existing){Object.keys(x).forEach(k=>{if(!existing[k]&&x[k])existing[k]=x[k];});}\n  else if(hits.length<12)hits.push(x);\n });\n return hits;\n}\nfunction inject(){\n if(document.getElementById("dgTop3"))return;\n const a=document.getElementById("dgProductOut"); if(!a)return;\n const b=document.createElement("div");\n b.id="dgTop3";\n b.style.cssText="margin-top:14px;padding:16px;background:#f7f9fc;border-radius:20px;border:1px solid #e5eaf2";\n b.innerHTML=\'<div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b><div class="small">Produktliste erfassen → Bilder pro ISIN ergänzen → belegte Daten vergleichen</div></div></div>\'+\n \'<div style="margin-top:14px;padding:12px;background:#fff;border-radius:16px;border:1px solid #e1e7f0">\'+\n \'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><b>📷 DEGIRO-Screenshots</b><span class="small">2–3 Bilder</span></div>\'+\n \'<div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px">\'+\n \'<label for="dgCentralShot1" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">\'+\n \'<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>\'+\n \'<span id="dgShotLabel1" style="margin-top:7px;font-weight:700;font-size:12px">Bild 1</span><input id="dgCentralShot1" type="file" accept="image/*" style="display:none"></label>\'+\n \'<label for="dgCentralShot2" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">\'+\n \'<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>\'+\n \'<span id="dgShotLabel2" style="margin-top:7px;font-weight:700;font-size:12px">Bild 2</span><input id="dgCentralShot2" type="file" accept="image/*" style="display:none"></label>\'+\n \'<label for="dgCentralShot3" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">\'+\n \'<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>\'+\n \'<span id="dgShotLabel3" style="margin-top:7px;font-weight:700;font-size:12px">Bild 3 <span style="font-weight:400">(optional)</span></span><input id="dgCentralShot3" type="file" accept="image/*" style="display:none"></label>\'+\n \'</div><div id="dgCentralStatus" class="small" style="margin-top:9px">Noch keine Bilder hochgeladen.</div></div>\'+\n \'<div id="dgMissingProducts" style="margin-top:12px"></div>\'+\n \'<div id="dgManualSnapshots" style="margin-top:12px"></div>\'+\n \'<div id="dgConditionalOut" style="margin-top:12px"></div>\'+\n \'<div id="dgTop3Out" style="margin-top:12px"></div>\'+\n \'<details style="margin-top:10px"><summary style="cursor:pointer;font-weight:700">Details / manuelle Kursnachweise</summary><div class="small" style="margin:7px 0">Hier lassen sich Screenshotwerte korrigieren und datierte Stuttgart-/Onvista-Nachweise bedingt auswerten.</div><div id="dgTop3Inputs"></div></details>\'+\n \'<button style="margin-top:10px;width:100%" id="dgRankBtn">🔎 Analyse erneut ausführen</button>\';\n a.parentNode.insertBefore(b,a.nextSibling);\n const q=b.querySelector("#dgTop3Inputs");\n for(let i=1;i<=12;i++){\n  const r=document.createElement("div");\n  r.style.cssText="margin:8px 0;padding:9px;background:#fff;border-radius:10px";\n  r.innerHTML=\'<b>Kandidat \'+i+\'</b><div id="dgOcrStatus\'+i+\'" class="small" style="margin-top:5px">Wartet auf Screenshot.</div><div id="dgResearch\'+i+\'" class="small research" style="margin-top:5px">🌐 Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="\'+i+\'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="\'+i+\'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="\'+i+\'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="\'+i+\'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="\'+i+\'" type="number" step=".01" placeholder="KO-Level"><input data-dg="spread" data-i="\'+i+\'" type="number" step=".01" min="0" placeholder="Spread"><input data-dg="isin" data-i="\'+i+\'" placeholder="ISIN"></div><label class="small"><input data-dg="confirmed" data-i="\'+i+\'" type="checkbox"> ISIN, erkannte Werte und zugeordnete Quellenzeiten am Original geprüft</label><button data-research="\'+i+\'">Aktuelle Produktdaten laden</button>\';\n  r.insertAdjacentHTML("beforeend",\'<div id="dgEvidence\'+i+\'"></div><div style="margin-top:8px"><label for="dgDetailShot\'+i+\'">📷 Zusatzbild für dieses Produkt hochladen</label><input id="dgDetailShot\'+i+\'" type="file" accept="image/*" multiple><div class="small">Produktdetail oder Kursdaten mit sichtbarer ISIN. Mehrere Bilder können nacheinander ergänzt werden. Kurszeit braucht Datum, Sekunden und Zeitzone; Hebel und KO benötigen eigene Quellenzeiten. Fehlende Zeiten werden nicht ergänzt.</div></div>\');\n  r.insertAdjacentHTML("beforeend",window.BobCombined.form(i));\n  r.querySelector("[data-combined-save]").addEventListener("click",()=>{\n   const read=k=>r.querySelector(\'[data-combined="\'+k+\'"]\')?.value.trim()||"";\n   const reviewed=r.querySelector(\'[data-combined="reviewed"]\').checked;\n   const isin=r.querySelector(\'[data-dg="isin"]\').value.trim().toUpperCase();\n   const barriers=[1,2].filter(z=>read("ko"+z)).map(z=>({isin,value:read("ko"+z),currency:"USD",source:read("koSource"+z),url:read("koUrl"+z),at:read("koAt"+z),validUntil:read("koUntil"+z),confirmed:reviewed}));\n   combinedReferences.set(i,{isin,source:read("source"),venue:read("venue"),url:read("url"),bid:read("bid"),ask:read("ask"),quoteAt:read("quoteAt"),paired:reviewed,reviewed,barriers,goldReference:read("goldReference"),goldAt:read("goldAt"),goldUrl:read("goldUrl"),fxUrl:read("fxUrl"),fxReference:read("fxReference"),fxAt:read("fxAt"),referenceConfirmed:r.querySelector(\'[data-combined="referenceConfirmed"]\').checked});rankUI();\n  });\n  r.querySelector("[data-combined-clear]").addEventListener("click",()=>{combinedReferences.delete(i);rankUI();});\n  q.appendChild(r);\n  r.querySelector("#dgDetailShot"+i).addEventListener("change",async e=>{\n   const input=e.target,files=Array.from(input.files||[]),isin=document.querySelector(\'[data-dg="isin"][data-i="\'+i+\'"]\')?.value;\n   input.value="";input.disabled=true;\n   try{for(const file of files){if(document.querySelector(\'[data-dg="isin"][data-i="\'+i+\'"]\')?.value!==isin)break;await readScreenshot(i,file);}}\n   finally{input.disabled=false;}\n  });\n  r.querySelector(\'[data-research]\').addEventListener(\'click\',()=>enrichProduct(i));\n  r.querySelector(\'[data-dg="confirmed"]\').addEventListener(\'change\',()=>{enrichProduct(i);rankUI();});\n  r.querySelectorAll(\'[data-dg]\').forEach(el=>el.addEventListener(\'input\',()=>{if(el.dataset.dg!=="confirmed"){combinedReferences.delete(i);productQuotes.delete(i);futureResearchQuotes.delete(i);detailScreenshots.delete(i);rowVersions.set(i,(rowVersions.get(i)||0)+1);if(el.dataset.dg==="isin")r.querySelector(\'[data-dg="confirmed"]\').checked=false;}rankUI();}));\n }\n populateCandidateRows(loadIdentities());\n let centralTexts=[],centralRecoveries=[];\n async function processCentralShot(file,label,slot){\n  if(!file)return;\n  const status=b.querySelector("#dgCentralStatus"),lab=b.querySelector("#dgShotLabel"+slot);\n  try{\n   if(lab)lab.textContent=label+" wartet …";\n   if(status)status.textContent="⏳ "+label+" wartet auf den OCR-Worker …";\n   const result=await recognizeOcr(file,"dgCentralStatus");\n   centralTexts[slot-1]=result.data.text||"";centralRecoveries[slot-1]=result.data.isinRecoveries||{};\n   const all=centralTexts.filter(Boolean).join("\\n\\n");\n   const items=parseScreenshotCandidates(all);const recovered=Object.assign({},...centralRecoveries);for(const x of items){if(recovered[x.isin]){x.originalIsin=recovered[x.isin];x.ocrRecovery=true;}}\n   populateCandidateRows(items);\n   items.slice(0,12).forEach((x,idx)=>{if(x.isin)enrichProduct(idx+1);});\n   if(lab)lab.textContent="✓ "+label+" geladen";\n   if(status){const count=centralTexts.filter(Boolean).length;status.textContent=count<2?"✅ "+items.length+" Produkt(e) erkannt. Bitte noch Bild "+(count+1)+" hochladen.":"✅ "+count+" Bilder gelesen · "+items.length+" unterschiedliche Produkte erkannt.";const reread=items.filter(x=>x.ocrRecovery).length;if(reread)status.textContent+=" "+reread+" unsichere ISIN(s) durch Zweitlesung erkannt – am Screenshot prüfen.";const corrected=items.filter(x=>x.originalIsin&&!x.ocrRecovery).length;if(corrected)status.textContent+=" "+corrected+" ISIN(s) mit gültiger Prüfziffer aus O/0 bzw. I/1 normalisiert – bitte prüfen.";const uncertain=items.filter(x=>!validIsin(x.isin)).length;if(uncertain)status.textContent+=" ⚠️ "+uncertain+" ISIN(s) bitte unter Details prüfen (OCR unsicher oder Prüfziffer ungültig).";status.textContent+=" Aktuelle Emittentenkurse werden recherchiert. ISINs unter Details am Screenshot bestätigen. Quellen ohne datierte Kurse bleiben gesperrt.";}\n   if(centralTexts.filter(Boolean).length>=2)rankUI();\n  }catch(e){\n   if(lab)lab.textContent=label+" erneut versuchen";\n   if(status)status.textContent="⚠️ "+label+" konnte nicht automatisch gelesen werden: "+(e&&e.message?e.message:"OCR-Fehler");\n   console.warn("[BOB] DEGIRO OCR",e);\n  }\n }\n [1,2,3].forEach(slot=>{\n  b.querySelector("#dgCentralShot"+slot).addEventListener("change",e=>processCentralShot(e.target.files&&e.target.files[0],"Bild "+slot,slot));\n });\n b.querySelector("#dgRankBtn").addEventListener("click",()=>{rankUI();for(let i=1;i<=12;i++)enrichProduct(i);});\n setInterval(()=>{if(!document.hidden){rankUI();for(let i=1;i<=12;i++){if(futureResearchQuotes.has(i)||productQuotes.get(i)?.productModel||document.querySelector(\'[data-dg="confirmed"][data-i="\'+i+\'"]\')?.checked)enrichProduct(i);}}},30000);\n setInterval(()=>{if(!document.hidden)rankUI();},1000);\n}\nfunction rankUI(){\n saveIdentities();\n for(const [i,x] of futureResearchQuotes){\n  const isin=document.querySelector(\'[data-dg="isin"][data-i="\'+i+\'"]\')?.value.trim().toUpperCase();\n  if(isin!==x.isin){futureResearchQuotes.delete(i);continue;}\n  const meta=document.getElementById("dgResearch"+i),info=x.metadata;\n  if(meta)meta.textContent="🌐 "+x.source+" · ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · "+x.reason+futureResearchText(x)+productEstimateText(x)+". Produkt für aktuelle Rangliste gesperrt.";\n }\n for(let i=1;i<=12;i++){const out=document.getElementById(\'dgEvidence\'+i),html=screenshotSummary(detailScreenshots.get(i));if(out&&out.innerHTML!==html)out.innerHTML=html;}\n for(const [i,q] of productQuotes){\n  const computed=document.getElementById("dgCalculatedState"+i);if(computed)computed.textContent=productEstimateText(q);\n  const state=document.getElementById("dgQuoteState"+i),timing=quoteTiming(q);\n  if(state)state.textContent=q.eligible&&q.marketOpen&&timing.fresh?"aktuell · "+timing.ageSeconds+" s alt":"GESPERRT · "+(timing.ageSeconds===null?"Zeitstempel unbekannt":timing.ageSeconds+" s alt")+(q.marketOpen?"":" · Markt geschlossen");\n }\n const s=spot(),d=scenario(),a=atr();\n const bundle=window.liveBundleCache,sourceAge=n(bundle?.spots?.xaus_age_seconds),fetchAt=n(bundle?.fetched_at);\n const spotAge=sourceAge!==null&&fetchAt!==null?sourceAge+(Date.now()/1000-fetchAt):null;\n const spotFresh=spotAge!==null&&spotAge>=-5&&spotAge<=60&&!bundle?.spots?.spot_error;\n const ps=Array.from({length:12},(_,z)=>z+1).map(i=>({\n  name:document.querySelector(\'[data-dg="name"][data-i="\'+i+\'"]\')?.value.trim(),\n  isin:document.querySelector(\'[data-dg="isin"][data-i="\'+i+\'"]\')?.value.trim(),\n  productDirection:document.querySelector(\'[data-dg="dir"][data-i="\'+i+\'"]\')?.value,\n  price:n(document.querySelector(\'[data-dg="price"][data-i="\'+i+\'"]\')?.value),\n  leverage:n(document.querySelector(\'[data-dg="lev"][data-i="\'+i+\'"]\')?.value),\n  ko:n(document.querySelector(\'[data-dg="ko"][data-i="\'+i+\'"]\')?.value),\n  spread:n(document.querySelector(\'[data-dg="spread"][data-i="\'+i+\'"]\')?.value),\n  snapshot:detailScreenshots.get(i),quote:productQuotes.get(i)||futureResearchQuotes.get(i),isinConfirmed:document.querySelector(\'[data-dg="confirmed"][data-i="\'+i+\'"]\')?.checked===true,\n  spot:s\n }));\n for(let i=1;i<=12;i++){const out=document.getElementById("dgCombinedState"+i),ref=combinedReferences.get(i);if(ref&&ref.isin!==ps[i-1].isin)combinedReferences.delete(i);if(out)out.innerHTML=window.BobCombined.render(window.BobCombined.assess(ps[i-1],combinedReferences.get(i),bundle));}\n const missingOut=document.getElementById("dgMissingProducts");\n if(missingOut){\n  const html=productUploadCards(ps,d);\n  if(missingOut.dataset.content!==html){\n   missingOut.innerHTML=html;missingOut.dataset.content=html;\n   missingOut.querySelectorAll(\'[data-detail-upload]\').forEach(btn=>btn.addEventListener("click",()=>document.getElementById("dgDetailShot"+btn.dataset.detailUpload)?.click()));\n   missingOut.querySelectorAll(\'[data-card-research]\').forEach(btn=>btn.addEventListener(\'click\',()=>enrichProduct(Number(btn.dataset.cardResearch))));\n   missingOut.querySelectorAll(\'[data-card-confirm]\').forEach(box=>box.addEventListener(\'change\',()=>{\n    const field=document.querySelector(\'[data-dg="confirmed"][data-i="\'+box.dataset.cardConfirm+\'"]\');if(field)field.checked=box.checked;rankUI();\n   }));\n  }\n }\n const manualOut=document.getElementById("dgManualSnapshots");\n if(manualOut){\n  const ctx={direction:d,spotFresh,spot:s,atr:a,trend:document.getElementById(\'trend\')?.textContent,trend2:document.getElementById(\'trend2\')?.textContent,mtf:document.getElementById(\'mtfSummary\')?.textContent,rsi:n(document.getElementById(\'rsi\')?.textContent),hist:n(document.getElementById(\'hist\')?.textContent),adx:n(document.getElementById(\'adx\')?.textContent),momentum:n(document.getElementById(\'momentum\')?.textContent)};\n  const comparison=rankManualSnapshots(ps,ctx);\n  manualOut.innerHTML=comparison.total?\'<b>📷 Vergleich belegter Momentaufnahmen · \'+comparison.total+\' Produkt(e)</b>\'+comparison.candidates.map((p,i)=>\'<div class="small" style="margin-top:8px"><b>\'+(i+1)+\'. \'+esc(p.isin)+\'</b> · technische Passung \'+p.evaluation.score+\'/100 · KO-Abstand \'+p.evaluation.koDistancePct.toFixed(2)+\'%<br>Brief \'+esc(p.snapshot.ask)+\' EUR · Geld \'+esc(p.snapshot.bid)+\' EUR · Spread \'+esc(p.spread)+\' EUR · Hebel \'+esc(p.leverage)+\' · KO \'+esc(p.ko)+(p.evaluation.warnings.length?\'<br>\'+esc(p.evaluation.warnings.join(\' · \')):\'\')+\'</div>\').join(\'\')+\'<div class="small">Rangfolge nur innerhalb der belegten Momentaufnahmen. Laufende Aktualisierung, Marktstatus und Ausführbarkeit nicht bestätigt – keine Live-Freigabe. Unvollständige Produkte sind nicht im Vergleich.</div>\':\'\';\n }\n const conditionalOut=document.getElementById("dgConditionalOut");\n if(conditionalOut){\n  const hasModels=ps.some(p=>p.quote?.calculatedProduct||p.quote?.futureResearch);\n  const ctx={spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,mtf:document.getElementById("mtfSummary")?.textContent,rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),momentum:n(document.getElementById("momentum")?.textContent)};\n  conditionalOut.innerHTML=hasModels?renderConditional(rankConditional(ps,ctx)):"";\n }\n const r=rankProducts(ps,{requireFreshQuotes:true,spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,mtf:document.getElementById("mtfSummary")?.textContent,rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),momentum:n(document.getElementById("momentum")?.textContent)});\n const o=document.getElementById("dgTop3Out");if(!o)return r;\n if(!r.candidates.length){\n  o.innerHTML=\'<div style="padding:14px;background:#fff;border-radius:15px;border:1px solid #e5e7eb"><b style="font-size:16px">📊 Bob-Aktualanalyse</b><div class="small" style="margin-top:6px">Szenario: <b>\'+esc(d)+\'</b></div><div class="warning" style="margin-top:9px"><b>Kein passender Trade-Kandidat.</b></div><div class="small" style="margin-top:5px">\'+esc(r.gateReason||"Mindestens ein vollständiger Screenshot-Kandidat wird benötigt.")+\'</div></div>\';\n  return r;\n }\n if(!r.tradeable){\n  o.innerHTML=\'<div style="padding:15px;background:#fff;border-radius:16px;border:1px solid #e5e7eb"><b style="font-size:17px">📊 Bob-Aktualanalyse</b><div class="small" style="margin-top:6px">Szenario: <b>\'+esc(r.scenario)+\'</b> · \'+r.total+\' Kandidat(en) geprüft</div><div class="warning" style="margin-top:10px"><b>Kein eindeutiger Trade-Kandidat.</b></div><div class="small" style="margin-top:5px">\'+esc(r.gateReason)+\'</div></div>\';\n  return r;\n }\n const top=r.candidates.slice(0,3);\n const cards=top.map((p,i)=>{\n  const e=p.evaluation, name=p.name||p.isin||"DEGIRO-Produkt";\n  const ko=e.koDistancePct===null?"—":e.koDistancePct.toFixed(2)+"%";\n  const at=e.atrMultiple===null?"—":e.atrMultiple.toFixed(1)+" ATR";\n  const action=e.direction==="LONG"?"LONG":"SHORT";\n  const rank=i+1;\n  const rankLabel=rank===1?"🥇 Platz 1":rank===2?"🥈 Platz 2":"🥉 Platz 3";\n  const reason=e.reasons.filter(x=>!x.includes("widerspricht")).slice(0,2).join(" · ")||"Richtung und Produktdaten wurden passend zum Bob-Szenario geprüft.";\n  return \'<div style="margin-top:10px;padding:13px;background:#fff;border-radius:15px;border:1px solid #e5e7eb">\'+\n   \'<div style="font-weight:800;font-size:16px">\'+rankLabel+\' · \'+esc(name)+\'</div>\'+\n   \'<div style="margin-top:5px"><b>\'+action+\'</b> · Produktkurs \'+(p.price??"—")+\' · Hebel \'+(e.leverage?e.leverage.toFixed(2):"—")+\'×</div>\'+\n   \'<div class="small">\'+esc(p.quote.source)+\' · Kurszeit \'+esc(new Date(p.quote.quoteAt).toLocaleTimeString())+\' · Spread \'+esc(p.spread)+\' EUR · DEGIRO-Ausführungskurs prüfen</div>\'+\n   (p.quote.leverageNote?\'<div class="small">\'+esc(p.quote.leverageNote)+\'</div>\':\'\')+\n   \'<div class="small" style="margin-top:4px">KO-Abstand \'+ko+\' · ATR-Puffer \'+at+\' · Setup-Qualität \'+e.setupScore+\'/100</div>\'+\n   \'<div class="small" style="margin-top:7px"><b>Warum:</b> \'+esc(reason)+\'</div>\'+\n   (e.warnings.length?\'<div class="small warning" style="margin-top:6px">⚠️ \'+esc(e.warnings.slice(0,2).join(" · "))+\'</div>\':\'\')+\n  \'</div>\';\n }).join("");\n o.innerHTML=\'<div style="padding:15px;background:#fff;border-radius:18px;border:2px solid #dbe4f0">\'+\n  \'<div class="small">AKTUELLE BOB-ANALYSE · \'+esc(r.scenario)+\' · \'+r.total+\' Kandidat(en) geprüft</div>\'+\n  \'<div style="font-size:20px;font-weight:800;margin-top:4px">🎯 Vergleich bestätigter Produktkurse</div>\'+\n  \'<div class="small" style="margin-top:4px">Bob sortiert die passenden Produkte nach technischer Passung und Produktrisiko.</div>\'+\n  cards+\n  \'<div class="small" style="margin-top:9px">Die Plätze sind eine technische Rangfolge der geprüften DEGIRO-Kandidaten, keine Gewinnwahrscheinlichkeit und keine Garantie.</div></div>\';\n return r;\n}\n\nif(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{try{inject();}catch(e){console.warn(e);}});else try{inject();}catch(e){console.warn(e);}}\nwindow.BobDegiro={screenshotCurrentState,renderScreenshotCurrentState,conditionalCandidate,rankConditional,renderConditional,qualityText,isFutureProduct,futureResearchText,productEstimateText,rankManualSnapshots,productUploadCards,sourceTimestamp,screenshotTimes,evidenceTiming,manualSnapshotStatus,needsDirectionalData,loadIdentities,saveIdentities,riskModel,koDistancePct,evaluateProduct,quoteTiming,currentQuote,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates,validIsin,normalizeOcrIsin,populateCandidateRows,recoverOcrIsins,detailScreenshotData,missingProductData,supplementaryHint,screenshotTimeLabel,mergeScreenshotEvidence,manualProductMissing,escapeHtml:esc};\n})();\n'
UPSTREAM_TIMEOUT = 4
FRESH_MAX_AGE = 180
LIVE_CACHE_TTL = 65
FX_CACHE_TTL = 900
_live_cache = None
_live_cache_at = 0.0
_fx_cache = {"EUR": None, "CHF": None}
_fx_cache_at = 0.0
_live_lock = threading.Lock()

def fetch_json(url, retries=2, user_agent="Bob/1.1"):
    last_error = None
    for attempt in range(retries + 1):
        req = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=UPSTREAM_TIMEOUT) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Upstream HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = RuntimeError(f"Upstream HTTP {exc.code} ({url})")
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = RuntimeError(f"Upstream nicht erreichbar oder ungültige JSON-Antwort ({url})")
        if attempt < retries:
            time.sleep(0.6 * (attempt + 1))
    raise last_error or RuntimeError(f"Upstream nicht erreichbar ({url})")

def fetch_json_post(url, payload, retries=1, user_agent="Bob/1.1"):
    last_error = None
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    for attempt in range(retries + 1):
        req = Request(
            url,
            data=body,
            method="POST",
            headers={"User-Agent": user_agent, "Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=UPSTREAM_TIMEOUT) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Upstream HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = RuntimeError(f"Upstream HTTP {exc.code} ({url})")
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = RuntimeError(f"Upstream nicht erreichbar oder ungültige JSON-Antwort ({url})")
        if attempt < retries:
            time.sleep(0.4 * (attempt + 1))
    raise last_error or RuntimeError(f"Upstream nicht erreichbar ({url})")

def enrich_degiro_product(isin):
    return product_quotes.get_quote(isin)

def fetch_goldprice_bars(interval, days):
    """Best-effort genuine XAU/USD spot OHLC; empty means unavailable on current API tier."""
    end = datetime.now(timezone.utc)
    start = datetime.fromtimestamp(end.timestamp() - days * 86400, timezone.utc)
    url = (
        "https://api.goldprice.dev/v1/bars?symbol=XAU-USD-SPOT"
        f"&interval={interval}&from={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&to={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=10000"
    )
    try:
        payload = fetch_json(url, retries=1, user_agent="Bob/1.1")
        out = []
        for b in payload.get("bars", []) if isinstance(payload, dict) else []:
            try:
                ts = datetime.fromisoformat(str(b["bar_start"]).replace("Z", "+00:00")).timestamp()
                o, h, low, close = [float(b[k]) for k in ("open", "high", "low", "close")]
                if not all(v > 0 and v == v for v in (o, h, low, close)): continue
                out.append({"openTime": int(ts*1000), "open": o, "high": h, "low": low, "close": close, "isOpen": not bool(b.get("is_closed", False))})
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        out.sort(key=lambda x: x["openTime"])
        return out
    except Exception:
        return []
def iso_age_seconds(value):
    if not value:
        return None
    try:
        stamp = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(stamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, time.time() - dt.timestamp())
    except (TypeError, ValueError):
        return None

def dated_spot_row(row, now=None):
    """Read a price observation time, never a response-generation timestamp."""
    now = time.time() if now is None else now
    price = row.get('price')
    at = row.get('price_as_of')
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise ValueError('Ungültiger Gold-Spotkurs')
    if not isinstance(at, str):
        raise ValueError('Gold-Quellenzeit fehlt')
    dt = datetime.fromisoformat(at.replace('Z', '+00:00'))
    age = now - dt.timestamp()
    if dt.tzinfo is None or not 0 <= age <= FRESH_MAX_AGE or row.get('is_stale') is not False:
        raise ValueError('Gold-Quellenzeit oder Aktualität nicht bestätigt')
    return float(price), age, at

def normalize_biquote_bars(payload):
    bars = payload.get("bars") if isinstance(payload, dict) else None
    if not isinstance(bars, list):
        return []
    out = []
    for b in bars:
        try:
            ot = b.get("openTime")
            o, h, l, c = map(float, (b.get("open"), b.get("high"), b.get("low"), b.get("close")))
            if not ot or not all(v == v for v in (o, h, l, c)):
                continue
            out.append({
                "openTime": ot,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "isOpen": bool(b.get("isOpen", False))
            })
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["openTime"])
    return out

def mark_bar_state(bars, minutes):
    """Mark the currently forming bar as open; never feed it into closed-bar analysis."""
    now_ms = int(time.time() * 1000)
    step = minutes * 60 * 1000
    for b in bars:
        try:
            b["isOpen"] = now_ms < int(b["openTime"]) + step
        except (TypeError, ValueError, KeyError):
            b["isOpen"] = True
    return bars

def aggregate_bars(bars, minutes):
    step = minutes * 60 * 1000
    buckets = {}
    now_ms = int(time.time() * 1000)
    for b in bars:
        try:
            ts = int(b["openTime"])
            bucket = (ts // step) * step
            if bucket not in buckets:
                buckets[bucket] = {"openTime": bucket, "open": float(b["open"]), "high": float(b["high"]), "low": float(b["low"]), "close": float(b["close"]), "isOpen": False, "instrument": b.get("instrument", "unknown")}
            else:
                x = buckets[bucket]
                x["high"] = max(x["high"], float(b["high"]))
                x["low"] = min(x["low"], float(b["low"]))
                x["close"] = float(b["close"])
        except (TypeError, ValueError, KeyError):
            continue
    out = []
    for x in sorted(buckets.values(), key=lambda v: v["openTime"]):
        x["isOpen"] = now_ms < x["openTime"] + step
        out.append(x)
    return out

def build_live_bundle():
    """Build Bob's live bundle without letting slow secondary sources block the spot heartbeat.

    XAU/USD spot, technical history and FX are fetched concurrently. A valid spot
    response is returned even when technical history or FX is temporarily slow.
    """
    global _live_cache, _live_cache_at, _fx_cache, _fx_cache_at
    if _live_cache is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
        return _live_cache

    with _live_lock:
        if _live_cache is not None and time.time() - _live_cache_at < LIVE_CACHE_TTL:
            return _live_cache

        now = time.time()

        def fetch_spot():
            last_error = None
            endpoints = [
                "https://xaus.com/api/v1/spot?compact=1",
                "https://api.goldprice.dev/v1/prices?symbol=XAU-USD-SPOT",
                "https://api.goldprice.dev/v1/spot/XAU-USD-SPOT",
            ]
            for endpoint in endpoints:
                try:
                    payload = fetch_json(endpoint, retries=1, user_agent="Bob/1.3")
                    if endpoint.startswith("https://xaus.com/"):
                        if (not isinstance(payload, dict) or payload.get('xau', {}).get('currency') != 'USD'
                                or payload.get('xau', {}).get('unit') != 'troy_oz'):
                            raise ValueError('Gold-Spotwährung oder Einheit fehlt')
                        row = {
                            "price": payload.get("spot_usd_oz") if isinstance(payload, dict) else None,
                            "price_as_of": payload.get("price_as_of"),
                            "is_stale": payload.get('stale') is not False or payload.get('data_state', {}).get('status') != 'fresh',
                        }
                    elif "/v1/spot/" in endpoint:
                        row = payload if isinstance(payload, dict) else None
                    else:
                        symbols = payload.get("symbols") if isinstance(payload, dict) else None
                        row = symbols[0] if isinstance(symbols, list) and symbols else None
                    if not isinstance(row, dict):
                        raise RuntimeError("XAU/USD-Spotquelle liefert keine gültigen Daten")
                    price, age, price_as_of = dated_spot_row(row)
                    source_name = "XAUS · live" if endpoint.startswith("https://xaus.com/") else "GoldPrice.dev · live"
                    if price <= 0:
                        raise RuntimeError(f"{source_name} liefert keinen gültigen XAU/USD-Preis")
                    if row.get("is_stale") is True or age is None or age > FRESH_MAX_AGE:
                        raise RuntimeError(
                            f"{source_name} Spot nicht frisch (stale={row.get('is_stale')}, "
                            f"Alter {age if age is not None else 'unbekannt'} s)"
                        )
                    return price, age, None, source_name, True, price_as_of
                except Exception as exc:
                    last_error = exc
            return None, None, str(last_error) if last_error else "Spotquelle nicht verfügbar", None, False, None

        def fetch_yahoo(interval, range_value):
            # XAUS exposes a documented XAU chart proxy. Use it first so Render
            # does not depend on direct Yahoo connectivity (which currently returns 404).
            xaus_interval = {"5m":"5m", "1h":"1h"}.get(interval, interval)
            try:
                payload = fetch_json(
                    f"https://xaus.com/api/v1/chart?symbol=xau&range={range_value}&interval={xaus_interval}",
                    retries=1,
                    user_agent="Bob/1.4",
                )
                points = payload.get("points") if isinstance(payload, dict) else None
                if isinstance(points, list) and points:
                    out = []
                    for p in points:
                        try:
                            ts = int(p["t"])
                            o, h, low, close = map(float, (p["o"], p["h"], p["l"], p["c"]))
                            if not all(v == v and v > 0 for v in (o, h, low, close)):
                                continue
                            out.append({
                                "openTime": ts * 1000,
                                "open": o,
                                "high": h,
                                "low": low,
                                "close": close,
                                "isOpen": False,
                                "instrument": "XAU/USD",
                            })
                        except (KeyError, TypeError, ValueError, OverflowError):
                            continue
                    out.sort(key=lambda x: x["openTime"])
                    if out:
                        return out
            except Exception:
                pass

            # Keep direct Yahoo as a secondary fallback.
            payload = fetch_json(
                f"https://query2.finance.yahoo.com/v8/finance/chart/GC%3DF?interval={interval}"
                f"&range={range_value}&includePrePost=true",
                retries=1,
                user_agent="Mozilla/5.0 (Bob/1.5; +https://bob-private-scanner.onrender.com)",
            )
            result = payload.get("chart", {}).get("result", [None])[0] if isinstance(payload, dict) else None
            if not result:
                raise RuntimeError(f"Keine {interval}-Historie verfügbar")
            timestamps = result.get("timestamp") or []
            quote = (result.get("indicators", {}).get("quote") or [None])[0] or {}
            opens = quote.get("open") or []
            highs = quote.get("high") or []
            lows = quote.get("low") or []
            closes = quote.get("close") or []
            out = []
            for i, ts in enumerate(timestamps):
                try:
                    o, h, low, close = map(float, (opens[i], highs[i], lows[i], closes[i]))
                    if not all(v == v and v > 0 for v in (o, h, low, close)):
                        continue
                    out.append({"openTime": int(ts)*1000, "open":o, "high":h, "low":low, "close":close, "isOpen":False, "instrument":"GC=F"})
                except (IndexError, TypeError, ValueError, OverflowError):
                    continue
            out.sort(key=lambda x:x["openTime"])
            return out

        def fetch_fx():
            global _fx_cache, _fx_cache_at
            if time.time() - _fx_cache_at < FX_CACHE_TTL and any(v is not None for v in _fx_cache.values()):
                return _fx_cache["EUR"], _fx_cache["CHF"], []
            rates = {"EUR": None, "CHF": None}
            errors = []
            for ccy in ("EUR", "CHF"):
                try:
                    fx = fetch_json(
                        f"https://api.goldprice.dev/v1/convert?from=USD&to={ccy}&amount=1",
                        retries=1,
                        user_agent="Bob/1.3",
                    )
                    rate = float(fx.get("rate")) if isinstance(fx, dict) else None
                    if rate and rate > 0:
                        rates[ccy] = rate
                        _fx_cache[ccy] = rate
                    else:
                        errors.append(f"Ungültige {ccy}-FX-Rate")
                except Exception as exc:
                    errors.append(str(exc))
            _fx_cache_at = time.time()
            return rates["EUR"] or _fx_cache["EUR"], rates["CHF"] or _fx_cache["CHF"], errors

        # The spot price is the primary heartbeat. Do NOT wait for every secondary
        # source: ThreadPoolExecutor's context manager would otherwise wait for slow
        # Yahoo/FX requests at shutdown and keep /api/live hanging.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bob-live")
        futures = {
            pool.submit(fetch_spot): "spot",
            pool.submit(fetch_yahoo, "5m", "5d"): "5m",
            pool.submit(fetch_yahoo, "1h", "3mo"): "1h",
            pool.submit(fetch_fx): "fx",
        }
        results = {}
        try:
            # The heartbeat gets a generous but bounded window.
            spot_future = next(f for f, name in futures.items() if name == "spot")
            try:
                results["spot"] = spot_future.result(timeout=12)
            except Exception as exc:
                results["spot"] = exc

            # Secondary data is best-effort. Never let it block the live price.
            secondary_deadline = time.monotonic() + 2.0
            for future, name in futures.items():
                if name == "spot":
                    continue
                remaining = max(0.0, secondary_deadline - time.monotonic())
                if remaining <= 0:
                    results[name] = TimeoutError("Sekundärquelle zu langsam")
                    continue
                try:
                    results[name] = future.result(timeout=remaining)
                except FuturesTimeoutError:
                    results[name] = TimeoutError("Sekundärquelle zu langsam")
                except Exception as exc:
                    results[name] = exc
        finally:
            # Cancel unfinished secondary work and return the HTTP response without
            # waiting for those worker threads to finish.
            for future, name in futures.items():
                if name != "spot" and not future.done():
                    future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)

        spot_result = results.get("spot")
        if isinstance(spot_result, tuple):
            goldprice_price, goldprice_age, spot_error, spot_source, is_spot, spot_price_as_of = spot_result
        else:
            goldprice_price = goldprice_age = None
            spot_error = str(spot_result) if spot_result else "Spotquelle nicht verfügbar"
            spot_source = None
            is_spot = False
            spot_price_as_of = None

        bars_5m = results.get("5m", [])
        if isinstance(bars_5m, Exception):
            technical_5m_error = str(bars_5m)
            bars_5m = []
        else:
            technical_5m_error = None
        bars_1h = results.get("1h", [])
        if isinstance(bars_1h, Exception):
            technical_1h_error = str(bars_1h)
            bars_1h = []
        else:
            technical_1h_error = None

        fx_result = results.get("fx")
        if isinstance(fx_result, tuple):
            usd_eur, usd_chf, fx_errors = fx_result
        else:
            usd_eur, usd_chf, fx_errors = _fx_cache["EUR"], _fx_cache["CHF"], [str(fx_result)] if fx_result else []

        if bars_5m:
            mark_bar_state(bars_5m, 5)
        if bars_1h:
            mark_bar_state(bars_1h, 60)

        technical_errors = []
        if technical_5m_error:
            technical_errors.append(technical_5m_error)
        if technical_1h_error:
            technical_errors.append(technical_1h_error)
        if bars_5m:
            age = max(0, now - bars_5m[-1]["openTime"] / 1000)
            if age > 900:
                technical_errors.append(f"5m-Historie nicht frisch ({age:.0f} s)")
        technical_errors.extend(fx_errors)

        if goldprice_price is None:
            # Never promote technical/futures history to the XAU/USD spot field.
            # A GC=F close is a futures reference, not a spot price, and must not
            # masquerade as live XAU/USD data when the genuine spot source fails.
            raise RuntimeError("Kein kostenloser Live-XAU/USD-Spotpreis verfügbar" + (f": {spot_error}" if spot_error else ""))

        bars_15m = aggregate_bars(bars_5m, 15) if bars_5m else []
        bars_4h = aggregate_bars(bars_1h, 240) if bars_1h else []
        reference = bars_5m[-1]["close"] if bars_5m else goldprice_price
        diff = goldprice_price - reference
        pct = (diff / reference * 100) if reference else 0.0
        points_source = bars_5m if bars_5m else bars_1h
        legacy_points = [
            {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(b["openTime"] / 1000)), "p": b["close"]}
            for b in points_source
        ]

        status = "fresh" if goldprice_age is not None and goldprice_age <= FRESH_MAX_AGE else "partial"
        bundle = {
            "fetched_at": int(time.time()),
            "spots": {
                "xaus": goldprice_price,
                "goldprice": goldprice_price,
                "yahoo_gc_f": reference,
                "diff": diff,
                "pct": pct,
                "xaus_age_seconds": goldprice_age,
                "spot_price_as_of": spot_price_as_of,
                "goldprice_age_seconds": goldprice_age,
                "usd_eur": usd_eur,
                "usd_chf": usd_chf,
                "yahoo_gc_f_age_seconds": max(0, now - bars_5m[-1]["openTime"] / 1000) if bars_5m else None,
                "yahoo_1h_age_seconds": max(0, now - bars_1h[-1]["openTime"] / 1000) if bars_1h else None,
                "technical_4h_status": "available" if bars_4h else "unavailable",
                "technical_4h_error": "; ".join(technical_errors) if technical_errors else None,
                "goldprice_status": spot_source,
                "xaus_is_spot": spot_source == "XAUS · live",
                "is_genuine_xauusd_spot": is_spot,
                "spot_source_type": "XAU/USD spot" if is_spot else None,
                "primary": spot_source,
                "reference": "Yahoo Finance GC=F",
                "reference_note": "GC=F ist Gold-Futures, nicht XAU/USD Spot",
                "spot_error": spot_error,
            },
            "history": {
                "bars_by_tf": {"5m": bars_5m, "15m": bars_15m, "1h": bars_1h, "4h": bars_4h},
                "points": legacy_points,
                "data_state": {
                    "status": status,
                    "source": (spot_source or "keine Spotquelle") + " · Historie " + ", ".join(sorted({b.get("instrument", "unknown") for b in bars_5m+bars_1h})),
                    "technical_4h_status": "available" if bars_4h else "unavailable",
                    "technical_errors": technical_errors,
                },
                "age_seconds": goldprice_age,
            },
        }
        _live_cache = bundle
        _live_cache_at = time.time()
        return bundle

def _ema(values, period):
    if not values:
        return None
    k = 2.0 / (period + 1.0)
    e = float(values[0])
    for value in values[1:]:
        e = float(value) * k + e * (1.0 - k)
    return e

def _rsi(values, period=14):
    if len(values) < period + 2:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    gains /= period
    losses /= period
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        gains = (gains * (period - 1) + max(d, 0.0)) / period
        losses = (losses * (period - 1) + max(-d, 0.0)) / period
    return 100.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)

def _mtf_score(bars, tf):
    closed = [b for b in (bars or []) if not b.get("isOpen")][-220:]
    if len(closed) < 200:
        return {"dir":"NEUTRAL","available":False,"reason":"zu wenig Historie","bars":len(closed)}
    latest = int(closed[-1]["openTime"])
    age = max(0, int(time.time() * 1000) - latest)
    freshness = {"5m":1200000,"15m":2700000,"1h":10800000,"4h":43200000}.get(tf,10800000)
    if age > freshness:
        return {"dir":"NEUTRAL","available":False,"reason":"Historie zu alt","bars":len(closed),"ageMs":age}
    values = [float(b["close"]) for b in closed]
    e20, e50, e200 = _ema(values,20), _ema(values,50), _ema(values,200)
    e12, e26 = _ema(values,12), _ema(values,26)
    mac = e12 - e26
    prev_values = values[:-1]
    prev_mac = _ema(prev_values,12) - _ema(prev_values,26)
    rsi = _rsi(values)
    if rsi is None:
        return {"dir":"NEUTRAL","available":False,"reason":"zu wenig Historie für RSI","bars":len(closed),"ageMs":age}
    score = 0
    score += 1 if values[-1] > e20 else -1
    score += 1 if e20 > e50 else -1
    score += 1 if e50 > e200 else -1
    score += 1 if mac > prev_mac else -1
    score += 1 if 50 <= rsi <= 70 else (-1 if rsi < 35 else 0)
    direction = "LONG" if score >= 2 else "SHORT" if score <= -2 else "NEUTRAL"
    return {"dir":direction,"available":True,"reason":"ok","bars":len(closed),"rsi":round(rsi,2),"score":score,"ageMs":age}

def build_mtf_verification(bundle):
    tfbars = bundle.get("history",{}).get("bars_by_tf",{}) if isinstance(bundle,dict) else {}
    results = {tf:_mtf_score(tfbars.get(tf,[]),tf) for tf in ("5m","15m","1h","4h")}
    valid = all(v.get("available") for v in results.values())
    d4,d1,d15,d5 = (results[tf]["dir"] for tf in ("4h","1h","15m","5m"))
    sign = lambda d: 1 if d=="LONG" else -1 if d=="SHORT" else 0
    regime,trend,setup,timing = map(sign,(d4,d1,d15,d5))
    reason = "4h Regime · 1h Trend · 15m Setup · 5m Timing"
    if not valid:
        overall,bias,reason = "NEUTRAL",0.0,"MTF unvollständig"
    elif regime and trend and regime != trend:
        overall,bias,reason = "NEUTRAL",0.0,"4h/1h widersprüchlich"
    elif not (trend or regime):
        overall,bias,reason = "NEUTRAL",0.0,"Kein übergeordneter Trend"
    elif setup == -(trend or regime):
        overall,bias,reason = "NEUTRAL",0.0,"15m Setup gegen Haupttrend"
    elif timing == -(trend or regime):
        overall,bias,reason = "NEUTRAL",0.0,"5m Timing gegen Haupttrend"
    else:
        primary = trend or regime
        overall = "LONG" if primary > 0 else "SHORT"
        bias = regime*0.35 + trend*0.35 + setup*0.20 + timing*0.10
    hierarchy = {"regime":d4,"trend":d1,"setup":d15,"timing":d5,"bias":round(bias,3),"reason":reason}
    return {"overall":overall,"valid":valid,"results":results,"hierarchy":hierarchy,"verifiedAt":datetime.now(timezone.utc).isoformat()}

class Handler(BaseHTTPRequestHandler):
    def authenticated(self):
        return bob_auth.authenticated(self.headers, USER, PASSWORD)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith(ocr_assets.PREFIX):
            ocr_assets.serve(self, path)
            return
        if path == "/login":
            bob_auth.login_page(self)
            return
        if path in ("/", "/index.html", "/bob-live", "/bob-v12") and not self.authenticated():
            bob_auth.send(self, 303, location="/login")
            return
        # Sensitive data APIs must be authenticated before any data generation.
        # Keep static PWA resources and /health public, but never expose live,
        # MTF, or DEGIRO enrichment data without the existing Bob credentials.
        protected_api_path = path in ("/api/live", "/api/mtf", "/api/degiro/enrich", "/api/collection-status")
        if protected_api_path:
            auth = self.headers.get("Authorization", "")
            expected = "Basic " + base64.b64encode(
                f"{USER}:{PASSWORD}".encode("utf-8")
            ).decode("ascii")
            if not self.authenticated():
                self.send_response(401)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b"Authentication required.")
                return

        if path == "/api/collection-status":
            body = json.dumps(auto_collection.status(), ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/degiro/enrich":
            try:
                query = parse_qs(urlparse(self.path).query)
                isin = (query.get("isin") or [""])[0].strip().upper()
                if len(isin) != 12:
                    raise ValueError("ISIN fehlt oder ist ungültig")
                result = enrich_degiro_product(isin)
                body = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                body = json.dumps({"found":False,"source":"Emittentenrecherche","reason":"Zusatzprüfung momentan nicht verfügbar","checkedAt":datetime.now(timezone.utc).isoformat()}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            return
        if path == "/api/mtf":
            try:
                verification = build_mtf_verification(build_live_bundle())
                body = json.dumps(verification, ensure_ascii=False, separators=(",",":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_response(503)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(json.dumps({"error":str(exc)}).encode("utf-8"))
            return
        if path == "/health":
            auto_collection.start()
            body = json.dumps({"status":"ok","service":"bob","fibonacciMonitor":dict(FIB_MONITOR_HEALTH),"automaticCollection":auto_collection.health()},separators=(",",":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        # Public read-only app resources. No credentials or secrets are returned here.
        # This is required for normal PWA/browser fetch behavior after the initial protected page load.
        if path == "/push_manager.js":
            try:
                body = PUSH_MANAGER_JS.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/degiro_assistant.js":
            try:
                body = DEGIRO_ASSISTANT_JS.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_response(404)
                self.end_headers()
            return

        if path == "/sw.js" and SW is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(SW)
            return

        if path == "/icon.svg" and ICON is not None:
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(ICON)
            return

        if path == "/manifest.json" and MANIFEST is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(MANIFEST)
            return

        if path == "/api/live":
            try:
                payload = build_live_bundle()
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                print(f"Bob /api/live ERROR: {type(exc).__name__}: {exc}", flush=True)
                body = json.dumps({"error": "Live-Daten momentan nicht verfügbar", "error_type": type(exc).__name__}).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            return

        path = urlparse(self.path).path

        auth = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{USER}:{PASSWORD}".encode("utf-8")
        ).decode("ascii")

        worker_token = self.headers.get("X-Bob-Worker-Token", "")
        worker_ok = bool(SIGNAL_WORKER_TOKEN) and hmac.compare_digest(worker_token, SIGNAL_WORKER_TOKEN)
        public_push_path = path in ("/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences")
        if not public_push_path and not worker_ok and (not self.authenticated()):
            print(
                f'BOB_AUTH_FAIL path={path} auth_present={bool(auth)} '
                f'auth_scheme={auth.split(" ",1)[0] if auth else "-"} '
                f'user_configured={bool(USER)} password_configured={bool(PASSWORD)} '
                f'worker_token_present={bool(worker_token)} worker_token_configured={bool(SIGNAL_WORKER_TOKEN)}',
                flush=True,
            )
            self.send_response(401)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        # Fresh pathname bypasses stale PWA shells on devices that cached an older root.
        if path == "/bob-v12":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Bob-Version", "bob-v12")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.end_headers()
            self.wfile.write(HTML)
            return

        if path == "/bob-live":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Bob-Version", "live-shell-v8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; img-src 'self' data:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(HTML)
            return

        if path in ("/", "/index.html"):
            print(f'BOB_ROOT_SHELL path={path} shell_sha_hint=bc7499bb9f3e0a1676022a3d3c2225a236615adf auth_present={bool(self.headers.get("Authorization", ""))}', flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline'; "
                "connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; "
                "img-src 'self' data:; "
                "worker-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'"
            )
            self.end_headers()
            self.wfile.write(HTML)
            return

        if path == "/api/push/vapid-public-key":
            try:
                if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
                    raise RuntimeError("Push-Service nicht konfiguriert")
                base = PUSH_SERVICE_URL
                if not base.startswith("http://") and not base.startswith("https://"):
                    base = "http://" + base
                req = Request(base.rstrip("/") + "/vapid-public-key", headers={"Accept":"application/json"})
                with urlopen(req, timeout=8) as response:
                    result = response.read()
                    status = response.status
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(result)
            except HTTPError as exc:
                self.send_response(exc.code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"error":"Push-Service-Fehler"}')
            except (URLError, TimeoutError):
                self.send_response(503)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(b'{"error":"Push-Service nicht erreichbar"}')
            return


    def do_HEAD(self):
        # Render and other HTTP probes use HEAD. Mirror the root/health access
        # policy without generating a response body, so probes do not produce
        # false 501 errors and the private root stays private.
        path = urlparse(self.path).path
        if path == "/health":
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/login":
            bob_auth.send(self, 200)
            return
        if path in ("/", "/index.html") and not self.authenticated():
            bob_auth.send(self, 303, location="/login")
            return
        if path in ("/", "/index.html"):
            auth = self.headers.get("Authorization", "")
            expected = "Basic " + base64.b64encode(
                f"{USER}:{PASSWORD}".encode("utf-8")
            ).decode("ascii")
            if not self.authenticated():
                self.send_response(401)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self' https://xaus.com https://api.goldprice.dev https://ntfy.sh; img-src 'self' data:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login":
            bob_auth.login(self, USER, PASSWORD)
            return
        if path == "/logout":
            bob_auth.logout(self)
            return
        if bob_auth.cookie(self.headers, bob_auth.COOKIE) and not bob_auth.same_origin(self.headers):
            bob_auth.send(self, 403)
            return
        auth = self.headers.get("Authorization", "")
        expected = "Basic " + base64.b64encode(
            f"{USER}:{PASSWORD}".encode("utf-8")
        ).decode("ascii")
        worker_token = self.headers.get("X-Bob-Worker-Token", "")
        worker_ok = bool(SIGNAL_WORKER_TOKEN) and hmac.compare_digest(worker_token, SIGNAL_WORKER_TOKEN)

        if path == "/api/diag":
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0 or length > 8192:
                    raise ValueError("invalid diagnostic payload size")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                event = str(payload.get("event", "unknown"))[:80]
                details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
                safe = {}
                for key in ("bars5m","bars15m","bars1h","bars4h","available","overall","error","reason","historyStatus","source","direct","server"):
                    if key in details:
                        value = details[key]
                        safe[key] = str(value)[:300] if isinstance(value, str) else value
                print(f"BOB_DIAG event={event} seq={payload.get('seq')} details={json.dumps(safe, ensure_ascii=False, separators=(',',':'))}", flush=True)
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except Exception as exc:
                print(f"BOB_DIAG_ERROR {type(exc).__name__}: {exc}", flush=True)
                self.send_response(400)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            return

        if path in ("/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences") and not worker_ok and (not self.authenticated()):
            self.send_response(401)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Authentication required.")
            return

        path = urlparse(self.path).path
        if path not in ("/api/push/send", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences"):
            self.send_response(404)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Not found.")
            return

        if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"error":"Push-Service nicht konfiguriert"}'.encode("utf-8"))
            return

        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Payload-Größe")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            base = PUSH_SERVICE_URL
            if not base.startswith("http://") and not base.startswith("https://"):
                base = "http://" + base
            relay_path = {
                "/api/push/send": "/send",
                "/api/push/subscribe": "/subscribe",
                "/api/push/unsubscribe": "/unsubscribe",
                "/api/push/preferences": "/preferences",
            }[path]
            req = Request(
                base.rstrip("/") + relay_path,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Bob-Push-Token": PUSH_SERVICE_TOKEN,
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=12) as response:
                result = response.read()
                status = response.status
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(result)
        except HTTPError as exc:
            body = exc.read() or b'{"error":"Push-Service-Fehler"}'
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ValueError, json.JSONDecodeError):
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"error":"Ungültige Push-Payload"}'.encode("utf-8"))
        except (URLError, TimeoutError):
            self.send_response(503)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write('{"error":"Push-Service nicht erreichbar"}'.encode("utf-8"))

    def log_message(self, fmt, *args):
        # Explicit runtime access logging. Render HTTP request logs are not
        # available on every workspace tier, so keep a compact server-side
        # trace for diagnosing browser -> Render connectivity.
        try:
            request_id = self.headers.get("Rndr-Id", "-")
            print(f"BOB_HTTP path={self.path} method={self.command} status={args[1] if len(args)>1 else '-'} rndr_id={request_id}", flush=True)
        except Exception:
            pass

def fibonacci_monitor_loop():
    """Monitor registered active trades using existing free services."""
    if not PUSH_SERVICE_URL or not PUSH_SERVICE_TOKEN:
        FIB_MONITOR_HEALTH["status"] = "unconfigured"
        print("BOB_FIB monitor_unconfigured", flush=True)
        return
    base = PUSH_SERVICE_URL.rstrip("/")
    if not base.startswith(("https://", "http://")):
        base = "http://" + base
    while True:
        try:
            request = Request(base+"/monitor-status", headers={"X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
            with urlopen(request, timeout=10) as response:
                active = json.loads(response.read(4096)).get("activeMonitors", 0)
            FIB_MONITOR_HEALTH.update(status="active" if active else "idle", lastCheckedAt=int(time.time()), lastSuccessAt=int(time.time()))
            print("BOB_FIB monitor_connected active="+str(active), flush=True)
            if active:
                bundle = build_live_bundle()
                bars = bundle.get("history", {}).get("bars_by_tf", {})
                payload = {"barsByTf":{tf:bars.get(tf, [])[-12:] for tf in ("5m","15m","1h")}}
                request = Request(base+"/monitor", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type":"application/json","X-Bob-Push-Token":PUSH_SERVICE_TOKEN})
                with urlopen(request, timeout=20) as response:
                    result = json.loads(response.read(4096))
                print("BOB_FIB monitor_checked active="+str(active)+" sent="+str(result.get("sent",0)), flush=True)
        except Exception as exc:
            FIB_MONITOR_HEALTH.update(status="unavailable", lastCheckedAt=int(time.time()))
            print("BOB_FIB monitor_error="+type(exc).__name__, flush=True)
        time.sleep(60)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print(f"BOB_START port={port} host=0.0.0.0 version=runtime-http-trace-v1", flush=True)
    threading.Thread(target=fibonacci_monitor_loop, name="bob-fibonacci", daemon=True).start()
    auto_collection.start()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

# Bob maintenance marker: 4h MTF upgrade in progress
