/* Bob Mein Trade: locally observed, source-labelled product value curve.
   Never downloads extra provider data, sends orders, or invents product history. */
(function(root){
 'use strict';
 const STORE='bobProductPriceCurveV1',MAX_SAMPLES=400,MIN_SAMPLE_MS=28000;
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 const positive=x=>finite(x)&&x>0;
 const stamp=x=>typeof x==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(x)?Date.parse(x):NaN;
 const recent=(at,now,max)=>finite(at)&&now>=at&&now-at<=max;
 const number=v=>Number.isFinite(Number(v))?Number(v):NaN;
 const fmt=(value,currency)=>finite(value)?value.toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:4})+' '+currency:'—';
 const clock=at=>finite(at)?new Date(at).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'unbekannt';

 function assess(input,now=Date.now()){
  const trade=input?.trade,p=trade?.product,currency=p?.currency;
  const absent=(reason)=>({available:false,reason,tradeKey:null,currency:null,stage:'unavailable'});
  if(!trade?.active||trade.test||!p||!['EUR','CHF'].includes(currency)
     ||!['LONG','SHORT'].includes(p.direction)||!p.isin||!p.referenceConfirmed||!p.simpleSpotTurbo)
   return absent('Noch kein bestätigter EUR-/CHF-Gold-Spot-Produkttrade. Zuerst Produkt und Kaufdaten erfassen.');
  const key=String(trade.tradeId||trade.monitorStartedAt||p.isin);
  const tradeKey=p.isin+'|'+key;
  const spot=input.spots||{},gold=number(spot.xaus),spotAt=stamp(spot.spot_price_as_of);
  const spotFresh=spot.is_genuine_xauusd_spot===true&&!spot.spot_error&&positive(gold)&&recent(spotAt,now,60000);
  const fx=spot[currency==='CHF'?'usd_chf_meta':'usd_eur_meta']||{};
  const fxAt=stamp(fx.fetchedAt),fxFresh=positive(number(fx.rate))&&!fx.error&&recent(fxAt,now,90000);
  const engine=root.BobTradeProduct;
  const model=fxFresh?engine?.withFx(p,spot,now):null;
  const calculated=spotFresh&&fxFresh?engine?.price(model,gold):null;
  const modelOk=calculated?.available===true&&model?.fxDetails?.delayed===false;
  const ko=number(p.ko),distance=spotFresh&&positive(ko)?Math.abs(gold-ko)/gold*100:null;
  const knockedOut=spotFresh&&positive(ko)&&(p.direction==='LONG'?gold<=ko:gold>=ko);
  const q=input.quote;
  const qAt=stamp(q?.at),qAskAt=stamp(q?.askAt);
  const quoteOk=q?.isin===p.isin&&q.currency===currency
    &&(q.kind==='issuer'||q.kind==='research')
    &&positive(q.bid)&&positive(q.ask)&&q.ask>=q.bid
    &&q.error!==true&&q.delayed!==true
    &&recent(qAt,now,90000)&&recent(qAskAt,now,90000);
  // A same-time issuer observation can independently test the stored model.
  // This is NOT an estimate of the difference to an executable DEGIRO quote.
  const comparison=quoteOk&&modelOk&&Math.abs(qAt-spotAt)<=30000&&Math.abs(qAt-fxAt)<=30000
   ?{quoted:q.bid,estimated:calculated.price,at:qAt,fxAt,spotAt,
     quotedSource:String(q.source||'Anbieterbeobachtung'),kind:q.kind,currency} :null;
  let kind=null,price=null,source='',sourceAt=null;
  if(quoteOk){
   price=q.bid;source=String(q.source||'Anbieterbeobachtung');sourceAt=qAt;
   kind=q.kind==='issuer'?'issuer':'research';
  }else if(modelOk){
   price=calculated.price;source='Bob · Gold/FX-Produktmodell';sourceAt=spotAt;kind='model';
  }
  const stopGold=number(input.stopGold),targetGold=number(input.targetGold);
  // Stop/target model comparison needs the same verified fresh Gold/FX pair as Bob's existing stop assistant.
  const stop=spotFresh&&fxFresh&&engine?.price(model,stopGold),target=spotFresh&&fxFresh&&engine?.price(model,targetGold);
  const levels=stop?.available===true&&target?.available===true
     &&stop.price<target.price&&stop.price>0;
  let stage='waiting';
  if(knockedOut)stage='ko';
  else if(!quoteOk&&!modelOk)stage='waiting';
  else if(!levels)stage='levels-unavailable';
  else if(price<=stop.price)stage='stop';
  else if(price>=target.price)stage='target';
  else if(finite(distance)&&distance<=2)stage='ko-near';
  else stage='observing';
  const actionBase={
   ko:'KO-Schwelle beim Goldpreis erreicht/überschritten: Produktstatus sofort bei DEGIRO prüfen. Keine reguläre Verkaufskursschätzung.',
   stop:'Stop-Zone erreicht: Bob würde zum Prüfen des Ausstiegs bei DEGIRO warnen. Kein automatischer Verkauf.',
   target:'Ziel-Zone erreicht: Bob würde Gewinnschutz, Zielverlängerung und Stop-Nachziehen prüfen.',
   'ko-near':'KO-Abstand höchstens 2 %: Bob würde vor erhöhtem Knock-out-Risiko warnen.',
   'levels-unavailable':'Stop/Ziel derzeit nicht sicher in Produktwährung berechenbar. Bestehenden Stop nicht lockern.',
   observing:'Bob beobachtet das Produkt. Ein neuer Stop wird nur nach Prüfung vorgeschlagen; bestehenden Stop nicht lockern.',
   waiting:'Kein frischer Quellen- oder Modellkurs. Bob wartet auf aktuelle Nachweise; keine neue Stop-/Zielbestätigung.'
  }[stage];
  const action=finite(distance)&&distance<=2&&stage!=='ko'&&stage!=='ko-near'
    ?actionBase+' Zusätzlich KO-Abstand höchstens 2 %: Knock-out-Risiko prüfen.'
    :actionBase;
  return {available:positive(price),tradeKey,isin:p.isin,currency,price,kind,source,sourceAt,
   spotAt,fxAt,fxRate:fxFresh?number(fx.rate):null,comparison,
   ko:positive(ko)?ko:null,koDistancePct:distance,knockedOut,
   underlyingGold:spotFresh?gold:null,stop:levels?stop.price:null,target:levels?target.price:null,
   stopGold:positive(stopGold)?stopGold:null,targetGold:positive(targetGold)?targetGold:null,
   stage,action,reason:quoteOk?(kind==='issuer'?'Original datierter Emittenten-Geldkurs, KEIN bestätigter DEGIRO-Ausführungskurs.':'Datierte Anbieter-/Chartbeobachtung, KEIN ausführbarer Brokerkurs.'):
      modelOk?'Rechnerischer Geldkurs aus datiertem Gold-Spot und aktuellem FX-Abruf; angenommene Produktbedingungen, keine bestätigte Ausführung.':
      'Kein ausreichend aktueller Preis. Alter Verlauf bleibt sichtbar; es werden keine Werte ergänzt.',
   observationOnly:true,degiroExecutable:false,automaticOrder:false};
 }
 function addObservation(history,result,now=Date.now()){
  if(!result?.tradeKey)return {tradeKey:history?.tradeKey||null,rows:Array.isArray(history?.rows)?history.rows:[],added:false};
  const base=history&&history.tradeKey===result?.tradeKey&&Array.isArray(history.rows)
   ?history:{tradeKey:result?.tradeKey,rows:[]};
  const rows=base.rows.filter(x=>x&&positive(x.price)&&['issuer','research','model'].includes(x.kind)
    &&finite(x.at)&&x.at<=now&&x.at>=now-7*86400000&&finite(x.sourceAt)&&x.sourceAt<=now)
    .slice(-MAX_SAMPLES);
  if(!result?.available||!finite(result.sourceAt)||!recent(result.sourceAt,now,90000)
    ||result.stage==='ko')return {tradeKey:result?.tradeKey,rows,added:false};
  const last=rows.at(-1);
  if(last&&(last.sourceAt===result.sourceAt&&last.kind===result.kind))return {tradeKey:result.tradeKey,rows,added:false};
  if(last&&now-last.at<MIN_SAMPLE_MS)return {tradeKey:result.tradeKey,rows,added:false};
  rows.push({at:now,sourceAt:result.sourceAt,price:result.price,kind:result.kind,
   source:result.source.slice(0,100),currency:result.currency,fxAt:result.fxAt,
   gold:result.underlyingGold,koDistancePct:result.koDistancePct});
  return {tradeKey:result.tradeKey,rows:rows.slice(-MAX_SAMPLES),added:true};
 }
 function read(){
  try{const v=JSON.parse(root.localStorage?.getItem(STORE)||'null');return v&&typeof v==='object'?v:null;}catch(_){return null;}
 }
 function save(h){try{root.localStorage?.setItem(STORE,JSON.stringify(h));}catch(_){}}
 function fibonacci(rows){
  // Fibonacci needs one continuous, like-kind source series. Outages/issuer-to-model
  // transitions break the swing; long unattended gaps never become fake price moves.
  const ordered=(Array.isArray(rows)?rows:[]).filter(x=>x&&positive(x.price)&&finite(x.at))
   .sort((a,b)=>a.at-b.at);
  const p=[];
  for(const x of ordered){
   const prev=p.at(-1);
   if(prev&&(x.at-prev.at>180000||x.kind!==prev.kind||x.source!==prev.source))p.length=0;
   if(!prev||x.at>prev.at||!p.length)p.push(x);
  }
  if(p.length<6||new Set(p.map(x=>x.at)).size<6||p.at(-1).at-p[0].at<120000)return null;
  let low=p[0],high=p[0];for(const x of p){if(x.price<low.price)low=x;if(x.price>high.price)high=x;}
  const d=high.price-low.price;if(d<Math.max(.03,high.price*.0015))return null;
  const rising=low.at<high.at;
  return {low:low.price,high:high.price,rising,samples:p.length,source:p.at(-1).source||p.at(-1).kind||'Preisbeobachtung',
   levels:[0,.236,.382,.5,.618,.786,1].map(r=>({ratio:r,price:rising?high.price-r*d:low.price+r*d}))};
 }
 let panel=null,canvas=null,picked=null,lastResult=null,lastHistory=null,zoom='price',showFib=true;
 const QUALITY_STORE='bobProviderModelCalibrationV1';
 function median(values){const a=[...values].sort((x,y)=>x-y);return a.length?(a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2):null;}
 function calibrate(history,now=Date.now()){
  const all=(history?.rows||[]).filter(x=>x&&positive(x.quoted)&&positive(x.estimated)
    &&finite(x.at)&&now>=x.at&&now-x.at<=86400000);
  const last=all.at(-1);
  // Never transfer bias between different issuer feeds or research quote types.
  const samples=last?all.filter(x=>x.kind===last.kind&&x.source===last.source):[];
  if(samples.length<5)return {usable:false,count:samples.length,reason:'Mindestens 5 unabhängige zeitgleiche Anbieterbeobachtungen benötigt'};
  const span=samples.at(-1).at-samples[0].at;
  if(span<300000)return {usable:false,count:samples.length,reason:'Kalibrierung braucht mindestens 5 Minuten getrennte Beobachtungen'};
  const deviations=samples.map(x=>x.quoted-x.estimated);
  const offset=median(deviations),scale=median(samples.map(x=>x.estimated));
  const dispersion=median(deviations.map(x=>Math.abs(x-offset)));
  if(!positive(scale)||!finite(offset)||!finite(dispersion)||Math.abs(offset)>scale*.03||dispersion>scale*.01)
   return {usable:false,count:samples.length,reason:'Abweichungen sind zu groß oder uneinheitlich; keine automatische Korrektur'};
  if(now-samples.at(-1).at>1800000)return {usable:false,count:samples.length,reason:'Kalibrierung über 30 Minuten alt'};
  return {usable:true,count:samples.length,offset,dispersion,reason:'Zeitgleicher SG/comdirect-Anbieterabgleich · nur indikative Modellkorrektur'};
 }
 function learnComparison(previous,comparison,tradeKey,now=Date.now()){
  const base=previous?.tradeKey===tradeKey&&Array.isArray(previous.rows)?previous:{tradeKey,rows:[]};
  const rows=base.rows.filter(x=>x&&finite(x.at)&&now-x.at<86400000&&now>=x.at).slice(-29);
  if(comparison&&positive(comparison.quoted)&&positive(comparison.estimated)
     &&finite(comparison.at)&&now-comparison.at>=0&&now-comparison.at<=90000
     &&!rows.some(x=>x.at===comparison.at&&x.kind===comparison.kind)
     &&(!rows.length||comparison.at-rows.at(-1).at>=60000)){
   rows.push({at:comparison.at,quoted:comparison.quoted,estimated:comparison.estimated,
    kind:comparison.kind,currency:comparison.currency,source:comparison.quotedSource});
  }
  return {tradeKey,rows:rows.slice(-30)};
 }
 function readQuality(){try{return JSON.parse(root.localStorage?.getItem(QUALITY_STORE)||'null')}catch(_){return null}}
 function saveQuality(value){try{root.localStorage?.setItem(QUALITY_STORE,JSON.stringify(value))}catch(_){}}

 function reviewStop(result,history,trade){
  if(!result?.available||!positive(result.price)||!positive(result.stop)||!positive(result.target)
     ||result.stage==='ko'||!positive(trade?.product?.entry))return {ready:false,reason:'Stopp-Prüfung wartet auf aktuellen Modell-/Anbieterkurs und gültigen Produktplan.'};
  const entry=trade.product.entry,price=result.price,stop=result.stop,target=result.target;
  if(!(stop<target))return {ready:false,reason:'Stopp/Ziel widersprüchlich, keine Anpassung.'};
  const riskPct=(price-stop)/price*100,rewardPct=(target-price)/price*100;
  const rr=riskPct>0&&rewardPct>0?rewardPct/riskPct:null;
  let detail='Aktueller Stopp-Abstand '+riskPct.toFixed(1)+' %; '+
   (positive(rr)?'verbleibendes Chancen/Risiko ≈ '+rr.toFixed(2)+':1. ':'Ziel bereits erreicht oder Stoppzone unterschritten. ')+
   (riskPct>10?'Weit für einen kurzfristigen Trade – an Marktvolatilität und KO-Risiko prüfen. ':'');
  if(result.stage==='stop'||riskPct<=0)return {ready:false,riskPct,rr,reason:detail+'Stoppzone erreicht; bei DEGIRO prüfen.'};
  const sequence=[];
  for(const row of history?.rows||[]){
   if(!positive(row.price)||!finite(row.at))continue;
   const last=sequence.at(-1);
   if(last&&(row.kind!==last.kind||row.source!==last.source||row.at-last.at>180000))sequence.length=0;
   sequence.push(row);
  }
  if(sequence.length<12||sequence.at(-1).at-sequence[0].at<300000)
   return {ready:true,riskPct,rr,reason:detail+'Für Nachzieh-Vorschlag mindestens 12 zusammenhängende Kursbeobachtungen nötig.'};
  const moves=sequence.slice(-12).map((row,i,all)=>i?Math.abs(row.price-all[i-1].price):0).slice(1);
  const movement=moves.reduce((a,b)=>a+b,0)/moves.length;
  const margin=Math.max(price*.0075,3*movement);
  const possible=price-margin;
  // Only suggest protecting profit after at least one initial R gained.
  const initialRisk=Math.max(.01,entry-stop);
  if(price-entry<initialRisk||possible<=stop+.02||possible>=price)
   return {ready:true,riskPct,rr,reason:detail+'Kein ausreichend abgesicherter Gewinn für einen engeren Stopp; bestehenden Stopp nicht lockern.'};
  return {ready:true,riskPct,rr,suggestedStop:Math.max(stop,possible),
   reason:detail+'Indikativer engerer Stopp aus Kursbewegungen; nur nach Prüfung bei DEGIRO selbst setzen.'};
 }
 let background={tradeId:null,rows:[],checkedAt:0,status:'noch nicht synchronisiert',busy:false};
 function mergedHistory(local,remote,tradeKey){
  const pool=new Map();
  for(const row of [...(remote||[]),...(local?.rows||[])]){
   if(!row||!positive(row.price)||!finite(row.at)||!finite(row.sourceAt)
       ||!['issuer','research','model'].includes(row.kind))continue;
   const id=row.kind+'|'+row.sourceAt+'|'+(row.kind==='model'?(row.fxAt??''):'');
   pool.set(id,row);
  }
  return {tradeKey,rows:[...pool.values()].sort((a,b)=>a.at-b.at).slice(-800)};
 }
 function refreshBackground(trade,now=Date.now()){
  const id=trade?.active&&!trade.test&&trade.tradeId?String(trade.tradeId):null;
  if(!id||!root.fetch)return;
  if(background.tradeId!==id)background={tradeId:id,rows:[],checkedAt:0,status:'warte auf Hintergrunddaten',busy:false};
  if(background.busy||now-background.checkedAt<30000)return;
  background.checkedAt=now;background.busy=true;
  root.fetch('/api/real-trades/curve',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({tradeId:id}),signal:root.AbortSignal?.timeout?.(12000)})
   .then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
   .then(data=>{
    if(background.tradeId!==id)return;
    if(data?.tradeId!==id||!Array.isArray(data.rows))throw Error('Ungültige Hintergrundantwort');
    background.rows=data.rows.filter(v=>v&&positive(v.price)&&finite(v.at)&&finite(v.sourceAt));
    background.status='Serveraufzeichnung · '+background.rows.length+' datierte Modellpunkte';
    if(lastHistory?.tradeKey?.endsWith('|'+id)){
     lastHistory=mergedHistory(read(),background.rows,lastHistory.tradeKey);
     draw(lastResult,lastHistory);showStatus();
    }
   }).catch(()=>{if(background.tradeId===id)background.status='Serveraufzeichnung vorübergehend nicht erreichbar';showStatus()})
    .finally(()=>{if(background.tradeId===id)background.busy=false;});
 }
 function showStatus(){
  if(panel)panel.querySelector('[data-curve-background]').textContent=background.status+
   ' · Modellpunkte sind keine DEGIRO-Ausführung. Fehlende Kurse bleiben Lücken.';
 }

 function mount(element){
  if(!root.document||!element||panel)return;
  panel=root.document.createElement('section');panel.id='bobProductCurvePanel';panel.className='card';
  panel.innerHTML='<h3>Mein DEGIRO-Produkt · Kursverlauf</h3>'+
   '<div class="small" data-curve-isin role="status">Produkttrade wird geprüft …</div>'+
   '<div data-curve-price style="font-size:29px;font-weight:800;letter-spacing:-.5px;margin:6px 0">—</div>'+
   '<div class="small" data-curve-source></div>'+
   '<div style="display:flex;gap:5px;align-items:center;margin:10px 0 8px">'+
   '<button type="button" data-curve-zoom="price" aria-pressed="true" style="width:auto;flex:1 1 0;min-width:0;padding:8px 3px;font-size:12px;border:1px solid #94a3b8;border-radius:18px;background:#e2e8f0;color:#0f172a">Kursfokus</button>'+
   '<button type="button" data-curve-zoom="all" aria-pressed="false" style="width:auto;flex:1 1 0;min-width:0;padding:8px 3px;font-size:12px;border:1px solid #94a3b8;border-radius:18px;background:#f8fafc;color:#0f172a">Stopp &amp; Ziel</button>'+
   '<button type="button" data-curve-fib aria-pressed="true" style="width:auto;flex:1 1 0;min-width:0;padding:8px 3px;font-size:12px;border:1px solid #94a3b8;border-radius:18px;background:#f1f5f9;color:#0f172a">Fibonacci ✓</button></div>'+
   '<canvas data-curve-chart width="900" height="430" style="width:100%;height:auto;border-radius:12px;background:#f8fafc;touch-action:manipulation" aria-label="Beobachteter Kursverlauf des Gold-Hebelprodukts in seiner Produktwährung. Stop und Ziel als berechnete Linien."></canvas>'+
   '<div class="small" data-curve-quality role="status"></div>'+ 
   '<div class="small" data-curve-background></div>'+ 
   '<div class="small" data-curve-fib-note></div>'+
   '<div class="small" data-curve-picked aria-live="polite"></div>'+
   '<div class="small" data-curve-levels></div>'+ 
   '<div class="small" data-curve-stop-review role="status"></div>'+ 
   '<p data-curve-action role="status"></p>'+
   '<p class="small">Kurve ab Beginn dieser Aufzeichnung auf diesem Handy: echte datierte Anbieterbeobachtungen und klar gekennzeichnete Modellpunkte. Keine erfundene rückwirkende Historie, keine Ausführungskurse. Bei geschlossener App entstehen hier keine neuen Punkte. KO-Schwelle in Gold-USD, nicht auf der Produktpreisachse. Bob empfiehlt nur; du handelst selbst bei DEGIRO.</p>';
  element.append(panel);canvas=panel.querySelector('canvas');
  panel.querySelectorAll('[data-curve-zoom]').forEach(button=>button.addEventListener('click',()=>{
   zoom=button.getAttribute('data-curve-zoom');
   panel.querySelectorAll('[data-curve-zoom]').forEach(b=>{const chosen=b===button;b.setAttribute('aria-pressed',String(chosen));b.style.background=chosen?'#e2e8f0':'#f8fafc';});
   draw(lastResult,lastHistory);
  }));
  panel.querySelector('[data-curve-fib]').addEventListener('click',event=>{
   showFib=!showFib;event.currentTarget.setAttribute('aria-pressed',String(showFib));
   event.currentTarget.textContent=showFib?'Fibonacci ✓':'Fibonacci aus';
   draw(lastResult,lastHistory);
  });
  canvas.addEventListener('pointerdown',event=>{
   const h=lastHistory;if(!h?.rows?.length)return;
   const rect=canvas.getBoundingClientRect();if(!rect.width)return;
   const x=(event.clientX-rect.left)*canvas.width/rect.width;
   const first=h.rows[0].at,last=h.rows.at(-1).at,span=Math.max(last-first,30000);
   const target=first+Math.max(0,Math.min(1,(x-82)/(canvas.width-114)))*span;
   picked=h.rows.reduce((best,v)=>!best||Math.abs(v.at-target)<Math.abs(best.at-target)?v:best,null);
   showPicked();
  });
 }
 function showPicked(){
  if(!panel)return;panel.querySelector('[data-curve-picked]').textContent=picked?
   'Ausgewählter Punkt · '+clock(picked.at)+' aufgezeichnet · '+fmt(picked.price,picked.currency)
    +' · '+(picked.kind==='model'?'≈ berechnet':picked.kind==='issuer'?'Emittent':'Analysequelle')
    +' · ursprüngliche Kurszeit '+clock(picked.sourceAt):
   'Kurvenpunkt antippen: Beobachtung und ursprüngliche Quellenzeit anzeigen.';
 }
 function line(ctx,ys,color,dash=[]){
  ctx.beginPath();ctx.setLineDash(dash);ctx.strokeStyle=color;ctx.lineWidth=2;
  for(const [i,y] of ys.entries()){if(i===0)ctx.moveTo(y[0],y[1]);else ctx.lineTo(y[0],y[1]);}
  ctx.stroke();ctx.setLineDash([]);
 }
 function draw(result,h){
  if(!canvas)return;
  const ctx=canvas.getContext('2d');if(!ctx)return;
  const w=canvas.width,hgt=canvas.height,rows=(h?.rows||[]).filter(x=>finite(x.price));
  ctx.clearRect(0,0,w,hgt);ctx.fillStyle='#334155';ctx.font='19px system-ui';
  const valid=[...rows.map(x=>x.price),result?.available?result.price:null,...(zoom==='all'?[result?.stop,result?.target]:[])].filter(positive);
  if(!valid.length){ctx.fillText('Noch kein datierter Produktkurs verfügbar',40,165);return;}
  const low=Math.min(...valid),high=Math.max(...valid),pad=Math.max(.12,high*.012,(high-low)*.12),min=Math.max(0,low-pad),max=high+pad;
  const x0=82,x1=w-32,y0=28,y1=hgt-67;
  const y=value=>y1-(value-min)/Math.max(.0001,max-min)*(y1-y0);
  const start=rows[0]?.at??Date.now(),end=rows.at(-1)?.at??start,period=Math.max(30000,end-start);
  const x=at=>x0+(at-start)/period*(x1-x0);
  ctx.lineWidth=1;ctx.font='16px system-ui';
  for(let i=0;i<=4;i++){const v=min+(max-min)*i/4,py=y(v);
   line(ctx,[[x0,py],[x1,py]],'#dde5ed');ctx.fillStyle='#475569';ctx.fillText(v.toFixed(2),5,py+5);}
  if(rows.length<2){ctx.fillStyle='#64748b';ctx.fillText('Verlauf wird ab jetzt aufgezeichnet …',x0+15,y1-30);}
  for(let i=1;i<rows.length;i++){
   const a=rows[i-1],b=rows[i];
   if(a.kind!==b.kind||b.at-a.at>180000)continue; // Do not bridge source switches or data outages.
   const color=b.kind==='issuer'?'#0f766e':b.kind==='research'?'#64748b':'#2563eb';
   ctx.beginPath();ctx.moveTo(x(a.at),y1);ctx.lineTo(x(a.at),y(a.price));
   ctx.lineTo(x(b.at),y(b.price));ctx.lineTo(x(b.at),y1);ctx.closePath();
   const fill=ctx.createLinearGradient(0,y0,0,y1);
   fill.addColorStop(0,'rgba(56,189,248,.23)');fill.addColorStop(1,'rgba(56,189,248,.02)');
   ctx.fillStyle=fill;ctx.fill();
   line(ctx,[[x(a.at),y(a.price)],[x(b.at),y(b.price)]],color,b.kind==='model'?[8,5]:[]);
  }
  for(const row of rows.slice(-200)){
   ctx.beginPath();ctx.arc(x(row.at),y(row.price),row===rows.at(-1)?5:2.5,0,2*Math.PI);
   ctx.fillStyle=row.kind==='issuer'?'#0f766e':row.kind==='research'?'#64748b':'#2563eb';ctx.fill();
  }
  const fib=fibonacci(rows);
  if(showFib&&fib){
   const labelled=[];
   for(const level of fib.levels){
    const py=y(level.price);if(py<y0||py>y1)continue;
    line(ctx,[[x0,py],[x1,py]],'#b98739',[5,7]);
    if(!labelled.some(v=>Math.abs(v-py)<19)){
     ctx.fillStyle='#98651f';ctx.font='13px system-ui';
     ctx.fillText('F '+(level.ratio*100).toFixed(1)+'% · '+level.price.toFixed(2),x0+8,Math.max(y0+16,py-6));
     labelled.push(py);
    }
   }
  }
  ctx.font='17px system-ui';
  for(const [name,value,color] of [['Stopp ≈',result?.stop,'#b91c1c'],['Ziel ≈',result?.target,'#15803d']]){
   if(!positive(value))continue;
   const below=value<min,above=value>max,py=y(Math.max(min,Math.min(max,value)));
   if(!below&&!above)line(ctx,[[x0,py],[x1,py]],color,[9,7]);
   ctx.fillStyle=color;
   ctx.fillText(name+' '+value.toFixed(2)+(above?' ↑':below?' ↓':''),x0+5,
    above?y0+18:below?y1-10:Math.max(y0+18,py-7));
  }
  if(result?.available&&positive(result.price)){
   const py=y(Math.max(min,Math.min(max,result.price)));
   ctx.beginPath();ctx.arc(x1,py,5,0,2*Math.PI);ctx.fillStyle='#0f766e';ctx.fill();
   ctx.fillStyle='#0f766e';ctx.font='17px system-ui';
   ctx.fillText('Aktuell '+result.price.toFixed(2),x1-160,Math.max(y0+17,py-11));
  }
  ctx.fillStyle='#475569';ctx.font='16px system-ui';
  ctx.fillText(clock(start),x0,y1+24);ctx.fillText(clock(end),x1-95,y1+24);
  ctx.fillText((result?.currency||'EUR')+' je Stück · datierte Beobachtungen',x0+155,hgt-8);
 }
 function update(input,now=Date.now()){
  if(!panel)return;
  let result=assess(input,now);
  const before=readQuality(),learned=learnComparison(before,result.comparison,result.tradeKey,now);
  if(learned.rows.length!==(before?.tradeKey===learned.tradeKey?before?.rows?.length:0))saveQuality(learned);
  const quality=calibrate(learned,now);
  if(result.available&&result.kind==='model'&&quality.usable){
   // Display-only correction: never changes saved stop, gold decisions or orders.
   const adjusted=result.price+quality.offset;
   if(positive(adjusted)){
    result={...result,rawModelPrice:result.price,price:adjusted,
     stop:positive(result.stop)?result.stop+quality.offset:result.stop,
     target:positive(result.target)?result.target+quality.offset:result.target,
     source:result.source+' · indikativ kalibriert',calibrated:true};
   }
  }
  const existing=read();
  const local=addObservation(existing,result,now);
  if(local.added||!existing||existing.tradeKey!==local.tradeKey)save(local);
  const h=mergedHistory(local,background.tradeId===input?.trade?.tradeId?background.rows:[],local.tradeKey);
  refreshBackground(input?.trade,now);
  const repaint=local.added||lastHistory?.tradeKey!==h.tradeKey
    ||lastResult?.stage!==result.stage||lastResult?.stop!==result.stop
    ||lastResult?.target!==result.target||lastResult?.kind!==result.kind
    ||lastResult?.price!==result.price||lastResult?.koDistancePct!==result.koDistancePct;
  lastResult=result;lastHistory=h;
  if(picked&&!h.rows.some(v=>v.at===picked.at)){picked=null;}
  const show=(sel,value)=>{const node=panel.querySelector(sel);if(node)node.textContent=value;};
  const match=result.comparison;
  const qualityText=match?
   'Zeitgleicher Preisabgleich · Anbieter '+fmt(match.quoted,result.currency)+
   ' · unkalibriertes Modell '+fmt(match.estimated,result.currency)+
   ' · Differenz '+((match.estimated/match.quoted-1)*100).toFixed(2)+' % (kein DEGIRO-Kurs).':
   'Kein zeitgleicher Anbieterpreis zum aktuellen Modell verfügbar.';
  show('[data-curve-quality]',qualityText+' Kalibrierung: '+(quality.usable?
   quality.count+' geprüfte Paare; Korrektur '+(quality.offset>=0?'+':'')+
   quality.offset.toFixed(3)+' '+result.currency+' · nur Modellanzeige.':
   quality.count+' Paare; '+quality.reason+'.'));
  show('[data-curve-isin]',result.isin?result.isin+' · '+result.currency+' pro Stück':'Kein aktiver Produkttrade');
  show('[data-curve-price]',result.available?(result.kind==='model'?'≈ ':'')+fmt(result.price,result.currency):'—');
  show('[data-curve-source]',result.available?
   (result.kind==='model'?'Rechnerisch':result.kind==='issuer'?'Original-Anbieter-Geldkurs':'Anbieter-Analysebeobachtung')
    +' · '+result.source+' · Quellzeit '+clock(result.sourceAt)+' · keine DEGIRO-Ausführung':
   result.reason);
  const levels=[result.stop!=null?'Stop ≈ '+fmt(result.stop,result.currency):'Stop: nicht berechenbar',
    result.target!=null?'Ziel ≈ '+fmt(result.target,result.currency):'Ziel: nicht berechenbar',
    result.ko!=null?'KO-Schwelle '+result.ko.toFixed(2)+' USD/oz Gold':'KO-Schwelle: nicht bestätigt',
    finite(result.koDistancePct)?'KO-Abstand ca. '+result.koDistancePct.toFixed(2)+' % (Gold)':'KO-Abstand derzeit nicht prüfbar'].join(' · ');
  show('[data-curve-levels]',levels);
  const stopReview=reviewStop(result,h,input?.trade);
  show('[data-curve-stop-review]','Automatische Stopp-Prüfung: '+stopReview.reason+
   (positive(stopReview.suggestedStop)?' Nur Vorschlag: Stopp ≈ '+fmt(stopReview.suggestedStop,result.currency)+'.':'') );
  const fib=fibonacci(h.rows);
  show('[data-curve-fib-note]',fib?
   'Fibonacci aus beobachtetem Produktswing ('+(fib.rising?'Tief → Hoch':'Hoch → Tief')+
   '): '+fmt(fib.low,result.currency)+' bis '+fmt(fib.high,result.currency)+
   ' · '+fib.samples+' zusammenhängende Punkte · keine garantierten Signale.':
   'Fibonacci erscheint automatisch ab 6 datierten Kursbeobachtungen über mindestens 2 Minuten mit messbarer Kursspanne.');
  show('[data-curve-action]',result.action||'Keine Handelsempfehlung; Daten prüfen.');
  if(repaint)draw(result,h);
  showStatus();
  showPicked();
 }
 root.BobProductCurve={assess,addObservation,mergedHistory,learnComparison,calibrate,reviewStop,fibonacci,mount,update};
 if(typeof module!=='undefined'&&module.exports)module.exports={assess,addObservation,mergedHistory,learnComparison,calibrate,reviewStop,fibonacci};
})(typeof window!=='undefined'?window:globalThis);
