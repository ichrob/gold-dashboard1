/* Bob DEGIRO assistant: deterministic risk math, product-fit checks and Top-3 ranking. No order execution. */
(function(){
function n(v){const x=Number(v);return Number.isFinite(x)?x:null;}
function koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}
function directionOf(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null)return null;return ko<spot?"LONG":ko>spot?"SHORT":null;}
function riskModel(p){const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);if(spot===null||stop===null||riskEur===null||riskEur<=0)return{ok:false,reason:"Ungültige Eingabedaten für Risiko."};if(fx===null||fx<=0)return{ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};const dist=Math.abs(spot-stop);if(dist<=0)return{ok:false,reason:"Stop-Distanz ist null."};const maxLossUsd=riskEur/fx,approxNotionalUsd=maxLossUsd/(dist/spot),approxNotionalEur=approxNotionalUsd*fx,marginEur=approxNotionalEur/lev,ko=n(p.ko),koPct=koDistancePct(spot,ko),warnings=[];if(ko!==null&&((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");return{ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};}
function technicalQuality(ctx={}){const d=String(ctx.direction||"NEUTRAL").toUpperCase();if(d==="NEUTRAL")return{score:50,reasons:["Kein eindeutiges Richtungsszenario."]};let score=50,reasons=[];const side=v=>{const x=String(v||"").toUpperCase();return x.includes("LONG")||x.includes("BULL")||x.includes("UP")?"LONG":x.includes("SHORT")||x.includes("BEAR")||x.includes("DOWN")?"SHORT":""};const trend=side(ctx.trend),trend2=side(ctx.trend2),mtf=side(ctx.mtf),rsi=Number(ctx.rsi),hist=Number(ctx.hist),adx=Number(ctx.adx),momentum=Number(ctx.momentum);if(trend===d){score+=12;reasons.push("EMA-Trend bestätigt.");}else if(trend&&trend!==d){score-=12;reasons.push("EMA-Trend widerspricht.");}if(trend2===d){score+=10;reasons.push("Langfristtrend bestätigt.");}else if(trend2&&trend2!==d){score-=10;reasons.push("Langfristtrend widerspricht.");}if(mtf===d){score+=15;reasons.push("MTF bestätigt.");}else if(mtf&&mtf!==d){score-=15;reasons.push("MTF widerspricht.");}if(Number.isFinite(rsi)){const support=(d==="LONG"&&rsi>=55&&rsi<=65)||(d==="SHORT"&&rsi>=35&&rsi<=45);const broad=(d==="LONG"&&rsi>=50&&rsi<70)||(d==="SHORT"&&rsi<=50&&rsi>30);if(support){score+=10;reasons.push("RSI liegt im günstigen Trendbereich.");}else if(broad){score+=5;reasons.push("RSI unterstützt die Richtung.");}else if((d==="LONG"&&rsi>75)||(d==="SHORT"&&rsi<25)){score-=10;reasons.push("RSI zeigt erhöhtes Überdehnungsrisiko.");}}if(Number.isFinite(hist)){const h=hist>0?"LONG":hist<0?"SHORT":"";if(h===d){score+=10;reasons.push("MACD-Histogramm bestätigt.");}else if(h&&h!==d){score-=10;reasons.push("MACD-Histogramm widerspricht.");}}if(Number.isFinite(adx)){if(adx>=30){score+=7;reasons.push("ADX zeigt einen starken Trend.");}else if(adx>=20){score+=3;reasons.push("ADX bestätigt vorhandene Trendstärke.");}else if(adx<15){score-=5;reasons.push("ADX zeigt wenig Trendstärke.");}}if(Number.isFinite(momentum)){const m=momentum>0?"LONG":momentum<0?"SHORT":"";if(m===d){score+=8;reasons.push("Momentum bestätigt.");}else if(m&&m!==d){score-=8;reasons.push("Momentum widerspricht.");}}return{score:Math.max(0,Math.min(100,Math.round(score))),reasons};}
function evaluateProduct(p){const spot=n(p.spot),ko=n(p.ko),lev=Math.max(1,n(p.leverage)||1),spread=Math.max(0,n(p.spread)||0),atr=n(p.atr),requested=String(p.direction||"NEUTRAL").toUpperCase(),productDirection=String(p.productDirection||directionOf(spot,ko)||"").toUpperCase(),reasons=[],warnings=[];if(spot===null||spot<=0)return{ok:false,fit:false,score:0,reasons:["Kein gültiger XAU/USD-Preis."],warnings:[]};if(!productDirection||!["LONG","SHORT"].includes(productDirection))reasons.push("Richtung des Produkts fehlt.");if(requested!=="NEUTRAL"&&productDirection&&requested!==productDirection)reasons.push("Produkt-Richtung passt nicht zum aktuellen Bob-Szenario.");if(ko===null)warnings.push("KO-Level fehlt – KO-Abstand kann nicht geprüft werden.");const koPct=koDistancePct(spot,ko),koDistance=ko===null?null:Math.abs(spot-ko),atrMultiple=koDistance!==null&&atr!==null&&atr>0?koDistance/atr:null;if(koPct!==null&&koPct<2)warnings.push("KO-Abstand unter 2%.");if(koPct!==null&&koPct<1)warnings.push("KO-Abstand unter 1% – sehr enger Puffer.");if(atrMultiple!==null&&atrMultiple<1.5)warnings.push("KO-Puffer kleiner als 1,5 ATR.");if(atrMultiple!==null&&atrMultiple<1)warnings.push("KO-Puffer kleiner als 1 ATR – sehr eng.");if(lev>10)warnings.push("Hebel über 10× – sehr hohe Empfindlichkeit.");if(spread>0)reasons.push("Spread wurde berücksichtigt.");let productScore=100;if(requested!=="NEUTRAL"&&productDirection!==requested)productScore-=60;if(!productDirection)productScore-=20;if(ko===null)productScore-=20;if(koPct!==null&&koPct<2)productScore-=20;if(koPct!==null&&koPct<1)productScore-=20;if(atrMultiple!==null&&atrMultiple<1.5)productScore-=15;if(atrMultiple!==null&&atrMultiple<1)productScore-=20;if(lev>10)productScore-=15;if(spread>0)productScore-=Math.min(10,spread);const quality=technicalQuality(p);const score=Math.round(productScore*0.45+quality.score*0.55);const fit=productScore>=60&&!reasons.some(x=>x.includes("passt nicht"));const conflictCount=quality.reasons.filter(x=>x.includes("widerspricht")).length;const confirmationCount=quality.reasons.filter(x=>x.includes("bestätigt")||x.includes("unterstützt")||x.includes("günstigen")||x.includes("Momentum")).length;if(conflictCount>=3){warnings.push("Mehrere technische Signale widersprechen der Richtung.");}if(requested!=="NEUTRAL"&&quality.score<35){warnings.push("Setup-Qualität sehr niedrig – kein starker technischer Konsens.");}const confidence=Math.max(0,Math.min(100,Math.round(quality.score-(conflictCount*5))));return{ok:true,fit,score:Math.max(0,Math.round(score)),direction:productDirection,koDistancePct:koPct,koDistance,atrMultiple,leverage:lev,reasons:reasons.concat(quality.reasons),warnings,productScore,setupScore:quality.score,confidence,conflictCount,confirmationCount};}
function rankProducts(products,context={}){const scenario=String(context.direction||"NEUTRAL").toUpperCase();if(scenario==="NEUTRAL")return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Momentum ist NEUTRAL – Bob empfiehlt kein DEGIRO-Produkt."};const valid=(products||[]).map((p,i)=>Object.assign({_index:i},p)).filter(p=>String(p.name||p.isin||"").trim()&&n(p.spot)>0).map(p=>Object.assign(p,{evaluation:evaluateProduct(Object.assign({},p,context))})).filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.direction===scenario).sort((a,b)=>b.evaluation.score-a.evaluation.score);const best=valid[0]?.evaluation;const setupGate=!!best&&(best.setupScore>=35&&best.conflictCount<3);return{scenario,candidates:valid.slice(0,4),total:valid.length,tradeable:setupGate,gateReason:setupGate?"":"Technischer Konsens zu schwach oder zu widersprüchlich – kein Favorit."};}
function scenario(){const s=typeof window.confirmedSignalDirection==="function"?window.confirmedSignalDirection():null;if(s&&["LONG","SHORT","NEUTRAL"].includes(String(s).toUpperCase()))return String(s).toUpperCase();const t=String(document.getElementById("signal")?.textContent||"").toUpperCase();return t.includes("LONG")?"LONG":t.includes("SHORT")?"SHORT":"NEUTRAL";}
function spot(){const x=n(window.lastPrice);if(x)return x;const m=String(document.getElementById("price")?.textContent||"").match(/[0-9]+(?:[.,][0-9]+)?/);return m?n(m[0].replace(",",".")):null;}
function atr(){return n(window.A?.at)||n(window.A?.atr)||null;}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
let ocrLoader=null;
function loadOcr(){
 if(typeof window==="undefined")return Promise.reject(new Error("Browser erforderlich."));
 if(window.Tesseract)return Promise.resolve(window.Tesseract);
 if(ocrLoader)return ocrLoader;
 ocrLoader=new Promise((resolve,reject)=>{
  const s=document.createElement("script");
  s.src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
  s.onload=()=>window.Tesseract?resolve(window.Tesseract):reject(new Error("OCR konnte nicht geladen werden."));
  s.onerror=()=>reject(new Error("Kostenlose OCR-Bibliothek konnte nicht geladen werden."));
  document.head.appendChild(s);
 });
 return ocrLoader;
}
function ocrExtract(text){
 const raw=String(text||"").replace(/\r/g," ");
 const upper=raw.toUpperCase();
 const isin=(raw.match(/\b[A-Z]{2}[A-Z0-9]{10}\b/)||[])[0]||"";
 const lev=(raw.match(/(?:HEBEL|LEVERAGE)?\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*[X×]/i)||[])[1]||"";
 const ko=(raw.match(/(?:KO|KNOCK[- ]?OUT|BARRIERE|BARRIER)\s*[:=]?\s*([0-9]{3,6}(?:[.,][0-9]+)?)/i)||[])[1]||"";
 const spread=(raw.match(/(?:SPREAD|GELD\s*\/\s*BRIEF|BID\s*\/\s*ASK)\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";
 const price=(raw.match(/(?:PRODUKTKURS|PRODUKTPREIS|KURS|PREIS|PRICE|QUOTE)\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";
 const direction=upper.includes("SHORT")||upper.includes("PUT")?"SHORT":(upper.includes("LONG")||upper.includes("CALL")?"LONG":"");
 const lines=raw.split(/\n+/).map(x=>x.trim()).filter(Boolean);
 const nameLine=lines.find(x=>/GOLD|XAU|TURBO|KNOCK|CALL|PUT/i.test(x)&&x.length<100)||"";
 return {isin,leverage:lev.replace(",","."),ko:ko.replace(",","."),spread:spread.replace(",","."),price:price.replace(",","."),direction,name:nameLine};
}
async function enrichProduct(i){
 const isin=document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value.trim()||"";
 const name=document.querySelector('[data-dg="name"][data-i="'+i+'"]')?.value.trim()||"";
 const status=document.getElementById("dgOcrStatus"+i);
 if(!isin)return;
 try{
  if(status)status.textContent="🌐 Öffentliche Zusatzdaten werden geprüft …";
  const res=await fetch("/api/degiro/enrich?isin="+encodeURIComponent(isin)+"&name="+encodeURIComponent(name),{cache:"no-store"});
  if(!res.ok)throw new Error("Zusatzdaten nicht verfügbar");
  const x=await res.json();
  const meta=document.getElementById("dgResearch"+i);
  if(meta){
   if(x.found){
    meta.innerHTML="🌐 <b>Hintergrundprüfung:</b> "+esc(x.name||"Instrument erkannt")+" · "+esc(x.securityType2||x.securityType||"Instrument")+" · "+esc(x.exchCode||"Börse unbekannt")+" · "+esc(x.currency||"Währung unbekannt")+" · Quelle: "+esc(x.source)+" · "+new Date(x.checkedAt).toLocaleTimeString();
   }else{
    meta.textContent="🌐 Keine eindeutigen öffentlichen Zusatzdaten zur ISIN gefunden. Screenshot bleibt maßgeblich.";
   }
  }
  if(status)status.textContent="✅ Screenshot bleibt Primärquelle · öffentliche Zusatzdaten ergänzt.";
 }catch(e){
  const meta=document.getElementById("dgResearch"+i);
  if(meta)meta.textContent="🌐 Hintergrundprüfung momentan nicht verfügbar · Screenshot bleibt Primärquelle.";
  if(status)status.textContent="✅ Screenshot gelesen · Zusatzprüfung nicht verfügbar.";
 }
}
async function readScreenshot(i,file){
 const status=document.getElementById("dgOcrStatus"+i);
 if(!file)return;
 if(status)status.textContent="📷 Screenshot wird kostenlos direkt im Browser gelesen …";
 try{
  const T=await loadOcr();
  const result=await T.recognize(file,"deu+eng",{logger:m=>{if(status&&m&&m.status==="recognizing text"&&m.progress)status.textContent="📷 OCR "+Math.round(m.progress*100)+"%";}});
  const x=ocrExtract(result.data.text);
  const set=(kind,value)=>{const el=document.querySelector('[data-dg="'+kind+'"][data-i="'+i+'"]');if(el&&value)el.value=value;};
  set("name",x.name);set("isin",x.isin);set("dir",x.direction);set("price",x.price);set("lev",x.leverage);set("ko",x.ko);set("spread",x.spread); if(x.isin)enrichProduct(i);
  if(status)status.textContent=x.isin?"✅ Screenshot gelesen – Angaben bitte kurz gegen DEGIRO prüfen.":"⚠️ Screenshot gelesen, aber keine sichere ISIN erkannt – Angaben bitte prüfen.";
 }catch(e){if(status)status.textContent="⚠️ OCR nicht verfügbar. Kandidaten können weiterhin manuell eingegeben werden.";}
}
function parseScreenshotCandidates(text){const raw=String(text||"").replace(/\r/g,"");const hits=[];const re=/\b[A-Z]{2}[A-Z0-9]{10}\b/g;let m;while((m=re.exec(raw))&&hits.length<4){const start=Math.max(0,raw.lastIndexOf("\n",m.index-1)+1),end=Math.min(raw.length,(raw.indexOf("\n",m.index)===-1?raw.length:raw.indexOf("\n",m.index)));const line=raw.slice(start,end).trim();const context=raw.slice(Math.max(0,m.index-120),Math.min(raw.length,m.index+180));const x=ocrExtract(line||context);if(!x.direction)x.direction=ocrExtract(context).direction;x.isin=m[0];if(!hits.some(v=>v.isin===x.isin))hits.push(x);}return hits;}
async function readCentralScreenshot(file){
 const status=document.getElementById("dgCentralStatus");if(!file)return;
 try{
  if(status)status.textContent="📷 Screenshot wird kostenlos direkt im Browser gelesen …";
  const T=await loadOcr();const result=await T.recognize(file,"eng");
  const items=parseScreenshotCandidates(result.data.text);
  items.forEach((x,idx)=>{const i=idx+1;const set=(k,v)=>{const el=document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]');if(el&&v)el.value=v;};set("name",x.name||x.isin);set("isin",x.isin);set("dir",x.direction);set("lev",x.leverage);set("ko",x.ko);set("spread",x.spread);const s=document.getElementById("dgOcrStatus"+i);if(s)s.textContent="✅ Zentraler Screenshot erkannt – Angaben kurz gegen DEGIRO prüfen.";if(x.isin)enrichProduct(i);});
  if(status)status.textContent=items.length?"✅ "+items.length+" Produkt(e) erkannt.":"⚠️ Keine sichere ISIN erkannt – bitte Einzelkarten verwenden.";
  if(items.length)rankUI();
 }catch(e){if(status)status.textContent="⚠️ Zentrale OCR nicht verfügbar. Einzelkarten bleiben nutzbar.";}
}
function inject(){
 if(document.getElementById("dgTop3"))return;
 const a=document.getElementById("dgProductOut"); if(!a)return;
 const b=document.createElement("div");
 b.id="dgTop3";
 b.style.cssText="margin-top:14px;padding:16px;background:#f7f9fc;border-radius:20px;border:1px solid #e5eaf2";
 b.innerHTML='<div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b><div class="small">Screenshots hochladen → Bob analysiert → passender Trade-Kandidat</div></div></div>'+
 '<div style="margin-top:14px;padding:12px;background:#fff;border-radius:16px;border:1px solid #e1e7f0">'+
 '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><b>📷 DEGIRO-Screenshots</b><span class="small">2–3 Bilder</span></div>'+
 '<div class="grid" style="grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px">'+
 '<label for="dgCentralShot1" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">'+
 '<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>'+
 '<span id="dgShotLabel1" style="margin-top:7px;font-weight:700;font-size:12px">Bild 1</span><input id="dgCentralShot1" type="file" accept="image/*" style="display:none"></label>'+
 '<label for="dgCentralShot2" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">'+
 '<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>'+
 '<span id="dgShotLabel2" style="margin-top:7px;font-weight:700;font-size:12px">Bild 2</span><input id="dgCentralShot2" type="file" accept="image/*" style="display:none"></label>'+
 '<label for="dgCentralShot3" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:112px;padding:8px;background:#f8fbff;border:1px solid #dce7f5;border-radius:14px;cursor:pointer;text-align:center">'+
 '<span style="display:flex;align-items:center;justify-content:center;width:48px;height:48px;border-radius:15px;background:#1677ff;color:#fff;font-size:31px;font-weight:700;line-height:1;box-shadow:0 3px 8px rgba(22,119,255,.22)">↑</span>'+
 '<span id="dgShotLabel3" style="margin-top:7px;font-weight:700;font-size:12px">Bild 3 <span style="font-weight:400">(optional)</span></span><input id="dgCentralShot3" type="file" accept="image/*" style="display:none"></label>'+
 '</div><div id="dgCentralStatus" class="small" style="margin-top:9px">Noch keine Bilder hochgeladen.</div></div>'+
 '<div id="dgTop3Out" style="margin-top:12px"></div>'+
 '<details style="margin-top:10px"><summary style="cursor:pointer;font-weight:700">Details / manuelle Korrektur</summary><div class="small" style="margin:7px 0">Nur öffnen, wenn Bob einen Wert aus dem Screenshot nicht sicher erkennt.</div><div id="dgTop3Inputs"></div></details>'+
 '<button style="margin-top:10px;width:100%" id="dgRankBtn">🔎 Analyse erneut ausführen</button>';
 a.parentNode.insertBefore(b,a.nextSibling);
 const q=b.querySelector("#dgTop3Inputs");
 for(let i=1;i<=8;i++){
  const r=document.createElement("div");
  r.style.cssText="margin:8px 0;padding:9px;background:#fff;border-radius:10px";
  r.innerHTML='<b>Kandidat '+i+'</b><div id="dgOcrStatus'+i+'" class="small" style="margin-top:5px">Wartet auf Screenshot.</div><div id="dgResearch'+i+'" class="small research" style="margin-top:5px">🌐 Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="'+i+'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="'+i+'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="'+i+'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="'+i+'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="'+i+'" type="number" step=".01" placeholder="KO-Level"><input data-dg="spread" data-i="'+i+'" type="number" step=".01" min="0" placeholder="Spread"><input data-dg="isin" data-i="'+i+'" placeholder="ISIN"></div>';
  q.appendChild(r);
 }
 let centralTexts=[];
 async function processCentralShot(file,label,slot){
  if(!file)return;
  const status=b.querySelector("#dgCentralStatus"),lab=b.querySelector("#dgShotLabel"+slot);
  try{
   if(lab)lab.textContent=label+" wird gelesen …";
   if(status)status.textContent="📷 "+label+" wird gelesen …";
   const T=await loadOcr();
   const result=await T.recognize(file,"deu+eng");
   centralTexts[slot-1]=result.data.text||"";
   const all=centralTexts.filter(Boolean).join("\n\n");
   const items=parseScreenshotCandidates(all);
   items.slice(0,8).forEach((x,idx)=>{
    const i=idx+1;
    const set=(k,v)=>{const el=document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]');if(el&&v)el.value=v;};
    set("name",x.name||x.isin);set("isin",x.isin);set("dir",x.direction);set("price",x.price);set("lev",x.leverage);set("ko",x.ko);set("spread",x.spread);
    const s=document.getElementById("dgOcrStatus"+i);if(s)s.textContent="✅ Aus Screenshot erkannt – Angaben kurz gegen DEGIRO prüfen.";
    if(x.isin)enrichProduct(i);
   });
   if(lab)lab.textContent="✓ "+label+" geladen";
   if(status){ const count=centralTexts.filter(Boolean).length; status.textContent=count<2 ? "⏳ "+count+" Bild geladen. Bitte noch Bild "+(count+1)+" hochladen …" : "⏳ "+items.length+" Produkt(e) erkannt. Analyse wird ausgeführt …"; }
   if(centralTexts.filter(Boolean).length>=2){ rankUI(); }
  }
  catch(e){
   if(lab)lab.textContent=label+" erneut versuchen";
   if(status)status.textContent="⚠️ "+label+" konnte nicht automatisch gelesen werden. Bitte erneut auswählen.";
   console.warn("[BOB] DEGIRO OCR",e);
  }
 }
 [1,2,3].forEach(slot=>{
  b.querySelector("#dgCentralShot"+slot).addEventListener("change",e=>processCentralShot(e.target.files&&e.target.files[0],"Bild "+slot,slot));
 });
 b.querySelector("#dgRankBtn").addEventListener("click",rankUI);
}
function rankUI(){
 const s=spot(),d=scenario(),a=atr();
 const ps=Array.from({length:8},(_,z)=>z+1).map(i=>({
  name:document.querySelector('[data-dg="name"][data-i="'+i+'"]')?.value.trim(),
  isin:document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value.trim(),
  productDirection:document.querySelector('[data-dg="dir"][data-i="'+i+'"]')?.value,
  price:n(document.querySelector('[data-dg="price"][data-i="'+i+'"]')?.value),
  leverage:n(document.querySelector('[data-dg="lev"][data-i="'+i+'"]')?.value),
  ko:n(document.querySelector('[data-dg="ko"][data-i="'+i+'"]')?.value),
  spread:n(document.querySelector('[data-dg="spread"][data-i="'+i+'"]')?.value)||0,
  spot:s
 }));
 const r=rankProducts(ps,{direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,mtf:document.getElementById("mtfSummary")?.textContent,rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),momentum:n(document.getElementById("momentum")?.textContent)});
 const o=document.getElementById("dgTop3Out");if(!o)return r;
 if(!r.candidates.length){
  o.innerHTML='<div style="padding:14px;background:#fff;border-radius:15px;border:1px solid #e5e7eb"><b style="font-size:16px">📊 Bob-Aktualanalyse</b><div class="small" style="margin-top:6px">Szenario: <b>'+esc(d)+'</b></div><div class="warning" style="margin-top:9px"><b>Kein passender Trade-Kandidat.</b></div><div class="small" style="margin-top:5px">'+esc(r.gateReason||"Mindestens ein vollständiger Screenshot-Kandidat wird benötigt.")+'</div></div>';
  return r;
 }
 if(!r.tradeable){
  o.innerHTML='<div style="padding:15px;background:#fff;border-radius:16px;border:1px solid #e5e7eb"><b style="font-size:17px">📊 Bob-Aktualanalyse</b><div class="small" style="margin-top:6px">Szenario: <b>'+esc(r.scenario)+'</b> · '+r.total+' Kandidat(en) geprüft</div><div class="warning" style="margin-top:10px"><b>Kein eindeutiger Trade-Kandidat.</b></div><div class="small" style="margin-top:5px">'+esc(r.gateReason)+'</div></div>';
  return r;
 }
 const top=r.candidates.slice(0,3);
 const cards=top.map((p,i)=>{
  const e=p.evaluation, name=p.name||p.isin||"DEGIRO-Produkt";
  const ko=e.koDistancePct===null?"—":e.koDistancePct.toFixed(2)+"%";
  const at=e.atrMultiple===null?"—":e.atrMultiple.toFixed(1)+" ATR";
  const action=e.direction==="LONG"?"LONG":"SHORT";
  const rank=i+1;
  const rankLabel=rank===1?"🥇 Platz 1":rank===2?"🥈 Platz 2":"🥉 Platz 3";
  const reason=e.reasons.filter(x=>!x.includes("widerspricht")).slice(0,2).join(" · ")||"Richtung und Produktdaten wurden passend zum Bob-Szenario geprüft.";
  return '<div style="margin-top:10px;padding:13px;background:#fff;border-radius:15px;border:1px solid #e5e7eb">'+
   '<div style="font-weight:800;font-size:16px">'+rankLabel+' · '+esc(name)+'</div>'+
   '<div style="margin-top:5px"><b>'+action+'</b> · Produktkurs '+(p.price??"—")+' · Hebel '+(e.leverage||"—")+'×</div>'+
   '<div class="small" style="margin-top:4px">KO-Abstand '+ko+' · ATR-Puffer '+at+' · Setup-Qualität '+e.setupScore+'/100</div>'+
   '<div class="small" style="margin-top:7px"><b>Warum:</b> '+esc(reason)+'</div>'+
   (e.warnings.length?'<div class="small warning" style="margin-top:6px">⚠️ '+esc(e.warnings.slice(0,2).join(" · "))+'</div>':'')+
  '</div>';
 }).join("");
 o.innerHTML='<div style="padding:15px;background:#fff;border-radius:18px;border:2px solid #dbe4f0">'+
  '<div class="small">AKTUELLE BOB-ANALYSE · '+esc(r.scenario)+' · '+r.total+' Kandidat(en) geprüft</div>'+
  '<div style="font-size:20px;font-weight:800;margin-top:4px">🎯 Trade-Rangliste</div>'+
  '<div class="small" style="margin-top:4px">Bob sortiert die passenden Produkte nach technischer Passung und Produktrisiko.</div>'+
  cards+
  '<div class="small" style="margin-top:9px">Die Plätze sind eine technische Rangfolge der geprüften DEGIRO-Kandidaten, keine Gewinnwahrscheinlichkeit und keine Garantie.</div></div>';
 return r;
}

if(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{try{inject();}catch(e){console.warn(e);}});else try{inject();}catch(e){console.warn(e);}}
window.BobDegiro={riskModel,koDistancePct,evaluateProduct,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates};
})();