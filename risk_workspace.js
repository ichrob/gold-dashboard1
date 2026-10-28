/* Experimental risk analysis. Read-only: never sends orders or changes trade stops. */
(function(root){
'use strict';
const positive=x=>typeof x==='number'&&Number.isFinite(x)&&x>0;
const side=x=>['LONG','SHORT'].includes(x);
const POLICY={version:'risk-v1',spotMaxAgeMs:60000,confirmationAtr:.15,warningAtr:.5,trailingAtr:1.5,timeLimitMs:5*60000};
function analyze(bundle,now=Date.now()){
 const fail=reason=>({ready:false,direction:'ABWARTEN',stage:'DATEN FEHLEN',reason});
 const s=bundle?.spots,at=Date.parse(s?.spot_price_as_of);
 if(typeof s?.spot_price_as_of!=='string'||!/(?:Z|[+-]\d{2}:\d{2})$/i.test(s.spot_price_as_of)||s?.is_genuine_xauusd_spot!==true||s.spot_error||!positive(s.xaus)||!Number.isFinite(at)||at>now||now-at>POLICY.spotMaxAgeMs)return fail('Aktueller Gold-Spot mit Originalzeit fehlt.');
 const raw=bundle?.history?.bars_by_tf?.['1m'];
 if(!Array.isArray(raw))return fail('1-Minuten-Kerzen fehlen; kein schnelles Signal.');
 const bars=raw.filter(b=>b.isOpen!==true&&Number.isFinite(b.openTime)&&b.openTime+60000<=now).slice(-21);
 if(bars.length<21)return fail('Mindestens 21 abgeschlossene 1-Minuten-Kerzen benötigt.');
 if(bars.some((b,i)=>b.instrument!=='XAU/USD'||b.estimated===true||b.openTime%60000!==0||!['open','high','low','close'].every(k=>positive(b[k]))||b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close)||b.low>b.high||(i&&b.openTime-bars[i-1].openTime!==60000)))return fail('1-Minuten-Kerzen unplausibel oder lückenhaft.');
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
 if(trade.test===true)return {active:false,action:'SIMULATION',reason:'Testtrade bleibt in der bestehenden Simulation; hier ist kein tatsächlicher Einstieg bestätigt.'};
 if(previous?.id!==trade.tradeId||previous?.dir!==trade.dir)previous={};
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
// Same engine in browser and Node worker. Returned events become durable only
// after provider acceptance; failed sends are retried from the previous checkpoint.
function advance(previous,options,signal,now=Date.now()){
 const old=previous||{},state=JSON.parse(JSON.stringify(old)),events=[];
 state.version=POLICY.version;state.checkedAt=now;
 if(options?.enabled!==true)return {state:{version:POLICY.version,checkedAt:now,enabled:false},events};
 state.enabled=true;
 const fresh=signal?.ready===true&&positive(signal.at)&&signal.at<=now&&now-signal.at<60000;
 const monotonic=!positive(old.dataAt)||signal?.at>=old.dataAt;
 const checked=fresh&&monotonic?signal:{ready:false,reason:'Aktuelle, fortlaufende Originalkurszeit fehlt.'};
 state.signal=checked;
 if(checked.ready)state.dataAt=checked.at;
 state.watch=monitor(old.watch,options.tradeEnabled?options.trade:null,checked,now);
 function add(kind,title,body,channel){
  const expiresAt=Math.min(checked.at+60000,now+60000);
  events.push({title,body,tag:'bob-risk-'+channel,data:{kind:channel,eventKind:kind,riskOnly:true,
   url:'/#risk',direction:checked.direction,dataAt:checked.at,signalBarAt:checked.barAt,
   generatedAt:now,expiresAt,tradeId:channel==='trade'?options.trade?.tradeId:null,
   experimental:true,affectsApproval:false}});
 }
 if(checked.ready&&options.general===true&&options.entryAllowed===true){
  const key=checked.direction+':'+checked.stage;
  if(side(checked.direction)&&['VORWARNUNG','BESTÄTIGT'].includes(checked.stage)&&key!==old.announced){
   const cooldown=state.cooldowns||{};
   if(!positive(cooldown[key])||now-cooldown[key]>=120000){
    add('risk-'+(checked.stage==='BESTÄTIGT'?'confirmed':'warning'),'RISIKO · '+checked.direction+' · '+checked.stage,
     checked.reason+' Experimentelle Marktbeobachtung; keine Produktfreigabe oder Order.','general');
    state.announced=key;state.cooldowns={...cooldown,[key]:now};
   }
  }else if(checked.direction==='ABWARTEN'&&old.announced){
   add('risk-withdrawn','RISIKO · kurze Bewegung nicht mehr bestätigt',
    'Die zuletzt gemeldete kurze Richtung wird nicht mehr bestätigt. Keine Entwarnung für einen bestehenden Trade.','general');
   state.announced=null;
  }
 }
 const w=state.watch,prev=old.watch;
 if(checked.ready&&options.tradeEnabled===true&&w.active&&['AUSSTIEG PRÜFEN','ZEITGRENZE PRÜFEN','GEGENBEWEGUNG'].includes(w.action)&&
    (prev?.id!==w.id||old.announcedTradeAction!==w.action)){
  const kind=w.action==='AUSSTIEG PRÜFEN'?'risk-exit':w.action==='ZEITGRENZE PRÜFEN'?'risk-time':'risk-countermove';
  add(kind,'RISIKO · '+w.action,w.reason+(positive(w.stop)?' Zusätzliche Gold-Warnschwelle '+w.stop.toFixed(2)+' USD.':'')+' Keine automatische Verkaufsorder.','trade');
  state.announcedTradeAction=w.action;
 }
 if(w.action==='BEOBACHTEN')state.announcedTradeAction=null;
 if(!w.active||prev?.id!==w.id&&!events.some(e=>e.data.kind==='trade'))state.announcedTradeAction=null;
 if(events.length){state.history=[...(old.history||[]),...events.map(e=>({at:now,kind:e.data.eventKind,direction:checked.direction}))].slice(-30);}
 return {state,events};
}
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>positive(x)?x.toFixed(2):'—';
function markup(state,rows,watch,main){
 return `<div class="card"><h3>${esc(state.direction)} · ${esc(state.stage)}</h3><p>${esc(state.reason)}</p><p>Haupttrend: ${esc(main||'unbekannt')} · kurze Richtung separat${side(main)&&side(state.direction)&&main!==state.direction?' · GEGEN DEN HAUPTTREND':''}</p><p class="small">${state.ready?'Gold '+fmt(state.spot)+' USD · Originalzeit '+esc(new Date(state.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}))+' · '+state.ageSeconds+' s alt':'ABWARTEN: keine aktuelle Rangliste'}</p></div>
 <div class="card"><h3>Top 2 · hoher Hebel</h3><p>Aus deiner geladenen DEGIRO-Liste, passend zur kurzen Richtung. Absteigend nach Hebel nach den bestehenden KO- und Produktprüfungen. Analyse-Kandidaten, keine Handelsfreigabe.</p>${rows.map((r,i)=>`<article style="border:1px solid #dce3ed;border-radius:12px;padding:12px;margin:10px 0;overflow-wrap:anywhere"><h4>Platz ${i+1} · ${esc(r.p.isin)}</h4><p>${esc(r.p.productDirection)} · <strong>Hebel ${fmt(r.p.leverage)}×</strong></p><p>Analysepreis ${esc(r.p.price)} ${esc(r.p.quote?.currency||r.p.snapshot?.currency||'Währung unbestätigt')} · KO ${fmt(r.p.ko)} USD · Abstand ${fmt(r.evaluation.koDistancePct)} %</p><p class="small">${esc(r.sourceNote||'Originalquelle/Preiszeit nicht vollständig bestätigt')}</p><p class="small">${esc(r.warning||'Originalnachweise beim Produkt prüfen')} · ${esc((r.missing||[]).join(' · '))}</p><p><b>NICHT ALS DEGIRO-AUSFÜHRUNG BESTÄTIGT</b></p></article>`).join('')}${rows.length<2?'<p>Nur '+rows.length+' passende Kandidaten. Fehlende Plätze werden nicht mit ungeeigneten Produkten aufgefüllt.</p>':''}<button type="button" data-view="products">Produktnachweise öffnen</button></div>
 <div class="card"><h3>Rücksetzer und Ausstieg</h3><p><b>${esc(watch.action)}</b> · ${esc(watch.reason||'Einen tatsächlichen Einstieg unter Mein Trade erfassen.')}</p>${positive(watch.stop)?'<p>Zusätzliche Gold-Warnschwelle: '+fmt(watch.stop)+' USD. Nur Hinweis; bestehender Broker-Stop wird nicht geändert.</p>':''}<button type="button" data-view="trade">Mein Trade öffnen</button></div>`;
}
let remote=null,remoteAt=0,pushNote='Serverstatus noch nicht bestätigt.';
function server(result){
 remote=result;remoteAt=Date.now();renderPushState();refresh();
}
function renderPushState(){
 const box=root.document?.getElementById('bobRiskPushStatus'),button=root.document?.getElementById('bobRiskPushToggle');
 if(!box||!button)return;
 const pref=root.BobPush?.state?.()||{},enabled=pref.risk===true;
 button.textContent=enabled?'Risiko-Push ausschalten':'Risiko-Push einschalten';button.setAttribute('aria-pressed',String(enabled));
 const fresh=remote&&Date.now()-remoteAt<90000,checked=remote?.riskState?.checkedAt;
 box.textContent=!pref.serverRegistered?'Zuerst Gerät unter Push und Verbindung registrieren.':
  !fresh?pushNote:remote.riskEnabled!==enabled?'Einstellung am Server noch nicht bestätigt.':
  !enabled?'Risiko-Push ausgeschaltet.':
  !(pref.general||pref.trade)?'Servereinstellung gespeichert; Markt- oder Trade-Push muss eingeschaltet sein.':
  !Number.isFinite(checked)||checked>Date.now()||Date.now()-checked>90000?'Risiko-Push gespeichert; aktueller Hintergrunddurchlauf noch nicht bestätigt.':
  'Hintergrundprüfung: '+new Date(checked).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich'})+' · '+
  (remote.riskState.signal?.ready?'Kursdaten geprüft':'Daten eingeschränkt')+'. Versand ist kein bestätigter Handyempfang.';
}
async function togglePush(){
 const button=root.document.getElementById('bobRiskPushToggle');button.disabled=true;
 try{
  const pref=root.BobPush?.state?.()||{};
  if(!pref.serverRegistered)throw Error('Bitte zuerst Push unter Einstellungen registrieren.');
  if(!pref.risk&&!pref.general&&!pref.trade)throw Error('Bitte zuerst Marktbeobachtung oder Aktiver Trade unter Mein Trade einschalten.');
  if(typeof root.BobRiskPush?.set!=='function')throw Error('Push-Anbindung noch nicht geladen.');
  const enabled=!pref.risk;
  const ok=await root.BobRiskPush.set(enabled);
  if(!ok||remote?.riskEnabled!==enabled)throw Error('Server hat die Risiko-Einstellung nicht bestätigt. Erneut synchronisieren.');
  pushNote=enabled?'Risiko-Push gespeichert; erster Hintergrunddurchlauf ausstehend.':'Risiko-Push ausgeschaltet.';
 }catch(e){pushNote=e.message;remoteAt=0;}finally{button.disabled=false;renderPushState();}
}
let input=null,host=null,watch={},history=[],lastKey='',lastAt=null;
function refresh(){
 if(!host)return;
 renderPushState();
 const now=Date.now();
 let state=analyze(input?.bundle,now);
 if(root.BobSession?.expired?.())state={ready:false,direction:'ABWARTEN',stage:'GESPERRT',reason:'Bitte erneut anmelden.'};
 if(state.ready&&lastAt!==null&&state.at<lastAt)state={ready:false,direction:'ABWARTEN',stage:'DATEN FEHLEN',reason:'Rückläufige Kurszeit; neuer aktueller Datensatz erforderlich.'};
 if(state.ready)lastAt=state.at;
 const rows=ranking(input?.products,state,input?.context||{},root.BobDegiro,now);
 let trade;try{trade=root.BobTradeSync?.current?.();}catch(_){}
 const saved=remote?.riskState?.watch;
 if(root.BobPush?.state?.().risk===true&&saved&&trade?.active===true&&saved.id===trade.tradeId&&saved?.dir===trade?.dir&&positive(saved.stop)){
  // Restore the durable tighter boundary after reload, without changing the actual trade.
  if(watch.id!==saved.id||!positive(watch.stop)||
     (saved.dir==='LONG'?saved.stop>watch.stop:saved.stop<watch.stop))watch={...saved};
 }
 watch=monitor(watch,trade,state,now);
 const key=[state.direction,state.stage,watch.action].join('|');
 if(key!==lastKey){history.unshift({at:now,text:state.direction+' · '+state.stage+' · '+watch.action});history=history.slice(0,30);lastKey=key;}
 const html=markup(state,rows,watch,input?.context?.trend)+'<div class="card"><h3>Warnungsverlauf dieser Sitzung</h3>'+history.map(x=>'<p class="small">'+esc(new Date(x.at).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich'}))+' · '+esc(x.text)+'</p>').join('')+'</div>';
 if(host._riskHtml!==html){host.innerHTML=html;host._riskHtml=html;}
}
function update(snapshot){input=snapshot;refresh();}
let paperBusy=false;
async function refreshPaper(){
 const el=root.document?.getElementById('bobRiskPaper');
 if(!el||paperBusy||root.document.hidden)return;
 paperBusy=true;
 try{
  const response=await root.fetch('/api/risk-paper',{cache:'no-store'});
  if(!response.ok)throw Error('Simulation nicht erreichbar oder Anmeldung erforderlich.');
  const data=await response.json();if(!data.accounts)throw Error('Simulation noch nicht gestartet.');
  const euros=x=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(2)+' €':'unbewertet';
  const checked=data.checkedAt, fresh=Number.isFinite(checked)&&checked<=Date.now()&&Date.now()-checked<=120000;
  el.innerHTML='<h3>Virtuelles Testkonto · 2.000 €</h3><p>'+ (fresh?'Letzte Prüfung: ':'Keine aktuelle Prüfung bestätigt: ')+esc(checked?new Date(checked).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch offen')+'</p><p class="small">Drei unabhängige Vergleichskonten mit je 2.000 €; maximal 1.000 € inklusive Einstiegsgebühr je Position. Einstieg nur BESTÄTIGT, Produkt auf Platz 1. Keine Orders. 0/30/60 Sekunden zusätzliche Wartezeit, tatsächliche Ausführung erst beim nächsten passenden beobachteten Kurs.</p>'+Object.values(data.accounts).map(a=>{
   const p=a.position;
   return '<article><h4>'+esc(a.delaySeconds)+' s Verzögerung</h4><p>Modell-Kontowert: <b>'+euros(a.equity)+'</b> · frei '+euros(a.cash)+'</p><p>Realisierter Modellerfolg: '+euros(a.realized)+' · Rendite auf Startkapital '+(a.realized/2000*100).toFixed(2)+' %</p><p>'+a.closed+' abgeschlossen · '+a.incomplete+' davon mit Beobachtungslücken · Trefferquote '+(a.closed?(100*a.wins/a.closed).toFixed(1)+' %':'noch offen')+' · größter beobachteter Rückgang '+euros(a.maxDrawdown)+'</p><p>'+esc(a.reason)+'</p>'+(p?'<p>Virtuell: '+esc(p.direction)+' · '+esc(p.isin)+' · '+p.units+' Stück</p>':'')+'<p class="small">'+(a.reviewReady?'100 lückenfrei beobachtete Abschlüsse erreicht; erste Auswertung möglich, kein Profitabilitätsnachweis.':'Erste Auswertung ab 100 Abschlüssen ohne dokumentierte Beobachtungslücken.')+'</p><details><summary>Letzte Abschlüsse und Kursbelege</summary>'+a.recent.map(c=>'<p>'+esc(c.isin)+' · '+esc(c.direction)+' · '+euros(c.modelNet)+' · '+esc(c.exitReason)+'<br>Brief '+esc(c.entryQuote.ask)+' ('+esc(c.entryQuote.askAt||c.entryQuote.quoteAt)+') → Geld '+esc(c.exitQuote.bid)+' ('+esc(c.exitQuote.bidAt||c.exitQuote.quoteAt)+')<br>'+esc(c.entryQuote.source)+' / '+esc(c.exitQuote.source)+(c.dataGap?' · Datenlücke':'')+'</p>').join('')+'</details></article>';
  }).join('')+'<p class="small"><b>Kostenmodell:</b> beobachteter Spread plus angenommene 5 € je Kauf/Verkauf. Finanzierung, FX und zusätzliche Slippage nicht vollständig belegt. Modellnetto ist kein bestätigter DEGIRO-Nettogewinn. CHF-Umrechnungs-/Chartkurse werden hier ausgeschlossen. KO ohne Abrechnung bleibt unbewertet. Rückgang nur an beobachteten Zeitpunkten; fehlende Zwischenkurse können Verluste verbergen. Ergebnisse mit Datenlücken sind in den Kontosummen enthalten und separat gezählt.</p>';
 }catch(e){el.textContent='2.000-€-Simulation: '+e.message;}finally{paperBusy=false;}
}
function mount(panel){
 if(!panel||host)return;
 const paper=root.document.createElement('div');paper.className='card';paper.id='bobRiskPaper';paper.textContent='2.000-€-Simulation wird geladen …';panel.append(paper);refreshPaper();root.setInterval(refreshPaper,30000);
 const intro=root.document.createElement('div');intro.className='card';
 intro.innerHTML='<p><b>Experimentell · keine Echtgeldorders</b></p><p class="small">Lokale Ansicht plus zuschaltbarer Hintergrund-Push. Prüfung mit Bobs vorhandenen Kursdaten, normalerweise etwa alle 30 Sekunden; kein zugesicherter Sekundenstream.</p><details><summary>Regeln, Kosten und Grenzen</summary><p>Hohe Hebel verstärken Gewinne und Verluste. Die Regeln sind noch nicht als profitable Strategie bestätigt. Die bestehende Trade-Überwachung bleibt separat.</p><p>Vorwarnung aus laufendem Spot und 1-Minuten-Struktur. Bestätigung: zwei abgeschlossene Minutenkerzen über/unter einem vorher bekannten Niveau plus 0,15 ATR. Vorwarnung und Bestätigung können sich widersprechen.</p><p>Gewinnschutz: 1,5 Minuten-ATR vom besten seit Beobachtungsbeginn gesehenen Spot, nie lockerer als der bestehende Stop. Nach fünf Minuten ohne günstige Fortsetzung: Zeitwarnung. Neustart beginnt eine neue Beobachtung; vergangene Spitzen werden nicht erfunden.</p><p>Spread, Gebühren, Kursstellung und deine Reaktionszeit können den Vorteil aufheben. Die Rangliste belegt weder einen Nettogewinn noch einen aktuellen DEGIRO-Verkaufskurs. Emittenten-, Screenshot- und berechnete Preise bleiben Analysewerte.</p><p>Vor einem belastbaren Einsatz fehlen zeitlich getrennte Simulationen mit echten Produktkursen, Kosten und gemessener Push-/Reaktionsverzögerung. Beobachtete Warnungen sind keine ausgeführten Trades.</p></details>';
 const push=root.document.createElement('div');push.className='card';push.innerHTML='<h3>Risiko-Push</h3><p id="bobRiskPushStatus" role="status"></p><button id="bobRiskPushToggle" type="button">Risiko-Push einschalten</button><p class="small">Marktbeobachtung erhält Vorwarnung und Bestätigung; Aktiver Trade erhält Gegenbewegungs- und Ausstiegswarnungen. Nur bei eingeschaltetem jeweiligem Push-Kanal. Keine Orders.</p><button type="button" data-view="settings">Push und Verbindung</button>';panel.append(push);push.querySelector('#bobRiskPushToggle').addEventListener('click',togglePush);
 host=root.document.createElement('div');host.id='bobRiskContent';host.setAttribute('aria-live','polite');panel.insertBefore(intro,push);panel.insertBefore(host,push);refresh();
 root.setInterval(()=>{if(!root.document.hidden)refresh();},1000);
 root.document.addEventListener('visibilitychange',()=>{if(!root.document.hidden){refresh();refreshPaper();}});
 root.navigator?.serviceWorker?.addEventListener('message',event=>{
  if(event.data?.type==='BOB_PUSH_CLICK'&&event.data.data?.url==='/#risk')
   root.document.querySelector('#bobNavigation [data-view="risk"]')?.click();
 });
}
const api={POLICY,analyze,ranking,monitor,advance,markup,update,mount,server};root.BobRisk=api;
if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof window==='undefined'?globalThis:window);
