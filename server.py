import os
import base64
import hmac
import json
import time
import threading
import bob_auth
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

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "Bob.html"
SW_PATH = BASE_DIR / "sw.js"
MANIFEST_PATH = BASE_DIR / "manifest.json"
ICON_PATH = BASE_DIR / "icon.svg"

# Load static shell assets once at startup. The request handler serves these
# bytes directly; keeping the load explicit prevents runtime NameError failures.
HTML = HTML_PATH.read_bytes() if HTML_PATH.exists() else b""
SW = SW_PATH.read_bytes() if SW_PATH.exists() else None
MANIFEST = MANIFEST_PATH.read_bytes() if MANIFEST_PATH.exists() else None
ICON = ICON_PATH.read_bytes() if ICON_PATH.exists() else None
# Runtime-module fallback: Render must serve these two browser modules even if
# the deployed filesystem snapshot omits an untracked/static file. Keeping the
# source embedded here makes the JS delivery independent of that filesystem edge case.
PUSH_MANAGER_JS = "/* Bob Push Manager: browser notification + optional server Web Push registration. */\n(function(){\n  const KEY=\"bobPushV1\", LEGACY=\"goldScannerPush\";\n  const PUSH_API=\"/api/push\";\n  const defaults={registered:false,serverRegistered:false,general:false,trade:false,activeTrade:false};\n  function read(){\n    try{\n      const raw=localStorage.getItem(KEY);\n      if(raw)return {...defaults,...JSON.parse(raw)};\n      const old=localStorage.getItem(LEGACY);\n      if(old)return {...defaults,...JSON.parse(old)};\n    }catch(_){}\n    return {...defaults};\n  }\n  function save(s){const next={...defaults,...s};try{localStorage.setItem(KEY,JSON.stringify(next));}catch(_){}return next;}\n  function b64ToBytes(value){\n    const pad=\"=\".repeat((4-(value.length%4))%4);\n    const raw=atob(value.replace(/-/g,\"+\").replace(/_/g,\"/\")+pad);\n    return Uint8Array.from(raw,c=>c.charCodeAt(0));\n  }\n  async function registerServerPush(reg){\n    try{\n      const keyRes=await fetch(PUSH_API+\"/vapid-public-key\",{cache:\"no-store\"});\n      if(!keyRes.ok)throw new Error(\"VAPID-Key konnte nicht geladen werden.\");\n      const {publicKey}=await keyRes.json();\n      if(!publicKey)throw new Error(\"VAPID-Key fehlt.\");\n      if(!reg.pushManager)return false;\n      // Recreate the browser subscription with the current VAPID public key.\n      // This repairs subscriptions created with a previous VAPID key after a\n      // server-side key rotation or a recreated push database.\n      let sub=await reg.pushManager.getSubscription();\n      if(sub){\n        try{\n          await fetch(PUSH_API+\"/unsubscribe\",{\n            method:\"POST\",\n            headers:{\"Content-Type\":\"application/json\"},\n            body:JSON.stringify({endpoint:sub.endpoint})\n          });\n        }catch(_){}\n        try{await sub.unsubscribe();}catch(_){}\n        sub=null;\n      }\n      sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(publicKey)});\n      const res=await fetch(PUSH_API+\"/subscribe\",{\n        method:\"POST\",\n        headers:{\"Content-Type\":\"application/json\"},\n        body:JSON.stringify({subscription:sub.toJSON()})\n      });\n      if(!res.ok)throw new Error(\"Push-Subscription konnte nicht gespeichert werden.\");\n      return true;\n    }catch(_){return false;}\n  }\n  async function enable(){\n    if(!(\"Notification\" in window))throw new Error(\"Web-Benachrichtigungen werden von diesem Browser nicht unterstützt.\");\n    const p=await Notification.requestPermission();\n    if(p!==\"granted\")throw new Error(\"Benachrichtigungen wurden nicht freigegeben.\");\n    let serverRegistered=false;\n    if(\"serviceWorker\" in navigator){\n      const reg=await navigator.serviceWorker.register(\"/sw.js\",{updateViaCache:\"none\"});\n      try{await reg.update();}catch(_){}\n      serverRegistered=await registerServerPush(reg);\n    }\n    return save({...read(),registered:true,serverRegistered});\n  }\n  function state(){return read();}\n  function allowed(kind){\n    const s=read();\n    return s.registered&&Notification.permission===\"granted\"&&s[kind]===true&&(kind!==\"trade\"||s.activeTrade===true);\n  }\n  async function emit(kind,title,body,data={}){\n    const testTrade=kind===\"trade\"&&data&&data.test===true;\n    if(testTrade){\n      const s=read();\n      if(!(s.registered&&Notification.permission===\"granted\"&&s.trade===true))return false;\n    }else if(!allowed(kind))return false;\n    const tag=\"bob-\"+kind+\"-\"+(data.signalId||\"current\");\n    const payload={title,body,data:{...data,url:data.url||\"/\",kind,signalId:data.signalId||null},tag};\n    let serverSent=false;\n    if(read().serverRegistered){\n      try{\n        const res=await fetch(\"/api/push/send\",{\n          method:\"POST\",\n          headers:{\"Content-Type\":\"application/json\"},\n          body:JSON.stringify(payload)\n        });\n        if(res.ok){\n          const result=await res.json().catch(()=>null);\n          serverSent=Boolean(result&&result.sent>0);\n          if(result&&result.vapidReset){\n            const reg=await navigator.serviceWorker.ready;\n            serverSent=await registerServerPush(reg);\n            if(serverSent){\n              const retry=await fetch(\"/api/push/send\",{\n                method:\"POST\",\n                headers:{\"Content-Type\":\"application/json\"},\n                body:JSON.stringify(payload)\n              });\n              if(retry.ok){\n                const retryResult=await retry.json().catch(()=>null);\n                serverSent=Boolean(retryResult&&retryResult.sent>0);\n              }\n            }\n          }\n        }\n      }catch(_){}\n    }\n    if(serverSent)return true;\n    const options={body,tag,data:{url:data.url||\"/\",kind,signalId:data.signalId||null},renotify:false};\n    try{\n      if(\"serviceWorker\" in navigator){\n        const reg=await navigator.serviceWorker.ready;\n        await reg.showNotification(title,options);\n        return true;\n      }\n      new Notification(title,options);\n      return true;\n    }catch(_){return false;}\n  }\n  function set(kind,value){return save({...read(),[kind]:Boolean(value)});}\n  function setActiveTrade(value){return set(\"activeTrade\",value);}\n  window.BobPush={state,save,enable,allowed,emit,set,setActiveTrade};\n})();"
DEGIRO_ASSISTANT_JS = '/* Bob DEGIRO assistant: deterministic risk math, product-fit checks and Top-3 ranking. No order execution. */\n(function(){\nfunction n(v){if(v===null||v===undefined||String(v).trim()==="")return null;const x=Number(v);return Number.isFinite(x)?x:null;}\nfunction validIsin(value){\n const isin=String(value||"").trim().toUpperCase();\n if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))return false;\n // Repeated O in the common DE000 prefix is an ambiguous OCR reading, even\n // when a coincidental checksum passes. Require a visual correction.\n if(/^DE(?=[0O]{3})(?=[0O]{0,2}O)/.test(isin))return false;\n const digits=isin.split("").map(c=>/[A-Z]/.test(c)?String(c.charCodeAt(0)-55):c).join("");\n let sum=0;\n for(let i=digits.length-1,double=false;i>=0;i--,double=!double){let x=Number(digits[i]);if(double)x*=2;sum+=x>9?x-9:x;}\n return sum%10===0;\n}\nfunction normalizeOcrIsin(value){\n const original=String(value||"").trim().toUpperCase();\n if(validIsin(original))return{isin:original,originalIsin:""};\n // German WKN excludes I/O. Only substitute those confusable glyphs,\n // only for DE000-style identifiers, and accept only a valid checksum.\n // Never infer other digits (such as 9) from an ambiguous OCR character.\n if(!/^DE[0O]{3}[A-Z0-9]{7}$/.test(original))return{isin:original,originalIsin:""};\n const candidate="DE000"+original.slice(5).replace(/O/g,"0").replace(/I/g,"1");\n return validIsin(candidate)?{isin:candidate,originalIsin:original}:{isin:original,originalIsin:""};\n}\nfunction koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}\nfunction directionOf(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null)return null;return ko<spot?"LONG":ko>spot?"SHORT":null;}\nfunction riskModel(p){const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);if(spot===null||stop===null||riskEur===null||riskEur<=0)return{ok:false,reason:"Ungültige Eingabedaten für Risiko."};if(fx===null||fx<=0)return{ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};const dist=Math.abs(spot-stop);if(dist<=0)return{ok:false,reason:"Stop-Distanz ist null."};const maxLossUsd=riskEur/fx,approxNotionalUsd=maxLossUsd/(dist/spot),approxNotionalEur=approxNotionalUsd*fx,marginEur=approxNotionalEur/lev,ko=n(p.ko),koPct=koDistancePct(spot,ko),warnings=[];if(ko!==null&&((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");return{ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};}\nfunction technicalQuality(ctx={}){const d=String(ctx.direction||"NEUTRAL").toUpperCase();if(d==="NEUTRAL")return{score:50,reasons:["Kein eindeutiges Richtungsszenario."]};let score=50,reasons=[];const side=v=>{const x=String(v||"").toUpperCase();return x.includes("LONG")||x.includes("BULL")||x.includes("UP")?"LONG":x.includes("SHORT")||x.includes("BEAR")||x.includes("DOWN")?"SHORT":""};const trend=side(ctx.trend),trend2=side(ctx.trend2),mtf=side(ctx.mtf),rsi=Number(ctx.rsi),hist=Number(ctx.hist),adx=Number(ctx.adx),momentum=Number(ctx.momentum);if(trend===d){score+=12;reasons.push("EMA-Trend bestätigt.");}else if(trend&&trend!==d){score-=12;reasons.push("EMA-Trend widerspricht.");}if(trend2===d){score+=10;reasons.push("Langfristtrend bestätigt.");}else if(trend2&&trend2!==d){score-=10;reasons.push("Langfristtrend widerspricht.");}if(mtf===d){score+=15;reasons.push("MTF bestätigt.");}else if(mtf&&mtf!==d){score-=15;reasons.push("MTF widerspricht.");}if(Number.isFinite(rsi)){const support=(d==="LONG"&&rsi>=55&&rsi<=65)||(d==="SHORT"&&rsi>=35&&rsi<=45);const broad=(d==="LONG"&&rsi>=50&&rsi<70)||(d==="SHORT"&&rsi<=50&&rsi>30);if(support){score+=10;reasons.push("RSI liegt im günstigen Trendbereich.");}else if(broad){score+=5;reasons.push("RSI unterstützt die Richtung.");}else if((d==="LONG"&&rsi>75)||(d==="SHORT"&&rsi<25)){score-=10;reasons.push("RSI zeigt erhöhtes Überdehnungsrisiko.");}}if(Number.isFinite(hist)){const h=hist>0?"LONG":hist<0?"SHORT":"";if(h===d){score+=10;reasons.push("MACD-Histogramm bestätigt.");}else if(h&&h!==d){score-=10;reasons.push("MACD-Histogramm widerspricht.");}}if(Number.isFinite(adx)){if(adx>=30){score+=7;reasons.push("ADX zeigt einen starken Trend.");}else if(adx>=20){score+=3;reasons.push("ADX bestätigt vorhandene Trendstärke.");}else if(adx<15){score-=5;reasons.push("ADX zeigt wenig Trendstärke.");}}if(Number.isFinite(momentum)){const m=momentum>0?"LONG":momentum<0?"SHORT":"";if(m===d){score+=8;reasons.push("Momentum bestätigt.");}else if(m&&m!==d){score-=8;reasons.push("Momentum widerspricht.");}}return{score:Math.max(0,Math.min(100,Math.round(score))),reasons};}\nfunction evaluateProduct(p){const spot=n(p.spot),ko=n(p.ko),lev=Math.max(1,n(p.leverage)||1),spread=Math.max(0,n(p.spread)||0),atr=n(p.atr),requested=String(p.direction||"NEUTRAL").toUpperCase(),productDirection=String(p.productDirection||directionOf(spot,ko)||"").toUpperCase(),reasons=[],warnings=[];if(spot===null||spot<=0)return{ok:false,fit:false,score:0,reasons:["Kein gültiger XAU/USD-Preis."],warnings:[]};if(!productDirection||!["LONG","SHORT"].includes(productDirection))reasons.push("Richtung des Produkts fehlt.");if(requested!=="NEUTRAL"&&productDirection&&requested!==productDirection)reasons.push("Produkt-Richtung passt nicht zum aktuellen Bob-Szenario.");if(ko!==null&&((productDirection==="LONG"&&ko>=spot)||(productDirection==="SHORT"&&ko<=spot)))return{ok:false,fit:false,score:0,reasons:["KO-Level liegt am oder jenseits des aktuellen Goldpreises – Produkt gesperrt."],warnings:[]};if(ko===null)warnings.push("KO-Level fehlt – KO-Abstand kann nicht geprüft werden.");const koPct=koDistancePct(spot,ko),koDistance=ko===null?null:Math.abs(spot-ko),atrMultiple=koDistance!==null&&atr!==null&&atr>0?koDistance/atr:null;if(koPct!==null&&koPct<2)warnings.push("KO-Abstand unter 2%.");if(koPct!==null&&koPct<1)warnings.push("KO-Abstand unter 1% – sehr enger Puffer.");if(atrMultiple!==null&&atrMultiple<1.5)warnings.push("KO-Puffer kleiner als 1,5 ATR.");if(atrMultiple!==null&&atrMultiple<1)warnings.push("KO-Puffer kleiner als 1 ATR – sehr eng.");if(lev>10)warnings.push("Hebel über 10× – sehr hohe Empfindlichkeit.");if(spread>0)reasons.push("Spread wurde berücksichtigt.");let productScore=100;if(requested!=="NEUTRAL"&&productDirection!==requested)productScore-=60;if(!productDirection)productScore-=20;if(ko===null)productScore-=20;if(koPct!==null&&koPct<2)productScore-=20;if(koPct!==null&&koPct<1)productScore-=20;if(atrMultiple!==null&&atrMultiple<1.5)productScore-=15;if(atrMultiple!==null&&atrMultiple<1)productScore-=20;if(lev>10)productScore-=15;if(spread>0)productScore-=Math.min(10,spread);const quality=technicalQuality(p);const score=Math.round(productScore*0.45+quality.score*0.55);const fit=productScore>=60&&!reasons.some(x=>x.includes("passt nicht"));const conflictCount=quality.reasons.filter(x=>x.includes("widerspricht")).length;const confirmationCount=quality.reasons.filter(x=>x.includes("bestätigt")||x.includes("unterstützt")||x.includes("günstigen")||x.includes("Momentum")).length;if(conflictCount>=3){warnings.push("Mehrere technische Signale widersprechen der Richtung.");}if(requested!=="NEUTRAL"&&quality.score<35){warnings.push("Setup-Qualität sehr niedrig – kein starker technischer Konsens.");}const confidence=Math.max(0,Math.min(100,Math.round(quality.score-(conflictCount*5))));return{ok:true,fit,score:Math.max(0,Math.round(score)),direction:productDirection,koDistancePct:koPct,koDistance,atrMultiple,leverage:lev,reasons:reasons.concat(quality.reasons),warnings,productScore,setupScore:quality.score,confidence,conflictCount,confirmationCount};}\nfunction quoteTiming(q,now=Date.now()){\n const times=q?[q.quoteAt,q.bidAt,q.askAt,q.leverageAt,q.snapshotAt].map(v=>typeof v==="string"&&/(?:Z|[+-]\\d{2}:\\d{2})$/.test(v)?Date.parse(v):NaN):[];\n const ages=times.map(t=>now-t),age=ages.length?Math.max(...ages):NaN;\n const fresh=ages.length===5&&ages.every(x=>Number.isFinite(x)&&x>=-5000&&x<=60000)&&now<=Date.parse(q.tradingEndAt);\n return{fresh,ageSeconds:Number.isFinite(age)?Math.max(0,Math.ceil(age/1000)):null};\n}\nfunction currentQuote(p,now=Date.now()){\n const q=p.quote;\n return !!q&&q.found&&q.eligible===true&&q.marketOpen&&quoteTiming(q,now).fresh&&q.currency==="EUR"&&q.isin===String(p.isin||"").toUpperCase()&&validIsin(p.isin)&&q.price===p.price&&q.leverage===p.leverage&&q.ko===p.ko&&q.spread===p.spread&&q.direction===p.productDirection&&p.isinConfirmed===true;\n}\nfunction rankProducts(products,context={}){const scenario=String(context.direction||"NEUTRAL").toUpperCase();if(scenario==="NEUTRAL")return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Momentum ist NEUTRAL – Bob empfiehlt kein DEGIRO-Produkt."};if(context.requireFreshQuotes&&context.spotFresh!==true)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Goldpreis veraltet oder Kurszeit unbekannt – aktuelle Rangliste gesperrt."};const valid=(products||[]).map((p,i)=>Object.assign({_index:i},p)).filter(p=>String(p.name||p.isin||"").trim()&&n(p.spot)>0&&(!context.requireFreshQuotes||currentQuote(p,context.now??Date.now()))).map(p=>Object.assign(p,{evaluation:evaluateProduct(Object.assign({},p,context))})).filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.direction===scenario).sort((a,b)=>b.evaluation.score-a.evaluation.score);if(context.requireFreshQuotes&&!valid.length)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Keine passenden, bestätigten Produkte mit höchstens 60 Sekunden alten Emittentenkursen für eine Live-Rangliste. Screenshot-Momentaufnahmen werden getrennt geprüft. ISIN unter Details prüfen; veraltete oder fehlende Daten sind gesperrt."};const best=valid[0]?.evaluation;const setupGate=!!best&&(best.setupScore>=35&&best.conflictCount<3);const p=valid[0];const complete=!!p&&n(p.price)>0&&n(p.leverage)>=1&&n(p.ko)>0&&n(p.spread)!==null&&n(p.spread)>=0&&(!p.isin||validIsin(p.isin));return{scenario,candidates:valid.slice(0,4),total:valid.length,tradeable:setupGate&&complete,gateReason:!setupGate?"Technischer Konsens zu schwach oder zu widersprüchlich – kein Favorit.":!complete?"Produktdaten unvollständig oder ISIN ungültig – Kurs, Hebel, KO und Spread unter Details prüfen und ergänzen.":""};}\nfunction scenario(){const s=typeof window.confirmedSignalDirection==="function"?window.confirmedSignalDirection():null;if(s&&["LONG","SHORT","NEUTRAL"].includes(String(s).toUpperCase()))return String(s).toUpperCase();const t=String(document.getElementById("signal")?.textContent||"").toUpperCase();return t.includes("LONG")?"LONG":t.includes("SHORT")?"SHORT":"NEUTRAL";}\nfunction spot(){const x=n(window.lastPrice);if(x)return x;const m=String(document.getElementById("price")?.textContent||"").match(/[0-9]+(?:[.,][0-9]+)?/);return m?n(m[0].replace(",",".")):null;}\nfunction atr(){return n(window.A?.at)||n(window.A?.atr)||null;}\nfunction esc(s){return String(s).replace(/[&<>"\']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;","\'":"&#39;"}[c]));}\nlet ocrLoader=null,ocrWorkerPromise=null,ocrQueue=Promise.resolve();\nfunction ocrTimeout(promise,ms,message){\n let timer;\n return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(message)),ms);})]).finally(()=>clearTimeout(timer));\n}\nfunction loadOcr(){\n if(typeof window==="undefined")return Promise.reject(new Error("Browser erforderlich."));\n if(window.Tesseract)return Promise.resolve(window.Tesseract);\n if(ocrLoader)return ocrLoader;\n ocrLoader=new Promise((resolve,reject)=>{\n  const s=document.createElement("script");\n  s.src="/ocr-assets/v5/tesseract.min.js";\n  s.onload=()=>window.Tesseract?resolve(window.Tesseract):reject(new Error("OCR-Bibliothek konnte nicht geladen werden."));\n  s.onerror=()=>{ocrLoader=null;s.remove();reject(new Error("OCR-Bibliothek konnte nicht geladen werden. Bitte erneut versuchen."));};\n  document.head.appendChild(s);\n });\n ocrLoader=ocrTimeout(ocrLoader,30000,"OCR-Bibliothek konnte nicht innerhalb von 30 Sekunden geladen werden").catch(e=>{ocrLoader=null;throw e;});\n return ocrLoader;\n}\nasync function loadOcrWorker(statusId){\n if(ocrWorkerPromise)return ocrWorkerPromise;\n const T=await loadOcr();\n const status=document.getElementById(statusId||"");\n if(status)status.textContent="📦 OCR-Engine wird gestartet …";\n const initializing=T.createWorker("eng",1,{\n  workerPath:"/ocr-assets/v5/worker.min.js",\n  langPath:"/ocr-assets/v5",\n  corePath:"/ocr-assets/v5",\n  workerBlobURL:false,\n  logger:m=>{\n   const s=document.getElementById(statusId||"");\n   if(!s||!m)return;\n   if(m.status==="loading language traineddata")s.textContent="📦 OCR-Sprachdaten werden geladen …";\n   else if(m.status==="recognizing text"&&m.progress)s.textContent="📷 OCR "+Math.round(m.progress*100)+"%";\n  }\n });\n ocrWorkerPromise=ocrTimeout(initializing,60000,"OCR-Engine konnte nicht innerhalb von 60 Sekunden gestartet werden").catch(e=>{ocrWorkerPromise=null;initializing.then(w=>w.terminate()).catch(()=>{});throw e;});\n return ocrWorkerPromise;\n}\nasync function prepareOcrImage(file,statusId,isinPass=false){\n const status=document.getElementById(statusId||"");\n try{\n  const bitmap=await createImageBitmap(file);\n  const maxSide=isinPass?3200:1800,scale=Math.min(isinPass?2:1,maxSide/Math.max(bitmap.width,bitmap.height),Math.sqrt(4500000/(bitmap.width*bitmap.height)));\n  const canvas=document.createElement("canvas");canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));\n  const ctx=canvas.getContext("2d",{alpha:false});if(isinPass)ctx.imageSmoothingEnabled=false;ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();\n  if(status)status.textContent="🖼️ Screenshot für OCR optimiert …";\n  return await new Promise((resolve,reject)=>canvas.toBlob(x=>x?resolve(x):reject(new Error("Bildaufbereitung fehlgeschlagen")),isinPass?"image/png":"image/jpeg",0.86));\n }catch(e){return file;}\n}\nfunction recoverOcrIsins(primary,secondary){\n const candidates=Array.from(new Set((String(secondary||"").toUpperCase().match(/DE[0OCD]{3}[A-Z0-9]{6}[0-9](?![A-Z0-9])/g)||[]).map(x=>"DE000"+x.slice(5)).filter(validIsin))),corrections={};\n const text=String(primary||"").replace(/\\bDE[0O]{3}[A-Z0-9]{7}\\b/g,raw=>{\n  if(validIsin(normalizeOcrIsin(raw).isin))return raw;\n  const matches=candidates.filter(candidate=>{\n   let differences=0;\n   for(let i=0;i<12;i++){if(raw[i]===candidate[i])continue;\n    if(i>=2&&i<5&&raw[i]==="O"&&candidate[i]==="0")continue;\n    if(i>=5&&((raw[i]==="O"&&/[09]/.test(candidate[i]))||(raw[i]==="I"&&/[19]/.test(candidate[i])))){differences++;continue;}\n    return false;\n   }\n   return differences>0&&differences<=2;\n  });\n  if(matches.length!==1)return raw;\n  corrections[matches[0]]=raw;return matches[0];\n });\n return{text,corrections};\n}\nfunction recognizeOcr(file,statusId){\n const job=ocrQueue.then(async()=>{\n  const worker=await loadOcrWorker(statusId);\n  const prepared=await prepareOcrImage(file,statusId);\n  let result;\n  try{\n   result=await ocrTimeout(worker.recognize(prepared),45000,"OCR-Zeitüberschreitung nach 45 Sekunden");\n  }catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});throw e;}\n  if(parseScreenshotCandidates(result.data.text||"").some(x=>!validIsin(x.isin))){\n   let secondaryFailed=false;\n   try{\n    const status=document.getElementById(statusId||"");if(status)status.textContent="🔎 Unsichere ISINs werden mit einem zweiten Lesedurchgang geprüft …";\n    const enlarged=await prepareOcrImage(file,statusId,true);\n    await worker.setParameters({tessedit_pageseg_mode:"11",tessedit_char_whitelist:"0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"});\n    const second=await ocrTimeout(worker.recognize(enlarged),45000,"ISIN-Zweitlesung nach 45 Sekunden beendet");\n    const recovered=recoverOcrIsins(result.data.text,second.data.text);\n    result.data.text=recovered.text;result.data.isinRecoveries=recovered.corrections;\n   }catch(e){secondaryFailed=true;ocrWorkerPromise=null;await worker.terminate().catch(()=>{});console.warn("[BOB] ISIN-Zweitlesung",e&&e.message?e.message:e);}\n   finally{try{if(!secondaryFailed)await worker.setParameters({tessedit_pageseg_mode:"3",tessedit_char_whitelist:""});}catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});}}\n  }\n  return result;\n });\n ocrQueue=job.catch(()=>{});\n return job;\n}\nfunction ocrExtract(text){\n const raw=String(text||"").replace(/\\r/g," ");\n const upper=raw.toUpperCase();\n const ident=normalizeOcrIsin((raw.match(/\\b[A-Z]{2}[A-Z0-9]{10}\\b/)||[])[0]||"");\n const isin=ident.isin;\n const levMatch=raw.match(/\\b(?:HEBEL|LEVERAGE)\\s*[:=]?\\s*(\\d+(?:[.,]\\d+)?)\\s*(?:[X×]\\b)?|\\b(\\d+(?:[.,]\\d+)?)\\s*[X×](?![A-Z0-9])/i);\n const lev=levMatch?(levMatch[1]||levMatch[2]||""):"";\n const ko=(raw.match(/\\b(?:KO|KNOCK[- ]?OUT|BARRIERE|BARRIER|BAR|SL)\\b\\s*[:=]?\\s*([0-9]{3,6}(?:[.,][0-9]+)?)/i)||[])[1]||"";\n const spread=(raw.match(/(?:SPREAD|GELD\\s*\\/\\s*BRIEF|BID\\s*\\/\\s*ASK)\\s*[:=]?\\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";\n const price=(raw.match(/(?:PRODUKTKURS|PRODUKTPREIS|KURS|PREIS|PRICE|QUOTE)\\s*[:=]?\\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";\n const direction=upper.includes("SHORT")||upper.includes("PUT")?"SHORT":(upper.includes("LONG")||upper.includes("CALL")?"LONG":"");\n const lines=raw.split(/\\n+/).map(x=>x.trim()).filter(Boolean);\n const nameLine=lines.find(x=>/GOLD|XAU|TURBO|KNOCK|CALL|PUT/i.test(x)&&x.length<100)||"";\n return {isin,originalIsin:ident.originalIsin,leverage:lev.replace(",","."),ko:ko.replace(",","."),spread:spread.replace(",","."),price:price.replace(",","."),direction,name:nameLine};\n}\nconst productQuotes=new Map(),pendingQuotes=new Set(),detailScreenshots=new Map(),rowVersions=new Map();\nfunction populateCandidateRows(items){\n // Replacing a screenshot must not retain prices, confirmation or surplus products.\n for(let i=1;i<=12;i++){\n  const x=items[i-1],values=x?{name:x.name||x.isin,isin:x.isin,dir:x.direction,price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread}:{};\n  for(const k of ["name","isin","dir","price","lev","ko","spread"]){const el=document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\');if(el)el.value=values[k]??"";}\n  productQuotes.delete(i);detailScreenshots.delete(i);rowVersions.set(i,(rowVersions.get(i)||0)+1);\n  const upload=document.getElementById("dgDetailShot"+i);if(upload)upload.value="";\n  const confirmed=document.querySelector(\'[data-dg="confirmed"][data-i="\'+i+\'"]\');if(confirmed)confirmed.checked=false;\n  const status=document.getElementById("dgOcrStatus"+i),research=document.getElementById("dgResearch"+i);\n  if(research)research.textContent="🌐 Zusatzdaten: warten auf ISIN.";\n  if(status)status.textContent=!x?"Wartet auf Screenshot.":!validIsin(x.isin)?"⚠️ ISIN unsicher: "+(x.isin||"nicht erkannt")+". Bitte direkt am Screenshot korrigieren; Produkt bleibt gesperrt.":x.ocrRecovery?"⚠️ OCR-Zweitlesung: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Am Screenshot prüfen und bestätigen.":x.originalIsin?"⚠️ OCR normalisiert: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Bitte am Screenshot prüfen.":"✅ Aus Screenshot erkannt – ISIN am Screenshot prüfen und bestätigen.";\n }\n}\n\nasync function enrichProduct(i){\n const field=k=>document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\');\n const isin=(field("isin")?.value.trim()||"").toUpperCase(),meta=document.getElementById("dgResearch"+i);\n if(!validIsin(isin)){productQuotes.delete(i);if(meta)meta.textContent="ISIN-Prüfziffer ungültig: bitte am Screenshot korrigieren.";return;}\n if(pendingQuotes.has(i))return;\n pendingQuotes.add(i);\n const version=rowVersions.get(i)||0;\n try{\n  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),18000);\n  let res;try{res=await fetch("/api/degiro/enrich?isin="+encodeURIComponent(isin),{cache:"no-store",signal:ctl.signal});}finally{clearTimeout(timer);}\n  if(!res.ok)throw Error("Produktrecherche nicht verfügbar");\n  const x=await res.json();\n  if((rowVersions.get(i)||0)!==version||(field("isin")?.value.trim()||"").toUpperCase()!==isin)return;\n  productQuotes.delete(i);\n  if(x.found&&x.isin===isin){\n   productQuotes.set(i,x);\n   for(const [key,val] of Object.entries({price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread,dir:x.direction})){if(field(key))field(key).value=val;}\n   if(meta)meta.innerHTML="🌐 "+esc(x.source)+" · Geld "+esc(x.bid)+" / Brief "+esc(x.ask)+" EUR · Spread "+esc(x.spread)+" EUR ("+esc(x.spreadPct)+"%) · Hebel "+esc(x.leverage)+"× · Kurszeit "+esc(new Date(x.quoteAt).toLocaleString())+" · "+\'<span id="dgQuoteState\'+i+\'">\'+(x.eligible?"aktuell":"GESPERRT: "+esc(x.reason))+\'</span>\'+". Emittentenkurs; ausführbarer DEGIRO-Kurs kann abweichen.";\n  }else if(meta)meta.textContent="🌐 "+(x.reason||"Keine verlässlich datierten Emittentenkurse verfügbar")+". Produkt für aktuelle Rangliste gesperrt.";\n }catch(e){productQuotes.delete(i);if(meta)meta.textContent="🌐 Recherche nicht erreichbar: Produkt für aktuelle Rangliste gesperrt.";}\n finally{pendingQuotes.delete(i);rankUI();}\n}\n// Only explicitly labelled source timestamps count. Never use upload/device time.\nfunction sourceTimestamp(value){\n const m=String(value||\'\').trim().match(/^(\\d{2})[/.](\\d{2})[/.](\\d{4})\\s+(\\d{2}):(\\d{2}):(\\d{2})\\s*(Z|UTC|CET|CEST|[+-]\\d{2}:?\\d{2})$/i);\n if(!m)return null;\n const [,dd,mm,yy,hh,mi,ss,zone]=m,parts=[+yy,+mm,+dd,+hh,+mi,+ss];\n const local=Date.UTC(+yy,+mm-1,+dd,+hh,+mi,+ss),date=new Date(local);\n if(date.getUTCFullYear()!==parts[0]||date.getUTCMonth()+1!==parts[1]||date.getUTCDate()!==parts[2]||+hh>23||+mi>59||+ss>59)return null;\n const z=zone.toUpperCase();let offset=0;\n if(z===\'CET\')offset=60;else if(z===\'CEST\')offset=120;\n else if(z!==\'Z\'&&z!==\'UTC\'){const p=z.match(/^([+-])(\\d{2}):?(\\d{2})$/);if(+p[2]>14||+p[3]>59||+p[2]===14&&+p[3]!==0)return null;offset=(+p[2]*60+ +p[3])*(p[1]===\'-\'?-1:1);}\n return new Date(local-offset*60000).toISOString();\n}\nfunction screenshotTimes(raw){\n const out={};\n for(const [key,label] of Object.entries({quote:\'Kurszeit|Kursstand|Quote time\',bid:\'Geldzeit|Bid time\',ask:\'Briefzeit|Ask time\',leverage:\'Hebelzeit|Leverage time\',ko:\'KO-Zeit|KO time\'})){\n  const matches=Array.from(String(raw).matchAll(new RegExp(\'(?:^|\\\\n)\\\\s*(?:\'+label+\')\\\\s*[:=]?\\\\s*([^\\\\n]+)\',\'gi\')));\n  // Multiple conflicting labels are ambiguous. A minute-only time cannot prove 60s.\n  out[key]=matches.length===1?{present:true,text:matches[0][1].trim(),at:sourceTimestamp(matches[0][1])}:{present:matches.length>0,text:\'\',at:null};\n }\n return out;\n}\nfunction evidenceTiming(e,now=Date.now()){\n const at=e?.at,parsed=typeof at===\'string\'&&/(?:Z|[+-]\\d{2}:\\d{2})$/.test(at)?Date.parse(at):NaN;\n const age=now-parsed;\n return{fresh:Number.isFinite(age)&&age>=0&&age<=60000,ageSeconds:Number.isFinite(age)?Math.ceil(age/1000):null};\n}\nfunction fieldSourceTime(x,key){\n const field={Geld:\'bid\',Brief:\'ask\',Hebel:\'leverage\',KO:\'ko\'}[key];\n if(x.times?.[field]?.present)return x.times[field].at;\n return [\'Geld\',\'Brief\',\'Kurs\',\'Spread\'].includes(key)?x.times?.quote?.at||null:null;\n}\nfunction manualSnapshotStatus(p,x,now=Date.now()){\n const reasons=[],e=x?.evidence||{};\n if(!x||x.isin!==String(p.isin||\'\').trim().toUpperCase()||!validIsin(p.isin))reasons.push(\'Bildidentität nicht bestätigt\');\n if(p.isinConfirmed!==true)reasons.push(\'Erkannte Werte und Quellenzeiten am Original bestätigen\');\n if(x?.currency!==\'EUR\'||!(n(x?.bid)>0)||!(n(x?.ask)>=n(x?.bid)))reasons.push(\'Geld und Brief in EUR fehlen\');\n const pairs={Geld:x?.bid,Brief:x?.ask,Spread:p.spread,Hebel:p.leverage,KO:p.ko};\n for(const [key,value] of Object.entries(pairs)){\n  if(n(value)===null||n(e[key]?.value)!==n(value)||!evidenceTiming(e[key],now).fresh)reasons.push(key+\': eigener Zeitnachweis fehlt oder älter als 60 Sekunden\');\n }\n if(n(p.price)!==n(x?.ask)||!(n(p.leverage)>=1)||!(n(p.ko)>0)||n(p.spread)===null||Math.abs(n(p.spread)-(n(x?.ask)-n(x?.bid)))>0.000001)reasons.push(\'Produktwerte unvollständig oder widersprüchlich\');\n if(x?.delayed)reasons.push(\'Bild weist auf verzögerte Kurse hin\');\n return{complete:reasons.length===0,reasons,liveVerified:false};\n}\nconst IDENTITY_KEY=\'bobDegiroIdentitiesV1\';\nfunction saveIdentities(){\n try{const items=[];for(let i=1;i<=12;i++){const read=k=>document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\')?.value||\'\';if(validIsin(read(\'isin\')))items.push({isin:read(\'isin\').toUpperCase(),name:read(\'name\'),direction:read(\'dir\')});}localStorage.setItem(IDENTITY_KEY,JSON.stringify(items));}catch(_){}\n}\nfunction loadIdentities(){\n try{const items=JSON.parse(localStorage.getItem(IDENTITY_KEY)||\'[]\');return Array.isArray(items)?items.filter(x=>x&&validIsin(x.isin)).slice(0,12).map(x=>({isin:x.isin,name:String(x.name||x.isin),direction:[\'LONG\',\'SHORT\'].includes(x.direction)?x.direction:\'\'})):[];}catch(_){return [];}\n}\nfunction needsDirectionalData(p,direction){\n return [\'LONG\',\'SHORT\'].includes(direction)&&p.productDirection===direction&&!currentQuote(p)&&!manualSnapshotStatus(p,p.snapshot).complete;\n}\n\nfunction detailScreenshotData(text,expectedIsin){\n const raw=String(text||""),ids=Array.from(new Set(parseScreenshotCandidates(raw).map(x=>x.isin)));\n if(!validIsin(expectedIsin))return{ok:false,reason:"Bitte zuerst die ISIN dieses Produkts am Screenshot prüfen und korrigieren."};\n if(ids.length!==1||ids[0]!==expectedIsin)return{ok:false,reason:ids.length?"Der Screenshot gehört nicht eindeutig zu "+expectedIsin+". Bitte nur dieses Produkt mit sichtbarer ISIN hochladen.":"ISIN im Zusatzbild fehlt. Bitte die ISIN zusammen mit den Produktdaten zeigen."};\n const x=ocrExtract(raw.replace(/(\\bBAR\\s*\\n)[@©●•®]\\s*(?=[0-9])/gi,"$1"));\n if(!x.price){const top=raw.match(/(?:^|\\n)\\s*€\\s*([0-9]+(?:[.,][0-9]+)?)\\b/);if(top)x.price=top[1].replace(",",".");}\n const amount=label=>{const m=raw.match(new RegExp("\\\\b(?:"+label+")(?!\\\\s*(?:Vol|Volumen))\\\\s*[:=]?\\\\s*(?:€|EUR)?\\\\s*([0-9]+(?:[.,][0-9]+)?)","i"));return m?Number(m[1].replace(",",".")):null;};\n const bid=amount("Geld|Bid"),ask=amount("Brief|Ask");\n if((bid!==null&&bid<=0)||(ask!==null&&ask<=0)||(bid!==null&&ask!==null&&ask<bid))return{ok:false,reason:"Geld-/Briefkurse widersprüchlich gelesen. Bitte ein schärferes Bild hochladen."};\n const stamp=(raw.match(/\\b\\d{2}[/.]\\d{2}[/.]\\d{4}\\s+\\d{2}:\\d{2}(?::\\d{2})?\\b/)||[])[0]||"";\n const currency=/\\bEUR\\b|€/.test(raw)?"EUR":"";\n if(bid!==null&&ask!==null&&currency==="EUR"){x.price=String(ask);x.spread=String(Math.round((ask-bid)*1000000)/1000000);}\n if(!x.leverage){const lv=raw.match(/\\bLV\\s+(\\d+(?:[.,]\\d+)?)/i);if(lv)x.leverage=lv[1].replace(",",".");}\n return{ok:true,...x,bid,ask,currency,sourceTime:stamp,times:screenshotTimes(raw),delayed:/verzögert|delayed/i.test(raw)};\n}\nasync function readScreenshot(i,file){\n const status=document.getElementById("dgOcrStatus"+i),field=k=>document.querySelector(\'[data-dg="\'+k+\'"][data-i="\'+i+\'"]\');\n if(!file)return;\n const expected=(field("isin")?.value||"").trim().toUpperCase(),version=(rowVersions.get(i)||0)+1;rowVersions.set(i,version);\n if(status)status.textContent="📷 Zusatzbild für "+expected+" wird kostenlos im Browser gelesen …";\n try{\n  const result=await recognizeOcr(file,"dgOcrStatus"+i);\n  if((rowVersions.get(i)||0)!==version||(field("isin")?.value||"").trim().toUpperCase()!==expected)return;\n  const x=detailScreenshotData(result.data.text,expected);\n  if(!x.ok){if(status)status.textContent="⚠️ "+x.reason;return;}\n  productQuotes.delete(i);\n  for(const [k,v] of Object.entries({dir:x.direction,price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread})){if(v!==""&&v!==null&&v!==undefined&&field(k))field(k).value=v;}\n  const merged=mergeScreenshotEvidence(detailScreenshots.get(i),x,file.name);\n  if(merged.clearSpread&&field("spread"))field("spread").value="";\n  detailScreenshots.set(i,merged);if(field("confirmed"))field("confirmed").checked=false;\n  if(status)status.textContent="✅ Zusatzbild zugeordnet. Gelesene Werte unter Details am Screenshot prüfen. "+(merged.sourceTime?"Kurszeit im Bild: "+merged.sourceTime:"Kurszeit im Bild fehlt.");\n  const meta=document.getElementById("dgResearch"+i);if(meta)meta.textContent="📷 DEGIRO-Momentaufnahme · "+(merged.bid!==null?"Geld "+merged.bid+" / Brief "+(merged.ask??"fehlt")+" "+merged.currency+" · ":"")+"keine laufenden Live-Daten. Fehlende oder nicht verlässlich datierte Werte bleiben für die aktuelle Rangliste gesperrt.";\n  rankUI();\n }catch(e){if((rowVersions.get(i)||0)!==version)return;if(status)status.textContent="⚠️ Zusatzbild konnte nicht gelesen werden. Bitte erneut versuchen oder die Angaben unter Details ergänzen.";}\n}\nfunction mergeScreenshotEvidence(previous,x,source){\n previous=previous||{};\n const evidence={...(previous.evidence||{})};\n const hasQuote=n(x.price)!==null||x.bid!==null&&x.bid!==undefined||x.ask!==null&&x.ask!==undefined;\n // Keep the original quote\'s timestamp when adding only static product details.\n const merged={...previous,...x,evidence,clearSpread:false};\n if(!hasQuote){for(const key of ["bid","ask","currency","sourceTime","delayed"])merged[key]=previous[key]??x[key];}\n else {for(const key of ["Kurs","Geld","Brief","Spread"])delete evidence[key];merged.clearSpread=n(x.spread)===null;}\n for(const [key,value] of Object.entries({Richtung:x.direction,Kurs:x.price,Hebel:x.leverage,KO:x.ko,Geld:x.bid,Brief:x.ask,Spread:x.spread})){if(value!==""&&value!==null&&value!==undefined)evidence[key]={value,source,at:fieldSourceTime(x,key)};}\n if(hasQuote&&evidence.Spread){const times=[evidence.Geld?.at,evidence.Brief?.at];evidence.Spread.at=times.every(Boolean)?times.sort()[0]:null;}\n for(const [key,field] of Object.entries({Kurs:"price",Hebel:"leverage",KO:"ko",Spread:"spread",Richtung:"direction"})){merged[field]=evidence[key]?.value??"";}\n return merged;\n}\nfunction supplementaryHint(missing){\n const identity=missing.includes("eindeutige ISIN");\n const staticFields=missing.some(v=>["Produktrichtung","Hebel","KO-Schwelle"].includes(v));\n const quotes=missing.some(v=>["Produktkurs","Geld-/Briefkurse für den Spread","bestätigte aktuelle Kursdaten mit Zeitstempeln"].includes(v));\n return (identity?"Bitte ein Bild mit eindeutig sichtbarer ISIN hochladen. ":"")+(staticFields?"Bitte Produktübersicht mit Richtung, Hebel und KO-Schwelle ergänzen. Für Hebel und KO sind eigene datierte Quellen erforderlich; ein neues Kursbild erneuert sie nicht. ":"")+(quotes?"Bitte Kursdatenbild mit ISIN, Geld, Brief und ausdrücklich zugeordneter Kurszeit (Datum, Sekunden, Zeitzone) ergänzen. Uploadzeit zählt nicht. ":"")+"Erkannte Werte bitte am Original prüfen.";\n}\nfunction screenshotTimeLabel(x){\n const e=x?.evidence?.Geld;\n if(e?.at){const t=evidenceTiming(e);return \'Kursquelle: \'+e.at+\' · \'+(t.fresh?\'höchstens 60 Sekunden alt\':t.ageSeconds===null?\'Zeit unklar\':t.ageSeconds+\' s alt / gesperrt\')+\' · Momentaufnahme, keine Live-Verifizierung.\';}\n return x?.sourceTime?\'Kursstand im Bild: \'+x.sourceTime+\' · Aktualität nicht verifiziert. Vollständige, ausdrücklich zugeordnete Kurszeit mit Sekunden und Zeitzone erforderlich.\':\'Kurszeit fehlt – Aktualität nicht prüfbar. Kein Live-Kurs.\';\n}\nfunction screenshotSummary(x){\n if(!x)return "";\n const rows=Object.entries(x.evidence||{}).map(([key,e])=>{const t=evidenceTiming(e);return \'<tr><td>\'+esc(key)+\'</td><td>\'+esc(e.value)+\'</td><td>\'+esc(e.source)+\'</td><td>\'+esc(e.at||\'Zeit / Zeitzone fehlt\')+(key===\'Richtung\'?\'\':\' · \'+esc(t.ageSeconds===null?\'gesperrt\':t.ageSeconds+\' s · \'+(t.fresh?\'≤ 60 s\':\'gesperrt\')))+\'</td></tr>\';}).join("");\n return \'<div class="small"><b>Erkannte Angaben – bitte prüfen</b><table style="width:100%"><thead><tr><th>Angabe</th><th>Wert</th><th>Bildquelle</th><th>Quellenzeit</th></tr></thead><tbody>\'+rows+\'</tbody></table>\'+esc(screenshotTimeLabel(x))+\'</div>\';\n}\nfunction manualProductMissing(p){\n const missing=[];\n if(!validIsin(p.isin))missing.push("gültige ISIN");\n if(!(n(p.price)>0))missing.push("Produktkurs");\n if(!(n(p.leverage)>=1))missing.push("Hebel");\n if(!(n(p.ko)>0))missing.push("KO-Schwelle");\n if(n(p.spread)===null||n(p.spread)<0)missing.push("Spread");\n return missing;\n}\nfunction missingProductData(p){\n const missing=[];\n if(!validIsin(p.isin))missing.push("eindeutige ISIN");\n if(!["LONG","SHORT"].includes(p.productDirection))missing.push("Produktrichtung");\n if(!(n(p.price)>0))missing.push("Produktkurs");\n if(!(n(p.leverage)>=1))missing.push("Hebel");\n if(!(n(p.ko)>0))missing.push("KO-Schwelle");\n if(n(p.spread)===null||n(p.spread)<0)missing.push("Geld-/Briefkurse für den Spread");\n if(!currentQuote(p))missing.push("bestätigte aktuelle Kursdaten mit Zeitstempeln");\n return missing;\n}\nfunction parseScreenshotCandidates(text){\n const raw=String(text||"").replace(/\\r/g,"");\n const matches=Array.from(raw.matchAll(/\\b[A-Z]{2}[A-Z0-9]{10}\\b/g));\n const starts=matches.map((m,i)=>{\n  const lineStart=raw.lastIndexOf("\\n",m.index-1)+1;\n  const lower=i?matches[i-1].index+matches[i-1][0].length:0;\n  const preceding=raw.slice(lower,lineStart);\n  const headings=Array.from(preceding.matchAll(/(?:^|\\n)([^\\n]*(?:GOLD|XAU|TURBO)[^\\n]*(?:LONG|SHORT|CALL|PUT)[^\\n]*)/gi));\n  const heading=headings[headings.length-1];\n  return heading?lower+heading.index+(heading[0].startsWith("\\n")?1:0):(i?lineStart:0);\n });\n const hits=[];\n matches.forEach((m,i)=>{\n  const x=ocrExtract(raw.slice(starts[i],i+1<matches.length?starts[i+1]:raw.length));\n  const ident=normalizeOcrIsin(m[0]);x.isin=ident.isin;x.originalIsin=ident.originalIsin;\n  const existing=hits.find(v=>v.isin===x.isin);\n  if(existing){Object.keys(x).forEach(k=>{if(!existing[k]&&x[k])existing[k]=x[k];});}\n  else if(hits.length<12)hits.push(x);\n });\n return hits;\n}\nfunction inject(){\n if(document.getElementById("dgTop3"))return;\n const a=document.getElementById("dgProductOut"); if(!a)return;\n const b=document.createElement("div");\n b.id="dgTop3";\n b.style.cssText="margin-top:14px;padding:16px;background:#f7f9fc;border-radius:20px;border:1px solid #e5eaf2";\n b.innerHTML=\'<div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b><div class="small">Screenshots hochladen → Bob analysiert → passender Trade-Kandidat</div></div></div>\'+\n \'<div style="margin-top:14px;padding:12px;background:#fff;border-radius:16px;border:1px solid #e1e7f0">\'+\n \'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><b>📷 DEGIRO-Screenshots</b><span class="small">2–3 Bilder</span></div>\'+\n \'<div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px">\'+\n \'<label for="dgCentralShot1" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">\'+\n \'<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>\'+\n \'<span id="dgShotLabel1" style="margin-top:7px;font-weight:700;font-size:12px">Bild 1</span><input id="dgCentralShot1" type="file" accept="image/*" style="display:none"></label>\'+\n \'<label for="dgCentralShot2" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">\'+\n \'<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>\'+\n \'<span id="dgShotLabel2" style="margin-top:7px;font-weight:700;font-size:12px">Bild 2</span><input id="dgCentralShot2" type="file" accept="image/*" style="display:none"></label>\'+\n \'<label for="dgCentralShot3" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">\'+\n \'<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>\'+\n \'<span id="dgShotLabel3" style="margin-top:7px;font-weight:700;font-size:12px">Bild 3 <span style="font-weight:400">(optional)</span></span><input id="dgCentralShot3" type="file" accept="image/*" style="display:none"></label>\'+\n \'</div><div id="dgCentralStatus" class="small" style="margin-top:9px">Noch keine Bilder hochgeladen.</div></div>\'+\n \'<div id="dgMissingProducts" style="margin-top:12px"></div>\'+\n \'<div id="dgManualSnapshots" style="margin-top:12px"></div>\'+\n \'<div id="dgTop3Out" style="margin-top:12px"></div>\'+\n \'<details style="margin-top:10px"><summary style="cursor:pointer;font-weight:700">Details / manuelle Korrektur</summary><div class="small" style="margin:7px 0">Nur öffnen, wenn Bob einen Wert aus dem Screenshot nicht sicher erkennt.</div><div id="dgTop3Inputs"></div></details>\'+\n \'<button style="margin-top:10px;width:100%" id="dgRankBtn">🔎 Analyse erneut ausführen</button>\';\n a.parentNode.insertBefore(b,a.nextSibling);\n const q=b.querySelector("#dgTop3Inputs");\n for(let i=1;i<=12;i++){\n  const r=document.createElement("div");\n  r.style.cssText="margin:8px 0;padding:9px;background:#fff;border-radius:10px";\n  r.innerHTML=\'<b>Kandidat \'+i+\'</b><div id="dgOcrStatus\'+i+\'" class="small" style="margin-top:5px">Wartet auf Screenshot.</div><div id="dgResearch\'+i+\'" class="small research" style="margin-top:5px">🌐 Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="\'+i+\'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="\'+i+\'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="\'+i+\'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="\'+i+\'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="\'+i+\'" type="number" step=".01" placeholder="KO-Level"><input data-dg="spread" data-i="\'+i+\'" type="number" step=".01" min="0" placeholder="Spread"><input data-dg="isin" data-i="\'+i+\'" placeholder="ISIN"></div><label class="small"><input data-dg="confirmed" data-i="\'+i+\'" type="checkbox"> ISIN, erkannte Werte und zugeordnete Quellenzeiten am Original geprüft</label><button data-research="\'+i+\'">Aktuelle Produktdaten laden</button>\';\n  r.insertAdjacentHTML("beforeend",\'<div id="dgEvidence\'+i+\'"></div><div style="margin-top:8px"><label for="dgDetailShot\'+i+\'">📷 Zusatzbild für dieses Produkt hochladen</label><input id="dgDetailShot\'+i+\'" type="file" accept="image/*"><div class="small">Produktdetail oder Kursdaten mit sichtbarer ISIN. Mehrere Bilder können nacheinander ergänzt werden. Kurszeit braucht Datum, Sekunden und Zeitzone; Hebel und KO benötigen eigene Quellenzeiten. Fehlende Zeiten werden nicht ergänzt.</div></div>\');\n  q.appendChild(r);\n  r.querySelector("#dgDetailShot"+i).addEventListener("change",e=>readScreenshot(i,e.target.files?.[0]));\n  r.querySelector(\'[data-research]\').addEventListener(\'click\',()=>enrichProduct(i));\n  r.querySelector(\'[data-dg="confirmed"]\').addEventListener(\'change\',()=>{enrichProduct(i);rankUI();});\n  r.querySelectorAll(\'[data-dg]\').forEach(el=>el.addEventListener(\'input\',()=>{if(el.dataset.dg!=="confirmed"){productQuotes.delete(i);detailScreenshots.delete(i);rowVersions.set(i,(rowVersions.get(i)||0)+1);if(el.dataset.dg==="isin")r.querySelector(\'[data-dg="confirmed"]\').checked=false;}rankUI();}));\n }\n populateCandidateRows(loadIdentities());\n let centralTexts=[],centralRecoveries=[];\n async function processCentralShot(file,label,slot){\n  if(!file)return;\n  const status=b.querySelector("#dgCentralStatus"),lab=b.querySelector("#dgShotLabel"+slot);\n  try{\n   if(lab)lab.textContent=label+" wartet …";\n   if(status)status.textContent="⏳ "+label+" wartet auf den OCR-Worker …";\n   const result=await recognizeOcr(file,"dgCentralStatus");\n   centralTexts[slot-1]=result.data.text||"";centralRecoveries[slot-1]=result.data.isinRecoveries||{};\n   const all=centralTexts.filter(Boolean).join("\\n\\n");\n   const items=parseScreenshotCandidates(all);const recovered=Object.assign({},...centralRecoveries);for(const x of items){if(recovered[x.isin]){x.originalIsin=recovered[x.isin];x.ocrRecovery=true;}}\n   populateCandidateRows(items);\n   items.slice(0,12).forEach((x,idx)=>{if(x.isin)enrichProduct(idx+1);});\n   if(lab)lab.textContent="✓ "+label+" geladen";\n   if(status){const count=centralTexts.filter(Boolean).length;status.textContent=count<2?"✅ "+items.length+" Produkt(e) erkannt. Bitte noch Bild "+(count+1)+" hochladen.":"✅ "+count+" Bilder gelesen · "+items.length+" unterschiedliche Produkte erkannt.";const reread=items.filter(x=>x.ocrRecovery).length;if(reread)status.textContent+=" "+reread+" unsichere ISIN(s) durch Zweitlesung erkannt – am Screenshot prüfen.";const corrected=items.filter(x=>x.originalIsin&&!x.ocrRecovery).length;if(corrected)status.textContent+=" "+corrected+" ISIN(s) mit gültiger Prüfziffer aus O/0 bzw. I/1 normalisiert – bitte prüfen.";const uncertain=items.filter(x=>!validIsin(x.isin)).length;if(uncertain)status.textContent+=" ⚠️ "+uncertain+" ISIN(s) bitte unter Details prüfen (OCR unsicher oder Prüfziffer ungültig).";status.textContent+=" Aktuelle Emittentenkurse werden recherchiert. ISINs unter Details am Screenshot bestätigen. Quellen ohne datierte Kurse bleiben gesperrt.";}\n   if(centralTexts.filter(Boolean).length>=2)rankUI();\n  }catch(e){\n   if(lab)lab.textContent=label+" erneut versuchen";\n   if(status)status.textContent="⚠️ "+label+" konnte nicht automatisch gelesen werden: "+(e&&e.message?e.message:"OCR-Fehler");\n   console.warn("[BOB] DEGIRO OCR",e);\n  }\n }\n [1,2,3].forEach(slot=>{\n  b.querySelector("#dgCentralShot"+slot).addEventListener("change",e=>processCentralShot(e.target.files&&e.target.files[0],"Bild "+slot,slot));\n });\n b.querySelector("#dgRankBtn").addEventListener("click",()=>{rankUI();for(let i=1;i<=12;i++)enrichProduct(i);});\n setInterval(()=>{if(!document.hidden){rankUI();for(let i=1;i<=12;i++){if(document.querySelector(\'[data-dg="confirmed"][data-i="\'+i+\'"]\')?.checked)enrichProduct(i);}}},30000);\n setInterval(()=>{if(!document.hidden)rankUI();},1000);\n}\nfunction rankUI(){\n saveIdentities();\n for(let i=1;i<=12;i++){const out=document.getElementById(\'dgEvidence\'+i),html=screenshotSummary(detailScreenshots.get(i));if(out&&out.innerHTML!==html)out.innerHTML=html;}\n for(const [i,q] of productQuotes){\n  const state=document.getElementById("dgQuoteState"+i),timing=quoteTiming(q);\n  if(state)state.textContent=q.eligible&&q.marketOpen&&timing.fresh?"aktuell · "+timing.ageSeconds+" s alt":"GESPERRT · "+(timing.ageSeconds===null?"Zeitstempel unbekannt":timing.ageSeconds+" s alt")+(q.marketOpen?"":" · Markt geschlossen");\n }\n const s=spot(),d=scenario(),a=atr();\n const bundle=window.liveBundleCache,sourceAge=n(bundle?.spots?.xaus_age_seconds),fetchAt=n(bundle?.fetched_at);\n const spotAge=sourceAge!==null&&fetchAt!==null?sourceAge+(Date.now()/1000-fetchAt):null;\n const spotFresh=spotAge!==null&&spotAge>=-5&&spotAge<=60&&!bundle?.spots?.spot_error;\n const ps=Array.from({length:12},(_,z)=>z+1).map(i=>({\n  name:document.querySelector(\'[data-dg="name"][data-i="\'+i+\'"]\')?.value.trim(),\n  isin:document.querySelector(\'[data-dg="isin"][data-i="\'+i+\'"]\')?.value.trim(),\n  productDirection:document.querySelector(\'[data-dg="dir"][data-i="\'+i+\'"]\')?.value,\n  price:n(document.querySelector(\'[data-dg="price"][data-i="\'+i+\'"]\')?.value),\n  leverage:n(document.querySelector(\'[data-dg="lev"][data-i="\'+i+\'"]\')?.value),\n  ko:n(document.querySelector(\'[data-dg="ko"][data-i="\'+i+\'"]\')?.value),\n  spread:n(document.querySelector(\'[data-dg="spread"][data-i="\'+i+\'"]\')?.value),\n  snapshot:detailScreenshots.get(i),quote:productQuotes.get(i),isinConfirmed:document.querySelector(\'[data-dg="confirmed"][data-i="\'+i+\'"]\')?.checked===true,\n  spot:s\n }));\n const missingOut=document.getElementById("dgMissingProducts");\n if(missingOut){\n  const cards=ps.map((p,z)=>{const i=z+1;let missing=missingProductData(p);if(!currentQuote(p)&&p.snapshot){const state=manualSnapshotStatus(p,p.snapshot);if(state.complete)missing=[];else missing.push(...state.reasons);}return{p,i,missing};}).filter(x=>(x.p.name||x.p.isin)&&x.missing.length&&needsDirectionalData(x.p,d));\n  const html=cards.length?\'<b>📷 Neue Bilder für \'+esc(d)+\'-Produkte benötigt</b>\'+cards.map(({p,i,missing})=>\'<div style="margin-top:8px;padding:10px;background:#fff;border:1px solid #e1e7f0;border-radius:12px"><b>\'+esc(p.isin||p.name)+\'</b><div class="small">Fehlt / prüfen: \'+esc(missing.join(" · "))+\'</div>\'+screenshotSummary(detailScreenshots.get(i))+\'<button data-detail-upload="\'+i+\'">Zusatzbild für dieses Produkt hochladen</button><div class="small">\'+esc(document.getElementById("dgOcrStatus"+i)?.textContent||"")+\'</div><div class="small">\'+esc(supplementaryHint(missing))+\'</div></div>\').join(""):"";\n  if(missingOut.dataset.content!==html){missingOut.innerHTML=html;missingOut.dataset.content=html;missingOut.querySelectorAll(\'[data-detail-upload]\').forEach(btn=>btn.addEventListener("click",()=>document.getElementById("dgDetailShot"+btn.dataset.detailUpload)?.click()));}\n }\n const manualOut=document.getElementById("dgManualSnapshots");\n if(manualOut){\n  const assessed=d==="NEUTRAL"||!spotFresh?[]:ps.filter(p=>p.productDirection===d&&!currentQuote(p)&&manualSnapshotStatus(p,p.snapshot).complete).map(p=>({...p,evaluation:evaluateProduct({...p,spot:s,direction:d,atr:a})})).filter(p=>p.evaluation.ok&&p.evaluation.fit);\n  manualOut.innerHTML=assessed.length?\'<b>📷 Zeitlich vollständige Momentaufnahmen</b>\'+assessed.map(p=>\'<div class="small">\'+esc(p.isin)+\' · Brief \'+esc(p.snapshot.ask)+\' EUR · Geld \'+esc(p.snapshot.bid)+\' EUR · Spread \'+esc(p.spread)+\' EUR · Hebel \'+esc(p.leverage)+\' · KO \'+esc(p.ko)+\'<br>Technische Passung der gespeicherten Werte. Laufende Aktualisierung, Marktstatus und Ausführbarkeit nicht bestätigt – keine Live-Freigabe.</div>\').join(\'\'):\'\';\n }\n const r=rankProducts(ps,{requireFreshQuotes:true,spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,mtf:document.getElementById("mtfSummary")?.textContent,rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),momentum:n(document.getElementById("momentum")?.textContent)});\n const o=document.getElementById("dgTop3Out");if(!o)return r;\n if(!r.candidates.length){\n  o.innerHTML=\'<div style="padding:14px;background:#fff;border-radius:15px;border:1px solid #e5e7eb"><b style="font-size:16px">📊 Bob-Aktualanalyse</b><div class="small" style="margin-top:6px">Szenario: <b>\'+esc(d)+\'</b></div><div class="warning" style="margin-top:9px"><b>Kein passender Trade-Kandidat.</b></div><div class="small" style="margin-top:5px">\'+esc(r.gateReason||"Mindestens ein vollständiger Screenshot-Kandidat wird benötigt.")+\'</div></div>\';\n  return r;\n }\n if(!r.tradeable){\n  o.innerHTML=\'<div style="padding:15px;background:#fff;border-radius:16px;border:1px solid #e5e7eb"><b style="font-size:17px">📊 Bob-Aktualanalyse</b><div class="small" style="margin-top:6px">Szenario: <b>\'+esc(r.scenario)+\'</b> · \'+r.total+\' Kandidat(en) geprüft</div><div class="warning" style="margin-top:10px"><b>Kein eindeutiger Trade-Kandidat.</b></div><div class="small" style="margin-top:5px">\'+esc(r.gateReason)+\'</div></div>\';\n  return r;\n }\n const top=r.candidates.slice(0,3);\n const cards=top.map((p,i)=>{\n  const e=p.evaluation, name=p.name||p.isin||"DEGIRO-Produkt";\n  const ko=e.koDistancePct===null?"—":e.koDistancePct.toFixed(2)+"%";\n  const at=e.atrMultiple===null?"—":e.atrMultiple.toFixed(1)+" ATR";\n  const action=e.direction==="LONG"?"LONG":"SHORT";\n  const rank=i+1;\n  const rankLabel=rank===1?"🥇 Platz 1":rank===2?"🥈 Platz 2":"🥉 Platz 3";\n  const reason=e.reasons.filter(x=>!x.includes("widerspricht")).slice(0,2).join(" · ")||"Richtung und Produktdaten wurden passend zum Bob-Szenario geprüft.";\n  return \'<div style="margin-top:10px;padding:13px;background:#fff;border-radius:15px;border:1px solid #e5e7eb">\'+\n   \'<div style="font-weight:800;font-size:16px">\'+rankLabel+\' · \'+esc(name)+\'</div>\'+\n   \'<div style="margin-top:5px"><b>\'+action+\'</b> · Produktkurs \'+(p.price??"—")+\' · Hebel \'+(e.leverage||"—")+\'×</div>\'+\n   \'<div class="small">Emittent OTC · Kurszeit \'+esc(new Date(p.quote.quoteAt).toLocaleTimeString())+\' · Spread \'+esc(p.spread)+\' EUR · DEGIRO-Ausführungskurs prüfen</div>\'+\n   \'<div class="small" style="margin-top:4px">KO-Abstand \'+ko+\' · ATR-Puffer \'+at+\' · Setup-Qualität \'+e.setupScore+\'/100</div>\'+\n   \'<div class="small" style="margin-top:7px"><b>Warum:</b> \'+esc(reason)+\'</div>\'+\n   (e.warnings.length?\'<div class="small warning" style="margin-top:6px">⚠️ \'+esc(e.warnings.slice(0,2).join(" · "))+\'</div>\':\'\')+\n  \'</div>\';\n }).join("");\n o.innerHTML=\'<div style="padding:15px;background:#fff;border-radius:18px;border:2px solid #dbe4f0">\'+\n  \'<div class="small">AKTUELLE BOB-ANALYSE · \'+esc(r.scenario)+\' · \'+r.total+\' Kandidat(en) geprüft</div>\'+\n  \'<div style="font-size:20px;font-weight:800;margin-top:4px">🎯 Trade-Rangliste</div>\'+\n  \'<div class="small" style="margin-top:4px">Bob sortiert die passenden Produkte nach technischer Passung und Produktrisiko.</div>\'+\n  cards+\n  \'<div class="small" style="margin-top:9px">Die Plätze sind eine technische Rangfolge der geprüften DEGIRO-Kandidaten, keine Gewinnwahrscheinlichkeit und keine Garantie.</div></div>\';\n return r;\n}\n\nif(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{try{inject();}catch(e){console.warn(e);}});else try{inject();}catch(e){console.warn(e);}}\nwindow.BobDegiro={sourceTimestamp,screenshotTimes,evidenceTiming,manualSnapshotStatus,needsDirectionalData,loadIdentities,saveIdentities,riskModel,koDistancePct,evaluateProduct,quoteTiming,currentQuote,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates,validIsin,normalizeOcrIsin,populateCandidateRows,recoverOcrIsins,detailScreenshotData,missingProductData,supplementaryHint,screenshotTimeLabel,mergeScreenshotEvidence,manualProductMissing,escapeHtml:esc};\n})();\n'
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
                buckets[bucket] = {"openTime": bucket, "open": float(b["open"]), "high": float(b["high"]), "low": float(b["low"]), "close": float(b["close"]), "isOpen": False}
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
                        row = {
                            "price": payload.get("spot_usd_oz") if isinstance(payload, dict) else None,
                            "computed_at": payload.get("updated_at") if isinstance(payload, dict) else None,
                            "is_stale": (payload.get("data_state", {}).get("status") == "stale") if isinstance(payload, dict) else True,
                        }
                    elif "/v1/spot/" in endpoint:
                        row = payload if isinstance(payload, dict) else None
                    else:
                        symbols = payload.get("symbols") if isinstance(payload, dict) else None
                        row = symbols[0] if isinstance(symbols, list) and symbols else None
                    if not isinstance(row, dict):
                        raise RuntimeError("XAU/USD-Spotquelle liefert keine gültigen Daten")
                    price = float(row.get("price"))
                    age = iso_age_seconds(row.get("computed_at"))
                    source_name = "XAUS · live" if endpoint.startswith("https://xaus.com/") else "GoldPrice.dev · live"
                    if price <= 0:
                        raise RuntimeError(f"{source_name} liefert keinen gültigen XAU/USD-Preis")
                    if row.get("is_stale") is True or age is None or age > FRESH_MAX_AGE:
                        raise RuntimeError(
                            f"{source_name} Spot nicht frisch (stale={row.get('is_stale')}, "
                            f"Alter {age if age is not None else 'unbekannt'} s)"
                        )
                    return price, age, None, source_name, True
                except Exception as exc:
                    last_error = exc
            return None, None, str(last_error) if last_error else "Spotquelle nicht verfügbar", None, False

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
                    out.append({"openTime": int(ts)*1000, "open":o, "high":h, "low":low, "close":close, "isOpen":False})
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
            goldprice_price, goldprice_age, spot_error, spot_source, is_spot = spot_result
        else:
            goldprice_price = goldprice_age = None
            spot_error = str(spot_result) if spot_result else "Spotquelle nicht verfügbar"
            spot_source = None
            is_spot = False

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
                    "source": (spot_source or "keine Spotquelle") + " + Yahoo Finance GC=F technische Referenz",
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
        protected_api_path = path in ("/api/live", "/api/mtf", "/api/degiro/enrich")
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
            body = b'{"status":"ok","service":"bob"}'
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print(f"BOB_START port={port} host=0.0.0.0 version=runtime-http-trace-v1", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

# Bob maintenance marker: 4h MTF upgrade in progress

