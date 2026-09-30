/* Bob DEGIRO assistant: deterministic risk math, product-fit checks and Top-3 ranking. No order execution. */
(function(){
function n(v){const x=Number(v);return Number.isFinite(x)?x:null;}
function koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}
function directionOf(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null)return null;return ko<spot?"LONG":ko>spot?"SHORT":null;}
function riskModel(p){const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);if(spot===null||stop===null||riskEur===null||riskEur<=0)return{ok:false,reason:"Ungültige Eingabedaten für Risiko."};if(fx===null||fx<=0)return{ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};const dist=Math.abs(spot-stop);if(dist<=0)return{ok:false,reason:"Stop-Distanz ist null."};const maxLossUsd=riskEur/fx,approxNotionalUsd=maxLossUsd/(dist/spot),approxNotionalEur=approxNotionalUsd*fx,marginEur=approxNotionalEur/lev,ko=n(p.ko),koPct=koDistancePct(spot,ko),warnings=[];if(ko!==null&&((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");return{ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};}
function evaluateProduct(p){const spot=n(p.spot),ko=n(p.ko),lev=Math.max(1,n(p.leverage)||1),spread=Math.max(0,n(p.spread)||0),atr=n(p.atr),requested=String(p.direction||"NEUTRAL").toUpperCase(),productDirection=String(p.productDirection||directionOf(spot,ko)||"").toUpperCase(),reasons=[],warnings=[];if(spot===null||spot<=0)return{ok:false,fit:false,score:0,reasons:["Kein gültiger XAU/USD-Preis."],warnings:[]};if(!productDirection||!["LONG","SHORT"].includes(productDirection))reasons.push("Richtung des Produkts fehlt.");if(requested!=="NEUTRAL"&&productDirection&&requested!==productDirection)reasons.push("Produkt-Richtung passt nicht zum aktuellen Bob-Szenario.");if(ko===null)warnings.push("KO-Level fehlt – KO-Abstand kann nicht geprüft werden.");const koPct=koDistancePct(spot,ko),koDistance=ko===null?null:Math.abs(spot-ko),atrMultiple=koDistance!==null&&atr!==null&&atr>0?koDistance/atr:null;if(koPct!==null&&koPct<2)warnings.push("KO-Abstand unter 2%.");if(koPct!==null&&koPct<1)warnings.push("KO-Abstand unter 1% – sehr enger Puffer.");if(atrMultiple!==null&&atrMultiple<1.5)warnings.push("KO-Puffer kleiner als 1,5 ATR.");if(atrMultiple!==null&&atrMultiple<1)warnings.push("KO-Puffer kleiner als 1 ATR – sehr eng.");if(lev>10)warnings.push("Hebel über 10× – sehr hohe Empfindlichkeit.");if(spread>0)reasons.push("Spread wurde berücksichtigt.");let score=100;if(requested!=="NEUTRAL"&&productDirection!==requested)score-=60;if(!productDirection)score-=20;if(ko===null)score-=20;if(koPct!==null&&koPct<2)score-=20;if(koPct!==null&&koPct<1)score-=20;if(atrMultiple!==null&&atrMultiple<1.5)score-=15;if(atrMultiple!==null&&atrMultiple<1)score-=20;if(lev>10)score-=15;if(spread>0)score-=Math.min(10,spread);const fit=score>=60&&!reasons.some(x=>x.includes("passt nicht"));return{ok:true,fit,score:Math.max(0,Math.round(score)),direction:productDirection,koDistancePct:koPct,koDistance,atrMultiple,leverage:lev,reasons,warnings};}
function rankProducts(products,context={}){const valid=(products||[]).map((p,i)=>Object.assign({_index:i},p)).filter(p=>String(p.name||p.isin||"").trim()&&n(p.spot)>0).map(p=>Object.assign(p,{evaluation:evaluateProduct(Object.assign({},p,context))})).filter(p=>p.evaluation.ok).sort((a,b)=>b.evaluation.score-a.evaluation.score);return{scenario:String(context.direction||"NEUTRAL").toUpperCase(),candidates:valid.slice(0,4),total:valid.length};}
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
 const spread=(raw.match(/(?:SPREAD)\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";
 const direction=upper.includes("SHORT")||upper.includes("PUT")?"SHORT":(upper.includes("LONG")||upper.includes("CALL")?"LONG":"");
 const lines=raw.split(/\n+/).map(x=>x.trim()).filter(Boolean);
 const nameLine=lines.find(x=>/GOLD|XAU|TURBO|KNOCK|CALL|PUT/i.test(x)&&x.length<100)||"";
 return {isin,leverage:lev.replace(",","."),ko:ko.replace(",","."),spread:spread.replace(",","."),direction,name:nameLine};
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
  const result=await T.recognize(file,"eng",{logger:m=>{if(status&&m&&m.status==="recognizing text"&&m.progress)status.textContent="📷 OCR "+Math.round(m.progress*100)+"%";}});
  const x=ocrExtract(result.data.text);
  const set=(kind,value)=>{const el=document.querySelector('[data-dg="'+kind+'"][data-i="'+i+'"]');if(el&&value)el.value=value;};
  set("name",x.name);set("isin",x.isin);set("dir",x.direction);set("lev",x.leverage);set("ko",x.ko);set("spread",x.spread); if(x.isin)enrichProduct(i);
  if(status)status.textContent=x.isin?"✅ Screenshot gelesen – Angaben bitte kurz gegen DEGIRO prüfen.":"⚠️ Screenshot gelesen, aber keine sichere ISIN erkannt – Angaben bitte prüfen.";
 }catch(e){if(status)status.textContent="⚠️ OCR nicht verfügbar. Kandidaten können weiterhin manuell eingegeben werden.";}
}
function parseScreenshotCandidates(text){const raw=String(text||"");const hits=[];const re=/\b[A-Z]{2}[A-Z0-9]{10}\b/g;let m;while((m=re.exec(raw))&&hits.length<4){const x=ocrExtract(raw.slice(Math.max(0,m.index-180),Math.min(raw.length,m.index+260)));x.isin=m[0];if(!hits.some(v=>v.isin===x.isin))hits.push(x);}return hits;}\nfunction inject(){if(document.getElementById("dgTop3"))return;const a=document.getElementById("dgProductOut");if(!a)return;const b=document.createElement("div");b.id="dgTop3";b.style.cssText="margin-top:14px;padding:12px;background:#f6f8fa;border-radius:12px";b.innerHTML='<b>🏆 Bob Top 4 – DEGIRO-Produkte</b><div class="small" style="margin:6px 0 10px">Bob prüft die Kandidaten im Hintergrund nach Richtung, KO-Abstand, Volatilität, Hebel und Spread. Der Check ist keine Gewinnwahrscheinlichkeit.</div><div id="dgTop3Inputs"></div><button style="margin-top:8px" id="dgRankBtn">🔎 Top 4 vergleichen</button><div id="dgTop3Out" style="margin-top:10px"></div>';a.parentNode.insertBefore(b,a.nextSibling);const q=b.querySelector("#dgTop3Inputs");for(let i=1;i<=4;i++){const r=document.createElement("div");r.style.cssText="margin:8px 0;padding:8px;background:#fff;border-radius:10px";r.innerHTML='<b>Kandidat '+i+'</b><div class="small" style="margin-top:5px">Kostenloser Screenshot-Fallback (OCR direkt im Browser):</div><input type="file" accept="image/*" data-dgshot="1" data-i="'+i+'" style="margin:6px 0"><div id="dgOcrStatus'+i+'" class="small">Kein Screenshot gelesen.</div><div id="dgResearch'+i+'" class="small research" style="margin-top:6px">🌐 Öffentliche Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="'+i+'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="'+i+'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="'+i+'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="'+i+'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="'+i+'" type="number" step=".01" placeholder="KO-Level"><input data-dg="spread" data-i="'+i+'" type="number" step=".01" min="0" placeholder="Spread"></div>';q.appendChild(r);r.querySelector('[data-dgshot="1"]').addEventListener("change",e=>readScreenshot(i,e.target.files&&e.target.files[0]));}b.querySelector("#dgRankBtn").addEventListener("click",rankUI);}
function rankUI(){const s=spot(),d=scenario(),a=atr(),ps=[1,2,3,4].map(i=>({name:document.querySelector('[data-dg="name"][data-i="'+i+'"]')?.value.trim(),productDirection:document.querySelector('[data-dg="dir"][data-i="'+i+'"]')?.value,price:n(document.querySelector('[data-dg="price"][data-i="'+i+'"]')?.value),leverage:n(document.querySelector('[data-dg="lev"][data-i="'+i+'"]')?.value),ko:n(document.querySelector('[data-dg="ko"][data-i="'+i+'"]')?.value),spread:n(document.querySelector('[data-dg="spread"][data-i="'+i+'"]')?.value)||0,spot:s})),r=rankProducts(ps,{direction:d,atr:a,spot:s}),o=document.getElementById("dgTop3Out");if(!o)return r;if(!r.candidates.length){o.innerHTML='<span class="bad"><b>Keine passende Auswahl.</b></span><div class="small">Mindestens einen vollständigen Kandidaten eingeben. Bei neutralem Szenario wird keine Richtung künstlich bevorzugt.</div>';return r;}const best=r.candidates[0];o.innerHTML='<div class="small">Szenario: <b>'+r.scenario+'</b> · '+r.total+' Kandidat(en) geprüft</div>'+r.candidates.map((p,i)=>{const e=p.evaluation,k=e.koDistancePct===null?"—":e.koDistancePct.toFixed(2)+"%",at=e.atrMultiple===null?"—":e.atrMultiple.toFixed(1)+" ATR",w=e.warnings.slice(0,2).join(" · "),fav=i===0,why=fav?(e.direction===r.scenario?'Richtung passt zum Szenario. ':'Neutrales Szenario. ')+(e.koDistancePct!==null?'KO-Puffer '+k+'. ':'')+(e.atrMultiple!==null?'ATR-Puffer '+at+'.':''):'';return '<div style="margin-top:8px;padding:10px;background:#fff;border-radius:10px;border:2px solid '+(fav?'#16a34a':'#e5e7eb')+'"><b>'+(fav?'🟢 ⭐ BOB-FAVORIT':'🔵 '+(i+1)+'.')+' '+esc(p.name||"Produkt")+'</b><div class="small">'+esc(e.direction||"—")+' · Hebel '+(e.leverage||"—")+'× · KO-Abstand '+k+' · '+at+' · Technischer Check '+e.score+'/100</div>'+(fav?'<div class="small ok" style="margin-top:6px"><b>Warum:</b> '+esc(why)+'</div>':'')+(w?'<div class="small warning" style="margin-top:6px">'+esc(w)+'</div>':'<div class="small ok" style="margin-top:6px">Keine wesentliche Warnung im aktuellen Check.</div>')+'</div>';}).join("")+'<div class="small" style="margin-top:8px">Bob kennzeichnet den technisch passendsten Kandidaten. Das ist keine Gewinnwahrscheinlichkeit und keine Garantie.</div>';return r;}
if(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{try{inject();}catch(e){console.warn(e);}});else try{inject();}catch(e){console.warn(e);}}
window.BobDegiro={riskModel,koDistancePct,evaluateProduct,rankProducts};
})();