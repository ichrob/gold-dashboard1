/* Experimental risk analysis. Read-only: never sends orders or changes trade stops. */
(function(root){
'use strict';
const positive=x=>typeof x==='number'&&Number.isFinite(x)&&x>0;
const side=x=>['LONG','SHORT'].includes(x);
const POLICY={version:'risk-v1',spotMaxAgeMs:60000,confirmationAtr:.15,warningAtr:.5,trailingAtr:1.5,timeLimitMs:5*60000};
function analyze(bundle,now=Date.now()){
 const fail=reason=>({ready:false,direction:'ABWARTEN',stage:'DATEN FEHLEN',reason});
 const s=bundle?.spots,at=Date.parse(s?.spot_price_as_of);
 if(s?.is_genuine_xauusd_spot!==true||s.spot_error||!positive(s.xaus)||!Number.isFinite(at)||at>now||now-at>POLICY.spotMaxAgeMs)return fail('Aktueller Gold-Spot mit Originalzeit fehlt.');
 const raw=bundle?.history?.bars_by_tf?.['1m'];
 if(!Array.isArray(raw))return fail('1-Minuten-Kerzen fehlen; kein schnelles Signal.');
 const bars=raw.filter(b=>b.isOpen!==true&&Number.isFinite(b.openTime)&&b.openTime+60000<=now).slice(-21);
 if(bars.length<21)return fail('Mindestens 21 abgeschlossene 1-Minuten-Kerzen benötigt.');
 if(bars.some((b,i)=>b.instrument!=='XAU/USD'||b.openTime%60000!==0||!['open','high','low','close'].every(k=>positive(b[k]))||b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close)||b.low>b.high||(i&&b.openTime-bars[i-1].openTime!==60000)))return fail('1-Minuten-Kerzen unplausibel oder lückenhaft.');
 const last=bars.at(-1),prev=bars.at(-2);
 if(now-last.openTime>120000||at<last.openTime+60000)return fail('Spot und abgeschlossene Minutenkerzen sind zeitlich nicht aktuell.');
 const ranges=bars.slice(1).map((b,i)=>Math.max(b.high-b.low,Math.abs(b.high-bars[i].close),Math.abs(b.low-bars[i].close)));
 const atr=ranges.slice(-14).reduce((a,b)=>a+b,0)/14;
 if(!positive(atr)||Math.abs(s.xaus-last.close)>5*atr)return fail('Schwankungsbreite oder Übereinstimmung von Spot und Kerzen prüfen.');
 // Reference levels precede BOTH confirmation bars; no future pivot data.
 const reference=bars.slice(-7,-2),high=Math.max(...reference.map(b=>b.high)),low=Math.min(...reference.map(b=>b.low));
 const upper=high+POLICY.confirmationAtr*atr,lower=low-POLICY.confirmationAtr*atr;
 let direction='ABWARTEN',stage='BEOBACHTEN',reason='Noch keine eindeutige kurze Bewegung.';
 if(prev.close>upper&&last.close>upper&&s.xaus>upper){direction='LONG';stage='BESTÄTIGT';reason='Zwei geschlossene Minutenkerzen über dem vorher bekannten Hoch; Spot bestätigt.';}
 else if(prev.close<lower&&last.close<lower&&s.xaus<lower){direction='SHORT';stage='BESTÄTIGT';reason='Zwei geschlossene Minutenkerzen unter dem vorher bekannten Tief; Spot bestätigt.';}
 else if(s.xaus>last.close&&s.xaus-low>=POLICY.warningAtr*atr&&last.close>=prev.close){direction='LONG';stage='VORWARNUNG';reason='Kurzer Aufwärtsimpuls; noch keine bestätigte Fortsetzung.';}
 else if(s.xaus<last.close&&high-s.xaus>=POLICY.warningAtr*atr&&last.close<=prev.close){direction='SHORT';stage='VORWARNUNG';reason='Kurzer Rücksetzer; noch keine bestätigte Fortsetzung.';}
 return {ready:true,direction,stage,reason,spot:s.xaus,at,barAt:last.openTime,atr,high,low,ageSeconds:Math.round((now-at)/1000)};
}
function ranking(products,state,context,api,now=Date.now()){
 if(!state.ready||!side(state.direction)||!api?.earlyWarningRanking)return [];
 const seen=new Set(),rows=[];
 for(const original of products||[]){
  if(!original?.isin||seen.has(original.isin))continue;
  seen.add(original.isin);
  // Singleton calls keep all original KO, identity, factor and contract gates,
  // without truncating the universe to the old top three before leverage sort.
  const row=api.earlyWarningRanking([original],{...context,now,direction:state.direction,spot:state.spot,spotFresh:true});
  if(row.length&&positive(row[0].p.leverage))rows.push(row[0]);
 }
 return rows.sort((a,b)=>b.p.leverage-a.p.leverage||a.p.isin.localeCompare(b.p.isin)).slice(0,2);
}
function monitor(previous,trade,state,now=Date.now()){
 if(!trade?.active||!side(trade.dir))return {active:false,action:'KEIN AKTIVER TRADE'};
 if(!state.ready)return {...previous,active:true,action:'ÜBERWACHUNG EINGESCHRÄNKT',reason:state.reason};
 if(!trade.tradeId||!positive(trade.stop)||!positive(trade.entry))return {active:true,action:'TRADE-ANGABEN FEHLEN',reason:'Trade-ID, tatsächlicher Einstieg und bestehender Gold-Stop erforderlich.'};
 const sign=trade.dir==='LONG'?1:-1,initial=previous?.id!==trade.tradeId||previous?.dir!==trade.dir;
 const current=initial?{id:trade.tradeId,dir:trade.dir,startedAt:now,best:state.spot,stop:trade.stop,lastAt:state.at}: {...previous};
 if(!initial&&state.at<current.lastAt)return {...current,action:'ÜBERWACHUNG EINGESCHRÄNKT',reason:'Rückläufige Kurszeit.'};
 if(sign*(state.spot-current.best)>0)current.best=state.spot;
 const trailing=current.best-sign*POLICY.trailingAtr*state.atr;
 // Never loosen even when volatility increases; respect the existing trade stop.
 current.stop=sign===1?Math.max(current.stop,trade.stop,trailing):Math.min(current.stop,trade.stop,trailing);
 current.active=true;current.lastAt=state.at;
 if(current.exitAt||sign*(state.spot-current.stop)<=0){current.exitAt=current.exitAt||state.at;current.action='AUSSTIEG PRÜFEN';current.reason='Gewinnschutz-/Verlustgrenze erreicht. Kein Verkauf ausgeführt.';}
 else if(now-current.startedAt>=POLICY.timeLimitMs&&sign*(state.spot-trade.entry)<=0){current.action='ZEITGRENZE PRÜFEN';current.reason='Seit mindestens fünf Minuten beobachtet, noch keine günstige Fortsetzung gegenüber Einstieg.';}
 else if(side(state.direction)&&state.direction!==trade.dir){current.action='GEGENBEWEGUNG';current.reason='Kurze Richtung läuft gegen den erfassten Trade.';}
 else {current.action='BEOBACHTEN';current.reason='Schutzgrenze wird bei neuen Kursen geprüft.';}
 return current;
}
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>positive(x)?x.toFixed(2):'—';
function markup(state,rows,watch,main){
 return `<div class="card"><h3>${esc(state.direction)} · ${esc(state.stage)}</h3><p>${esc(state.reason)}</p><p>Haupttrend: ${esc(main||'unbekannt')} · kurze Richtung separat${side(main)&&side(state.direction)&&main!==state.direction?' · GEGEN DEN HAUPTTREND':''}</p><p class="small">${state.ready?'Gold '+fmt(state.spot)+' USD · Originalzeit '+esc(new Date(state.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}))+' · '+state.ageSeconds+' s alt':'ABWARTEN: keine aktuelle Rangliste'}</p></div>
 <div class="card"><h3>Top 2 · hoher Hebel</h3><p>Aus deiner geladenen DEGIRO-Liste, passend zur kurzen Richtung. Absteigend nach Hebel nach den bestehenden KO- und Produktprüfungen. Analyse-Kandidaten, keine Handelsfreigabe.</p>${rows.map((r,i)=>`<article style="border:1px solid #dce3ed;border-radius:12px;padding:12px;margin:10px 0;overflow-wrap:anywhere"><h4>Platz ${i+1} · ${esc(r.p.isin)}</h4><p>${esc(r.p.productDirection)} · <strong>Hebel ${fmt(r.p.leverage)}×</strong></p><p>Analysepreis ${esc(r.p.price)} · KO ${fmt(r.p.ko)} USD · Abstand ${fmt(r.evaluation.koDistancePct)} %</p><p class="small">${esc(r.sourceNote||'Originalquelle/Preiszeit nicht vollständig bestätigt')}</p><p class="small">${esc(r.warning||'Originalnachweise beim Produkt prüfen')} · ${esc((r.missing||[]).join(' · '))}</p><p><b>NICHT ALS DEGIRO-AUSFÜHRUNG BESTÄTIGT</b></p></article>`).join('')}${rows.length<2?'<p>Nur '+rows.length+' passende Kandidaten. Fehlende Plätze werden nicht mit ungeeigneten Produkten aufgefüllt.</p>':''}<button type="button" data-view="products">Produktnachweise öffnen</button></div>
 <div class="card"><h3>Rücksetzer und Ausstieg</h3><p><b>${esc(watch.action)}</b> · ${esc(watch.reason||'Einen tatsächlichen Einstieg unter Mein Trade erfassen.')}</p>${positive(watch.stop)?'<p>Zusätzliche Gold-Warnschwelle: '+fmt(watch.stop)+' USD. Nur Hinweis; bestehender Broker-Stop wird nicht geändert.</p>':''}<button type="button" data-view="trade">Mein Trade öffnen</button></div>`;
}
let input=null,host=null,watch={},history=[],lastKey='',lastAt=null;
function refresh(){
 if(!host)return;
 const now=Date.now();
 let state=analyze(input?.bundle,now);
 if(root.BobSession?.expired?.())state={ready:false,direction:'ABWARTEN',stage:'GESPERRT',reason:'Bitte erneut anmelden.'};
 if(state.ready&&lastAt!==null&&state.at<lastAt)state={ready:false,direction:'ABWARTEN',stage:'DATEN FEHLEN',reason:'Rückläufige Kurszeit; neuer aktueller Datensatz erforderlich.'};
 if(state.ready)lastAt=state.at;
 const rows=ranking(input?.products,state,input?.context||{},root.BobDegiro,now);
 let trade;try{trade=root.BobTradeSync?.current?.();}catch(_){}
 watch=monitor(watch,trade,state,now);
 const key=[state.direction,state.stage,watch.action].join('|');
 if(key!==lastKey){history.unshift({at:now,text:state.direction+' · '+state.stage+' · '+watch.action});history=history.slice(0,30);lastKey=key;}
 const html=markup(state,rows,watch,input?.context?.trend)+'<div class="card"><h3>Warnungsverlauf dieser Sitzung</h3>'+history.map(x=>'<p class="small">'+esc(new Date(x.at).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich'}))+' · '+esc(x.text)+'</p>').join('')+'</div>';
 if(host._riskHtml!==html){host.innerHTML=html;host._riskHtml=html;}
}
function update(snapshot){input=snapshot;refresh();}
function mount(panel){
 if(!panel||host)return;
 const intro=root.document.createElement('div');intro.className='card';
 intro.innerHTML='<p><b>Experimentelle Risikoanalyse · keine Echtgeldorders</b></p><p>Hohe Hebel verstärken Gewinne und Verluste. Die Regeln sind noch nicht als profitable Strategie bestätigt.</p><p><b>Betrieb:</b> Aktualisierung mit Bobs vorhandenen Kursdaten. Kein zugesicherter Sekundenstream. Zusätzliche Risiko-Warnungen gelten nur bei geöffneter, aktiver App; kein eigener Hintergrund-Push. Die bestehende Trade-Überwachung bleibt separat.</p><details><summary>Regeln, Kosten und Grenzen</summary><p>Vorwarnung aus laufendem Spot und 1-Minuten-Struktur. Bestätigung: zwei abgeschlossene Minutenkerzen über/unter einem vorher bekannten Niveau plus 0,15 ATR. Vorwarnung und Bestätigung können sich widersprechen.</p><p>Gewinnschutz: 1,5 Minuten-ATR vom besten seit Beobachtungsbeginn gesehenen Spot, nie lockerer als der bestehende Stop. Nach fünf Minuten ohne günstige Fortsetzung: Zeitwarnung. Neustart beginnt eine neue Beobachtung; vergangene Spitzen werden nicht erfunden.</p><p>Spread, Gebühren, Kursstellung und deine Reaktionszeit können den Vorteil aufheben. Die Rangliste belegt weder einen Nettogewinn noch einen aktuellen DEGIRO-Verkaufskurs. Emittenten-, Screenshot- und berechnete Preise bleiben Analysewerte.</p><p>Vor einem belastbaren Einsatz fehlen zeitlich getrennte Simulationen mit echten Produktkursen, Kosten und gemessener Push-/Reaktionsverzögerung. Beobachtete Warnungen sind keine ausgeführten Trades.</p></details>';
 host=root.document.createElement('div');host.id='bobRiskContent';host.setAttribute('aria-live','polite');panel.append(intro,host);refresh();
 root.setInterval(()=>{if(!root.document.hidden)refresh();},1000);
 root.document.addEventListener('visibilitychange',()=>{if(!root.document.hidden)refresh();});
}
const api={POLICY,analyze,ranking,monitor,markup,update,mount};root.BobRisk=api;
if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
