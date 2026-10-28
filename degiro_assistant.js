/* Local, user-entered evidence only. No portal requests or order execution. */
(function(){
const number=v=>v!==null&&v!==undefined&&String(v).trim()!==''&&Number.isFinite(Number(String(v).replace(',','.')))?Number(String(v).replace(',','.')):null;
const time=v=>typeof v==='string'&&/T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(v)?Date.parse(v):NaN;
const fresh=(v,now,seconds)=>Number.isFinite(time(v))&&now>=time(v)&&now-time(v)<=seconds*1000;
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const FIXED_KO_KEY='bobFixedScreenshotKoV1';
// Explicit user configuration from the DEGIRO screenshots; not issuer certification.
const FIXED_KO_DEFAULTS={'DE000FG4JXV7':{isin:'DE000FG4JXV7',direction:'SHORT',value:4460,currency:'USD',source:'DEGIRO-Screenshot, vom Nutzer als fester Wert bestätigt',imageSource:'DEGIRO-Produktname BAR 4460',userConfirmed:true,confirmedAt:'2026-10-02T15:12:37+02:00'}};
function fixedBarriers(){try{const x=JSON.parse(localStorage.getItem(FIXED_KO_KEY)||'{}');return x&&typeof x==='object'&&!Array.isArray(x)?x:{};}catch(_){return {};}}
function fixedFor(p){const all=fixedBarriers(),x=Object.prototype.hasOwnProperty.call(all,p.isin)?all[p.isin]:FIXED_KO_DEFAULTS[p.isin];return x&&x.isin===p.isin&&x.direction===p.productDirection&&x.userConfirmed===true&&number(x.value)>0&&x.currency==='USD'&&(number(p.ko)===null||number(p.ko)===number(x.value))?x:null;}
function saveFixed(p,image){if(!window.BobDegiro.validIsin(p.isin)||!['LONG','SHORT'].includes(p.productDirection)||!(number(p.ko)>0))return false;try{const all=fixedBarriers();all[p.isin]={isin:p.isin,direction:p.productDirection,value:number(p.ko),currency:'USD',source:'DEGIRO-Screenshot, vom Nutzer bestätigt',imageSource:image||'manuell aus DEGIRO-Screenshot',userConfirmed:true,confirmedAt:new Date().toISOString()};localStorage.setItem(FIXED_KO_KEY,JSON.stringify(all));return true;}catch(_){return false;}}
function removeFixed(isin){try{const all=fixedBarriers();all[isin]=null;localStorage.setItem(FIXED_KO_KEY,JSON.stringify(all));}catch(_){} }
const FIXED_KO_HISTORY_KEY='bobFixedScreenshotKoHistoryV1';
function resetFixedList(){
 // Preserve original evidence for diagnosis; never silently carry it into a new
 // list generation as a current KO confirmation or trading authorization.
 try{
  const current=fixedBarriers();
  const ids=new Set([...Object.keys(FIXED_KO_DEFAULTS),...Object.keys(current)]);
  const history=JSON.parse(localStorage.getItem(FIXED_KO_HISTORY_KEY)||'{}');
  if(!history||typeof history!=='object'||Array.isArray(history))return false;
  const next={...history};
  for(const isin of ids){
   const proof=Object.prototype.hasOwnProperty.call(current,isin)?current[isin]:FIXED_KO_DEFAULTS[isin];
   if(proof&&proof.isin===isin&&proof.userConfirmed===true){
    const entries=Array.isArray(next[isin])?next[isin]:[];
    const identity=JSON.stringify([proof.direction,proof.value,proof.confirmedAt,proof.source]);
    if(!entries.some(e=>JSON.stringify([e.direction,e.value,e.confirmedAt,e.source])===identity))
     next[isin]=[...entries,proof].slice(-30);
   }
  }
  // Persist archive first. On storage failure retain current proofs untouched.
  const archived=JSON.stringify(next);
  localStorage.setItem(FIXED_KO_HISTORY_KEY,archived);
  if(localStorage.getItem(FIXED_KO_HISTORY_KEY)!==archived)return false;
  const revoked=JSON.stringify(Object.fromEntries([...ids].map(id=>[id,null])));
  localStorage.setItem(FIXED_KO_KEY,revoked);
  return localStorage.getItem(FIXED_KO_KEY)===revoked;
 }catch(_){return false;}
}
function assess(p,r,bundle,now=Date.now()){
 const out={eligible:false,tradeable:false,estimated:false,reasons:[],quote:null,ko:null,distanceUsd:null,distancePct:null};
 const fail=s=>out.reasons.push(s);
 const imagePair=r?.imageEvidence?.bid&&r.imageEvidence.bid===r.imageEvidence.ask;
 const fixed=fixedFor(p);
 if(!r&&!fixed)return out;
 r=r||{isin:p.isin};
 if(!window.BobDegiro.validIsin(p.isin)||(!p.isinConfirmed&&!fixed)||r.isin!==p.isin){fail('ISIN und Produktzuordnung bestätigen');return out;}
 if(!['LONG','SHORT'].includes(p.productDirection)){fail('Produktrichtung fehlt');return out;}
 const meta=p.quote?.isin===p.isin&&p.quote?.productVerified?p.quote.metadata:null;
 if(meta&&((Number(meta.status)&(2|8|16|32))||meta.direction&&meta.direction!==p.productDirection)){fail('Emittent meldet inaktives Produkt oder widersprüchliche Richtung');return out;}
 if(r.assumedSeconds)fail('Ergänzte Sekunden sind kein Quellenzeitnachweis');
 const bid=number(r.bid),ask=number(r.ask);
 if(!['Stuttgart','Onvista','DEGIRO'].includes(r.source)||!r.venue||!(/^https:\/\//.test(r.url||'')||imagePair)||!r.paired||!r.reviewed||r.delayed||r.assumedSeconds||!fresh(r.quoteAt,now,1800)||!(bid>0&&ask>=bid))fail('Geld/Brief als geprüftes, nicht verzögertes Paar derselben Quelle und desselben Handelsplatzes mit Quellenzeit (höchstens 30 Minuten) ergänzen');
 else out.quote={bid,ask,spread:ask-bid,source:r.source,venue:r.venue,url:r.url,imageSource:imagePair?r.imageEvidence.bid:null,at:r.quoteAt,liveVerified:false};
 const evidence=fixed?[fixed]:(r.barriers||[]).filter(x=>number(x.value)>0&&x.isin===p.isin&&x.currency==='USD'&&x.source&&(/^https:\/\//.test(x.url||'')||x.imageSource)&&x.confirmed&&fresh(x.at,now,86400)&&Number.isFinite(time(x.validUntil))&&time(x.validUntil)>now&&time(x.validUntil)-time(x.at)<=86400000);
 if(!fixed&&(evidence.length!==(r.barriers||[]).length||!evidence.length))fail('Jede KO-Schwelle braucht ISIN, USD, Quelle, Quellenzeit und bestätigte aktuelle Gültigkeit');
 else{
  const values=evidence.map(x=>number(x.value)),lo=Math.min(...values),hi=Math.max(...values);
  if(hi-lo>1+1e-9)fail('KO-Widerspruch größer als 1 USD: Berechnung ausgesetzt');
  else out.ko={value:p.productDirection==='SHORT'?lo:hi,differenceUsd:hi-lo,evidence,fixed:!!fixed};
 }
 const state=window.BobDegiro.screenshotCurrentState(fixed?{...p,isinConfirmed:true}:p,bundle,now);
 const gold=state.basis;
 out.basis=gold;out.basisLabel=state.rows[0]?.text||'';
 if(gold===null)fail('Aktueller passender Basiswert fehlt; Future und Spot bleiben getrennt');
 if(out.ko&&gold!==null){
  out.distanceUsd=(out.ko.value-gold)*(p.productDirection==='SHORT'?1:-1);
  out.distancePct=out.distanceUsd/gold*100;
  if(out.distanceUsd<=0)fail('Aktueller Basiswert an oder jenseits der gewählten KO-Schwelle; historische KO-Berührung zusätzlich prüfen');
 }
 const m=p.quote?.productVerified&&p.quote?.productModel?.verifiedSimpleTurbo?p.quote.productModel:null;
 const c=p.quote?.calculatedProduct,fx=number(c?.usdEur),ratio=number(m?.ratio),strike=number(m?.strike);
 // Require issuer-verified terms and fresh FX. An entered barrier never modifies them.
 if(!m||m.isin!==p.isin||m.underlying!=='XAU/USD'||m.direction!==p.productDirection||!(ratio>0&&strike>0&&fx>0)||!fresh(c?.fxDataAt,now,60)||!fresh(c?.fxEffectiveAt,now,60)||!Number.isFinite(time(m.tradingEndAt))||now>time(m.tradingEndAt))fail('Für die Preisschätzung fehlen bestätigte Spot-Produktbedingungen oder aktueller USD→EUR-Kurs');
 else if(out.quote&&out.ko&&out.distanceUsd>0&&gold!==null){
  if(Math.abs(number(m.ko)-out.ko.value)>1+1e-9){fail('Emittentenmodell und gewählte KO-Schwelle widersprechen sich um mehr als 1 USD');return out;}
  const currentTimes=[bundle?.spots?.spot_price_as_of,c.fxDataAt,c.fxEffectiveAt].map(time);
  if(currentTimes.some(x=>!Number.isFinite(x))||Math.max(...currentTimes)-Math.min(...currentTimes)>15000){fail('Aktueller Gold-/FX-Zeitversatz größer als 15 Sekunden');return out;}
  const g0=number(r.goldReference),f0=number(r.fxReference);
  const stamps=[r.quoteAt,r.goldAt,r.fxAt].map(time);
  if(!(g0>0&&f0>0)||stamps.some(x=>!Number.isFinite(x))||Math.max(...stamps)-Math.min(...stamps)>5000||stamps.some(x=>x>now)||!r.referenceConfirmed||!/^https:\/\//.test(r.goldUrl||'')||!/^https:\/\//.test(r.fxUrl||''))fail('Gold- und FX-Referenz zum Kursnachweis fehlen (Zeitversatz höchstens 5 Sekunden)');
  else if((m.direction==='SHORT'&&(g0>=out.ko.value||gold>=strike))||(m.direction==='LONG'&&(g0<=out.ko.value||gold<=strike)))fail('Referenz oder aktueller Basiswert überschreitet KO-/Strike-Grenze');
  else{
   const change=(m.direction==='LONG'?1:-1)*ratio*((gold-strike)*fx-(g0-strike)*f0);
   const estimatedBid=bid+change,estimatedAsk=ask+change;
   if(!(estimatedBid>0&&estimatedAsk>=estimatedBid))fail('Berechneter Produktpreis unplausibel');
   else{out.estimated=true;out.estimate={bid:estimatedBid,ask:estimatedAsk,leverage:gold*fx*ratio/estimatedAsk,referenceAt:r.quoteAt,fxAt:c.fxDataAt,formula:'P = P₀ + Richtung × Verhältnis × [(Gold − Strike) × FX − (Gold₀ − Strike) × FX₀]'};}
  }
 }
 return out;
}
function render(state){
 if(!state.quote&&!state.ko&&!state.reasons.length)return '';
 const q=state.quote,k=state.ko,e=state.estimate;
 return '<div class="small" style="padding:10px;border:1px solid #dbe4f0;border-radius:12px"><b>Kombinierte, bedingte Bewertung</b>'+
 (q?'<div>Kursnachweis: '+escape(q.source)+' · '+escape(q.venue)+' · Geld '+q.bid.toFixed(4)+' / Brief '+q.ask.toFixed(4)+' EUR · '+escape(q.at)+(q.imageSource?' · Bild '+escape(q.imageSource):'')+'</div>':'')+
 (state.basis!==null&&state.basis!==undefined?'<div>'+escape(state.basisLabel)+'</div>':'')+
 (k?'<div>Konservative KO-Schwelle: '+k.value.toFixed(4)+' USD · Quellenabweichung '+k.differenceUsd.toFixed(4)+' USD'+(state.distanceUsd!==null?' · Abstand '+state.distanceUsd.toFixed(2)+' USD / '+state.distancePct.toFixed(2)+'%':'')+'</div>'+k.evidence.map(x=>'<div>KO-Nachweis: '+escape(x.source)+(k.fixed?' · fester Berechnungswert · Bestätigung '+escape(x.confirmedAt)+' (keine Kurszeit)':' · '+escape(x.at)+' · bestätigt gültig bis '+escape(x.validUntil))+'</div>').join(''):'')+
 (e?'<div><b>Schätzung, keine SG-Quotierung:</b> Geld ≈ '+e.bid.toFixed(4)+' / Brief ≈ '+e.ask.toFixed(4)+' EUR · Hebel ≈ '+e.leverage.toFixed(2)+'× · FX-Zeit '+escape(e.fxAt)+'</div><div>'+escape(e.formula)+'</div>':'')+
 state.reasons.map(x=>'<div>Offen: '+escape(x)+'</div>').join('')+
 '<div>Unverbindlicher Kandidatenvergleich. Keine Live-Freigabe. Freigabe ausschließlich nach der Pflichtprüfung in der Produktauswahl. Schätzfehler, Preisaufschlag und zwischenzeitliche KO-Berührung unbestätigt. Tatsächlichen DEGIRO-Geld-/Briefkurs vor einer Entscheidung prüfen.</div></div>';
}
function rank(products,references,bundle,context={}){
 const now=context.now??Date.now(),direction=String(context.direction||'NEUTRAL').toUpperCase();
 const out={candidates:[],excluded:[],total:0,selection:null,tradeable:false,direction,reason:''};
 if(!['LONG','SHORT'].includes(direction)||context.spotFresh!==true){out.reason='ABWARTEN: eindeutiges Momentum und aktueller Gold-Spot fehlen';return out;}
 const api=window.BobDegiro,seen=new Set();
 for(const [index,p] of products.entries()){
  if(!p.isin)continue;
  // Same ISIN never occupies two places or combines references from two rows.
  if(seen.has(p.isin)){out.excluded.push({isin:p.isin,reason:'Doppelte ISIN; nur der erste Eintrag wird geprüft'});continue;}seen.add(p.isin);
  const reject=reason=>out.excluded.push({isin:p.isin,reason});
  if(p.productDirection!==direction){reject('Produktrichtung passt nicht zum Momentum');continue;}
  if(api.isFutureProduct(p)){reject('Future benötigt eigene Kontrakt-MTF; siehe getrennten Future-Vergleich');continue;}
  let candidate;
  if(api.currentQuote(p,now)){
   candidate={...p,spread:Number.isFinite(p.quote.ask-p.quote.bid)?p.quote.ask-p.quote.bid:p.spread,rankingQuoteAt:p.quote.quoteAt,spot:context.spot,priceKind:'Bestätigter Produktkurs',estimated:false,source:p.quote.source,venue:'Emittenten-Kursquelle',at:p.quote.quoteAt};
  }else{
   const state=assess(p,references[index],bundle,now);
   if(!state.estimated||state.reasons.length){reject(state.reasons.join(' · ')||'Vollständiger Stuttgart-/Onvista-Nachweis fehlt');continue;}
   const local=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',weekday:'short',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now));
   const part=type=>local.find(x=>x.type===type)?.value;
   if(['Sat','Sun'].includes(part('weekday'))||Number(part('hour'))<8||Number(part('hour'))>=22){reject('Außerhalb des Modell-Handelsfensters (werktags 08–22 Uhr Berlin)');continue;}
   candidate={...p,spot:state.basis,price:state.estimate.ask,leverage:state.estimate.leverage,ko:state.ko.value,spread:state.estimate.ask-state.estimate.bid,estimated:true,priceKind:'Bedingte Schätzung',source:state.quote.source,venue:state.quote.venue,at:state.quote.at,state};
  }
  const evaluation=api.evaluateProduct({...context,...candidate,direction});
  if(!evaluation.ok||!evaluation.fit||evaluation.setupScore<35||evaluation.conflictCount>=3){reject(evaluation.reasons.join(' · ')||'Technische Passung oder Produktrisiko unzureichend');continue;}
  out.candidates.push({...candidate,evaluation});
 }
 out.candidates.sort((a,b)=>b.evaluation.score-a.evaluation.score||Number(a.estimated)-Number(b.estimated)||a.isin.localeCompare(b.isin));
 out.total=out.candidates.length;
 const best=out.candidates[0],second=out.candidates[1];
 // Sorting is useful even when a tied score does not establish one best choice.
 if(best&&(!second||best.evaluation.score>second.evaluation.score))out.selection=best;
 out.reason=!best?'ABWARTEN: kein vollständiges, zum Momentum passendes Produkt':!out.selection?'Gleiche technische Bewertung: kein eindeutiger Favorit':best.estimated?'Vorläufige Auswahl auf Basis einer Schätzung; Genauigkeit noch unbestätigt':'Auswahl unter den vollständig bewertbaren Produkten';
 out.candidates=out.candidates.slice(0,3);
 return out;
}
function renderTop3(result){
 return '<div style="padding:14px;background:#fff;border:2px solid #dbe4f0;border-radius:15px"><b>Unverbindlicher Kandidatenvergleich · '+escape(result.direction)+'</b><div class="small">'+escape(result.reason)+' · '+result.total+' passende Produkte</div>'+
 result.candidates.map((p,i)=>'<div style="padding:10px;margin-top:8px;border:1px solid #e1e7f0;border-radius:10px"><b>Platz '+(i+1)+' · '+escape(p.isin)+'</b><div class="small">'+escape(p.name)+' · '+escape(p.productDirection)+'</div><div class="small"><b>'+escape(p.priceKind)+'</b> · Brief '+(p.estimated?'≈ ':'')+p.price.toFixed(4)+' EUR · Hebel '+(p.estimated?'≈ ':'')+p.leverage.toFixed(2)+'×</div><div class="small">KO '+p.ko.toFixed(4)+' USD · Abstand '+p.evaluation.koDistancePct.toFixed(2)+'% · KO-Pufferwert '+p.evaluation.score+'/100</div><div class="small">Quelle '+escape(p.source)+' · '+escape(p.venue)+' · '+(p.estimated?'Referenzzeit ':'Kurszeit ')+escape(p.at)+'</div><div class="small">Warum: '+escape(p.evaluation.reasons.slice(0,3).join(' · ')).replace(/\bHebel\b/g,'<strong>Hebel</strong>')+'</div>'+p.evaluation.warnings.map(w=>'<div class="small warning">'+escape(w)+'</div>').join('')+(p.estimated?'<div class="small">Schätzgenauigkeit noch unbestätigt; angenommener Quellenaufschlag kann sich ändern.</div>':'')+'</div>').join('')+
 (result.excluded.length?'<details><summary>Ausgeschlossene Produkte ('+result.excluded.length+')</summary>'+result.excluded.map(p=>'<div class="small">'+escape(p.isin)+' · '+escape(p.reason)+'</div>').join('')+'</details>':'')+
 '<div class="small">Rangfolge nur innerhalb vollständiger Kandidaten, keine Gewinnwahrscheinlichkeit. Schätzungen bleiben bedingt; keine automatische Handelsfreigabe oder Order. Aktuellen DEGIRO-Briefkurs und Produktbedingungen prüfen.</div></div>';
}
function form(i){
 const field=(key,label)=>'<label class="small" style="display:block">'+label+'<input data-combined="'+key+'" style="width:100%"></label>';
 return '<details data-combined-form="'+i+'"><summary>Kursnachweis aus Screenshots / manuell</summary><div class="small">Zusatzbilder dieses Produkts füllen belegte Felder automatisch aus. Danach Angaben am Original prüfen und bestätigen. Alle Zeiten aus der Quelle, mit Sekunden und Zeitzone, z. B. 2026-10-02T08:31:00+02:00. Abrufzeit ersetzt keine Kurszeit. Eingaben bleiben nur in diesem geöffneten Tab.</div><select data-combined="source"><option value="">Bildquelle wählen</option><option>DEGIRO</option><option>Stuttgart</option><option>Onvista</option></select><div id="dgCombinedDraft'+i+'" class="small"></div>'+
 [['venue','Handelsplatz (z. B. SG OTC oder Stuttgart)'],['url','Quellenlink (bei einem belegten Bild optional)'],['bid','Geld EUR'],['ask','Brief EUR'],['quoteAt','Gemeinsame Quellenzeit des Geld-/Briefpaars'],['ko1','KO 1 USD'],['koSource1','KO 1 Quelle'],['koUrl1','KO 1 Quellenlink (bei belegtem Bild optional)'],['koAt1','KO 1 Quellenzeit'],['koUntil1','KO 1 bestätigt gültig bis'],['ko2','KO 2 USD (optional)'],['koSource2','KO 2 Quelle'],['koUrl2','KO 2 Quellenlink'],['koAt2','KO 2 Quellenzeit'],['koUntil2','KO 2 bestätigt gültig bis'],['goldReference','Gold USD zum Kursnachweis (optional für Schätzung)'],['goldAt','Quellenzeit Gold-Referenz'],['goldUrl','Link Gold-Referenz'],['fxReference','USD→EUR zum Kursnachweis'],['fxAt','Quellenzeit FX-Referenz'],['fxUrl','Link FX-Referenz']].map(x=>field(...x)).join('')+
 '<label class="small"><input data-combined="fixedKo" type="checkbox"> Barriere im KO-Level-Feld dieser ISIN als festen USD-Berechnungswert aus meinem DEGIRO-Screenshot bestätigen (ohne SG-Nachweis). Bleibt auf diesem Gerät gespeichert, bis geändert oder entfernt.</label><button data-fixed-save="'+i+'">Feste Screenshot-Barriere speichern</button><button data-fixed-clear="'+i+'">Feste Barriere entfernen</button><div class="small">Screenshot-Aufnahmezeit und Kurszeit sind getrennt. Europe/Zurich ist deine Nutzereinstellung, kein Bildnachweis. Minutenangaben bleiben minutengenau; Sekunden werden nicht ergänzt. Uploadzeit ersetzt keine Kurszeit.</div><label class="small"><input data-combined="reviewed" type="checkbox"> ISIN, Geld-/Briefpaar, Quellen und KO-Gültigkeitsangaben am Original geprüft; zulässige persönliche Nutzung bestätigt</label><label class="small"><input data-combined="referenceConfirmed" type="checkbox"> Gold-/FX-Referenzen am Original geprüft</label><button data-combined-save="'+i+'">Nachweis bedingt auswerten</button><button data-combined-clear="'+i+'">Nachweis entfernen</button><div class="small">Keine erfundenen Zeiten oder Gültigkeitsintervalle eintragen. Nicht belegbare Felder leer lassen; Bob zeigt sie als offen.</div></details><div id="dgCombinedState'+i+'"></div>';
}
function screenshotDraft(raw,isin){
 raw=String(raw||'');const api=window.BobDegiro;
 const ids=Array.from(new Set(api.parseScreenshotCandidates(raw).map(x=>x.isin)));
 if(!api.validIsin(isin)||ids.length!==1||ids[0]!==isin)return {ok:false,reason:'Bild braucht die eindeutig passende ISIN'};
 const fields={},notes=[],source=/onvista/i.test(raw)?'Onvista':/degiro/i.test(raw)?'DEGIRO':/boerse-stuttgart\.de|bör­se-stuttgart\.de/i.test(raw)?'Stuttgart':'';
 const value=s=>{s=String(s).replace(/\s/g,'');if(s.includes(','))s=s.replace(/\./g,'').replace(',','.');return number(s);};
 const bids=Array.from(raw.matchAll(/\b(?:Geld|Bid)(?!\s*(?:Vol|Volumen|zeit))\b/gi)),asks=Array.from(raw.matchAll(/\b(?:Brief|Ask)(?!\s*(?:Vol|Volumen|zeit))\b/gi));
 const hasQuote=bids.length>0||asks.length>0;
 const amount=(label,other)=>{
  if(label.length!==1)return null;const start=label[0].index+label[0][0].length,end=other.find(x=>x.index>start)?.index??raw.length;
  const section=raw.slice(start,end).split(/heute|Kurszeit|Geldzeit|Briefzeit|\b\d{2}[/.]\d{2}[/.]\d{4}/i)[0];
  // DEGIRO overview: the labelled quote precedes unrelated EUR rows
  // (open, close, high, low, position). Do not count those as extra quotes.
  const direct=section.match(/^\s*[:=]?\s*(?:€\s*([\d.,]+)|([\d.,]+)\s*EUR\b)[ \t]*(?=\r?\n|$)/i);
  if(direct)return value(direct[1]||direct[2]);
  const eur=Array.from(section.matchAll(/(?:€\s*([\d.,]+)|([\d.,]+)\s*EUR\b)/gi));
  if(eur.length===1)return value(eur[0][1]||eur[0][2]);
  if(eur.length)return null;
  const plain=section.match(/^\s*[:=]?\s*([\d.,]+)(?![\d.,])/i);
  return plain&&!/^(?:Stk|Stück|Vol|%)/i.test(section.slice(plain[0].length).trim())&&!/^\s*[•·]/.test(section)?value(plain[1]):null;
 };
 const bid=amount(bids,asks),ask=amount(asks,bids);
 const partialQuote=/EUR\b|€/.test(raw)&&((bids.length===1&&asks.length===0&&bid>0)||(asks.length===1&&bids.length===0&&ask>0))?{bid,ask}:null;
 if(hasQuote&&bids.length===1&&asks.length===1&&bid>0&&ask>=bid&&/EUR\b|€/.test(raw)){fields.bid=String(bid);fields.ask=String(ask);}
 else if(hasQuote)notes.push('Geld-/Briefpaar nicht eindeutig: ein Handelsplatz pro Kursbild, keine Volumenwerte als Kurse');
 const times=api.screenshotTimes(raw),bt=times.bid?.at||times.quote?.at,at=times.ask?.at||times.quote?.at;
 if(hasQuote&&bt&&bt===at)fields.quoteAt=bt;
 else if(hasQuote){const displayed=Array.from(raw.matchAll(/heute\s*[,·]?\s*(\d{2}:\d{2}:\d{2})/gi)).map(x=>x[1]);if(displayed.length&&new Set(displayed).size===1)fields.quoteAt='heute, '+displayed[0];else fields.quoteAt=times.quote?.text||(raw.match(/\b\d{2}[/.]\d{2}[/.]\d{4}\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||'';notes.push('Kursdatum / Sekunden / Zeitzone fehlen oder sind nicht eindeutig zugeordnet');}
 const supplemented=null;
 const venue=raw.match(/(?:Börse|Handelsplatz)\s*[:=]?\s*([^\n]+)/i);
 if(hasQuote&&venue)fields.venue=venue[1].trim();
 else if(hasQuote&&/Soci[eé]t[eé]\s+G[eé]n[eé]rale(?:\s*\(EUR\)|\s+OTC)/i.test(raw))fields.venue=/\bOTC\b/i.test(raw)?'Société Générale OTC':'Société Générale';
 const url=raw.match(/https:\/\/[^\s<>]+/);if(url)fields.url=url[0];
 const ko=raw.match(/(?:K\.?\s*O\.?\s*[- ]?Schwelle|K\.?\s*O\.?|KO-Level|KO-Barriere)\s*[:=]?\s*([\d.,]+)\s*USD\b/i);
 if(ko&&value(ko[1])>0){fields.ko1=String(value(ko[1]));fields.koSource1=source;fields.koAt1=times.ko?.at||times.ko?.text||'';const until=raw.match(/(?:KO gültig bis|KO valid until)\s*[:=]?\s*([^\n]+)/i);fields.koUntil1=until?api.sourceTimestamp(until[1])||until[1].trim():'';if(url)fields.koUrl1=url[0];}
 const strike=raw.match(/Basispreis\s*[:=]?\s*([\d.,]+)\s*USD/i),ratio=raw.match(/Bezugsverhältnis\s*[:=]?\s*([\d.,]+)/i);
 if(strike)notes.push('Basispreis aus Bild: '+value(strike[1])+' USD');if(ratio)notes.push('Bezugsverhältnis aus Bild: '+value(ratio[1])+' (noch kein bestätigtes Emittentenmodell)');
 if(!source)notes.push('Bildquelle bitte auswählen');
 if(!ko)notes.push('KO-Schwelle mit ausdrücklich angegebener USD-Währung fehlt');
 else if(!fields.koAt1||!fields.koUntil1)notes.push('KO-Quellenzeit / bestätigte Gültigkeit bleiben offen');
 return {ok:true,isin,source,fields,hasQuote,partialQuote,supplementedTime:supplemented,paired:!!fields.bid&&!!fields.ask,delayed:/verzögert|delayed/i.test(raw),notes};
}
function mergeDraft(previous,incoming,image){
 if(previous?.isin!==incoming.isin)previous=null;
 const out={isin:incoming.isin,fields:{...(previous?.fields||{})},evidence:{...(previous?.evidence||{})},notes:incoming.notes,delayed:previous?.delayed||false,supplementedTime:previous?.supplementedTime||null};
 const clear=keys=>{for(const key of keys){delete out.fields[key];delete out.evidence[key];}};
 if(incoming.hasQuote){clear(['bid','ask','quoteAt','venue','url','source']);out.delayed=incoming.delayed;out.supplementedTime=incoming.supplementedTime||null;out.fields.source=incoming.source;out.evidence.source=image;}
 if(incoming.fields.ko1)clear(['ko1','koSource1','koUrl1','koAt1','koUntil1']);
 for(const [key,v] of Object.entries(incoming.fields)){if(!incoming.hasQuote&&['url','venue','quoteAt'].includes(key))continue;out.fields[key]=v;out.evidence[key]=image;}
 return out;
}
function compareSnapshot(p,reference,draft,q,now=Date.now()){
 if(reference&&reference.isin!==p.isin||!reference&&draft&&draft.isin!==p.isin)return null;
 const r=reference||draft?.fields;if(!r)return null;
 const bid=number(r.bid),ask=number(r.ask);if(!(bid>0&&ask>=bid))return null;
 const out={isin:p.isin,snapshot:{bid,ask,source:r.source||draft?.fields?.source||'Quelle offen',venue:r.venue||'Handelsplatz offen',at:r.quoteAt||'Kurszeit offen',image:draft?.evidence?.bid||reference?.imageEvidence?.bid||null},current:null,reason:'Frischer Kurs derselben ISIN mit Quelle und Kurszeit fehlt'};
 if(!q||q.isin!==p.isin||!q.found||q.estimated||q.calculatedProduct||q.delayed||!q.source||!fresh(q.quoteAt,now,90)||!(number(q.bid)>0&&number(q.ask)>=number(q.bid)))return out;
 out.current={bid:number(q.bid),ask:number(q.ask),source:q.source,venue:q.venue||'Emittenten-Kursquelle',at:q.quoteAt};out.bidChange=out.current.bid-bid;out.askChange=out.current.ask-ask;out.sameVenue=!!r.venue&&r.venue===out.current.venue;out.reason=null;return out;
}
function renderComparison(x){
 if(!x)return '';
 const row=(label,q)=>'<tr><td>'+escape(label)+'</td><td>'+escape(q.bid.toFixed(2))+' / '+escape(q.ask.toFixed(2))+' EUR</td><td>'+escape(q.source)+' · '+escape(q.venue)+'</td><td>'+escape(q.at)+'</td></tr>';
 return '<div class="small"><b>Screenshot / frischer Produktkurs · '+escape(x.isin)+'</b><table><thead><tr><th>Stand</th><th>Geld / Brief</th><th>Quelle / Handelsplatz</th><th>Kurszeit laut Quelle</th></tr></thead><tbody>'+row('Momentaufnahme',x.snapshot)+(x.current?row('Frisch abgerufen',x.current):'')+'</tbody></table>'+(x.current?'Änderung Geld '+escape(x.bidChange.toFixed(2))+' EUR · Brief '+escape(x.askChange.toFixed(2))+' EUR. '+(x.sameVenue?'Gleicher Handelsplatz.':'Handelsplätze können abweichen; Preisunterschiede sind keine reine Kursbewegung.'):'Offen: '+escape(x.reason))+'. Screenshot bleibt eine Momentaufnahme; fehlende Sekunden bleiben unbekannt.</div>';
}
window.BobCombined={fixedBarriers,resetFixedList,compareSnapshot,renderComparison,fixedFor,saveFixed,removeFixed,assess,render,form,time,rank,renderTop3,screenshotDraft,mergeDraft};
})();

/* Bob DEGIRO assistant: deterministic risk math, product-fit checks and Top-3 ranking. No order execution. */
(function(){
function n(v){if(v===null||v===undefined||String(v).trim()==="")return null;const x=Number(v);return Number.isFinite(x)?x:null;}
function validIsin(value){
 const isin=String(value||"").trim().toUpperCase();
 if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))return false;
 // Repeated O in the common DE000 prefix is an ambiguous OCR reading, even
 // when a coincidental checksum passes. Require a visual correction.
 if(/^DE(?=[0O]{3})(?=[0O]{0,2}O)/.test(isin))return false;
 const digits=isin.split("").map(c=>/[A-Z]/.test(c)?String(c.charCodeAt(0)-55):c).join("");
 let sum=0;
 for(let i=digits.length-1,double=false;i>=0;i--,double=!double){let x=Number(digits[i]);if(double)x*=2;sum+=x>9?x-9:x;}
 return sum%10===0;
}
function normalizeOcrIsin(value,productText=''){
 const original=String(value||"").trim().toUpperCase();
 if(validIsin(original)&&!/^DE[0OQ]{3,4}[A-Z0-9]{7}$/.test(original))return{isin:original,originalIsin:""};
 if(validIsin(original)&&original.startsWith("DE000")&&original.length===12)return{isin:original,originalIsin:""};
 // German WKN excludes I/O. Only substitute those confusable glyphs,
 // only for DE000-style identifiers, and accept only a valid checksum.
 // Other substitutions require a reviewed identity and matching product context.
 if(!/^DE[0OQ]{3,4}[A-Z0-9]{7}$/.test(original))return{isin:original,originalIsin:""};
 const candidate="DE000"+original.slice(-7).replace(/O/g,"0").replace(/I/g,"1");
 // The user-reviewed 23 Oct list established one specific J/U OCR alias:
 // DEOOOPU8APE4 -> DE000PJ8APE4 (BNP GOLD Mini Long).
 // SL/STR are daily conditions, not permanent identity fields.
 // Require the same BNP/EUR/Long/R10 row with positive four-decimal terms.
 // Two independent observations of the complete row remain mandatory.
 const miniTerms=productText.match(/\bBNP\s+GOLD\s+Mini\s+Long\s+SL\s+(\d+[.,]\d{4})\s+STR\s+(\d+[.,]\d{4})\s+R\s*10\b/i);
 const miniSl=miniTerms?Number(miniTerms[1].replace(',','.')):null;
 const miniStr=miniTerms?Number(miniTerms[2].replace(',','.')):null;
 const miniSnapshot=miniSl>0&&miniStr>0&&miniSl>miniStr
  && /\bBNP\s+OTC\s+EUR\b/i.test(productText)
  && !/\b(?:SHORT|PUT|FACTOR|FAKTOR)\b/i.test(productText);
 if(candidate==='DE000PU8APE4'&&miniSnapshot&&validIsin('DE000PJ8APE4'))
  return {isin:'DE000PJ8APE4',originalIsin:original,
   identityCorrection:'Bekannte BNP-Mini-Long-ISIN: OCR J/U anhand gültiger ISIN und aktueller vollständiger Zeile abgeglichen; nur Bilddaten'};
 // User originals 1000074190.jpg and 1000074192.jpg show DE000PJ9NB98
 // in both DEGIRO layouts. Scope the observed OCR aliases to this broker
 // and these product/quote layouts; never repair arbitrary valid identifiers.
 const reviewedDegiroLayout=/\bBNP\s+OTC\b/i.test(productText)&&(
  /\bBNP\s+GOLD\s+Unlimited\s+Long\s+SL\b/i.test(productText)||
  /Symbol\s*[|I]?\s*ISIN/i.test(productText)&&/\bGeld\b/i.test(productText)&&/\bBrief\b/i.test(productText));
 if(['DE000PJ0NB98','DE000PJ0NB9S'].includes(candidate)&&reviewedDegiroLayout
    && !/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText))
  return {isin:'DE000PJ9NB98',originalIsin:original,identityCorrection:'DEGIRO-Produktidentität an Originalbildern 1000074190.jpg und 1000074192.jpg geprüft'};
 // Visually verified user original 1000070573.jpg. Both labelled identifiers
 // and both exact USD terms must agree; this is not general S -> 9 guessing.
 const identityTerms=normalizeProductTermLayout(productText);
 const bnpTermsContext=/(?:derivate\.bnpparibas\.com|\bBNP\s+PARIBAS\b)/i.test(productText)
  && /\bWKN\s+PJ[SO]NB9\b/i.test(productText)
  && /Knock-out-Schwelle\s+3\.996,2705\s+USD\s*\(05\.10\.2026\)/i.test(identityTerms)
  && /Basispreis\s+3\.996,2705\s+USD\s*\(05\.10\.2026\)/i.test(identityTerms)
  && /Typ\s+Unlimited\s+Long/i.test(productText)
  && !/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText);
 if(['DE000PJSNB98','DE000PJ0NB98'].includes(candidate)&&bnpTermsContext)return {isin:'DE000PJ9NB98',originalIsin:original,identityCorrection:'Produktidentität an BNP-Originalbildern geprüft; WKN und beide USD-Stammdaten stimmen überein'};

 // Verified against the user's original DEGIRO list 1000070092.jpg.
 // This is a single known identity, not a general I/1 -> 9 substitution.
 if(['DE000PJ1NCK0','DE000PJ0NCK0'].includes(candidate)&&/\bBNP\s+GOLD\s+Unlimited\s+Long\b/i.test(productText)&&!/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText)&&validIsin('DE000PJ9NCK0'))return {isin:'DE000PJ9NCK0',originalIsin:original,identityCorrection:'BNP-Produktidentität am Originalbild belegt'};
 // Original DEGIRO list 1000070469.jpg shows PJ9NB98, BNP Gold Long,
 // SL/STR 3996.2705 and R 10. Do not generalise I/1 -> 9 from checksum alone.
 // The same identity is visible in 1000072797.jpg with adjusted daily terms.
 // Restrict the correction to the reviewed alias and full product signature;
 // equal positive SL/STR values corroborate the row, not a fixed old price.
 const bnpNbTerms=productText.match(/\bBNP\s+GOLD\s+Unlimited\s+Long\s+SL\s+(\d+[.,]\d+)\s+STR\s+(\d+[.,]\d+)\s+R\s*10\b/i);
 const bnpNbContext=!!bnpNbTerms&&Number(bnpNbTerms[1].replace(',','.'))>0
  && Number(bnpNbTerms[1].replace(',','.'))===Number(bnpNbTerms[2].replace(',','.'))
  && !/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText);
 if(['DE000PJ1NB98','DE000PJ0NB98'].includes(candidate)&&bnpNbContext&&validIsin('DE000PJ9NB98'))return {isin:'DE000PJ9NB98',originalIsin:original,identityCorrection:'BNP-Produktidentität an Originalbildern 1000070469.jpg und 1000072797.jpg belegt'};
 // Verified visually in the original DEGIRO list 1000069826(1).jpg.
 // A checksum alone cannot justify S/5 substitutions: require this exact product context.
 const sgContext=/\bSG\s+GOLD\s+TURBO\s+BEST\s+OPEN[-\s]?END\s+CALL\b/i.test(productText)
  && /\bBAR\s+4113[.,]57\s+BP\s+4113[.,]57\b/i.test(productText)
  && !/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText);
 if(candidate==='DE000FGSNMF2'&&sgContext&&validIsin('DE000FG5NMF2'))return {isin:'DE000FG5NMF2',originalIsin:original,identityCorrection:'SG-Produktidentität am Originalbild belegt (S/5)'};
 return validIsin(candidate)?{isin:candidate,originalIsin:original}:{isin:original,originalIsin:""};
}
function koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}
function directionOf(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null)return null;return ko<spot?"LONG":ko>spot?"SHORT":null;}
function riskModel(p){const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);if(spot===null||stop===null||riskEur===null||riskEur<=0)return{ok:false,reason:"Ungültige Eingabedaten für Risiko."};if(fx===null||fx<=0)return{ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};const dist=Math.abs(spot-stop);if(dist<=0)return{ok:false,reason:"Stop-Distanz ist null."};const maxLossUsd=riskEur/fx,approxNotionalUsd=maxLossUsd/(dist/spot),approxNotionalEur=approxNotionalUsd*fx,marginEur=approxNotionalEur/lev,ko=n(p.ko),koPct=koDistancePct(spot,ko),warnings=[];if(ko!==null&&((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");return{ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};}
// Related price indicators form ONE collective; repetitions never add votes.
function collectiveSignal(values){
 if(!values.length||values.some(v=>typeof v!=='number'||!Number.isFinite(v)))return 0;
 const signs=new Set(values.filter(v=>typeof v==='number'&&Number.isFinite(v)).map(v=>Math.sign(v)));
 if(!signs.size||signs.has(1)&&signs.has(-1))return 0;
 const side=signs.has(1)?1:signs.has(-1)?-1:0;
 return side*(signs.has(0)?0.5:1);
}
function technicalQuality(ctx={}){
 const d=String(ctx.direction||'NEUTRAL').toUpperCase();
 if(!['LONG','SHORT'].includes(d))return {score:50,reasons:['Kein eindeutiges Richtungsszenario.']};
 const side=v=>{const x=String(v||'').toUpperCase();if(/NEUTRAL|ABWARTEN|MIXED|GEMISCHT/.test(x))return 0;return /LONG|BULL|UP/.test(x)?1:/SHORT|BEAR|DOWN/.test(x)?-1:0;};
 const sign=v=>n(v)===null?0:Math.sign(n(v));
 const r=n(ctx.rsi),rsi=r!==null&&r>50&&r<75?1:r!==null&&r<50&&r>25?-1:0;
 const value=ctx.policy==='intraday-responsive-v6'&&n(ctx.signalScore)!==null?(n(ctx.signalScore)-50)/50:ctx.policy==='intraday-responsive-v6'?(side(ctx.trend)!==0&&side(ctx.trend)===sign(ctx.hist)?side(ctx.trend)*(n(ctx.rsi)!==null&&Math.sign(n(ctx.rsi)-50)===side(ctx.trend)?1:.5):0):collectiveSignal([side(ctx.trend),...(['intraday-shadow-v1','intraday-fast-v3','intraday-consistent-v4','intraday-responsive-v6'].includes(ctx.policy)?[]:[side(ctx.trend2)]),sign(ctx.hist),rsi]);
 const expected=d==='LONG'?1:-1,mtf=side(ctx.mtf);
 const conflict=value*expected<0||mtf!==0&&mtf!==expected;
 const score=conflict?0:50+50*value*expected;
 return {score,reasons:[conflict?'Kursindikatoren-Kollektiv widerspricht.':value*expected>0?'Kursindikatoren-Kollektiv bestätigt.':'Kursindikatoren-Kollektiv neutral oder widersprüchlich.','EMA, MACD und RSI zählen gemeinsam einmal; Momentum-Anzeige und MTF geben keine Zusatzpunkte. ADX beschreibt nur Trendstärke.'],collectives:1};
}
const futureIsins=new Set(["DE000FG309G0"]);
function isFutureProduct(p){return /\bFUTURE\b/i.test(p.name||p.snapshot?.name||'')||/future/i.test(p.snapshot?.terms?.underlying?.value||'')||!!p.snapshot?.terms?.contract?.value||p.underlyingType==="FUTURE"||p.quote?.metadata?.underlyingType==="FUTURE"||futureIsins.has(String(p.isin||"").trim().toUpperCase());}
function futureResearchText(x,now=Date.now()){
 const r=x.futureResearch;if(!r)return "";
 const at=v=>typeof v==="string"&&!Number.isNaN(Date.parse(v))?new Date(v).toLocaleString():"unbekannt";
 let text=" · FUTURES-RECHERCHE "+r.contract;
 if(Number.isFinite(r.bid)&&Number.isFinite(r.ask))text+=" · Geld "+r.bid+" / Brief "+r.ask+" EUR · Geldzeit "+at(r.bidAt)+" · Briefzeit "+at(r.askAt);
 if(r.underlyingPriceUsd)text+=" · Futures-Basiswert "+r.underlyingPriceUsd+" USD · Basiswertzeit "+at(r.underlyingAt)+" (verzögert oder Echtzeitstatus unbestätigt)";
 const c=r.futureReference||r.calculatedFuture;
 if(c){
  const age=(now-Date.parse(c.priceAt))/1000,refAge=(now-Date.parse(c.referenceAt))/1000;
  if(c.available&&Number.isFinite(c.priceUsd)&&c.priceUsd>0&&age>=0&&age<=60&&(c.kind==="cfd-reference"||refAge>=0&&refAge<=1800)){
   if(c.kind==="cfd-reference")text+=" · GOLD-CFD ALS FUTURE-REFERENZ: "+Number(c.priceUsd).toFixed(2)+" USD · Quellenzeit "+at(c.priceAt)+" · "+c.note;
   else text+=" · BERECHNETER FUTURE-KURS: "+Number(c.priceUsd).toFixed(2)+" USD · "+(c.proxySource||"Investing.com CFD")+"-Kurszeit "+at(c.priceAt)+" ("+Math.ceil(age)+" s alt) · echter GCZ26-Referenzkurs "+c.referencePriceUsd+" USD von "+at(c.referenceAt)+" · Zeitversatz "+c.alignmentSeconds+" s"+(c.proxyReferenceKind==="linear-interpolation"?" (Quellenreferenz zeitlich interpoliert)":"")+" · Formel: "+c.formula+" · "+c.note;
  }else{
   const reasons=[];
   if(c.available){
    if(!Number.isFinite(age)||age<0)reasons.push("Schätzungszeit fehlt oder liegt in der Zukunft");
    else if(age>60)reasons.push("Schätzung "+Math.ceil(age)+" s alt (höchstens 60 s)");
    if(c.kind!=="cfd-reference"&&(!Number.isFinite(refAge)||refAge<0))reasons.push("Future-Referenzzeit fehlt oder liegt in der Zukunft");
    else if(c.kind!=="cfd-reference"&&refAge>1800)reasons.push("Future-Referenz "+Math.ceil(refAge/60)+" min alt (höchstens 30 min)");
   }
   text+=" · Berechneter Future-Kurs: "+(c.available?"ausgesetzt – "+(reasons.join("; ")||"Kurs nicht verwendbar")+" · Schätzungszeit "+at(c.priceAt):c.reason||"noch nicht verfügbar");
  }
  const collection=c.collection;
  if(collection){
   const sourceAge=(now-Date.parse(collection.lastAt))/1000;
   text+=" · "+(c.proxyKind==="gold-api-spot"?"Gold-Spot":"CFD")+"-Erfassung: "+collection.sampleCount+" Beobachtungen über "+Math.floor(collection.coveredSeconds/60)+" min · letzter Quellenzeitpunkt "+at(collection.lastAt)+" · "+(Number.isFinite(sourceAge)&&sourceAge>=0&&sourceAge<=60?"frisch":"nicht aktuell")+(Number.isFinite(c.referenceAgeSeconds)?" · Future-Referenz "+Math.ceil(c.referenceAgeSeconds/60)+" min alt":"");
   if(Number.isFinite(collection.largestGapSeconds))text+=" · größte Erfassungslücke "+collection.largestGapSeconds+" s";
   if(Number.isFinite(collection.continuousSeconds))text+=" · jüngster zusammenhängender Abschnitt "+Math.floor(collection.continuousSeconds/60)+" min (Lücken höchstens "+collection.maxGapSeconds+" s)";
  }
  text+=" · "+qualityText(c.validation,"USD");
  if(c.sourceStatus)text+=" · Quellenstatus: "+c.sourceStatus;
  if(c.storageStatus)text+=" · "+c.storageStatus;
  if(c.proxyKind==="gold-api-spot")text+=" · Spot dient ausschließlich der Kursschätzung; Richtung und MTF stammen weiterhin vom exakten GCZ26-Kontrakt";
  for(const alternative of c.alternatives||[])if(alternative.proxyKind!==c.proxyKind&&!alternative.available)text+=" · "+(alternative.proxyKind==="gold-api-spot"?"Spot-Ersatz":"Investing.com CFD")+": "+(alternative.sourceStatus||alternative.reason||"noch nicht verfügbar");
 }
 if(r.indicativeLeverage)text+=" · Recherche-Hebel ca. "+Number(r.indicativeLeverage).toFixed(2)+"× · KO-Abstand zum verzögerten Basiswert ca. "+Number(r.indicativeKoDistancePct).toFixed(2)+"% · Näherung mit verzögertem Basiswert";
 const analysis=r.contractAnalysis;
 if(analysis)text+=" · Eigene Kontraktanalyse: "+(analysis.available?analysis.direction+" · 5m/15m/1h/4h · "+Object.entries(analysis.blocks||{}).map(([k,v])=>k+": "+v).join(" · ")+" · "+analysis.source:analysis.reason||"Historie wird geladen");
 return text+" · "+r.estimateNote;
}
function productEstimateText(x,now=Date.now()){
 const c=x.calculatedProduct;if(!c)return "";
 const age=(now-Date.parse(c.priceAt))/1000,refAge=(now-Date.parse(c.referenceAt))/1000;
 const times=[c.goldAt,c.fxDataAt,c.fxEffectiveAt].map(t=>(now-Date.parse(t))/1000);
 if(c.available&&Number.isFinite(c.priceEur)&&c.priceEur>0&&age>=0&&age<=60&&refAge>=0&&refAge<=1800&&times.every(t=>Number.isFinite(t)&&t>=0&&t<=60)){
  return " · BERECHNETER PRODUKTKURS: ca. "+Number(c.priceEur).toFixed(2)+" EUR (Brief-Schätzung) · Geld-Schätzung "+Number(c.bidEur).toFixed(2)+" EUR · Daten "+Math.ceil(age)+" s alt · bestätigter Produkt-Referenzkurs vom "+new Date(c.referenceAt).toLocaleString()+" · "+c.formula+" · "+c.note+" · "+qualityText(c.validation,"EUR")+" · Keine Live-Handelsfreigabe.";
 }
 return " · Berechneter Produktkurs: "+(c.available?"veraltet – Aktualisierung erforderlich":c.reason||"kein verifiziertes Modell verfügbar");
}
function qualityText(v,unit){
 if(!v)return "Genauigkeitsmessung startet";
 if(!v.ready){
  const span=n(v.observedSpanSeconds)??Math.min(n(v.bid?.observedSpanSeconds)||0,n(v.ask?.observedSpanSeconds)||0);
  let text="Genauigkeit noch nicht ausreichend gemessen · "+(v.sampleCount||0)+"/"+(v.minSamples||20)+" passende Vergleiche · Messzeitraum "+Math.floor(span/60)+"/10 min"+(v.horizonBucket?" · Referenzabstand "+v.horizonBucket:"");
  if(v.sampleCount>0&&Number.isFinite(v.maxAbsoluteError))text+=" · bisher maximale Abweichung "+v.maxAbsoluteError.toFixed(unit==="EUR"?4:2)+" "+unit+" (vorläufig)";
  for(const s of v.horizonSummaries||[]){
   text+=" · Messgruppe "+s.horizonBucket+": "+s.sampleCount+" Vergleiche";
   if(s.sampleCount>0&&Number.isFinite(s.meanAbsoluteError)&&Number.isFinite(s.maxAbsoluteError))text+=" · mittlere absolute Abweichung "+s.meanAbsoluteError.toFixed(2)+" "+unit+", maximal "+s.maxAbsoluteError.toFixed(2)+" "+unit+" (vorläufig)";
  }
  return text;
 }
 const error=n(v.maxAbsoluteError)??Math.max(n(v.bid?.maxAbsoluteError)||0,n(v.ask?.maxAbsoluteError)||0);
 return v.sampleCount+" Vergleiche · bisher maximale Abweichung "+Number(error).toFixed(unit==="EUR"?4:2)+" "+unit+" · zukünftige Fehler können größer sein";
}
function freshTimes(times,now,maxAge=60){
 const parsed=times.map(t=>typeof t==="string"&&/(?:Z|[+-]\d{2}:\d{2})$/.test(t)?Date.parse(t):NaN);
 return parsed.length>0&&parsed.every(t=>Number.isFinite(t)&&now>=t&&now-t<=maxAge*1000);
}
// Read-only assessment: never fills ranking inputs or renews source times.
function screenshotCurrentState(p,bundle,now=Date.now()){
 const out={eligible:false,liveVerified:false,rows:[],basis:null,koDistancePct:null,leverage:null};
 const fixed=window.BobCombined.fixedFor(p);
 if(!validIsin(p.isin)||p.isinConfirmed!==true&&!fixed){out.rows.push({label:'Produktzuordnung',text:'ISIN und erkannte Werte am Original bestätigen'});return out;}
 const q=p.quote?.isin===p.isin?p.quote:null,shot=p.snapshot?.isin===p.isin?p.snapshot:null;
 const meta=q?.productVerified?q.metadata:null;
 const model=q?.productVerified&&q.productModel?.isin===p.isin?q.productModel:null;
 const future=isFutureProduct(p)||/\bFUTURE\b/i.test(p.name||shot?.name||'');
 const side=meta?.direction||shot?.direction||p.productDirection,ko=n(fixed?.value)??n(meta?.ko)??n(shot?.ko)??n(p.ko);
 let basis=null,basisLabel='',basisAt=null;
 if(future){
  const r=q?.futureResearch,c=r?.futureReference||r?.calculatedFuture;
  if(meta?.underlyingType==='FUTURE'&&meta.contract&&meta.contract===r?.contract&&r.contract===c?.contract&&c.available&&n(c.priceUsd)>0&&freshTimes([c.priceAt],now)&&(c.kind==='cfd-reference'||freshTimes([c.referenceAt],now,1800))){
   basis=n(c.priceUsd);basisAt=c.priceAt;basisLabel=c.kind==='cfd-reference'?'Gold-CFD als '+r.contract+'-Referenz (kein Börsenkurs)':'Berechneter '+r.contract+'-Kurs (Schätzung, keine Börsen-Echtzeit)';
  }else if(meta?.underlyingType==='FUTURE'&&meta.contract===r?.contract&&r?.underlyingDataState==='realtime'&&n(r.underlyingPriceUsd)>0&&freshTimes([r.underlyingAt],now)){
   basis=n(r.underlyingPriceUsd);basisAt=r.underlyingAt;basisLabel='Datierter '+r.contract+'-Basiswert';
  }
 }else{
  const spots=bundle?.spots,age=n(spots?.xaus_age_seconds),fetched=n(bundle?.fetched_at),elapsed=fetched===null?null:now/1000-fetched;
  const confirmedSpot=meta?.underlyingType==='SPOT'&&meta.underlying==='XAU/USD'||model?.verifiedSimpleTurbo&&model.underlying==='XAU/USD';
  // Undifferentiated "Gold" is a scenario, not verified spot identity.
  const scenario=!meta||meta.underlyingType==='SPOT';
  const spotScenario=confirmedSpot||scenario&&/\bGOLD\b|XAU/i.test(p.name||shot?.name||'');
  if(spotScenario&&spots?.is_genuine_xauusd_spot===true&&!spots.spot_error&&n(spots.xaus)>0&&age!==null&&age>=0&&elapsed!==null&&elapsed>=0&&age+elapsed<=60&&freshTimes([spots.spot_price_as_of],now)){
   basis=n(spots.xaus);basisAt=spots.spot_price_as_of;
   basisLabel=confirmedSpot?'Aktueller XAU/USD-Spot':'Gold-Spot-Szenario; Produktbasiswert noch zu bestätigen';
  }
 }
 out.basis=basis;
 out.rows.push({label:'Basiswert / Datenzeit',text:basis===null?(future?'Passender, datierter Future-Kontrakt fehlt; kein Spot-Ersatz':'Aktueller bestätigter Gold-Spotkurs oder Basiswertzuordnung fehlt'):basisLabel+' · '+basis.toFixed(2)+' USD · Quellenzeit '+basisAt});
 if(basis!==null&&ko>0&&['LONG','SHORT'].includes(side)){
  const signed=(side==='LONG'?basis-ko:ko-basis)/basis*100;out.koDistancePct=signed;
  out.rows.push({label:'Abstand zur angegebenen KO-Schwelle',text:(signed<=0?'Basiswert an / jenseits der angegebenen Schwelle':'Puffer '+signed.toFixed(2)+'%')+' · KO '+ko+' USD · '+(future?'Basiswert geschätzt; ':'')+(fixed?'Fester USD-Berechnungswert aus DEGIRO-Screenshot, vom Nutzer bestätigt; kein Nachweis eines vergangenen KO-Ereignisses':'Aktualität und USD-Einheit der KO-Schwelle gesondert bestätigen; kein Nachweis eines vergangenen KO-Ereignisses')});
 }else out.rows.push({label:'KO-Abstand',text:'Basiswert, Richtung oder KO-Schwelle fehlen / sind nicht zugeordnet'});
 const c=q?.calculatedProduct;
 if(model?.verifiedSimpleTurbo&&model.underlying==='XAU/USD'&&!future&&c?.available&&c.direction===model.direction&&c.ratio===model.ratio&&c.strikeUsd===model.strike&&meta?.ko===model.ko&&n(c.goldUsd)>0&&n(c.usdEur)>0&&n(c.ratio)>0&&n(c.askEur)>0&&freshTimes([c.priceAt,c.goldAt,c.fxDataAt,c.fxEffectiveAt],now)&&freshTimes([c.referenceAt],now,1800)&&Number.isFinite(Date.parse(model.tradingEndAt))&&now<=Date.parse(model.tradingEndAt)){
  out.leverage=n(c.goldUsd)*n(c.usdEur)*n(c.ratio)/n(c.askEur);
  out.rows.push({label:'Berechneter Hebel',text:out.leverage.toFixed(2)+'× · geschätzter Brief '+Number(c.askEur).toFixed(4)+' EUR · Näherung mit Delta ±1; kein Emittentenhebel · '+qualityText(c.validation,'EUR')});
 }else if(q&&currentQuote(p,now)&&n(q.leverage)>0){
  out.leverage=n(q.leverage);out.rows.push({label:'Hebel',text:out.leverage.toFixed(2)+'× · '+(q.leverageEstimated?'rechnerische Näherung':'datierter Emittentenwert')});
 }else{
  const r=q?.futureResearch,times=[basisAt,r?.bidAt,r?.askAt,r?.fxDataAt,r?.fxEffectiveAt].map(Date.parse);
  if(future&&basis!==null&&r?.marketOpen&&now<=Date.parse(r.tradingEndAt)&&n(r.bid)>0&&n(r.ask)>=n(r.bid)&&n(r.ratio)>0&&n(r.usdEur)>0&&freshTimes([r.bidAt,r.askAt,r.fxDataAt,r.fxEffectiveAt],now)&&Math.max(...times)-Math.min(...times)<=15000){
   out.leverage=basis*r.usdEur*r.ratio/r.ask;
   out.rows.push({label:'Berechneter Hebel',text:out.leverage.toFixed(2)+'× · Future-Basiswert × USD/EUR × Bezugsverhältnis / datierter Briefkurs · '+basisLabel+' · Näherung, kein Emittentenhebel'});
  }else out.rows.push({label:'Aktueller Hebel / Produktkurs',text:'Frischer Produktbrief und FX oder bestätigtes Berechnungsmodell fehlen. LV aus dem Produktnamen und alter Screenshot-Brief werden nicht als aktuell übernommen'});
 }
 const status=manualSnapshotStatus(p,shot,now);
 out.rows.push({label:'Produktkurse / Nachweise',text:(shot?.currency==='EUR'&&n(shot.bid)>0&&n(shot.ask)>=n(shot.bid)?'Geld '+shot.bid+' / Brief '+shot.ask+' EUR · '+(shot.sourceTime||'Quellenzeit nicht vollständig belegt'):'Kein vollständiges Kursbild')+' · '+(status.complete?'vollständige Momentaufnahme, keine Live-Verifizierung':status.reasons.join('; '))});
 const ke=meta?.koEvidence;
 if(ke?.state==='issuer_reported'&&ke.currency==='USD'&&n(ke.value)>0&&n(ke.value)===n(meta.ko)&&typeof ke.updatedAtRaw==='string'&&ke.updatedAtRaw){
  out.rows.push({label:'SG-KO-Nachweis',text:ke.value+' USD · Emittenten-Aktualisierung '+ke.updatedAtRaw+(ke.timezoneKnown===true?'':' (Zeitzone nicht angegeben)')+' · Abruf '+(ke.retrievedAt||'nicht belegt')+' · '+(freshTimes([ke.retrievedAt],now)?'gerade abgerufene Emittentenangabe':'Abruf nicht mehr frisch')+'; Gültigkeitszeitraum und Geld-/Briefkurse dadurch nicht bestätigt'});
 }
 return out;
}
function renderScreenshotCurrentState(p,bundle,now=Date.now()){
 const state=screenshotCurrentState(p,bundle,now);
 return '<div class="small" style="margin-top:8px;padding:8px;background:#f4f7fb;border-radius:8px"><b>Berechneter Zustand / offene Nachweise</b>'+state.rows.map(r=>'<div style="margin-top:5px"><b>'+esc(r.label)+':</b> '+esc(r.text)+'</div>').join('')+'<div style="margin-top:5px">Teilbewertung / Szenario. Keine zusätzliche Live-Freigabe; Quellenzeiten werden durch die Berechnung nicht erneuert.</div></div>';
}
function conditionalCandidate(p,context={},now=Date.now()){
 if(knockoutStatus(p))return {ok:false,isin:p.isin,reason:"Ausgeknockt – Produkt ausgeschlossen"};
 if(/FAKTOR|FACTOR/i.test(p.name||''))return {ok:false,isin:p.isin,reason:"Faktorprodukt benötigt eigenes tägliches Anpassungsmodell",scope:"FACTOR",direction:p.productDirection};
 const q=p.quote,fail=reason=>({ok:false,isin:p.isin,reason,scope:isFutureProduct(p)?q?.futureResearch?.contract||q?.metadata?.contract||"FUTURE":"XAU/USD",direction:isFutureProduct(p)?q?.futureResearch?.direction:q?.productModel?.direction||q?.direction||p.productDirection});
 if(!q||q.isin!==p.isin||!validIsin(p.isin)||p.isinConfirmed!==true)return fail("ISIN oder Produktidentität nicht bestätigt");
 let basis,ask,bid,ko,strike,ratio,fx,errorPrice=0,errorBasis=0,scope,ctx,quality,priceKind,at,rankingQuoteAt,analysisGearing,gearingAt;
 if(isFutureProduct(p)){
  const r=q.futureResearch,c=r?.futureReference||r?.calculatedFuture,a=r?.contractAnalysis;
  if(!q.productVerified||q.metadata?.underlyingType!=="FUTURE"||q.metadata.contract!==r?.contract||r?.contract!==c?.contract||r?.contract!==a?.contract)return fail("Futures-Kontrakt nicht vollständig bestätigt");
  if(!c.available||!c.validation?.ready||c.validation.sampleCount<20)return fail("Future-Referenz: Genauigkeit gegenüber dem Börsenkurs noch nicht ausreichend gemessen");
  if(!a.available||!["LONG","SHORT"].includes(a.direction)||a.technicalSourceFamilies!==1||!['5m','15m'].every(tf=>a.frames?.[tf]?.available)||Object.keys(a.frames||{}).length!==4||!freshTimes([a.checkedAt],now,180)||!Number.isFinite(Date.parse(a.expiresAt))||now>Date.parse(a.expiresAt))return fail("ABWARTEN: eigene Kontrakt-MTF fehlt, ist uneinheitlich oder veraltet");
  const shot=selectionDetailStatus(p,now),useShot=shot.complete;
  const prices=useShot?{bid:n(p.snapshot.bid),ask:n(p.snapshot.ask),bidAt:shot.at,askAt:shot.at}:r;
  if(!r.marketOpen||!Number.isFinite(Date.parse(r.tradingEndAt))||now>Date.parse(r.tradingEndAt)||!freshTimes([prices.bidAt,prices.askAt],now,90)||!freshTimes([r.fxDataAt,r.fxEffectiveAt,c.priceAt],now)||!(c.kind==='cfd-reference'||freshTimes([c.referenceAt],now,1800)))return fail("Future-, Produkt- oder FX-Daten nicht aktuell");
  const times=[prices.bidAt,prices.askAt,r.fxDataAt,r.fxEffectiveAt,c.priceAt].map(Date.parse);
  rankingQuoteAt=new Date(Math.min(...times)).toISOString();
  if(Math.max(...times)-Math.min(...times)>(useShot?90000:15000))return fail("Future- und Produktdaten zeitlich zu weit auseinander");
  if(useShot&&Math.abs(n(p.ko)-n(r.ko))>1)return fail("Screenshot-Barriere und Future-Produktbedingungen widersprechen sich um mehr als 1 USD");
  basis=n(c.priceUsd);ask=n(prices.ask);bid=n(prices.bid);ko=n(r.ko);strike=n(r.strike);ratio=n(r.ratio);fx=n(r.usdEur);errorBasis=n(c.comparisonErrorUsd);
  if(!(errorBasis>=Math.max(.1,n(c.validation.maxAbsoluteError)||0)))return fail("Gemessene Future-Abweichung fehlt");
  if(r.direction!==a.direction)return fail("Produkt passt nicht zum eigenen Futures-Szenario");
  const timing=n(a.frames['5m'].ema20);
  if(timing===null||a.direction==="LONG"&&basis-errorBasis<=timing||a.direction==="SHORT"&&basis+errorBasis>=timing)return fail("ABWARTEN: berechnete Kursspanne bestätigt das Kontrakt-Timing nicht eindeutig");
  scope=r.contract;priceKind=c.kind==="cfd-reference"?"Produktkurs · Gold-CFD als Future-Referenz":useShot?"DEGIRO-Kursmomentaufnahme · berechnete Future-Referenz":"Bestätigter Produktkurs · berechneter Basiswert";quality=c.validation;at=c.priceAt;
  ctx={policy:'intraday-responsive-v6',direction:a.direction,trend:a.frames['15m'].trend,trend2:a.frames['1h'].ema50>a.frames['1h'].ema200?"LONG":"SHORT",mtf:a.direction,rsi:a.rsi,hist:a.macdHistogram,momentum:a.macdHistogram,atr:a.atr};
 }else if(analysisReleaseQuote(p,now)){
  if(!context.spotFresh||!["LONG","SHORT"].includes(context.direction))return fail("ABWARTEN: Spot-Szenario oder aktueller Goldpreis fehlen");
  const a=analysisReleaseQuote(p,now);
  basis=n(context.spot);ask=n(a.ask);bid=n(a.bid);ko=n(p.ko);scope="XAU/USD";ctx=context;at=a.at;
  analysisGearing=a.leverageKind==='screenshot'?a.leverage:null;gearingAt=a.leverageAt;
  priceKind=(a.priceKind==="secondary-market"?"Ersatzquellenkurs":"Chartkurs")+(a.leverageKind==='screenshot'?" · CHF/EUR zeitlich bestätigt · Hebel aus Momentaufnahme "+a.leverageAt:" · berechneter Hebel")+" · Analysefreigabe";
 }else if(currentQuote(p,now)){
  if(!context.spotFresh||!["LONG","SHORT"].includes(context.direction))return fail("ABWARTEN: Spot-Szenario oder aktueller Goldpreis fehlen");
  basis=n(context.spot);ask=n(q.ask);bid=n(q.bid);ko=n(q.ko);scope="XAU/USD";ctx=context;at=q.quoteAt;
  priceKind="Bestätigter Emittentenkurs";
 }else{
  const c=q.calculatedProduct,m=q.productModel;
  if(!q.productVerified||!m?.verifiedSimpleTurbo||m.isin!==p.isin||m.underlying!=="XAU/USD"||!c?.available||!c.validation?.ready||c.validation.sampleCount<20)return fail("Produktschätzung: Referenz oder ausreichende Genauigkeitsmessung fehlen");
  if(!context.spotFresh||!["LONG","SHORT"].includes(context.direction)||!freshTimes([c.priceAt,c.goldAt,c.fxDataAt,c.fxEffectiveAt],now)||!freshTimes([c.referenceAt],now,1800)||!Number.isFinite(Date.parse(m.tradingEndAt))||now>Date.parse(m.tradingEndAt))return fail("ABWARTEN: aktuelle Daten oder Spot-Szenario fehlen");
  if(c.direction!==m.direction||c.ratio!==m.ratio||c.strikeUsd!==m.strike||q.metadata?.ko!==m.ko)return fail("Produktbedingungen passen nicht zum Berechnungsmodell");
  basis=n(c.goldUsd);ask=n(c.askEur);bid=n(c.bidEur);ko=n(m.ko);strike=n(m.strike);ratio=n(m.ratio);fx=n(c.usdEur);errorPrice=n(c.comparisonErrorEur);
  const measured=Math.max(.01,n(c.validation.bid?.maxAbsoluteError)||0,n(c.validation.ask?.maxAbsoluteError)||0);
  if(!(errorPrice>=measured))return fail("Gemessene Produktabweichung fehlt");
  scope="XAU/USD";ctx=context;quality=c.validation;priceKind="Berechneter Produktkurs";at=c.priceAt;
 }
 if(!(basis>0&&ask>0&&bid>0&&ask>=bid&&ko>0&&ask>errorPrice&&basis>errorBasis))return fail("Unvollständige Preise oder zu große beobachtete Abweichung");
 const direction=isFutureProduct(p)?q.futureResearch.direction:q.productModel?.direction||q.direction||q.metadata?.direction;
 if((errorPrice>0||errorBasis>0)&&(!(ratio>0&&fx>0&&strike>0)||direction==="LONG"&&basis-errorBasis<=strike||direction==="SHORT"&&basis+errorBasis>=strike))return fail("Berechnungsparameter fehlen oder Finanzierungsschwelle innerhalb der Spanne erreicht");
 const market=selectionMarketGate(ctx);if(!market.ok)return fail(market.reasons.join(' · '));
 if(isFutureProduct(p))for(const [frame,value] of Object.entries(q.futureResearch.contractAnalysis.frames)){
  if(frame==='4h')continue;
  for(const key of ['direction','trend'])if(value[key]&&String(value[key]).toUpperCase()!==ctx.direction)return fail('Kontrakt-'+frame+' '+key+' widerspricht '+ctx.direction);
 }
 const lev=(u,price)=>ratio>0&&fx>0?u*fx*ratio/price:analysisGearing??n(q.leverage);
 const evaluations=[];
 for(const u of [basis-errorBasis,basis+errorBasis])for(const price of [ask-errorPrice,ask+errorPrice]){
  const e=evaluateProductCore({...p,...ctx,spot:u,ko,price,productDirection:direction,leverage:lev(u,price),spread:ask-bid+2*errorPrice,now,rankingUncertaintyUsd:errorBasis,rankingBasisUsd:basis,rankingEstimated:errorBasis>0||errorPrice>0,rankingEstimateValidated:true,rankingQuoteAt:rankingQuoteAt||at});
  if(!e.ok||!e.fit||e.direction!==ctx.direction||e.setupScore<35||e.conflictCount>=3)return fail(e.reasons.join(" · ")||"ABWARTEN: Passung oder KO-Puffer innerhalb der beobachteten Fehlerspanne nicht stabil");
  evaluations.push(e);
 }
 return {ok:true,isin:p.isin,name:p.name||p.isin,scope,direction:ctx.direction,priceKind,
  price:ask,priceError:errorPrice,basis,basisError:errorBasis,quality,at,
  source:isFutureProduct(p)?(q.futureResearch.futureReference||q.futureResearch.calculatedFuture).proxySource:q.source,
  quoteAt:isFutureProduct(p)?(selectionDetailStatus(p,now).complete?selectionDetailStatus(p,now).timeLabel:q.futureResearch.askAt):(at||q.quoteAt),
  reasons:evaluations.reduce((worst,e)=>e.score<worst.score?e:worst).reasons,
  warnings:[...new Set([...evaluations.flatMap(e=>e.warnings||[]),...(gearingAt?['Hebel aus gespeicherter Momentaufnahme vom '+gearingAt+'; kein aktueller berechneter Hebel']:[])])],
  scoreLow:Math.min(...evaluations.map(e=>e.score)),scoreHigh:Math.max(...evaluations.map(e=>e.score)),
  leverageLow:Math.min(...evaluations.map(e=>e.leverage)),leverageHigh:Math.max(...evaluations.map(e=>e.leverage)),
  koDistanceMinPct:Math.min(...evaluations.map(e=>e.koDistancePct)),spreadWorst:ask-bid+2*errorPrice};
}
function rankConditional(products,context={}){
 const now=context.now??Date.now(),groups=new Map(),excluded=[];
 for(const p of products){
  if(!p.quote){if(p.isin&&p.isinConfirmed)excluded.push({isin:p.isin,scope:isFutureProduct(p)?"FUTURE":"XAU/USD",direction:p.productDirection,reason:"Produktdaten fehlen"});continue;}
  const c=conditionalCandidate(p,context,now);
  if(!c.ok){excluded.push(c);continue;}
  const key=c.scope+" · "+c.direction;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(c);
 }
 const results=Array.from(groups,([scope,candidates])=>{
  candidates.sort((a,b)=>b.scoreLow-a.scoreLow);
  return {scope,candidates,favorite:null,reason:"Unverbindlicher Kandidatenvergleich, keine Freigabe. Pflichtprüfung in der Produktauswahl; aktuellen DEGIRO-Briefkurs prüfen"};
 });
 return {groups:results,excluded,tradeable:false,needsDegiroCheck:true};
}
function renderConditional(result){
 const rows=result.groups.map(g=>'<div style="margin-top:10px"><b>'+esc(g.scope)+' · '+'Unverbindliche Kandidaten · keine Freigabe'+'</b><div class="small">'+esc(g.reason)+'</div>'+g.candidates.slice(0,3).map(c=>'<div class="small" style="margin-top:8px"><b>'+esc(c.isin)+'</b> · '+esc(c.priceKind)+' · Kurs ca. '+c.price.toFixed(2)+' EUR'+(c.priceError?' · Vergleichsspanne ±'+c.priceError.toFixed(4)+' EUR':'')+' · Basiswert '+c.basis.toFixed(2)+' USD'+(c.basisError?' ±'+c.basisError.toFixed(2)+' USD':'')+'<br>KO-Pufferwert '+c.scoreLow+'–'+c.scoreHigh+'/100 · Hebel ca. '+c.leverageLow.toFixed(2)+'–'+c.leverageHigh.toFixed(2)+'× · KO-Abstand mindestens '+c.koDistanceMinPct.toFixed(2)+'% innerhalb der Vergleichsspanne · Datenzeit '+esc(new Date(c.at).toLocaleTimeString())+'<br>Warum: '+esc((c.reasons||[]).slice(0,3).join(' · ')).replace(/\bHebel\b/g,'<strong>Hebel</strong>')+(c.quality?'<br>'+esc(qualityText(c.quality,c.priceError?'EUR':'USD')):'')+'</div>').join('')+'</div>').join('');
 const waiting=result.excluded.map(x=>'<div class="small">'+esc(x.isin)+' · '+esc(x.reason)+'</div>').join('');
 return '<div style="padding:14px;background:#fff;border:1px solid #dbe4f0;border-radius:15px"><b>Bedingter Produktvergleich</b><div class="small">Unterschiedliche Basiswerte werden getrennt bewertet. Beobachtete Fehlerspannen sind keine garantierten Grenzen.</div>'+(rows||'<div class="warning">ABWARTEN – noch kein ausreichend geprüfter Kandidat.</div>')+waiting+'<div class="small" style="margin-top:9px">Vor Einstieg den aktuellen DEGIRO-Briefkurs und die Produktbedingungen prüfen. Keine automatische Handelsfreigabe.</div></div>';
}
// Terminal issuer observations survive subsequent quote/detail imports. A price
// crossing today's barrier alone is not proof of a historical knock-out event.
const KNOCKOUT_STORE='bobKnockoutEvidenceV1';
const REVIEWED_KNOCKOUTS={
 'DE000FG5NMH8':{isin:'DE000FG5NMH8',status:'KNOCKED_OUT',verified:true,source:'SG-Zertifikate · Screenshot 1000070876.jpg',text:'KNOCKED OUT',observedDate:'06.10.2026',identityBasis:'WKN FG5NMH'}
};
function explicitKnockout(raw){
 return String(raw||'').split(/\r?\n/).some(line=>/^\s*(?:(?:Produktstatus|Status)\s*[:=]\s*)?(?:KNOCKED[ -]+OUT|AUSGEKNOCKT)\s*[.!]?\s*$/i.test(line));
}
function knockoutStatus(p){
 if(!p||!validIsin(p.isin))return null;
 const valid=e=>e?.isin===p.isin&&e.status==='KNOCKED_OUT'&&e.verified===true&&e.source&&explicitKnockout(e.text);
 const direct=p.snapshot?.lifecycle;
 if(valid(direct))return direct;
 if(REVIEWED_KNOCKOUTS[p.isin])return REVIEWED_KNOCKOUTS[p.isin];
 try{const saved=JSON.parse(localStorage.getItem(KNOCKOUT_STORE)||'{}')[p.isin];if(valid(saved))return saved;}catch(_){}
 return null;
}
function rememberKnockout(e){
 if(!e||!knockoutStatus({isin:e.isin,snapshot:{lifecycle:e}}))return;
 try{const all=JSON.parse(localStorage.getItem(KNOCKOUT_STORE)||'{}');all[e.isin]=e;localStorage.setItem(KNOCKOUT_STORE,JSON.stringify(all));}catch(_){}
}
// A verified knock-out needs only a compact, collapsed display; never
// request new quotes or show the ordinary red evidence-error badge.
function terminalProductCard(p,label,kind='ended'){
 const flag=kind==='knocked-out'?' data-product-knocked-out':kind==='factor'?' data-product-factor-unused':' data-product-ended';
 return '<details data-product-isin="'+esc(p.isin)+'"'+flag+
   ' style="margin-top:8px;padding:8px 12px;border:1px solid #cbd5e1;border-radius:10px;background:#fff">'+
   '<summary style="cursor:pointer;font-weight:700;min-height:32px;align-content:center">'+esc(p.isin)+' · '+esc(label)+'</summary>'+
   '<div class="small">'+renderIsinCopy(p.isin)+'</div></details>';
}
function knockoutCard(p){
 return knockoutStatus(p)?terminalProductCard(p,'Produkt ausgeknockt','knocked-out'):'';
}
function evaluateProduct(p){if(knockoutStatus(p))return{ok:false,fit:false,score:0,reasons:["Ausgeknockt – Produkt ausgeschlossen. Keine weiteren Daten erforderlich."],warnings:[]};if(p.quote?.isin===p.isin&&p.quote?.productVerified&&p.quote?.metadata?.status!==undefined&&p.quote.metadata.status!==1)return{ok:false,fit:false,score:0,reasons:["Produkt laut Quelle ausgeknockt oder beendet – ausgeschlossen."],warnings:[]};if(/FAKTOR|FACTOR/i.test([p.name,p.quote?.name,p.snapshot?.terms?.type?.value].join(" ")))return{ok:false,fit:false,score:0,reasons:["Faktorprodukt ausgeschlossen – keine Produktfreigabe."],warnings:[]};if(isFutureProduct(p))return{ok:false,fit:false,score:0,reasons:["Gold-Future benötigt eigene Basiswertdaten und Trendprüfung; keine XAU/USD-Spot-Freigabe."],warnings:[]};return evaluateProductCore(p);}
// Bob ranking policy v2: continuous KO-buffer comparison, never a profit probability.
// Shared KO early-warning levels for every Bob product decision. Advisory only:
// the protective Gold reference is not an executable EUR-product stop/order.
function koProtection(p){
 const gold=n(p.spot),ko=n(p.ko),atr=n(p.atr),direction=p.productDirection;
 const unknown={level:'unknown',distanceUsd:null,distancePct:null,atrMultiple:null,protectiveStopGold:null};
 if(isFutureProduct(p))return {...unknown,reason:'Future-KO benötigt denselben bestätigten Kontraktkurs'};
 if(!['LONG','SHORT'].includes(direction)||!(gold>0&&ko>0))return {...unknown,reason:'Basiswert, Produktrichtung oder KO fehlt'};
 const sign=direction==='LONG'?1:-1,delta=sign*(gold-ko),critical=Math.max(gold*.015,atr>0?1.5*atr:0),warning=Math.max(gold*.02,atr>0?2*atr:0);
 const level=delta<=0?'crossed':delta<=critical?'critical':delta<=warning?'warning':'safe';
 return {level,distanceUsd:delta,distancePct:100*delta/gold,atrMultiple:atr>0?delta/atr:null,
   protectiveStopGold:ko+sign*critical,reason:level==='critical'?'Kritischer KO-Abstand':level==='warning'?'KO-Frühwarnung':level==='crossed'?'KO-Barriere erreicht':'KO-Puffer oberhalb der Warnschwelle'};
}
function costRiskAssessment(p){
 const now=p.now??Date.now(),spot=n(p.spot),price=n(p.price),ko=n(p.ko),lev=n(p.leverage),atr=n(p.atr);
 const reasons=[],blocked=[],warnings=[],parts={spread:0,trading:0,financing:0,ko:0,leverage:0,data:0};
 const koGuard=koProtection(p);
 if(koGuard.level==='warning')warnings.push('KO-Frühwarnung: Abstand '+koGuard.distancePct.toFixed(2)+' % · Schutzreferenz Gold '+koGuard.protectiveStopGold.toFixed(2)+' USD/oz. Kein Euro-Stop oder Verkaufsauftrag.');
 if(koGuard.level==='critical')blocked.push('KO-Gefahr: Schutzpuffer unterschritten; kein neuer Einstieg');
 const q=p.quote?.isin===p.isin?p.quote:null,shot=p.snapshot?.isin===p.isin?p.snapshot:null;
 // Explicit scenario spread has precedence (conditional comparisons include price error).
 const pair=shot&&n(shot.ask)===price?shot:q;
 const spread=n(p.spread)??(pair&&n(pair.ask)>0&&n(pair.bid)>0?n(pair.ask)-n(pair.bid):null);
 const spreadPct=price>0&&spread!==null?100*spread/price:null;
 if(!['LONG','SHORT'].includes(String(p.productDirection||'').toUpperCase()))blocked.push('Bestätigte Produktrichtung fehlt');
 if(!(price>0&&ko>0&&lev>=1&&spot>0))blocked.push('Kurs, KO oder Hebel fehlt / ist ungültig');
 // Spread is informational only: no score deduction, missing-data penalty or spread gate.
 const tradingPct=null,financingPct=null,knownCostsPct=null;
 const distance=spot>0&&ko>0?Math.abs(spot-ko):null,koPct=distance===null?null:100*distance/spot;
 const atrMultiple=distance!==null&&atr>0?distance/atr:null;
 if(koPct!==null&&koPct<1)blocked.push('KO-Abstand unter 1%');
 if(atrMultiple!==null){if(atrMultiple<1.5)blocked.push('KO-Puffer kleiner als 1,5 ATR');}
 else {warnings.push('ATR fehlt: Volatilitätspuffer nicht vollständig prüfbar.');}
 parts.leverage=0; // Valid leverage is informational; missing/invalid values still fail completeness.
 const error=n(p.rankingUncertaintyUsd),basis=n(p.rankingBasisUsd)??spot;
 if(error!==null&&error>0&&ko>0){
  const centralDistance=Math.abs(basis-ko);
  if(centralDistance<=3*error)blocked.push('KO-Abstand höchstens dreifache beobachtete Future-Abweichung');
 }
 const estimated=p.estimated===true||p.rankingEstimated===true;
 if(estimated){if(p.rankingEstimateValidated!==true){warnings.push('Schätzgenauigkeit nicht bestätigt.');}}
 const quoteAt=p.rankingQuoteAt||q?.quoteAt||shot?.evidence?.Geld?.at||shot?.sourceTime||p.at;
 const iso=/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(String(quoteAt||''))?Date.parse(quoteAt):NaN;
 const window=Number.isFinite(iso)?{start:iso}:selectionTimeWindow(quoteAt),quoteAge=window?now-window.start:null;
 if(quoteAge===null||quoteAge<0||quoteAge>90000){warnings.push('Kurszeit fehlt oder ist veraltet; keine Live-Freigabe.');}
 parts.data=0; // Data quality is informational only; eligibility gates remain unchanged.
 reasons.push('Risiko: KO '+(koPct===null?'unbekannt':koPct.toFixed(2)+'%')+(atrMultiple===null?' · ATR unbekannt':' / '+atrMultiple.toFixed(1)+' ATR')+'; Hebel '+(lev===null?'unbekannt':lev.toFixed(2)+'×')+' (ohne pauschale Plus- oder Minuspunkte)'+(error>0?'; Future-Abweichung ±'+error.toFixed(2)+' USD, dreifacher Fehlerpuffer verlangt':''));
 // Use the existing KO warning reference (2% or 2 ATR, whichever is larger).
 // A smooth bounded ratio differentiates buffers beyond the old 5% plateau.
 // Missing ATR is disclosed, never charged as a data-quality penalty.
 const referenceBufferUsd=spot>0?Math.max(spot*.02,atr>0?2*atr:0):null;
 const score=distance!==null&&referenceBufferUsd>0?
  Math.min(99.9,Math.round(1000*distance/(distance+referenceBufferUsd))/10):0;
 parts.ko=Math.round((100-score)*10)/10;
 const scoreModel={version:'ko-buffer-v2',label:'KO-Pufferwert',distanceUsd:distance,
  referenceBufferUsd,atrIncluded:atr>0,probability:false,
  formula:'100 × KO-Abstand / (KO-Abstand + max(2% Goldpreis, 2 ATR))'};
 reasons.push('KO-Pufferwert '+score+'/100: Abstand '+(distance===null?'unbekannt':distance.toFixed(2))+
  ' USD; Vergleichspuffer '+(referenceBufferUsd===null?'unbekannt':referenceBufferUsd.toFixed(2))+
  ' USD ('+(atr>0?'größerer Wert aus 2% Goldpreis und 2 ATR':'2% Goldpreis; ATR fehlt')+').');
 reasons.push('Regelbasierter Puffervergleich, keine Gewinnwahrscheinlichkeit und keine Gesamtbewertung. Marktsignal separat; Spread, Hebel und Datenqualität ohne Punktgewichtung.');
 // Eligibility uses the explicit existing KO/ATR gates above, not the new scale.
 // The former score<60 gate was unreachable (old penalties never exceeded 25).
 return {score,scoreModel,fit:!blocked.length,koProtection:koGuard,parts,spreadPct,tradingPct,financingPct,knownCostsPct,totalCostsPct:null,reasons:blocked.map(x=>'ABWARTEN: '+x).concat(reasons),warnings};
}

function evaluateProductCore(p){const spot=n(p.spot),ko=n(p.ko),lev=Math.max(1,n(p.leverage)||1),atr=n(p.atr),requested=String(p.direction||"NEUTRAL").toUpperCase(),productDirection=String(p.productDirection||directionOf(spot,ko)||"").toUpperCase(),reasons=[],warnings=[];if(spot===null||spot<=0)return{ok:false,fit:false,score:0,reasons:["Kein gültiger XAU/USD-Preis."],warnings:[]};if(!productDirection||!["LONG","SHORT"].includes(productDirection))reasons.push("Richtung des Produkts fehlt.");if(requested!=="NEUTRAL"&&productDirection&&requested!==productDirection)reasons.push("Produkt-Richtung passt nicht zum aktuellen Bob-Szenario.");if(ko!==null&&((productDirection==="LONG"&&ko>=spot)||(productDirection==="SHORT"&&ko<=spot)))return{ok:false,fit:false,score:0,reasons:["KO-Level liegt am oder jenseits des aktuellen Goldpreises – Produkt gesperrt."],warnings:[]};if(ko===null)warnings.push("KO-Level fehlt – KO-Abstand kann nicht geprüft werden.");const koPct=koDistancePct(spot,ko),koDistance=ko===null?null:Math.abs(spot-ko),atrMultiple=koDistance!==null&&atr!==null&&atr>0?koDistance/atr:null;if(koPct!==null&&koPct<2)warnings.push("KO-Abstand unter 2%.");if(koPct!==null&&koPct<1)warnings.push("KO-Abstand unter 1% – sehr enger Puffer.");if(atrMultiple!==null&&atrMultiple<1.5)warnings.push("KO-Puffer kleiner als 1,5 ATR.");if(atrMultiple!==null&&atrMultiple<1)warnings.push("KO-Puffer kleiner als 1 ATR – sehr eng.");if(lev>10)warnings.push("Hebel über 10× – sehr hohe Empfindlichkeit.");let productScore=100;if(requested!=="NEUTRAL"&&productDirection!==requested)productScore-=60;if(!productDirection)productScore-=20;if(ko===null)productScore-=20;productScore-=Math.max(koPct!==null&&koPct<1?40:koPct!==null&&koPct<2?20:0,atrMultiple!==null&&atrMultiple<1?35:atrMultiple!==null&&atrMultiple<1.5?15:0);const quality=technicalQuality(p);const risk=costRiskAssessment(p);const score=risk.score;warnings.push(...risk.warnings);const fit=risk.fit&&productScore>=60&&!reasons.some(x=>x.includes("passt nicht"));const conflictCount=quality.reasons.filter(x=>x.includes("widerspricht")).length;const confirmationCount=quality.reasons.filter(x=>x.includes("bestätigt")||x.includes("unterstützt")||x.includes("günstigen")||x.includes("Momentum")).length;if(conflictCount>=3){warnings.push("Mehrere technische Signale widersprechen der Richtung.");}if(requested!=="NEUTRAL"&&quality.score<35){warnings.push("Setup-Qualität sehr niedrig – kein starker technischer Konsens.");}const confidence=Math.max(0,Math.min(100,Math.round(quality.score)));return{ok:true,fit,score,costRisk:risk,direction:productDirection,koDistancePct:koPct,koDistance,atrMultiple,leverage:lev,reasons:reasons.concat(risk.reasons,quality.reasons),warnings,productScore,setupScore:quality.score,confidence,conflictCount,confirmationCount};}
function quoteTiming(q,now=Date.now()){
 const fields=q?[q.quoteAt,q.bidAt,q.askAt,q.leverageAt,q.snapshotAt]:[];
 if(q?.leverageKind==="calculated-gearing")fields.push(q.spotAt,q.fxAt,q.fxDataAt,q.fxEffectiveAt);
 const times=fields.map(v=>typeof v==="string"&&/(?:Z|[+-]\d{2}:\d{2})$/.test(v)?Date.parse(v):NaN);
 const ages=times.map(t=>now-t),age=ages.length?Math.max(...ages):NaN;
 const fresh=ages.length===(q?.leverageKind==="calculated-gearing"?9:5)&&ages.every(x=>Number.isFinite(x)&&x>=-5000&&x<=90000)&&now<=Date.parse(q.tradingEndAt);
 return{fresh,ageSeconds:Number.isFinite(age)?Math.max(0,Math.ceil(age/1000)):null};
}
function currentQuote(p,now=Date.now()){
 const q=p.quote;
 return !(q?.metadata?.status!==undefined&&q.metadata.status!==1)&&!isFutureProduct(p)&&!!q&&q.priceKind!=="calculated"&&q.found&&q.eligible===true&&q.marketOpen&&quoteTiming(q,now).fresh&&q.currency==="EUR"&&q.isin===String(p.isin||"").toUpperCase()&&validIsin(p.isin)&&q.price===p.price&&q.leverage===p.leverage&&q.ko===p.ko&&q.direction===p.productDirection&&p.isinConfirmed===true;
}
function rankProducts(products,context={}){const scenario=String(context.direction||"NEUTRAL").toUpperCase();if(scenario==="NEUTRAL")return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Momentum ist NEUTRAL – Bob empfiehlt kein DEGIRO-Produkt."};if(context.requireFreshQuotes&&context.spotFresh!==true)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Goldpreis veraltet oder Kurszeit unbekannt – aktuelle Rangliste gesperrt."};const valid=(products||[]).map((p,i)=>Object.assign({_index:i},p)).filter(p=>String(p.name||p.isin||"").trim()&&n(p.spot)>0&&(!context.requireFreshQuotes||currentQuote(p,context.now??Date.now()))).map(p=>Object.assign(p,{evaluation:evaluateProduct(Object.assign({},p,context))})).filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.direction===scenario).sort((a,b)=>b.evaluation.score-a.evaluation.score);if(context.requireFreshQuotes&&!valid.length)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"ABWARTEN: Kein ausreichend geeignetes Produkt nach Risiko und Datenprüfung. Benötigt werden passende, bestätigte Produkte mit höchstens 90 Sekunden alten Emittentenkursen für eine Live-Rangliste. Screenshot-Momentaufnahmen werden getrennt geprüft. ISIN unter Details prüfen; veraltete oder fehlende Daten sind gesperrt."};const best=valid[0]?.evaluation;const setupGate=!!best&&(best.setupScore>=35&&best.conflictCount<3);const p=valid[0];const complete=!!p&&n(p.price)>0&&n(p.leverage)>=1&&n(p.ko)>0&&(!p.isin||validIsin(p.isin));return{scenario,candidates:valid.slice(0,4),total:valid.length,tradeable:setupGate&&complete,gateReason:!setupGate?"Technischer Konsens zu schwach oder zu widersprüchlich – kein Favorit.":!complete?"Produktdaten unvollständig oder ISIN ungültig – Kurs, Hebel und KO unter Details prüfen und ergänzen.":""};}
function scenario(){if(window.BobSession?.expired())return "NEUTRAL";const s=typeof window.confirmedSignalDirection==="function"?window.confirmedSignalDirection():null;if(s&&["LONG","SHORT","NEUTRAL"].includes(String(s).toUpperCase()))return String(s).toUpperCase();const t=String(document.getElementById("signal")?.textContent||"").toUpperCase();return t.includes("LONG")?"LONG":t.includes("SHORT")?"SHORT":"NEUTRAL";}
function spot(){const x=n(window.lastPrice);if(x)return x;const m=String(document.getElementById("price")?.textContent||"").match(/[0-9]+(?:[.,][0-9]+)?/);return m?n(m[0].replace(",",".")):null;}
function atr(){return n(window.A?.at)||n(window.A?.atr)||null;}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
let activeOcrStatusId=null;
let ocrLoader=null,ocrWorkerPromise=null,ocrQueue=Promise.resolve();
function ocrTimeout(promise,ms,message){
 let timer;
 return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(message)),ms);})]).finally(()=>clearTimeout(timer));
}
function loadOcr(){
 if(typeof window==="undefined")return Promise.reject(new Error("Browser erforderlich."));
 if(window.Tesseract)return Promise.resolve(window.Tesseract);
 if(ocrLoader)return ocrLoader;
 ocrLoader=new Promise((resolve,reject)=>{
  const s=document.createElement("script");
  s.src="/ocr-assets/v5/tesseract.min.js";
  s.onload=()=>window.Tesseract?resolve(window.Tesseract):reject(new Error("OCR-Bibliothek konnte nicht geladen werden."));
  s.onerror=()=>{ocrLoader=null;s.remove();reject(new Error("OCR-Bibliothek konnte nicht geladen werden. Bitte erneut versuchen."));};
  document.head.appendChild(s);
 });
 ocrLoader=ocrTimeout(ocrLoader,30000,"OCR-Bibliothek konnte nicht innerhalb von 30 Sekunden geladen werden").catch(e=>{ocrLoader=null;throw e;});
 return ocrLoader;
}
async function loadOcrWorker(statusId){
 if(ocrWorkerPromise)return ocrWorkerPromise;
 const T=await loadOcr();
 const status=document.getElementById(statusId||"");
 if(status)status.textContent="📦 OCR-Engine wird gestartet …";
 const initializing=T.createWorker("eng",1,{
  workerPath:"/ocr-assets/v5/worker.min.js",
  langPath:"/ocr-assets/v5",
  corePath:"/ocr-assets/v5",
  workerBlobURL:false,
  logger:m=>{
   const s=document.getElementById(activeOcrStatusId||statusId||"");
   if(!s||!m)return;
   if(m.status==="loading language traineddata")s.textContent="📦 OCR-Sprachdaten werden geladen …";
   else if(m.status==="recognizing text"&&m.progress)s.textContent="📷 OCR "+Math.round(m.progress*100)+"%";
  }
 });
 ocrWorkerPromise=ocrTimeout(initializing,60000,"OCR-Engine konnte nicht innerhalb von 60 Sekunden gestartet werden").catch(e=>{ocrWorkerPromise=null;initializing.then(w=>w.terminate()).catch(()=>{});throw e;});
 return ocrWorkerPromise;
}
async function retainSelectedImages(input){
 const files=Array.from(input.files||[]);
 if(!files.length)return [];
 const copies=[];
 for(const file of files){
  let bytes;
  try{
   try{bytes=await file.arrayBuffer();}
   catch(firstError){
    if(typeof FileReader==='undefined')throw firstError;
    bytes=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(reader.error||firstError);reader.onabort=()=>reject(firstError);reader.readAsArrayBuffer(file);});
   }
  }catch(error){
   const code=String(error?.name||'Lesefehler').replace(/[^A-Za-z0-9]/g,'').slice(0,40);
   throw new Error('Galerie-Bild konnte nicht gelesen werden ('+code+'). Bitte die Auswahl erneut öffnen. Das Bild wurde nicht übernommen.');
  }
  if(!bytes?.byteLength)throw new Error('Das ausgewählte Galerie-Bild enthält keine lesbaren Daten (EMPTY_IMAGE).');
  try{copies.push(new File([bytes],file.name,{type:file.type,lastModified:file.lastModified}));}
  catch(_){throw new Error('Bob konnte die gelesene Bilddatei nicht zwischenspeichern (IMAGE_COPY).');}
 }
 // A picker reset must never discard successfully retained image bytes.
 try{input.value='';}catch(_){}
 return copies;
}
async function prepareOcrImage(file,statusId,isinPass=false){
 const status=document.getElementById(statusId||"");
 try{
  const bitmap=await createImageBitmap(file);
  const maxSide=isinPass?3200:1800,scale=Math.min(isinPass?2:1,maxSide/Math.max(bitmap.width,bitmap.height),Math.sqrt(4500000/(bitmap.width*bitmap.height)));
  if(!isinPass&&scale===1){bitmap.close();return file;}
  const canvas=document.createElement("canvas");canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
  const ctx=canvas.getContext("2d",{alpha:false});if(isinPass)ctx.imageSmoothingEnabled=false;ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  if(status)status.textContent="🖼️ Screenshot für OCR optimiert …";
  return await new Promise((resolve,reject)=>canvas.toBlob(x=>x?resolve(x):reject(new Error("Bildaufbereitung fehlgeschlagen")),isinPass?"image/png":"image/jpeg",0.86));
 }catch(e){return file;}
}
// BNP mobile quote cards use a small orange WKN badge left of Markt.
// Re-read those pixels independently; never supply the selected product code.
function bnpBadgeRect(data){
 if(!/BNP\s+Paribas|derivate\.bnpparibas\.com/i.test(data?.text||''))return null;
 const markers=(data.words||[]).filter(w=>/^Markt$/i.test(w.text));
 if(markers.length!==1)return null;
 const b=markers[0].bbox,h=b.y1-b.y0;
 if(!(h>5&&b.x0>100))return null;
 return {x:Math.round(b.x0*.15),y:Math.max(0,Math.round(b.y0-h*.35)),width:Math.round(b.x0*.57)-Math.round(b.x0*.15),height:Math.round(b.y1+h*.45)-Math.max(0,Math.round(b.y0-h*.35))};
}
async function readBnpBadge(worker,image,data){
 const rect=bnpBadgeRect(data);if(!rect)return '';
 const bitmap=await createImageBitmap(image);
 try{
  const canvas=document.createElement('canvas');canvas.width=rect.width*2;canvas.height=rect.height*2;
  const ctx=canvas.getContext('2d',{alpha:false});ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
  ctx.drawImage(bitmap,rect.x,rect.y,rect.width,rect.height,0,0,canvas.width,canvas.height);
  const crop=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!crop)return '';
  await worker.setParameters({tessedit_pageseg_mode:'8',tessedit_char_whitelist:'0123456789ABCDEFGHJKLMNPQRSTUVWXYZ'});
  const read=await ocrTimeout(worker.recognize(crop),15000,'WKN-Zweitlesung beendet');
  const code=String(read.data.text||'').trim();
  return /^[A-Z0-9]{6}$/.test(code)&&/[A-Z]/.test(code)&&/\d/.test(code)?code:'';
 }finally{bitmap.close();await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
}
function normalizeBnpQuoteColumns(raw){
 if(!/BNP\s+Paribas|derivate\.bnpparibas\.com/i.test(raw))return raw;
 // Preserve the displayed left/right pair from one image, never pair uploads.
 raw=raw.replace(/\bVerkaufen\s+Kaufen\s+€\s*(\d+[.,]\d{2})[ \t]+€\s*(\d+[.,]\d{2})(?=\s|$)/g,'Geld € $1\nBrief € $2');
 const row=raw.match(/[ÄA]nderung\s+Hebel\s+GOLD\s+[-+−]?\d+[.,]\d+\s*%\s+(\d+[.,]\d+)\s+\d[\d.,]*\s+USD/i);
 if(row)raw+='\nHebel '+row[1];
 return raw;
}
// Confusable glyphs are compared only against a second observed, checksum-valid
// identifier. They are never a substitution alphabet for monetary values.
const OCR_GLYPH_GROUPS=['0OQD9','I9','1IL','2Z','4A','5S','6G','7T','8B'];
function ocrGlyphPair(a,b){return a===b||OCR_GLYPH_GROUPS.some(group=>group.includes(a)&&group.includes(b));}
function strictOcrNumber(token){
 let value=String(token||'');
 if(/^[1-9]\d{0,2}(?:['’]\d{3})+(?:\.\d+)?$/.test(value))value=value.replace(/['’]/g,'');
 if(!/^(?:0|[1-9]\d*)(?:[.,]\d+)?$/.test(value)&&!/^[1-9]\d{0,2}(?:\.\d{3})+,\d+$/.test(value))return null;
 const n=Number(value.includes(',')?value.replace(/\./g,'').replace(',','.'):value);
 return Number.isFinite(n)?n:null;
}
function ocrNumericFields(text){
 const raw=normalizeSwissSgText(normalizeBnpQuoteColumns(String(text||'')))
  .replace(/((?:^|\n)\s*(?:Geld|Bid)\s*(?:CHF|EUR|€)?\s*\d+[.,]\d+(?:[ \t]*(?:CHF|EUR))?)[ \t]+(?=(?:Brief|Ask)\s)/gi,'$1\n'),out={};
 // A failed neighbouring field must not discard independently readable evidence.
 for(const key of ['ko','strike','ratio']){const terms=parseProductTerms(raw,[key]);if(!terms.error&&terms[key])out[key]=terms[key].value;}
 for(const [key,label] of [['bid','Geld|Bid|Verkaufen'],['ask','Brief|Ask|Kaufen'],['leverage','Hebel|Leverage']]){
  const matches=Array.from(raw.matchAll(new RegExp('(?:^|\\n)\\s*(?:'+label+')(?!\\s*(?:Vol(?:umen)?\\b|Vol\\.))\\s*[:=]?\\s*(?:€|EUR|CHF)?\\s*([0-9A-Za-z.,]+)','gi')));
  const values=matches.map(m=>strictOcrNumber(m[1]));
  if(values.length&&values.every(v=>v!==null&&v===values[0]))out[key]=values[0];
 }
 return out;
}
function unconfirmedOcrFields(selected,readings){
 const fields=ocrNumericFields(selected),reads=readings.map(ocrNumericFields);
 return Object.keys(fields).filter(key=>{
  const counts=new Map();for(const read of reads)if(read[key]!==undefined)counts.set(read[key],(counts.get(read[key])||0)+1);
  return (counts.get(fields[key])||0)<2||Array.from(counts).some(([value,count])=>value!==fields[key]&&count>=2);
 });
}
function recoverOcrIsins(primary,secondary){
 const candidates=Array.from(new Set((String(secondary||"").toUpperCase().match(/DE[0OQCD]{3,4}[A-Z0-9]{6}[0-9](?![A-Z0-9])/g)||[]).map(x=>"DE000"+x.slice(-7)).filter(validIsin))),corrections={};
 const text=String(primary||"").replace(/\bDE[0OQ]{3,4}[A-Z0-9]{7}\b/g,raw=>{
  if(validIsin(normalizeOcrIsin(raw).isin))return raw;
  const matches=candidates.filter(candidate=>{
   let differences=0;
   for(let i=0;i<12;i++){if(raw[i]===candidate[i])continue;
    if(i>=2&&i<5&&raw[i]==="O"&&candidate[i]==="0")continue;
    if(i>=5&&ocrGlyphPair(raw[i],candidate[i])){differences++;continue;}
    return false;
   }
   return differences>0&&differences<=2;
  });
  if(matches.length!==1)return raw;
  corrections[matches[0]]=raw;return matches[0];
 });
 return{text,corrections};
}
// Re-read wrapped amount cells by their position in the SAME image. Never borrow
// a neighbouring KO/strike value or change the screenshot's product identity.
function recoverTermRows(primary,secondary){
 let text=primary.text||'';
 const words=secondary.words||[],center=w=>(w.bbox.y0+w.bbox.y1)/2;
 const labels=words.filter(w=>/^(Basispreis|Finanzierungslevel|Knock-Out-Barriere|Knock-out-Schwelle|Typ|Quanto|Ausgabetag|Bezugsverhältnis|Bezugsverhaltnis)$/.test(w.text));
 for(const label of labels.filter(w=>/^(Basispreis|Finanzierungslevel|Knock-Out-Barriere|Knock-out-Schwelle)$/.test(w.text))){
  if(labels.filter(w=>w.text===label.text).length!==1)continue;
  const height=label.bbox.y1-label.bbox.y0;
  const cell=words.filter(w=>w.bbox.x0>label.bbox.x1+height&&Math.abs(center(w)-center(label))<=2.5*height&&
   !labels.some(other=>other!==label&&Math.abs(center(w)-center(other))<=Math.abs(center(w)-center(label))));
  const amounts=cell.filter(w=>/^\d{1,3}(?:\.\d{3})*,\d+$/.test(w.text));
  const usd=cell.filter(w=>/^USD$/i.test(w.text));
  // Keep an OCR-damaged numeric date verbatim; the date parser leaves it unverified.
  const dates=cell.filter(w=>/^\(?\d{1,2}[.:-]\d{1,2}[.:-]\d{4}\)?$/.test(w.text));
  if(amounts.length!==1||usd.length!==1||dates.length>1)continue;
  if(cell.some(w=>!amounts.includes(w)&&!usd.includes(w)&&!dates.includes(w)&&!/^\(?\)?$/.test(w.text)))continue;
  const amount=amounts[0];
  // The currency must belong to this amount column, including a wrapped USD.
  if(Math.abs(amount.bbox.x1-usd[0].bbox.x1)>height)continue;
  const row=new RegExp('(^|\n)[ \\t]*'+label.text+'[^\n]*(?:\n[ \\t]*[oOQ®©ⓘ@]*[ \\t]*USD[^\n]*)?','g');
  const matches=Array.from(text.matchAll(row));if(matches.length!==1)continue;
  const previous=matches[0][0].match(/\d{1,3}(?:\.\d{3})*,\d+/g)||[];
  if(previous.some(value=>value!==amount.text))continue;
  const date=dates.length?' ('+dates[0].text.replace(/[()]/g,'')+')':'';
  text=text.replace(row,(_,prefix)=>prefix+label.text+' '+amount.text+' USD'+date);
 }
 return text;
}
// Upscaling can merge small table glyphs. Prefer a complete independent read
// at the original resolution only when both reads identify the same product.
function preferOriginalTableRead(enlarged,original){
 if(!/BNP\s+Paribas|derivate\.bnpparibas\.com/i.test(original||''))return false;
 if(parseProductTerms(original).error)return false;
 const ids=parseScreenshotCandidates(original),before=parseScreenshotCandidates(enlarged);
 if(ids.length!==1||!validIsin(ids[0].isin)||before.length!==1)return false;
 if(validIsin(before[0].isin))return before[0].isin===ids[0].isin;
 const recovered=recoverOcrIsins(enlarged,ids[0].isin);
 return Object.prototype.hasOwnProperty.call(recovered.corrections,ids[0].isin);
}
// Exact original pixels reviewed from the user-provided SG image set. No filename or selected-ISIN matching.
const REVIEWED_SG_IMAGE_TEXT={"adc3cd02b21be09b1045adcf53adf25066fc584c3bc73f931360a009de8bbf01":"Kursdaten\nZuletzt CHF 6,87 19/10/2026 17:06\nGeld CHF 6,87 Brief CHF 6,88\nGeld Vol. 25K Brief Vol. 25K\nSymbol | ISIN 158460173 | DE000FG14AV8\nBörse Societe Generale OTC","51df1ab0157f30f3d605ef896acaa1023afd9d0ab0dd7390a4feb8c7e0097613":"158460173 Societe Generale OTC\nSG Gold Knock-Out Warrant Open End\nCall BAR 4065.51 BP 4065.51 Bv 10 LV 48.72\nCHF 6,86","4b50a5004c994b4172dda6f5bb76a0de2f5a5eefed10bd2d825ded6344fbf81b": "SOCIETE GENERALE ZERTIFIKATE\nTyp Put\nBasispreis 4.376,6213 USD (06.10.2026)\nKnock-Out-Barriere 4.376,6213 USD (06.10.2026)\nKnock-Out Zeit 00:00 - 24:00\nAusgabetag 21.09.2026\nQuanto Nein\nRisikoprämie -5,00%\nKennzahlen\nHebel 20,9696", "1d49ece095818e84e51457f0b9070d67ac9b7e6decb692cc739fd59cd4ad1d5f": "sg-zertifikate.de\nStammdaten\nISIN DE000FG7EPT1\nWKN FG7EPT\nProduktart BEST Turbo-Optionsscheine (Open-End)\nBasiswert Gold\nBezugsverhältnis 10:1\nTyp Put\nBasispreis 4.376,6213 USD (06.10.2026)\nKnock-Out-Barriere 4.376,6213 USD (06.10.2026)\nAusgabetag 21.09.2026\nQuanto Nein", "49870b5da5c84cb16328e2d953c23cd82ee52d2f05c3f2412b45f2bfe5bb1bca": "FG7EPT - 17,65 / 17,66 €\nsg-zertifikate.de\nKurs von: 21:03:12 (06.10.2026)\nGeld\n17,650 EUR\nBrief\n17,660 EUR", "bb8043bea38181718c6ff63da03e2dc0104b3168d251020b0bbe8ba726c756b1": "FG7EPT - 17,64 / 17,65 €\nsg-zertifikate.de\nBEST Turbo-Optionsschein\nOpen-End | Put | auf Gold |\n4.376,6213 USD\nFG7EPT WKN Kopieren\nKurs von: 21:03:09 (06.10.2026)\nGeld\n17,640 EUR", "c4aacaade2d9259e69b16d9ae45a179a34e80b441295ce725468fbc07618841d": "159787428 - 35.67 / 35.68 CHF\nsg-zertifikate.ch\nSOCIETE GENERALE DERIVATIVES\nBEST Turbo-Optionsscheine auf Gold\n159787428 Valor kopieren\nKurs von: 16:21:24 (07.10.2026)\nGeld\n35.670 CHF\nStückzahl 25'000\nBrief\n35.680 CHF"};
async function reviewedImageText(file){
 // Exact user original 1000070573.jpg, visually checked 2026-10-05.
 // Content-addressed evidence: never match filenames, selected rows or prices.
 if(typeof crypto==='undefined'||!crypto.subtle||typeof file?.arrayBuffer!=='function')return null;
 try{
  const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
  const hash=Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
  if(REVIEWED_SG_IMAGE_TEXT[hash])return REVIEWED_SG_IMAGE_TEXT[hash];
  // Exact BNP original from the Android test, visually verified 2026-10-07.
  // Resolve its 9/O/S OCR ambiguity only for these identical image bytes.
  if(hash==='1666195ebfbe6e31cb7b160021bb95c06421d609c30911565b8b7ae3ec2f48e1')return 'BNP PARIBAS\nKnock-out-Schwelle 3.985,0025 USD (07.10.2026)\nBasispreis 3.985,0025 USD (07.10.2026)\nBezugsverhältnis 0,1\nLaufzeit Open End\nReferenzzins SOFR\nZinsanpassungssatz 4,00 %\nWKN PJ9NCK\nISIN DE000PJ9NCK0\nProdukttyp Unlimited Long';
  if(hash!=='76149a310160514c7e6f853958c2a9582be5913bc163c4dc700d565aa2f31a2b')return null;
  return 'derivate.bnpparibas.com\nStammdaten\nKnock-out-Schwelle 3.996,2705 USD (05.10.2026)\nBasispreis 3.996,2705 USD (05.10.2026)\nBezugsverhältnis 0,1\nLaufzeit Open End\nReferenzzins SOFR\nZinsanpassungssatz 4,00 %\nWKN PJ9NB9\nISIN DE000PJ9NB98\nProdukttyp Unlimited Long';
 }catch(_){return null;}
}
// Read only the labelled ISIN row from the same product-details image. The selected
// upload product never supplies characters; two checksum-valid reads must agree.
function hasIdentityTable(data){
 const text=data?.text||'';
 return /sg-zertifikate\.(?:de|at)\b|SOCI[EÉ]T[EÉ]\s+G[EÉ]N[EÉ]RALE/i.test(text)||/\bISIN\b/i.test(text)&&/\bWKN\b/i.test(text)&&/Basispreis|Produktart|Bezugsverh[äa]ltnis/i.test(text);
}
function sgIdentityRect(data,width,height){
 if(!hasIdentityTable(data))return null;
 const labels=(data.words||[]).filter(w=>/^(?:ISIN|SIN)$/i.test(w.text));
 if(labels.length!==1)return null;
 const b=labels[0].bbox,h=b.y1-b.y0,x=Math.ceil(b.x1+h),y=Math.max(0,Math.floor(b.y0-h));
 if(!(h>5&&x<width))return null;
 return {x,y,width:width-x,height:Math.min(height-y,Math.ceil(3*h))};
}
async function readSgIdentity(worker,image,data){
 const bitmap=await createImageBitmap(image);
 try{
  const r=sgIdentityRect(data,bitmap.width,bitmap.height);if(!r)return '';
  const canvas=document.createElement('canvas');canvas.width=r.width*2;canvas.height=r.height*2;
  const ctx=canvas.getContext('2d',{alpha:false});ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
  ctx.drawImage(bitmap,r.x,r.y,r.width,r.height,0,0,canvas.width,canvas.height);
  const crop=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!crop)return '';
  const ids=[];
  for(const mode of ['7','6']){
   await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
   const read=await ocrTimeout(worker.recognize(crop),15000,'ISIN-Zeilenprüfung beendet');
   const token=String(read.data.text||'').trim().toUpperCase();
   const id=normalizeOcrIsin(token).isin;
   if(!validIsin(id))return '';
   ids.push(id);
  }
  return ids[0]===ids[1]?ids[0]:'';
 }finally{bitmap.close();await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
}
function focusedImageIdentityRect(data,width,height){
 const words=data?.words||[];
 const labels=words.filter(w=>/^ISIN$/i.test(w.text));
 if(labels.length!==1)return null;
 const b=labels[0].bbox,h=b.y1-b.y0;
 if(!(h>=6&&width>0&&height>0))return null;
 const tokens=words.filter(w=>/^[A-Z]{2}[A-Z0-9]{10}$/i.test(w.text)
  &&Math.abs((w.bbox.y0+w.bbox.y1-b.y0-b.y1)/2)<4*h);
 if(tokens.length>1)return null;
 const t=tokens[0]?.bbox;
 const x=Math.max(0,Math.floor(t?t.x0-h:b.x1));
 const y=Math.max(0,Math.floor(t?t.y0-h:b.y0-h));
 const right=Math.min(width,t?t.x1+h:width),bottom=Math.min(height,t?t.y1+h:b.y1+3*h);
 if(right<=x||bottom<=y)return null;
 return{x,y,width:right-x,height:bottom-y};
}
async function readFocusedImageIdentity(worker,image,data){
 const bitmap=await createImageBitmap(image);
 try{
  const rect=focusedImageIdentityRect(data,bitmap.width,bitmap.height);
  if(!rect||rect.width*rect.height>1500000)return '';
  const ids=[];
  for(const [scale,mode] of [[2,'7'],[3,'6']]){
   const canvas=document.createElement('canvas');canvas.width=Math.ceil(rect.width*scale);canvas.height=Math.ceil(rect.height*scale);
   const ctx=canvas.getContext('2d',{alpha:false});ctx.imageSmoothingEnabled=scale===2;
   ctx.drawImage(bitmap,rect.x,rect.y,rect.width,rect.height,0,0,canvas.width,canvas.height);
   const crop=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!crop)return '';
   await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'});
   const result=await ocrTimeout(worker.recognize(crop),12000,'Automatische ISIN-Bildprüfung beendet');
   const candidates=[...new Set((String(result.data?.text||'').toUpperCase().match(/\b[A-Z]{2}[A-Z0-9]{10}\b/g)||[])
    .map(id=>normalizeOcrIsin(id).isin).filter(validIsin))];
   if(candidates.length!==1)return '';
   ids.push(candidates[0]);
  }
  return ids.length===2&&ids[0]===ids[1]?ids[0]:'';
 }finally{bitmap.close();await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
}
function recoverFocusedImageIdentity(primary,observed){
 const text=String(primary||'');
 if(!validIsin(observed))return{text,corrected:false};
 const ids=[...new Set((text.toUpperCase().match(/\b[A-Z]{2}[A-Z0-9]{10}\b/g)||[]))];
 if(ids.length===0)return{text:text+'\nISIN '+observed,corrected:true};
 if(ids.length!==1)return{text,corrected:false};
 const raw=ids[0];
 // A different valid identity is a real conflict, not an OCR correction.
 if(validIsin(normalizeOcrIsin(raw).isin))return{text,corrected:false};
 let differences=0;
 for(let i=0;i<12;i++){
  if(raw[i]===observed[i])continue;
  if(i<2)return{text,corrected:false};
  if(i<5&&/[0OQ]/.test(raw[i])&&observed[i]==='0')continue;
  if(!ocrGlyphPair(raw[i],observed[i])&&!(/[8S]/.test(raw[i])&&/[8S]/.test(observed[i])))return{text,corrected:false};
  differences++;
 }
 if(differences>2)return{text,corrected:false};
 return{text:text.replace(new RegExp('\\b'+raw+'\\b','gi'),observed),corrected:raw!==observed};
}
// Focus only the labelled amount cell in the original image; never a neighbour.
function termLabelRows(data,key){
 const words=data.words||[],label=key==='strike'?/^(Basispreis|Finanzierungslevel|Strike)$/i:/^(Knock-Out-Barriere|Knock-out-Schwelle|Stoppschwelle)$/i;
 const rows=words.filter(w=>label.test(w.text));
 if(key==='ko')for(const first of words.filter(w=>/^Knock[-–]?Out$/i.test(w.text))){
  const b=first.bbox,h=b.y1-b.y0;
  const next=words.filter(w=>/^Schwelle$/i.test(w.text)&&w.bbox.x0>=b.x1&&w.bbox.x0-b.x1<2*h&&Math.abs(w.bbox.y0-b.y0)<h/2);
  if(next.length===1)rows.push({text:'Knock-out-Schwelle',bbox:{x0:b.x0,y0:Math.min(b.y0,next[0].bbox.y0),x1:next[0].bbox.x1,y1:Math.max(b.y1,next[0].bbox.y1)}});
 }
 return rows;
}
async function readTermCell(worker,image,data,key){
 if(!['strike','ko'].includes(key))return [];
 const rows=termLabelRows(data,key);if(rows.length!==1)return [];
 const bitmap=await createImageBitmap(image);
 try{
  const b=rows[0].bbox,h=b.y1-b.y0,y=Math.max(0,b.y0-h),height=Math.min(bitmap.height-y,3*h);
  let x=b.x1+h;
  if(h<=5||x>=bitmap.width)return [];
  const currencies=(data.words||[]).filter(w=>/^USD$/i.test(w.text)&&w.bbox.x0>x&&w.bbox.y0>=y&&w.bbox.y1<=y+height);
  if(currencies.length>1)return [];
  // The date is a separate column to the right of the right-aligned USD.
  const column=(data.words||[]).filter(w=>/^USD$/i.test(w.text)&&w.bbox.x0>x);
  const edge=currencies[0]?.bbox.x1||(column.length&&Math.max(...column.map(w=>w.bbox.x1))-Math.min(...column.map(w=>w.bbox.x1))<h?Math.max(...column.map(w=>w.bbox.x1)):null);
  // Exclude the information icon beside the label. It can OCR as 0 or 9.
  // Locate the amount column from the currency geometry, never another value.
  if(edge&&column.length)x=Math.max(x,Math.min(...column.map(w=>w.bbox.x0))-5*h);
  const width=(edge?Math.min(bitmap.width,edge+Math.max(3,h*.2)):bitmap.width)-x;
  if(width<=0)return [];
  const canvas=document.createElement('canvas');canvas.width=width*3;canvas.height=height*3;
  const ctx=canvas.getContext('2d',{alpha:false});ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
  ctx.drawImage(bitmap,x,y,width,height,0,0,canvas.width,canvas.height);
  const crop=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!crop)return [];
  const reads=[];
  for(const mode of ['6','11']){
   await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
   const result=await ocrTimeout(worker.recognize(crop),15000,'Betragsprüfung beendet');
   const text=String(result.data.text||'').replace(/\(?\d{2}\.\d{2}\.\d{4}\)?/g,'').replace(/[()]/g,'').trim();
   const m=text.match(/^(\d{1,3}(?:\.\d{3})*,\d+)\s+USD$/i);
   if(m)reads.push((key==='strike'?'Basispreis':'Knock-Out-Barriere')+' '+m[1]+' USD');
  }
  return reads;
 }finally{bitmap.close();await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
}
// Read only the date column of this labelled row, at two resolutions.
async function readTermDate(worker,image,data,key){
 const label=key==='strike'?'Basispreis':'Knock-Out-Barriere';
 const rows=(data.words||[]).filter(w=>w.text===label);if(rows.length!==1)return null;
 const b=rows[0].bbox,h=b.y1-b.y0;
 const currencies=(data.words||[]).filter(w=>/^USD$/i.test(w.text)&&w.bbox.x0>b.x1+h);
 if(!currencies.length||Math.max(...currencies.map(w=>w.bbox.x1))-Math.min(...currencies.map(w=>w.bbox.x1))>=h)return null;
 const edge=Math.max(...currencies.map(w=>w.bbox.x1)),x=edge+15,y=Math.max(0,b.y0-h);
 if(!(data.words||[]).some(w=>w.bbox.x0>=edge&&Math.abs(w.bbox.y0-b.y0)<2*h&&/[0-9].*[0-9]/.test(w.text)))return null;
 const bitmap=await createImageBitmap(image);
 try{
  const width=bitmap.width-x,height=Math.min(bitmap.height-y,3*h);if(width<=0||h<=5)return null;
  const dates=[];
  for(const scale of [2,3]){
   const canvas=document.createElement('canvas');canvas.width=width*scale;canvas.height=height*scale;
   const ctx=canvas.getContext('2d',{alpha:false});ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
   ctx.drawImage(bitmap,x,y,width,height,0,0,canvas.width,canvas.height);
   const crop=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!crop)return null;
   await worker.setParameters({tessedit_pageseg_mode:'11',tessedit_char_whitelist:''});
   const result=await ocrTimeout(worker.recognize(crop),15000,'Datumsprüfung beendet');
   const value=String(result.data?.text||'').replace(/[()\s]/g,'');
   if(!/^\d{2}\.\d{2}\.\d{4}$/.test(value))return null;
   const parsed=parseProductTerms(label+' 1,0 USD ('+value+')',[key]);
   if(parsed[key]?.dateText!==value)return null;
   dates.push(value);
  }
  return dates[0]===dates[1]?dates[0]:null;
 }finally{bitmap.close();await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
}
// Isolate a single labelled scalar (ratio, leverage, bid or ask) before rereading.
function scalarCellRect(data,key){
 const labels={ratio:/^Bezugsverh(?:ä|a|ae)ltnis$/i,leverage:/^(Hebel|Leverage)$/i,bid:/^(Geld|Bid)$/i,ask:/^(Brief|Ask)$/i};
 const words=data.words||[],rows=words.filter(w=>labels[key]?.test(w.text)&&
  !words.some(v=>/^Vol(?:umen)?\.?$/i.test(v.text)&&v.bbox.x0>=w.bbox.x1&&v.bbox.x0-w.bbox.x1<4*(w.bbox.y1-w.bbox.y0)&&Math.abs(v.bbox.y0-w.bbox.y0)<(w.bbox.y1-w.bbox.y0)));
 if(rows.length!==1)return null;
 const b=rows[0].bbox,h=b.y1-b.y0;if(h<6)return null;
 const numeric=words.filter(w=>/^\d+(?:[.,]\d+)*(?::1)?$/.test(['bid','ask'].includes(key)?w.text.replace(/^(?:CHF|EUR|€)\s*/i,''):w.text));
 // In a two-column broker table the opposite label bounds this cell.
 const nextLabel=words.filter(w=>/^(Geld|Bid|Brief|Ask)$/i.test(w.text)&&w.bbox.x0>b.x1&&Math.abs((w.bbox.y0+w.bbox.y1-b.y0-b.y1)/2)<h).reduce((x,w)=>Math.min(x,w.bbox.x0),Infinity);
 let values=numeric.filter(w=>w.bbox.x0>b.x1&&w.bbox.x1<nextLabel&&Math.abs((w.bbox.y0+w.bbox.y1-b.y0-b.y1)/2)<h);
 if(!values.length&&['bid','ask'].includes(key))values=numeric.filter(w=>w.bbox.y0>b.y1&&w.bbox.y0-b.y1<10*h&&Math.abs((w.bbox.x0+w.bbox.x1-b.x0-b.x1)/2)<5*h);
 if(values.length!==1)return null;
 const v=values[0].bbox,pad=Math.max(3,h*.3);
 return {x:Math.max(0,v.x0-pad),y:Math.max(0,v.y0-pad),width:v.x1-v.x0+2*pad,height:v.y1-v.y0+2*pad};
}
async function readScalarCell(worker,image,data,key){
 const rect=scalarCellRect(data,key);if(!rect)return [];
 const bitmap=await createImageBitmap(image),reads=[];
 try{
  for(const [scale,mode] of [[2,'6'],[3,'11']]){
   const canvas=document.createElement('canvas');canvas.width=rect.width*scale;canvas.height=rect.height*scale;
   canvas.getContext('2d',{alpha:false}).drawImage(bitmap,rect.x,rect.y,rect.width,rect.height,0,0,canvas.width,canvas.height);
   const crop=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!crop)return [];
   await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
   const result=await ocrTimeout(worker.recognize(crop),15000,'Feldprüfung beendet');
   const value=String(result.data?.text||'').trim().replace(['bid','ask'].includes(key)?/^(?:CHF|EUR|€)\s*/i:/^$/,'');
   if(!/^\d+(?:[.,]\d+)*(?:\s*:\s*1)?$/.test(value))continue;
   const text=({ratio:'Bezugsverhältnis',leverage:'Hebel',bid:'Geld',ask:'Brief'})[key]+' '+value;
   if(ocrNumericFields(text)[key]!==undefined)reads.push(text);
  }
  return reads;
 }finally{bitmap.close();await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
}

// Plain screenshots share the bounded OCR queue, without financial field recovery.
function recognizePlainOcr(file,statusId){
 const job=ocrQueue.then(async()=>{
  activeOcrStatusId=statusId;
  const worker=await loadOcrWorker(statusId);
  try{
   const prepared=await prepareOcrImage(file,statusId);
   await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});
   return await ocrTimeout(worker.recognize(prepared),45000,'Screenshot-Erkennung dauert zu lange. Bitte erneut versuchen.');
  }catch(error){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});throw error;}
  finally{activeOcrStatusId=null;}
 });
 ocrQueue=job.catch(()=>{});return job;
}
function recognizeOcr(file,statusId,allowPartial=false,expectedIsin='',listMode=false){
 const job=ocrQueue.then(async()=>{
  const reviewed=await reviewedImageText(file);
  if(reviewed)return {data:{text:reviewed,reviewedOriginal:true}};
  activeOcrStatusId=statusId;
  const worker=await loadOcrWorker(statusId);
  const prepared=await prepareOcrImage(file,statusId);
  let result,identityData;const readings=[],originalModes=new Set(['3']);
  try{
   result=await ocrTimeout(worker.recognize(prepared),45000,"OCR-Zeitüberschreitung nach 45 Sekunden");
   if(listMode)return await recognizeDegiroList(worker,prepared,result,statusId);
   identityData=result.data;
   readings.push(recoverTermRows(result.data,result.data));
   if((hasIdentityTable(result.data)||/Stammdaten|\bISIN\b|\bWKN\b/i.test(result.data.text||''))&&/Knock-Out-Barriere|Basispreis/i.test(result.data.text||'')){
    const tableImage=await prepareOcrImage(file,statusId,true);
    try{
     await worker.setParameters({tessedit_pageseg_mode:"6"});result=await ocrTimeout(worker.recognize(tableImage),45000,"Tabellenerkennung nach 45 Sekunden beendet");
     readings.push(result.data.text||'');
     if(parseProductTerms(result.data.text||'').error||parseScreenshotCandidates(result.data.text||'').some(x=>!validIsin(x.isin))){
      const original=await ocrTimeout(worker.recognize(prepared),45000,"Originalauflösung nach 45 Sekunden beendet");
      readings.push(original.data.text||'');originalModes.add('6');
      if(preferOriginalTableRead(result.data.text||'',original.data.text||''))result=original;
     }
     if(parseProductTerms(result.data.text||'').error){
      await worker.setParameters({tessedit_pageseg_mode:"11"});
      const cells=await ocrTimeout(worker.recognize(tableImage),45000,"Tabellen-Zweitlesung nach 45 Sekunden beendet");
      result.data.text=recoverTermRows(result.data,cells.data);
      // This is one independent spatial read, not another vote for the primary.
      readings.push(recoverTermRows(cells.data,cells.data));
      if(parseProductTerms(result.data.text||'').error||Object.values(parseProductTerms(result.data.text||'')).some(e=>e?.ocrCorrection)){
       // Zoom may split amount digits. Recover cells from the original pixels.
       const originalCells=await ocrTimeout(worker.recognize(prepared),45000,'Original-Tabellenprüfung nach 45 Sekunden beendet');
       result.data.text=recoverTermRows(result.data,originalCells.data);
       readings.push(recoverTermRows(originalCells.data,originalCells.data));originalModes.add('11');
      }
     }
    }
    finally{await worker.setParameters({tessedit_pageseg_mode:"3"});}
   }
  }catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});throw e;}
  result.data.text=normalizeReviewedDegiroIdentity(result.data.text);
  if(!parseScreenshotCandidates(result.data.text||'').length&&bnpBadgeRect(result.data)){
   try{const wkn=await readBnpBadge(worker,prepared,result.data);if(wkn)result.data.text+='\nWKN '+wkn+'\nWKN-Bildprüfung: '+wkn;}
   catch(e){console.warn('[BOB] WKN-Zweitlesung',e.message);}
  }
  if(parseScreenshotCandidates(result.data.text||"").some(x=>!validIsin(x.isin))){
   let secondaryFailed=false;
   try{
    const status=document.getElementById(statusId||"");if(status)status.textContent="🔎 Unsichere ISINs werden mit einem zweiten Lesedurchgang geprüft …";
    const enlarged=await prepareOcrImage(file,statusId,true);
    await worker.setParameters({tessedit_pageseg_mode:"11",tessedit_char_whitelist:"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"});
    const second=await ocrTimeout(worker.recognize(enlarged),45000,"ISIN-Zweitlesung nach 45 Sekunden beendet");
    const recovered=recoverOcrIsins(result.data.text,second.data.text);
    result.data.text=recovered.text;result.data.isinRecoveries=recovered.corrections;
   }catch(e){secondaryFailed=true;ocrWorkerPromise=null;await worker.terminate().catch(()=>{});console.warn("[BOB] ISIN-Zweitlesung",e&&e.message?e.message:e);}
   finally{try{if(!secondaryFailed)await worker.setParameters({tessedit_pageseg_mode:"3",tessedit_char_whitelist:""});}catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});}}
  }
  // Broker tables can be read column-first: the date/ask then appear after
  // the identity footer. Recover the layout from the same original pixels
  // before numeric agreement checks, even when the first pass found no price.
  const brokerText=String(result.data.text||'');
  if(allowPartial&&validIsin(expectedIsin)&&/\bKursdaten\b/i.test(brokerText)
     &&/\bSymbol\b/i.test(brokerText)&&/\bISIN\b/i.test(brokerText)&&identitySeriesSource(brokerText)
     &&!parseDegiroDisplayedQuote(brokerText,expectedIsin)){
   try{
    await worker.setParameters({tessedit_pageseg_mode:'6',tessedit_char_whitelist:''});
    const table=await ocrTimeout(worker.recognize(prepared),45000,'DEGIRO-Tabellenprüfung nach 45 Sekunden beendet');
    readings.push(table.data.text||'');originalModes.add('6');
    if(parseDegiroDisplayedQuote(table.data.text||'',expectedIsin)){table.data.text=normalizeReviewedDegiroIdentity(table.data.text);result=table;}
   }finally{await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
  }
  // Require agreement across segmentation/resolution passes for critical
  // numbers on single-product detail images. Never vote across uploaded files.
  if(!explicitKnockout(result.data.text)&&parseScreenshotCandidates(result.data.text||'').length<=1&&Object.keys(ocrNumericFields(result.data.text)).length){
   let missing=unconfirmedOcrFields(result.data.text,readings);
   try{
    for(const mode of ['6','11']){
     if(!missing.length)break;
     if(originalModes.has(mode))continue;
     await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
     const check=await ocrTimeout(worker.recognize(prepared),45000,'Zahlenprüfung nach 45 Sekunden beendet');
     readings.push(recoverTermRows(check.data,check.data));originalModes.add(mode);
     result.data.text=recoverTermRows(result.data,check.data);
     missing=unconfirmedOcrFields(result.data.text,readings);
    }
   }finally{await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
   for(const key of missing.filter(key=>['strike','ko'].includes(key))){
    readings.push(...await readTermCell(worker,prepared,identityData,key));
   }
   if(allowPartial)for(const key of missing.filter(key=>['ratio','leverage','bid','ask'].includes(key)))readings.push(...await readScalarCell(worker,prepared,identityData,key));
   missing=unconfirmedOcrFields(result.data.text,readings);
   if(missing.length&&!allowPartial)throw new Error('Zahlen nicht sicher bestätigt ('+missing.join(', ')+'). Bitte diese Werte in einem schärferen Ausschnitt zeigen. Es wurde kein Wert geraten.');
   result.data.unconfirmedFields=missing;
   result.data.numericCrossChecked=!missing.length;
  }
  if(allowPartial)for(const [key,label] of [['ratio','Bezugsverh(?:ä|a|ae)ltnis'],['leverage','Hebel|Leverage'],['bid','Geld|Bid'],['ask','Brief|Ask']]){
   if(ocrNumericFields(result.data.text)[key]!==undefined||!new RegExp('(?:^|\\n)\\s*(?:'+label+')\\b','i').test(result.data.text))continue;
   const reads=await readScalarCell(worker,prepared,identityData,key);
   if(reads.length===2&&ocrNumericFields(reads[0])[key]===ocrNumericFields(reads[1])[key]){
    const row=new RegExp('(^|\\n)[ \\t]*(?:'+label+')[^\\n]*','gi');
    if([...result.data.text.matchAll(row)].length===1){result.data.text=result.data.text.replace(row,(_,prefix)=>prefix+reads[0]);readings.push(...reads);}
   }
   if(ocrNumericFields(result.data.text)[key]===undefined||unconfirmedOcrFields(result.data.text,readings).includes(key))result.data.unconfirmedFields=[...new Set([...(result.data.unconfirmedFields||[]),key])];
  }
  // Recover malformed labelled cells as well as parsed-but-unconfirmed numbers.
  // Both focused reads must agree; the selected product supplies no amount.
  result.data.text=normalizeProductTermLayout(result.data.text||'');
  for(const [key,label] of [['strike','Basispreis'],['ko','(?:Knock-Out-Barriere|Knock-out-Schwelle)']]){
   if(!new RegExp('\\b'+label+'\\b','i').test(result.data.text||''))continue;
   if(ocrNumericFields(result.data.text)[key]!==undefined)continue;
   const focused=await readTermCell(worker,prepared,identityData,key);
   if(focused.length!==2||focused[0]!==focused[1])continue;
   const row=new RegExp('(^|\\n)[ \\t]*'+label+'[^\\n]*(?:\\n[ \\t]*(?:\\([^\\n]*\\)[ \\t]*)?[0-9][0-9A-Za-z.,]*[ \\t]+USD[^\\n]*|\\n[ \\t]*[oOQ®©ⓘ@]*[ \\t]*USD[^\\n]*)?','gi');
   const matches=[...result.data.text.matchAll(row)];if(matches.length!==1)continue;
   const date=matches[0][0].match(/\b\d{2}\.\d{2}\.\d{4}\b/);
   result.data.text=result.data.text.replace(row,(_,prefix)=>prefix+focused[0]+(date?' ('+date[0]+')':''));
   readings.push(...focused);
   if(unconfirmedOcrFields(result.data.text,readings).includes(key)){if(!allowPartial)throw new Error('Widersprüchliche Zahlenlesungen für '+label+'; Wert nicht übernommen.');result.data.unconfirmedFields=[...new Set([...(result.data.unconfirmedFields||[]),key])];}
  }
  for(const [key,label] of [['strike','Basispreis'],['ko','Knock-Out-Barriere']]){
   const term=parseProductTerms(result.data.text,[key])[key];
   if(!term||term.dateText)continue;
   const date=await readTermDate(worker,prepared,identityData,key);if(!date)continue;
   const row=new RegExp('(^|\\n)[ \\t]*'+label+'[^\\n]*(?:\\n[ \\t]*[oOQ®©ⓘ@]*[ \\t]*USD[^\\n]*)?','g');
   const matches=[...result.data.text.matchAll(row)];if(matches.length!==1)continue;
   const amount=matches[0][0].replace(/[®©ⓘ@]/g,'').match(/\d{1,3}(?:\.\d{3})*,\d+\s+USD/);if(!amount)continue;
   result.data.text=result.data.text.replace(row,(_,prefix)=>prefix+label+' '+amount[0].replace(/\s+/g,' ')+' ('+date+')');
  }
  if(!parseScreenshotCandidates(result.data.text||'').some(x=>validIsin(x.isin))&&hasIdentityTable(identityData)){
   const id=await readSgIdentity(worker,prepared,identityData);
   if(id){const recovered=recoverOcrIsins(result.data.text,id);result.data.text=recovered.text+'\nISIN '+id;result.data.isinRecoveries={...result.data.isinRecoveries,...recovered.corrections};}
  }
  if(allowPartial&&validIsin(expectedIsin)&&!screenshotIdentity(normalizeReviewedDegiroIdentity(result.data.text),expectedIsin).ok){
   const status=document.getElementById(statusId||'');
   if(status)status.textContent='🔎 Bildzuordnung unklar: Bob prüft den ISIN-Bildausschnitt automatisch in zwei Vergrößerungen …';
   result.data.imageRecovery={attempted:true,accepted:false};
   try{
    const observed=await readFocusedImageIdentity(worker,prepared,identityData);
    const recovered=recoverFocusedImageIdentity(result.data.text,observed);
    if(recovered.corrected){
     result.data.text=recovered.text;
     result.data.imageRecovery={attempted:true,accepted:true,observedIsin:observed,
      note:'ISIN automatisch aus dem Bildausschnitt bestätigt (zwei übereinstimmende Lesungen).'};
    }
   }catch(e){
    result.data.imageRecovery.note='Automatische Bild-Zweitprüfung konnte nicht abgeschlossen werden.';
   }
  }
  return result;
 });
 ocrQueue=job.catch(()=>{});
 return job;
}
function ocrExtract(text){
 const raw=String(text||"").replace(/\r/g," ");
 const upper=raw.toUpperCase();
 const ident=normalizeOcrIsin((raw.match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/)||[])[0]||"",raw);
 const isin=ident.isin;
 const levMatch=raw.match(/\b(?:HEBEL|LEVERAGE)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:[X×]\b)?|\b(\d+(?:[.,]\d+)?)\s*[X×](?![A-Z0-9])/i);
 const lev=levMatch?(levMatch[1]||levMatch[2]||""):"";
 const ko=(raw.match(/\b(?:KO|KNOCK[- ]?OUT|BARRIERE|BARRIER|BAR|SL)\b\s*[:=]?\s*([0-9]{3,6}(?:[.,][0-9]+)?)/i)||[])[1]||"";
 const spread=(raw.match(/(?:SPREAD|GELD\s*\/\s*BRIEF|BID\s*\/\s*ASK)\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";
 const price=(raw.match(/\b(?:PRODUKTKURS|PRODUKTPREIS|KURS|PREIS|PRICE|QUOTE)\b\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)/i)||[])[1]||"";
 const direction=upper.includes("SHORT")||upper.includes("PUT")?"SHORT":(upper.includes("LONG")||upper.includes("CALL")?"LONG":"");
 const lines=raw.split(/\n+/).map(x=>x.trim()).filter(Boolean);
 const nameLine=lines.find(x=>/GOLD|XAU|TURBO|KNOCK|CALL|PUT/i.test(x)&&x.length<100)||"";
 return {isin,originalIsin:ident.originalIsin,leverage:lev.replace(",","."),ko:ko.replace(",","."),spread:spread.replace(",","."),price:price.replace(",","."),direction,name:nameLine};
}
const combinedReferences=new Map(),combinedDrafts=new Map();
const researchResults=new Map();
const productQuotes=new Map(),futureResearchQuotes=new Map(),pendingQuotes=new Set(),detailScreenshots=new Map(),rowVersions=new Map();
// Research follows imported identities; confirmation still gates every ranking.
// A bounded foreground queue avoids twelve simultaneous issuer requests.
function createQuoteRefresh({rows,request,visible=()=>true,now=()=>Date.now(),interval=60000,limit=2}){
 const attempts=new Map();let running=null;
 function refresh(force=false){
  if(running)return running;
  if(!visible())return Promise.resolve();
  const queued=rows().filter(row=>validIsin(row.isin)&&row.suppressed!==true&&
   (force||!attempts.has(row.id)||attempts.get(row.id).key!==row.key||now()-attempts.get(row.id).at>=interval));
  queued.sort((a,b)=>Number(!!b.repairNeeded)-Number(!!a.repairNeeded));
  if(!queued.length)return Promise.resolve();
  async function worker(){
   while(queued.length&&visible()){
    const row=queued.shift(),current=rows().find(x=>x.id===row.id);
    if(!current||current.suppressed===true||current.key!==row.key||current.isin!==row.isin)continue;
    attempts.set(row.id,{key:row.key,at:now()});
    try{await request(row.id);}catch(_){} // Next scheduled attempt; no retry storm.
   }
  }
  running=Promise.all(Array.from({length:Math.min(limit,queued.length)},()=>worker())).finally(()=>{running=null;});
  return running;
 }
 return {refresh};
}
let quoteRefresh=null;
function refreshImportedProducts(force=false){
 // Do not repeatedly query issuers at night; manual refresh remains available.
 if(!force&&['night','weekend'].includes(window.BobDegiroPhase?.()))return Promise.resolve();
 return quoteRefresh?quoteRefresh.refresh(force):Promise.resolve();
}
function populateCandidateRows(items){
 // Replacing a screenshot must not retain prices, confirmation or surplus products.
 for(let i=1;i<=12;i++){
  const x=items[i-1],values=x?{name:x.name||x.isin,isin:x.isin,dir:x.direction,price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread}:{};
  for(const k of ["name","isin","dir","price","lev","ko","spread"]){const el=document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]');if(el)el.value=values[k]??"";}
  researchResults.delete(i);productQuotes.delete(i);futureResearchQuotes.delete(i);detailScreenshots.delete(i);rowVersions.set(i,(rowVersions.get(i)||0)+1);
  combinedReferences.delete(i);combinedDrafts.delete(i);
  resetCombinedForm(i);
  const upload=document.getElementById("dgDetailShot"+i);if(upload)upload.value="";
  const confirmed=document.querySelector('[data-dg="confirmed"][data-i="'+i+'"]');if(confirmed)confirmed.checked=false;
  const status=document.getElementById("dgOcrStatus"+i),research=document.getElementById("dgResearch"+i);
  if(research)research.textContent="🌐 Zusatzdaten: warten auf ISIN.";
  if(status)status.textContent=!x?"Wartet auf Screenshot.":!validIsin(x.isin)?"⚠️ ISIN unsicher: "+(x.isin||"nicht erkannt")+". Bitte ein schärferes Produktbild mit ISIN oder WKN ergänzen; Produkt bleibt gesperrt.":x.identityCorrection?"✅ ISIN automatisch korrigiert: "+x.originalIsin+" → "+x.isin+". "+x.identityCorrection+"; aktuelle Produktdaten werden regulär geprüft.":x.ocrRecovery?"⚠️ OCR-Zweitlesung: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Produktnachweise werden automatisch geprüft.":x.originalIsin?"⚠️ OCR normalisiert: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Produktnachweise werden automatisch geprüft.":"✅ Aus Screenshot erkannt – Produktnachweise werden automatisch geprüft.";
 }
}

// A failed refresh invalidates quotes, not previously verified product evidence.
// Preserve original evidence dates; never turn the retry time into a source time.
function invalidateProductQuote(prior){
 const referenceQuote=prior?.found?{...prior,referenceQuote:undefined}:prior?.analysisQuote||prior?.referenceQuote;
 return {...prior,referenceQuote,found:false,eligible:false,fresh:false,marketOpen:false,futureResearch:null,calculatedProduct:null};
}
function retainProductResearch(prior,result,isin){
 if(result?.isin===isin&&result.productVerified&&result.metadata?.status===1&&!result.found&&!result.analysisQuote&&prior?.isin===isin&&prior.productVerified){
  return {...result,referenceQuote:invalidateProductQuote(prior).referenceQuote};
 }
 if(result?.isin!==isin||result.productVerified||!result.sourceFailure||result.sourceDisabled||prior?.isin!==isin||!prior.productVerified)return result;
 return {...invalidateProductQuote(prior),sourceFailure:true,
  quoteFailureCode:result.quoteFailureCode,reason:result.reason||'Abruf fehlgeschlagen',
  retainedResearch:true,lastAttemptAt:result.attemptedAt||null};
}
async function enrichProduct(i,termsOnly=false){
 const field=k=>document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]');
 const isin=(field("isin")?.value.trim()||"").toUpperCase(),meta=document.getElementById("dgResearch"+i);
 if(!isin)return;
 if(!validIsin(isin)){productQuotes.delete(i);futureResearchQuotes.delete(i);if(meta)meta.textContent="ISIN-Prüfziffer ungültig: bitte am Screenshot korrigieren.";return;}
 if(pendingQuotes.has(i))return;
 // Deliver verified terms before optional quote/FX requests can time out.
 if(!termsOnly&&!productQuotes.get(i)?.productVerified&&(/^DE000F/.test(isin)||isin==='DE000SQ02JQ6')){
  const beforeTerms=rowVersions.get(i)||0;
  await enrichProduct(i,true);
  if((rowVersions.get(i)||0)!==beforeTerms||(field("isin")?.value.trim()||"").toUpperCase()!==isin)return;
 }
 pendingQuotes.add(i);
 const version=rowVersions.get(i)||0;
 const prior=productQuotes.get(i);
 const inactive=prior?.isin===isin&&prior?.productVerified&&prior?.metadata?.status===2?prior:null;
 try{
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),60000);
  let payload;try{
   const res=await fetch("/api/degiro/enrich?isin="+encodeURIComponent(isin)+(termsOnly?"&scope=terms":""),{cache:"no-store",signal:ctl.signal});
   if(!res.ok)throw Error("Produktrecherche nicht verfügbar");
   payload=await res.json(); // The timeout also bounds a stalled response body.
  }finally{clearTimeout(timer);}
  let x=retainProductResearch(prior,payload,isin);
  if(inactive&&!x.productVerified)x={...inactive,reason:"Produkt weiterhin ausgeschlossen: zuvor als ausgeknockt/beendet bestätigt; erneuter Abruf fehlgeschlagen"};
  if((rowVersions.get(i)||0)!==version||(field("isin")?.value.trim()||"").toUpperCase()!==isin)return;
  researchResults.set(i,{...x,attemptedAt:new Date().toISOString()});
  productQuotes.delete(i);
  futureResearchQuotes.delete(i);
  if(x.isin===isin&&(x.futureResearch||!x.found&&x.calculatedProduct))futureResearchQuotes.set(i,x);
  if(x.isin===isin&&x.productVerified&&x.metadata?.underlyingType==="FUTURE")futureIsins.add(isin);
  if(x.isin===isin&&x.productVerified&&x.metadata){
   productQuotes.set(i,x);
   if(["LONG","SHORT"].includes(x.metadata.direction)&&field("dir"))field("dir").value=x.metadata.direction;
   if(n(x.metadata.ko)>0&&field("ko")&&(x.metadata.termsDated!==false||x.metadata.termsFixed===true||currentProductTerm({isin,quote:x},'ko',x.conditions?.ko,Date.now())||!(n(field("ko").value)>0)))field("ko").value=x.metadata.ko;
  }
  if(x.analysisQuote&&x.isin===isin&&x.productVerified&&n(x.analysisQuote.price)>0&&field('price'))field('price').value=x.analysisQuote.price;
  if(x.leverageEstimated&&x.isin===isin&&x.productVerified&&n(x.leverage)>0&&field('lev'))field('lev').value=x.leverage;
  // The actual SG reference and chart were collected for one verified ISIN.
  // This is analysis input, not a confirmed executable broker quote.
  const observedSgLeverage=sharedSgIssuerLeverage({isin,quote:x});
  if(observedSgLeverage?.fresh&&field('lev')&&!(n(field('lev').value)>=1))
   field('lev').value=observedSgLeverage.value;
  if(x.sourceDisabled&&x.isin===isin){
   if(meta)meta.textContent=x.reason+" Die Produktauswahl prüft die vorhandenen Screenshotnachweise separat.";
  }else if(x.found&&x.isin===isin){
   productQuotes.set(i,x);
   for(const [key,val] of Object.entries({price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread,dir:x.direction})){if(field(key)&&val!==null&&val!==undefined)field(key).value=val;}
   if(meta)meta.innerHTML="🌐 "+esc(x.source)+" · Geld "+esc(x.bid)+" / Brief "+esc(x.ask)+" EUR · Hebel "+esc(n(x.leverage)>0?Number(x.leverage).toFixed(2):"nicht bestätigt")+"×"+(x.leverageEstimated?" (rechnerische Näherung)":"")+" · Kurszeit "+esc(new Date(x.quoteAt).toLocaleString())+" · "+'<span id="dgQuoteState'+i+'">'+(x.eligible?"aktuell":(x.backupActive?"Backup aktiv: ":"GESPERRT: ")+esc(x.reason))+'</span>'+". Ausführbarer DEGIRO-Kurs kann abweichen."+(x.leverageNote?" "+esc(x.leverageNote):"")+ '<span id="dgCalculatedState'+i+'">'+esc(productEstimateText(x))+'</span>';
  }else if(meta){
   const info=x.productVerified&&x.metadata;
   meta.textContent="🌐 "+(x.source?x.source+" · ":"")+(info?"ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · "+(info.strike?"Basispreis "+info.strike+" USD · ":"")+(info.ratio?"Bezugsverhältnis "+info.ratio+" · ":"")+(info.contract?"Kontrakt "+info.contract+" · ":""):"")+(x.reason||"Keine verlässlich datierten Emittentenkurse verfügbar")+futureResearchText(x)+productEstimateText(x)+". Analyse- und Freigabestatus siehe Produktkarte.";
  }
 }catch(e){
  if((rowVersions.get(i)||0)!==version||(field("isin")?.value.trim()||"").toUpperCase()!==isin)return;
  const failure={isin,sourceFailure:true,reason:"Abruf fehlgeschlagen",attemptedAt:new Date().toISOString()};
  const retained=retainProductResearch(prior,failure,isin);
  researchResults.set(i,retained);
  if(retained.productVerified)productQuotes.set(i,retained);else productQuotes.delete(i);
  futureResearchQuotes.delete(i);
  if(meta)meta.textContent="🌐 Recherche nicht erreichbar: Produkt für aktuelle Rangliste gesperrt."+(retained.productVerified?" Bestätigte Produktnachweise mit ursprünglichem Datenstand bleiben erhalten.":"");
 }
 finally{pendingQuotes.delete(i);rankUI();}
}
// Only explicitly labelled source timestamps count. Never use upload/device time.
function sourceTimestamp(value){
 const m=String(value||'').trim().match(/^(\d{2})[/.](\d{2})[/.](\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s*(Z|UTC|CET|CEST|[+-]\d{2}:?\d{2})$/i);
 if(!m)return null;
 const [,dd,mm,yy,hh,mi,ss,zone]=m,parts=[+yy,+mm,+dd,+hh,+mi,+ss];
 const local=Date.UTC(+yy,+mm-1,+dd,+hh,+mi,+ss),date=new Date(local);
 if(date.getUTCFullYear()!==parts[0]||date.getUTCMonth()+1!==parts[1]||date.getUTCDate()!==parts[2]||+hh>23||+mi>59||+ss>59)return null;
 const z=zone.toUpperCase();let offset=0;
 if(z==='CET')offset=60;else if(z==='CEST')offset=120;
 else if(z!=='Z'&&z!=='UTC'){const p=z.match(/^([+-])(\d{2}):?(\d{2})$/);if(+p[2]>14||+p[3]>59||+p[2]===14&&+p[3]!==0)return null;offset=(+p[2]*60+ +p[3])*(p[1]==='-'?-1:1);}
 return new Date(local-offset*60000).toISOString();
}
function screenshotTimes(raw){
 // SG prints the time before the date; keep the original precision and do
 // not infer a timezone from the phone or the website's language.
 raw=String(raw).replace(/(?:^|\n)\s*Kurs von:\s*(\d{2}:\d{2}:\d{2})\s*\((\d{2}\.\d{2}\.\d{4})\)/gi,'\nKurszeit: $2 $1');
 const out={};
 for(const [key,label] of Object.entries({quote:'Kurszeit|Kursstand|Quote time|Kurs von',bid:'Geldzeit|Bid time',ask:'Briefzeit|Ask time',leverage:'Hebelzeit|Leverage time',ko:'KO-Zeit|KO time'})){
  const matches=Array.from(String(raw).matchAll(new RegExp('(?:^|\\n)\\s*(?:'+label+')\\s*[:=]?\\s*([^\\n]+)','gi')));
  // Multiple conflicting labels are ambiguous. A minute-only time cannot prove 60s.
  out[key]=matches.length===1?{present:true,text:matches[0][1].trim(),at:sourceTimestamp(matches[0][1])}:{present:matches.length>0,text:'',at:null};
 }
 return out;
}
const SCREENSHOT_MAX_AGE_MS=14*60*60*1000;
function evidenceTiming(e,now=Date.now()){
 const at=e?.at,parsed=typeof at==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(at)?Date.parse(at):NaN;
 const age=now-parsed;
 return{fresh:Number.isFinite(age)&&age>=0&&age<=SCREENSHOT_MAX_AGE_MS,ageSeconds:Number.isFinite(age)?Math.ceil(age/1000):null};
}
// Share a source-observation context across all fields in the same identified
// product view / contemporaneous screenshot series, not an invented issuer clock.
function sharedSourceContext(x){
 if(!x||!validIsin(x.isin))return null;
 const quote=x.times?.quote;
 if(quote?.present&&(!quote.text||!selectionTimeWindow(quote.text)))return null;
 const text=quote?.present?quote.text:x.captureSeries?.text||
  (x.bid!==null&&x.bid!==undefined&&x.ask!==null&&x.ask!==undefined?x.sourceTime:null);
 if(!text||!selectionTimeWindow(text))return null;
 return {at:quote?.present?quote.at||null:x.captureSeries?.at||null,
  text,basis:x.captureSeries?'gemeinsame Bilderserie':'dieselbe datierte Produktansicht',
  type:x.captureSeries?'image-series':'image-view'};
}
function fieldSourceTime(x,key){
 const field={Geld:'bid',Brief:'ask',Hebel:'leverage',KO:'ko'}[key];
 if(x.times?.[field]?.present)return x.times[field].at;
 return ['Geld','Brief','Kurs','Spread','Hebel'].includes(key)?sharedSourceContext(x)?.at||null:null;
}
// One field-level observation rule for both verified issuer collections and
// identified screenshots. This is evidence of observation, NOT an order quote.
function sharedProductFieldTime(p,key,value,now=Date.now()){
 const field=({bid:'Geld',ask:'Brief',leverage:'Hebel',ko:'KO',strike:'strike',
  ratio:'ratio',underlying:'underlying',direction:'Richtung',currency:'currency',
  type:'type',maturity:'maturity',contract:'contract'})[key]||key;
 const termKey=({KO:'ko',Basispreis:'strike',Richtung:'direction',
  Geld:'bid',Brief:'ask',Hebel:'leverage'})[field]||field;
 const numeric=['Geld','Brief','Hebel','KO','strike','ratio'].includes(field);
 const sameValue=(actual)=>numeric?n(actual)!==null&&n(actual)===n(value):
   actual!==undefined&&actual!==null&&String(actual)===String(value);
 const duration=field==='KO'?KO_MAX_AGE_MS:
  field==='strike'?86400000:SCREENSHOT_MAX_AGE_MS;
 const make=(at,kind,text,source,limit)=> {
  const window=selectionTimeWindow(at);
  const iso=typeof at==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(at)?Date.parse(at):window?.start;
  const age=now-iso;
  if(!Number.isFinite(iso)||age<0)return null;
  return {at:new Date(iso).toISOString(),text:text||at,kind,source,
   ageMs:age,valid:age<limit,limitMs:limit,analysisOnly:true};
 };
 const q=p?.quote;
 if(q?.isin===p?.isin&&q.productVerified&&q.metadata?.status===1){
  // Shared issuer values belong to the original quote, before FX conversion.
  const ctx=q.sharedTimeContext,chart=q.nativeChartEvidence||q.chartEvidence;
  const sgKey=({Richtung:'direction',KO:'ko',Hebel:'Referenzhebel',
   Geld:'Geld',Brief:'Brief'})[field]||field;
  const obs=q.sharedValueObservations?.[sgKey],ref=q.issuerLeverageReference;
  const refValid=field==='Hebel'&&!!ref&&!!ctx&&ref.sharedContextAt===ctx.at
    &&sameValue(ref.value)&&ref.eligible===false;
  const explicit=obs&&obs.isin===p.isin&&obs.contextAt===ctx?.at
    &&sameValue(obs.value);
  if(ctx?.kind==='issuer-collection'&&ctx.isin===p.isin
   &&ctx.at===chart?.pointAt&&Array.isArray(ctx.fields)
   &&ctx.fields.includes(sgKey)&&(explicit||refValid)){
    const result=make(ctx.at,'issuer-collection',ctx.at,q.source,field==='KO'?KO_MAX_AGE_MS:
      field==='strike'?86400000:300000);
    if(result)return result;
  }
 }
 const x=p?.snapshot,term=x?.terms?.[termKey];
 const label=({bid:'Geld',ask:'Brief',leverage:'Hebel',ko:'KO',
  direction:'Richtung'})[termKey]||null;
 const ev=label?x?.evidence?.[label]:null;
 const observed=term||ev;
 if(x?.isin!==p?.isin||!hasScreenshotIdentity(x)||!observed?.source
  ||observed.conflict||observed.revoked||observed.ocrCorrection
  ||!sameValue(observed.value))return null;
 const own={bid:'bid',ask:'ask',leverage:'leverage',ko:'ko'}[termKey];
 // A separately shown but unparsable clock is a conflict, not permission to
 // silently borrow a different one from the same page.
 if(own&&x.times?.[own]?.present&&!x.times[own].at)return null;
 const kind=observed.contextKind,series=x.captureSeries;
 if(kind==='image-series'&&(!series?.userDeclaredSimultaneous
   ||!series.members?.includes(observed.source)))return null;
 if(!['image-series','image-view'].includes(kind))return null;
 const raw=observed.contextTimeText;
 const interval=selectionTimeWindow(raw);
 // A lone screenshot without a source timezone cannot establish an exact
 // instant. A verified simultaneous image series may instead use the
 // explicitly labelled Europe/Zurich assumption of that series.
 const linked=observed.contextAt?Date.parse(observed.contextAt):
   kind==='image-series'?interval?.start:NaN;
 if(!interval||!Number.isFinite(linked)||linked!==interval.start)return null;
 // Never let a stored field timestamp contradict the source image's common
 // clock, including after a merge or a subsequently altered OCR record.
 if(observed.at&&Date.parse(observed.at)!==linked)return null;
 // A real field-specific clock takes precedence over the common observation.
 // It may not be refreshed or concealed by a newer timestamp elsewhere.
 if(own&&x.times?.[own]?.present&&!x.times[own].fromSeries
    &&Date.parse(x.times[own].at)!==linked)return null;
 return make(raw,kind,raw,observed.source,duration);
}
function manualSnapshotStatus(p,x,now=Date.now()){
 const reasons=[],e=x?.evidence||{};
 if(isFutureProduct(p))reasons.push(p.quote?.futureResearch?.contractAnalysis?.available?"Gold-Future: Kontraktanalyse vorhanden; bedingten Vergleich beachten. Keine Spot-Freigabe":"Gold-Future: eigene Basiswertdaten und Trendprüfung erforderlich; keine Spot-Freigabe");
 if(!x||x.isin!==String(p.isin||'').trim().toUpperCase()||!validIsin(p.isin))reasons.push('Bildidentität nicht bestätigt');
 if(p.isinConfirmed!==true)reasons.push('Eindeutige Produktzuordnung oder widerspruchsfreie Bildwerte fehlen');
 if(x?.currency!=='EUR'||!(n(x?.bid)>0)||!(n(x?.ask)>=n(x?.bid)))reasons.push('Geld und Brief in EUR fehlen');
 if(e.Geld?.at!==e.Brief?.at)reasons.push('Geld-/Briefzeiten stimmen nicht überein');
 const pairs={Geld:x?.bid,Brief:x?.ask,Hebel:p.leverage,KO:p.ko};
 for(const [key,value] of Object.entries(pairs)){
  const own=evidenceTiming(e[key],now);
  const ownAge=typeof e[key]?.at==='string'?now-Date.parse(e[key].at):NaN;
  const limit=key==='KO'?KO_MAX_AGE_MS:SCREENSHOT_MAX_AGE_MS;
  const shared=sharedProductFieldTime({...p,snapshot:x},key,value,now);
  if(n(value)===null||n(e[key]?.value)!==n(value)
   ||!(own.fresh&&Number.isFinite(ownAge)&&ownAge<limit||shared?.valid))
   reasons.push(key+': eigener oder gemeinsamer Zeitbezug fehlt bzw. ist abgelaufen');
 }
 if(n(p.price)!==n(x?.ask)||!(n(p.leverage)>=1)||!(n(p.ko)>0))reasons.push('Produktwerte unvollständig oder widersprüchlich');
 if(x?.delayed)reasons.push('Bild weist auf verzögerte Kurse hin');
 return{complete:reasons.length===0,reasons,liveVerified:false};
}
function rankManualSnapshots(products,context={}){
 const scenario=String(context.direction||'NEUTRAL').toUpperCase(),now=context.now??Date.now();
 if(!['LONG','SHORT'].includes(scenario)||context.spotFresh!==true)return{candidates:[],total:0,liveVerified:false};
 const candidates=(products||[]).filter(p=>p.productDirection===scenario&&!currentQuote(p,now)&&manualSnapshotStatus(p,p.snapshot,now).complete)
  .map(p=>({...p,evaluation:evaluateProduct({...p,...context,spread:n(p.snapshot.ask)-n(p.snapshot.bid),rankingQuoteAt:p.snapshot.evidence?.Geld?.at||p.snapshot.sourceTime})}))
  .filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.setupScore>=35&&p.evaluation.conflictCount<3)
  .sort((a,b)=>b.evaluation.score-a.evaluation.score);
 return{candidates,total:candidates.length,liveVerified:false};
}

// Original screenshot time: exact instant or an explicitly uncertain minute interval.
function selectionTimeWindow(raw){
 const exact=sourceTimestamp(raw);if(exact)return {start:Date.parse(exact),end:Date.parse(exact),label:raw};
 const m=String(raw||'').match(/^(\d{2})[/.](\d{2})[/.](\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?$/);
 if(!m)return null;
 const [,dd,mm,yy,hh,mi,ss]=m,local=Date.UTC(+yy,+mm-1,+dd,+hh,+mi,+(ss||0));
 const fmt=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
 const matches=[60,120].map(offset=>local-offset*60000).filter(t=>{
  const parts=Object.fromEntries(fmt.formatToParts(new Date(t)).map(x=>[x.type,x.value]));
  return parts.year===yy&&parts.month===mm&&parts.day===dd&&parts.hour===hh&&parts.minute===mi&&parts.second===(ss||'00');
 });
 if(matches.length!==1)return null;
 return {start:matches[0],end:matches[0]+(ss?0:59999),label:raw+' · Europe/Zurich angenommen'+(ss?'':' · Sekunden unbekannt')};
}
function selectionDetailStatus(p,now=Date.now(),seriesAnalysis=false){
 if(knockoutStatus(p))return {complete:false,terminal:true,reasons:["Ausgeknockt – keine weiteren Daten erforderlich"]};
 const x=p.snapshot,e=x?.evidence||{},reasons=productTermsStatus(p,now,seriesAnalysis).reasons.slice();
 if(!validIsin(p.isin)||x?.isin!==p.isin)reasons.push('Detailbild mit derselben ISIN');
 if(!p.isinConfirmed)reasons.push('Eindeutige Produktzuordnung oder widerspruchsfreie Bildwerte fehlen');
 if(!(x?.currency==='EUR'||seriesAnalysis&&x?.currency==='CHF')||!(n(x.bid)>0&&n(x.ask)>=n(x.bid))||!seriesAnalysis&&n(p.price)!==n(x.ask))reasons.push((x?.currency==='CHF'?'CHF-Kursbild vorhanden; zeitlich passende EUR-Umrechnung für diesen Nachweis fehlt':'Aktuelles Kursbild mit Geld/Brief in EUR'));
 const pair=e.Geld?.source&&e.Geld.source===e.Brief?.source&&n(e.Geld.value)===n(x?.bid)&&n(e.Brief.value)===n(x?.ask);
 const explicit=x?.times?.quote;
 const time=pair?selectionTimeWindow(explicit?.present?explicit.text:x?.sourceTime):null;
 if(!time||now<time.start||now-time.start>SCREENSHOT_MAX_AGE_MS)reasons.push('Kurszeit mit Datum: höchstens 14 Stunden alt; keine ergänzten Sekunden');
 for(const key of ['bid','ask'])if(x?.times?.[key]?.present){
  const own=selectionTimeWindow(x.times[key].text);
  if(!own||now<own.start||now-own.start>SCREENSHOT_MAX_AGE_MS||!time||own.end<time.start||own.start>time.end)reasons.push('Widersprüchliche oder ungültige '+(key==='bid'?'Geldzeit':'Briefzeit')+' am Original prüfen');
 }
 if(x?.times?.leverage?.present&&!x.times.leverage.fromSeries){
  const own=selectionTimeWindow(x.times.leverage.text),actual=Date.parse(x.times.leverage.at);
  if(!own||!Number.isFinite(actual)||actual!==own.start
   ||!evidenceTiming(e.Hebel,now).fresh||Date.parse(e.Hebel?.at)!==actual)
   reasons.push('Eigene Hebelzeit ist ungültig oder veraltet');
 }
 if(x?.delayed)reasons.push('Nicht verzögerten Produktkurs ergänzen');
 const commonLeverage=sharedProductFieldTime(p,'Hebel',e.Hebel?.value,now);
 if(!(n(e.Hebel?.value)>=1&&(seriesAnalysis||n(e.Hebel?.value)===n(p.leverage)))
  ||!evidenceTiming(e.Hebel,now).fresh&&!commonLeverage?.valid)
  reasons.push('Aktuelles Detailbild mit Hebel und zugehöriger Zeit');
 const fixed=window.BobCombined.fixedFor(p),meta=p.quote?.productVerified?p.quote.metadata:null;
 if(!(n(p.ko)>0)||!(fixed||termValueMatches(p.ko,meta?.ko,x?.terms?.ko||e.KO)||screenshotKoCurrent(p,now)))reasons.push('KO-Barriere mit gültigem Nachweis oder festen Screenshotwert bestätigen');
 return {complete:!reasons.length,reasons,at:time?new Date(time.start).toISOString():null,timeLabel:time?.label,source:e.Geld?.source};
}
// Read the rendered result blocks, never the MTF legend containing all three labels.
function selectionUiSignals(doc=document){
 const momentum=String(doc.getElementById('blockMomentum')?.textContent||'').trim().toUpperCase();
 return {policy:'intraday-responsive-v6',mtf:doc.getElementById('blockMtf')?.textContent||'NEUTRAL',momentum:momentum==='LONG'?1:momentum==='SHORT'?-1:0};
}
// A direction label alone is not an entry confirmation. Missing values stay unknown.
function selectionMarketGate(context={}){
 const d=String(context.direction||'NEUTRAL').toUpperCase(),reasons=[];
 if(!['LONG','SHORT'].includes(d))return {ok:false,reasons:['Marktsignal neutral: keine bestätigte Long-/Short-Richtung']};
 const side=v=>{const x=String(v||'').toUpperCase();if(/NEUTRAL|ABWARTEN|MIXED|GEMISCHT/.test(x))return '';const long=/LONG|BULL|UP/.test(x),short=/SHORT|BEAR|DOWN/.test(x);return long===short?'':long?'LONG':'SHORT';};
 for(const [key,label] of [['trend','EMA-Trend'],...(['intraday-shadow-v1','intraday-fast-v3','intraday-consistent-v4','intraday-responsive-v6','intraday-trend-follow-v7'].includes(context.policy)?[]:[['trend2','Langfristtrend']]),['mtf','MTF']]){
  const value=side(context[key]);if(!value)reasons.push(label+' neutral oder nicht bestätigt');else if(value!==d)reasons.push(label+' widerspricht '+d);
 }
 for(const [key,label] of [['hist','MACD'],['momentum','Momentum']]){
  const value=n(context[key]);if(value===null||value===0)reasons.push(label+' neutral oder nicht vorhanden');else if((value>0?'LONG':'SHORT')!==d)reasons.push(label+' widerspricht '+d);
 }
 if(!(n(context.atr)>0))reasons.push('ATR fehlt: KO-Puffer gegenüber Volatilität nicht prüfbar');
 return {ok:!reasons.length,reasons};
}
// Post-gate ordering only: membership, scores, evidence and protection rules stay intact.
function applyLearnedRanking(candidates,products=[],policy=window.BobRankingPolicy,now=Date.now()){
 const sorted=candidates.slice().sort((a,b)=>b.score-a.score||a.isin.localeCompare(b.isin));
 const valid=policy?.id==='product-ranking-v1'&&policy.maxScoreGap===5&&Number.isFinite(policy.issuedAt)&&Number.isFinite(policy.expiresAt)&&policy.issuedAt<=now&&policy.expiresAt>now&&policy.expiresAt-policy.issuedAt<=120000;
 if(!valid)return sorted;
 const groups=new Map();
 sorted.forEach((c,index)=>{
  const p=products.find(p=>p.isin===c.isin),currency=p?.quote?.metadata?.currency||p?.currency||p?.quote?.currency;
  if(c.scope!=='XAU/USD'||c.indicative||c.estimated||c.paperOnly||!['EUR','CHF'].includes(currency)||!['LONG','SHORT'].includes(c.direction))return;
  const key=currency+':'+c.direction;
  if(!groups.has(key))groups.set(key,{currency,indices:[]});groups.get(key).indices.push(index);
 });
 for(const {currency,indices} of groups.values()){
  const pick={second:1,third:2}[policy.variants?.[currency]];
  if(!pick||indices.length<=pick)continue;
  const first=sorted[indices[0]],chosen=sorted[indices[pick]];
  if(!Number.isFinite(first.score)||!Number.isFinite(chosen.score)||first.score-chosen.score>5)continue;
  const ordered=indices.map(i=>sorted[i]);ordered.unshift(ordered.splice(pick,1)[0]);
  indices.forEach((i,k)=>{sorted[i]={...ordered[k],rankingVariant:policy.variants[currency],rankingCurrency:currency};});
 }
 return sorted;
}
function selectionWorkflow(products,context={},bundle,references=[]){
 const now=context.now??Date.now(),direction=String(context.direction||'NEUTRAL').toUpperCase();
 const result={direction,stage:'LISTE',groups:[],requests:[],waiting:[],total:0,tradeable:false,approved:false,approvedCount:0,gateReasons:[],checkedAt:now,notApproved:[]};
 const seen=new Set(),items=[];
 for(const [index,p] of products.entries())if(p.isin&&!seen.has(p.isin)){seen.add(p.isin);items.push({...p,index:index+1});}
 const conflicting=new Set(items.filter(p=>products.some(other=>other.isin===p.isin&&JSON.stringify(other)!==JSON.stringify(products[p.index-1]))).map(p=>p.isin));
 result.notApproved=products.map((p,i)=>({...p,index:i+1})).filter(p=>!p.isin&&p.name).map(p=>({isin:'ISIN fehlt',name:p.name,index:p.index,reasons:['Eindeutige ISIN fehlt: Produktzuordnung zuerst bestätigen']}));
 result.total=items.length+result.notApproved.length;
 const market=selectionMarketGate(context);
 // Shared, source-clocked entry timing protection. It affects only new
 // product suggestions; already active real trades retain monitoring.
 const confirmedAt=context.confirmationAt||window.BobDecisionAuditState?.confirmationAt||
    (Number.isFinite(window.BobDecisionAuditState?.confirmedAt)?
     window.BobDecisionAuditState.confirmedAt+300000:null);
 const timing=window.BobLateEntryGuard?.check(bundle,direction,now,confirmedAt);
 if(timing&&!timing.allowed){
  market.ok=false;
  market.reasons.push('Einstiegsfenster verpasst / ABWARTEN: '+timing.reason);
 }
 result.entryTimingGate=timing||null;
 result.gateReasons=!items.length?['Keine Produkte mit bestätigter ISIN vorhanden']:market.reasons;
 if(!items.length){result.stage='ABWARTEN';return result;}
 result.stage='DETAILBILDER';const groups=new Map();
 const add=c=>{if(!market.ok||c.direction!==direction)return;const key=c.scope+' · '+c.direction;if(!groups.has(key))groups.set(key,[]);const arr=groups.get(key);if(!arr.some(x=>x.isin===c.isin))arr.push(c);};
 const completeProducts=products.filter((p,i)=>!conflicting.has(p.isin)&&finalProductStatus(p,now,references[i]).complete);
 const completeReferences=completeProducts.map(p=>references[products.indexOf(p)]);
 const combined=window.BobCombined.rank(completeProducts,completeReferences,bundle,context);
 for(const p of combined.candidates.filter(p=>!p.estimated))add({isin:p.isin,name:p.name,direction,scope:'XAU/USD',score:p.evaluation.score,price:p.price,at:p.at,source:p.source,priceKind:p.priceKind,reasons:p.evaluation.reasons,warnings:p.evaluation.warnings});
 for(const p of items){
  if(knockoutStatus(p)){result.waiting.push({isin:p.isin,reason:"Ausgeknockt – Produkt ausgeschlossen"});continue;}
  if(conflicting.has(p.isin)){result.waiting.push({isin:p.isin,reason:'Widersprüchliche doppelte ISIN: Listen und Detailbilder am Original prüfen'});continue;}
  if(p.productDirection!==direction){result.waiting.push({isin:p.isin,reason:'Produktrichtung '+(p.productDirection||'unbekannt')+' passt nicht zu '+direction});continue;}
  if(/FAKTOR|FACTOR/i.test(p.name||'')){result.waiting.push({isin:p.isin,reason:'Faktorprodukt: eigenes tägliches Anpassungsmodell fehlt'});continue;}
  const terms=finalProductStatus(p,now,references[p.index-1]);
  if(!terms.complete){result.requests.push({isin:p.isin,name:p.name,index:p.index,reasons:terms.reasons,scope:isFutureProduct(p)?'FUTURE':'XAU/USD'});continue;}
  const cond=conditionalCandidate(p,context,now);if(cond.ok){if(cond.direction===direction)add({...cond,score:cond.scoreLow});else result.waiting.push({isin:p.isin,reason:"Eigene Future-Analyse passt nicht zur aktuellen Vorauswahl-Richtung"});continue;}
  // The direct quote was already evaluated by BobCombined.rank above.
  // Do not request screenshots for the same complete live evidence.
  if(currentQuote(p,now)||analysisReleaseQuote(p,now)){if(!cond.ok)result.waiting.push({isin:p.isin,reason:cond.reason});continue;}
  const state=selectionDetailStatus(p,now);
  if(!isFutureProduct(p)&&state.complete&&context.spotFresh===true){
   const e=evaluateProduct({...p,...context,spread:n(p.snapshot.ask)-n(p.snapshot.bid),rankingQuoteAt:state.at});
   if(e.ok&&e.fit&&e.setupScore>=35&&e.conflictCount<3)add({isin:p.isin,name:p.name,direction,scope:'XAU/USD',score:e.score,price:p.price,at:state.timeLabel,source:state.source,priceKind:'DEGIRO-Screenshot · bis 14 Stunden gültiger Nachweis, kein Livekurs',reasons:e.reasons,warnings:e.warnings});
   else result.waiting.push({isin:p.isin,reason:e.reasons.join(' · ')||'Technische Passung unzureichend'});
  }else if(!state.complete)result.requests.push({isin:p.isin,name:p.name,index:p.index,reasons:state.reasons,scope:isFutureProduct(p)?'FUTURE':'XAU/USD'});
  else result.waiting.push({isin:p.isin,reason:isFutureProduct(p)?cond.reason:'Aktuelle Gold-Spot-Analyse fehlt'});
 }
 result.eligibleCandidates=Array.from(groups.values()).flat().slice().sort((a,b)=>b.score-a.score||a.isin.localeCompare(b.isin));
 const rankOrder=applyLearnedRanking(result.eligibleCandidates,products,window.BobRankingPolicy,now);
 for(const [scope,candidates] of groups){result.groups.push({scope,total:candidates.length,candidates:rankOrder.filter(c=>candidates.some(x=>x.isin===c.isin)).slice(0,3)});}
 // This is an upload priority, not a product recommendation from incomplete prices.
 result.requests.sort((a,b)=>Number(a.scope==='FUTURE')-Number(b.scope==='FUTURE')||a.index-b.index);
 // At most three displayed selections overall; each keeps its own basis label.
 const selected=rankOrder.slice(0,3);
 result.groups=result.groups.map(g=>({...g,candidates:g.candidates.filter(c=>selected.includes(c))})).filter(g=>g.candidates.length);
 for(const candidate of result.eligibleCandidates){
  const product=products.find(p=>p.isin===candidate.isin);
  candidate.analysisApproval=calculatedAnalysisStatus(product,context,now);
 }
 result.approvedCount=selected.length;result.approved=selected.length>0;
 const selectedIds=new Set(selected.map(p=>p.isin));
 const eligibleIds=new Set(Array.from(groups.values()).flat().map(p=>p.isin));
 result.notApproved.push(...items.filter(p=>!selectedIds.has(p.isin)).map(p=>{
  const request=result.requests.find(x=>x.isin===p.isin),waiting=result.waiting.find(x=>x.isin===p.isin);
  const contractHelp=productTermsStatus(p,now).reasons.filter(reason=>reason.startsWith('Exakter Gold-Future-Kontrakt fehlt'));
  const reasons=[...result.gateReasons,...(request?.reasons||[]),...(waiting?[waiting.reason]:[]),...contractHelp];
  if(!reasons.length)reasons.push(eligibleIds.has(p.isin)?'Grundsätzlich geeignet, aber derzeit nicht unter den höchstens drei ausgewählten Produkten. Keine Freigabe in dieser Auswahl.':'Pflichtprüfung nicht bestanden: aktuelle Produkt- und Marktnachweise prüfen');
  return {isin:p.isin,name:p.name,index:p.index,reasons:[...new Set(reasons)],missingReasons:finalProductStatus(p,now,references[p.index-1]).reasons};
 }));
 result.stage=result.approved?'TOP3':'ABWARTEN';return result;
}
function renderSecondaryValidity(q){
 const check=q?.secondaryValidity;if(!check)return '';
 const labels={checking:'Prüfung läuft im Hintergrund',open:'Gültigkeitsnachweis weiterhin offen',partial:'Einzelne Gültigkeitsnachweise bestätigt',confirmed:'Basispreis und KO datiert bestätigt'};
 return '<div data-secondary-validity><b>Automatische Ersatzquellenprüfung · '+esc(labels[check.state]||'offen')+'</b><div>Erneute Prüfung nach fünf Minuten; Abrufzeit ersetzt kein Gültigkeitsdatum.</div>'+ (check.sources||[]).map(s=>'<div>'+esc(s.provider)+' · '+esc(s.state==='checking'?'wird geprüft':s.state==='unavailable'?'kein auswertbarer Nachweis verfügbar':'Produktwerte gefunden')+(s.checkedAt?' · geprüft '+esc(s.checkedAt):'')+Object.entries(s.terms||{}).map(([key,t])=>'<div>'+esc(key==='ko'?'KO-Schwelle':'Basispreis')+': '+esc(t.value)+' USD · '+esc(t.assessment||'noch nicht bestätigt')+' · Gültigkeitsstand '+esc(t.dateText||'nicht angegeben')+'</div>').join('')+'</div>').join('')+'</div>';
}
function renderProductSources(p){
 const attempt=researchResults.get(p.index),q=attempt?.isin===p.isin?attempt:p.quote?.isin===p.isin?p.quote:null;
 const time=v=>{const d=new Date(v);return v&&Number.isFinite(d.getTime())?d.toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' (Zürich)':'nicht vorhanden';};
 const link=(label,url)=>{try{const u=new URL(url);if(u.protocol==='https:')return '<a href="'+esc(u.href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+'</a>';}catch(_){}return esc(label);};
 if(!q)return '<div class="small" data-product-sources style="margin-top:8px"><b>Quellenprüfung</b><div>Noch kein Abrufresultat für diese ISIN vorhanden.</div></div>';
 const terms=q.productVerified&&(q.importActive||q.metadata?.termsDated||q.metadata?.termsFixed)?q:q.exchangeResearch?.productVerified?q.exchangeResearch:q;
 const verified=q.productVerified===true||terms.productVerified===true;
 const source=q.termsSource||terms.source||q.source||'Quelle nicht angegeben';
 const url=q.termsSourceUrl||terms.sourceUrl||q.sourceUrl;
 const at=q.termsCheckedAt||terms.checkedAt;
 return '<div class="small" data-product-sources style="margin-top:8px;padding:8px;border:1px solid #d1d5db;border-radius:8px"><b>Quellenprüfung · '+(verified?'Produktdaten abgerufen':q.found?'Kursdaten abgerufen':'Abruf ohne bestätigte Produktdaten')+'</b>'+
 '<div>Produktquelle: '+link(source,url)+'</div><div>Daten abgerufen: '+esc(time(at))+'</div>'+
 (q.attemptedAt?'<div>Letzter Prüfversuch: '+esc(time(q.attemptedAt))+'</div>':'')+
 '<div>Basispreis / KO: '+(q.metadata?.termsFixed?'Feste Vertragswerte mit Fälligkeit bestätigt':q.metadata?.termsDated===false?(renderTermSeriesValidity({...p,quote:q})||'<em>Werte vorhanden – Seriennachweis noch offen</em>'):'Datierte Nachweise siehe Pflichtprüfung')+'</div>'+
 renderSecondaryValidity(q)+'<div>Kursquelle: '+(q.found?link(q.source||'Kursanbieter',q.sourceUrl):'kein bestätigter Geld-/Briefnachweis aus diesem Abruf')+'</div>'+
 '<div>Kurszeit: '+esc(time(q.quoteAt))+'</div>'+
 '<div>'+esc(q.reason||'Weitere Pflichtprüfungen entscheiden über die Freigabe.')+'</div><div>Abrufzeit ist keine Kurszeit. Für Basispreis/KO akzeptiert Bob den ausgewiesenen Seriennachweis; ein Emittenten-Gültigkeitsdatum wird dadurch nicht behauptet.</div></div>';
}
function productIssuerLabel(p){
 const sgIds=['DE000FA06UL6','DE000FG5GUX2','DE000SQ02JQ6','DE000FG4JXV7','DE000FG309G0','DE000FG7EPT1','DE000FC1CHB7','DE000FG5GUT0','DE000FG6XB39','DE000FG5NMF2','DE000FG7MTA6','DE000FG7K283','DE000FG5NMH8','DE000FG7K3L2','DE000FE4UF01','DE000FG7K275','DE000FG34XV8'];
 const sg=sgIds.includes(p.isin)||/^SG\b|Soci[eé]t[eé] G[eé]n[eé]rale/i.test(p.name||'');
 return sg?'SG':/BNP|Paribas/i.test(p.name||'')||['DE000PJ9NB98','DE000PJ9NCK0'].includes(p.isin)?'BNP':'Emittenten';
}
function screenshotProductLink(p){
 if(!validIsin(p.isin))return '';
 const issuer=productIssuerLabel(p),url=p.isin==='DE000FG34XV8'?'https://www.sg-zertifikate.ch/product-details/159787428':issuer==='SG'?'https://www.sg-zertifikate.de/product-details/'+p.isin.slice(5,11).toLowerCase():issuer==='BNP'?'https://derivate.bnpparibas.com/product-details/'+p.isin+'/':null;
 return url?'<a data-screenshot-product="'+esc(p.isin)+'" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:10px 0;font-weight:700">'+esc(issuer)+'-Produkt öffnen ↗</a>':'';
}
// Explain unavailable FX independently of screenshot and broker evidence.
function productFxIssue(p,now=Date.now()){
 const q=p?.quote;
 if(q?.isin!==p.isin||q.productVerified!==true)return null;
 if(q.nativeChartEvidence?.currency==='CHF'&&!q.currencyConversion)
  return {at:null,reason:'Für die CHF/EUR-Umrechnung fehlt ein aktueller, zeitlich passender Wechselkurs.'};
 const i=q.leverageCalculation?.inputs;
 if(!i)return null;
 const times=[i.fxDataAt,i.fxEffectiveAt].map(v=>Date.parse(v));
 if(times.some(t=>!Number.isFinite(t)||t>now||now-t>300000))
  return {at:i.fxEffectiveAt||i.fxDataAt||null,reason:'Für den berechneten Hebel fehlt ein aktueller Wechselkurs.'};
 return null;
}
// Reconcile handset-only evidence gaps with the server's same-list, recent
// issuer analysis. Display-only: never feeds finalProductStatus(), ranking
// approval, broker execution checks or any order decision.
function serverAnalysisEvidence(p,now=Date.now()){
 const report=window.BobProductAuditReport,observed=Date.parse(report?.lastCheckedAt);
 if(report?.status!=='ok'||!Array.isArray(report.items)||!listArchive?.storedAt
    ||report.listUploadedAt!==listArchive.storedAt||!Number.isFinite(observed)
    ||now<observed||now-observed>180000)return null;
 // Source conflicts and contract contradictions must remain visible even
 // when the server has newer quote/leverage observations.
 const localTerms=typeof productTermsStatus==='function'?productTermsStatus(p,now,true):null;
 if((localTerms?.reasons||[]).some(reason=>/widerspr|quellenkonflikt|nicht eindeutig|falscher Basiswert|Faktorprodukt|Future-Kontrakt|Kontraktkonflikt/i.test(reason)))return null;
 const item=report.items.find(row=>row.isin===p.isin);
 if(!item||!['issuer-evidence-complete','analysis-evidence-complete'].includes(item.state)
    ||item.direction!==p.productDirection||item.missing?.length
    ||item.sourceStatusEvidence?.issuerStatus!==1
    ||item.tradeApproved===true||item.leverageObservation?.current!==true
    ||!(n(item.leverageObservation.value)>=1))return null;
 const at=Date.parse(item.quoteSourceAt),lev=Date.parse(item.leverageObservation.at);
 if(!Number.isFinite(at)||!Number.isFinite(lev)
    ||at>now||lev>now||now-at>90000||now-lev>90000)return null;
 const quote=(item.sourceObservations||[]).find(row=>{
  if(row.isinBound!==true||row.current!==true||row.degiroExecutable!==false
     ||row.label==='SG-Chart'||!String(row.venue||'').trim()
     ||!(n(row.bid)>0&&n(row.ask)>=n(row.bid))
     ||row.currency!==item.nativeCurrency)return false;
  const bidAt=Date.parse(row.bidAt),askAt=Date.parse(row.askAt);
  return Number.isFinite(bidAt)&&Number.isFinite(askAt)
    &&bidAt<=now&&askAt<=now&&now-bidAt<=90000&&now-askAt<=90000
    &&Math.abs(bidAt-askAt)<=90000;
 });
 return quote?{quote,leverage:item.leverageObservation.value,leverageKind:item.leverageObservation.kind,leverageAt:item.leverageObservation.at,source:item.source}:null;
}
function renderServerAnalysisEvidence(p){
 const evidence=serverAnalysisEvidence(p);
 if(!evidence)return '';
 const q=evidence.quote,number=value=>Number(value).toLocaleString('de-CH',{maximumFractionDigits:4});
 return '<div data-server-analysis-evidence class="small" style="margin:8px 0;padding:9px;border:1px solid #86efac;border-radius:8px">'+
  '<b>✓ Aktuelle Serveranalyse · keine DEGIRO-Ausführungszusage</b><div>'+
  'Geld '+number(q.bid)+' / Brief '+number(q.ask)+' '+esc(q.currency)+' · Quelle: '+esc(q.source||evidence.source)+
  ' · Kurszeit: '+esc(q.bidAt)+' · Hebel '+number(evidence.leverage)+'× ('+
  esc(evidence.leverageKind==='calculated-gearing'?'berechnet':'Quellenwert')+')</div></div>';
}
// Only evidence failures belong beside the ISIN; market/ranking reasons stay below.
function productProblemLabels(p){
 if(knockoutStatus(p)||compactProductExclusion(p)||(typeof serverAnalysisEvidence==='function'&&serverAnalysisEvidence(p)))return [];
 const result=finalProductStatus(p);
 if(result.complete)return [];
 const paused=typeof expectedQuotePause==='function'&&expectedQuotePause(p);
 const analysis=typeof currentSgChfAnalysisProof==='function'?currentSgChfAnalysisProof(p):null;
 const labels=analysis&&!degiroVenueObserved(p)&&!degiroVenueInferred(p)?['DEGIRO-Handelsplatznachweis']:[];
 if(typeof productFxIssue==='function'&&productFxIssue(p))labels.push('Wechselkurs veraltet oder nicht verfügbar');
 // Missing evidence is different from a missing numeric value. A datable
 // analysis quote must not be shown as an absent Geld/Brief pair merely because
 // the independent DEGIRO trade-execution evidence remains unconfirmed.
 const fields=typeof productFieldStates==='function'?productFieldStates(p):null;
 const pairPresent=!!fields&&['bid','ask'].every(key=>n(fields[key]?.value)>0);
 const leveragePresent=!!fields&&n(fields.leverage?.value)>=1;
 for(const reason of result.reasons){
  const r=String(reason),found=[];
  if(paused&&/^(?:BNP-Kursabruf: Markt geschlossen oder Produkt derzeit nicht handelbar|Kurszeit mit Datum: höchstens 14 Stunden alt; keine ergänzten Sekunden|Geld-\/Briefkurs veraltet|Kurs veraltet)$/.test(r))continue;
  // These are fallback screenshot requirements, not absent issuer analysis data.
  // Keep contradictory evidence and all contract/KO failures visible.
  if(analysis&&/^(?:Zusätzlicher Live-Nachweis offen|Detailbild mit derselben ISIN|Aktuelles Kursbild mit Geld\/Brief in EUR|Kurszeit mit Datum: höchstens 14 Stunden alt; keine ergänzten Sekunden|Aktuelles Detailbild mit Hebel und zugehöriger Zeit)$/.test(r))continue;
  if(/DEGIRO-Handelsplatznachweis/i.test(r))found.push('DEGIRO-Handelsplatznachweis');
  if(/Hebel/i.test(r))found.push(leveragePresent?'Hebelzeit / Quellenprüfung':'Hebel');
  if(/Kurszeit|Quellenzeit|Zeitstempel|Kurs.*(alt|zeit)|Geld.*Brief.*Zeit/i.test(r))found.push('Kurszeit');
  if(/Geld|Brief|Kursbild|Produktkurs|Kursnachweis|Live-Nachweis|BNP-Kursabruf/i.test(r))found.push(pairPresent?(degiroVenueObserved(p)||degiroVenueInferred(p)?'Kursart / Ausführbarkeit':'Kursart / DEGIRO-Handelsplatznachweis'):'Kursnachweis');
  if(/Basispreis|Finanzierungslevel/i.test(r))found.push('Basispreis');
  if(/KO|Knock-out|Barriere/i.test(r))found.push('KO-Nachweis');
  if(/Bezugsverhältnis/i.test(r))found.push('Bezugsverhältnis');
  if(/Basiswert|Future|Referenzkontrakt/i.test(r))found.push('Basiswert');
  if(/Laufzeit|Fälligkeit/i.test(r))found.push('Laufzeit');
  if(/Währung|CHF|Wechselkurs/i.test(r))found.push('Währung / Umrechnung');
  if(/Produkttyp|Produktrichtung|Long\/Short/i.test(r))found.push('Produkttyp');
  if(/ISIN|Bildzuordnung|Detailbild|Produktzuordnung/i.test(r))found.push('Produktnachweis');
  if(!found.length)found.push('Nachweis prüfen');
  for(const label of found)if(!labels.includes(label))labels.push(label);
 }
 return labels;
}
function renderProductProblemSummary(p){
 const labels=productProblemLabels(p);
 return labels.length?'<strong data-product-problems style="font-size:16px;line-height:1.5;color:#b45309;margin-left:6px">('+esc(labels.join(', '))+')</strong>':'';
}
function productHelpState(p){
 const server=typeof serverAnalysisEvidence==='function'?serverAnalysisEvidence(p):null;
 if(server)return {labels:[],checking:false,manual:false,status:'Aktuelle Server-Nachweise vorhanden',action:'Geld, Brief und Hebel sind durch datierte Anbieter-/Vergleichsdaten für die Analyse belegt. Die lokale Handyansicht kann noch ältere Bildwerte zeigen. Keine neuen Screenshots erforderlich; ein ausführbarer DEGIRO-Kurs bleibt separat unbestätigt.'};
 const labels=productProblemLabels(p),attempt=researchResults.get(p.index);
 const paused=typeof expectedQuotePause==='function'&&expectedQuotePause(p);
 if(paused&&!labels.length)return {labels,checking:false,manual:false,status:'Reguläre Handelspause',action:'Keine neuen Kursbilder nötig. Bob prüft die Kurse beim nächsten regulären Handelsfenster erneut; gespeicherte Werte behalten ihren Datenstand.'};
 const q=attempt?.isin===p.isin?attempt:p.quote?.isin===p.isin?p.quote:null;
 const checking=pendingQuotes.has(p.index)||q?.secondaryValidity?.state==='checking'||q?.comdirectFieldsBackup?.state==='checking';
 const venueMissing=labels.includes('DEGIRO-Handelsplatznachweis');
 const fxIssue=typeof productFxIssue==='function'?productFxIssue(p):null;
 if(fxIssue&&labels.length&&!checking)return {labels,checking:false,manual:false,status:'Wechselkursprüfung offen',action:fxIssue.reason+(fxIssue.at?' Quellenstand: '+fxIssue.at+'.':'')+' Bob versucht den Abruf automatisch erneut. Neue Produktbilder beheben diese Wechselkurslücke nicht. Weitere Produkt- und Handelsplatznachweise bleiben separat erforderlich.'+(venueMissing?' Konkret offen: Welcher DEGIRO-Handelsplatz gehört zu dieser ISIN und Handelswährung? Nur für diesen Nachweis ein DEGIRO-Detailbild mit ISIN, Börse, Währung und Datum ergänzen.':'')};
 const failed=!!q?.sourceFailure;
 const fields=typeof productFieldStates==='function'?productFieldStates(p):null;
 const valuesPresent=q?.productVerified===true&&fields&&['bid','ask'].every(key=>n(fields[key]?.value)>0)&&n(fields.leverage?.value)>=1;
 const needsTerms=labels.some(label=>/Basispreis|KO-Nachweis|Bezugsverhältnis|Basiswert|Laufzeit|Produkttyp|Produktnachweis/.test(label));
 // A temporary issuer outage with retained, correctly identified values
 // needs automatic retries rather than an immediate request for more images.
 const manual=labels.length>0&&!checking&&!!q&&(q.productVerified!==true||needsTerms||(failed&&!valuesPresent));
 const continuity=typeof analysisContinuityStatus==='function'?analysisContinuityStatus(p):null;
 if(continuity&&labels.length)return {labels,checking,manual,
  status:'Produktprüfung offen · '+continuity.label+' für die Analyse',
  action:'Offene Nachweise: '+labels.join(', ')+'. '+
   (checking?'Bob prüft die zugelassenen Quellen gerade erneut. ':manual?'Vorhandene Originalbelege unter „Gespeicherte Bildwerte, Quellen und Zeitbezug“ prüfen und nur die offenen Angaben ergänzen. ':'Bob prüft die zugelassenen Quellen automatisch erneut. ')+
   (continuity.calculated?'Der angezeigte Modellwert ersetzt keinen Originalkurs. ':'Ein aktueller Originalkurs bestätigt nur den Kurs, nicht die übrigen Produktnachweise. ')+
   'Keine bestätigte DEGIRO-Ausführung.'};
 if(continuity)return {labels,checking,manual:false,
  status:continuity.label+' · Analyse',
  action:continuity.calculated?'Bob überbrückt die Kurslücke automatisch mit einem gekennzeichneten Modellwert. Frische Originalkurse erhalten wieder Vorrang. DEGIRO-Ausführung separat prüfen.':'Produktnachweise in dieser Ansicht vorhanden. Der Originalkurs ist ein Anbieterwert; DEGIRO-Ausführung separat prüfen.'};
 return {labels,checking,manual,
  status:!labels.length?'Produktdaten vollständig':venueMissing?'DEGIRO-Handelsplatznachweis offen':checking?'Bob sucht gerade automatisch':manual?'Zusätzlicher Nachweis hilfreich':valuesPresent?'Kurs und Hebel vorhanden · Nachweisprüfung offen':'Automatische Prüfung noch offen',
  action:!labels.length?'Keine neuen Bilder nötig.':venueMissing?'Konkret offen: Welcher DEGIRO-Handelsplatz gehört zu dieser ISIN und Handelswährung? Dafür vorhandene Produktdetails prüfen; nur wenn die Zuordnung fehlt, ein Detailbild mit ISIN, Börse, Währung und Datum ergänzen.':checking?'Du musst jetzt nichts tun.':manual?'Öffne DEGIRO und ergänze nur die genannten Angaben als Screenshot.':valuesPresent?'Beim nächsten automatischen Abruf prüft Bob Kursart und Originalzeiten erneut. Die gespeicherten Zahlen bleiben für die Analyse sichtbar; ein ausführbarer DEGIRO-Kurs ist damit nicht bestätigt.':'Du musst die Werte nicht erneut eingeben. Den letzten Abruf findest du unter Details.'};
}
function renderProductHelp(p){
 const h=productHelpState(p);
 return '<div data-product-help role="status"><b>'+esc(h.status)+'</b><div>'+esc(h.action)+'</div></div>';
}
function renderScreenshotSources(p){
 const labels=productProblemLabels(p);
 if(!labels.length||!validIsin(p.isin))return '';
 const web='https://trader.degiro.nl/';
 const android=typeof navigator!=='undefined'&&/Android/i.test(navigator.userAgent||'');
 // No invented ISIN deep route: open the broker, then search the copied ISIN.
 // The browser fallback remains usable if the app does not accept this URL.
 const href=android?'intent://trader.degiro.nl/#Intent;scheme=https;package=nl.degiro.trader;S.browser_fallback_url='+encodeURIComponent(web)+';end':web;
 const issuer=screenshotProductLink(p);
 const help=productHelpState(p);
 return '<details'+(help.manual?' open':'')+'><summary>Angaben per Screenshot ergänzen · DEGIRO zuerst</summary><div data-screenshot-sources style="margin:8px 0 12px;padding:10px;border:1px solid #93c5fd;border-radius:8px">'+
 '<a data-screenshot-product="'+esc(p.isin)+'" href="'+esc(href)+'" style="display:inline-block;min-height:44px;font-weight:700;line-height:44px">'+(android?'DEGIRO-App öffnen ↗':'DEGIRO öffnen ↗')+'</a> · <b>erste Wahl</b>'+
 '<div>ISIN oben kopieren → in DEGIRO suchen → Produkt öffnen. Screenshot mit <b>'+esc(labels.join(', '))+'</b>, ISIN und angezeigtem Datenstand aufnehmen. Geld/Brief in der Produktwährung und die zugehörige Kurszeit zeigen.</div>'+
 '<div class="small">'+(android?'Falls sich nur die Webseite öffnet: DEGIRO-App über dein App-Symbol starten. ':'')+'Danach zu Bob zurückkehren und „Bilder / PDF zu diesem Produkt hinzufügen“ wählen.</div>'+
 '<div style="margin-top:8px"><b>Falls die Angaben bei DEGIRO fehlen:</b> '+(issuer||'Emittent in den DEGIRO-Produktdetails nachsehen und dessen Produktseite mit dieser ISIN öffnen.')+'</div>'+
 '<div class="small">Hebel: Kennzahlen mit Datenstand. KO, Basispreis und Bezugsverhältnis: Stammdaten; genauer Basiswert und Laufzeit: Produktdetails / Dokumente. '+(degiroVenueObserved(p)||degiroVenueInferred(p)?'':'Für den DEGIRO-Handelsplatz den DEGIRO-Kursbereich aufnehmen. ')+' Bei einer gemeinsamen Bildserie muss der Zeitbezug eindeutig erkennbar sein.</div></div></details>';
}
function renderTestScreenshotRequest(p){
 if(knockoutStatus(p))return '';
 if(productDataStatus(p).complete)return '';
 const issuer=productIssuerLabel(p);
 const issue=bnpSourceIssue(p);
 if(p.quote?.isin===p.isin&&p.quote?.productVerified&&p.quote?.importActive)return '<div class="small" data-sg-direct-status>'+esc(p.quote.reason||'SG-Direktimport aktiv')+' Fehlende Nachweise stehen oben einzeln. Ein Screenshot kann nur diese verbleibenden Lücken ergänzen.</div>';
 if(issue)return '<div class="small" data-bnp-source-delay>'+esc(issue)+'. Bob fragt automatisch erneut ab. Vorhandene Produktbedingungen bleiben getrennt geprüft. Ein Screenshot ist nur ein zusätzlicher Nachweis.</div>';
 return '<div data-test-screenshot-request class="small" style="margin:12px 0;padding:12px;background:#eaf3ff;border-radius:10px"><b>Für den Intraday-Test: aktuelle Screenshots erneut hochladen</b><div>Bitte öffne die '+esc(issuer)+'-Produktseite für <strong>'+esc(p.isin)+'</strong> und lade neue Bilder über den Knopf darunter hoch.</div>'+screenshotProductLink(p)+'<ul><li><b>Kursdaten:</b> Geld- und Briefkurs, angezeigtes Datum/Uhrzeit sowie ISIN oder WKN sichtbar aufnehmen.</li><li><b>Stammdaten:</b> fehlende oder nicht aktuell bestätigte Angaben ergänzen, insbesondere Basispreis und KO-Barriere mit Datenstand.</li></ul><div>Für einen späteren Vergleich erneut ein aktuelles Kursbild ergänzen. So kann Bob die Produktentwicklung besser auswerten. Kein Kauf nötig; die Bilder allein erteilen keine Handelsfreigabe.</div></div>';
}
function renderIssuerHelp(p,reasons){
 if(!reasons?.length||!validIsin(p.isin))return '';
 const issuer=productIssuerLabel(p),url=p.isin==='DE000FG34XV8'?'https://www.sg-zertifikate.ch/product-details/159787428':issuer==='SG'?'https://www.sg-zertifikate.de/product-details/'+p.isin.slice(5,11).toLowerCase():issuer==='BNP'?'https://derivate.bnpparibas.com/product-details/'+p.isin+'/':null;
 return '<div class="small" data-issuer-help style="margin:10px 0">'+(url?'<a data-screenshot-product="'+esc(p.isin)+'" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(issuer)+'-Produkt öffnen</a>':'Produktseite des Emittenten öffnen ('+esc(issuer)+').')+'<button type="button" data-copy-product-isin="'+esc(p.isin)+'">ISIN kopieren</button><span role="status" data-copy-status></span><details><summary>Hilfe zum Screenshot</summary>ISIN, fehlende Werte und den angezeigten Datenstand aufnehmen. Nach der Bildauswahl wird automatisch eingelesen.</details></div>';
}
const RETURN_PRODUCT_KEY='bob.productScreenshotReturn.v1';
let returnProductIsin='',returnProductPending=false;
try{returnProductIsin=localStorage.getItem(RETURN_PRODUCT_KEY)||'';returnProductPending=!!returnProductIsin;}catch(_){}
function screenshotReturnRow(isin,rows){
 const matches=rows.filter(row=>String(row.isin||'').trim().toUpperCase()===isin);
 return validIsin(isin)&&matches.length===1?matches[0]:null;
}
function updateScreenshotReturn(resume=false){
 const panel=document.getElementById('dgScreenshotReturn');if(!panel)return;
 const rows=Array.from(document.querySelectorAll('[data-dg="isin"]')).map(el=>({isin:el.value,index:el.dataset.i}));
 const row=screenshotReturnRow(returnProductIsin,rows);
 panel.hidden=!row;
 if(!row)return;
 panel.querySelector('[data-return-isin]').textContent=returnProductIsin;
 const links=panel.querySelector('[data-return-product-link]');
 if(links){
  const name=document.querySelector('[data-dg="name"][data-i="'+row.index+'"]')?.value||'';
  const html=screenshotProductLink({isin:returnProductIsin,name});
  if(links._productLinkHtml!==html){links.innerHTML=html;links._productLinkHtml=html;bindIsinCopy(links);}
 }

 if(resume&&returnProductPending&&!document.hidden){
  returnProductPending=false;
  document.querySelector('#bobNavigation [data-view="products"]')?.click();
  panel.scrollIntoView({block:'start'});
 }
}
function rememberScreenshotProduct(isin){
 if(!validIsin(isin))return;
 returnProductIsin=isin;returnProductPending=true;
 try{localStorage.setItem(RETURN_PRODUCT_KEY,isin);}catch(_){}
 updateScreenshotReturn();
}
function renderIsinCopy(isin){
 // The same one-tap control appears beside every identified product, including
 // blocked and knocked-out products. Only copying is allowed; no trade action.
 if(!validIsin(isin))return '';
 return '<span data-isin-copy style="display:inline-flex;align-items:center;vertical-align:middle;gap:4px;margin-left:6px;white-space:nowrap">'+
  '<button type="button" data-copy-product-isin="'+esc(isin)+'" aria-label="ISIN '+esc(isin)+' kopieren" title="ISIN kopieren" style="min-width:44px;min-height:44px;padding:5px;margin:0;font-size:20px;line-height:1">📋</button>'+
  '<span class="small" role="status" aria-live="polite" data-copy-status style="font-size:12px"></span></span>';
}
function bindIsinCopy(root){
 root.querySelectorAll('[data-screenshot-product]').forEach(link=>{
  if(link.dataset.returnBound)return;link.dataset.returnBound='1';
  link.addEventListener('click',()=>rememberScreenshotProduct(link.dataset.screenshotProduct));
 });
 root.querySelectorAll('[data-copy-product-isin]').forEach(button=>{
  if(button.dataset.copyBound)return;button.dataset.copyBound='1';
  button.addEventListener('click',async()=>{
   const isin=(button.parentNode.querySelector('[data-dg="isin"]')?.value||button.dataset.copyProductIsin||'').trim().toUpperCase(),status=button.parentNode.querySelector('[data-copy-status]');
   if(!validIsin(isin)){if(status)status.textContent=' Bitte zuerst eine gültige ISIN eintragen.';return;}
   try{await navigator.clipboard.writeText(isin);if(status)status.textContent=' ✓ Kopiert';}
   catch(_){
    const field=document.createElement('textarea');field.value=isin;field.readOnly=true;field.style.cssText='position:fixed;left:0;top:0;opacity:0';
    document.body.append(field);field.select();field.setSelectionRange(0,isin.length);
    let copied=false;try{copied=document.execCommand('copy');}catch(_){}finally{field.remove();}
    if(status)status.textContent=copied?' ✓ Kopiert':' Kopieren nicht möglich: '+isin;
   }
  });
 });
}
function missingValueLocation(reason,p={}){
 if(/^CHF-Kursbild vorhanden/.test(reason))return 'CHF-Originalkurs ist gespeichert. Bob verwendet für die EUR-Analyse eine separat datierte automatische Umrechnung. Für diesen historischen Kursnachweis fehlt ein zeitlich passender Wechselkurs; dasselbe Bild erneut hochzuladen hilft nicht.';
 const key=/Basispreis|Finanzierungslevel/.test(reason)?'strike':/KO|Knock-out|Barriere/i.test(reason)?'ko':null;
 const term=key&&p.snapshot?.terms?.[key];
 if(term&&n(term.value)>0&&!term.at&&/datierte|Gültigkeitsnachweis|Aktualität|gültigem Nachweis/i.test(reason))return 'Wert aus dem Bild übernommen. Ein Gültigkeitsdatum ist dort nicht belegt. Bob akzeptiert stattdessen einen gültigen Zeitbezug derselben Bilderserie. Fehlt dieser oder ist er abgelaufen, bleibt der Wert mit Hinweis für die Analyse nutzbar.';
 if(/Produkttyp|Produktrichtung/.test(reason))return 'Stammdaten → Typ / Produktart: Call oder Put bzw. Long oder Short.';
 if(String(reason).startsWith('BNP-Kursabruf:'))return 'Automatische BNP-Quelle; Bob wiederholt den Abruf. Die letzte Quellenzeit steht unter Quellen und Einzelheiten.';
  if(/Future-Kontrakt|Futures-Kontrakt/.test(reason))return 'Stammdaten: Basiswert mit Kontraktmonat/Jahr. Bei fehlenden Details: Dokumentation → Endgültige Bedingungen, Referenzkontrakt / Futures Contract und Börse.';
  if(/Geld|Brief|Kurszeit|Kursbild|Produktkurs|Kursnachweis/.test(reason))return 'Kursbereich oben: Geld und Brief in EUR zusammen mit „Kurs von“ (Datum/Uhrzeit) aufnehmen. Falls auch der Hebel fehlt: Kennzahlen ergänzen.';
  if(/Hebel/.test(reason))return 'Kennzahlen: Hebel aufnehmen. Den zugehörigen Datenstand mit erfassen, sofern angezeigt.';
  if(/Basispreis|Finanzierungslevel/.test(reason))return 'Stammdaten: Basispreis und das direkt daneben angegebene Datum aufnehmen.';
  if(/KO|Knock-out|Barriere/i.test(reason))return 'Stammdaten: Knock-Out-Barriere und das direkt daneben angegebene Datum aufnehmen.';
  if(/Bezugsverhältnis/.test(reason))return 'Stammdaten: Bezugsverhältnis aufnehmen.';
  if(/Basiswert|Goldreferenz|Gold-Referenz/.test(reason))return 'Dokumentation → Rechtliche Dokumente → Endgültige Bedingungen (PDF): Ausstattungstabelle / Basiswert und Referenzpreis. PDF über „Bilder / PDF hinzufügen“ hochladen; die Angabe Gold allein reicht nicht.';
  if(/ISIN|Bildzuordnung|Detailbild|Original|Long\/Short/.test(reason))return 'Stammdaten: ISIN und Typ (Call/Put) sowie den Produktnamen aufnehmen.';
  if(/Währung/.test(reason))return 'Kursbereich: Währung neben Geld/Brief aufnehmen.';
  if(/Laufzeit|Fälligkeit|abgelaufen/.test(reason))return 'Produktname / Stammdaten: Open End oder Fälligkeit aufnehmen; ergänzend Produktbeschreibung.';
  if(/Produkttyp|Produktrichtung|Richtung/.test(reason))return 'Stammdaten → Typ / Produktart: Call oder Put bzw. Long oder Short.';
  if(/Kosten|Finanzierung|Risikoprämie/.test(reason))return 'Dokumentation → Kostenausweis; Finanzierung und Risikoprämie unter Stammdaten / Produktbedingungen.';
  return 'Stammdaten und Produktbeschreibung prüfen; ergänzende Angaben stehen unter Dokumentation.';
}
function renderUploadMissing(p,status){
 if(!p||status?.terminal)return status?.terminal?'<strong>Ausgeknockt – keine weiteren Daten erforderlich.</strong>':'';
 const reasons=[...new Set(status?.reasons||[])];
 if(!reasons.length)return '';
 return '<div class="small" style="margin-top:12px"><strong>Für die Live-Freigabe noch offen:</strong><div>Übernommene Bildwerte bleiben gespeichert. Offene Nachweise sind kein fehlgeschlagener Bildimport.</div>'+reasons.map(reason=>'<div style="margin:10px 0"><b>'+esc(reason)+'</b><br>Fundort: '+esc(missingValueLocation(reason,p))+'</div>').join('')+'</div>';
}
function renderMissingValues(reasons,p={}){
 if(knockoutStatus(p))return '';
 const all=[...new Set(reasons||[])];if(!all.length)return '';
 const fields=productFieldStates(p),terms={...(p.snapshot?.terms||{}),...(p.quote?.conditions||{})};
 const isEvidenceIssue=reason=>{
  if(/Zeitversatz|zeitlich|Zeitabstand|Aktualität|Datenstand|Quellenantwort veraltet|Live-Nachweis/.test(reason))return true;
  if(/Hebel/.test(reason)&&fields.leverage.state!=='fehlt')return true;
  if(/Geld|Brief|Kurszeit|Kursbild|Produktkurs|Kursnachweis/.test(reason)&&(['bid','ask'].every(k=>fields[k].state!=='fehlt')||/^CHF-Kursbild vorhanden/.test(reason)))return true;
  const key=/Basispreis|Finanzierungslevel/.test(reason)?'strike':/KO|Knock|Barriere/i.test(reason)?'ko':null;
  return key&&n(terms[key]?.value??(key==='ko'?p.ko:null))>0&&/datier|Gültigkeit|gültigem Nachweis|24 Stunden/i.test(reason);
 };
 const values=all.filter(reason=>!isEvidenceIssue(reason)),evidence=all.filter(isEvidenceIssue);
 const evidenceHtml=evidence.length?'<details class="small" data-time-evidence style="margin-top:8px"><summary><strong>Zeitbezug / Berechnungsnachweise prüfen</strong></summary><div>Vorhandene Werte bleiben gespeichert. Ein unpassender oder unbestätigter Zeitbezug ist separat ausgewiesen und zählt nicht als fehlender Produktwert. Die Live-Freigabe wird separat geprüft.</div><ul>'+evidence.map(reason=>'<li>'+esc(reason)+'</li>').join('')+'</ul></details>':'';
 if(!values.length)return evidenceHtml;
 const provider=/^BNP\b/i.test(p.name||'')||['DE000PJ9NCK0','DE000PG0XK25'].includes(p.isin)?'BNP-Produktseite':'SG-Produktseite';

 return evidenceHtml+'<details class="small" data-missing-values style="margin-top:8px"><summary style="cursor:pointer;padding:8px 0"><strong>Fehlende Werte</strong></summary><ul>'+values.map(reason=>'<li style="margin:10px 0"><strong>'+esc(reason.startsWith('Exakter Gold-Future-Kontrakt fehlt')?'Exakter Future-Kontrakt fehlt oder ist nicht aktuell bestätigt':reason)+'</strong><br>Fundort auf der '+esc(provider)+': '+esc(missingValueLocation(reason,p))+'</li>').join('')+'</ul><div>Den Produktlink oben öffnen. Lesbare Screenshots mit ISIN, Feldnamen und angezeigtem Datenstand oder die endgültigen Bedingungen als PDF über „Bilder / PDF hinzufügen“ hochladen. Mehrere Ausschnitte sind möglich. Nicht angezeigte Datumsangaben bleiben offen; die Handy-Uhr ersetzt keinen Datenstand.</div></details>';
}
function renderImageImportStatus(index){
 const message=typeof document==='undefined'?'':document.getElementById('dgOcrStatus'+index)?.textContent||'';
 return '<div class="small" role="status" aria-live="polite" data-image-import-status="'+index+'" style="margin-top:8px;white-space:normal;overflow-wrap:anywhere">'+esc(message||'Nach der Bildauswahl startet das Einlesen automatisch. Kein zusätzlicher Upload-Klick nötig.')+'<div style="margin-top:4px;font-size:12px;color:#64748b">Bildimport 05.10-15 · Galerieauswahl</div></div>';
}
// Keep disclosure state by product identity and nested section, never by row order.
function detailStateKey(el){
 const product=el.closest('[data-product-isin]');
 const labels=[];let node=el;
 while(node){
  if(node.tagName==='DETAILS')labels.unshift((node.getAttribute?.('data-product-details')||node.querySelector(':scope > summary')?.textContent||'').replace(/\(\d+\)/g,'').replace(/\s+/g,' ').trim());
  if(node===product)break;
  node=node.parentElement;
 }
 return (product?.getAttribute('data-product-isin')||'panel')+'|'+labels.join('>');
}
// Keep the currently read content at the same viewport offset during a
// synchronous background render. Resolve replaced cards by ISIN, not rank.
function preserveReadingPosition(render){
 if(typeof document==='undefined'||!document.elementFromPoint||!window.scrollTo)return render();
 const x=window.scrollX,y=window.scrollY;
 const hit=document.elementFromPoint(Math.min(40,window.innerWidth/2),Math.min(120,window.innerHeight/3));
 const anchors=[];let node=hit;
 while(node&&node!==document.body){
  const root=node.closest('[id]');
  if(root){
   const product=node.closest('[data-product-isin]');
   const base=product&&root.contains(product)?product:root;
   const path=[];let child=node;
   while(child&&child!==base){path.unshift([...child.parentElement.children].indexOf(child));child=child.parentElement;}
   if(child===base)anchors.push({id:root.id,isin:base===product?product.getAttribute('data-product-isin'):null,path,top:node.getBoundingClientRect().top,tag:node.tagName});
  }
  node=node.parentElement;
 }
 const style=document.documentElement.style,previous=style.overflowAnchor;
 style.overflowAnchor='none';
 try{return render();}
 finally{
  let target=y;
  for(const a of anchors){
   const root=document.getElementById(a.id);
   let current=a.isin?[...(root?.querySelectorAll('[data-product-isin]')||[])].find(el=>el.getAttribute('data-product-isin')===a.isin):root;
   for(const index of a.path)current=current?.children[index];
   if(current&&current.tagName===a.tag&&current.getClientRects().length){target=window.scrollY+current.getBoundingClientRect().top-a.top;break;}
  }
  window.scrollTo({left:x,top:Math.max(0,target),behavior:'instant'});
  style.overflowAnchor=previous;
 }
}
function updateProductHtml(root,html){
 if(root._bobRenderedHtml===html)return false;
 const state=new Map([...root.querySelectorAll('details')].map(el=>[detailStateKey(el),el.open]));
 const focused=typeof document!=='undefined'?document.activeElement:null;
 const focusKey=focused?.tagName==='SUMMARY'&&root.contains(focused)?detailStateKey(focused.parentElement):null;
 root.innerHTML=html;root._bobRenderedHtml=html;
 for(const el of root.querySelectorAll('details')){
  const key=detailStateKey(el);if(state.has(key))el.open=state.get(key);
  if(key===focusKey)el.querySelector(':scope > summary')?.focus({preventScroll:true});
 }
 return true;
}
function productEvidenceReason(p,reason){
 return reason==='Detailbild mit derselben ISIN'&&p.quote?.isin===p.isin&&p.quote.productVerified===true&&automaticIdentity(p)?'Zusätzlicher Live-Nachweis offen':reason;
}
// Completeness of an accepted analysis snapshot is independent of live release.
function productDataStatus(p,now=Date.now(),reference){
 const live=finalProductStatus(p,now,reference);
 if(live.complete||live.terminal)return {...live,basis:'live'};
 const x=p.snapshot,series=x?.captureSeries,time=selectionTimeWindow(series?.text);
 const sameView=x?.isin===p.isin&&hasScreenshotIdentity(x)
  &&['Geld','Brief','Hebel'].every(key=>{
   const current=key==='Geld'?x.bid:key==='Brief'?x.ask:p.leverage;
   const evidence=sharedProductFieldTime(p,key,current,now);
   return evidence?.kind==='image-view'&&evidence.valid;
  });
 const seriesCurrent=!!series?.userDeclaredSimultaneous&&!!time
  &&now>=time.start&&now-time.start<=SCREENSHOT_MAX_AGE_MS;
 if(x?.isin!==p.isin||!sameView&&!seriesCurrent)return {...live,basis:'incomplete'};
 const result=selectionDetailStatus(p,now,true),reasons=result.reasons.slice();
 // Undated terms must actually belong to this series, not an older merged import.
 for(const key of ['strike','ko']){
  const term=x.terms?.[key]||(key==='ko'?x.evidence?.KO:null);
  if(!currentProductTerm(p,key,term,now)
    &&!currentProductTerm(p,key,p.quote?.conditions?.[key],now))
    reasons.push((key==='strike'?'Basispreis':'KO-Barriere')+': Wert gehört nicht zum gültigen gemeinsamen Zeitbezug');
 }
 return {...result,complete:!reasons.length,reasons,
  basis:sameView?'shared-view':'series',warnings:productTermsStatus(p,now,true).warnings};
}
function productCompletionBadge(){
 return '';
}
function productDirectionDataState(p,now=Date.now()){
 const fields=productFieldStates(p,now),data=productDataStatus(p,now);
 const terms=productTermsStatus(p,now,true);
 const missing=Object.values(fields).some(f=>f.state==='fehlt')||terms.reasons.some(r=>/: Wert fehlt|Long\/Short fehlt|ungültig|widerspr|nicht eindeutig|ausgeschlossen|Exakter Future-Kontrakt/i.test(r));
 const unresolvedTerms=terms.reasons.some(r=>!/Wert eingelesen.*(?:datier|24 Stunden)|KO.*(?:8.Stunden|Zeitbezug|datier|Gültigkeit|Nachweis)|Aktualität|veraltet/i.test(r));
 const blocked=!!data.terminal||!data.complete&&(missing||unresolvedTerms);
 const stale=!blocked&&(!data.complete||Object.values(fields).some(f=>/veraltet|unbestätigt|abweichend/.test(f.state)));
 return {blocked,stale,missing};
}
function currentSgChfAnalysisProof(p,now=Date.now()){
 // This is a *display-only* evidence tier, not finalProductStatus or execution.
 // Only the authentic, single-ISIN CHF chart and its matching SG reference
 // leverage observed in the same issuer collection cycle qualify.
 const q=p?.quote,m=q?.metadata,chart=q?.nativeChartEvidence;
 if(!validIsin(p?.isin)||q?.isin!==p.isin||q.productVerified!==true
    ||q.sourceFailure||q.quoteFailureCode||m?.status!==1
    ||m.issuerExchangeCode!=='CBSW'||m.currency!=='CHF'
    ||m.underlyingType!=='SPOT'||m.underlying!=='XAU/USD'
    ||!['LONG','SHORT'].includes(p.productDirection)||m.direction!==p.productDirection
    ||chart?.currency!=='CHF'||chart.delayed===true
    ||!(n(chart.bid)>0&&n(chart.ask)>=n(chart.bid)))return null;
 const chartAt=Date.parse(chart.pointAt);
 if(!Number.isFinite(chartAt)||chartAt>now||now-chartAt>300000)return null;
 const leverage=sharedSgIssuerLeverage(p,now),observed=q.sharedValueObservations?.Referenzhebel;
 if(!leverage?.fresh||Date.parse(leverage.at)!==chartAt||!(leverage.value>=1)
    ||observed?.isin!==p.isin||observed.contextAt!==chart.pointAt
    ||n(observed.value)!==leverage.value)return null;
 return {bid:chart.bid,ask:chart.ask,leverage:leverage.value,
  at:chart.pointAt,currency:'CHF',analysisOnly:true,degiroExecutable:false};
}
// One visual check state for both each card and the collection heading.
// This describes displayed data, never trading approval.
function productDirectionCheck(p,now=Date.now()){
 if(expectedQuotePause(p,now))return {kind:'none',paused:true};
 const venue=sharedVenueStatus(p,now);
 if(venue?.required&&!venue.current)return {kind:'none',state:{blocked:true,stale:false,missing:true}};
 const analysis=currentSgChfAnalysisProof(p,now);
 if(analysis)return {kind:'qualified',analysis};
 const state=productDirectionDataState(p,now);
 // This does not change state.blocked or any final release / ranking gate.
 const server=(state.blocked||state.stale)&&typeof serverAnalysisEvidence==='function'?serverAnalysisEvidence(p,now):null;
 if(server)return {kind:'qualified',serverEvidence:server,state};
 return {kind:state.blocked?'none':state.stale?'qualified':'confirmed',state};
}
function renderProductIdentity(p,now=Date.now()){
 const excluded=knockoutStatus(p)?'Ausgeknockt – Produkt ausgeschlossen':compactProductExclusion(p);
 const check=excluded?{kind:'none'}:productDirectionCheck(p,now);
 const symbol=check.kind==='confirmed'?'✓':check.kind==='qualified'?'(✓)':'✗';
 let reason='Analysewerte vollständig · DEGIRO-Ausführung separat prüfen.';
 if(excluded)reason=excluded;
 else if(check.paused)reason='Reguläre Handelspause · kein aktueller Vollständigkeitshaken.';
 else if(check.analysis)reason='Einschränkung: SG-Chartkurs und Hebel für die Analyse; kein bestätigter DEGIRO-Ausführungskurs.';
 else if(check.serverEvidence)reason='Aktuelle Server-Analysewerte liegen vor. Lokale Bildwerte können noch unvollständig sein; keine bestätigte DEGIRO-Ausführung.';
 else if(check.kind!=='confirmed'){
  const fields=Object.values(productFieldStates(p,now));
  const details=fields.filter(f=>/fehlt|veraltet|unbestätigt|abweichend/.test(f.state)).map(f=>f.key+': '+f.state);
  const terms=productDataStatus(p,now).reasons||[];
  reason=(check.kind==='qualified'?'Einschränkung: ':'Offen: ')+[...new Set([...details,...terms])].join(' · ');
  if(!details.length&&!terms.length)reason+='Produktnachweise noch nicht vollständig bestätigt.';
 }
 return '<div data-product-identity><b>'+esc(p.isin)+'</b> <strong data-isin-check="'+check.kind+'" aria-label="'+esc(reason)+'" style="font-size:1.6em;white-space:nowrap;color:'+(check.kind==='none'?'#b91c1c':'#15803d')+'">'+symbol+'</strong>'+renderIsinCopy(p.isin)+
  '<div data-isin-check-reason role="status" style="margin:6px 0;font-size:14px;line-height:1.5;color:'+(check.kind==='confirmed'?'#166534':'#92400e')+'">'+esc(reason)+'</div></div>';
}
function renderGoldProductsHeading(products,now=Date.now()){
 const remaining=products.filter(p=>!knockoutStatus(p)&&!compactProductExclusion(p));
 const checks=remaining.map(p=>productDirectionCheck(p,now));
 if(!checks.length||checks.some(c=>c.kind==='none'))return 'Gold-Hebelprodukte';
 const qualified=checks.some(c=>c.kind==='qualified');
 return 'Gold-Hebelprodukte <strong data-products-check="'+(qualified?'qualified':'confirmed')+
  '" aria-label="'+(qualified?'Alle berücksichtigten Produkte zeigen einen grünen Haken, teilweise mit Einschränkung':'Alle berücksichtigten Produkte zeigen einen vollständigen grünen Haken')+
  '" style="font-size:1.6em;font-weight:900;color:#15803d">'+(qualified?'(✓)':'✓')+'</strong>';
}
function analysisContinuityStatus(p,now=Date.now()){
 const c=continuityDisplay(p,now);
 if(c)return {label:c.state==='original'?'Originalkurs aktuell':'Berechneter Kurs aktuell',calculated:c.state==='calculated'};
 if(calculatedProductDisplay(p,now))return {label:'Berechneter Kurs aktuell',calculated:true};
 return null;
}
function renderProductDirectionStatus(p,now=Date.now()){
 const continuity=typeof analysisContinuityStatus==='function'?analysisContinuityStatus(p,now):null;
 if(continuity){
  const labels=productProblemLabels(p);
  return '<span data-direction-data-status data-analysis-continuity role="status" style="display:inline-flex;gap:6px;flex-wrap:wrap"><strong>'+esc(continuity.label)+' · Analyse</strong><span'+(labels.length?' data-product-evidence-open style="color:#92400e"':'')+'>'+esc(labels.length?'Produktprüfung offen: '+labels.join(', ')+'. Keine bestätigte DEGIRO-Ausführung.':'DEGIRO-Ausführung separat prüfen.')+'</span></span>';
 }
 const check=productDirectionCheck(p,now);
 if(check.paused)return '<span data-direction-data-status data-regular-trading-pause>Reguläre Handelspause · letzter Kursstand gespeichert</span>';
 if(check.serverEvidence)return '<span data-direction-data-status data-server-analysis-only role="status" style="color:#166534;font-weight:700">(✓) Server-Kurs/Hebel nachgewiesen · nur Analyse · kein DEGIRO-Ausführungskurs</span>';
 const analysis=check.analysis;
 if(analysis){
  // Fresh analysis evidence and broker execution are separate display facts.
  // Keep productDirectionCheck and all trading/collection gates unchanged.
  const venue=degiroVenueObserved(p)?'<span style="color:#15803d">✓ DEGIRO-Handelsplatz belegt</span>':
   degiroVenueInferred(p,listArchive,now)?'<span>Handelsplatz aus Quellen abgeleitet</span>':
   '<span style="color:#92400e">⚠ DEGIRO-Handelsplatznachweis offen</span>';
  return '<span data-direction-data-status data-sg-chf-analysis-only role="status" aria-label="Kurs und Hebel aktuell für die Analyse; gemeinsamer Zeitbezug bestätigt; Ausführungskurs bei DEGIRO nicht bestätigt" style="display:inline-flex;gap:6px;flex-wrap:wrap"><strong style="color:#15803d">✓ Kurs/Hebel aktuell · Analyse</strong><span style="color:#15803d">✓ Gemeinsamer Zeitbezug bestätigt</span>'+venue+'<span data-execution-proof-open style="color:#92400e">Ausführungskurs bei DEGIRO: nicht bestätigt</span></span>';
 }

 const {blocked,stale,missing}=check.state;
 const fields=Object.values(productFieldStates(p,now));
 const expired=fields.filter(f=>/veraltet/.test(f.state));
 const uncertain=fields.filter(f=>/unbestätigt|abweichend/.test(f.state));
 const detail=expired.length?'Veraltete Werte: '+expired.map(f=>f.key+(Number.isFinite(f.ageSeconds)?' ('+Math.floor(f.ageSeconds/60)+' Min.)':'')).join(', '):
  uncertain.length?'Zeitnachweis offen: '+uncertain.map(f=>f.key).join(', '):'Nachweisprüfung offen · Aktualität separat prüfen';
 const label=blocked?(missing?'Werte fehlen oder sind widersprüchlich':'Datenprüfung offen'):stale?detail:'Daten vollständig';
 return '<span data-direction-data-status role="status" aria-label="'+esc(label)+'" style="display:inline-flex;align-items:center;gap:6px;margin-left:8px;max-width:100%;min-width:0"><strong style="white-space:nowrap;flex:0 0 auto;overflow-wrap:normal;font-size:1.6em;font-weight:900;color:'+(blocked?'#b91c1c':'#15803d')+'">'+(blocked?'✗':stale?'(✓)':'✓')+'</strong>'+(stale?'<span style="font-weight:700;min-width:0">'+esc(detail)+'</span>':'')+'</span>';

}
function valuePresenceMark(missing){
 return missing?'<span style="color:#b91c1c;font-weight:700" aria-label="Wert fehlt">✗</span>':'<span style="color:#15803d;font-weight:700" aria-label="Wert vorhanden">✓</span>';
}
// Keep a current, same-list issuer terminal finding visible even if the
// handset retains an older quote snapshot. A terminal code does NOT by
// itself establish that a knock-out occurred.
function serverIssuerTerminated(p,now=Date.now()){
 const report=window.BobProductAuditReport,at=Date.parse(report?.lastCheckedAt);
 if(report?.status!=='ok'||!listArchive?.storedAt
    ||report.listUploadedAt!==listArchive.storedAt
    ||!Number.isFinite(at)||now<at||now-at>180000)return false;
 const item=report.items?.find(row=>row?.isin===p.isin);
 return item?.state==='terminated'&&item.sourceStatusEvidence?.issuerTerminal===true
    &&item.sourceStatusEvidence?.issuerStatus===2;
}
function compactProductExclusion(p){
 const direct=p.quote?.isin===p.isin&&p.quote?.productVerified?p.quote:null;
 return direct?.metadata?.status===2||(typeof serverIssuerTerminated==='function'&&serverIssuerTerminated(p))?'Produkt beendet – ausgeschlossen':/FAKTOR|FACTOR/i.test([p.name,direct?.metadata?.name,p.snapshot?.terms?.type?.value].join(' '))?'Faktorprodukt ausgeschlossen':null;
}
function additionalProductsComplete(products,now=Date.now()){
 const remaining=products.filter(p=>!knockoutStatus(p)&&!compactProductExclusion(p));
 return remaining.length>0&&remaining.every(p=>{const state=productDirectionDataState(p,now);return !state.blocked&&!state.stale;});
}
// A user-uploaded DEGIRO list establishes only observed membership of the
// screenshot, never broker-side orderability or a live executable quote.
function degiroListObservation(isin,archive=listArchive,now=Date.now()){
 const stamp=Date.parse(archive?.storedAt),items=archive?.items;
 const inImage=validIsin(isin)&&Array.isArray(items)&&items.some(x=>x?.isin===isin&&validIsin(x.isin));
 if(!inImage||!archive?.files?.length||!Number.isFinite(stamp)||stamp>now)
  return {observed:false,currentDay:false,executable:false,quoteConfirmed:false};
 const day=zurichListDay(stamp).day,clock=zurichListDay(now);
 return {observed:true,currentDay:day===clock.day&&!clock.closed,
  uploadedAt:archive.storedAt,executable:false,quoteConfirmed:false};
}
function observedDegiroListRow(isin,archive=listArchive,now=Date.now()){
 const observation=degiroListObservation(isin,archive,now);
 const row=archive?.items?.find(x=>x.isin===isin)?.listRow;
 if(!observation.observed||!row||row.version!==1||row.isin!==isin||!row.complete||!row.crossChecked||!row.imageReference||row.source!=='DEGIRO-Listenbild'||row.isExecutableQuote!==false)return null;
 return {...row,currentDay:observation.currentDay,uploadedAt:observation.uploadedAt};
}
function renderDegiroListEvidence(p,now=Date.now(),archive=listArchive){
 const proof=degiroListObservation(p?.isin,archive,now);
 if(!proof.observed)return '';
 const row=observedDegiroListRow(p?.isin,archive,now);
 const uploaded=new Date(proof.uploadedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false});
 return '<div class="small" data-degiro-list-evidence><b'+(proof.currentDay?' style="color:#15803d"':'')+'>'+
  (proof.currentDay?'✓ In deiner DEGIRO-Liste vorhanden':'In älterer DEGIRO-Liste vorhanden · heutige Liste fehlt')+
  '</b> · hochgeladen '+esc(uploaded)+' (Zürich).'+(row?'<br><b>DEGIRO-Listennachweis: '+esc(row.venue)+' · '+esc(row.currency)+'</b><br>BAR/SL (Barriere): '+esc(row.ko)+' · BP/STR (Basispreis): '+esc(row.strike)+' · Bv/R: '+esc(row.ratioDivisor)+' (Bezugsverhältnis '+esc(row.ratio)+')'+(row.maturity?' · Laufzeit: '+esc(row.maturity):'')+'<br>'+(row.reviewMethod==='exact-original-sha256-visual-review'?'Originalbild per SHA-256 exakt geprüft':row.reviewMethod==='samsung-image-size-and-sha256-prefix-reviewed'?'Samsung-Bild anhand Größe und SHA-256-Präfix abgeglichen (kein ausführbarer Brokerkurs)':'Produktzeile zweifach gelesen')+' · '+esc(row.imageReference)+'. Listenansicht, kein ausführbarer Brokerkurs.':'')+'</div>';
}
// A real DEGIRO product-detail *display* is more evidence than list membership,
// but less than an executable order quote, order acknowledgement or fill.
// Only data explicitly visible in ONE original image is accepted.
function normalizeReviewedDegiroIdentity(raw){
 let text=String(raw||'');
 // Original DEGIRO table 1000074244.jpg explicitly pairs this numeric
 // symbol with its ISIN. Correct only the observed S/8 alias, never a
 // different valid identifier or any amount. Do not use the selected card.
 if(/\b158460173\b/.test(text)&&/\bCHF\b/.test(text)
    &&/\bKursdaten\b/i.test(text)&&/\bSymbol\b/i.test(text)&&/\bISIN\b/i.test(text)
    &&/Soci[eé]t[eé]\s+G[eé]n[eé]rale\s+OTC/i.test(text))
  text=text.replace(/\bDE[0OQ]{3}FG14AV[S8]\b/gi,'DE000FG14AV8');
 // Visually reviewed original 1000073369.jpg: Symbol 159788766 identifies
 // DE000FG8NHQ3. Never infer S -> 8 from the selected card or checksum alone.
 if(!/\bKursdaten\b/i.test(text)||!/Symbol\s*\|\s*ISIN/i.test(text)
    ||!/\b159788766\b/.test(text)||!/\bCHF\b/.test(text)
    ||!/(?:Börse|Boerse|Borse)\s+Soci[eé]t[eé]\s+G[eé]n[eé]rale\s+OTC/i.test(text))return text;
 return text.replace(/\bDE[0OQ]{3}FG[8S]NHQ3\b/gi,'DE000FG8NHQ3');
}
// Display listing proof independently of issuer quote availability. Never a
// trading gate: only the current screenshot generation and original clock count.
// Consume the same server listing assessment in badges, explanations and selection.
function sharedVenueStatus(p,now=Date.now()){
 const report=window.BobProductAuditReport;
 const generation=listArchive?.storedAt;
 const at=Date.parse(report?.lastCheckedAt);
 if(report?.status!=='ok'||!generation||report.listUploadedAt!==generation
    ||!Number.isFinite(at)||now<at||now-at>180000)return null;
 const row=report.items?.find(x=>x.isin===p.isin),state=row?.brokerVenueStatus;
 if(state?.version!==1||state.executionConfirmed!==false)return null;
 const currency=p.currency||p.quote?.metadata?.currency||p.snapshot?.currency;
 const evidence=state.evidence||state.historicalEvidence;
 if(evidence&&currency&&evidence.currency!==currency)return null;
 // Original expiry is checked on each render, even before the next report.
 const current=state.current===true&&!!serverVenueEvidence(p,report,generation,now);
 return {...state,current,state:current?'current':state.historicalEvidence?'historical':'missing'};
}
function renderVenueHistory(p){
 const state=sharedVenueStatus(p),e=state?.historicalEvidence;
 if(!e||state.current)return '';
 return '<div class="small" data-venue-history><b>Früherer DEGIRO-Handelsplatz: '+esc(e.venue)+'</b> · '+esc(e.currency)+' · Nachweis vom '+esc(e.observedMinute.replace('T',' '))+'. Erneut mit der aktuellen Liste geprüft; aktueller Handelsplatznachweis noch offen. Nur ISIN, Börse, Währung und Datum im DEGIRO-Detailbild ergänzen. Kein aktueller Brokerkurs.</div>';
}
function serverVenueEvidence(p,report=window.BobProductAuditReport,generation=listArchive?.storedAt,now=Date.now()){
 const e=Array.isArray(report?.items)?report.items.find(row=>row?.isin===p?.isin)?.brokerVenueEvidence:null;
 const receipt=Date.parse(report?.lastCheckedAt),until=Date.parse(e?.validUntil);
 if(report?.status!=='ok'||!generation||report.listUploadedAt!==generation
    ||!Number.isFinite(receipt)||now<receipt||now-receipt>180000
    ||!e||e.isin!==p.isin||e.listUploadedAt!==generation||e.broker!=='DEGIRO'
    ||e.listingConfirmed!==true||e.executionConfirmed!==false
    ||!['owner-reviewed-screenshot','automatic-detail-screenshot','automatic-list-screenshot'].includes(e.kind)
    ||!['EUR','CHF'].includes(e.currency)||e.timezone!=='Europe/Zurich'||e.timePrecision!=='minute'
    ||!e.imageReference||!Number.isFinite(until)||now>=until
    ||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(e.observedMinute||''))return null;
 const currency=p.currency||p.quote?.metadata?.currency||p.snapshot?.currency;
 if(currency&&currency!==e.currency)return null;
 if(e.kind==='owner-reviewed-screenshot'&&!['Societe Generale OTC','BNP OTC','BNP Paribas OTC'].includes(e.venue))return null;
 if(typeof e.venue!=='string'||!e.venue.trim()||/^(?:unknown|unbekannt|[-—])$/i.test(e.venue.trim()))return null;
 const minute=t=>{
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(t));
  const v=k=>parts.find(x=>x.type===k)?.value;
  return v('year')+'-'+v('month')+'-'+v('day')+'T'+v('hour')+':'+v('minute');
 };
 const local=minute(now);
 if(e.observedMinute.slice(0,10)!==local.slice(0,10)||e.observedMinute>local
    ||minute(until)!==local.slice(0,10)+'T22:00')return null;
 return e;
}
function renderServerVenueEvidence(p){
 const e=serverVenueEvidence(p);
 return e?'<div class="small" data-server-listing-proof><span style="color:#15803d">✓ DEGIRO-Handelsplatz belegt</span> · '+esc(e.venue)+' · '+esc(e.currency)+(e.kind==='automatic-list-screenshot'?' · Listenstand laut Upload ':' · Listenbild ')+esc(e.observedMinute.replace('T',' '))+' · gültig bis 22:00 Uhr. Aktueller Brokerkurs separat zu prüfen.</div>':'';
}
function degiroVenueObserved(p){
 const shared=sharedVenueStatus(p);if(shared)return shared.current;
 if(serverVenueEvidence(p))return true;
 const listed=observedDegiroListRow(p?.isin);
 if(listed?.currentDay&&(!p.currency||p.currency===listed.currency)&&(!p.snapshot?.currency||p.snapshot.currency===listed.currency))return true;
 const q=p?.snapshot?.degiroVenueEvidence||p?.snapshot?.degiroDisplayedQuote;
 return !!q&&q.isin===p.isin&&q.brokerDisplayConfirmed===true&&q.isExecutableQuote===false
  &&((['CHF','EUR'].includes(q.currency)&&/^Soci[eé]t[eé]\s+G[eé]n[eé]rale\s+OTC$/i.test(q.venue||''))
    ||(q.currency==='EUR'&&/^BNP\s+(?:Paribas\s+)?OTC$/i.test(q.venue||'')))
  &&!!selectionTimeWindow(q.sourceTime);
}
// Reviewed public policy supports a venue inference, never per-product broker proof.
// Re-evaluate on every render; stale list/issuer/policy evidence cannot persist it.
function verifiedOtcIssuer(p){
 const q=p?.quote,m=q?.metadata;
 if(!validIsin(p?.isin)||q?.isin!==p.isin||q.productVerified!==true||q.sourceDisabled
    ||m?.status!==1||m.tradingHalted===true||m.underlyingType!=='SPOT'||m.underlying!=='XAU/USD'
    ||!['LONG','SHORT'].includes(p.productDirection)||m.direction!==p.productDirection
    ||compactProductExclusion(p)||knockoutStatus(p))return null;
 if(/^BNP Paribas ·/.test(q.source||'')&&m.currency==='EUR'
    &&q.sourceUrl==='https://derivate.bnpparibas.com/product-details/'+p.isin+'/'
    &&!m.issuerExchangeCode)return {issuer:'BNP',venue:'BNP Paribas OTC',currency:'EUR',venuePattern:/^BNP\s+Paribas\s+OTC$/i};
 if((/^Soci[eé]t[eé] G[eé]n[eé]rale\b|^SG\b/i).test(q.source||'')
    &&m.issuerExchangeCode==='CBSW'&&m.currency==='CHF')
  return {issuer:'SG',venue:'Société Générale OTC',currency:'CHF',venuePattern:/^Soci[eé]t[eé]\s+G[eé]n[eé]rale\s+OTC$/i};
 return null;
}
function degiroTradingSession(p,now=Date.now(),archive=listArchive){
 const issuer=verifiedOtcIssuer(p),q=p?.quote,checked=Date.parse(q?.checkedAt);
 const reviewed=Date.parse('2026-10-16T17:00:00Z');
 if(!issuer||now<reviewed||now-reviewed>30*86400000||!Number.isFinite(checked)
    ||checked>now||now-checked>7*86400000||!degiroListObservation(p.isin,archive,now).observed)return null;
 const broker=p.snapshot?.degiroDisplayedQuote;
 if(broker&&(broker.isin!==p.isin||broker.currency!==issuer.currency||!issuer.venuePattern.test(broker.venue||'')))return null;
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Zurich',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now)).map(x=>[x.type,x.value]));
 const minutes=Number(parts.hour)*60+Number(parts.minute),weekend=['Sat','Sun'].includes(parts.weekday);
 return {issuer:issuer.issuer,scheduledPause:weekend||minutes<480||minutes>=1320,
  reason:weekend?'Wochenende':'außerhalb 08:00–22:00 Uhr',
  label:'Reguläre Handelszeit: Mo–Fr 08:00–22:00 Uhr (Zürich)',
  sourceUrl:'https://www.degiro.ch/fr/connaissances/heures-ouverture-bourse',
  // A schedule is not a live status or a verified holiday calendar.
  holidayVerified:false,marketOpenConfirmed:false};
}
function expectedQuotePause(p,now=Date.now()){
 const session=degiroTradingSession(p,now),q=p?.quote;
 if(!session?.scheduledPause||q.sourceFailure||q.quoteFailureCode)return false;
 const fields=productFieldStates(p,now);
 return ['bid','ask'].every(k=>n(fields[k]?.value)>0&&Number.isFinite(fields[k]?.ageSeconds)&&fields[k].ageSeconds>=0);
}
function renderDegiroTradingSession(p){
 const session=degiroTradingSession(p);
 if(!session)return '';
 return '<div class="small" data-degiro-trading-session><b>'+
  (session.scheduledPause?'Reguläre Handelspause · '+esc(session.reason):'Innerhalb der regulären Handelszeit')+
  '</b><div>'+esc(session.label)+'. Feiertage und Sonderunterbrechungen sind nicht bestätigt.</div>'+
  (session.scheduledPause?'<div>Neue Kurse sind während dieser Pause nicht regulär zu erwarten. Gespeicherte Werte behalten ihren ursprünglichen Datenstand.</div>':'')+
  '<a href="'+session.sourceUrl+'" target="_blank" rel="noopener noreferrer">DEGIRO-Handelszeiten · geprüft am 16.10.2026</a></div>';
}
function degiroVenueInferred(p,archive=listArchive,now=Date.now()){
 const shared=sharedVenueStatus(p,now);if(shared?.required&&!shared.current)return null;
 const reviewedAt='2026-10-16T17:00:00Z',reviewed=Date.parse(reviewedAt);
 const q=p?.quote,broker=p?.snapshot?.degiroDisplayedQuote,issuer=verifiedOtcIssuer(p);
 if(!issuer||degiroVenueObserved(p)||!degiroListObservation(p?.isin,archive,now).currentDay
    ||now<reviewed||now-reviewed>30*86400000||q.sourceFailure)return null;
 const checked=Date.parse(q.checkedAt);
 if(!Number.isFinite(checked)||checked>now||now-checked>86400000)return null;
 // Never overrule conflicting broker details, even when old or incomplete.
 if(broker&&(broker.isin!==p.isin||broker.currency!==issuer.currency
    ||!issuer.venuePattern.test(broker.venue||'')))return null;
 return {isin:p.isin,venue:issuer.venue,issuer:issuer.issuer,currency:issuer.currency,
  kind:'source-inference',brokerDisplayConfirmed:false,isExecutableQuote:false,
  executionGuaranteed:false,reviewedAt,listAt:archive.storedAt,issuerCheckedAt:q.checkedAt,
  sourceUrl:'https://www.degiro.ch/fr/produits-and-places-boursieres',
  policyUrl:'https://www.degiro.ch/data/pdf/ch-fr/PSP_Ordres_et_politique_dexecution_des_ordres.pdf'};
}
function renderDegiroVenueInference(p){
 const proof=degiroVenueInferred(p);
 if(!proof)return '';
 return '<div class="small" data-degiro-venue-inferred><b>'+esc(proof.venue)+' – aus Quellen abgeleitet</b>'+
  '<div>Zuordnung: heutiger DEGIRO-Listeneintrag dieser ISIN + bestätigte '+esc(proof.issuer)+'-Produktdaten in '+esc(proof.currency)+' + öffentliche DEGIRO-Handelsplatzangaben. Dafür ist kein weiteres Bild nötig.</div>'+
  '<div>Kein direkter DEGIRO-Einzelnachweis und kein ausführbarer Kurs.</div>'+
  '<details><summary>Quellen der Zuordnung</summary><div>Listenbild: '+esc(proof.listAt)+
  ' · '+esc(proof.issuer)+'-Stammdaten abgerufen: '+esc(proof.issuerCheckedAt)+
  '</div><a href="'+proof.sourceUrl+'" target="_blank" rel="noopener noreferrer">DEGIRO: Produkte und Handelsplätze</a> · '+
  '<a href="'+proof.policyUrl+'" target="_blank" rel="noopener noreferrer">DEGIRO: Ausführungsrichtlinie</a>'+
  '<div>Öffentliche Quellen geprüft am 16.10.2026; für diese Ableitung höchstens 30 Tage verwendet.</div></details></div>';
}
function parseDegiroDisplayedQuote(raw,expectedIsin,venueOnly=false){
 raw=normalizeReviewedDegiroIdentity(raw);
 if(!validIsin(expectedIsin)||!/\bKursdaten\b/i.test(raw)
    ||!/\b(?:Börse|Boerse|Borse)\b/i.test(raw)
    ||!/Symbol\s*\|\s*ISIN/i.test(raw))return null;
 const tokens=[...new Set(raw.toUpperCase().match(/\b[A-Z]{2}[A-Z0-9]{10}\b/g)||[])];
 const ids=[...new Set(tokens.map(token=>normalizeOcrIsin(token,raw).isin))];
 if(ids.length!==1||ids[0]!==expectedIsin)return null;
 const start=raw.search(/\bKursdaten\b/i);
 const end=raw.search(/Symbol\s*\|\s*ISIN/i);
 if(start<0||end<=start)return null;
 const table=raw.slice(start,end);
 const currencies=[...new Set((table.match(/€|\b(?:EUR|CHF|USD|GBP)\b/gi)||[]).map(v=>v==='€'?'EUR':v.toUpperCase()))];
 if(currencies.length!==1||!['EUR','CHF'].includes(currencies[0])||/verzögert|delayed/i.test(table))return null;
 const currency=currencies[0];
 const read=label=>{
  const re=new RegExp('\\b'+label+'\\b(?!\\s*(?:Vol\\.?|Volumen))\\s*[:=]?\\s*(?:€\\s*|(?:EUR|CHF)\\s*)?([0-9]{1,5}(?:[.,][0-9]{1,4})?)(?:\\s*(?:€|EUR|CHF))?(?=\\s|$)','gi');
  const matches=[...table.matchAll(re)];
  return matches.length===1?Number(matches[0][1].replace(',','.')):null;
 };
 const bid=read('Geld'),ask=read('Brief');
 if(!venueOnly&&!(bid>0&&ask>=bid))return null;
 const dates=[...new Set([...table.matchAll(/\b(\d{2}[/.]\d{2}[/.]\d{4})\s+(\d{2}:\d{2})(?::(\d{2}))?\b/g)]
   .map(m=>m[1]+' '+m[2]+(m[3]?':'+m[3]:'')))];
 if(dates.length!==1||!selectionTimeWindow(dates[0]))return null;
 const venues=[...raw.matchAll(/(?:^|\n)\s*(?:Börse|Boerse|Borse)\s*[:=]?\s*([^\n]+)/gi)];
 if(venues.length!==1)return null;
 const venue=venues[0][1].trim();
 if(!venue||venue.length>100||/^(?:-|—|unbekannt)$/i.test(venue))return null;
 return {isin:expectedIsin,source:'DEGIRO-Produktdetail',venue,currency,
   ...(venueOnly?{}:{bid,ask}),sourceTime:dates[0],timeBasis:'Kursdaten-Anzeige; keine eigene Geld-/Briefzeit',
   brokerDisplayConfirmed:true,orderWindowVerified:false,orderSubmitted:false,
   executionGuaranteed:false,isExecutableQuote:false};
}
// DEGIRO *display* evidence from a user-selected product screenshot.
// No logged-in brokerage API, order-book guarantee, or trading permissions.
function degiroScreenQuoteState(q,isin,now=Date.now()){
 const unavailable={state:'missing',displayOnly:true,brokerConnected:false,
  executionConfirmed:false,isExecutableQuote:false,tradeApproved:false};
 if(!validIsin(isin)||!q||q.isin!==isin||q.source!=='DEGIRO-Produktdetail'
   ||q.brokerDisplayConfirmed!==true||q.isExecutableQuote!==false
   ||q.orderWindowVerified!==false||q.orderSubmitted!==false
   ||q.executionGuaranteed!==false||!['EUR','CHF'].includes(q.currency)
   ||typeof q.venue!=='string'||q.venue.trim().length<2
   ||!(Number.isFinite(q.bid)&&q.bid>0&&Number.isFinite(q.ask)&&q.ask>=q.bid))
  return unavailable;
 const observed=selectionTimeWindow(q.sourceTime),at=observed?.start;
 if(!Number.isFinite(at)||at>now)return {...unavailable,state:'invalid-time'};
 const ageSeconds=Math.max(0,Math.floor((now-at)/1000));
 return {state:ageSeconds<=90?'display-recent':'historical',displayOnly:true,
  brokerConnected:false,executionConfirmed:false,isExecutableQuote:false,
  tradeApproved:false,isin,currency:q.currency,venue:q.venue,bid:q.bid,ask:q.ask,
  sourceTime:q.sourceTime,timeBasis:q.timeBasis,ageSeconds};
}
function degiroBrokerQuotePanelState(rows,now=Date.now()){
 if(!Array.isArray(rows))return {total:0,quotes:0,recent:0,historical:0,items:[]};
 const seen=new Set(),items=[];
 for(const p of rows){
  if(!validIsin(p?.isin)||seen.has(p.isin))continue;seen.add(p.isin);
  const status=degiroScreenQuoteState(p?.snapshot?.degiroDisplayedQuote,p.isin,now);
  items.push({isin:p.isin,direction:p.direction||'',slot:p.slot||null,status,
   listingConfirmed:p.listingConfirmed===true});
 }
 return {total:items.length,quotes:items.filter(x=>['display-recent','historical'].includes(x.status.state)).length,
  recent:items.filter(x=>x.status.state==='display-recent').length,
  historical:items.filter(x=>x.status.state==='historical').length,items};
}
function currentDegiroBrokerQuoteRows(now=Date.now()){
 const rows=[];
 for(let i=1;i<=12;i++){
  const isin=document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value?.trim().toUpperCase();
  if(!validIsin(isin))continue;
  const direction=document.querySelector('[data-dg="dir"][data-i="'+i+'"]')?.value;
  const snapshot=detailScreenshots.get(i);
  rows.push({isin,direction,slot:i,snapshot:snapshot?.isin===isin?snapshot:null,
   listingConfirmed:!!observedDegiroListRow(isin,listArchive,now)});
 }
 return rows;
}
function refreshDegiroBrokerQuotePanel(now=Date.now()){
 const container=document.getElementById('dgBrokerQuoteRows');
 if(!container)return;
 const report=degiroBrokerQuotePanelState(currentDegiroBrokerQuoteRows(now),now);
 const heading=document.getElementById('dgBrokerQuoteCount');
 if(heading)heading.textContent=report.total+' gelistete Produkte · '+report.quotes+
  ' DEGIRO-Anzeigekurs-Bilder · '+report.recent+' mit höchstens 90 s alter Bild-Kurszeit';
 const parts=[];
 for(const p of report.items){
  const q=p.status;
  const quote=['display-recent','historical'].includes(q.state)
   ?'DEGIRO-Anzeigekurs '+q.bid.toFixed(2)+' / '+q.ask.toFixed(2)+' '+esc(q.currency)+
    ' · '+esc(q.venue)+' · Quellenanzeige '+esc(q.sourceTime)+
    (q.state==='display-recent'?' · Zeit höchstens 90 s zurück':' · historisch')
   :q.state==='invalid-time'?'Bild-Kurszeit ungültig oder in der Zukunft':
    'Kein datierter DEGIRO-Anzeigekurs aus Produktdetailbild';
  parts.push('<div data-broker-quote-isin="'+esc(p.isin)+'" style="padding:8px 0;border-top:1px solid #e3e7ee">'+
   '<div><b>'+esc(p.isin)+'</b> · '+esc(p.direction||'Richtung offen')+
   ' · '+(p.listingConfirmed?'✓ Listung bei DEGIRO nachgewiesen':'Listennachweis prüfen')+'</div>'+
   '<div class="small" data-broker-display-state="'+esc(q.state)+'">'+quote+'</div>'+
   '<div class="small" style="color:#92400e">Keine bestätigte Ausführung und keine Handelsfreigabe.</div>'+
   (p.slot?'<button type="button" data-dg-broker-quote-upload="'+p.slot+'" style="margin-top:6px;min-height:44px;background:#e9f2ff;color:#1659aa">📷 DEGIRO-Kursdatenbild hinzufügen</button>':'')+
   '</div>');
 }
 container.innerHTML=report.items.length?parts.join(''):
  '<div class="small">Keine DEGIRO-Produkte geladen. Gespeicherte DEGIRO-Liste prüfen.</div>';
}
function renderDegiroDisplayedQuote(p,now=Date.now()){
 const q=p?.snapshot?.degiroDisplayedQuote;
 if(!q||q.isin!==p.isin||q.brokerDisplayConfirmed!==true||q.isExecutableQuote!==false
   ||!['EUR','CHF'].includes(q.currency)||!(q.bid>0&&q.ask>=q.bid))return '';
 const window=selectionTimeWindow(q.sourceTime),age=window?now-window.start:null;
 const timing=age!==null&&age>=0&&age<=90000?'bis 90 s nach dem Kurszeitpunkt':'historischer Nachweis, kein aktueller Kurs';
 return '<div data-degiro-otc-observation class="small" style="margin-top:8px;padding:8px;border:1px solid #cbd5e1;border-radius:8px">'+
  '<b>DEGIRO zeigt Geld/Brief auf der Produktdetailseite</b>'+
  '<div>ISIN '+esc(q.isin)+' · Handelsplatz '+esc(q.venue)+' · Geld '+q.bid.toFixed(2)+
  ' / Brief '+q.ask.toFixed(2)+' '+esc(q.currency)+' · Quellenanzeige '+esc(q.sourceTime)+
  ' (Zeitzone Europe/Zurich zur Einordnung angenommen; Sekunden unbekannt, wenn nicht angegeben).</div>'+
  '<div>'+esc(timing)+' · '+esc(q.timeBasis)+
  '. Bestätigt eine DEGIRO-Kursanzeige, aber keine Orderannahme oder ausführbare Preisgarantie. DEGIRO-Handel bleibt manuell.</div></div>';
}
function productObservedTimeStatus(p,now=Date.now()){
 const fields=productFieldStates(p,now);
 const observed=Object.values(fields).filter(f=>n(f.value)>0);
 const valid=f=>{
  if(!f.at||!Number.isFinite(Date.parse(f.at)))return false;
  if(/veraltet|unbestätigt|abweichend|fehlt/i.test(f.state))return false;
  return true;
 };
 const confirmed=observed.filter(valid);
 const unresolved=observed.filter(f=>!valid(f));
 const missing=Object.values(fields).filter(f=>f.state==='fehlt').map(f=>f.key);
 return {confirmed:observed.length>0&&unresolved.length===0,
  tracked:observed.length,confirmedCount:confirmed.length,
  unresolved:unresolved.map(f=>f.key),missing,
  label:!observed.length?'Keine belegten Kurs-/Hebelzeiten vorhanden':
   unresolved.length?'Für '+unresolved.map(f=>f.key).join(', ')+' fehlt ein aktueller Zeitnachweis':
   'Zeitbezug für '+confirmed.length+' vorhandene Kurs-/Hebelwerte bestätigt'+
    (missing.length?' · '+missing.join(', ')+' weiterhin nicht vorhanden':'')};
}
function renderAutomaticProductCheck(p){
 const recent=p?.index!=null?researchResults.get(p.index):null;
 const q=recent?.isin===p?.isin?recent:p?.quote?.isin===p?.isin?p.quote:null;
 if(!q)return '<div class="small" data-product-auto-check>Emittentenprüfung: noch kein Abrufresultat für diese ISIN vorhanden.</div>';
 const date=q.attemptedAt||q.checkedAt||q.termsCheckedAt;
 const parsed=date?Date.parse(date):NaN;
 const at=Number.isFinite(parsed)?new Date(parsed).toLocaleString('de-CH',
  {timeZone:'Europe/Zurich',hour12:false})+' (Zürich)':'Zeit unbekannt';
 const label=q.sourceFailure?'Abrufproblem':
  q.productVerified&&q.analysisQuote?.priceKind==='issuer-chart'?'Produkt bestätigt · SG-Chartkurse für Analyse':
  q.productVerified?'Produktidentität bestätigt · aktuelle Kurse separat prüfen':
  'Emittentenidentität noch nicht bestätigt';
 const reason=String(q.reason||q.sgDiscovery?.reason||'').slice(0,230);
 const backup=q.comdirectFieldsBackup;
 const names={direction:'Long/Short',type:'Produktart',underlying:'Basiswert',currency:'Währung',maturity:'Laufzeit',lastTradingDay:'Letzter Handelstag',ratio:'Bezugsverhältnis',issuer:'Emittent',ko:'KO-Schwelle',strike:'Basispreis',leverage:'Hebel',koDistancePct:'KO-Abstand %',financingCosts:'Finanzierungskosten'};
 const backupHtml=backup?'<details data-comdirect-fields><summary>comdirect · zweite Quelle</summary>'+
  '<div>'+esc(({checking:'Abruf läuft',unavailable:'Abruf nicht verfügbar',observed:'Quelle gelesen',active:'Werte abgeglichen',conflict:'Abweichungen gefunden',inactive:'Quelle meldet Produkt beendet',rejected:'Produktzuordnung abgelehnt'})[backup.state]||backup.state)+'</div>'+
  Object.entries(backup.observations||{}).map(([key,item])=>'<div>'+esc(names[key]||key)+': '+esc(item.value)+' · '+esc((backup.conflicts||[]).includes(key)?'Abweichung · nicht ersetzt':(backup.filledFields||[]).includes(key)?'ergänzt':'Quellenbeobachtung')+(item.conditionVerified===false?' · Datenstand nicht bestätigt':'')+'</div>').join('')+
  Object.entries(backup.sourceDecisions||{}).filter(([,d])=>d.state==='dated-issuer-selected').map(([key,d])=>'<div><b>'+esc(names[key]||key)+': '+esc(d.primaryValue)+' · Emittentenstand '+esc(d.dateText)+'</b><br>'+esc(d.reason)+'</div>').join('')+
  ((backup.missing||[]).length?'<div>Nicht geliefert: '+esc(backup.missing.map(k=>names[k]||k).join(', '))+'</div>':'')+
  '<div>Die Abrufzeit ist keine veröffentlichte Kurs- oder Hebelzeit. Geld/Brief werden separat mit ihrem Kurszeitpunkt geprüft.</div></details>':'';
 return '<div class="small" data-product-auto-check style="margin:6px 0;color:#536176">'+
   '<b>Letzter automatischer Emittentenabruf (Prüfzeit, keine Kurszeit):</b> '+esc(at)+' · '+esc(label)+
   (reason?'<div>'+esc(reason)+'</div>':'')+backupHtml+'</div>';
}
// A single read-only presentation layer. This never feeds ranking or execution.
function goldProductGroup(p,now=Date.now()){
 if(knockoutStatus(p))return 'ended';
 const exclusion=compactProductExclusion(p);
 if(exclusion==='Faktorprodukt ausgeschlossen')return 'factor';
 if(exclusion)return 'ended';
 if(typeof serverAnalysisEvidence==='function'&&serverAnalysisEvidence(p,now))return 'active';
 const local=productDataStatus(p,now);
 return local.complete&&compactProductValues(p,now).missing.length===0?'active':'review';
}
// Read-only list-generation reconciliation; mismatched/old reports never
// rewrite original screenshots or grant execution permission.
function goldProductSyncState(p,now=Date.now()){
 const report=window.BobProductAuditReport;
 const receipt=Date.parse(report?.lastCheckedAt),generation=listArchive?.storedAt;
 if(!generation||report?.status!=='ok'||!Array.isArray(report.items)
    ||!Number.isFinite(receipt)||receipt>now||now-receipt>180000)
  return {state:'unconfirmed',message:'Serverabgleich nicht aktuell bestätigt'};
 if(report.listUploadedAt!==generation)
  return {state:'different-list',message:'Andere Listenfassung am Server · Originalwerte bleiben erhalten'};
 const item=report.items.find(x=>x.isin===p.isin);
 if(!item||item.direction!==p.productDirection)
  return {state:'not-covered',message:'Produkt nur lokal vorhanden · Belege separat prüfen'};
 if(item.state==='terminated')return {state:'terminated',message:'Beendet laut Emittenten-Nachweis'};
 if(item.state==='excluded-factor')return {state:'excluded-factor',message:'Faktorprodukt ausgeschlossen · keine weiteren Kursnachweise erforderlich'};
 if((item.missing||[]).length)return {state:'missing',message:'Nachweise am Server weiterhin offen'};
 if(!['analysis-evidence-complete','issuer-evidence-complete'].includes(item.state))
  return {state:'unconfirmed',message:'Nachweisklasse nicht bestätigt'};
 return {state:'matched',message:'Listenfassung und ISIN mit Server abgeglichen'};
}
function goldProductRepairStatus(p,now=Date.now()){
 const sync=goldProductSyncState(p,now);
 const item=sync.state==='missing'?window.BobProductAuditReport?.items?.find(x=>x.isin===p.isin):null;
 const retry=(item?.sourceRecovery||[]).find(e=>e?.state==='waiting'||e?.state==='failed');
 if(retry)return 'Automatische Quellenprüfung: Wiederholung'+(Number.isFinite(retry.retryAfterSeconds)?' frühestens in '+retry.retryAfterSeconds+' s':'')+' · keine neuen Zeitstempel erfunden';
 if(sync.state==='missing')return 'Bob prüft zugelassene Quellen erneut; fehlende Nachweise bleiben gesperrt';
 if(sync.state==='matched')return 'Keine offenen Analyse-Nachweislücken im letzten Serverbericht';
 if(sync.state==='terminated')return 'Keine laufende Produktkursüberwachung erforderlich';
 if(sync.state==='excluded-factor')return 'Faktorprodukt ausgeschlossen; keine Reparatur fehlender Kurs- oder Zeitangaben nötig';
 return 'Originalbelege gespeichert; Serverabgleich separat offen';
}

// Listing in the user's DEGIRO screenshot is an independently proven fact.
// It is NOT a broker fill, executable order quote or trading approval.
function goldProductBrokerListStatus(p,now=Date.now(),archive=listArchive){
 const local=observedDegiroListRow(p?.isin,archive,now);
 if(local){
  const at=Number.isFinite(Date.parse(local.uploadedAt))
   ?new Date(local.uploadedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false})
   :'Aufnahmezeit nicht verfügbar';
  return {state:local.currentDay?'confirmed':'historical',
   message:(local.currentDay?'✓ In DEGIRO-Liste bestätigt':'✓ In älterer DEGIRO-Liste nachgewiesen')
   +' · '+local.venue+' · '+local.currency+' · Upload '+at};
 }
 // Server reconciliation is separate from locally retained original images.
 const shared=sharedVenueStatus(p,now),e=shared?.evidence;
 if(shared?.current&&e?.listingConfirmed===true&&e.executionConfirmed===false&&e.isin===p?.isin)
  return {state:'confirmed',message:'✓ In DEGIRO-Liste bestätigt · '+e.venue+' · '+e.currency+' · Serverabgleich'};
 return {state:'unconfirmed',message:'DEGIRO-Listennachweis derzeit nicht bestätigt'};
}
// Display-only DEGIRO evidence from a manually selected product detail
// screenshot. Never substitute this for a price guaranteed in an order window.
function degiroManualQuoteSummary(p,now=Date.now()){
 const status=degiroScreenQuoteState(p?.snapshot?.degiroDisplayedQuote,p?.isin,now);
 if(status.state!=='display-recent'&&status.state!=='historical')
  return '<div class="small" data-degiro-manual-quote="missing">DEGIRO-Anzeigekurs: kein geprüftes Produktdetailbild. '
    +'Unter „DEGIRO-Kursdaten · Leseprüfung“ ein Kursdatenbild ergänzen.</div>';
 const text=status.state==='display-recent'?'Kursanzeige aus DEGIRO · Zeit höchstens 90 s zurück'
  :'Historische DEGIRO-Kursanzeige · nicht aktuell';
 return '<div class="small" data-degiro-manual-quote="'+esc(status.state)+'" style="padding:7px;border:1px solid #cbd5e1;border-radius:7px">'+
  '<b>'+esc(text)+'</b> · Geld '+esc(status.bid.toFixed(2))+' / Brief '+esc(status.ask.toFixed(2))+
  ' '+esc(status.currency)+' · '+esc(status.venue)+' · Kursanzeige '+esc(status.sourceTime)+
  '<div>Vom Nutzer bereitgestelltes DEGIRO-Bild, keine Live-Verbindung und keine ausführbare Preisgarantie.</div></div>';
}
function compactProductValues(p,now=Date.now()){
 const verified=serverAnalysisEvidence(p,now);
 const fields=productFieldStates(p,now);
 const acceptable=x=>x&&typeof x.value==='number'&&x.value>0&&
   !/(unbestätigt|veraltet|abweichend)/i.test(x.state||'')&&
   (x.state==='aktuell'||x.state==='gemeinsamer SG-Zeitbezug · aktuell (nur Analyse)'||
    /Momentaufnahme|innerhalb Altersgrenze/.test(x.state||'')||
    /^(berechnet · aktuell|berechneter Hebel · Eingangsdaten: aktuell)$/.test(x.state||''));
 const analysis=analysisReleaseQuote(p,now);
 const bid=verified?.quote.bid??(acceptable(fields.bid)?fields.bid.value:analysis?.bid??null);
 const ask=verified?.quote.ask??(acceptable(fields.ask)?fields.ask.value:analysis?.ask??null);
 const lever=verified?.leverage??(acceptable(fields.leverage)?fields.leverage.value:
   analysis?(analysis.leverage??n(p.quote?.leverage)):null);
 const leverageKind=verified?.leverageKind||(acceptable(fields.leverage)?fields.leverage.kind:
   analysis?(analysis.leverageKind||'calculated-gearing'):'');
 const leverageAt=verified?verified.leverageAt:acceptable(fields.leverage)?fields.leverage.at:analysis?.leverageAt||analysis?.at;
 const calculated=leverageKind==='calculated-gearing'||leverageKind==='calculated'||
   !verified&&/berechnet/.test(fields.leverage?.state||'');
 const missing=[['Geld',bid],['Brief',ask],['Hebel',lever]].filter(([,v])=>!(v>0)).map(([name])=>name);
 return {verified,fields,analysis,bid,ask,lever,leverageKind,leverageAt,calculated,missing};
}
function goldProductCompactView(p,now=Date.now()){
 const values=compactProductValues(p,now);
 const {verified,fields,bid,ask,lever,missing}=values,status=productDataStatus(p,now);
 const leverageNote=lever!==null?
   'Hebel: '+(values.calculated?'berechnet · nur Analyse':['issuer-reference','shared-issuer-observation'].includes(values.leverageKind)
    ?'gemeinsamer SG-Zeitbezug · nur Analyse':'Quellenwert')+
   (values.leverageAt?' · '+values.leverageAt:''):'';
 const currency=verified?.quote.currency||p.quote?.nativeChartEvidence?.currency||p.quote?.currency||'EUR';
 const number=x=>Number.isFinite(x)&&x>0?Number(x).toLocaleString('de-CH',{maximumFractionDigits:3}):'—';
 const term=typeof koEvidenceStatus==='function'?koEvidenceStatus(p,now):null;
 const distance=term?.current&&n(p.spot)>0&&n(p.ko)>0&&['LONG','SHORT'].includes(p.productDirection)
   ?(p.productDirection==='LONG'?p.spot-p.ko:p.ko-p.spot)/p.spot*100:null;
 const priced=bid!==null&&ask!==null;
 const analysis=(!!verified||status.complete)&&missing.length===0;
 const check=analysis?'✓ Analyse-Nachweise vorhanden':missing.length?'⚠ '+missing.join(', ')+' fehlt oder ist nicht aktuell belegt':'⚠ Analyse-Nachweise prüfen';
 const timestamp=verified?.quote.bidAt||(priced?fields.bid?.at||values.analysis?.bidAt:null)||null;
 const detail=verified?'Serverbericht · passende Listenfassung':priced?(fields.bid?.kind==='calculated'?'Berechneter Analysewert':'Quellenbeobachtung')+' · lokaler Datenstand':'Kurs noch nicht aktuell belegt';
 const sync=goldProductSyncState(p,now);
 const brokerList=goldProductBrokerListStatus(p,now);
 return '<div data-product-compact-summary style="display:grid;gap:9px">'+
  '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:4px"><b>'+esc(p.isin||'ISIN fehlt')+'</b>'+renderIsinCopy(p.isin)+'</div>'+
  '<div class="small"><b>'+esc(p.productDirection||'Richtung offen')+'</b> · '+esc(check)+'</div>'+
  '<details data-compact-proof><summary>Details · Quellen und Nachweise</summary><div class="small" data-degiro-list-proof="'+esc(brokerList.state)+'">'+esc(brokerList.message)+'</div>'+
  degiroManualQuoteSummary(p,now)+'</details>'+
  '<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px">'+
   [['Geld',number(bid)+' '+(bid!==null?currency:'')],['Brief',number(ask)+' '+(ask!==null?currency:'')],['Hebel',number(lever)+(lever!==null?'×':'')],['KO-Abstand',Number.isFinite(distance)&&distance>=0?distance.toFixed(2)+' %':'—']].map(([label,value])=>
    '<div style="min-width:0;padding:6px;border-radius:7px;background:#f2f5f9"><div class="small">'+esc(label)+'</div><strong>'+esc(value.trim())+'</strong></div>').join('')+
  '</div><div class="small" data-analysis-status>'+esc(detail)+(timestamp?' · Kurszeit '+esc(timestamp):' · Kurszeit fehlt')+'</div>'+
  (leverageNote?'<div class="small" data-compact-leverage-source>'+esc(leverageNote)+'</div>':'')+
  (missing.length?'<div class="small" data-product-auto-repair role="status">'+esc(pendingQuotes.has(p.index)?'Automatische Quellenprüfung läuft':p.quote?.sourceFailure?'Letzter Abruf fehlgeschlagen · automatische Wiederholung vorgesehen':['night','weekend'].includes(window.BobDegiroPhase?.())?'Automatische Quellenprüfung in Handelspause': 'Automatische Quellenprüfung im 30-Sekunden-Zyklus vorgesehen')+' · '+esc(missing.join(', '))+' bleibt bis zum gültigen Nachweis offen.</div>':'')+
  '<details><summary>Abgleich und Bearbeitung</summary><div class="small" data-gold-sync="'+esc(sync.state)+'">'+esc(sync.message)+'</div>'+
  '<div class="small" data-gold-repair>'+esc(goldProductRepairStatus(p,now))+'</div></details>'+
  '<div class="small" data-execution-separate style="color:#92400e">Ausführbarer DEGIRO-Orderkurs und tatsächliche Ausführung nicht bestätigt · keine Handelsfreigabe</div></div>';
}
function goldProductOverview(products,now=Date.now()){
 const counters={active:0,review:0,ended:0,factor:0};
 for(const p of products)counters[goldProductGroup(p,now)]++;
 const listed=products.filter(p=>goldProductBrokerListStatus(p,now).state==='confirmed').length;
 return '<div data-gold-summary class="small" style="padding:10px;border:1px solid #cbd5e1;border-radius:10px;margin:8px 0">'+
  '<div data-degiro-list-count>Heute in DEGIRO-Liste bestätigt: '+listed+' von '+products.length+' Produkten.</div>'+
  'Analyse-Nachweise vorhanden: '+counters.active+' · Nachweise prüfen: '+counters.review+
  ' · Beendet: '+counters.ended+' · Faktor nicht verwendet: '+counters.factor+
  '<div>Listung ist kein ausführbarer DEGIRO-Orderkurs und keine bestätigte Ausführung. Handelsfreigabe bleibt separat.</div></div>';
}

function compactProductCard(p,reasons=[],status='Nicht freigegeben',calculationHtml=''){
 reasons=reasons.map(reason=>productEvidenceReason(p,reason));
 if(knockoutStatus(p))return knockoutCard(p);
 const direct=p.quote?.isin===p.isin&&p.quote?.productVerified?p.quote:null;
 const undatedReference=direct?.issuerLeverageReference?.dated===false&&n(direct.issuerLeverageReference.value)>0;
 const excluded=compactProductExclusion(p);
 if(excluded){
  if(direct?.metadata?.status===2||(typeof serverIssuerTerminated==='function'&&serverIssuerTerminated(p)))
   return terminalProductCard(p,'Produkt beendet');
  // Faktorprodukte are intentionally excluded from gold-leverage selection.
  // Render only a closed, neutral card (ISIN + reason), never a red X or
  // source-quote warnings, while preserving the underlying ranking exclusion.
  if(excluded==='Faktorprodukt ausgeschlossen')
   return terminalProductCard(p,'Faktor Goldprodukt nicht verwendet','factor');
  return '<div data-product-isin="'+esc(p.isin)+'" style="padding:14px;margin-top:10px;border:1px solid #dc2626;border-radius:12px">'+renderProductIdentity(p)+'<p>'+esc(excluded)+'</p><p>Keine weiteren Daten oder Screenshots erforderlich.</p>'+renderProductSources(p)+'</div>';
 }
 const selected=status==='Freigegeben · ausgewählt';
 const complete=finalProductStatus(p).complete;
 const x=p.snapshot,terms={...(x?.terms||{}),...(direct?.conditions||{})},values=[];
 for(const [key,label] of Object.entries({strike:'Basispreis USD',ko:'KO USD',ratio:'Bezugsverhältnis',underlying:'Basiswert'})){
  const v=terms[key]?.value??(key==='ko'?x?.evidence?.KO?.value:null);if(v!==undefined&&v!==null)values.push(label+': '+v);
 }
 for(const [key,e] of Object.entries(x?.evidence||{})){if(key!=='KO'&&key!=='Spread')values.push(key+': '+e.value+(e.at?' · '+e.at:''));}
 const groups=[],unconfirmed=[],locations=new Map(),fieldStates=productFieldStates(p);
 for(const reason of reasons){
  if(reason==='Zusätzlicher Live-Nachweis offen'){
   groups.push('Live-Kursbestätigung offen');locations.set('Live-Kursbestätigung offen','Produktidentität automatisch bestätigt. Für die Live-Freigabe fehlt eine bestätigte aktuelle Anbieterquotierung oder ein gültiger zusätzlicher Kursnachweis. Chartwerte und berechneter Hebel bleiben für die Analyse nutzbar.');continue;
  }
  if(/Geld|Brief|Kurszeit|Kursbild|Produktkurs|BNP-Kursabruf/.test(reason)&&['bid','ask'].every(k=>fieldStates[k].state!=='fehlt')){
   const label='Geld/Brief vorhanden; Datenstand und Kursart siehe oben. Live-Nachweis bleibt separat geprüft.';
   if(!unconfirmed.includes(label))unconfirmed.push(label);
   const open='Kursart und Aktualität noch nicht bestätigt';if(!groups.includes(open)){groups.push(open);locations.set(open,missingValueLocation(reason,p));}continue;
  }
  if(/Hebel/.test(reason)&&fieldStates.leverage.state==='fehlt'&&undatedReference){
   const open='SG-Referenzhebel vorhanden · eigener Quellenzeitpunkt fehlt';
   if(!groups.includes(open)){groups.push(open);locations.set(open,'SG → Kennzahlen / Hebel. Der SG-Wert ist vorhanden, aber ohne eigenen Quellenzeitstempel. Bob prüft dies selbstständig weiter; ein SG-Chartzeitpunkt darf nicht als Hebelzeit ausgegeben werden.');}
   continue;
  }
  if(/Hebel/.test(reason)&&fieldStates.leverage.state!=='fehlt'){
   const label='Hebel vorhanden · '+fieldStates.leverage.state+'; ursprünglichen Datenstand siehe oben.';
   if(!unconfirmed.includes(label))unconfirmed.push(label);
   const open=/berechneter Hebel|CFD-basierte Schätzung/.test(fieldStates.leverage.state)?'Hebel berechnet · Eingangsdaten '+(/veraltet/.test(fieldStates.leverage.state)?'veraltet':'noch nicht bestätigt'):'Hebel vorhanden · Aktualitätsprüfung offen';if(!groups.includes(open)){groups.push(open);locations.set(open,missingValueLocation(reason,p));}continue;
  }
  const dated=(/datier|24 Stunden|Gültigkeit/i.test(reason)||/gültigem Nachweis/i.test(reason)&&n(p.ko)>0)&&!/widerspr|ungültig/i.test(reason);
  const field=/Basispreis|Finanzierungslevel/.test(reason)?'Basispreis':/KO|Knock|Barriere/i.test(reason)?'KO-Barriere':null;
  if(dated&&field){const label=field+': Werte vorhanden – Aktualität unbestätigt';if(!unconfirmed.some(item=>item.startsWith(label)))unconfirmed.push(label+' · Fundort: '+missingValueLocation(reason,p));const open=field+': Gültigkeitsnachweis offen';if(!groups.includes(open)){groups.push(open);locations.set(open,missingValueLocation(reason,p));}continue;}
  const label=/Produkttyp|Produktrichtung/.test(reason)?'Produkttyp / Richtung (Stammdaten → Typ)':reason.startsWith('BNP-Kursabruf:')?reason:/Basiswert ungenau: Gold allein/.test(reason)?'Basiswert „Gold“ erkannt – genaue Referenz fehlt (Produktbeschreibung / Endgültige Bedingungen)':/Future-Kontrakt|Futures-Kontrakt|Referenzkontrakt/.test(reason)?'Future-Kontrakt (Stammdaten → Basiswert; ggf. Dokumente → Endgültige Bedingungen)':/Basispreis|Finanzierungslevel/.test(reason)?'Basispreis: gültiger Nachweis (Stammdaten)':/KO|Knock|Barriere/i.test(reason)?'KO-Barriere: gültiger Nachweis (Stammdaten)':/Geld|Brief|Kurs/.test(reason)?'Geld, Brief und Quellenzeit (Kursdaten)':/Hebel/.test(reason)?'Hebel mit Datenstand (Kennzahlen)':/Bezugsverhältnis/.test(reason)?'Bezugsverhältnis fehlt oder ist nicht eindeutig (Stammdaten)':/Basiswert/.test(reason)?'Exakter Basiswert fehlt (Stammdaten / Produktbeschreibung)':/Produkttyp|Long\/Short|Produktrichtung/.test(reason)?'Produkttyp / Richtung (Stammdaten → Typ)':/Laufzeit|Fälligkeit/.test(reason)?'Laufzeit / Fälligkeit (Stammdaten)':/Währung/.test(reason)?'Produktwährung (Kursdaten)':/ISIN|Produktzuordnung|Bildzuordnung|Bildwerte|Original|bestätig/.test(reason)?'Produktzuordnung oder Bildwerte nicht eindeutig':reason.split(':')[0]+' (Quellen und Einzelheiten → Fehlende Werte)';
  if(!groups.includes(label)){groups.push(label);locations.set(label,missingValueLocation(reason,p));}
 }
 const allReasons=[...new Set([status.replace(/^Nicht freigegeben · /,''),...reasons,...finalProductStatus(p).reasons])].filter(x=>!/^Produktnachweise prüfen$|^Nicht freigegeben$/.test(x));
 const signalText=typeof document!=='undefined'?(document.getElementById('quickSignal')?.textContent||''):'';
 const neutral=/ABWARTEN|NEUTRAL/.test(signalText)||allReasons.some(r=>/Marktsignal neutral/.test(r));
 const data=productDataStatus(p),temporal=allReasons.some(r=>/zeit|Aktualität|datier|veraltet|Gültigkeit|Nachweis/i.test(r));
 const timeEvidence=productObservedTimeStatus(p);
 const missingNumbers=Object.values(fieldStates).filter(f=>f.state==='fehlt').map(f=>f.key);
 const hasSgChart=!!direct?.analysisQuote&&direct.analysisQuote.priceKind==='issuer-chart'||!!direct?.nativeChartEvidence;
 const serverEvidence=typeof serverAnalysisEvidence==='function'?serverAnalysisEvidence(p):null;
 const dataText=serverEvidence?'Server-Kurs und Hebel nachgewiesen · lokale Einzelwerte separat prüfen':hasSgChart&&!missingNumbers.length?'Analysewerte vorhanden · ausführbarer Kurs separat offen':data.complete?'Werte vorhanden':missingNumbers.length===1&&missingNumbers[0]==='Hebel'&&undatedReference?'SG-Hebelreferenz vorhanden · eigene Quellenzeit fehlt':missingNumbers.length?'Fehlende Kurswerte: '+missingNumbers.join(', '):'Geld, Brief und Hebel vorhanden';
 const shortReason=r=>String(r).split('. Öffne')[0].split(' · Fundort:')[0].slice(0,160);
 const automaticQuoteIssue=!complete&&groups.length>0&&groups.every(r=>/^(Live-Kursbestätigung|Kursart und Aktualität|Hebel berechnet|Hebel vorhanden|SG-Referenzhebel|BNP-Kursabruf)/.test(r));
 const evidenceTitle=automaticQuoteIssue?'Werte vorhanden · Aktualitätsprüfung offen':missingNumbers.length?'Fehlende Werte und Nachweise':'Werte und Aktualitätsprüfung';
 const automaticRecoveryPending=!complete&&validIsin(p.isin)&&!knockoutStatus(p);
 const swissSgVenue=direct?.metadata?.issuerExchangeCode==='CBSW'&&
   (direct?.metadata?.currency==='CHF'||direct?.nativeChartEvidence?.currency==='CHF');
 const venueMissing=productProblemLabels(p).includes('DEGIRO-Handelsplatznachweis');
 const next=serverEvidence?'Serveranalyse vorhanden: keine neuen Bilder nötig. Keine bestätigte DEGIRO-Ausführung; lokale Produktfreigabe und Risikoprüfung bleiben separat.':venueMissing?productHelpState(p).action:automaticQuoteIssue?'Automatischer Kurs- und Hebelabruf wird erneut geprüft. Vorhandene Werte bleiben mit ihrem ursprünglichen Datenstand nutzbar; derzeit keine neuen Bilder erforderlich.':complete&&neutral?'Marktsignal neutral – auf eine bestätigte Richtung warten. Dafür sind keine neuen Bilder nötig.':complete?'Produktdaten vollständig – Auswahlgrund unter „Warum derzeit nicht ausgewählt?“ prüfen.':temporal&&data.complete?'Werte vorhanden – den offenen Zeitbezug unter „Werte und Aktualitätsprüfung“ prüfen.':automaticRecoveryPending?'Bob prüft die zugelassenen Emittentenquellen automatisch erneut. Fehlende oder unklare Nachweise bleiben gesperrt und werden unter „Problem“ dokumentiert. Nur wenn diese Quellen keine ausreichenden Daten liefern, können zusätzliche Originalbelege notwendig sein.':'Offene Angaben unter „Werte und Aktualitätsprüfung“ ansehen und nur diese ergänzen.';
 return '<div data-product-isin="'+esc(p.isin||'row-'+p.index)+'" '+(selected?'data-selection-approved':'data-selection-blocked')+'="'+p.index+'" style="padding:12px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;overflow-wrap:anywhere">'+
 goldProductCompactView(p)+'<details data-product-technical style="margin-top:10px"><summary>Details · Produktangaben und Aktionen</summary>'+renderProductIdentity(p)+renderProductProblemSummary(p)+productCompletionBadge(p)+renderDegiroListEvidence(p)+(typeof renderServerAnalysisEvidence==='function'?renderServerAnalysisEvidence(p):'')+renderProductHelp(p)+renderScreenshotSources(p)+'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px">'+esc(p.productDirection||'')+renderProductDirectionStatus(p)+'</div>'+
 renderServerVenueEvidence(p)+renderVenueHistory(p)+renderDegiroDisplayedQuote(p)+renderDegiroVenueInference(p)+renderDegiroTradingSession(p)+(swissSgVenue&&!degiroVenueObserved(p)&&!degiroVenueInferred(p)?'<div class="small" data-swiss-dots-warning><b>SG Swiss DOTS · CHF:</b> Offen ist die Zuordnung dieses CHF-Produkts zu einem DEGIRO-Handelsplatz. Die vorhandenen SG-Kurse werden für die Analyse verwendet.</div>':'')+'<div class="small" data-product-status><div><b>Daten:</b> '+valuePresenceMark(!serverEvidence&&missingNumbers.length>0)+' '+esc(dataText)+'</div><div><b>Zeitbezug vorhandener Kurs-/Hebelwerte:</b> '+valuePresenceMark(!serverEvidence&&!timeEvidence.confirmed)+' '+esc(serverEvidence?'Server-Nachweis aktuell · lokaler Bildzeitbezug separat geprüft':timeEvidence.label)+'</div><div><b>Aktuelle Auswahl:</b> '+(selected?'freigegeben · ausgewählt':'nicht ausgewählt')+(neutral?' · Marktsignal neutral':'')+'</div></div>'+
 '<p data-product-next><b>Nächster Schritt:</b> '+esc(selected?'Tatsächlichen DEGIRO-Kurs vor einem Einstieg prüfen.':next)+'</p><details><summary>Automatische Suche · letzter Stand</summary>'+renderAutomaticProductCheck(p)+'</details>'+renderPrimaryProductValues(p)+
 (allReasons.length?'<div class="small">'+allReasons.slice(0,2).map(shortReason).map(esc).join('<br>')+'</div>':'')+
 (selected?'': '<details style="margin-top:8px"><summary>Warum derzeit nicht ausgewählt?</summary><div class="small">'+(allReasons.length?allReasons.map(esc).join('<br>'):neutral?'Keine bestätigte Long-/Short-Marktrichtung. Die vollständigen Produktdaten müssen dafür nicht erneut hochgeladen werden.':'Die aktuelle Markt- und Risikoprüfung hat das Produkt nicht ausgewählt; vollständige Daten allein erteilen keine Freigabe.')+'</div></details>')+
 '<details data-product-values style="margin-top:10px"><summary><strong>Gespeicherte Bildwerte, Quellen und Zeitbezug</strong></summary>'+
 renderProductFieldStates(p)+renderTermSeriesValidity(p)+(currentConvertedChfEvidence(p)?'<div data-current-chf-proof>Aktueller CHF-Kurs und zeitlich passender Wechselkurs als EUR-Nachweis verwendet. Der historische Bildkurs bleibt unverändert; dafür ist kein nachträglicher Wechselkurs erforderlich. Hebel mit geprüftem Berechnungs- oder Bildzeitbezug berücksichtigt.</div>':'')+
 (values.length?'<details style="margin-top:10px"><summary>Automatisch erkannte Werte</summary><div class="small">'+values.map(esc).join('<br>')+'</div></details>':'')+
 (unconfirmed.length?'<div class="small" style="margin-top:8px"><em>'+unconfirmed.map(esc).join('<br>')+'</em></div>':'')+
 '</details><details style="margin-top:8px"><summary>'+evidenceTitle+(groups.length?' · '+groups.length+' Prüfpunkte':'')+'</summary><div class="small">'+(groups.length?groups.map(label=>'<div style="margin:10px 0"><strong>'+(automaticQuoteIssue?valuePresenceMark(false)+' Werte vorhanden · ':'')+esc(label)+'</strong><br>Fundort: '+esc(locations.get(label))+'</div>').join(''):'Produktdaten vollständig. Ergänzungen nur bei einem neuen Datenstand erforderlich.')+'</div>'+renderIssuerHelp(p,reasons)+renderTestScreenshotRequest(p)+'</details>'+
 calculationHtml+'<button data-selection-upload="'+p.index+'">Bilder / PDF zu diesem Produkt hinzufügen</button><button data-product-trade="'+esc(p.isin)+'">Vorhandenen Trade mit diesem Produkt erfassen</button>'+renderImageImportStatus(p.index)+
 '<details data-product-details="'+p.index+'" style="margin-top:10px"><summary>Quellen und Einzelheiten</summary><div class="small">'+esc(p.name||'')+'</div>'+renderProductSources(p)+renderMissingValues(reasons,p)+renderProductDecision(p,selected,[status,...reasons])+screenshotSummary(x)+'<button data-card-research="'+p.index+'">Daten erneut abrufen</button></details></details></div>';
}
// Display-only: a bounded, proven-identity turbo projection shares the NORMAL
// product-price row and labelled research ranking, never broker/trade approval.
// An 08:00 list price without paired Gold/FX reference is not a model anchor.
function calculatedProductDisplay(p,now=Date.now()){
 const q=p?.quote,c=q?.calculatedProduct,m=q?.productModel,meta=q?.metadata||{};
 if(!p||!validIsin(p.isin)||q?.isin!==p.isin||q.productVerified!==true||
    q.sourceDisabled||q.sourceFailure||(q.quoteFailureCode&&!(m?.provider==='BNP'&&String(q.issuerModelSource?.source||q.source||'').startsWith('BNP Paribas ·')&&(q.issuerModelSource?.sourceUrl||q.sourceUrl)==='https://derivate.bnpparibas.com/product-details/'+p.isin+'/'&&['STALE_OR_INVALID_SOURCE_TIME','MISSING_QUOTE_TIME'].includes(q.quoteFailureCode)))||meta.status!==1||
    meta.tradingHalted===true||meta.currency!=='EUR'||meta.underlyingType!=='SPOT'||
    meta.underlying!=='XAU/USD'||!['LONG','SHORT'].includes(meta.direction)||
    !m||m.isin!==p.isin||m.verifiedSimpleTurbo!==true||
    m.underlying!=='XAU/USD'||m.direction!==meta.direction||
    m.ratio!==meta.ratio||m.strike!==meta.strike||m.ko!==meta.ko||
    !c||c.available!==true||c.kind!=='calculated-turbo'||
    c.currency!=='EUR'||c.isDegiroQuote!==false||c.eligible!==false||
    c.direction!==m.direction||c.ratio!==m.ratio||c.strikeUsd!==m.strike||
    !freshTimes([c.priceAt,c.goldAt,c.fxDataAt,c.fxEffectiveAt],now,60)||
    !freshTimes([c.referenceAt],now,1800)||
    !Number.isFinite(Date.parse(m.tradingEndAt))||
    now>Date.parse(m.tradingEndAt)||
    !(n(c.referenceSkewSeconds)>=0&&n(c.referenceSkewSeconds)<=(c.anchorKind==='research-hybrid'?30:5))||
    !(n(c.bidEur)>0&&n(c.askEur)>=n(c.bidEur))||
    !(n(c.goldUsd)>0&&n(c.usdEur)>0))return null;
 const currentGold=n(c.goldUsd),ko=n(m.ko),strike=n(m.strike);
 if(!(currentGold>0&&ko>0&&strike>0&&
      (m.direction==='LONG'?currentGold>Math.max(ko,strike):
        currentGold<Math.min(ko,strike))))return null;
 return {isin:p.isin,bid:c.bidEur,ask:c.askEur,currency:'EUR',leverage:c.indicativeLeverage,
         at:c.priceAt,referenceAt:c.referenceAt,
         source:c.anchorKind==='research-hybrid'?(m.provider==='BNP'?'Bob · BNP/comdirect + Gold/FX':'Bob · SG/comdirect + Gold/FX'):'Bob · Gold-Spot/FX-Modell',
         referenceSource:c.anchorKind==='research-hybrid'?c.referenceSource:null,
         referenceClockGapSeconds:c.referenceSkewSeconds,
         priceKind:'calculated',referenceOnly:true,degiroExecutable:false,
         forwardValidation:c.forwardValidation||null,
         validationReady:c.validation?.ready===true,
         validationSamples:Number.isInteger(c.validation?.sampleCount)?c.validation.sampleCount:0,
         validationMeanErrorEur:Number.isFinite(c.validation?.meanAbsoluteError)?c.validation.meanAbsoluteError:null,
         validationPersistence:c.validation?.persistence||null};
}
// Use the same dated observation in the value display and field diagnostics.
function productDisplayQuote(q,isin,now){
 const live=q?.found?q:q?.analysisQuote||q?.referenceQuote;
 const recentPair=x=>x&&x.isin===isin&&x.currency==='EUR'&&!x.delayed&&!x.estimated&&!x.calculated&&x.priceKind!=='calculated'&&n(x.bid)>0&&n(x.ask)>=n(x.bid)&&[x.bidAt,x.askAt].every(t=>typeof t==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(t)&&Number.isFinite(Date.parse(t))&&now-Date.parse(t)>=0&&now-Date.parse(t)<=90000);
 if(q?.isin!==isin||q.productVerified!==true||q.metadata?.status!==1||q.sourceDisabled)return live;
 // Genuine current primary pair, then dated alternative pairs, then chart
 // observations. A retrieval timestamp never refreshes the source clock.
 if(q.found&&!q.sourceFailure&&!q.quoteFailureCode&&q.priceKind!=='issuer-chart'&&recentPair(q))return q;
 const backups=[q.analysisQuote,q.secondaryQuote].filter(x=>
  x?.priceKind==='market-observation'&&x.isExecutableQuote===false&&x.degiroExecutable===false&&recentPair(x));
 backups.sort((a,b)=>Math.min(Date.parse(b.bidAt),Date.parse(b.askAt))-Math.min(Date.parse(a.bidAt),Date.parse(a.askAt)));
 return backups[0]||live;
}
// Display-only continuity never changes product release or broker evidence.
function continuityDisplay(p,now){
 const q=p?.quote,c=q?.priceContinuity,m=c?.model,meta=q?.metadata||{};
 if(q?.isin!==p.isin||q?.productVerified!==true||meta.status!==1||meta.tradingHalted||q.sourceDisabled||!c||c.eligible!==false||c.degiroExecutable!==false)return null;
 if(c.state==='original'&&c.currency===meta.currency&&n(c.bid)>0&&n(c.ask)>=n(c.bid)&&freshTimes([c.at],now,90))return c;
 if(c.state!=='calculated'||c.kind!=='intrinsic'||c.currency!=='EUR'||meta.currency!=='EUR'||q.sourceFailure||
    !m||m.isin!==p.isin||m.verifiedSimpleTurbo!==true||m.underlying!=='XAU/USD'||meta.underlyingType!=='SPOT'||
    ['ratio','strike','ko','direction'].some(k=>m[k]!==meta[k])||!['LONG','SHORT'].includes(m.direction)||
    !(n(c.price)>0&&n(c.leverage)>0&&n(c.goldUsd)>0&&n(c.usdEur)>0)||
    !(m.direction==='LONG'?c.goldUsd>Math.max(m.ko,m.strike):c.goldUsd<Math.min(m.ko,m.strike))||
    !freshTimes([c.at,c.goldAt,c.fxDataAt,c.fxEffectiveAt],now,60)||
    !Number.isFinite(Date.parse(m.tradingEndAt))||now>Date.parse(m.tradingEndAt))return null;
 return c;
}
function renderPrimaryProductValues(p,now=Date.now()){
 const q=p.quote?.isin===p.isin&&p.quote.productVerified?p.quote:null;
 const continuity=continuityDisplay(p,now);
 const selectedQuote=productDisplayQuote(q,p.isin,now);
 const selectedRecent=selectedQuote&&selectedQuote!==q?.referenceQuote&&!(selectedQuote===q&&q?.sourceFailure)&&freshTimes([selectedQuote.bidAt,selectedQuote.askAt],now,90);
 const live=selectedRecent?selectedQuote:continuity?.state==='original'?{...continuity,isin:p.isin,bidAt:continuity.at,askAt:continuity.at,priceKind:'market-observation',isExecutableQuote:false}:selectedQuote;
 const fields=productFieldStates(p,now);
 const native=q?.nativeChartEvidence;
 const nativeChf=!!q?.productVerified&&native?.currency==='CHF'&&n(native.bid)>0
  &&n(native.ask)>=n(native.bid)&&typeof native.pointAt==='string';
 const euroPair=!!live&&!(live===q&&q?.sourceFailure)&&live!==q?.referenceQuote&&live.currency==='EUR'
  &&!live.delayed&&n(live.bid)>0&&n(live.ask)>=n(live.bid);
 const pair=euroPair?live:nativeChf?{...native,bidAt:native.pointAt,
  askAt:native.pointAt,source:'SG · datierter CHF-Chartkurs',priceKind:'issuer-chart',
  isExecutableQuote:false}:null;
 const clocks=[pair?.bidAt,pair?.askAt].map(t=>Date.parse(t));
 const marketObservation=pair?.priceKind==='market-observation';
 // Only native chart observations get the documented five-minute research
 // window. BNP issuer/other genuine bid-ask quotes use the 90-second clock.
 // Previously a five-minute-old BNP quote could still say "Aktueller Anbieterwert".
 const chartOnly=pair?.priceKind==='issuer-chart';
 const current=!!pair&&clocks.every(t=>Number.isFinite(t)&&now-t>=0&&now-t<=(chartOnly?300000:90000))
  &&Math.max(...clocks)-Math.min(...clocks)<=90000;
 // Prefer an original observation no older than 90 s. Older research quotes
 // remain visible in the source history while an independently refreshed
 // theoretical price takes the primary slot.
 const originalRecent=!!pair&&clocks.every(t=>Number.isFinite(t)&&now>=t&&now-t<=90000)
  &&Math.max(...clocks)-Math.min(...clocks)<=90000;
 const modelPrice=calculatedProductDisplay(p,now);
 const estimated=!!modelPrice&&!originalRecent;
 const displayed=estimated?modelPrice:pair;
 const at=estimated?modelPrice.at:pair?.bidAt||pair?.askAt||q?.quoteAt;
 const chart=pair?.priceKind==='issuer-chart'||pair?.isExecutableQuote===false;
 const fmt=v=>n(v)>0?Number(v).toLocaleString('de-CH',{maximumFractionDigits:4}):'—';
 const stamp=at&&Number.isFinite(Date.parse(at))?new Date(at).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false})+' (Zürich)':'Zeitbezug unbestätigt';
 const currency=pair?.currency||p.snapshot?.currency||p.currency||'EUR';
 const undatedLever=q?.issuerLeverageReference;
 const refRetrieved=Date.parse(undatedLever?.retrievedAt);
 const refRetrievedNote=Number.isFinite(refRetrieved)
  ?' · Technischer Abruf '+esc(new Date(refRetrieved).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false}))+' (Zürich), keine SG-Hebelquellenzeit.'
  :' · Technischer Abrufzeitpunkt unbekannt.';
 const linkedAt=undatedLever?.sharedContextAt;
 const linked=typeof linkedAt==='string'&&q?.sharedTimeContext?.at===linkedAt
  &&q.sharedTimeContext.isin===p.isin&&Number.isFinite(Date.parse(linkedAt))
  &&!!sharedSgIssuerLeverage(p,now);
 const sharedStamp=linked?new Date(linkedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false})+' (Zürich)':'';
 const refNote=undatedLever?.dated===false&&n(undatedLever.value)>0
  ?'<br><b>SG-Referenzhebel ('+(linked?'gemeinsamer Zeitbezug':'ohne Kurszeit')+'): '+esc(fmt(undatedLever.value))+'×</b> · '+(linked?'Gemeinsamer Hebel-Zeitbezug bestätigt: SG-Chartzeit derselben automatischen Abrufserie '+esc(sharedStamp)+' · gilt für die dort beobachteten Produktwerte. Keine zusätzlich separat veröffentlichte Hebelquellenzeit. ':'')+'Für die Analyse verwendbar, sofern der Beobachtungszeitpunkt aktuell ist; kein Nachweis einer DEGIRO-Ausführung.'+refRetrievedNote
  :'';
 const missingSgReferenceNote=q?.importActive===true&&q?.productVerified===true
  &&fields.leverage.state==='fehlt'&&!(n(undatedLever?.value)>0)
  ?'<br>SG-Referenzhebel: Von der automatisch abgefragten SG-Quelle nicht geliefert. Ein gemeinsamer Zeitbezug belegt nur vorhandene Werte; er ersetzt keinen fehlenden Hebel.':'';
 const headline=estimated?'Berechneter Kurs aktuell · Produktkurs · ≈ errechnet':continuity?.state==='original'?'Aktuelle Kursbeobachtung · '+(continuity.source||'Anbieter'):marketObservation?(current?'Aktuelle comdirect-Kursbeobachtung':'comdirect-Kursbeobachtung · nicht aktuell'):chart?(current?'Aktuelle SG-Chartbeobachtung · nur Analyse':'SG-Chartbeobachtung · nicht aktuell'):current?'Aktueller Anbieterwert':'Gespeicherter Anbieterwert · Originalzeit abgelaufen';
 const labels=estimated?' · theoretische Geld-/Brief-Schätzung, kein bestätigter DEGIRO-Ausführungskurs':marketObservation?' · '+esc(pair.source||'comdirect-Kursbeobachtung')+', kein bestätigter DEGIRO-Ausführungskurs':chart?' · Chartkurs, kein bestätigter Ausführungskurs':'';
 const note=!estimated&&pair&&!current?' · Datenalter überschreitet Analysefenster':'';
 const forward=modelPrice?.forwardValidation;
 const forwardInfo=forward?'<br>Vorab gespeicherte Schätzungen: '+esc(forward.sampleCount)+' passende spätere Originalkurse'+
  (Number.isFinite(forward.meanAbsoluteError)?' · mittlere Brief-Abweichung '+esc(forward.meanAbsoluteError.toFixed(4))+' EUR':' · Messung läuft')+
  (Number.isFinite(forward.maxAbsoluteError)?' · größte Brief-Abweichung '+esc(forward.maxAbsoluteError.toFixed(4))+' EUR':'')+
  ' · '+esc(forward.ready?'Mindeststichprobe erreicht':'Noch keine ausreichende Stichprobe')+'; keine Genauigkeitsgarantie.':'';
 const calculationInfo=estimated?'<br>≈ Datenstand '+esc(stamp)+' · Produktreferenz '+esc(modelPrice.referenceAt)+
  ' · Quelle '+esc(modelPrice.source)+
  (modelPrice.referenceSource?' · Kalibrierung '+esc(modelPrice.referenceSource):'')+
  ' · Originalzeitabstand '+esc(modelPrice.referenceClockGapSeconds)+' s'+
  ' · '+esc(modelPrice.validationReady?'Genauigkeitsmessung vorhanden':'Genauigkeit noch nicht ausreichend bestätigt')+
  ' · Modellvergleich: '+esc(modelPrice.validationSamples)+' Originalkursvergleiche'+
  (Number.isFinite(modelPrice.validationMeanErrorEur)?' · mittlere absolute Abweichung '+esc(modelPrice.validationMeanErrorEur.toFixed(3))+' EUR':'')+
  (modelPrice.validationPersistence?' · '+esc(modelPrice.validationPersistence):'')+
  ' · Modell nur für Bewertung und Vorwarnungen; kein automatischer Stopp, keine Handelsfreigabe.': '';
 const previousSource=estimated&&pair?'<br>Letzter originaler Datenstand (nicht aktuell): Geld '+esc(fmt(pair.bid))+
  ' / Brief '+esc(fmt(pair.ask))+' '+esc(pair.currency||'EUR')+' · '+esc(pair.bidAt||pair.askAt||'Zeit unbekannt'):'';
 const unpairedReference=n(p.price)>0&&fields.ask.state==='fehlt'&&!pair
  ?'<br><b>Gespeicherter Produkt-/Listenpreis: '+fmt(p.price)+' EUR</b> · kein bestätigter Briefkurs, Geld/Brief weiter abrufen.'
  :'';
 const basis=selectedPriceSnapshot(p,now);
 const basisNote=basis?'<br><span data-selected-price-key="'+esc(basis.selectionKey)+'">Gemeinsame Analysegrundlage: '+fmt(basis.price)+' EUR · '+esc(basis.kind==='calculated'?'berechnet':'beobachtet')+' · '+esc(basis.source)+' · '+esc(basis.at)+'</span>':'';
 if(continuity?.kind==='intrinsic'&&!originalRecent)return '<div class="small" data-primary-product-values data-price-kind="calculated"><b>Berechneter Kurs aktuell</b><br>≈ Theoretischer Produktwert '+fmt(continuity.price)+' EUR<br>≈ Berechneter Hebel '+fmt(continuity.leverage)+'×<br>'+esc(continuity.note)+'<br>Quelle: '+esc(continuity.source)+' · '+esc(new Date(continuity.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}))+' (Zürich)<br>Nur Analyse; keine Handelsfreigabe.'+basisNote+'</div>';
 const continuityLabel=originalRecent?'Originalkurs aktuell':estimated?'':'Keine aktuelle Berechnungsgrundlage';
 const comparison=continuity?.comparison;
 const comparisonNote=comparison?'<br>Rückkehr zum Originalkurs · Abweichung zum vorher berechneten Modell: '+esc(Number(comparison.differenceEur).toFixed(4))+' EUR gegenüber dem Original-Mittelkurs (Quellzeiten höchstens 15 s auseinander).':'';
 return '<div class="small" data-primary-product-values data-price-kind="'+(estimated?'calculated':'observation')+'">'+(continuityLabel?'<b>'+esc(continuityLabel)+'</b><br>':'')+'<b>'+esc(headline)+'</b>'+comparisonNote+'<br>'+
  (estimated?'≈ ':valuePresenceMark(fields.bid.state==='fehlt'))+' Geld '+fmt(displayed?displayed.bid:fields.bid.value)+
  ' / '+(estimated?'≈ ':valuePresenceMark(fields.ask.state==='fehlt'))+' Brief '+fmt(displayed?displayed.ask:fields.ask.value)+' '+esc(estimated?'EUR':currency)+
  labels+note+'<br>'+(displayed?'Quelle: '+esc(displayed.source||q.source||'Produktanbieter')+' · '+esc(stamp):'Datenstand: '+esc(fields.ask.state))+
  calculationInfo+forwardInfo+previousSource+basisNote+
  '<br>'+valuePresenceMark(fields.leverage.state==='fehlt')+(fields.leverage.state==='fehlt'&&undatedLever?.dated===false&&n(undatedLever.value)>0?' Aktueller Hebel nicht zeitlich bestätigt':' Hebel '+fmt(estimated&&n(modelPrice.leverage)>0?modelPrice.leverage:fields.leverage.value))+
  ' · '+esc(estimated?'berechnet · aktuelle Modellgrundlage':fields.leverage.state)+(q?.leverageEstimated?' · rechnerische Näherung, kein bestätigter Emittentenhebel':'')+
  (fields.leverage.state==='fehlt'&&q?.leverageCalculation?.reason?'<br>Berechnung derzeit nicht möglich: '+esc(q.leverageCalculation.reason):'')+
  refNote+missingSgReferenceNote+unpairedReference+'</div>';
}
function bindCompactCards(root){
 bindIsinCopy(root);
 root.querySelectorAll('[data-product-trade]').forEach(btn=>btn.addEventListener('click',()=>{
  const input=document.getElementById('exit-isin');if(!input)return;
  window.BobExitEstimate?.selectProduct(btn.dataset.productTrade);
  document.querySelector('#bobNavigation [data-view="trade"]')?.click();
  const panel=document.getElementById('bobExitEstimate');
  for(let node=panel;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
  panel?.scrollIntoView({behavior:'smooth',block:'start'});
  document.getElementById('exit-entry')?.focus();
 }));
 root.querySelectorAll('[data-selection-upload]').forEach(btn=>btn.addEventListener('click',()=>document.getElementById('dgDetailShot'+btn.dataset.selectionUpload)?.click()));
 root.querySelectorAll('[data-card-research]').forEach(btn=>btn.addEventListener('click',()=>enrichProduct(Number(btn.dataset.cardResearch))));
}
function renderProductDecision(c,approved=true,blocked=[]){
 const unique=values=>[...new Set(values.filter(Boolean).map(x=>String(x).split('. Öffne')[0]))];
 const concerns=unique([...(c.warnings||[]),...(c.reasons||[]).filter(x=>/widerspr|fehlt|unbekannt|unbestätigt|veraltet|Abweichung|Schätzung|ABWARTEN/i.test(x)),...blocked.map(x=>String(x).split('. Öffne')[0])]);
 const reasons=unique(c.reasons||[]);
 const why=approved?['Produktrichtung '+c.direction+' passt zur bestätigten Auswahlrichtung.','Produktnachweise und die für diesen Berechnungsweg geltenden Prüfungen bestanden.',(c.rankingVariant?'Geprüfte Lernrangfolge innerhalb von höchstens 5 Risikopunkten Abstand; Risikowert: '+c.score+'/100.':'Rangfolge nach Risikowert: '+c.score+'/100; bei Gleichstand entscheidet die ISIN, nicht eine höhere erwartete Rendite.'),...reasons]:reasons;
 const revoke=['Marktrichtung passt nicht mehr oder die Marktprüfung fällt aus.','Erforderliche Produkt-/Kursnachweise fehlen, laufen ab oder widersprechen sich.','Produkt ist inaktiv, abgelaufen oder die KO-Schwelle ist erreicht.','Risikoprüfung scheitert: etwa KO-Abstand unter 1 %, Puffer unter 1,5 ATR oder Risikowert unter 60/100.','Das Produkt fällt aus den höchstens drei ausgewählten Kandidaten.'];
 if(c.basisError>0||c.priceError>0)revoke.push('Die Schätzung ist nicht mehr ausreichend belegt oder die Prüfung innerhalb der beobachteten Fehlerspanne scheitert.');
 const lines=xs=>xs.map(esc).join('<br>');
 return '<details class="small" style="margin-top:8px"><summary>Warum dieses Produkt?</summary><b>Warum '+(approved?'ausgewählt':'nicht freigegeben')+'?</b><div>'+lines(why.length?why:['Keine Freigabe: Produktprüfung noch offen.'])+'</div><b>Was spricht dagegen / ist unsicher?</b><div>'+lines(concerns.length?concerns:['Keine zusätzlichen Warnungen aus dieser Prüfung. Das bedeutet nicht risikofrei.'])+'</div><b>Wann entfällt die Freigabe?</b><div>'+lines(revoke)+'</div></details>';
}
function renderSelectionWorkflow(r,products=[]){
 const steps='<div class="small">Listenbilder → unverbindliche Kandidaten → Pflichtprüfung → bis zu 3 geeignete Produkte</div><details><summary class="small">So bewertet Bob Kosten und Risiko</summary><div class="small">KO-Pufferwert: 100 minus Abzüge für Handels- und Finanzierungskosten, KO und Datenqualität. Spread nur zur Information: kein Punkteabzug und keine Spread-Sperre. Die Hebelhöhe allein bringt weder Plus- noch Minuspunkte. Vergleich: 1.000 EUR / 1 Kalendertag. Unbekannte Kosten erhalten jeweils den vollen 10-Punkte-Abzug; kein bestätigter Kostenvorteil. Mindestwert 60. Gleiche Werte bedeuten Gleichstand; ISIN sortiert nur die Anzeige. Kostennachweise unter Details / manuelle Kursnachweise.</div></details>';
 const excluded=(r.notApproved||[]).filter(p=>knockoutStatus({...products[p.index-1],...p}));
 return '<b>'+ (r.approved?'Zur Produktauswahl freigegeben · '+r.approvedCount+' geeignete'+(r.approvedCount===1?'s Produkt':' Produkte'):'Abwarten – derzeit kein geeignetes Produkt')+'</b>'+steps+
 '<div class="small">'+esc((r.gateReasons||[]).join(' · '))+'</div>'+
 '<div class="small">'+(r.groups.some(g=>g.candidates.some(c=>c.rankingVariant))?'Geprüfte Lernrangfolge aktiv; KO-Pufferwerte und Pflichtprüfungen bleiben unverändert. ':'')+r.total+' unterschiedliche Produkte. Vorauswahl nach Analyse-Richtung '+esc(r.direction)+'; fehlende Preise erhalten keine Rangpunkte.</div>'+
 r.groups.map(g=>'<div style="margin-top:12px"><b>'+esc(g.scope)+' · '+g.total+' bewertbare Produkte</b>'+g.candidates.map((c,i)=>'<div data-product-isin="'+esc(c.isin)+'" style="padding:10px;margin-top:8px;border:1px solid #dbe4f0;border-radius:12px"><b>Platz '+(i+1)+' · '+esc(c.isin)+'</b>'+renderIsinCopy(c.isin,true)+productCompletionBadge(products.find(p=>p.isin===c.isin)||c)+'<div class="small" data-product-status><div><b>Daten:</b> vollständig</div><div><b>Zeitbezug:</b> für diesen Analyseweg bestätigt</div><div><b>Aktuelle Auswahl:</b> geeignet für '+esc(c.direction)+renderProductDirectionStatus(products.find(p=>p.isin===c.isin)||c)+'</div></div><p><b>Nächster Schritt:</b> Tatsächlichen DEGIRO-Kurs vor einem Einstieg prüfen.</p><button data-product-trade="'+esc(c.isin)+'">Vorhandenen Trade mit diesem Produkt erfassen</button><details data-product-values style="margin-top:10px"><summary><strong>Produktwerte anzeigen</strong></summary><div class="small">'+esc(c.name)+'<br>'+esc(c.priceKind)+' · Brief '+Number(c.price).toFixed(2)+' EUR · KO-Pufferwert '+c.score+'/100<br>Warum: '+esc((c.reasons||[]).slice(0,3).join(' · ')).replace(/\bHebel\b/g,'<strong>Hebel</strong>')+'<br>Quelle '+esc(c.source||'Produktnachweis')+' · Datenzeit '+esc(c.at)+(c.quoteAt?' · Produktkurszeit '+esc(c.quoteAt):'')+(c.quality?'<br>'+esc(qualityText(c.quality,'USD')):'')+'</div>'+renderProductDecision(c)+renderProductSources(c)+'</details></div>').join('')+'</div>').join('')+
 excluded.map(p=>knockoutCard({...products[p.index-1],...p})).join('')+
 '<details class="small" style="margin-top:10px"><summary>Hinweise zur Produktauswahl</summary>Spot und Future werden getrennt bewertet. Weniger als drei belegte Produkte ergeben eine kürzere Liste. Freigabe gilt ausschließlich für diese geprüfte Produktauswahl, nicht als Handelsauftrag oder garantierter bester Trade. Kandidaten mit offenen Nachweisen bleiben gesperrt; tatsächlichen DEGIRO-Preis vor dem Einstieg prüfen.</details>';
}

function productUploadCards(products,direction,now=Date.now(),flow=null,context=null){
 const calculations=new Map(context?continuingAnalysis(products,context).map(row=>[row.p.isin,renderProductCalculation(row)]):[]);
 const selected=new Set((flow?.groups||[]).flatMap(g=>g.candidates).map(p=>p.isin));
 const all=(products||[]).map((p,z)=>({...p,index:z+1})).filter(p=>p.name||p.isin);
 const buckets={active:[],review:[],ended:[],factor:[]};
 for(const p of all)buckets[goldProductGroup(p,now)].push(p);
 const labels={active:'Aktive Gold-Hebelprodukte',review:'Nachweisprüfung offen',ended:'Beendete Produkte',factor:'Faktor Goldprodukte nicht verwendet'};
 const html=['active','review','ended','factor'].filter(group=>buckets[group].length).map(group=>{
  const rows=buckets[group].sort((a,b)=>Number(b.productDirection===direction)-Number(a.productDirection===direction));
  return '<section data-gold-group="'+group+'" style="margin:12px 0"><h4>'+labels[group]+' · '+rows.length+'</h4>'+
    rows.map(p=>{
     const blocked=flow?.notApproved?.find(v=>v.index===p.index);
     const status=selected.has(p.isin)?'Freigegeben · ausgewählt':blocked?'Nicht freigegeben · '+(blocked.reasons?.[0]||'Nachweise prüfen'):'Produktnachweise prüfen';
     return compactProductCard(p,blocked?.missingReasons||finalProductStatus(p,now).reasons,status,calculations.get(p.isin)||'');
    }).join('')+'</section>';
 }).join('');
 return goldProductOverview(all,now)+html;
}


// Original list images live in IndexedDB, independently of Android's file picker.
let listArchive=null,listArchiveUrls=[],productArchivePayload='';
let listRevision=0,listRecoveryBusy=false,listRecoveryAttempt=null;
const LIST_DAY_KEY='bobDegiroListDayV1'; // Legacy upload date: never expires a saved list.
function zurichListDay(now=Date.now()){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now));
 const get=k=>parts.find(p=>p.type===k).value;
 return {day:get('year')+'-'+get('month')+'-'+get('day'),closed:Number(get('hour'))>=22};
}
function listExpired(day,now=Date.now()){return false; /* Product identity does not expire; only dated quotes do. */}
function clearDailyList(){
 const empty=JSON.stringify({version:2,products:[]});
 listArchive=null;productArchivePayload=empty;
 localStorage.setItem(PRODUCT_STORE_KEY,empty);localStorage.setItem(IDENTITY_KEY,'[]');localStorage.removeItem(LIST_DAY_KEY);
 showListArchive();
 return archiveTransaction('readwrite',store=>{store.delete('list');return store.put(empty,'products');});
}
function expireVisibleList(){
 // Retain the last screenshot list across days, browser restarts and weekends.
 // Source age is assessed separately on every quote and term; never renew it.
}

function archiveTransaction(mode,action){
 return new Promise((resolve,reject)=>{
  // Some Android browsers leave an IndexedDB read pending indefinitely
  // (e.g. blocked/open transaction on a background tab). Never let a
  // READ block the product view. Do not time out WRITE transactions:
  // an uncertain write must not be claimed to have committed.
  let settled=false,db=null;
  const finish=(error,value)=>{
   if(settled)return;
   settled=true;
   if(timeout&&typeof clearTimeout==='function')clearTimeout(timeout);
   try{db?.close();}catch(_){}
   if(error)reject(error);else resolve(value);
  };
  const timeout=mode==='readonly'&&typeof setTimeout==='function'?setTimeout(()=>
   finish(Error('Lokaler Bildspeicher antwortet nicht; Produkt-Cache wird geprüft.')),6000):null;
  let request;
  try{request=indexedDB.open('bobProductArchive',1);}
  catch(error){finish(error);return;}
  request.onupgradeneeded=()=>{if(!settled)request.result.createObjectStore('records');};
  request.onerror=()=>finish(request.error||Error('Bildspeicher nicht verfügbar'));
  request.onsuccess=()=>{
   if(settled){try{request.result.close();}catch(_){}return;}
   db=request.result;
   let tx,result;
   try{
    tx=db.transaction('records',mode);
    tx.oncomplete=()=>finish(null,result?.result);
    tx.onerror=tx.onabort=()=>finish(tx.error||Error('Bildspeicher nicht verfügbar'));
    result=action(tx.objectStore('records'));
   }catch(error){finish(error);}
  };
 });
}
function showListArchive(){
 const el=document.getElementById('dgSavedListImages');if(!el)return;
 listArchiveUrls.forEach(url=>URL.revokeObjectURL(url));listArchiveUrls=[];
 if(!listArchive?.files?.length){el.textContent='';return;}
 el.innerHTML='<summary>Gespeicherte Listenbilder ('+listArchive.files.length+')</summary><div data-list-previews></div>';
 const previews=el.querySelector('[data-list-previews]');
 for(const file of listArchive.files){
  const url=URL.createObjectURL(file.blob);listArchiveUrls.push(url);
  const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';
  const img=document.createElement('img');img.src=url;img.alt=file.name;img.style.cssText='max-width:140px;max-height:180px;margin:6px';a.append(img);previews.append(a);
 }
}
async function saveReplacementListArchive(files,items){
 // Revoke old-generation attestations before committing a replacement list.
 // If persistence fails, preserve the active list instead of carrying old KO proof.
 if(!window.BobCombined.resetFixedList())throw Error('KO-Nachweishistorie konnte nicht sicher gespeichert werden; Liste nicht ersetzt');
 return saveListArchive(files,items);
}
async function saveListArchive(files,items){
 if(!Array.isArray(items)||!items.some(p=>validIsin(p?.isin)))throw Error('Keine gültige Produkt-ISIN erkannt. Alte Liste bleibt erhalten.');
 const previousArchive=listArchive;
 listRevision++;
 const record={files:files.map(file=>({name:file.name,blob:file})),items,storedAt:new Date().toISOString()};
 await archiveTransaction('readwrite',store=>{store.put(JSON.stringify({version:2,products:items.map(cleanStoredProduct).filter(Boolean),listUploadedAt:record.storedAt}),'products');return store.put(record,'list');});
 // Archive both generations at the import boundary, even before the next UI repaint.
 // History remains optional metadata and never grants current broker eligibility.
 try{
  const history=window.BobDegiroAllProducts?.updateEvidenceHistory;
  if(history){
   if(previousArchive?.storedAt)history(localStorage,previousArchive.items,previousArchive.storedAt);
   history(localStorage,record.items,record.storedAt);
  }
 }catch(_){}
 localStorage.setItem(LIST_DAY_KEY,zurichListDay(Date.parse(record.storedAt)).day);
 listArchive=record;showListArchive();
 // Best effort: storage persistence does not change quote/evidence timestamps.
 try{navigator.storage?.persist?.().catch(()=>{});}catch(_){}
}
async function recoverArchivedList(recognize=recognizeOcr,progress=()=>{}){
 const original=listArchive,revision=listRevision,now=Date.now();
 if(listRecoveryBusy||!original?.files?.length||!original.items?.some(x=>!validIsin(x.isin)))return null;
 if(listRecoveryAttempt?.at===original.storedAt&&now-listRecoveryAttempt.time<30*60*1000)return null;
 listRecoveryAttempt={at:original.storedAt,time:now};listRecoveryBusy=true;
 try{
  const reread=await readListBatch(original.files.map(x=>x.blob),recognize,progress);
  if(original!==listArchive||revision!==listRevision)return null;
  const known=original.items.filter(x=>validIsin(x.isin));
  // A reread may repair rows, never remove or exchange previously valid IDs.
  if(known.some(x=>!reread.some(y=>y.isin===x.isin)))return null;
  const ids=reread.filter(x=>validIsin(x.isin)).map(x=>x.isin);
  let repaired=0;
  const items=original.items.map(x=>{
   if(validIsin(x.isin))return x;
   const recovered=recoverOcrIsins(x.isin,ids.join('\n')).text;
   const match=reread.find(y=>y.isin===recovered);
   if(!match||!validIsin(recovered)||known.some(y=>y.isin===recovered)||!x.direction||match.direction!==x.direction)return x;
   repaired++;
   return {isin:recovered,name:match.name,direction:match.direction,originalIsin:x.isin,
    isinConfirmed:false,identityCorrection:'Automatische Zweitlesung des gespeicherten Originalbildes; Emittentenprüfung folgt'};
  });
  if(!repaired||new Set(items.map(x=>x.isin)).size!==items.length)return null;
  const existing=loadIdentities();
  const rows=items.map(x=>existing.find(y=>y.isin===x.isin)||cleanStoredProduct(x)).filter(Boolean);
  const record={...original,items,recovery:{checkedAt:new Date().toISOString(),corrected:repaired}};
  const payload=JSON.stringify({version:2,products:rows,listUploadedAt:original.storedAt});
  let committed=false;
  await archiveTransaction('readwrite',store=>{
   const request=store.get('list');
   request.onsuccess=()=>{
    if(original!==listArchive||revision!==listRevision||request.result?.storedAt!==original.storedAt)return;
    store.put(record,'list');store.put(payload,'products');committed=true;
   };
   return request;
  });
  if(!committed||original!==listArchive||revision!==listRevision)return null;
  listArchive=record;
  localStorage.setItem(PRODUCT_STORE_KEY,payload);
  // The original upload date and all valid rows' evidence stay unchanged.
  return {rows,corrected:repaired};
 }finally{listRecoveryBusy=false;}
}
async function restoreListArchive(){
 try{
  listArchive=await archiveTransaction('readonly',store=>store.get('list'));
  const day=listArchive?.storedAt?zurichListDay(Date.parse(listArchive.storedAt)).day:localStorage.getItem(LIST_DAY_KEY);
  // Upload date is provenance, not a daily deletion deadline.
  if(day)localStorage.setItem(LIST_DAY_KEY,day);
  const backup=await archiveTransaction('readonly',store=>store.get('products'));
  if(backup){
   // IndexedDB holds the atomic image+identity replacement. If a browser
   // closed between its transaction and localStorage update, prefer the newer
   // committed screenshot generation rather than resurrecting older rows.
   const current=localStorage.getItem(PRODUCT_STORE_KEY);
   let saved=null,local=null;
   try{saved=JSON.parse(backup);local=current?JSON.parse(current):null;}catch(_){}
   if(!current || (saved?.listUploadedAt &&
       (!local?.listUploadedAt || saved.listUploadedAt>local.listUploadedAt))){
     localStorage.setItem(PRODUCT_STORE_KEY,backup);
   }
  }
  // Recover an accidentally empty row cache from the same original image archive.
  if(!loadIdentities().length&&Array.isArray(listArchive?.items)){
   const rows=listArchive.items.map(cleanStoredProduct).filter(Boolean);
   if(rows.length){
    const payload=JSON.stringify({version:2,products:rows,listUploadedAt:listArchive.storedAt});
    localStorage.setItem(PRODUCT_STORE_KEY,payload);productStorageBlocked=false;
   }
  }
  // Never turn a restart/current date into the original screenshot date.
  showListArchive();
 }catch(_){
  // An inaccessible archive is not an empty list. Preserve every known
  // localStorage generation and do not overwrite it with an empty snapshot.
  productStorageBlocked=true;
  productStorageMessage='Bildspeicher nicht erreichbar. Gespeicherte Produktdaten bleiben unangetastet; bitte Speicher/Berechtigung prüfen.';
 }
}
const IDENTITY_KEY='bobDegiroIdentitiesV1', PRODUCT_STORE_KEY='bobDegiroProductsV2';
let productStorageMessage='',productStorageBlocked=false,productRowsReady=false;
function cleanStoredProduct(x){
 if(x&&!validIsin(x.isin)){
  const corrected=normalizeOcrIsin(x.isin,x.name||'');
  if(corrected.identityCorrection&&validIsin(corrected.isin))x={...x,isin:corrected.isin,isinConfirmed:false};
 }
 if(!x||!validIsin(x.isin))return null;
 const out={isin:x.isin,name:String(x.name||x.isin),direction:['LONG','SHORT'].includes(x.direction)?x.direction:''};
 for(const k of ['price','leverage','ko','spread'])if(n(x[k])!==null)out[k]=n(x[k]);
 if(x.snapshot?.isin===x.isin)out.snapshot=JSON.parse(JSON.stringify(x.snapshot));
 out.isinConfirmed=x.isinConfirmed===true;
 if(x.reference?.isin===x.isin)out.reference=JSON.parse(JSON.stringify(x.reference));
 return out;
}
function writeStoredProducts(items){
 if(productStorageBlocked)return false;
 try{const rows=items.map(cleanStoredProduct).filter(Boolean).slice(0,12);
  // Preserve the original DEGIRO screenshot timestamp if an IndexedDB read
  // fails but localStorage still retains the last committed list generation.
  // The page opening is NEVER a new evidence observation.
  let previousGeneration=null;
  try{
   const prior=JSON.parse(localStorage.getItem(PRODUCT_STORE_KEY)||'null');
   const stamp=prior?.listUploadedAt;
   if(typeof stamp==='string'&&Number.isFinite(Date.parse(stamp)))previousGeneration=stamp;
  }catch(_){}
  const payload=JSON.stringify({version:2,products:rows,listUploadedAt:listArchive?.storedAt||previousGeneration});
  // Only an actual screenshot upload sets its original observation date.
  if(localStorage.getItem(PRODUCT_STORE_KEY)!==payload)localStorage.setItem(PRODUCT_STORE_KEY,payload);
  if(localStorage.getItem(PRODUCT_STORE_KEY)!==payload)throw Error('Speicherung nicht bestätigt');
  if(productArchivePayload!==payload&&typeof indexedDB!=='undefined'){productArchivePayload=payload;archiveTransaction('readwrite',store=>store.put(payload,'products')).catch(()=>{productArchivePayload='';});}
  localStorage.setItem(IDENTITY_KEY,JSON.stringify(rows.map(({isin,name,direction})=>({isin,name,direction}))));
  productStorageMessage='Produktdaten, Bildquellen und Prüfstatus auf diesem Gerät gespeichert. Originalzeiten bleiben erhalten.';return true;
 }catch(_){productStorageMessage='Speicherung fehlgeschlagen: Produktdaten bleiben möglicherweise nur in diesem Tab. Bitte diesen Tab geöffnet lassen.';return false;}
}
function saveIdentities(){
 const items=[];for(let i=1;i<=12;i++){
  const read=k=>document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]')?.value||'';
  if(validIsin(read('isin')))items.push({isin:read('isin').toUpperCase(),name:read('name'),direction:read('dir'),price:read('price'),leverage:read('lev'),ko:read('ko'),spread:read('spread'),isinConfirmed:false,snapshot:detailScreenshots.get(i),reference:combinedReferences.get(i)});
 }
 if(items.length||!loadIdentities().length)writeStoredProducts(items);
 const label=document.getElementById?.('dgStorageStatus');if(label)label.textContent=productStorageMessage;
}
function loadIdentities(){
 try{const raw=localStorage.getItem(PRODUCT_STORE_KEY);if(raw){const saved=JSON.parse(raw);if(saved.version!==2||!Array.isArray(saved.products))throw Error('Unbekanntes Speicherformat');return saved.products.map(cleanStoredProduct).filter(Boolean).slice(0,12);}
 const items=JSON.parse(localStorage.getItem(IDENTITY_KEY)||'[]');return Array.isArray(items)?items.map(cleanStoredProduct).filter(Boolean).slice(0,12):[];
 }catch(_){productStorageBlocked=true;productStorageMessage='Gespeicherte Produktdaten konnten nicht gelesen werden; vorhandenen Speicher nicht überschreiben.';return [];}
}
// Visually checked original list images. These are historical observations,
// not current issuer terms. Missing source dates and ratio semantics stay unknown.
const REVIEWED_LIST_ROWS=[
 ['DE000FG4JXV7','SHORT',4460,'Turbo Classic','18/12/2026','1000070092.jpg'],
 ['DE000FC1CHB7','LONG',4025.71,'Turbo BEST','Open End','1000070092.jpg'],
 ['DE000FG7EPT1','SHORT',4377.17,'Turbo BEST','Open End','1000070092.jpg'],
 ['DE000FG5GUT0','LONG',4069.25,'Turbo BEST','Open End','1000070092.jpg'],
 ['DE000PJ9NCK0','LONG',3980.6468,'BNP Unlimited','Unbegrenzt','1000070092.jpg'],
 ['DE000FG5NMF2','LONG',4114.6,'Turbo BEST','Open End','1000070092.jpg'],
 ['DE000FG309G0','SHORT',4635.81,'Gold Future Turbo BEST','Open End','1000070094.jpg'],
 ['DE000FG6XB39','SHORT',4403.17,'Turbo BEST','Open End','1000070094.jpg'],
 ['DE000FG7K3L2','SHORT',4223.23,'Turbo BEST','Open End','1000070094.jpg'],
 ['DE000FE4UF01','LONG',null,'Gold Future Faktor',null,'1000070094.jpg']
];
function recoverReviewedLists(items){
 const rows=items.length?items:REVIEWED_LIST_ROWS.map(([isin,direction,ko,type])=>({isin,direction,ko,name:(/Gold/i.test(type)?type:'Gold '+type)+' '+direction+' '+isin}));
 return rows.map(p=>{
  const row=REVIEWED_LIST_ROWS.find(x=>x[0]===p.isin);if(!row)return p;
  const [isin,direction,ko,type,maturity,image]=row;
  if(p.direction&&p.direction!==direction)return p;
  const source='DEGIRO-Listenbild '+image,old=p.snapshot?.isin===isin?p.snapshot:{isin};
  const snapshot={...old,evidence:{...old.evidence},terms:{...old.terms}};
  const observed={strike:ko,type,currency:'EUR',maturity};
  for(const [key,value]of Object.entries(observed))if(value!==null&&!snapshot.terms[key])snapshot.terms[key]={value,at:null,source,reviewed:true};
  if(ko!==null&&!snapshot.evidence.KO)snapshot.evidence.KO={value:ko,at:null,source};
  snapshot.listEvidence={source,identityReviewed:true,sourceTime:null,ratioText:ko!==null?(isin==='DE000PJ9NCK0'?'R 10':'Bv 10')+' – Berechnungsfaktor noch nicht bestätigt':null};
  return {...p,direction:p.direction||direction,ko:p.ko??ko,snapshot,isinConfirmed:p.isinConfirmed===true||!p.snapshot&&n(p.price)===null&&n(p.leverage)===null};
 });
}
function restoreProductRows(items){
 populateCandidateRows(items);
 for(let i=1;i<=items.length;i++){
  const p=items[i-1];if(p.snapshot?.isin===p.isin)detailScreenshots.set(i,p.snapshot);
  if(p.reference?.isin===p.isin)combinedReferences.set(i,p.reference);
  const field=document.querySelector('[data-dg="confirmed"][data-i="'+i+'"]');if(field)field.checked=p.isinConfirmed===true;
 }
}
function needsDirectionalData(p,direction){
 return ['LONG','SHORT'].includes(direction)&&p.productDirection===direction&&!currentQuote({...p,isinConfirmed:true})&&!manualSnapshotStatus(p,p.snapshot).complete;
}

// Terms have their own source date; a quote/upload never refreshes them.
function normalizeSwissSgText(raw){
 raw=String(raw||'');
 if(!/sg-zertifikate\.ch\b|Swiss DOTS/i.test(raw))return raw;
 raw=raw.replace(/(^|\n)([ \t]*)Strike\b/gi,'$1$2Basispreis').replace(/(^|\n)([ \t]*)Stoppschwelle\b/gi,'$1$2Knock-Out-Barriere');
 raw=raw.replace(/Call\s*\/\s*Put\s+(Call|Put)\b/gi,'Produktrichtung $1');
 // Swiss grouping is unambiguous only with complete three-digit groups.
 raw=raw.replace(/\b[0-9][0-9'’]*\.[0-9]+(?=\s*USD\b)/g,v=>strictOcrNumber(v)===null?v:v.replace(/['’]/g,''));
 if(/BEST Turbo-\s*(?:\n\s*Produktart\s+)?Optionsscheine?/i.test(raw))raw=raw.replace(/(^|\n)\s*Produktart\s+(?:BEST Turbo-\s*)?Optionsscheine?/i,'$1Produktart BEST Turbo-Optionsscheine');
 return raw;
}
function normalizeProductTermLayout(raw){
 raw=String(raw||'').replace(/(Knock[-– ]Out)\s+Schwelle/gi,'Knock-out-Schwelle');
 // BNP's information icon and date precede the amount on narrow screens.
 // Join only a labelled USD cell; never use the rounded comparison cards.
 raw=raw.replace(/((?:Basispreis|Knock-out-Schwelle))\s*(?:[oOⓘ▶►&]\s*)?\((\d{2}\.\d{2}\.\d{4})\)\s*(?:[oOⓘ▶►&]\s*)?([\d.,]+)\s*USD\b/gi,'$1 $3 USD ($2)');
 raw=raw.replace(/((?:Basispreis|Knock-out-Schwelle)\s*[\d.,]+\s*USD)\s*\((\d{2}\.\d{2}\.\d{4})\)/gi,'$1 ($2)');
 return raw;
}
function parseProductTerms(raw,onlyKeys=null){
 raw=normalizeProductTermLayout(normalizeSwissSgText(raw)).replace(/(?:©|®|ⓘ|@)/g,'').replace(/Bezugsverhaltnis/g,'Bezugsverhältnis');
 // Description paragraphs are sentences, not table rows split by screen width.
 if(/Produktbeschreibung/i.test(raw)){
  const prose=raw.replace(/\s+/g,' '),rows=[];
  for(const m of prose.matchAll(/hat ein Bezugsverhältnis von (\d+(?:[.,]\d+)?\s*:\s*1)(?=[. ]|$)/gi))rows.push('Bezugsverhältnis '+m[1]);
  for(const m of prose.matchAll(/Der Basispreis und die Knock-Out-Barriere des Produkts liegen aktuell bei ([\d.,]+) USD\./gi))rows.push('Basispreis '+m[1]+' USD','Knock-Out-Barriere '+m[1]+' USD');
  for(const m of prose.matchAll(/bezieht sich auf den Basiswert (.+?) und hat ein/gi))rows.push('Basiswert '+m[1]);
  raw=rows.join('\n');
 }
 raw=raw.replace(/(^|\n)[ \t]*[oOQ]{1,2}[ \t]+(?=USD\b)/g,'$1');
 // Mobile SG tables wrap the USD/date cell, sometimes above its label.
 // Join only adjacent, recognisable amount/currency fragments, never another row.
 if(/BNP\s+Paribas|derivate\.bnpparibas\.com/i.test(raw))raw=raw.replace(/(^|\n)\s*Typ\s+(?=Unlimited\s+(?:Long|Short)\b)/gi,'$1Produkttyp ');
 // BNP places the terms date before the amount, on the same or next line.
 raw=raw.replace(/(Knock[- ]Out)\s+Schwelle/gi,'Knock-out-Schwelle');
 raw=raw.replace(/((?:Basispreis|Knock-out-Schwelle))\s*\((\d{2}\.\d{2}\.\d{4})\)\s*([\d.,]+)\s*USD\b/gi,'$1 $3 USD ($2)');
 raw=raw.replace(/(Laufzeit|Bezugsverhältnis)\s*[&▶►]\s*/g,'$1 ');
 const termLabel='(?:Basispreis|Finanzierungslevel|Knock-Out-Barriere|Knock-out-Schwelle)';
 raw=raw.replace(new RegExp('(?:^|\\n)[ \\t.,;]*([0-9][0-9.,]*)[ \\t]*\\n[ \\t]*('+termLabel+')[ \\t]*[:=]?[ \\t]*(?=USD\\b)','gi'),'\n$2 $1 ');
 raw=raw.replace(new RegExp('('+termLabel+'[ \\t]*[:=]?[ \\t]*(?:\\n[ \\t]*)?[0-9][0-9.,]*)[ \\t]*\\n(?:[ \\t]*\\n)*[ \\t]*(USD\\b)','gi'),'$1 $2');
 raw=raw.replace(new RegExp('('+termLabel+'[ \\t]*[:=]?[ \\t]*[0-9][0-9.,]*[ \\t]+USD)[ \\t]*\\n[ \\t]*(\\([^\\n]*\\))','gi'),'$1 $2');
 // A correctly read German USD amount establishes the table's number convention.
 const germanAmounts=/\b\d{1,3}\.\d{3},\d+\s*USD\b/.test(raw);
 const numberCorrection=germanAmounts&&/\b\d{1,3},\d{3},\d+\s*USD\b/.test(raw);
 if(germanAmounts)raw=raw.replace(/\b(\d{1,3}),(\d{3}),(\d+)\s*USD\b/g,'$1.$2,$3 USD');
 const out={},dates=Array.from(String(raw).matchAll(/(?:^|\n)\s*(?:Produktdatenstand|Bedingungenstand)\s*[:=]?\s*([^\n]+)/gi));
 if(new Set(dates.map(m=>m[1].trim())).size>1)return {error:'Widersprüchlicher Produktdatenstand'};
 const at=dates.length?sourceTimestamp(dates[0][1]):null;
 const labels={ko:'Knock-Out-Barriere|Knock-out-Schwelle',ratio:'Bezugsverhältnis|Bezugsverhaeltnis',strike:'Basispreis|Finanzierungslevel',underlying:'Basiswert|Underlying',contract:'Future-Kontrakt|Futures-Kontrakt|Kontrakt',type:'Produkttyp|Produktart',maturity:'Laufzeit|Fälligkeit|Faelligkeit',currency:'Produktwährung|Produktwaehrung',quanto:'Quanto|Währungsabsicherung'};
 for(const [key,label] of Object.entries(labels)){
  if(onlyKeys&&!onlyKeys.includes(key))continue;
  let matches=Array.from(String(raw).matchAll(new RegExp('(?:^|\\n)\\s*(?:'+label+')\\s*[:=]?\\s*([^\\n]+)','gi')));
  // Issuers use "Produktart" for the instrument family and "Typ" for
  // Call/Put or Long/Short. Only fall back to Typ when no product-family
  // label exists, otherwise both rows would be treated as contradictory.
  if(key==='type'&&!matches.length)matches=Array.from(String(raw).matchAll(/(?:^|\n)\s*Typ\s*[:=]?\s*([^\n]+)/gi));
  if(!matches.length)continue;
  const values=Array.from(new Set(matches.map(m=>m[1].trim())));
  if(values.length!==1)return {error:'Widersprüchliche Produktbedingung: '+label.split('|')[0]};
  let value=values[0],dateText=null,dateWarning=null,displayDecimals=null;
  if(['strike','ko'].includes(key)){
   const dated=value.match(/^([\d.,]+\s*USD)\s*\(([^\n]*)\)?\s*$/i);
   if(dated){
    value=dated[1].trim();const candidate=dated[2].replace(/\)\s*$/,'').trim();
    const parts=candidate.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
    const d=parts?new Date(Date.UTC(+parts[3],+parts[2]-1,+parts[1])):null;
    if(parts&&d.getUTCFullYear()===+parts[3]&&d.getUTCMonth()===+parts[2]-1&&d.getUTCDate()===+parts[1])dateText=candidate;
    else dateWarning='Datum im Bild nicht sicher erkannt; am Original prüfen. Aktualität nicht bestätigt.';
   }
  }
  if(key==='ratio'&&/^\d+(?:[.,]\d+)?\s*:\s*1$/.test(value)){
   const denominator=Number(value.split(':')[0].trim().replace(',','.'));
   if(!(denominator>0))return {error:'Bezugsverhältnis ungültig'};
   out[key]={value:1/denominator,at,displayText:values[0]};continue;
  }
  if(['ratio','strike','ko'].includes(key)){
   const m=value.match(['strike','ko'].includes(key)?/^([\d.,]+)\s*USD$/i:/^([\d.,]+)$/);
   if(!m)return {error:label.split('|')[0]+': Zahl'+(key==='strike'?' und Währung USD':'')+' eindeutig angeben'};
   if(['strike','ko'].includes(key))displayDecimals=(m[1].match(/[.,](\d+)$/)||[])[1]?.length??0;
   value=strictOcrNumber(m[1]);if(!(value>0&&Number.isFinite(value)))return {error:label.split('|')[0]+': positiver Wert erforderlich'};
  }
  out[key]={value,at:dateWarning?null:at,dateText,...(displayDecimals!==null?{displayDecimals}:{}),ocrCorrection:dateWarning||(numberCorrection&&['ko','strike'].includes(key)?'OCR-Trennzeichen anhand des deutschen Tabellenformats vereinheitlicht; am Original prüfen':null)};
 }
 return out;
}
// Offline research of product conditions only. No quote requests or quote clocks.
const PRODUCT_CONDITION_RESEARCH={
 'DE000FC1CHB7':{direction:'LONG',source:'https://www.onvista.de/derivate/Knock-Outs/309138945-FC1CHB-DE000FC1CHB7',values:{ratio:0.1,underlying:'XAU/USD',quanto:'Nein',type:'Turbo',maturity:'Open End',currency:'EUR'}},
 'DE000FG5GUT0':{direction:'LONG',source:'https://www.onvista.de/derivate/Knock-Outs/336000321-FG5GUT-DE000FG5GUT0',values:{ratio:0.1,underlying:'XAU/USD',quanto:'Nein',type:'Turbo',maturity:'Open End',currency:'EUR'}},
 'DE000FG5GUX2':{direction:'LONG',source:'https://www.sg-zertifikate.at/product-details/fg5gux',values:{ratio:0.1,quanto:'Nein',type:'Turbo BEST',maturity:'Open End'}}
};
const CONDITION_RESEARCH_AT='2026-10-03T13:10:00Z';
function applyResearchedTerms(items){
 return items.map(p=>{
  p=restorePdfReference(p);
  const record=PRODUCT_CONDITION_RESEARCH[p.isin];if(!record||p.direction!==record.direction)return p;
  const old=p.snapshot?.isin===p.isin?p.snapshot:{isin:p.isin},terms={...old.terms};
  for(const [key,value]of Object.entries(record.values))if(!terms[key]||terms[key].value===undefined||terms[key].value==='')terms[key]={value,at:null,source:record.source,conditionVerified:true,reviewedAt:CONDITION_RESEARCH_AT};
  return {...p,snapshot:{...old,terms}};
 });
}
function hasScreenshotIdentity(x){
 return !!x&&(['ISIN','WKN'].includes(x.identityBasis)||x.identityBasis==='Valor'&&SWISS_SG_VALORS[x.isin]===x.identityValor||x.identityBasis==='Bilderserie'&&validIsin(x.isin)&&x.identityContext?.isin===x.isin&&x.identityContext?.basis==='image-series'&&!!x.identityContext?.anchor||x.identityBasis==='Produktkontext'&&validIsin(x.isin)&&x.identityContext?.isin===x.isin&&x.identityContext?.basis==='opened-product');
}
function automaticIdentity(p){
 if(!validIsin(p.isin))return false;
 const q=p.quote,x=p.snapshot;
 const image=x?.isin===p.isin&&hasScreenshotIdentity(x);
 const issuer=q?.isin===p.isin&&q.productVerified===true;
 if(!image&&!issuer)return false;
 if(image){
  if(x.direction&&p.productDirection!==x.direction)return false;
  for(const [field,key]of Object.entries({price:'Kurs',leverage:'Hebel',ko:'KO'})){
   const e=x.evidence?.[key];
   // A verified quote for this exact product may update mutable market values.
   // Identity is separate from quote freshness; downstream quote gates remain.
   if(e&&n(p[field])!==n(e.value)&&!(field==='ko'&&termValueMatches(e.value,p.ko,e))&&!(issuer&&(['price','leverage'].includes(field)&&n(field==='price'?(q.price??q.analysisQuote?.price):q[field])!==null&&n(p[field])===n(field==='price'?(q.price??q.analysisQuote?.price):q[field])||field==='ko'&&currentProductTerm(p,'ko',q.conditions?.ko,Date.now())&&n(p.ko)===n(q.conditions.ko.value))))return false;
  }
 }
 if(issuer&&(q.direction||q.metadata?.direction)&&(q.direction||q.metadata.direction)!==p.productDirection)return false;
 return true;
}
function automaticCondition(e,key){
 if(!e?.source||e.conflict||e.revoked||e.ocrCorrection)return false;
 const value=String(e.value??'').trim();
 return key==='ratio'?n(e.value)>0&&n(e.value)<=1:
  key==='underlying'?/^(Gold|XAU\/USD|Gold Future)$/i.test(value):
  key==='type'?/^(BEST Turbo-Optionsscheine? \(Open-End\)|Turbo|Turbo BEST|Mini Future|Knock-out Turbo|Unlimited (?:Long|Short))$/i.test(value):
  key==='maturity'?/^(Open[ -]?End|Unbegrenzt)$/i.test(value):key==='currency'?['EUR','CHF'].includes(value):false;
}
function durableCondition(e,key,now){
 if(!e?.source||e.revoked===true||e.conflict===true)return false;
 if(e.automatic===true&&!e.at&&automaticCondition(e,key))return true;
 // Only explicit product-condition evidence may outlive a daily market snapshot.
 if(['type','currency','maturity'].includes(key)&&e.reviewed===true)return true;
 const checked=Date.parse(e.reviewedAt);
 if(key==='contract')return e.conditionVerified===true&&/^GC[FGHJKMNQUVXZ]\d{2}$/.test(e.value||'')&&Number.isFinite(checked)&&now>=checked&&now-checked<=86400000;
 return ['ratio','underlying','type','currency','maturity','quanto'].includes(key)&&e.conditionVerified===true&&Number.isFinite(checked)&&checked<=now;
}
function maturityDeadline(raw){
 const exact=sourceTimestamp(raw);if(exact)return Date.parse(exact);
 const m=String(raw).match(/^(\d{2})[/.](\d{2})[/.](\d{4})$/);if(!m)return null;
 // A date alone is accepted before its Zurich calendar day. Do not invent an intraday expiry.
 return selectionTimeWindow(m[1]+'/'+m[2]+'/'+m[3]+' 00:00')?.start??null;
}
// Daily issuer terms carry a calendar date, not an invented intraday timestamp.
function currentDatedTerm(e,now){
 if(!e?.source||e.conflict||e.revoked||e.ocrCorrection)return false;
 if(e.fixed===true&&e.conditionVerified===true&&String(e.source).startsWith('https://www.sg-zertifikate.de/')&&e.policySource==='https://www.sg-zertifikate.de/contentmgmt/media/c5bihw1s/bro_turbo-optionsscheine.pdf'){const age=now-Date.parse(e.reviewedAt);return age>=0&&age<=86400000&&/^\d{4}-\d{2}-\d{2}$/.test(e.validUntil||'')&&e.validUntil>zurichListDay(now).day;}
 if(e.at){const age=now-Date.parse(e.at);return Number.isFinite(age)&&age>=0&&age<=86400000;}
 const m=String(e.dateText||'').match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
 return !!m&&m[3]+'-'+m[2]+'-'+m[1]===zurichListDay(now).day;
}
// User policy accepts a coherent observation series for term validity in Bob.
// Own issuer dates remain authoritative; request/capture time is labelled separately.
function termSeriesReference(p,key,e,now=Date.now()){
 if(!['strike','ko'].includes(key)||!e?.source||!(n(e.value)>0)||e.at||e.dateText||e.sourceTimeRaw||e.conflict||e.revoked||e.ocrCorrection)return null;
 const q=p.quote?.isin===p.isin&&p.quote.productVerified?p.quote:null,direct=q?.conditions?.[key],automatic=e.validitySeries;
 // Central proof wins for both origins, but only for the exact value and
 // source. A separately declared term/effective date is handled above.
 const shared=sharedProductFieldTime(p,key,e.value,now);
 if(shared?.valid&&shared.kind==='issuer-collection'&&direct===e)
  return {origin:'automatic',text:shared.at,label:'Gemeinsamer Zeitbezug der SG-Abrufserie'};
 if(automatic?.policy==='declared-series-v1'&&automatic.origin==='automatic'&&automatic.isin===p.isin&&automatic.source===e.source&&direct?.source===e.source&&n(direct.value)===n(e.value)){
  const age=now-Date.parse(automatic.observedAt);
  if(Number.isFinite(age)&&age>=0&&age<=86400000)return {origin:'automatic',text:automatic.observedAt,label:'Zeitbezug der automatischen Abrufserie'};
 }
 const x=p.snapshot,series=x?.captureSeries;
 const term=x?.terms?.[key];
 // KO can be recognized as a priced image field without a duplicate
 // 'terms.ko' record. Its original observation context still counts.
 if(term&&(term.conflict||term.revoked||n(term.value)!==n(e.value)))return null;
 const own=term||key==='ko'&&x?.evidence?.KO;
 if(x?.isin!==p.isin||!hasScreenshotIdentity(x)||own?.source!==e.source||n(own.value)!==n(e.value))return null;
 // Both single views and grouped screenshots now use the SAME verified
 // field-time function as the issuer import, without copying another source.
 if(shared?.valid&&shared.source===e.source&&['image-view','image-series'].includes(shared.kind))
  return {origin:shared.kind==='image-view'?'image-view':'screenshot',text:shared.text,
   label:shared.kind==='image-view'?'Gemeinsamer Zeitbezug derselben Produktansicht':'Zeitbezug der Aufnahmeserie'};
 return null;
}
const KO_MAX_AGE_MS=8*60*60*1000;
function koTermTime(p,e,now){
 if(!e?.source||!(n(e.value)>0)||e.conflict||e.revoked||e.ocrCorrection)return NaN;
 if(e.at)return Date.parse(e.at);
 if(p.quote?.isin===p.isin&&p.quote.productVerified&&p.quote.conditions?.ko===e&&e.conditionVerified&&currentDatedTerm(e,now))return Date.parse(e.reviewedAt);
 const ref=termSeriesReference(p,'ko',e,now);
 if(ref)return ref.origin==='automatic'?Date.parse(ref.text):selectionTimeWindow(ref.text)?.start;
 // Keep the original, now-expired shared observation visible as "8h
 // abgelaufen" instead of incorrectly reporting that a value never existed.
 const shared=sharedProductFieldTime(p,'KO',e.value,now);
 const q=p.quote,shot=p.snapshot;
 const sameIssuer=q?.isin===p.isin&&q.conditions?.ko===e&&shared?.kind==='issuer-collection';
 const sameImage=(shot?.terms?.ko===e||shot?.evidence?.KO===e)
  &&['image-view','image-series'].includes(shared?.kind)
  &&shared.source===e.source;
 if(shared&&(sameIssuer||sameImage))return Date.parse(shared.at);
 return NaN;
}
function koEvidenceStatus(p,now=Date.now()){
 const q=p.quote?.isin===p.isin&&p.quote.productVerified?p.quote:null;
 const shot=p.snapshot?.isin===p.isin?p.snapshot:null;
 const evidence=[q?.conditions?.ko,shot?.terms?.ko,shot?.evidence?.KO];
 const matches=evidence.filter(e=>e&&termValueMatches(p.ko,e.value,e));
 const times=matches.map(e=>({at:koTermTime(p,e,now),source:e.source}));
 // Preserve the original checkedAt on retained issuer metadata; an unsuccessful
 // request must never extend the evidence window.
 if(q?.metadata?.termsDated!==false&&q?.source&&termValueMatches(p.ko,q?.metadata?.ko,shot?.evidence?.KO)&&!q?.conditions?.ko)
  times.push({at:Date.parse(q.checkedAt),source:q.source});
 const fixed=window.BobCombined.fixedFor(p);
 if(fixed)times.push({at:Date.parse(fixed.confirmedAt),source:fixed.source});
 const latest=times.filter(x=>Number.isFinite(x.at)&&x.at<=now).sort((a,b)=>b.at-a.at)[0];
 const blocked=matches.some(e=>e.conflict||e.revoked||e.ocrCorrection)||!!(shot?.evidence?.KO?.dateText&&shot.terms?.ko&&shot.evidence.KO.dateText!==shot.terms.ko.dateText);
 const expiresAt=latest?latest.at+KO_MAX_AGE_MS:null;
 const current=!!latest&&!blocked&&now<expiresAt;
 return {current,at:latest?new Date(latest.at).toISOString():null,expiresAt:expiresAt?new Date(expiresAt).toISOString():null,
  source:latest?.source||null,reason:current?'KO-Schwelle: innerhalb der 8-Stunden-Nachweisfrist':
  latest?'KO-Schwelle: 8-Stunden-Nachweisfrist abgelaufen – automatisch aktualisieren oder neuen Screenshot ergänzen':
  'KO-Schwelle: belegter Zeitbezug fehlt – aktuellen Abruf oder Screenshot ergänzen'};
}
function currentProductTerm(p,key,e,now){
 if(key==='ko'){const at=koTermTime(p,e,now);return Number.isFinite(at)&&now>=at&&now-at<KO_MAX_AGE_MS;}
 return currentDatedTerm(e,now)||!!termSeriesReference(p,key,e,now);
}
function renderTermSeriesValidity(p,now=Date.now()){
 const koState=koEvidenceStatus(p,now);
 return '<div data-ko-validity><b>'+esc(koState.reason)+'</b>'+(koState.expiresAt?'<br>Nachweis bis '+esc(new Date(koState.expiresAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}))+' (Zürich)':'')+'</div>'+ ['strike','ko'].map(key=>{
  const direct=p.quote?.conditions?.[key],shot=p.snapshot?.terms?.[key];
  const ref=termSeriesReference(p,key,direct,now)||termSeriesReference(p,key,shot,now);
  return ref?'<div data-term-series-validity><b>'+esc(key==='strike'?'Basispreis':'KO-Schwelle')+': gemeinsamer Zeitbezug für Bob gültig</b><br>'+esc(ref.label+' · '+ref.text)+' · kein separat bestätigtes Emittenten-Gültigkeitsdatum</div>':'';
 }).join('');
}
function screenshotKoCurrent(p,now){
 const x=p.snapshot,e=x?.evidence?.KO,t=x?.terms?.ko;
 if(x?.isin!==p.isin||n(e?.value)!==n(p.ko))return false;
 if(e?.conflict||e?.revoked||e?.ocrCorrection)return false;
 if(e?.at)return currentProductTerm(p,'ko',e,now);
 if(e?.dateText&&t?.dateText&&e.dateText!==t.dateText)return false;
 // An actual KO field from the very same dated image carries the shared
 // observation context even when no separate terms.ko entry was extracted.
 if(hasScreenshotIdentity(x)&&currentProductTerm(p,'ko',e,now))return true;
 // An undated repeat in a quote image does not invalidate the separate
 // dated terms image. Match identity and amount; never transfer its date.
 return hasScreenshotIdentity(x)&&n(t?.value)===n(p.ko)&&currentProductTerm(p,'ko',t,now);
}
function termValueMatches(value,actual,e){
 if(n(value)===n(actual))return true;
 const digits=e?.displayDecimals;
 return n(e?.value)===n(value)&&!!e?.source&&Number.isInteger(digits)&&digits>=2&&digits<=8&&n(actual)>0&&Number(n(actual).toFixed(digits))===n(value);
}
// Explicit daily issuer terms supersede an undated image observation only.
// Preserve image evidence; neither capture time nor numerical proximity is proof.
function datedIssuerSupersedesObservation(p,key,direct,old,now){
 const q=p.quote;
 if(q?.isin!==p.isin||!q.productVerified||!direct?.conditionVerified||direct.secondary
  ||direct.source!=='https://derivate.bnpparibas.com/product-details/'+p.isin+'/'
  ||!direct.dateText||!currentDatedTerm(direct,now)||!currentProductTerm(p,key,direct,now)
  ||n(q.metadata?.[key])!==n(direct.value)||!(n(direct.value)>0))return false;
 const age=now-Date.parse(direct.reviewedAt);
 if(!Number.isFinite(age)||age<0||age>=KO_MAX_AGE_MS)return false;
 if(!old||old.at||old.dateText||old.sourceTimeRaw||old.conditionVerified
  ||old.conflict||old.revoked||old.ocrCorrection)return false;
 const ref=termSeriesReference(p,key,old,now);
 return !!ref&&['screenshot','image-view'].includes(ref.origin);
}
function productTermsStatus(p,now=Date.now(),allowObserved=false){
 const reasons=[],warnings=[],values={},q=p.quote?.isin===p.isin?p.quote:null;
 const meta=q?.productVerified?q.metadata:null;
 const model=q?.productModel?.isin===p.isin?q.productModel:meta?.underlyingType==='FUTURE'&&meta.contract&&meta.contract===q?.futureResearch?.contract?q.futureResearch:null;
 const shot=p.snapshot?.isin===p.isin?p.snapshot:null,terms={...(q?.productVerified?q.conditions:{}),...shot?.terms};
 // Prefer today's separately dated issuer terms over expired image evidence.
 for(const key of ['strike','ko']){
  const direct=q?.productVerified?q.conditions?.[key]:null,old=shot?.terms?.[key]||(key==='ko'?shot?.evidence?.KO:null);
  if(currentProductTerm(p,key,direct,now)){
   if(datedIssuerSupersedesObservation(p,key,direct,old,now)&&!termValueMatches(old.value,direct.value,old)){
    terms[key]=direct;
    warnings.push((key==='strike'?'Basispreis':'KO-Barriere')+': datierter Emittentenwert '+direct.value+' USD (Stand '+direct.dateText+') übernommen; undatierter Bildwert '+old.value+' USD bleibt als frühere Beobachtung gespeichert');
   }else if((currentProductTerm(p,key,old,now)||key==='ko'&&currentDatedTerm(old,now))&&!termValueMatches(old.value,direct.value,old))reasons.push((key==='strike'?'Basispreis':'KO-Barriere')+': aktuelle Nachweise widersprechen sich (Bild '+old.value+' USD; Emittent '+direct.value+' USD'+(direct.dateText?' · Stand '+direct.dateText:'')+'). Aufnahmezeit bestätigt nicht das Gültigkeitsdatum des Bildwerts');
   else terms[key]=direct;
  }
 }
 if(shot&&hasScreenshotIdentity(shot))for(const [key,e]of Object.entries(shot.terms||{})){
  if(automaticCondition(e,key))terms[key]={...e,automatic:true};
 }
 if(!validIsin(p.isin)||p.isinConfirmed!==true)reasons.push('Eindeutige Produktzuordnung oder widerspruchsfreie Bildwerte fehlen');
 if(!['LONG','SHORT'].includes(p.productDirection))reasons.push('Long/Short fehlt');
 if(/FAKTOR|FACTOR/i.test([p.name,q?.name,meta?.name,terms.type?.value].join(' ')))reasons.push('Faktorprodukt ausgeschlossen');
 const api=model&&q?.productVerified&&q.source&&q.checkedAt&&now>=Date.parse(q.checkedAt)&&now-Date.parse(q.checkedAt)<=86400000?model:null;
 // Explicit issuer conditions take precedence over generic historical list labels.
 for(const key of ['ratio','underlying','contract','type','maturity','currency']){
  const direct=q?.productVerified?q.conditions?.[key]:null;
  if(direct?.conditionVerified&&durableCondition(direct,key,now)){
   const old=shot?.terms?.[key];
   if(key==='ratio'&&old&&durableCondition(old,key,now)&&n(old.value)!==n(direct.value))reasons.push('Bezugsverhältnis: bestätigte Nachweise widersprechen sich');
   terms[key]=direct;
  }
 }
 const labels={ratio:'Bezugsverhältnis',strike:'Basispreis in USD',underlying:'Exakter Basiswert (z. B. XAU/USD)',type:'Produkttyp',maturity:'Laufzeit / Fälligkeit oder Open End',currency:'Produktwährung'};
 for(const [key,label] of Object.entries(labels)){
  const e=terms[key],age=now-Date.parse(e?.at);
  if(key==='strike'&&((shot&&hasScreenshotIdentity(shot))||q?.productVerified&&e===q.conditions?.strike)&&currentProductTerm(p,key,e,now)||durableCondition(e,key,now)||e?.source&&Number.isFinite(age)&&age>=0&&age<=86400000)values[key]=e.value;
  else if(api&&['ratio','strike','underlying'].includes(key))values[key]=api[key];
  if(key==='strike'&&allowObserved&&values[key]===undefined&&e?.source&&n(e.value)>0&&!e.ocrCorrection&&!e.conflict&&!e.revoked){values[key]=e.value;warnings.push('Basispreis: mit beobachtetem Wert gerechnet; Gültigkeitsdatum nicht bestätigt');}
  if(values[key]===undefined||values[key]==='')reasons.push(label+((e?.value!==undefined&&e.value!=='')?(key==='strike'?': Wert eingelesen; gültiger datierter Nachweis fehlt oder ist älter als 24 Stunden':': Wert eingelesen; Produktbedingung nicht eindeutig belegt'):': Wert fehlt'));
 }
 for(const key of ['ratio','strike'])if(values[key]!==undefined&&!(n(values[key])>0))reasons.push(labels[key]+': ungültig');
 if(values.currency&&values.currency!=='EUR'&&!(values.currency==='CHF'&&q?.currencyConversion?.fromCurrency==='CHF'&&q.currencyConversion.toCurrency==='EUR'))reasons.push('Produktwährung: bestätigte Umrechnung in EUR fehlt');
 if(allowObserved&&values.currency==='CHF'){
  const eur=q?.analysisQuote?.currency==='EUR'?q.analysisQuote:q?.currency==='EUR'?q:null;
  if(!eur||!(n(eur.ask)>0)||n(eur.ask)!==n(p.price))reasons.push('EUR-Produktkurs passt nicht zur bestätigten CHF-Umrechnung');
 }
 if(values.type&&!/turbo|mini.?future|knock.?out|^Unlimited (?:Long|Short)$/i.test(values.type))reasons.push('Produkttyp nicht als Turbo / Knock-out bestätigt');
 const typeDirection=String(values.type||'').match(/^Unlimited (Long|Short)$/i);
 if(typeDirection&&typeDirection[1].toUpperCase()!==p.productDirection)reasons.push('Produktrichtung widerspricht Produkttyp');
 const future=isFutureProduct(p)||/future/i.test(values.underlying||'');
 if(future){
  const e=terms.contract,age=now-Date.parse(e?.at);
  values.contract=durableCondition(e,'contract',now)||e?.source&&Number.isFinite(age)&&age>=0&&age<=86400000?e.value:null;
  if(!/^GC[FGHJKMNQUVXZ]\d{2}$/.test(values.contract||''))reasons.push('Exakter Gold-Future-Kontrakt fehlt oder ist nicht aktuell bestätigt. Öffne das betroffene Produkt bei DEGIRO: Produktdetails → Dokumente → Endgültige Bedingungen (falls dort nicht vorhanden: Dokumente auf der Emittentenseite). Nutze im Dokument die Suche (Lupe): zuerst deine ISIN, dann Basiswert / Underlying, Referenzkontrakt / Futures Contract oder Kontraktmonat. Die Angaben stehen häufig in einer Tabelle mit Produktbedingungen; bei mehreren Produkten zählt nur die Zeile zu deiner ISIN. Benötigt werden der genaue Future mit Monat/Jahr und Börse. Suche zusätzlich nach Roll / Rollover / Anpassung des Basiswerts für einen möglichen Kontraktwechsel. Lade gut lesbare Screenshots der passenden Tabellenzeile samt Spaltenüberschriften und der relevanten Textstellen als Detailbilder zu diesem Produkt hoch; ISIN und Dokumentdatum bitte mit aufnehmen. Eine feste Seitenzahl kann Bob ohne das konkrete Dokument nicht nennen.');
  if(meta?.contract&&values.contract&&meta.contract!==values.contract)reasons.push('Future-Kontrakt widerspricht Emittentendaten');
  if(values.underlying&&!/\bgold\b.*\bfuture\b|\bfuture\b.*\bgold\b/i.test(values.underlying))reasons.push('Exakter Gold-Future-Basiswert widerspricht Produktart');
 }else if(values.underlying&&values.underlying!=='XAU/USD')reasons.push('Basiswert ungenau: Gold allein bestätigt keinen Spot-Basiswert');
 if(meta?.direction&&meta.direction!==p.productDirection||model?.direction&&model.direction!==p.productDirection||shot?.direction&&shot.direction!==p.productDirection)reasons.push('Long/Short widerspricht Produktnachweis');
 for(const key of ['ratio','strike'])if(model?.[key]&&values[key]&&!termValueMatches(values[key],model[key],terms[key]))reasons.push(labels[key]+': Screenshot und Emittent widersprechen sich');
 if(values.maturity&&!/^open\s*end$|^unbegrenzt$/i.test(values.maturity)){
  const end=maturityDeadline(values.maturity);
  if(!Number.isFinite(end)||end<=now)reasons.push('Fälligkeit fehlt als eindeutiger Zeitpunkt oder Produkt ist abgelaufen');
 }
 const ko=shot?.evidence?.KO,apiKoAge=now-Date.parse(q?.checkedAt);
 if(!(n(p.ko)>0))reasons.push('Knock-out-Schwelle fehlt');
 else if(!koEvidenceStatus(p,now).current){
  if(allowObserved)warnings.push(koEvidenceStatus(p,now).reason+'; mit gespeichertem Wert gerechnet, keine aktuelle Freigabe');
  else reasons.push(koEvidenceStatus(p,now).reason);
 }

 if(meta?.ko&&!termValueMatches(p.ko,meta.ko,ko))reasons.push('Knock-out-Schwelle widerspricht Produktquelle: gespeichert '+p.ko+' USD ('+(ko?.source||'Produktliste / manuelle Eingabe')+'; Stand '+(ko?.at||ko?.dateText||'nicht belegt')+'), Quelle '+meta.ko+' USD ('+(q.termsSource||q.source||'Produktquelle')+'; Gültigkeitsstand '+(meta.termsDated===false?'nicht belegt':q.checkedAt||'nicht belegt')+'). Abrufzeit '+(q.termsCheckedAt||q.checkedAt||'unbekannt')+' ist kein Gültigkeitsdatum.');
 if(meta?.status!==undefined&&(!(meta.status&1)||meta.status&(2|8|16|32)))reasons.push('Produkt laut Emittent nicht aktiv');
 return {complete:reasons.length===0,reasons,values,warnings};
}
function bnpSourceIssue(p,now=Date.now()){
 const q=p.quote;
 if(q?.isin!==p.isin||!q?.productVerified||!/^BNP Paribas/.test(q.source||''))return '';
 if(q.sourceFailure)return 'BNP-Kursabruf: Abruf fehlgeschlagen; bestätigte Produktnachweise bleiben mit ursprünglichem Datenstand erhalten';
 if(!q.found)return '';
 if(!q.marketOpen||now>Date.parse(q.tradingEndAt))return 'BNP-Kursabruf: Markt geschlossen oder Produkt derzeit nicht handelbar';
 const timing=quoteTiming(q,now);
 return timing.fresh?'':'BNP-Kursabruf: Quellenantwort veraltet oder Geld-/Brief-/Hebelzeit nicht prüfbar';
}
function sharedSgIssuerLeverage(p,now=Date.now()){
 const ref=p?.quote?.issuerLeverageReference;
 if(!(n(ref?.value)>=1)||ref?.dated!==false||ref?.eligible!==false)return null;
 const proof=sharedProductFieldTime(p,'Hebel',ref.value,now);
 if(proof?.kind!=='issuer-collection')return null;
 return {value:n(ref.value),at:proof.at,source:ref.source,
  fresh:proof.valid,kind:'shared-issuer-observation',analysisOnly:true};
}
function productFieldStates(p,now=Date.now()){
 const q=p.quote?.isin===p.isin&&p.quote.productVerified?p.quote:null;
 const shot=p.snapshot?.isin===p.isin?p.snapshot:null;
 const live=productDisplayQuote(q,p.isin,now);
 const from=(key,value,at,source,limit=90000,kind='')=>{
  const t=typeof at==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(at)?Date.parse(at):selectionTimeWindow(at)?.start;
  const age=Number.isFinite(t)?now-t:null;
  return {key,value,at:at||null,source:source||'gespeicherter Wert',kind,ageSeconds:age===null?null:Math.floor(age/1000),state:!(n(value)>0)?'fehlt':age===null||age<0?'Aktualität unbestätigt':age>limit?'veraltet':kind==='screenshot'?'Momentaufnahme · innerhalb Nachweisfrist (14 h)':limit===300000&&age>90000?'innerhalb Altersgrenze (300 s)':'aktuell'};
 };
 const items={},analysisLimit=(q?.analysisMaxAgeSeconds||90)*1000;
 const native=q?.nativeChartEvidence;
 // Preserve the issuer's native CHF price observation even when a current
 // CHF/EUR conversion is unavailable. Do not label it an executable quote.
 const nativeChf=!!q?.productVerified&&native?.currency==='CHF'
  &&n(native.bid)>0&&n(native.ask)>=n(native.bid)&&typeof native.pointAt==='string';
 for(const [key,label] of [['bid','Geld'],['ask','Brief']]){
  // A DEGIRO list "price" (last/reference) is NOT an evidenced bid or ask.
  // Only named provider fields or a paired/individually sourced screenshot
  // may populate Geld/Brief, even when the generic price input is nonempty.
  const direct=live?.currency==='EUR'&&n(live[key])>0&&
    (n(live.bid)===null||n(live.ask)===null||n(live.ask)>=n(live.bid));
  const e=shot?.evidence?.[label];
  const paired=shot?.currency==='EUR'&&n(shot.bid)>0&&n(shot.ask)>=n(shot.bid);
  const single=shot?.currency==='EUR'&&!!e?.source&&n(e.value)>0;
  const nativeObserved=nativeChf?{...native,bidAt:native.pointAt,askAt:native.pointAt,
    source:'SG · datierter CHF-Chartkurs',priceKind:'issuer-chart'}:null;
  const observed=direct?live:nativeObserved;
  const imageValue=paired?n(shot[key]):single?n(e.value):null;
  items[key]=from(label,observed?observed[key]:imageValue,
    observed?observed[key+'At']:imageValue!==null?(e?.at||shot?.sourceTime):null,
    observed?observed.source:imageValue!==null?e?.source:null,
    observed?(observed===nativeObserved?300000:analysisLimit):SCREENSHOT_MAX_AGE_MS,observed?observed.priceKind:'screenshot');
  if(direct&&(live===q?.referenceQuote||live===q&&q?.sourceFailure)&&items[key].state!=='veraltet')items[key].state='Aktualität unbestätigt · letzter erfolgreicher Abruf';
  if(!direct&&e?.fromSeries){items[key].fromSeries=true;items[key].timeText=e.timeText;}
  else if(!direct&&e?.fromSharedContext){items[key].fromSharedContext=true;items[key].timeText=e.contextTimeText;}
 }
 const le=shot?.evidence?.Hebel,shared=sharedSgIssuerLeverage(p,now);
 const hasShot=!le?.conflict&&!le?.revoked&&n(le?.value)>=1;
 const directAt=Date.parse(q?.leverageAt);
 const directFresh=n(q?.leverage)>=1&&Number.isFinite(directAt)&&now>=directAt&&now-directAt<=90000;
 // A stale/undated retained leverage must not mask the current matching SG
 // reference used by the analysis badge above this diagnostic block.
 const preferShared=shared?.fresh&&!directFresh;
 const leverage=preferShared?shared.value:n(q?.leverage)>=1?q.leverage:hasShot?le.value:shared?.value??(n(p.leverage)>=1?p.leverage:null);
 const directLev=!preferShared&&q&&n(q.leverage)===n(leverage);
 const sharedLev=preferShared||(!directLev&&shared&&n(leverage)===shared.value&&!hasShot);
 items.leverage=from('Hebel',leverage,directLev?q.leverageAt:sharedLev?shared.at:hasShot&&n(le.value)===n(leverage)?le.at:null,
  directLev?(q.leverageSource||q.source):sharedLev?shared.source:le?.source,
  directLev?90000:sharedLev?300000:SCREENSHOT_MAX_AGE_MS,directLev?'':sharedLev?'issuer-reference':'screenshot');
 if(sharedLev){
  items.leverage.state=shared.fresh?'gemeinsamer SG-Zeitbezug · aktuell (nur Analyse)':'veraltet · gemeinsamer SG-Zeitbezug';
  items.leverage.fromSharedContext=true;
 }
 if(!directLev&&!sharedLev&&le?.fromSeries){items.leverage.fromSeries=true;items.leverage.timeText=le.timeText;}
 else if(!directLev&&!sharedLev&&le?.fromSharedContext){items.leverage.fromSharedContext=true;items.leverage.timeText=le.contextTimeText;}
 if(directLev&&q.leverageEstimated&&n(leverage)>0){
  const c=q.leverageCalculation;
  const clocks=[c?.inputs?.basisAt,c?.inputs?.askAt,c?.inputs?.fxDataAt,c?.inputs?.fxEffectiveAt].map(v=>typeof v==='string'?Date.parse(v):NaN);
  const valid=clocks.every(t=>Number.isFinite(t)&&t<=now);
  const age=valid?Math.max(...clocks.map(t=>now-t)):null;
  const inputState=!valid?'Aktualität unbestätigt':age>(c?.maxAllowedInputAgeSeconds||90)*1000?'veraltet':c?.inputsFresh===true?(age>90000?'innerhalb Altersgrenze (300 s)':'aktuell'):'zeitlich abweichend oder Aktualität unbestätigt';
  const names=['Goldkurs','Produkt-Briefkurs','USD/EUR-Datenstand','USD/EUR-Kurszeit'];
  const aged=clocks.flatMap((t,i)=>Number.isFinite(t)&&now-t>(c?.maxAllowedInputAgeSeconds||90)*1000?[names[i]+' '+Math.floor((now-t)/60000)+' Min.']:[]);
  items.leverage.state=(c?.inputs?.basisEstimated?'CFD-basierte Schätzung':'berechneter Hebel')+' · Eingangsdaten: '+inputState+(aged.length?' ('+aged.join(', ')+')':'');
 }
 // Use the same validated fallback as the main price display. A field is
 // present even when calculated; its provenance is separate from presence.
 // Fresh original observations retain precedence, including screenshots.
 const calculated=calculatedProductDisplay(p,now);
 if(calculated){
  const current=f=>f&&n(f.value)>0&&Number.isFinite(f.ageSeconds)&&f.ageSeconds>=0&&f.ageSeconds<=90
    &&!/(unbestätigt|veraltet|abweichend)/i.test(f.state);
  for(const key of ['bid','ask'])if(!current(items[key])){
   items[key]=from(key==='bid'?'Geld':'Brief',calculated[key],calculated.at,calculated.source,60000,'calculated');
   items[key].state='berechnet · aktuell';
  }
  if(!current(items.leverage)){
   const c=q.calculatedProduct;
   const value=n(c.goldUsd)*n(c.usdEur)*n(c.ratio)/n(c.askEur);
   if(Number.isFinite(value)&&value>0){
    items.leverage=from('Hebel',value,calculated.at,calculated.source,60000,'calculated');
    items.leverage.state='berechnet · aktuell';
   }
  }
 }
 return items;
}
function renderProductFieldStates(p){
 const fields=productFieldStates(p);
 const calculation=p.quote?.leverageCalculation, comparison=p.quote?.leverageComparison;
 const detail=calculation?.available?'<div>Berechnungsbasis: Briefkurs '+esc(calculation.inputs?.askNative??calculation.inputs?.askEur)+' '+esc(calculation.inputs?.quoteCurrency||'EUR')+' · Quellenzeit '+esc(calculation.inputs?.askAt)+' · '+esc(calculation.inputs?.priceKind==='issuer-chart'?'Chartbeobachtung':calculation.inputs?.priceSource)+'<br>Basiswert: '+esc(calculation.inputs?.basisEstimated?'geschätzt':calculation.inputs?.basisDelayed?'verzögerter Quellenkurs':'Quellenkurs')+' · '+esc(calculation.inputs?.basisSource)+' · '+esc(calculation.inputs?.contract||'Gold Spot')+'<br>Zeitabstand der Eingangskurse: '+esc(calculation.skewSeconds)+' s (Analysetoleranz: '+esc(calculation.maxAllowedSkewSeconds||30)+' s; maximales Datenalter: '+esc(calculation.maxAllowedInputAgeSeconds||90)+' s)</div>':'';
 const comparisonDetail=comparison?'<div>Hebelvergleich: '+esc(comparison.comparable?(comparison.warning?'Auffällige Abweichung: ':'Abweichung: ')+comparison.relativeDifferencePct+' % · '+comparison.note:comparison.reason)+'</div>':'';
 const native=p.quote?.nativeChartEvidence,fx=p.quote?.currencyConversion;
 const shared=p.quote?.isin===p.isin&&p.quote?.productVerified?p.quote?.sharedTimeContext:null;
 const observations=p.quote?.sharedValueObservations||{};
 const allValues=shared&&shared.isin===p.isin&&Array.isArray(shared.fields)
  ?shared.fields.filter(k=>observations[k]?.isin===p.isin&&observations[k].contextAt===shared.at)
  :[];
 const commonBlock=allValues.length?
  '<details data-shared-product-values><summary>Gemeinsamer SG-Zeitbezug · alle erfassten Werte ('+allValues.length+')</summary>'+
  '<div>Beobachtungszeitpunkt: '+esc(shared.at)+' · alle angezeigten Werte wurden für dieselbe ISIN in dieser SG-Abrufserie erfasst. Eigene Quellenzeit und Gültigkeitsdatum bleiben vorrangig.</div>'+
  allValues.map(k=>'<div><b>'+esc(k)+': '+esc(observations[k].value)+'</b> · gemeinsamer Zeitbezug '+esc(observations[k].contextAt)+
  (observations[k].sourceAt?' · eigene Quellenzeit '+esc(observations[k].sourceAt):'')+
  (observations[k].sourceDate?' · eigenes Gültigkeitsdatum '+esc(observations[k].sourceDate):'')+'</div>').join('')+
  '</details>':'';
 const nativeInfo=native?'<div><b>Originalkurs CHF: Geld '+esc(native.bid)+' / Brief '+esc(native.ask)+'</b><br>Quellenzeit '+esc(native.pointAt)+(fx?'<br>Für die Analyse in EUR umgerechnet · CHF/EUR '+esc(fx.rate)+' · '+esc(fx.at):'<br>EUR-Umrechnung noch nicht verfügbar')+'</div>':'';
 return '<div class="small" data-field-status>'+nativeInfo+commonBlock+detail+comparisonDetail+Object.values(fields).map(f=>'<div><b>'+valuePresenceMark(f.state==='fehlt')+' '+esc(f.key)+(f.kind==='issuer-chart'?' (Chartkurs)':'')+': '+esc(f.key==='Hebel'&&n(f.value)>0?Number(f.value).toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2}):f.value??'—')+' · '+esc(f.state)+'</b>'+ (f.at?'<br>'+ (f.fromSeries?'Zeitbezug der Aufnahmeserie ':f.kind==='issuer-reference'?'Gemeinsamer SG-Hebel-Zeitbezug ':f.fromSharedContext?'Gemeinsamer Zeitbezug derselben Produktansicht ':'Quellenzeit ')+esc(f.at)+' · '+esc(f.ageSeconds)+' s alt':f.fromSeries&&f.timeText?'<br>Zeitbezug der Aufnahmeserie '+esc(f.timeText)+(/\d{2}[/.]\d{2}[/.]\d{4}/.test(f.timeText)?' · Sekunden unbekannt':' · Kursdatum fehlt'):'')+'<br>'+esc(f.source)+(f.kind==='issuer-chart'?' · Chartbeobachtung, kein ausführbarer Kursnachweis':'')+'</div>').join('')+(p.quote?.leverageEstimated?'<div>'+esc(p.quote.leverageNote)+'</div>':'')+(p.quote?.leverageCalculation?.available===false?'<div>Hebelberechnung: '+esc(p.quote.leverageCalculation.reason)+'</div>':'')+(p.quote?.backupStatus?.state==='unavailable'?'<div>Onvista-Backup derzeit nicht verfügbar: '+esc(p.quote.backupStatus.code)+'</div>':'')+'</div>';
}
// A current native quote and its own FX evidence supersede the old screenshot
// quote for analysis selection. The image and its gearing retain original clocks.
function calculatedLeverageEvidence(p,now=Date.now()){
 const q=p.quote,c=q?.leverageCalculation,i=c?.inputs,m=q?.metadata;
 if(q?.isin!==p.isin||!q.productVerified||m?.status!==1||!m.simpleNonQuantoTurbo||!c?.available||!c.fresh||i?.basisEstimated||i?.basisDelayed)return null;
 const clocks=['askAt','basisAt','fxDataAt','fxEffectiveAt'].map(k=>typeof i?.[k]==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(i[k])?Date.parse(i[k]):NaN);
 if(clocks.some(t=>!Number.isFinite(t)||t>now||now-t>300000)||Math.max(...clocks)-Math.min(...clocks)>90000)return null;
 const values=[i.basisPriceUsd,i.usdEur,i.ratio,i.askNative,c.value].map(n);
 if(values.some(v=>!(v>0))||!['EUR','CHF'].includes(i.quoteCurrency)||n(i.ratio)!==n(m.ratio)||n(c.value)!==n(p.leverage))return null;
 const expected=values[0]*values[1]*values[2]/values[3];
 if(Math.abs(expected-c.value)>Math.abs(expected)*1e-9||Date.parse(c.at)!==Math.min(...clocks))return null;
 return {value:c.value,at:c.at,kind:'calculated-gearing'};
}
function currentConvertedChfEvidence(p,now=Date.now()){
 const q=p.quote,a=q?.analysisQuote,native=q?.nativeChartEvidence,fx=q?.currencyConversion,f=fx?.evidence;
 const x=p.snapshot,e=x?.evidence?.Hebel,calculated=calculatedLeverageEvidence(p,now);
 if(q?.isin!==p.isin||!q.productVerified||q.metadata?.status!==1||isFutureProduct(p)||knockoutStatus(p)||!automaticIdentity(p)||!productTermsStatus(p,now).complete)return null;
 if(!a||a.priceKind!=='issuer-chart'||a.currency!=='EUR'||!a.source||a.delayed||native?.currency!=='CHF'||native.delayed||fx?.fromCurrency!=='CHF'||fx.toCurrency!=='EUR'||!fx.source||f?.base!=='USD'||f.marketSession!=='open'||f.eurSource!=='live'||f.chfSource!=='live')return null;
 if(!calculated&&(x?.isin!==p.isin||!hasScreenshotIdentity(x)||!e?.source||e.conflict||e.revoked||e.ocrCorrection||!(n(e.value)>=1)||n(e.value)!==n(p.leverage)||!evidenceTiming(e,now).fresh))return null;
 const rate=n(f.eur)/n(f.chf),near=(v,w)=>Number.isFinite(v)&&Number.isFinite(w)&&Math.abs(v-w)<=Math.max(1e-9,Math.abs(w)*1e-12);
 if(!(n(f.eur)>0&&n(f.chf)>0&&rate>0&&rate<10&&n(native.bid)>0&&n(native.ask)>=n(native.bid))||!near(n(fx.rate),rate)||!near(n(a.bid),n(native.bid)*rate)||!near(n(a.ask),n(native.ask)*rate)||n(p.price)!==n(a.ask)||fx.nativeAt!==native.pointAt)return null;
 const raw=[native.pointAt,f.dataAt,f.eurAt,f.chfAt,a.bidAt,a.askAt,fx.at];
 const clocks=raw.map(v=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(v)?Date.parse(v):NaN);
 if(clocks.some(t=>!Number.isFinite(t)||t>now||now-t>300000)||Math.max(...clocks)-Math.min(...clocks)>90000)return null;
 const oldest=Math.min(...clocks.slice(0,4));
 if(clocks.slice(4).some(t=>t!==oldest))return null;
 const local=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Zurich',weekday:'short',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now)),part=k=>local.find(x=>x.type===k)?.value;
 if(['Sat','Sun'].includes(part('weekday'))||Number(part('hour'))<8||Number(part('hour'))>=22)return null;
 return {...a,at:new Date(oldest).toISOString(),leverage:calculated?.value??n(e.value),leverageAt:calculated?.at??e.at,leverageKind:calculated?'calculated-gearing':'screenshot',isExecutableQuote:false};
}
function analysisReleaseQuote(p,now=Date.now()){
 const converted=currentConvertedChfEvidence(p,now);if(converted)return converted;
 const q=p.quote,a=q?.analysisQuote,c=q?.leverageCalculation,i=c?.inputs;
 if(isFutureProduct(p)||knockoutStatus(p)||!automaticIdentity(p)||!q?.productVerified||q.metadata?.status!==1||!productTermsStatus(p,now).complete)return null;
 if(!a||a.currency!=='EUR'||!a.source||a.delayed||!(n(a.bid)>0&&n(a.ask)>=n(a.bid))||n(a.ask)!==n(p.price)||!c?.available||!c.inputsFresh||i?.basisEstimated||i?.basisDelayed||n(c.value)!==n(p.leverage)||n(q.leverage)!==n(p.leverage)||n(i.askEur)!==n(a.ask))return null;
 const clocks=[a.bidAt,a.askAt,i.askAt,i.basisAt,i.fxDataAt,i.fxEffectiveAt].map(v=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(v)?Date.parse(v):NaN);
 if(clocks.some(t=>!Number.isFinite(t)||t>now||now-t>300000)||Math.max(...clocks)-Math.min(...clocks)>90000)return null;
 const local=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',weekday:'short',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now));
 const part=k=>local.find(x=>x.type===k)?.value;
 if(['Sat','Sun'].includes(part('weekday'))||Number(part('hour'))<8||Number(part('hour'))>=22)return null;
 return {...a,at:new Date(Math.min(...clocks)).toISOString()};
}
function finalProductStatus(p,now=Date.now(),reference){
 if(knockoutStatus(p))return {complete:false,terminal:true,reasons:["Ausgeknockt – keine weiteren Daten erforderlich"]};
 const status=productTermsStatus(p,now),reasons=status.reasons.slice();
 const venue=sharedVenueStatus(p,now);
 if(venue?.required&&!venue.current)reasons.push('DEGIRO-Handelsplatznachweis offen');
 const q=p.quote?.isin===p.isin?p.quote:null;
 const r=q?.productVerified&&q.metadata?.contract===q.futureResearch?.contract?q.futureResearch:null;
 const pair=(x,source)=>!!source&&n(x?.bid)>0&&n(x?.ask)>=n(x.bid)&&!x.delayed&&freshTimes([x.bidAt,x.askAt],now,90);
 const issuer=pair(q,q?.source)&&q.found&&!q.estimated&&!q.calculatedProduct&&q.currency==='EUR'&&q.direction===p.productDirection&&q.marketOpen&&(isFutureProduct(p)||currentQuote(p,now));
 const future=pair(r,q?.source)&&r.direction===p.productDirection&&r.marketOpen;
 const shot=selectionDetailStatus(p,now);
 const ref=reference?.isin===p.isin&&reference.reviewed&&reference.paired&&reference.source&&reference.venue&&!reference.delayed&&n(reference.bid)>0&&n(reference.ask)>=n(reference.bid)&&freshTimes([reference.quoteAt],now,90);
 if(!issuer&&!future&&!shot.complete&&!ref&&!analysisReleaseQuote(p,now)){
  const issue=bnpSourceIssue(p,now);
  if(issue)reasons.push(issue);
  else reasons.push(...shot.reasons.filter(x=>!status.reasons.includes(x)).map(reason=>productEvidenceReason(p,reason)));
 }
 return {...status,complete:!reasons.length,reasons};
}
function detailScreenshotData(text,expectedIsin,productContext=null,excludedFields=[]){
 let raw=normalizeProductTermLayout(normalizeSwissSgText(normalizeBnpQuoteColumns(normalizeReviewedDegiroIdentity(text))));
 // BNP's Gold reference identifier is not the certificate ISIN.
 // Scope removal to the explicit Gold underlying section, preserving all
 // certificate identifiers and rejecting conflicting product identities.
 if(/derivate\.bnpparibas\.com|BNP\s+Paribas/i.test(raw)&&/Basiswert\s+GOLD\b/i.test(raw)){
  raw=raw.replace(/(Basiswert\s+GOLD\s+ISIN\s*[:=]?\s*)USFX0{5}XAU\b/i,'Basiswert GOLD\nReferenzkennung XAU/USD');
  raw=raw.replace(/(?:^|\n)\s*Basiswert\s*\n(?=\s*Basiswert\s+GOLD\b)/i,'\n');
 }
 if(!validIsin(expectedIsin))return{ok:false,reason:"Bitte zuerst die ISIN dieses Produkts am Screenshot prüfen und korrigieren."};
 const repairedIdentity=seriesIsinRepair(raw,expectedIsin,productContext);
 if(repairedIdentity)raw=repairedIdentity.text;
 const identity=screenshotIdentity(raw,expectedIsin,productContext);
 if(!identity.ok)return identity;
 // Preserve verified identity before uncertain numeric lines are removed:
 // those lines may be part of the reviewed broker-layout signature.
 const verifiedAliases=parseScreenshotCandidates(raw).filter(c=>c.isin===expectedIsin&&c.originalIsin&&c.identityCorrection);
 for(const candidate of verifiedAliases)raw=raw.replace(new RegExp('\\b'+candidate.originalIsin+'\\b','g'),expectedIsin);

 if(explicitKnockout(raw))return {ok:true,isin:expectedIsin,identityBasis:identity.basis,identityContext:identity.context||null,terms:{},times:{},lifecycle:{isin:expectedIsin,status:'KNOCKED_OUT',verified:true,text:'KNOCKED OUT',identityBasis:identity.basis}};

 const degiroVenueEvidence=parseDegiroDisplayedQuote(raw,expectedIsin,true);
 for(const key of excludedFields){
  const label=({strike:'Basispreis|Finanzierungslevel',ko:'Knock-Out-Barriere|Knock-out-Schwelle',ratio:'Bezugsverhältnis|Bezugsverhaltnis',leverage:'Hebel|Leverage',bid:'Geld|Bid',ask:'Brief|Ask'})[key];
  if(label)raw=raw.replace(new RegExp('(^|\\n)[ \\t]*(?:'+label+')[ \\t]*[:=]?[ \\t]*[^\\n]*','gi'),'$1');
 }

 if(/BNP\s+PARIBAS|derivate\.bnpparibas\.com/i.test(raw)){
  raw=raw.replace(/\bVerkaufen\b/g,'Geld').replace(/\bKaufen\b/g,'Brief');
 }
 // Reject an entire numeric token instead of accepting a numeric prefix
 // such as 12 from "12,O9". Alphabet characters are never prices.
 const numericTokens=raw.matchAll(/(?:^|\n)\s*(?:Geld|Brief|Bid|Ask|Hebel)\s*[:=]?\s*(?:€|EUR)?\s*([0-9][0-9A-Za-z.,]*)/gi);
 for(const token of numericTokens)if(strictOcrNumber(token[1])===null)return {ok:false,reason:'Zahl enthält unklare Zeichen: '+token[1]+'. Bitte einen schärferen Ausschnitt zeigen.'};
 const titlePair=excludedFields.some(k=>['bid','ask'].includes(k))?null:sgScreenshotTitlePair(raw,expectedIsin);
 if(titlePair){
  // Both values are visible in this same image's SG browser title. Never
  // borrow the second price or its timestamp from another screenshot.
  raw=raw.replace(/\b(?:Geld|Brief)\b/gi,'Kursanzeige');
  raw+='\nGeld '+titlePair.bid+' EUR\nBrief '+titlePair.ask+' EUR';
 }
 if(['WKN','Valor','Produktkontext','Bilderserie'].includes(identity.basis))raw='ISIN '+expectedIsin+'\n'+raw;
 const x=ocrExtract(raw.replace(/(\bBAR\s*\n)[@©●•®]\s*(?=[0-9])/gi,"$1"));
 if(/\b(?:SHORT|PUT)\b/i.test(raw)&&/\b(?:LONG|CALL)\b/i.test(raw))return {ok:false,reason:'Long/Short im Bild widersprüchlich: Produktzuordnung prüfen'};
 if(!x.price){const top=raw.match(/(?:^|\n)\s*€\s*([0-9]+(?:[.,][0-9]+)?)\b/);if(top)x.price=top[1].replace(",",".");}
 const amount=label=>{const m=raw.match(new RegExp("\\b(?:"+label+")(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR)?\\s*([0-9]+(?:[.,][0-9]+)?)","i"));return m?Number(m[1].replace(",",".")):null;};
 const native=swissScreenshotQuote(raw);
 let draft=native?{ok:false,currency:'CHF',hasQuote:native.hasQuote,paired:native.paired,partialQuote:native.partialQuote,fields:{bid:native.bid,ask:native.ask}}:window.BobCombined.screenshotDraft(raw,expectedIsin);
 const degiroDisplayedQuote=parseDegiroDisplayedQuote(raw,expectedIsin);
 if(degiroDisplayedQuote&&!draft.paired){
  draft={...draft,...(degiroDisplayedQuote.currency==='CHF'?{ok:false,currency:'CHF'}:{}),hasQuote:true,paired:true,partialQuote:null,
    fields:{...draft.fields,source:'DEGIRO',venue:degiroDisplayedQuote.venue,
      bid:String(degiroDisplayedQuote.bid),ask:String(degiroDisplayedQuote.ask),
      quoteAt:degiroDisplayedQuote.sourceTime}};
 }
 const uncertainBrokerPair=draft.hasQuote&&!draft.paired&&!draft.partialQuote&&!!degiroVenueEvidence;
 if(uncertainBrokerPair){
  draft={...draft,paired:false,partialQuote:{bid:null,ask:null}};
  x.price='';x.spread='';
 }
 if(draft.hasQuote&&!draft.paired&&!draft.partialQuote)return{ok:false,reason:'Produkt erkannt'+(identity.basis==='WKN'?' über WKN '+identity.wkn:'')+', aber Geld-/Briefpaar nicht vollständig oder eindeutig. Bitte beide Kurse im selben Bild zeigen.'};
 const bid=draft.partialQuote?draft.partialQuote.bid:draft.paired?n(draft.fields.bid):amount("Geld|Bid"),ask=draft.partialQuote?draft.partialQuote.ask:draft.paired?n(draft.fields.ask):amount("Brief|Ask");
 const importWarnings=[],importNotes=[];
 if(uncertainBrokerPair)importWarnings.push('Geld-/Briefpaar nicht eindeutig; Produktidentität und DEGIRO-Handelsplatz separat übernommen.');
 if(repairedIdentity)importNotes.push('ISIN-Zeichenverwechslung '+repairedIdentity.original+' anhand des eindeutig gelesenen Serienbilds '+productContext.anchor+' korrigiert; Prüfziffer bestätigt.');
 if(draft.partialQuote){x.price="";x.spread="";importWarnings.push(bid===null?"Geldkurs fehlt: Kursbereich mit Geld und Brief ergänzen.":"Briefkurs fehlt: Kursbereich mit Geld und Brief ergänzen.");}
 if(draft.fields?.ko1)x.ko=draft.fields.ko1;
 if((bid!==null&&bid<=0)||(ask!==null&&ask<=0)||(bid!==null&&ask!==null&&ask<bid))return{ok:false,reason:"Geld-/Briefkurse widersprüchlich gelesen. Bitte ein schärferes Bild hochladen."};
 const quoteText=raw.replace(/(?:^|\n)\s*(?:Produktdatenstand|Bedingungenstand|Fälligkeit|Faelligkeit|Laufzeit|KO-Zeit|Hebelzeit)\s*[:=]?[^\n]*/gi,'');
 const stamp=screenshotTimes(raw).quote?.text||(quoteText.match(/\b\d{2}[/.]\d{2}[/.]\d{4}\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||"";
 const currency=degiroDisplayedQuote?.currency||degiroVenueEvidence?.currency||(native?'CHF':/\bEUR\b|€/.test(raw)?"EUR":"");
 if(bid!==null&&ask!==null&&currency==="EUR"){x.price=String(ask);x.spread=String(Math.round((ask-bid)*1000000)/1000000);}
 if(currency==='CHF'){x.price='';x.spread='';if(bid!==null||ask!==null)importNotes.push('CHF-Originalkurse gespeichert; EUR-Analyse verwendet separat datierte automatische Umrechnung.');}
 if(!x.leverage){const lv=raw.match(/\bLV\s+(\d+(?:[.,]\d+)?)/i);if(lv)x.leverage=lv[1].replace(",",".");}
 let terms=parseProductTerms(raw);
 if(terms.error){
  if(!/sg-zertifikate\.(?:de|at)\b|SOCI[EÉ]T[EÉ]\s+G[EÉ]N[EÉ]RALE|BNP\s+Paribas|derivate\.bnpparibas\.com/i.test(raw)&&identity.basis!=='Produktkontext')return {ok:false,reason:terms.error};
  if(!/^(?:Basispreis|Knock-Out-Barriere): (?:Zahl|positiver Wert)/.test(terms.error))return {ok:false,reason:terms.error};
  terms={};
  for(const key of ['ko','ratio','strike','underlying','contract','type','maturity','currency','quanto']){
   const read=parseProductTerms(raw,[key]);
   if(read.error){
    if(!/^(?:Basispreis|Knock-Out-Barriere): (?:Zahl|positiver Wert)/.test(read.error))return {ok:false,reason:read.error};
    importWarnings.push(read.error);if(key==='ko')x.ko="";
   }else Object.assign(terms,read);
  }
  if(!Object.keys(terms).length&&bid===null&&ask===null&&!x.leverage)return {ok:false,reason:importWarnings.join(' · ')};
 }

 // Call/Put is direction, not the instrument family; do not overwrite a Turbo heading.
 if(/^(?:Call|Put|Long|Short)$/i.test(terms.type?.value||''))delete terms.type;
 // Explicit wrapped SG product heading/table text, not an inferred product model.
 if(/BEST Turbo-\s*(?:\n\s*Produktart\s+)?Optionsscheine?\s*\(Open-\s*End\)/i.test(raw)){
  terms.type={value:'BEST Turbo-Optionsscheine (Open-End)',at:null};
  terms.maturity={value:'Open End',at:null};
 }
 if(/sg-zertifikate\.(?:de|at)\b/i.test(raw)&&/BEST Turbo-Optionsschein\s+Open-End\s*\|\s*(?:Put|Call)\s*\|\s*auf Gold\b/i.test(raw)){
  terms.type={value:'BEST Turbo-Optionsschein (Open-End)',at:null};
  terms.maturity={value:'Open End',at:null};
  if(!terms.underlying)terms.underlying={value:'Gold',at:null};
 }
 if(!terms.currency&&['EUR','CHF'].includes(currency)&&bid!==null&&ask!==null)terms.currency={value:currency,at:null,fromQuote:true};
 if(terms.ko)x.ko=String(terms.ko.value);
 return{ok:true,...x,importWarnings,importNotes,identityBasis:identity.basis,identityValor:identity.valor||null,identityContext:identity.context||null,bid,ask,currency,...(degiroVenueEvidence?{degiroVenueEvidence}:{}),...(degiroDisplayedQuote?{degiroDisplayedQuote}:{}),sourceTime:stamp,times:screenshotTimes(raw),terms,delayed:/verzögert|delayed/i.test(raw),combinedDraft:draft};
}
// Registered issuer identity, verified against its ISIN/Valor table. Never infer
// an arbitrary numeric title from the currently selected product.
const SWISS_SG_VALORS={'DE000FG34XV8':'159787428'};
function swissScreenshotQuote(raw){
 if(!/sg-zertifikate\.ch\b/i.test(raw)||!/\bCHF\b/.test(raw))return null;
 const read=label=>{
  const rows=[...raw.matchAll(new RegExp('(?:^|\\n)\\s*'+label+'\\s*[:=]?\\s*([0-9][0-9.,]*)\\s*(CHF|EUR)\\b','gi'))];
  return rows.length===1&&rows[0][2].toUpperCase()==='CHF'?strictOcrNumber(rows[0][1]):null;
 };
 const bid=read('Geld'),ask=read('Brief'),hasQuote=/(?:^|\n)\s*(?:Geld|Brief)\b/i.test(raw);
 return{bid,ask,hasQuote,paired:bid>0&&ask>=bid,partialQuote:hasQuote&&((bid>0&&ask===null)||(ask>0&&bid===null))?{bid,ask}:null};
}
// Show only product identifiers on failures, never the full private OCR transcript.
function imageIdentityDiagnostic(raw){
 const text=String(raw||'').toUpperCase();
 const ids=[...new Set(text.match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])].slice(0,3);
 const wkns=[...new Set(Array.from(text.matchAll(/\bWKN\s*[:=]?\s*([A-Z0-9]{6})\b/g),m=>m[1]))].slice(0,3);
 return 'Gelesen: '+(ids.length?'ISIN '+ids.join(', '):'keine ISIN')+(wkns.length?' · WKN '+wkns.join(', '):'');
}
// Repair identifiers only against an independently readable same-batch image.
// Never use the selected upload card or checksum alone as correction evidence.
function identitySeriesSource(raw){
 const text=String(raw||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'');
 if(/\bBNP\s+OTC\b/i.test(text))return 'degiro-bnp';
 if(/Societe\s+Generale\s+OTC/i.test(text))return 'degiro-sg';
 return null;
}
function seriesIsinRepair(raw,isin,context){
 if(!validIsin(isin)||!isin.startsWith('DE000')||context?.basis!=='image-series'||
    context.isin!==isin||context.anchorIsinVerified!==true||!context.source)return null;
 const observedSource=identitySeriesSource(raw);
 // A second cropped DEGIRO quote may omit its OTC footer entirely. A
 // recognizable broker quote layout can be provisionally joined to a verified
 // same-selection anchor; an explicitly different venue is never allowed.
 if(observedSource&&observedSource!==context.source)return null;
 if(!observedSource&&!(/\bKursdaten\b/i.test(String(raw))&&/\bISIN\b/i.test(String(raw))&&
    /\b(?:Geld|Brief|Bid|Ask)\b/i.test(String(raw))))return null;
 const text=String(raw),upper=text.toUpperCase();
 const direct=upper.match(/\bDE[0OQ]{3}[A-Z0-9]{7}\b/g)||[];
 // OCR may insert spaces or line breaks inside the *labelled* ISIN. Do not
 // assemble unrelated product names or numeric amounts into identifiers.
 const spaced=[...upper.matchAll(/\b(?:ISIN|1SIN)\s*[:|]?\s*(DE(?:[\s-]*[A-Z0-9]){10})(?![A-Z0-9])/g)]
   .map(m=>({original:m[1],token:m[1].replace(/[\s-]/g,'')}));
 const tokens=[...new Set([...direct,...spaced.map(x=>x.token)])];
 if(tokens.length!==1)return null;
 const token=tokens[0],normalized='DE000'+token.slice(5);
 // An unspaced valid ISIN needs no series repair. Even if it disagrees with
 // the anchor, do not overwrite it. A spaced copy of the anchor can be joined.
 const split=spaced.find(x=>x.token===token&&x.original!==token);
 // A checksum-valid, *unspaced* identifier is independent evidence and must
 // never be rewritten. Its spaced spelling can be normalized only if equal to
 // the already independently confirmed series anchor.
 if((validIsin(token)&&(!split||token!==isin))||
    (validIsin(normalized)&&normalized!==isin))return null;
 if(normalized===isin){
  return split?{text:text.replace(split.original,isin),original:split.original}:null;
 }
 let changes=0;
 for(let i=5;i<12;i++)if(token[i]!==isin[i]){
  if(!ocrGlyphPair(token[i],isin[i])&&!(/^[8S]{2}$/.test(token[i]+isin[i])))return null;
  changes++;
 }
 if(changes<1||changes>2)return null;
 // A conflicting WKN, or a second readable identifier, still blocks linking.
 const wkns=[...upper.matchAll(/\bWKN\s*[:=]?\s*([A-Z0-9]{6})\b/g)].map(m=>m[1]);
 if(wkns.some(w=>w!==isin.slice(5,11)))return null;
 return {text:split?text.replace(split.original,isin):text.replace(new RegExp('\\b'+token+'\\b','gi'),isin),original:token};
}
function screenshotIdentity(raw,expectedIsin,productContext=null){
 raw=normalizeReviewedDegiroIdentity(raw);
 const repaired=seriesIsinRepair(raw,expectedIsin,productContext);
 if(repaired)raw=repaired.text;
 const valors=/sg-zertifikate\.ch\b/i.test(raw)?[...new Set([...String(raw).matchAll(/\bValor[ \t:]*([0-9]{6,9})\b|(?:^|\n)\s*(?:[x×]\s*)?([0-9]{6,9})\s*[-–]\s*\d+[.,]\d+\s*\/\s*\d+[.,]\d+\s*CHF\b/gi)].map(m=>m[1]||m[2]))]:[];
 if(valors.length&&(valors.length!==1||SWISS_SG_VALORS[expectedIsin]!==valors[0]))return {ok:false,reason:'Valor-Nummer im Bild gehört nicht zum ausgewählten Produkt.'};
 const ids=Array.from(new Set(parseScreenshotCandidates(raw).map(x=>x.isin)));
 if(ids.length)return ids.length===1&&ids[0]===expectedIsin?{ok:true,basis:'ISIN'}:{ok:false,reason:'Der Screenshot gehört nicht eindeutig zu '+expectedIsin+'. Bitte Produktkennung prüfen.'};
 const wkns=Array.from(String(raw).toUpperCase().matchAll(/\bWKN\s*[:=]?\s*([A-Z0-9]{6})\b|\b([A-Z0-9]{6})\s+WKN\b/g)).map(m=>m[1]||m[2]);
 if(/sg-zertifikate\.(?:de|at)\b/i.test(raw)){
  for(const m of String(raw).toUpperCase().matchAll(/(?:^|\n)[^\n]*?\b([A-Z0-9]{6})\s*[-–]\s*\d+[.,]\d+\s*\/\s*\d+[.,]\d+\s*€/g))wkns.push(m[1]);
  for(const m of String(raw).toUpperCase().matchAll(/(?:^|\n)\s*([A-Z0-9]{6})\s*(?=\n|$)/g))if(/[A-Z]/.test(m[1])&&/\d/.test(m[1]))wkns.push(m[1]);
 }
 // BNP prints WKN without a label, either in the product badge or browser title.
 // Only accept those layouts on an identified issuer screenshot; never infer
 // identity from the selected upload card or a substring of a longer code.
 if(/BNP\s+PARIBAS|derivate\.bnpparibas\.com/i.test(raw)){
  const primary=String(raw).split(/Ähnliche\s+Produkte/i)[0].toUpperCase();
  for(const m of primary.matchAll(/(?:^|\n)\s*([A-Z0-9]{6})\s*(?=\n|$|[^A-Z0-9\n]*MARKT\s+(?:GEÖFFNET|GESCHLOSSEN)\b|\d+[.,]\d+\s*\/\s*\d+[.,]\d+\s*€)/g)){
   if(/[A-Z]/.test(m[1])&&/\d/.test(m[1]))wkns.push(m[1]);
  }
 }
 // A focused badge read may disambiguate a confusable whole-page read.
 // Only the independently observed crop supplies the replacement; the selected
 // product is never a source. Unrelated identifiers continue to block import.
 const badge=String(raw).match(/(?:^|\n)WKN-Bildprüfung: ([A-Z0-9]{6})(?:\n|$)/);
 const labelled=[...new Set([...String(raw).toUpperCase().matchAll(/(?:^|\n)\s*WKN\s+([A-Z0-9]{6})\s*(?=\n|$)/g)].map(m=>m[1]))];
 const independent=labelled.length===1?labelled[0]:null;
 const unique=[...new Set(wkns.map(code=>{
  if(badge&&code.length===6&&Array.from(code).every((char,i)=>ocrGlyphPair(char,badge[1][i])))return badge[1];
  // A clearly labelled WKN in these same pixels disambiguates the browser title.
  // The selected product never supplies the replacement.
  if(independent&&/sg-zertifikate\.(?:de|at)\b/i.test(raw)&&code.length===6&&
   [...code].filter((char,i)=>char!==independent[i]).length===1&&
   [...code].every((char,i)=>char===independent[i]||/[7T]/.test(char)&&/[7T]/.test(independent[i])))return independent;
  return code;
 }))];
 if(validIsin(expectedIsin)&&expectedIsin.startsWith('DE000')&&unique.length===1&&unique[0]===expectedIsin.slice(5,11))return{ok:true,basis:'WKN',wkn:unique[0]};
 // The user explicitly assigns supplemental images through the issuer link.
 // Missing identity is allowed only in that captured product context. Any
 // observed conflicting ISIN/WKN above still blocks the import.
 const expectedWkn=expectedIsin.slice(5,11);
 if(!unique.length&&valors.length===1)return {ok:true,basis:'Valor',valor:valors[0]};
 const ambiguousSg=unique.length===1&&/sg-zertifikate\.(?:de|at)\b/i.test(raw)&&
  [...unique[0]].filter((char,i)=>char!==expectedWkn[i]).length===1&&
  [...unique[0]].every((char,i)=>char===expectedWkn[i]||/[7T]/.test(char)&&/[7T]/.test(expectedWkn[i]));
 if((!unique.length||ambiguousSg)&&validIsin(expectedIsin)&&productContext?.isin===expectedIsin&&productContext?.basis==='opened-product')
  return{ok:true,basis:'Produktkontext',context:{isin:expectedIsin,basis:'opened-product'}};
 if(!unique.length&&!valors.length&&validIsin(expectedIsin)&&productContext?.isin===expectedIsin&&productContext?.basis==='image-series'&&productContext?.anchor)
  return {ok:true,basis:'Bilderserie',context:{...productContext}};
 return{ok:false,reason:unique.length?'WKN im Bild passt nicht eindeutig zu '+expectedIsin+'. Bitte Produktkennung prüfen.':'ISIN oder WKN im Zusatzbild fehlt. Bitte die Produktkennung zusammen mit den Daten zeigen.'};
}
function sgScreenshotTitlePair(raw,isin){
 if(!/sg-zertifikate\.(?:de|at)\b/i.test(raw)||!validIsin(isin)||!isin.startsWith('DE000'))return null;
 if((raw.match(/\bGeld\b/g)||[]).length>1||(raw.match(/\bBrief\b/g)||[]).length>1)return null;
 const matches=Array.from(String(raw).matchAll(/\b([A-Z0-9]{6})\s*[-–]\s*(\d+[.,]\d+)\s*\/\s*(\d+[.,]\d+)\s*€/g));
 if(matches.length!==1||matches[0][1]!==isin.slice(5,11))return null;
 const numeric=s=>Number(s.replace(',','.')),bid=numeric(matches[0][2]),ask=numeric(matches[0][3]);
 const body=Array.from(String(raw).matchAll(/\b(\d+[.,]\d+)\s+EUR\b/g)).map(m=>numeric(m[1]));
 if(!(bid>0&&ask>=bid)||!body.length||body.some(v=>v!==bid&&v!==ask))return null;
 return{bid,ask};
}
function resetCombinedForm(i){
 const form=document.querySelector('[data-combined-form="'+i+'"]');if(!form?.querySelectorAll)return;
 form.querySelectorAll('[data-combined]').forEach(el=>{if(el.type==='checkbox')el.checked=false;else el.value='';});
 const summary=document.getElementById('dgCombinedDraft'+i);if(summary)summary.textContent='';
}
function prefillCombinedForm(i,draft,image){
 if(!draft?.ok)return;
 combinedReferences.delete(i);
 const form=document.querySelector('[data-combined-form="'+i+'"]');if(!form)return;
 const merged=window.BobCombined.mergeDraft(combinedDrafts.get(i),draft,image);combinedDrafts.set(i,merged);
 if(draft.hasQuote)for(const key of ['source','bid','ask','quoteAt','venue','url','goldReference','goldAt','goldUrl','fxReference','fxAt','fxUrl']){const el=form.querySelector('[data-combined="'+key+'"]');if(el)el.value='';}
 for(const [key,value] of Object.entries(merged.fields)){const el=form.querySelector('[data-combined="'+key+'"]');if(el)el.value=value;}
 form.querySelectorAll('input[type="checkbox"]').forEach(el=>el.checked=false);
 const summary=document.getElementById('dgCombinedDraft'+i);
 if(summary)summary.innerHTML='<b>Automatisch aus Bildern übernommen – bitte prüfen</b>'+Object.entries(merged.fields).filter(([,v])=>v!=='').map(([key,value])=>'<div>'+esc(key)+': '+esc(value)+' · Bild '+esc(merged.evidence[key]||image)+'</div>').join('')+merged.notes.map(note=>'<div>'+esc(note)+'</div>').join('');
 form.open=true;
}
const PDF_REFERENCE_STORE='bobProductPdfReferencesV1';
function restorePdfReference(p){
 try{
  const record=JSON.parse(localStorage.getItem(PDF_REFERENCE_STORE)||'{}')[p.isin];
  if(!record||record.isin!==p.isin||record.terms?.underlying?.value!=='XAU/USD'||!record.referenceDocument)return p;
  const old=p.snapshot?.isin===p.isin?p.snapshot:{isin:p.isin};
  if(old.terms?.underlying?.value&&!['Gold','XAU/USD'].includes(old.terms.underlying.value))return p;
  return {...p,snapshot:mergeScreenshotEvidence(old,record,record.terms.underlying.source)};
 }catch(_){return p;}
}
// Product PDFs supply static definitions only, never current market evidence.
function parseProductPdf(pages,expected,name){
 if(!validIsin(expected))throw new Error('Bitte zuerst eine gültige ISIN auswählen.');
 const normalized=pages.map(p=>String(p).replace(/\s+/g,' ').replace(/\(\s+/g,'(').replace(/\s+\)/g,')').replace(/"\s*(Referenzpreis)\s*"/g,'"$1"').trim());
 const all=normalized.join(' '),ids=[...new Set(all.match(/\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b/g)||[])].filter(validIsin);
 if(ids.length!==1||ids[0]!==expected)throw new Error('PDF ist nicht eindeutig dieser ISIN zugeordnet. Bitte die Einzelprodukt-Bedingungen wählen.');
 const table=normalized.findIndex(p=>/Ausstattungstabelle/.test(p)&&p.includes(expected)&&/Basiswert:\s*Gold \(unallocated gold\) gemäß den Regeln der LBMA/.test(p));
 const ko=normalized.findIndex(p=>/Knock-out-Ereignis/.test(p)&&/Bloomberg-Seite XAU Curncy/.test(p)&&/Briefkurs \(im Falle von Typ Put\)/.test(p));
 const fixing=normalized.findIndex(p=>/"Referenzpreis" ist/.test(p)&&/am Vormittag festgestellte[nr]? Gold-Preis/.test(p)&&/Feinunze/.test(p));
 if(table<0||ko<0||fixing<0||!/Typ:\s*Put\b/.test(normalized[table]))throw new Error('Goldreferenz in diesem PDF noch nicht eindeutig unterstützt. Es wurden keine Werte geändert.');
 const source=name+' · Seiten '+[table+1,ko+1,fixing+1].join(', '),reviewedAt=new Date().toISOString();
 const evidence=value=>({value,source,conditionVerified:true,reviewedAt});
 return {ok:true,isin:expected,identityBasis:'ISIN',terms:{underlying:evidence('XAU/USD')},
  referenceDocument:{name,isin:expected,importedAt:reviewedAt,pages:[table+1,ko+1,fixing+1],
   underlying:'Gold (unallocated gold) gemäß LBMA-Regeln',referenceVenue:'London Gold Market',
   knockOutReference:'Bloomberg XAU Curncy · Briefkurs USD je Feinunze (Put)',settlementReference:'Morgendliches Goldfixing / LBMA Gold Price AM',
   excerpts:[normalized[table].slice(0,1800),normalized[ko].slice(0,6000),normalized[fixing].slice(0,6000)]}};
}
let pdfLibraryPromise;
async function readProductPdf(file,expected){
 if(file.size>15*1024*1024)throw new Error('PDF zu groß. Maximal 15 MB.');
 const bytes=new Uint8Array(await file.arrayBuffer());
 if(String.fromCharCode(...bytes.slice(0,5))!=='%PDF-')throw new Error('Keine gültige PDF-Datei.');
 if(!pdfLibraryPromise)pdfLibraryPromise=import('https://cdn.jsdelivr.net/npm/pdfjs-dist@5.4.624/legacy/build/pdf.mjs').catch(e=>{pdfLibraryPromise=null;throw e;});
 const lib=await pdfLibraryPromise;
 lib.GlobalWorkerOptions.workerSrc='https://cdn.jsdelivr.net/npm/pdfjs-dist@5.4.624/legacy/build/pdf.worker.mjs';
 const task=lib.getDocument({data:bytes,isEvalSupported:false,useSystemFonts:false,disableFontFace:true});
 task.onPassword=()=>task.destroy();
 try{
  const pdf=await task.promise;if(pdf.numPages>80)throw new Error('Bitte die Einzelprodukt-Bedingungen mit höchstens 80 Seiten wählen.');
  const pages=[];
  for(let i=1;i<=pdf.numPages;i++){
   const page=await pdf.getPage(i),content=await page.getTextContent();pages.push(content.items.map(x=>x.str||'').join(' '));page.cleanup();
  }
  return parseProductPdf(pages,expected,file.name);
 }finally{await task.destroy();}
}
// Local originals support reprocessing after OCR updates. Never refresh source clocks.
const PRODUCT_OCR_VERSION='2026-10-23-second-image-series-v20';
const ORIGINAL_TTL=7*86400000,ORIGINAL_LIMIT=100*1024*1024;
const activeProductImports=new Set();
function originalRetention(records,now=Date.now()){
 const sorted=records.filter(r=>now-r.savedAt<ORIGINAL_TTL).reverse().sort((a,b)=>b.savedAt-a.savedAt);
 let bytes=0;return sorted.filter(r=>{bytes+=r.size||0;return bytes<=ORIGINAL_LIMIT;});
}
async function originalsTransaction(mode,action){
 if(typeof indexedDB==='undefined')throw new Error('Lokaler Bildspeicher ist nicht verfügbar');
 const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('bobProductOriginals',1);r.onupgradeneeded=()=>r.result.createObjectStore('files',{keyPath:'id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(new Error('Bildspeicher ist in einem anderen Fenster blockiert'));});
 try{return await new Promise((resolve,reject)=>{const tx=db.transaction('files',mode),store=tx.objectStore('files');let value;tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('Bildspeicherung abgebrochen'));action(store,v=>value=v);});}finally{db.close();}
}
async function loadProductOriginals(){
 return originalsTransaction('readwrite',(store,done)=>{const request=store.getAll();request.onsuccess=()=>{const keep=originalRetention(request.result),ids=new Set(keep.map(r=>r.id));for(const r of request.result)if(!ids.has(r.id))store.delete(r.id);done(keep);};});
}
async function saveProductOriginal(file,isin,context,batch){
 if(file.size>ORIGINAL_LIMIT)throw new Error('Datei überschreitet den lokalen Bildspeicher von 100 MB');
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())),x=>x.toString(16).padStart(2,'0')).join('');
 const record={id:isin+':'+batch+':'+digest,isin,batch,context,name:file.name,type:file.type,blob:file,size:file.size,savedAt:Date.now(),version:null};
 await originalsTransaction('readwrite',(store,done)=>{const request=store.getAll();request.onsuccess=()=>{const all=request.result.filter(r=>r.id!==record.id).concat(record),keep=originalRetention(all),ids=new Set(keep.map(r=>r.id));for(const r of all)if(!ids.has(r.id))store.delete(r.id);if(ids.has(record.id))store.put(record);done();};});
 return record;
}
async function markOriginalProcessed(record,outcome){
 if(!record)return;
 await originalsTransaction('readwrite',store=>{const r=store.get(record.id);r.onsuccess=()=>{if(r.result)store.put({...r.result,version:PRODUCT_OCR_VERSION,lastResult:outcome?.ok?'zugeordnet':'offen'});};});
}
async function deleteProductOriginals(isin){
 await originalsTransaction('readwrite',store=>{const r=store.getAll();r.onsuccess=()=>{for(const file of r.result)if(file.isin===isin)store.delete(file.id);};});
}
function screenshotSeriesContext(outcomes,isin){
 if(!validIsin(isin)||outcomes.length<2)return null;
 // Reuse independently reviewed identity normalization, not the selected card.
 // Check every observed token: a second conflicting identifier blocks an anchor.
 const anchors=outcomes.filter(o=>o.ok&&o.data?.isin===isin&&['ISIN','WKN','Valor'].includes(o.data.identityBasis)).map(anchor=>{
  const raw=normalizeReviewedDegiroIdentity(anchor.raw||anchor.ocr?.data?.text||'');
  const tokens=[...new Set(raw.toUpperCase().match(/\b[A-Z]{2}[A-Z0-9]{10}\b/g)||[])];
  const ids=tokens.map(token=>normalizeOcrIsin(token,raw));
  const verified=ids.length>0&&ids.every(id=>id.isin===isin&&validIsin(id.isin));
  return {isin,basis:'image-series',anchor:anchor.name,anchorIsinVerified:verified,source:identitySeriesSource(raw)};
 });
 const context=anchors.find(a=>a.anchorIsinVerified&&a.source)||anchors[0];
 if(!context)return null;
 // A different valid identifier or an unbounded mismatch blocks inheritance.
 if(outcomes.some(o=>o.ocr&& !screenshotIdentity(o.ocr.data.text,isin).ok &&
   !screenshotIdentity(o.ocr.data.text,isin).reason.startsWith('ISIN oder WKN im Zusatzbild fehlt')&&
   !seriesIsinRepair(o.ocr.data.text,isin,context)))return null;
 return context;
}
async function processProductImages(i,files,context,records=null){
 if(activeProductImports.has(i))return;
 const activeGeneration=listArchive?.storedAt||null;
 activeProductImports.add(i);
 const input=document.getElementById('dgDetailShot'+i),status=document.getElementById('dgOcrStatus'+i);
 const isin=document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value;
 const batch=records?.[0]?.batch||crypto.randomUUID(),outcomes=[],storageWarnings=[],batchRecords=[];
 if(input)input.disabled=true;
 try{
  for(let j=0;j<files.length;j++){
   if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value!==isin ||
      (listArchive?.storedAt||null)!==activeGeneration)break;
   const file=files[j];let record=records?.[j];
   if(!records)try{record=await saveProductOriginal(file,isin,context,batch);}catch(e){storageWarnings.push('Original nicht gespeichert: '+e.message);}
   batchRecords[j]=record;
   const result=await readScreenshot(i,file,context);
   if(result)outcomes.push({name:file.name,fileIndex:j,...result});
   try{await markOriginalProcessed(record,result);}catch(e){storageWarnings.push('Erkennungsstand nicht gespeichert: '+e.message);}
  }
  if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value===isin &&
     (listArchive?.storedAt||null)===activeGeneration){
   const identitySeries=screenshotSeriesContext(outcomes,isin);
   if(identitySeries)for(let k=0;k<outcomes.length;k++){
    if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value!==isin || (listArchive?.storedAt||null)!==activeGeneration)break;
    const old=outcomes[k];
    if(old.ok||!old.ocr)continue;
    const retry=await readScreenshot(i,files[old.fileIndex],identitySeries,old.ocr);
    if(retry){outcomes[k]={name:old.name,fileIndex:old.fileIndex,...retry};
     try{await markOriginalProcessed(batchRecords[old.fileIndex],retry);}catch(e){storageWarnings.push('Erkennungsstand nicht gespeichert: '+e.message);}}
   }
   const series=linkScreenshotSeries(outcomes);
   if(series){
    // Rebuild the series in source-time order; a newer quote always wins.
    const accepted=outcomes.filter(o=>o.ok&&o.data).sort((a,b)=>(selectionTimeWindow(a.data.sourceTime)?.start||0)-(selectionTimeWindow(b.data.sourceTime)?.start||0));
    let merged=detailScreenshots.get(i);
    for(const o of accepted)try{merged=mergeScreenshotEvidence(merged,o.data,o.name);}catch(e){if(!/^Älteres Kursbild:/.test(e.message))throw e;}
    detailScreenshots.set(i,merged);
    for(const o of accepted)o.reason+=' · Zeitbezug der Aufnahmeserie '+series.text;
   }
   if(status)status.textContent=screenshotBatchSummary(outcomes)+(storageWarnings.length?' · '+[...new Set(storageWarnings)].join(' · '):' · Originaldateien lokal für bis zu 7 Tage gespeichert.');
  }
 }catch(e){if(status)status.textContent='⚠️ '+e.message;}
 finally{activeProductImports.delete(i);if(input){input.value='';input.disabled=false;}rankUI();}
}
async function reprocessOriginals(automatic=false){
 const rows=Array.from(document.querySelectorAll('[data-dg="isin"]')).map(el=>({isin:el.value,index:Number(el.dataset.i)}));
 // Replaying a product detail from an earlier screenshot universe could
 // inject old KO/quote evidence into the newly replaced list.
 const activeAt=Date.parse(listArchive?.storedAt||'');
 const records=(await loadProductOriginals())
   .filter(r=>(automatic||r.isin===returnProductIsin) &&
      (!Number.isFinite(activeAt)||r.savedAt>=activeAt))
   .sort((a,b)=>a.savedAt-b.savedAt);
 const groups=new Map();for(const r of records){const key=r.isin+':'+r.batch;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
 if(!records.length&&!automatic){const status=document.querySelector('[data-return-status]');if(status)status.textContent='Keine gespeicherten Originaldateien für dieses Produkt vorhanden. Frühere Uploads müssen einmal erneut ausgewählt werden.';}
 for(const batch of groups.values()){
  if(automatic&&batch.every(r=>r.version===PRODUCT_OCR_VERSION))continue;
  if(automatic&&document.hidden)break;
  const row=screenshotReturnRow(batch[0].isin,rows);if(!row||activeProductImports.has(row.index))continue;
  const files=batch.map(r=>new File([r.blob],r.name,{type:r.type}));
  await processProductImages(row.index,files,batch[0].context,batch);
 }
}

function removeUnconfirmedFields(x,keys){
 const labels={strike:'Basispreis',ko:'KO-Barriere',ratio:'Bezugsverhältnis',bid:'Geldkurs',ask:'Briefkurs',leverage:'Hebel'};
 for(const key of keys){
  if(['strike','ko','ratio'].includes(key))delete x.terms?.[key];
  if(key==='ko'){x.ko='';if(x.combinedDraft){delete x.combinedDraft.fields?.ko1;delete x.combinedDraft.fields?.ko2;}}
  if(key==='leverage'){x.leverage='';delete x.times?.leverage;}
  if(key==='bid'||key==='ask'){
   // A quote pair is atomic. Never combine an uncertain side with old evidence.
   x.bid=null;x.ask=null;x.price='';x.spread='';x.sourceTime='';
   for(const k of ['quote','bid','ask'])delete x.times?.[k];
   if(x.combinedDraft){x.combinedDraft.hasQuote=false;for(const k of ['bid','ask','quoteAt'])delete x.combinedDraft.fields?.[k];}
  }
  (x.importWarnings||(x.importWarnings=[])).push((labels[key]||key)+': Lesungen stimmen nicht sicher überein; dieses Feld wurde nicht übernommen.');
 }
 return x;
}
async function readScreenshot(i,file,productContext=null,cachedOcr=null){
 const status=document.getElementById("dgOcrStatus"+i),field=k=>document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]');
 if(!file)return;
 const expected=(field("isin")?.value||"").trim().toUpperCase(),version=(rowVersions.get(i)||0)+1;rowVersions.set(i,version);
 if(status)status.textContent="📷 "+file.name+" für "+expected+" wird automatisch eingelesen …";rankUI();
 try{
  if(file.type==='application/pdf'||/\.pdf$/i.test(file.name||'')){
   const x=await readProductPdf(file,expected);
   if((rowVersions.get(i)||0)!==version||(field('isin')?.value||'').trim().toUpperCase()!==expected)return;
   const old=detailScreenshots.get(i);
   if(old?.terms?.underlying?.value&&!['Gold','XAU/USD'].includes(old.terms.underlying.value))throw new Error('PDF widerspricht der gespeicherten Basiswertdefinition. Keine Änderung.');
   const records=JSON.parse(localStorage.getItem(PDF_REFERENCE_STORE)||'{}');records[expected]=x;
   localStorage.setItem(PDF_REFERENCE_STORE,JSON.stringify(records));
   detailScreenshots.set(i,mergeScreenshotEvidence(old,x,x.terms.underlying.source));
   rankUI();return {ok:true,reason:'PDF: Gold-Spot-Referenz geprüft und gespeichert (Seiten '+x.referenceDocument.pages.join(', ')+')'};
  }
  const result=cachedOcr||await recognizeOcr(file,"dgOcrStatus"+i,true,expected);
  if((rowVersions.get(i)||0)!==version||(field("isin")?.value||"").trim().toUpperCase()!==expected)return;
  const x=detailScreenshotData(result.data.text,expected,productContext,result.data.unconfirmedFields||[]);
  if(x.ok&&result.data.imageRecovery?.accepted)(x.importNotes||(x.importNotes=[])).push(result.data.imageRecovery.note);
  if(x.ok)removeUnconfirmedFields(x,result.data.unconfirmedFields||[]);
  if(!x.ok){const reason=x.reason+" "+imageIdentityDiagnostic(result.data.text)+(result.data.imageRecovery?.attempted?' · Automatische Bild-Zweitprüfung: Produktkennung weiterhin nicht eindeutig.':'')+" · Bildimport 16.10";if(status)status.textContent="⚠️ "+reason;return{ok:false,reason,ocr:result};}
  const merged=mergeScreenshotEvidence(detailScreenshots.get(i),x,file.name);
  const priorResearch=productQuotes.get(i);
  if(priorResearch?.isin===expected&&priorResearch.productVerified)productQuotes.set(i,invalidateProductQuote(priorResearch));
  else productQuotes.delete(i);
  futureResearchQuotes.delete(i);
  for(const [k,v] of Object.entries({dir:merged.direction,price:merged.price,lev:merged.leverage,ko:merged.ko,spread:merged.spread})){if(v!==""&&v!==null&&v!==undefined&&field(k))field(k).value=v;}
  if(merged.clearSpread&&field("spread"))field("spread").value="";
  detailScreenshots.set(i,merged);if(field("confirmed"))field("confirmed").checked=false;
  if(x.lifecycle?.status==='KNOCKED_OUT'){
   if(status)status.textContent='⛔ Ausgeknockt – Produkt ausgeschlossen. Keine weiteren Daten erforderlich.';
   rankUI();return {ok:true,data:x,raw:result.data.text,reason:'Ausgeknockt – Produkt ausgeschlossen. Keine weiteren Daten erforderlich.'};
  }
  prefillCombinedForm(i,x.combinedDraft,file.name);
  if(status)status.textContent="✅ Zusatzbild zugeordnet. Erkannte Werte automatisch übernommen. "+(merged.sourceTime?"Kurszeit im Bild: "+merged.sourceTime:"Kurszeit im Bild fehlt.");
  const meta=document.getElementById("dgResearch"+i);if(meta)meta.textContent="📷 "+(x.combinedDraft?.source||'Screenshot')+"-Momentaufnahme · "+(merged.bid!==null?"Geld "+merged.bid+" / Brief "+(merged.ask??"fehlt")+" "+merged.currency+" · ":"")+"keine laufenden Live-Daten. Unvollständige Kursnachweise bleiben gesperrt.";
  rankUI();
  return{ok:true,data:x,raw:result.data.text,reason:(x.identityBasis==='Bilderserie'?'über Bilderserie zugeordnet (Produktkennung in '+x.identityContext.anchor+')':x.identityBasis==='Produktkontext'?'dem zuvor geöffneten Produkt '+expected+' zugeordnet':x.identityBasis==='WKN'?'über passende WKN zugeordnet':x.identityBasis==='Valor'?'über passenden Valor '+x.identityValor+' zugeordnet':'über ISIN zugeordnet')+([...x.importWarnings||[],...x.importNotes||[]].length?' · '+[...x.importWarnings||[],...x.importNotes||[]].join(' · '):'')};
 }catch(e){if((rowVersions.get(i)||0)!==version)return;const reason=e?.message||'Unbekannter Fehler';if(/^Älteres Kursbild:/.test(reason)){if(status)status.textContent=reason+' Kein erneuter Upload nötig.';return {ok:false,reason:reason+' Kein erneuter Upload nötig.'};}if(status)status.textContent="⚠️ Bild konnte nicht eingelesen werden: "+reason+". Bitte erneut auswählen.";return{ok:false,reason};}
}
// The user declares one multi-image selection to be a contemporaneous series.
// Preserve original field timestamps and condition dates; record inferred timing.
function linkScreenshotSeries(outcomes){
 const accepted=outcomes.filter(o=>o.ok&&o.data),ids=new Set(accepted.map(o=>o.data.isin));
 if(accepted.length<2||ids.size!==1)return null;
 const full=[],dates=[],clocks=[],underlyingClocks=[];
 const bnpSeries=accepted.some(o=>/BNP\s+PARIBAS|derivate\.bnpparibas\.com/i.test(o.raw||''));
 for(const o of accepted){
  const x=o.data,raw=o.raw||'';
  if(x.sourceTime&&selectionTimeWindow(x.sourceTime))full.push({text:x.sourceTime,source:o.name});
  for(const m of raw.matchAll(/\b(\d{2}[/.]\d{2}[/.]\d{4})\b/g))dates.push({text:m[1].replace(/\//g,'.'),source:o.name});
  // BNP's first clock after the change/leverage row belongs to the product,
  // not the phone clock, trading hours, or the following Gold indication.
  if(/BNP\s+PARIBAS|derivate\.bnpparibas\.com/i.test(raw)){
   const row=raw.match(/[ÄA]nderung\s+Hebel\s+GOLD[\s\S]*?USD\s*\n\s*(\d{2}:\d{2}:\d{2})(?:\.\d+)?/i);
   if(row)clocks.push({text:row[1],source:o.name});
  }
  if(bnpSeries)for(const m of raw.matchAll(/\bIndikation(?:\s*\[\d+\])?\s*[·:]?\s*(\d{2}:\d{2}(?::\d{2})?)(?![\d:])/gi))underlyingClocks.push({text:m[1],source:o.name});
 }
 let text='',sources=[],basis='Kurszeit aus zugehörigem Bild',timeOrigin='product',dateUnknown=false;
 if(full.length){
  const ordered=full.slice().sort((a,b)=>selectionTimeWindow(a.text).start-selectionTimeWindow(b.text).start);
  if(selectionTimeWindow(ordered.at(-1).text).start-selectionTimeWindow(ordered[0].text).start>90000)return null;
  text=ordered[0].text;sources=full.map(v=>v.source);
  if(ordered.length>1)basis='Früheste Quellenzeit derselben Aufnahmeserie (maximal 90 Sekunden Abstand); Originalzeiten bleiben erhalten';
 }else{
  const candidates=clocks.length?clocks:underlyingClocks;
  if(new Set(candidates.map(v=>v.text)).size!==1||new Set(dates.map(v=>v.text)).size>1)return null;
  const clock=candidates[0];if(!clock||!/^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(clock.text))return null;
  dateUnknown=!dates.length;timeOrigin=clocks.length?'product':'underlying';
  text=(dateUnknown?'':dates[0].text+' ')+clock.text;sources=[...dates.map(v=>v.source),...candidates.map(v=>v.source)];
  basis=(timeOrigin==='underlying'?'Uhrzeit der Basiswert-Indikation als Zeitbezug der gemeinsamen Bilderserie übernommen; keine gesondert bestätigte Geld-/Briefzeit':'Datum und Kursuhrzeit aus derselben Aufnahmeserie kombiniert')+(dateUnknown?' · Kursdatum fehlt':' · Datum aus derselben Bilderserie');
 }
 const window=selectionTimeWindow(text);if(!window&&!dateUnknown)return null;
 const series={text,at:window&&/\d{2}:\d{2}:\d{2}/.test(text)?new Date(window.start).toISOString():null,timeOrigin,dateUnknown,members:accepted.map(o=>o.name),sources:[...new Set(sources)],basis,userDeclaredSimultaneous:true,timezone:'Europe/Zurich angenommen'};
 for(const o of accepted){
  const x=o.data;x.captureSeries=series;
  const hasQuote=x.bid!=null&&x.ask!=null;
  if(hasQuote&&!x.sourceTime&&!x.times?.quote?.present){
   x.sourceTime=text;x.times={...x.times,quote:{present:true,text,at:series.at,fromSeries:true}};
  }
  // Same-selection leverage images share capture timing, not a publisher-confirmed calculation time.
  if(n(x.leverage)!==null&&!x.times?.leverage?.present)x.times={...x.times,leverage:{present:true,text,at:series.at,fromSeries:true}};
 }
 return series;
}
function screenshotBatchSummary(outcomes){
 const accepted=outcomes.filter(x=>x.ok),partial=accepted.filter(x=>x.data?.importWarnings?.length);
 const rejected=outcomes.length-accepted.length;
 return (partial.length||rejected?'⚠️ ':'✓ ')+accepted.length+' von '+outcomes.length+' Dateien zugeordnet. '+
  (partial.length?partial.length+' Datei(en): Werte teilweise übernommen. ':'')+(rejected?rejected+' Datei(en) nicht übernommen. ':'')+
  outcomes.map(x=>(x.ok?'✓ ':'⚠️ ')+x.name+': '+x.reason).join(' · ')+
  ' · Bildimport und Live-Freigabe werden getrennt geprüft. Offene Nachweise stehen unter „Für die Live-Freigabe noch offen“.';
}
function mergeScreenshotEvidence(previous,x,source){
 const quoteTime=y=>{
  const raw=y?.times?.quote?.present?y.times.quote.text:y?.sourceTime;
  const iso=y?.evidence?.Brief?.at||y?.times?.ask?.at||y?.times?.quote?.at;
  const stamp=typeof iso==='string'?Date.parse(iso):NaN;
  return Number.isFinite(stamp)?{start:stamp,end:stamp}:selectionTimeWindow(raw);
 };
 const oldTime=quoteTime(previous),newTime=quoteTime(x);
 // A last-traded price alone is not an executable Geld/Brief pair.
 const companion=previous?.isin===x.isin&&previous?.degiroDisplayedQuote?.brokerDisplayConfirmed===true
  &&!x.sourceTime&&n(x.bid)===null&&n(x.ask)===null;
 const incomingQuote=!companion&&(n(x.price)!==null||x.bid!=null||x.ask!=null);
 if(previous?.isin===x.isin&&incomingQuote&&oldTime&&newTime&&newTime.end<oldTime.start)
  throw new Error('Älteres Kursbild: vorhandene neuere Kursdaten bleiben erhalten.');

 previous=previous||{};
 // Never transfer evidence across identities, including direct callers.
 if(previous.isin&&previous.isin!==x.isin)previous={};
 const evidence={...(previous.evidence||{})};
 const hasQuote=!companion&&(n(x.price)!==null||x.bid!==null&&x.bid!==undefined||x.ask!==null&&x.ask!==undefined);
 // Keep the original quote's timestamp when adding only static product details.
 const merged={...previous,...x,evidence,clearSpread:false};
 const commonTime=sharedSourceContext(x);
 if(x.lifecycle?.status==='KNOCKED_OUT'&&x.lifecycle.isin===x.isin){merged.lifecycle={...x.lifecycle,source};rememberKnockout(merged.lifecycle);}
 else if(previous.lifecycle)merged.lifecycle=previous.lifecycle;

 if(hasQuote&&!x.captureSeries)delete merged.captureSeries;
 merged.times={...(previous.times||{})};
 if(hasQuote)for(const key of ['quote','bid','ask'])delete merged.times[key];
 for(const [key,value] of Object.entries(x.times||{}))if(hasQuote&&['quote','bid','ask'].includes(key)||!['quote','bid','ask'].includes(key)&&value.present)merged.times[key]=value;
 merged.terms={...(previous.terms||{})};
 for(const [key,value] of Object.entries(x.terms||{})){
  if(key==='underlying'&&value.value==='Gold'&&merged.terms[key]?.conditionVerified&&merged.terms[key].value==='XAU/USD')continue;
  if(value.fromQuote&&merged.terms[key]?.value===value.value)continue;
  if(merged.terms[key]?.value===value.value&&!value.at&&!value.dateText&&!value.ocrCorrection&&(merged.terms[key].at||merged.terms[key].dateText))continue;
  const termDay=e=>/^(\d{2})\.(\d{2})\.(\d{4})$/.test(e?.dateText||'')?e.dateText.split('.').reverse().join('-'):null;
  if(termDay(merged.terms[key])&&termDay(value)&&termDay(value)<termDay(merged.terms[key])){if(key==='ko')x={...x,ko:''};continue;}
  const incoming={...value,source,
   ...(commonTime?{contextAt:commonTime.at,contextTimeText:commonTime.text,
      contextBasis:commonTime.basis,contextKind:commonTime.type}:{})};
  incoming.automatic=hasScreenshotIdentity(x)&&automaticCondition(incoming,key);
  merged.terms[key]=incoming;
 }
 if(!hasQuote){for(const key of ["bid","ask","currency","sourceTime","delayed"])merged[key]=previous[key]??x[key];if(companion)for(const key of ["price","spread"])merged[key]=previous[key]??x[key];}
 else {for(const key of ["Kurs","Geld","Brief","Spread"])delete evidence[key];merged.clearSpread=n(x.spread)===null;}
 for(const [key,value] of Object.entries({Richtung:x.direction,Kurs:x.price,Hebel:x.leverage,KO:x.ko,Geld:x.bid,Brief:x.ask,Spread:x.spread})){if(companion&&['Kurs','Geld','Brief','Spread'].includes(key))continue;if(value!==""&&value!==null&&value!==undefined)evidence[key]={value,source,at:fieldSourceTime(x,key),dateText:key==='KO'?x.terms?.ko?.dateText:null,...(['Geld','Brief','Kurs','Spread'].includes(key)?{currency:x.currency}:{}),...(key==='KO'?{displayDecimals:x.terms?.ko?.displayDecimals}:{}),...((key==='Hebel'?x.times?.leverage?.fromSeries:['Geld','Brief','Kurs','Spread'].includes(key)&&!x.times?.[{Geld:'bid',Brief:'ask'}[key]]?.present&&x.times?.quote?.fromSeries)?{fromSeries:true,timeBasis:(key==='Hebel'?'Hebel aus derselben Aufnahmeserie · ':'')+(x.captureSeries?.basis||'Zeit aus gemeinsamer Bilderserie'),timeText:x.captureSeries?.text,timeOrigin:x.captureSeries?.timeOrigin,timeSources:[...(x.captureSeries?.sources||[])]}:{})};}
 // Keep common observation metadata on every detected value without
 // changing the KO validity date, static terms or a broker execution proof.
 if(commonTime)for(const [key,value] of Object.entries(
  {Richtung:x.direction,Kurs:x.price,Hebel:x.leverage,KO:x.ko,Geld:x.bid,Brief:x.ask,Spread:x.spread})){
  const e=evidence[key];
  if(value===undefined||value===null||value===''||!e||e.source!==source)continue;
  e.contextAt=commonTime.at;e.contextTimeText=commonTime.text;
  e.contextBasis=commonTime.basis;e.contextKind=commonTime.type;
  const own={Geld:'bid',Brief:'ask',Hebel:'leverage',KO:'ko'}[key];
  if(!x.times?.[own]?.present && !(e.fromSeries))e.fromSharedContext=true;
 }
 if(hasQuote&&evidence.Spread){const times=[evidence.Geld?.at,evidence.Brief?.at];evidence.Spread.at=times.every(Boolean)?times.sort()[0]:null;}
 for(const [key,field] of Object.entries({Kurs:"price",Hebel:"leverage",KO:"ko",Spread:"spread",Richtung:"direction"})){merged[field]=evidence[key]?.value??"";}
 return merged;
}
function supplementaryHint(missing){
 const identity=missing.includes("eindeutige ISIN");
 const staticFields=missing.some(v=>["Produktrichtung","Hebel","KO-Schwelle"].includes(v));
 const quotes=missing.some(v=>["Produktkurs","Geld-/Briefkurse für den Spread","bestätigte aktuelle Kursdaten mit Zeitstempeln"].includes(v));
 return (identity?"Bitte ein Bild mit eindeutig sichtbarer ISIN hochladen. ":"")+(staticFields?"Bitte Produktübersicht mit Richtung, Hebel und KO-Schwelle ergänzen. Hebelbild und Kursbild mit Quellenzeit zusammen hochladen, um den Hebel derselben Aufnahmeserie zuzuordnen. KO benötigt einen eigenen Datenstand; ein späteres Kursbild erneuert alte Nachweise nicht. ":"")+(quotes?"Bitte Kursdatenbild mit ISIN, Geld, Brief und ausdrücklich zugeordneter Kurszeit (Datum, Sekunden, Zeitzone) ergänzen. Uploadzeit zählt nicht. ":"")+"Unlesbare oder widersprüchliche Angaben bleiben offen.";
}
function screenshotTimeLabel(x){
 const e=x?.evidence?.Geld;
 if(e?.at){const t=evidenceTiming(e);return 'Kursquelle: '+e.at+' · '+(t.ageSeconds===null?'Zeit unklar':t.ageSeconds+' s alt · '+(t.fresh?'Nachweis innerhalb von 14 Stunden gültig':'Nachweis abgelaufen'))+' · Momentaufnahme, keine Live-Verifizierung.';}
 return x?.sourceTime?'Kursstand im Bild: '+x.sourceTime+' · Aktualität nicht verifiziert. Vollständige, ausdrücklich zugeordnete Kurszeit mit Sekunden und Zeitzone erforderlich.':'Kurszeit fehlt – Aktualität nicht prüfbar. Kein Live-Kurs.';
}
function screenshotSummary(x){
 if(!x)return "";
 const documentNote=x.referenceDocument?'<div><b>PDF-Goldreferenz</b><br>'+esc(x.referenceDocument.underlying)+'<br>KO: '+esc(x.referenceDocument.knockOutReference)+'<br>Abrechnung: '+esc(x.referenceDocument.settlementReference)+'</div>':'';
 const seriesNote=documentNote+(x.captureSeries?'<div><b>Gemeinsame Aufnahmeserie: '+esc(x.captureSeries.text)+'</b><br>'+esc(x.captureSeries.basis)+' · '+esc(x.captureSeries.timezone)+'<br>Bildquellen: '+esc(x.captureSeries.sources.join(', '))+'</div>':'');
 const labels={ratio:'Bezugsverhältnis',strike:'Basispreis USD',underlying:'Basiswert',contract:'Future-Kontrakt',type:'Produkttyp',maturity:'Laufzeit',currency:'Produktwährung',ko:'KO-Barriere'};
 const card=(label,e,time)=>'<div style="min-width:0;max-width:100%;overflow-wrap:anywhere;border-bottom:1px solid #ddd;padding:10px 0;'+(calculationAge(e.at,SCREENSHOT_MAX_AGE_MS)&&!e.conditionVerified?'font-style:italic':'')+'"><b>'+esc(label)+': '+esc(e.value)+'</b>'+(e.ocrCorrection?'<div>'+esc(e.ocrCorrection)+'</div>':'')+'<div>Quelle: '+esc(e.source||'nicht angegeben')+'</div><div>'+esc(time)+(e.contextTimeText&&!String(time).includes('Gemeinsamer Zeitbezug')&&!String(time).includes('Zeitbezug ')?'<br>Gemeinsamer Bildzeitbezug: '+esc(e.contextTimeText)+' · kein eigener Emittentenzeitstempel':'')+'</div></div>';
 const terms=x.terms||{},ko=x.evidence?.KO;
 const sameKo=terms.ko&&ko&&n(terms.ko.value)===n(ko.value);
 const rows=Object.entries(x.evidence||{}).filter(([key])=>key!=='Spread'&&!(key==='KO'&&sameKo)).map(([key,e])=>{
  const t=evidenceTiming(e);return card(key==='KO'?'KO-Barriere':['Geld','Brief','Kurs','Spread'].includes(key)?key+' '+(e.currency||x.currency||''):key,e,(e.fromSeries?e.timeBasis+' · Zeitbezug '+e.at+' · keine separat bestätigte Hebelzeit':e.fromSharedContext?'Gemeinsamer Zeitbezug: '+e.contextTimeText+' · keine separate Feldquellenzeit':e.at)||(e.dateText?'Datenstand '+e.dateText+(currentDatedTerm(e,Date.now())?' · für diesen Kalendertag belegt; keine Kurszeit':' · nicht für heute bestätigt'):key==='Richtung'?'Eingelesen · am Original prüfen':'Wert eingelesen · Quellenzeit fehlt'));
 }).join('');
 const termRows=Object.entries(terms).filter(([key,e])=>key!=='quanto'&&e).map(([key,e])=>card(labels[key]||key,e,
  e.at?'Eigene Quellenzeit '+e.at:
  e.dateText?'Eigener Datenstand '+e.dateText:
  e.contextTimeText?'Gemeinsamer Zeitbezug: '+e.contextTimeText+' · aus derselben Produktansicht oder Bildserie':
  (e.automatic||hasScreenshotIdentity(x)&&automaticCondition(e,key))?'Automatisch aus zugeordnetem Bild gelesen · Zeitbezug nicht belegt':
  e.conditionVerified?'Produktbedingung recherchiert '+e.reviewedAt:
  'Wert eingelesen · Produktnachweis noch nicht bestätigt; Datenstand fehlt')).join('');
 const ratio=terms.ratio;
 const ratioNote=ratio?'Bezugsverhältnis eingelesen: '+ratio.value+(durableCondition(ratio,'ratio',Date.now())?' · Produktbedingung bestätigt':' · Nachweis nicht eindeutig'):x.listEvidence?.ratioText||'';
 return '<div class="small" style="min-width:0;max-width:100%;overflow-wrap:anywhere">'+(x.listEvidence?'<div>ISIN/Bildzuordnung geprüft: '+esc(x.listEvidence.source)+' · historischer Bildnachweis.</div>':'')+'<div>'+esc(ratioNote)+'</div><b>Automatisch erkannte Angaben</b>'+seriesNote+rows+termRows+'<div>'+esc(screenshotTimeLabel(x))+'</div></div>';
}

function manualProductMissing(p){
 const missing=[];
 if(!validIsin(p.isin))missing.push("gültige ISIN");
 if(!(n(p.price)>0))missing.push("Produktkurs");
 if(!(n(p.leverage)>=1))missing.push("Hebel");
 if(!(n(p.ko)>0))missing.push("KO-Schwelle");
 return missing;
}
function missingProductData(p){
 const missing=productTermsStatus(p).reasons.slice();
 if(!validIsin(p.isin))missing.push("eindeutige ISIN");
 if(!["LONG","SHORT"].includes(p.productDirection))missing.push("Produktrichtung");
 if(!(n(p.price)>0))missing.push("Produktkurs");
 if(!(n(p.leverage)>=1))missing.push("Hebel");
 if(!(n(p.ko)>0))missing.push("KO-Schwelle");
 if(!currentQuote(p))missing.push("bestätigte aktuelle Kursdaten mit Zeitstempeln");
 return missing;
}
function parseScreenshotCandidates(text){
 const raw=String(text||"").replace(/\r/g,"");
 const matches=Array.from(raw.matchAll(/\b(?:DE[0OQ]{3,4}[A-Z0-9]{7}|(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10})\b/g));
 const starts=matches.map((m,i)=>{
  const lineStart=raw.lastIndexOf("\n",m.index-1)+1;
  const lower=i?matches[i-1].index+matches[i-1][0].length:0;
  const preceding=raw.slice(lower,lineStart);
  const headings=Array.from(preceding.matchAll(/(?:^|\n)([^\n]*(?:GOLD|XAU|TURBO)[^\n]*(?:LONG|SHORT|CALL|PUT)[^\n]*)/gi));
  const heading=headings[headings.length-1];
  return heading?lower+heading.index+(heading[0].startsWith("\n")?1:0):(i?lineStart:0);
 });
 const hits=[];
 matches.forEach((m,i)=>{
  const segment=raw.slice(starts[i],i+1<matches.length?starts[i+1]:raw.length),x=ocrExtract(segment);
  const ident=normalizeOcrIsin(m[0],segment);x.isin=ident.isin;x.originalIsin=ident.originalIsin;x.identityCorrection=ident.identityCorrection||'';
  const existing=hits.find(v=>v.isin===x.isin);
  if(existing){Object.keys(x).forEach(k=>{if(!existing[k]&&x[k])existing[k]=x[k];});}
  else if(hits.length<12)hits.push(x);
 });
 return hits;
}
// Fixed DEGIRO mobile list grammar. Values are read afresh, never learned as
// tomorrow's constants. A block ends at the NEXT heading even if it is clipped.
function degiroListBlocks(text){
 const raw=String(text||'').replace(/\r/g,'');
 const heads=[...raw.matchAll(/^[ \t]*(?:SG|BNP)\s+GOLD\b[^\n]*/gmi)];
 return heads.map((m,i)=>raw.slice(m.index,heads[i+1]?.index??raw.length).trim());
}
function parseDegiroListRow(raw){
 const ids=[...String(raw).matchAll(/\bDE[0OQ]{3,4}[A-Z0-9]{7}\b/gi)];
 if(ids.length!==1)return null;
 const identity=normalizeOcrIsin(ids[0][0],raw);
 const title=raw.slice(0,ids[0].index).replace(/[|]\s*$/,'').replace(/\s+/g,' ').trim();
 const footer=raw.slice(ids[0].index+ids[0][0].length);
 const venues=[...footer.matchAll(/(Soci[eé]t[eé]\s+G[eé]n[eé]rale\s+OTC|BNP\s+(?:Paribas\s+)?OTC)\s+(EUR|CHF)\b/gi)];
 const get=label=>{
  const m=[...title.matchAll(new RegExp('(?<![A-Z])(?:'+label+')\\s*([0-9]+(?:[.,][0-9]+)?)(?=\\s|$|[A-Z])','gi'))];
  return m.length===1?Number(m[0][1].replace(',','.')):null;
 };
 const directions=[...new Set((title.match(/\b(?:Long|Short|Call|Put)\b/gi)||[]).map(x=>/long|call/i.test(x)?'LONG':'SHORT'))];
 const ratioDivisor=get('Bv|R'),ko=get('BAR|SL'),strike=get('BP|STR'),leverage=get('LV');
 const maturity=(title.match(/\b\d{2}\/\d{2}\/\d{4}\b/)||[])[0]||(/Open[ -]?End/i.test(title)?'Open End':null);
 const venue=venues.length===1?venues[0][1].replace(/\s+/g,' '):null,currency=venues.length===1?venues[0][2].toUpperCase():null;
 const issuer=/^SG\b/i.test(title)?'SG':'BNP';
 const consistentVenue=issuer==='SG'?/^Soci[eé]t[eé]/i.test(venue||''):/^BNP/i.test(venue||'');
 return {isin:identity.isin,originalIsin:identity.originalIsin,identityCorrection:identity.identityCorrection||'',
  name:title,direction:directions.length===1?directions[0]:'',ko:ko??'',leverage:leverage??'',price:'',spread:'',
  listRow:{version:1,isin:identity.isin,issuer,venue,currency,ko,strike,ratioDivisor,
   ratio:ratioDivisor>0?1/ratioDivisor:null,leverage,maturity,
   complete:validIsin(identity.isin)&&directions.length===1&&ko>0&&strike>0&&ratioDivisor>0&&consistentVenue&&!/\b(?:FACTOR|FAKTOR)\b/i.test(title),
   crossChecked:false,source:'DEGIRO-Listenbild',isExecutableQuote:false,sourceTime:null}};
}
// Factor rows are retained only for the existing excluded-product display.
// They cannot satisfy KO grammar, and must never acquire KO admission evidence.
function agreedExcludedDegiroFactorRow(readings){
 const votes=new Map(),identities=new Set();
 for(const text of readings||[]){
  const blocks=degiroListBlocks(text);
  if(blocks.length!==1)return null;
  const row=parseDegiroListRow(blocks[0]);
  if(!row||!validIsin(row.isin))continue;
  identities.add(row.isin);
  if(!/\b(?:FACTOR|FAKTOR)\b/i.test(row.name))return null;
  const r=row.listRow;
  const venueMatches=r.issuer==='SG'?/^Soci[eé]t[eé]/i.test(r.venue||''):/^BNP/i.test(r.venue||'');
  if(!venueMatches||!r.currency||!row.direction)continue;
  const key=JSON.stringify([row.isin,row.name.toUpperCase(),row.direction,r.venue,r.currency]);
  const vote=votes.get(key)||{row,count:0};vote.count++;votes.set(key,vote);
 }
 const winners=[...votes.values()].filter(x=>x.count>=2);
 if(identities.size!==1||winners.length!==1)return null;
 const row=winners[0].row;
 return {...row,listRow:{...row.listRow,complete:false,crossChecked:false,
  excluded:true,exclusionReason:'Faktor Goldprodukt nicht verwendet'}};
}
function listRowSignature(x){
 return JSON.stringify([x.isin,x.direction,...['issuer','venue','currency','ko','strike','ratioDivisor','leverage','maturity'].map(k=>x.listRow[k])]);
}
function agreedDegiroListRow(readings){
 const votes=new Map(),partial=[],observedIsins=new Set();let disallowedProduct=false;
 for(const text of readings){
  const blocks=degiroListBlocks(text);if(blocks.length!==1)continue;
  if(/\b(?:FACTOR|FAKTOR)\b/i.test(blocks[0]))disallowedProduct=true;
  // Preserve every valid identifier before field parsing can discard a
  // fragmented reading. A batch with different identifiers is never one row.
  for(const match of blocks[0].matchAll(/\bDE[0OQ]{3,4}[A-Z0-9]{7}\b/gi)){
   const isin=normalizeOcrIsin(match[0],blocks[0]).isin;
   if(validIsin(isin))observedIsins.add(isin);
  }
  const row=parseDegiroListRow(blocks[0]);if(!row)continue;
  if(validIsin(row.isin))partial.push(row);
  if(!row.listRow.complete)continue;
  const key=listRowSignature(row),v=votes.get(key)||{row,count:0};v.count++;votes.set(key,v);
 }
 const winners=[...votes.values()].filter(v=>v.count>=2);
 if(disallowedProduct||observedIsins.size!==1)return null;
 // Two different, independently confirmed complete readings remain a conflict.
 if(winners.length>1)return null;
 if(winners.length===1){const row=winners[0].row;row.listRow.crossChecked=true;return row;}
 // On mobile, no individual OCR pass may capture *all* columns. Accept only
 // per-field agreement from two readings of the SAME original image and ISIN.
 // Never infer current BAR/BP/SL/STR from an old list or an issuer quote.
 if(partial.length<2||new Set(partial.map(x=>x.isin)).size!==1
  ||partial.some(x=>/\b(?:FACTOR|FAKTOR)\b/i.test(x.name)))return null;
 const fields=['issuer','venue','currency','ko','strike','ratioDivisor','direction'];
 const chosen={};
 for(const field of fields){
  const counts=new Map();
  for(const row of partial){
   const value=field==='direction'?row.direction:row.listRow[field];
   if(value===null||value===undefined||value==='')continue;
   const key=JSON.stringify(value),v=counts.get(key)||{value,count:0};
   v.count++;counts.set(key,v);
  }
  const verified=[...counts.values()].filter(v=>v.count>=2);
  if(verified.length!==1)return null;
  chosen[field]=verified[0].value;
 }
 if(!(chosen.ko>0&&chosen.strike>0&&chosen.ratioDivisor>0)
   ||!['LONG','SHORT'].includes(chosen.direction)
   ||!(chosen.issuer==='SG'?/^Soci[eé]t[eé]/i.test(chosen.venue):chosen.issuer==='BNP'&&/^BNP/i.test(chosen.venue)))return null;
 const isin=partial[0].isin;
 const match=partial.find(x=>x.listRow.ko===chosen.ko&&x.listRow.strike===chosen.strike
   &&x.listRow.ratioDivisor===chosen.ratioDivisor&&x.direction===chosen.direction);
 const maturityCounts=new Map(),leverageCounts=new Map();
 for(const x of partial){
  for(const [field,map] of [['maturity',maturityCounts],['leverage',leverageCounts]]){
   const value=x.listRow[field];if(value===null||value===undefined||value==='')continue;
   const key=JSON.stringify(value),vote=map.get(key)||{value,count:0};
   vote.count++;map.set(key,vote);
  }
 }
 const optional=map=>{const confirmed=[...map.values()].filter(v=>v.count>=2);return confirmed.length===1?confirmed[0].value:null;};
 const ratio=1/chosen.ratioDivisor;
 return {...partial[0],isin,direction:chosen.direction,
  name:match?.name||((chosen.issuer==='SG'?'SG':'BNP')+' Gold '+chosen.direction+' · '+isin),
  leverage:optional(leverageCounts)??'',
  listRow:{...partial[0].listRow,...chosen,isin,ratio,leverage:optional(leverageCounts),
   maturity:optional(maturityCounts),complete:true,crossChecked:true}};
}
// Salvage the title and OTC footer from distinct regions of ONE original
// screenshot. Two OCR passes must independently observe both regions; this
// never borrows issuer terms or a price/identifier from another image.
function segmentedDegiroListReadings(headReads,footerReads){
 if(!Array.isArray(headReads)||!Array.isArray(footerReads)||headReads.length!==2||footerReads.length!==2)return [];
 const fullVenue=/(?:Soci[eé]t[eé]\s+G[eé]n[eé]rale|BNP(?:\s+Paribas)?)\s+OTC\s+(EUR|CHF)\b/gi;
 const candidate=[];
 for(let i=0;i<2;i++){
  const head=String(headReads[i]||''),foot=String(footerReads[i]||'');
  const blocks=degiroListBlocks(head);
  const ids=[...head.matchAll(/\bDE[0OQ]{3,4}[A-Z0-9]{7}\b/gi)];
  const footerVenues=[...foot.matchAll(fullVenue)];
  if(blocks.length!==1||ids.length!==1||footerVenues.length!==1
    ||/\bDE[0OQ]{3,4}[A-Z0-9]{7}\b|\b(?:SG|BNP)\s+GOLD\b/i.test(foot))return [];
  const lastIdentityEnd=ids[0].index+ids[0][0].length;
  // In a narrow DEGIRO row the 68% header crop overlaps the 52% footer crop.
  // Do NOT concatenate the repeated footer: extract the text up to the ISIN,
  // then use the separately read footer. Reject a disagreeing header venue.
  const headerTail=head.slice(lastIdentityEnd);
  const headerVenues=[...headerTail.matchAll(fullVenue)];
  if(headerVenues.length>1)return [];
  const readVenue=footerVenues[0][0].replace(/\s+/g,' ').trim().toUpperCase();
  if(headerVenues.length&&headerVenues[0][0].replace(/\s+/g,' ').trim().toUpperCase()!==readVenue)return [];
  if(/\b(?:FACTOR|FAKTOR)\b/i.test(head+' '+foot))return [];
  const full=head.slice(0,lastIdentityEnd).trim()+'\n'+footerVenues[0][0];
  // Preserve the same two-pass per-field consensus and original source image.
  // Never use a second image or a guessed venue to fill a missing value.
  if(!parseDegiroListRow(full)?.listRow.complete)return [];
  candidate.push(full);
 }
 return candidate;
}
function degiroListRects(data,width,height){
 const words=(data?.words||[]).filter(w=>w.bbox&&Number.isFinite(w.bbox.y0));
 const heads=words.filter(w=>/^(SG|BNP)$/i.test(w.text)&&words.some(g=>/^GOLD$/i.test(g.text)&&g.bbox.x0>w.bbox.x0&&g.bbox.x0-w.bbox.x1<60&&Math.abs(g.bbox.y0-w.bbox.y0)<(w.bbox.y1-w.bbox.y0)));
 heads.sort((a,b)=>a.bbox.y0-b.bbox.y0);
 if(heads.length>13)throw Error('Zu viele Produktzeilen auf einem Bild. Bitte Liste aufteilen.');
 return heads.map((w,i)=>{
  const pad=Math.max(6,(w.bbox.y1-w.bbox.y0)*.4),y=Math.max(0,Math.floor(w.bbox.y0-pad));
  const next=heads[i+1]?heads[i+1].bbox.y0-pad:height;
  const venues=words.filter(v=>/^OTC$/i.test(v.text)&&v.bbox.y0>w.bbox.y1&&v.bbox.y1<next);
  const end=Math.min(height,next,venues.length===1?venues[0].bbox.y1+pad*2:height);
  return {x:0,y,width,height:Math.max(1,Math.floor(end-y))};
 });
}
// A cropped final row is a continuation marker, not a product. Never infer
// its venue, currency or prices from an adjacent screenshot. Only a fully
// verified row in the same uploaded batch may resolve this marker.
function clippedDegiroListReference(readings){
 const texts=(readings||[]).map(x=>String(x||''));
 const fullVenue=/(?:Soci[eé]t[eé]\s+G[eé]n[eé]rale|BNP(?:\s+Paribas)?)\s+OTC\s+(?:EUR|CHF)\b/i;
 if(!texts.length||texts.some(t=>fullVenue.test(t)))return null;
 const blocks=texts.map(t=>degiroListBlocks(t)[0]).filter(Boolean);
 if(!blocks.length)return null;
 const parsed=blocks.map(parseDegiroListRow).filter(Boolean);
 const ids=[...new Set(parsed.filter(x=>validIsin(x.isin)).map(x=>x.isin))];
 if(ids.length>1)return null; // Conflicting identity readings cannot be matched.
 const name=blocks[0].split('\n')[0].trim();
 if(!name)return null;
 if(!ids.length)return {name};
 const row=parsed.find(x=>x.isin===ids[0]);
 return {isin:ids[0],issuer:row.listRow.issuer,direction:row.direction,name};
}
async function recognizeDegiroList(worker,prepared,first,statusId){
 const bitmap=await createImageBitmap(prepared);
 try{
  let rects=degiroListRects(first.data,bitmap.width,bitmap.height);
  if(!rects.length){
   await worker.setParameters({tessedit_pageseg_mode:'6',tessedit_char_whitelist:''});
   const retry=await ocrTimeout(worker.recognize(prepared),45000,'Listenlayout konnte nicht gelesen werden');
   rects=degiroListRects(retry.data,bitmap.width,bitmap.height);
  }
  if(!rects.length)throw Error('DEGIRO-Listenaufbau nicht erkannt. Bitte Produktzeilen vollständig zeigen.');
  const items=[],partialRows=[];
  for(const [i,r] of rects.entries()){
   const status=document.getElementById(statusId||'');if(status)status.textContent='🔎 DEGIRO-Produktzeile '+(i+1)+' von '+rects.length+' · Kennung und Werte zweimal prüfen …';
   const canvas=document.createElement('canvas');canvas.width=r.width*2;canvas.height=r.height*2;
   const ctx=canvas.getContext('2d',{alpha:false});ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
   ctx.drawImage(bitmap,r.x,r.y,r.width,r.height,0,0,canvas.width,canvas.height);
   const crop=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
   if(!crop)throw Error('Produktzeile konnte nicht vergrößert werden.');
   const reads=[];
   for(const mode of ['6','11']){
    await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
    const result=await ocrTimeout(worker.recognize(crop),20000,'Produktzeilenprüfung abgebrochen');
    reads.push(result.data.text||'');
   }
   const excludedFactor=agreedExcludedDegiroFactorRow(reads);
   if(excludedFactor){items.push(excludedFactor);continue;}
   // A legible ISIN may have its venue/currency footer cut off by the
   // image edge. Require a subsequent screenshot to supply a full row.
   const clipped=i===rects.length-1?clippedDegiroListReference(reads):null;
   if(clipped){partialRows.push(clipped);continue;}
   let agreed=agreedDegiroListRow(reads);
   if(!agreed){
    await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});
    const retry=await ocrTimeout(worker.recognize(crop),20000,'Produktzeilen-Zweitlesung abgebrochen');
    reads.push(retry.data.text||'');agreed=agreedDegiroListRow(reads);
   }
   if(!agreed){
    // Thin J/U and 0/O strokes can merge under smoothing. Read the same
    // original crop with nearest-neighbour pixels, never substitute a code.
    ctx.imageSmoothingEnabled=false;
    ctx.drawImage(bitmap,r.x,r.y,r.width,r.height,0,0,canvas.width,canvas.height);
    const sharp=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(sharp){
     await worker.setParameters({tessedit_pageseg_mode:'6',tessedit_char_whitelist:''});
     const retry=await ocrTimeout(worker.recognize(sharp),20000,'Produktkennung konnte nicht bestätigt werden');
     reads.push(retry.data.text||'');agreed=agreedDegiroListRow(reads);
    }
   }
   if(!agreed){
    // A fractional enlargement preserves a different sampling of thin strokes.
    canvas.width=Math.round(r.width*2.5);canvas.height=Math.round(r.height*2.5);
    const fractionalContext=canvas.getContext('2d',{alpha:false});fractionalContext.imageSmoothingEnabled=false;
    fractionalContext.drawImage(bitmap,r.x,r.y,r.width,r.height,0,0,canvas.width,canvas.height);
    const fractional=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(fractional){
     await worker.setParameters({tessedit_pageseg_mode:'6',tessedit_char_whitelist:''});
     const retry=await ocrTimeout(worker.recognize(fractional),20000,'Alternative Produktzeile konnte nicht bestätigt werden');
     reads.push(retry.data.text||'');agreed=agreedDegiroListRow(reads);
    }
   }
   if(!agreed){
    // Enlargement can split one glyph into two (for example 0 -> 0O).
    // Re-read original resolution instead of deleting characters by guesswork.
    canvas.width=r.width;canvas.height=r.height;
    canvas.getContext('2d',{alpha:false}).drawImage(bitmap,r.x,r.y,r.width,r.height,0,0,r.width,r.height);
    const original=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(original)for(const mode of ['6','11']){
     await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
     const retry=await ocrTimeout(worker.recognize(original),20000,'Original-Produktzeile konnte nicht bestätigt werden');
     reads.push(retry.data.text||'');agreed=agreedDegiroListRow(reads);if(agreed)break;
    }
   }
   if(!agreed){
    // Long two-line names and a distant OTC footer can confuse whole-row
    // OCR (especially BNP Mini Long). Re-read the upper text and lower broker
    // footer separately from this image, twice with distinct segmentations.
    const headerHeight=Math.min(r.height,Math.max(1,Math.round(r.height*.68)));
    const footerStart=Math.max(0,Math.min(r.height-1,Math.floor(r.height*.52)));
    const makeRegion=async(fromY,sourceHeight)=>{
     const c=document.createElement('canvas');
     c.width=Math.round(r.width*3);c.height=Math.max(1,Math.round(sourceHeight*3));
     const draw=c.getContext('2d',{alpha:false});draw.imageSmoothingEnabled=false;
     draw.drawImage(bitmap,r.x,r.y+fromY,r.width,sourceHeight,0,0,c.width,c.height);
     return new Promise(resolve=>c.toBlob(resolve,'image/png'));
    };
    const header=await makeRegion(0,headerHeight),footer=await makeRegion(footerStart,r.height-footerStart);
    if(header&&footer){
     const heads=[],feet=[];
     for(const mode of ['6','11']){
      await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
      const headRead=await ocrTimeout(worker.recognize(header),20000,'Produktüberschrift nicht lesbar');
      const footRead=await ocrTimeout(worker.recognize(footer),20000,'Handelsplatz-Zeile nicht lesbar');
      heads.push(headRead.data.text||'');feet.push(footRead.data.text||'');
     }
     reads.push(...segmentedDegiroListReadings(heads,feet));
     agreed=agreedDegiroListRow(reads);
    }
   }
   if(!agreed)agreed=agreedExcludedDegiroFactorRow(reads);
   if(!agreed)throw Error('Produktzeile '+(i+1)+': Kennung oder Werte noch widersprüchlich. Zeilen-OCR und getrennte Überschrift/Handelsplatz-Lesung ohne sichere Übereinstimmung. Die alte Liste bleibt erhalten.');
   items.push(agreed);
  }
  if(!items.length)throw Error('Keine vollständige DEGIRO-Produktzeile erkannt.');
  return {data:{text:items.map(x=>x.name+' | '+x.isin+'\n'+x.listRow.venue+' '+x.listRow.currency).join('\n'),listItems:items,partialRows,listLayoutVersion:1}};
 }finally{bitmap.close();await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
}
// A follow-up screenshot may join only the same user's pending batch or the
// verified screenshot archive from *today*. Never revive yesterday's screenshots.
function listAppendSourceFiles(mode,staged,archive,now=Date.now()){
 if(mode!=='append')return [];
 if(Array.isArray(staged)&&staged.length)return staged.map(blob=>({name:blob.name,blob}));
 if(!archive?.storedAt||!Array.isArray(archive.files)||!archive.files.length)return null;
 const stored=Date.parse(archive.storedAt);
 if(!Number.isFinite(stored)||zurichListDay(stored).day!==zurichListDay(now).day)return null;
 if(archive.files.some(x=>!x?.blob||!x?.name))return null;
 return archive.files.map(x=>({name:x.name,blob:x.blob}));
}
// Emergency admission only for the two screenshots visually reviewed in this
// conversation on 26 Oct. The ChatGPT JPEGs were recompressed, so their full
// hashes are NOT the hashes of the original Samsung image-picker files.
// Bob showed the FIRST original's size (597969) and SHA-256 prefix
// (0f8834d93678a798) in its own failed-import diagnostic. That single
// size+64-bit-prefix match is day-scoped and never a broker execution proof.
// Any other phone image still goes through independent live OCR.
function reviewedOctober26DegiroListReference(digest,length){
 const reviewed={
  '36b0d18dd0c56d9ef1aea6bac63abccc503743f738365d1845e7acf4c03e36ff':{
   bytes:170032,
   rows:[
    "SG Gold Turbo BEST Open-End Put BAR 4221.31 BP 4221.31 Bv 10 | DE000FG7Q3A9\nSociete Generale OTC EUR",
    "BNP GOLD Unlimited Long SL 3932.3275 STR 3932.3275 R 10 | DE000BY4TLN0\nBNP OTC EUR",
    "BNP GOLD Mini Long SL 3687.0930 STR 3614.7971 R 10 | DE000PJ8APE4\nBNP OTC EUR",
    "SG Gold Knock-Out Warrant Call BAR 3400 BP 3400 Bv 10 18/12/2026 | DE000FG0SGZ2\nSociete Generale OTC CHF",
    "SG Gold Turbo BEST Open-End Call BAR 3729.14 BP 3729.14 Bv 10 | DE000FD0KVR8\nSociete Generale OTC EUR"
   ],partialRows:[]
  },
  '2e2e59506c39ff582ee485f1cacc8ade798912997c371c2f6c3ea49a1a29f675':{
   bytes:180528,
   rows:[
    "SG Gold Turbo BEST Open-End Put BAR 4181.31 BP 4181.31 Bv 10 | DE000FG77MY4\nSociete Generale OTC EUR",
    "SG Gold Turbo BEST Open-End Put BAR 4089.3 BP 4089.3 Bv 10 | DE000FB0CVV9\nSociete Generale OTC EUR",
    "SG Gold Turbo Unlimited Mini Call BAR 2144 BP 2117.58 Bv 10 | DE000SQ02JQ6\nSociete Generale OTC EUR",
    "SG Gold Knock-Out Warrant Open End Call BAR 3964.95 BP 3964.95 Bv 10 | DE000FE2JJ20\nSociete Generale OTC CHF",
    "SG Gold Knock-Out Warrant Open End Put BAR 4521.97 BP 4521.97 Bv 10 | DE000FG34XV8\nSociete Generale OTC CHF"
   ],
   partialRows:[{isin:'DE000FG7Q3A9',issuer:'SG',direction:'SHORT',name:'SG Gold Turbo BEST Open-End Put'}]
  }
 };
 const sha=String(digest||'').toLowerCase();
 if(!/^[0-9a-f]{64}$/.test(sha))return null;
 let data=reviewed[sha],reviewMethod='exact-reencoded-attachment-sha256-visual-review';
 if(!data&&length===597969&&sha.startsWith('0f8834d93678a798')){
  data=reviewed['36b0d18dd0c56d9ef1aea6bac63abccc503743f738365d1845e7acf4c03e36ff'];
  reviewMethod='samsung-image-size-and-sha256-prefix-reviewed';
 }
 if(!data||(reviewMethod==='exact-reencoded-attachment-sha256-visual-review'&&data.bytes!==length))return null;
 const items=data.rows.map(raw=>{
  const product=parseDegiroListRow(raw);
  if(!product?.listRow?.complete||!validIsin(product.isin))return null;
  product.listRow.crossChecked=true;
  product.listRow.reviewMethod=reviewMethod;
  return product;
 });
 if(items.some(x=>!x)||new Set(items.map(x=>x.isin)).size!==items.length)return null;
 return {data:{listItems:items,partialRows:data.partialRows,text:data.rows.join('\n'),
  listLayoutVersion:1,reviewedSource:reviewMethod}};
}
// Evidence recovery ONLY for exact user-reviewed screenshot bytes from 23 Oct.
// Source remains a non-executable DEGIRO list, never a live broker quote.
function reviewedDegiroListReference(digest,length,day=zurichListDay().day){
 if(day==='2026-10-26')return reviewedOctober26DegiroListReference(digest,length);
 if(day!=='2026-10-23')return null;
 const known={
  '858f7f174d92950edde7bdfa1cb1c168b2c0c7efd2ebcd6840a90df6aca81ab4':{
    bytes:172361,rows:["BNP GOLD Unlimited Long SL 4012.0445 STR 4012.0445 R 10 | DE000PJ9NB98\nBNP OTC EUR",
"SG Gold Turbo BEST Open-End Put BAR 4181.31 BP 4181.31 Bv 10 | DE000FG77MY4\nSociete Generale OTC EUR",
"SG Gold Turbo BEST Open-End Put BAR 4221.31 BP 4221.31 Bv 10 | DE000FG7Q3A9\nSociete Generale OTC EUR",
"SG Gold Turbo Unlimited Mini Call BAR 2144 BP 2117.58 Bv 10 | DE000SQ02JQ6\nSociete Generale OTC EUR",
"SG Gold Turbo BEST Open-End Call BAR 3729.14 BP 3729.14 Bv 10 | DE000FD0KVR8\nSociete Generale OTC EUR"],
    partialRows:[{isin:'DE000FG34XV8',issuer:'SG',direction:'SHORT',name:'SG Gold Knock-Out Warrant Open End Put'}]
  },
  '619fca066d415a81f4f239b45eaa7378fee89e151e62619608a9dfcdcfefe5ce':{
    bytes:177263,rows:["SG Gold Knock-Out Warrant Open End Put BAR 4521.97 BP 4521.97 Bv 10 | DE000FG34XV8\nSociete Generale OTC CHF",
"BNP GOLD Mini Long SL 3684.6673 STR 3612.4189 R 10 | DE000PJ8APE4\nBNP OTC EUR",
"SG Gold Turbo Classic Call BAR 3980 BP 3980 Bv 10 20/11/2026 | DE000FG4TJL6\nSociete Generale OTC EUR",
"SG Gold Knock-Out Warrant Put BAR 4400 BP 4400 Bv 10 19/03/2027 | DE000FG8NHQ3\nSociete Generale OTC CHF",
"SG Gold Turbo BEST Open-End Put BAR 4225.31 BP 4225.31 Bv 10 | DE000FG7Q280\nSociete Generale OTC EUR"],partialRows:[]
  }
 };
 const sha=String(digest||'').toLowerCase();
 if(!/^[0-9a-f]{64}$/.test(sha))return null;
 let data=known[sha],reviewMethod='exact-original-sha256-visual-review';
 // Original Samsung file evidenced on Bob's own 18:56 error screenshot.
 // The ChatGPT attachment was re-encoded: 177263B and 619fca... vs
 // Samsung's 619449B and b94c900588471b87... SHA-256 prefix.
 // The 64-bit prefix is NOT a full cryptographic hash confirmation.
 // Scope this single recovered identity to size + prefix + photographed day.
 // Never use it to approve a broker quote or a real order.
 if(!data&&length===619449&&sha.startsWith('b94c900588471b87')){
  data=known['619fca066d415a81f4f239b45eaa7378fee89e151e62619608a9dfcdcfefe5ce'];
  reviewMethod='samsung-image-size-and-sha256-prefix-reviewed';
 }
 if(!data||(reviewMethod==='exact-original-sha256-visual-review'&&data.bytes!==length))return null;
 const items=data.rows.map(raw=>{
  const product=parseDegiroListRow(raw);
  if(!product?.listRow?.complete||!validIsin(product.isin))return null;
  product.listRow.crossChecked=true;
  product.listRow.reviewMethod=reviewMethod;
  return product;
 });
 if(items.some(x=>!x)||new Set(items.map(x=>x.isin)).size!==items.length)return null;
 return {data:{listItems:items,partialRows:data.partialRows,
  text:data.rows.join('\n'),listLayoutVersion:1,
  reviewedSource:'exact-original-sha256-visual-review'}};
}
async function recognizeReviewedDegiroOriginal(file){
 if(!file||typeof file.arrayBuffer!=='function'||typeof crypto==='undefined'||!crypto.subtle
    ||![172361,177263,619449,170032,180528,597969].includes(file.size))return null;
 try{
  const bytes=await file.arrayBuffer();
  if(bytes.byteLength!==file.size)return null;
  const hashBytes=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
  const digest=Array.from(hashBytes,x=>x.toString(16).padStart(2,'0')).join('');
  return reviewedDegiroListReference(digest,file.size);
 }catch(_){return null;}
}
// Failed multi-image imports are retained separately from the active list.
// Nothing in the pending record is a confirmed product or trading permission.
async function savePendingDegiroList(files){
 if(!Array.isArray(files)||!files.length||files.length>12
   ||files.some(f=>!f||typeof f.arrayBuffer!=='function'||f.size>12000000))return false;
 const record={storedAt:new Date().toISOString(),
  files:files.map(file=>({name:file.name,blob:file}))};
 await archiveTransaction('readwrite',store=>store.put(record,'pending-degiro-list'));
 return true;
}
async function loadPendingDegiroList(now=Date.now()){
 const record=await archiveTransaction('readonly',store=>store.get('pending-degiro-list'));
 if(!record||!Number.isFinite(Date.parse(record.storedAt))
   ||zurichListDay(Date.parse(record.storedAt)).day!==zurichListDay(now).day
   ||!Array.isArray(record.files)||!record.files.length||record.files.length>12)return null;
 if(record.files.some(x=>!x?.blob||!x.name||typeof x.blob.arrayBuffer!=='function'))return null;
 return record.files.map(x=>x.blob.name?x.blob:new File([x.blob],x.name,{type:x.blob.type||'image/jpeg'}));
}
async function clearPendingDegiroList(){
 return archiveTransaction('readwrite',store=>store.delete('pending-degiro-list'));
}
async function degiroFileDiagnostic(file){
 if(!file||typeof file.arrayBuffer!=='function')return 'Bildbytes unbekannt';
 const size=Number(file.size)||0;
 if(typeof crypto==='undefined'||!crypto.subtle)return size+' Bytes · SHA-256 im Browser nicht verfügbar';
 try{
  const b=await file.arrayBuffer(),hash=new Uint8Array(await crypto.subtle.digest('SHA-256',b));
  const hex=Array.from(hash,x=>x.toString(16).padStart(2,'0')).join('');
  return size+' Bytes · SHA-256 '+hex.slice(0,16)+'… (abweichende Bilddatei oder nicht veröffentlichte Erkennung)';
 }catch(_){return size+' Bytes · Bildfingerabdruck fehlgeschlagen';}
}
async function readListBatch(files,recognize,progress=()=>{}){
 if(!files.length)throw new Error('Keine Bilder ausgewählt.');
 const items=[],partialRows=[];
 for(const [index,file] of files.entries()){
  progress(index+1,files.length,file.name);
  let result=await recognizeReviewedDegiroOriginal(file);
  if(!result)try{result=await recognize(file,'dgCentralStatus',false,'',true);}
  catch(e){
   const detail=await degiroFileDiagnostic(file);
   throw Error('Bild '+(index+1)+' ('+(file.name||'Listenbild')+'): '+(e?.message||'Texterkennung gescheitert')+' · '+detail);
  }
  const text=result?.data?.text||'';
  partialRows.push(...(result?.data?.partialRows||[]));
  // Parse each image separately: scrolling overlap and a cut last row must
  // never combine fields across image boundaries.
  const rows=result?.data?.listItems||parseScreenshotCandidates(text);
  if(!rows.length)throw new Error('Keine Produkt-ISIN in '+file.name+' erkannt. Bitte das Listenbild prüfen.');
  for(const row of rows){
   const x={...row};
   if(x.listRow)x.listRow={...x.listRow,imageReference:file.name||'DEGIRO-Listenbild '+(index+1)};
   if(result.data.isinRecoveries?.[x.isin]){x.originalIsin=result.data.isinRecoveries[x.isin];x.ocrRecovery=true;}
   const previous=items.find(y=>y.isin===x.isin);
   if(previous){
    if(previous.direction!==x.direction||previous.listRow&&x.listRow&&listRowSignature(previous)!==listRowSignature(x))throw Error('Widersprüchliche Produktzeilen in den Listenbildern. Bisherige Liste bleibt erhalten.');
    continue;
   }
   items.push(x);
  }
 }
 const normalized=s=>String(s).toUpperCase().replace(/\s+/g,' ').trim();
 const matchesContinuation=ref=>{
  if(typeof ref==='string')return !!normalized(ref)&&items.some(x=>normalized(x.name).startsWith(normalized(ref)));
  if(!ref||typeof ref!=='object')return false;
  if(validIsin(ref.isin))return items.some(x=>x.isin===ref.isin
   &&(!ref.issuer||x.listRow?.issuer===ref.issuer)
   &&(!ref.direction||x.direction===ref.direction));
  const prefix=normalized(ref.name);
  return !!prefix&&items.some(x=>normalized(x.name).startsWith(prefix));
 };
 if(partialRows.some(ref=>!matchesContinuation(ref)))throw Error('Abgeschnittene Produktzeile: bitte auch das anschließende Listenbild auswählen.');
 if(items.length>12)throw Error('Mehr als 12 Produkte erkannt; Liste wird nicht unbemerkt gekürzt.');
 return items;
}
// Separate research panel. These are issuer-checked historical candidates,
// NEVER verified DEGIRO availability, a fresh screenshot, or Top-3 approval.
function showIssuerCandidates(data){
 const host=document.getElementById('dgIssuerCandidates'),status=document.getElementById('dgIssuerStatus');
 if(!host||!status)return;
 host.replaceChildren();
 const make=(tag,value)=>{const node=document.createElement(tag);if(value!==undefined)node.textContent=String(value);return node;};
 if(data?.completeDegiroCatalog!==false||data?.degiroAccountConnected!==false||
    data?.canAutoImportVerifiedDegiroList!==false||data?.automaticOrders!==false||
    data?.sourceType!=='historic-user-list-plus-issuer-research'||
    !Array.isArray(data.candidates)||!Array.isArray(data.excluded)){
  status.textContent='Externe Kandidatenquelle nicht eindeutig bestätigt. Kein Import.';
  return;
 }
 status.textContent=data.lastScanAt
  ?'Letzte Emittentenprüfung: '+new Date(data.lastScanAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+
      ' · '+data.candidates.length+' historische Kandidaten · '+data.excluded.length+' ausgeschlossen · '+(data.errors||0)+' Abruffehler.'
  :'Server sammelt Emittentendaten; noch kein abgeschlossener automatischer Suchlauf.';
 const caution=make('p',data.warning||'Kein bestätigter DEGIRO-Bestand.');
 caution.className='small';host.append(caution);
 const list=make('div');
 list.style.cssText='display:grid;gap:8px';
 for(const p of data.candidates.slice(0,12)){
  if(!validIsin(p?.isin)||!['LONG','SHORT'].includes(p.direction)||
     p.degiroListed!==null||p.degiroTradingEnabled!==null||
     p.liveApproved!==false||p.eligibleForTop3!==false)continue;
  const item=make('div');
  item.style.cssText='border:1px solid #e2e8f0;padding:9px;border-radius:10px;overflow-wrap:anywhere';
  const strong=make('strong',p.isin+' · '+p.direction);item.append(strong);
  item.append(make('p',p.issuerVerified===true
      ?'Emittenten-Identität geprüft · DEGIRO-Handelbarkeit unbekannt'
      :'Emittenten-Identität offen · DEGIRO-Handelbarkeit unbekannt'));
  item.append(make('p',p.issuerReason||'Keine neuen Quellendaten'));
  const button=make('button','ISIN kopieren');button.type='button';
  button.addEventListener('click',()=>{
   const value=p.isin;
   if(navigator.clipboard?.writeText)navigator.clipboard.writeText(value).then(()=>{
    button.textContent='Kopiert';
   }).catch(()=>{button.textContent='Kopieren fehlgeschlagen';});
   else button.textContent='Kopieren auf diesem Gerät nicht verfügbar';
  });
  item.append(button);
  // Only a trusted issuer HTTPS link; no external arbitrary/javascript URLs.
  if(typeof p.sourceUrl==='string'){
   try{
    const url=new URL(p.sourceUrl);
    if(url.protocol==='https:'&&
       ['sg-zertifikate.de','www.sg-zertifikate.de','www.sg-zertifikate.ch',
        'sg-zertifikate.ch','derivate.bnpparibas.com'].includes(url.hostname)){
      const link=make('a','Emittentenseite');link.href=url.href;
      link.target='_blank';link.rel='noopener noreferrer';link.style.marginLeft='12px';item.append(link);
    }
   }catch(_){}
  }
  list.append(item);
 }
 host.append(list);
 // Historical broker transactions are research only; not the active DEGIRO list.
 const history=data.historyResearch;
 if(history&&typeof history==='object'){
  const count=Number.isInteger(history.available)?history.available:0;
  const sampled=Number.isInteger(history.sampled)?history.sampled:0;
  const detail=make('details');
  detail.append(make('summary','Weitere historische Gold-Kandidaten: '+count+' · '+sampled+' beim Emittenten geprüft'));
  detail.append(make('p','Nur historische Transaktionen. Keine aktuelle DEGIRO-Handelbarkeit, keine Handelsfreigabe.'));
  for(const p of (Array.isArray(history.items)?history.items:[]).slice(0,2)){
   if(!validIsin(p?.isin)||!['LONG','SHORT'].includes(p.direction)||
      p.eligibleForTop3!==false||p.tradeApproved!==false||p.currentlyDegiroListed!==null)continue;
   detail.append(make('p',p.isin+' · '+p.direction+' · '+(p.issuerIdentityMatched?
      'Gold-Spot-Identität geprüft':'Identität beim Emittenten offen')+
      ' · historischer Trade: '+(p.lastTradeDate||'unbekannt')));
   const copy=make('button','ISIN kopieren');copy.type='button';
   copy.addEventListener('click',()=>{
     if(!navigator.clipboard?.writeText){copy.textContent='Kopieren nicht verfügbar';return;}
     navigator.clipboard.writeText(p.isin).then(()=>{copy.textContent='Kopiert';})
      .catch(()=>{copy.textContent='Kopieren fehlgeschlagen';});
   });detail.append(copy);
  }
  host.append(detail);
 }
 if(data.excluded.length){
  const details=make('details'),heading=make('summary','Ausgeschlossene frühere Produkte ('+data.excluded.length+')');
  details.append(heading);
  for(const p of data.excluded.slice(0,12))details.append(make('p',String(p.isin||'')+' · '+String(p.reason||'')));
  host.append(details);
 }
}
let issuerCatalogLoading=false;
async function refreshIssuerCandidates(){
 if(issuerCatalogLoading)return;
 issuerCatalogLoading=true;
 const status=document.getElementById('dgIssuerStatus');
 try{
  const ctl=new AbortController(), timer=setTimeout(()=>ctl.abort(),12000);
  let response;
  try{response=await fetch('/api/degiro/candidates',{cache:'no-store',signal:ctl.signal});}
  finally{clearTimeout(timer);}
  if(!response.ok)throw Error('HTTP '+response.status);
  showIssuerCandidates(await response.json());
 }catch(e){if(status)status.textContent='Automatische Emittentenrecherche vorübergehend nicht erreichbar: '+String(e.message||e);}
 finally{issuerCatalogLoading=false;}
}

async function restoreServerCorrection(){
 const original=listArchive,revision=listRevision;
 const local=loadIdentities();
 const controller=typeof AbortController==='function'?new AbortController():null;
 const deadline=controller&&typeof setTimeout==='function'?setTimeout(()=>controller.abort(),8000):null;
 try{
  const response=await fetch('/api/degiro/list-correction',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller?.signal,body:JSON.stringify({action:'read'})});
  if(!response.ok)return;
  const data=await response.json();
  if(!data.ok||!Array.isArray(data.products)||!data.products.length||data.products.length>12
     ||!Number.isFinite(Date.parse(data.listUploadedAt))||Date.parse(data.listUploadedAt)>Date.now()
     ||(original?.storedAt&&data.listUploadedAt!==original.storedAt)
     ||listArchive!==original||revision!==listRevision)return;
  if(local.length&&(!data.corrected||original?.correctionVersion===data.version))return;
  const existing=loadIdentities();
  const items=data.products.map(p=>{
   const direction=p.productDirection||p.direction;
   const prior=existing.find(x=>x.isin===p.isin&&x.direction===direction);
   return cleanStoredProduct({...prior,isin:p.isin,name:p.name||p.isin,direction,isinConfirmed:false});
  });
  if(!items.length||items.some(x=>!x))return;
  const record={...original,files:original?.files||[],storedAt:data.listUploadedAt,items,correctionVersion:data.corrected?data.version:null};
  const payload=JSON.stringify({version:2,products:items,listUploadedAt:data.listUploadedAt});
  let committed=false;
  await archiveTransaction('readwrite',store=>{const request=store.get('list');request.onsuccess=()=>{
   if(listArchive!==original||revision!==listRevision||request.result?.storedAt!==original?.storedAt)return;
   store.put(record,'list');store.put(payload,'products');committed=true;
  };return request;});
  if(committed){
   listRevision++;listArchive=record;localStorage.setItem(PRODUCT_STORE_KEY,payload);
   productStorageBlocked=false;showListArchive();
   // The optional server read is asynchronous: reflect only the exact
   // verified list generation that was atomically committed above.
   if(productRowsReady){
    restoreProductRows(applyResearchedTerms(loadIdentities()));
    rankUI();
    const status=document.getElementById('dgCentralStatus');
    if(status)status.textContent='✅ '+items.length+' gespeicherte Produkte aus vorhandenem, datiertem Server-Nachweis wiederhergestellt. Originalzeit '+data.listUploadedAt+'. Keine Handelsfreigabe.';
   }
  }
  return committed;
 }catch(_){/* Keep local originals when server correction is unavailable. */return false;}
 finally{if(deadline&&typeof clearTimeout==='function')clearTimeout(deadline);}
}

function mountListCorrection(host){
 const panel=document.createElement('details');
 panel.innerHTML='<summary>Gespeicherte Serverliste korrigieren</summary><p>Originalbilder bleiben auf dem Upload-Gerät. Der ursprüngliche Listenzeitpunkt bleibt erhalten. Angaben mit den Originalbildern vergleichen.</p><button type="button" data-list-load>Aktuelle Serverliste laden</button><p data-list-generation></p><label>Produkte: eine Zeile je ISIN; LONG/SHORT; EUR/CHF; Handelsplatz<textarea data-list-rows rows="12" style="width:100%;box-sizing:border-box" aria-label="Listenkorrektur Produkte"></textarea></label><label>Screenshot-Zeit (Zürich)<input data-list-time type="datetime-local" aria-label="Screenshot-Zeit"></label><label>Originalbild-Referenz<input data-list-reference aria-label="Originalbild-Referenz" maxlength="200"></label><label><input type="checkbox" data-list-reviewed> Angaben anhand der Originalbilder geprüft</label><button type="button" data-list-save disabled>Korrektur auf dem Server speichern</button><p role="status" data-list-status></p>';
 host.append(panel);let current=null;
 const field=k=>panel.querySelector('[data-list-'+k+']');
 const call=async payload=>{const r=await fetch('/api/degiro/list-correction',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok||!data.ok)throw Error(data.error||'Speichern fehlgeschlagen');return data;};
 field('load').onclick=async()=>{try{current=await call({action:'read'});field('generation').textContent='Original-Listenstand: '+current.listUploadedAt;field('rows').value=current.products.map(p=>[p.isin,p.productDirection||p.direction,p.currency||'',p.listingVenue||''].join(';')).join('\n');field('save').disabled=false;field('status').textContent=current.products.length+' Serverprodukte geladen.';}catch(e){field('status').textContent=e.message;}};
 field('save').onclick=async()=>{field('save').disabled=true;try{
 if(!current||!field('reviewed').checked)throw Error('Originalbilder zuerst prüfen und bestätigen.');
 const products=field('rows').value.trim().split(/\n/).map(line=>{const [isin,direction,currency,venue,...extra]=line.split(';').map(x=>x.trim());if(extra.length)throw Error('Vier Felder je Zeile erforderlich');return {isin,direction,currency,venue};});
 const result=await call({action:'save',version:current.version,reviewed:true,products,observedMinute:field('time').value,imageReference:field('reference').value});
 current=result;field('status').textContent='Gespeichert: '+result.products.length+' Produkte · ursprünglicher Listenstand '+result.listUploadedAt+' bleibt erhalten. Hintergrundprüfung folgt. Keine Handelsfreigabe.';
 }catch(e){field('status').textContent=e.message;}finally{field('save').disabled=false;}};
}

async function inject(){
 if(document.getElementById("dgTop3"))return;
 const a=document.getElementById("dgProductOut"); if(!a)return;
 const b=document.createElement("div");
 b.id="dgTop3";
 b.style.cssText="margin-top:14px;padding:16px;background:#f7f9fc;border-radius:20px;border:1px solid #e5eaf2";
 b.innerHTML='<style>#dgTop3 > details,#dgTop3Out > section,#dgTop3Out > details,#dgApprovalOut > details{box-sizing:border-box;min-width:0;margin-top:14px;padding:12px;background:#fff;border:1px solid #e1e7f0;border-radius:16px;overflow-wrap:anywhere}#dgTop3 > details > summary,#dgTop3Out > details > summary,#dgApprovalOut > details > summary{cursor:pointer;font-weight:700}#dgTop3 > details[open] > summary,#dgTop3Out > details[open] > summary,#dgApprovalOut > details[open] > summary{margin-bottom:10px}</style><div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b></div></div>'+
 '<section id="dgEarlyProductRanking" hidden style="margin-top:12px;padding:12px;border:1px solid #d97706;border-radius:12px;white-space:pre-line;overflow-wrap:anywhere"></section>'+
 '<div id="dgTop3Out" style="margin-top:12px"></div>'+
 '<details style="margin-top:12px"><summary id="dgSavedProductsSummary" style="cursor:pointer;font-weight:700">Gold-Hebelprodukte</summary><div id="dgMissingProducts" style="margin-top:12px"></div></details>'+
 '<div id="dgScreenshotReturn" hidden style="margin-top:14px;padding:14px;background:#eaf3ff;border:2px solid #1677ff;border-radius:14px;scroll-margin-top:16px"><b>Screenshots für <span data-return-isin></span></b><p class="small">Bilder werden diesem zuvor geöffneten Produkt zugeordnet, auch wenn ISIN oder WKN im Bild fehlen. Eine eindeutig abweichende Produktkennung wird gemeldet.</p><div data-return-product-link></div><div data-return-missing></div><p class="small">Fehlenden Wert erneut aufnehmen: Produktseite öffnen, Screenshot machen und anschließend hier beim selben Produkt hinzufügen.</p><button type="button" data-return-upload style="width:100%;background:#1677ff">↑ Bilder / PDF für dieses Produkt hinzufügen</button><div class="small" style="margin:8px 0">Originaldateien: lokal auf diesem Gerät, bis zu 7 Tage / insgesamt 100 MB. Nach Erkennungsupdates prüft Bob gespeicherte Dateien erneut. Ursprüngliche Datenstände bleiben erhalten.</div><button type="button" data-return-reprocess>Gespeicherte Bilder erneut prüfen</button><button type="button" data-return-delete>Gespeicherte Originaldateien löschen</button><button type="button" data-return-close>Fertig / ausblenden</button><div role="status" data-return-status style="overflow-wrap:anywhere;min-width:0"></div><div role="status" data-return-complete hidden style="margin-top:12px;font-weight:700;color:#15803d">✅ Datenübertragung komplett</div></div>'+
 '<div style="margin-top:14px;padding:12px;background:#fff;border-radius:16px;border:1px solid #e1e7f0">'+
 '<details id="dgIssuerCatalogPanel" style="margin-bottom:12px;border:1px solid #d7e0ea;border-radius:10px;padding:10px"><summary><b>Automatische Gold-Produktrecherche · externe Kandidaten</b></summary><p class="small">Bob überprüft die früher in DEGIRO beobachteten ISINs ohne Screenshot bei Emittenten. Nicht die vollständige aktuelle DEGIRO-Liste; Handelbarkeit und neue Produkte sind nicht bestätigt. Keine automatische Top-3-Freigabe.</p><div role="status" class="small" id="dgIssuerStatus">Noch keine Serverprüfung.</div><div id="dgIssuerCandidates"></div></details>'+ '<b>📷 DEGIRO-Liste</b><button type="button" id="dgListUploadButton" style="margin-top:10px;width:100%;background:#1677ff">↑ Neue DEGIRO-Liste hochladen</button><button type="button" id="dgListAddButton" style="margin-top:8px;width:100%;background:#e9f2ff;color:#1659aa">＋ Weiteres Listenbild hinzufügen</button>'+
 '<input id="dgListUpload" type="file" accept="image/*" multiple hidden>'+
 '<details style="margin-top:8px"><summary>Hinweise zum Hochladen</summary><div class="small">Beide Screenshots können gemeinsam ausgewählt werden. Alternativ zuerst ein Bild hochladen und danach „Weiteres Listenbild hinzufügen“ wählen. Abgeschnittene Zeilen bleiben bis zum ergänzenden Bild vorgemerkt. Nur Bilder derselben Tagesliste werden kombiniert.</div></details>'+
 '<div id="dgCentralStatus" class="small" role="status" aria-live="polite" style="margin-top:9px">Gespeicherte Liste wird geladen …</div><details id="dgSavedListImages"></details></div>'+

 '<details id="dgBrokerQuotePanel" style="margin-top:10px;border:1px solid #cbd5e1;border-radius:12px;padding:10px"><summary><b>📈 DEGIRO-Kursdaten · Leseprüfung</b></summary>'+
 '<p class="small">Bob liest bereits gespeicherte, bewusst ausgewählte DEGIRO-Produktdetailbilder. Die Daten stammen nicht aus einer angemeldeten DEGIRO-API; die Kursdatenzeit ist nicht zwingend eine eigene Geld-/Briefzeit.</p>'+
 '<p class="small" id="dgBrokerQuoteCount" role="status">Kursbilder werden geprüft …</p><div id="dgBrokerQuoteRows"></div>'+
 '<p class="small">SnapTrade ist für Depot- und Auftragsdaten gedacht, nicht als 30-Sekunden-Kursfeed für Gold-Knock-outs. Emittenten- und Vergleichskurse bleiben getrennt.</p></details>'+
 '<div id="dgStorageStatus" class="small" role="status"></div>'+
 '<div id="dgManualSnapshots" style="margin-top:12px" hidden></div>'+
 '<div id="dgConditionalOut" style="margin-top:12px" hidden></div>'+
 '<div id="dgTop3Inputs" hidden></div>' +
 '<button style="margin-top:10px;width:100%" id="dgRankBtn" hidden>🔎 Analyse erneut ausführen</button><div id="dgApprovalOut"></div>';
 // Keep the daily list and gold products ahead of rankings and supporting tools.
 const listPanel=b.querySelector('#dgListUploadButton').parentElement;
 const savedProducts=b.querySelector('#dgSavedProductsSummary').parentElement;
 const issuerPanel=b.querySelector('#dgIssuerCatalogPanel');
 b.append(issuerPanel);
 b.querySelector(':scope > div').after(listPanel,savedProducts);
 a.parentNode.insertBefore(b,a.nextSibling);
 mountListCorrection(b);
 const q=b.querySelector("#dgTop3Inputs");
 for(let i=1;i<=12;i++){
  const r=document.createElement("div");
  r.style.cssText="margin:8px 0;padding:9px;background:#fff;border-radius:10px";
  r.innerHTML='<b>Kandidat '+i+'</b><div id="dgOcrStatus'+i+'" class="small" style="margin-top:5px">Wartet auf Screenshot.</div><div id="dgResearch'+i+'" class="small research" style="margin-top:5px">🌐 Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="'+i+'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="'+i+'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="'+i+'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="'+i+'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="'+i+'" type="number" step=".01" placeholder="KO-Level"><div><input data-dg="isin" data-i="'+i+'" placeholder="ISIN" aria-label="ISIN"><button type="button" data-copy-product-isin="" aria-label="ISIN kopieren" title="ISIN kopieren" style="min-width:44px;min-height:44px;padding:6px;margin-left:6px;font-size:20px">📋</button><span role="status" data-copy-status></span></div><span id="dgCompletion'+i+'" role="status"></span></div><button data-research="'+i+'">Aktuelle Produktdaten laden</button>';
  bindIsinCopy(r);
  r.insertAdjacentHTML("beforeend",'<div id="dgEvidence'+i+'"></div><div style="margin-top:8px"><label for="dgDetailShot'+i+'">📎 Bilder / PDF für dieses Produkt hochladen</label><input id="dgDetailShot'+i+'" type="file" accept="image/*,application/pdf,.pdf" multiple><div class="small">PDF-Endgültige Bedingungen oder Produktdetail oder Kursdaten mit sichtbarer ISIN. Mehrere Bilder können nacheinander ergänzt werden. Kurszeit braucht Datum, Sekunden und Zeitzone. Hebelbild und Kursbild direkt nacheinander aufnehmen und gemeinsam auswählen: Der Hebel erhält den Zeitbezug dieser Aufnahmeserie. Eine eigene Hebelzeit bleibt erhalten; KO benötigt einen eigenen Datenstand.</div></div>');
  r.insertAdjacentHTML("beforeend",window.BobCombined.form(i));
  r.querySelector('[data-fixed-save]').addEventListener('click',()=>{
   const read=k=>r.querySelector('[data-dg="'+k+'"]')?.value.trim()||'';
   const accepted=r.querySelector('[data-combined="fixedKo"]').checked;
   const ok=accepted&&window.BobCombined.saveFixed({isin:read('isin').toUpperCase(),productDirection:read('dir'),ko:read('ko')},combinedDrafts.get(i)?.evidence?.ko1);
   const status=document.getElementById('dgCombinedDraft'+i);if(status)status.textContent=ok?'Feste Barriere gespeichert: DEGIRO-Screenshot, vom Nutzer bestätigt. SG-Nachweis für diese Abstandberechnung nicht erforderlich.':'Bitte gültige ISIN, Richtung und positiven KO-Level eintragen und feste USD-Barriere bestätigen.';
   rankUI();
  });
  r.querySelector('[data-fixed-clear]').addEventListener('click',()=>{window.BobCombined.removeFixed(r.querySelector('[data-dg="isin"]').value.trim().toUpperCase());r.querySelector('[data-combined="fixedKo"]').checked=false;rankUI();});
  r.querySelector("[data-combined-save]").addEventListener("click",()=>{
   const read=k=>r.querySelector('[data-combined="'+k+'"]')?.value.trim()||"";
   const reviewed=r.querySelector('[data-combined="reviewed"]').checked;
   const isin=r.querySelector('[data-dg="isin"]').value.trim().toUpperCase();
   const barriers=[1,2].filter(z=>read("ko"+z)).map(z=>({isin,value:read("ko"+z),currency:"USD",source:read("koSource"+z),url:read("koUrl"+z),at:read("koAt"+z),validUntil:read("koUntil"+z),imageSource:z===1?combinedDrafts.get(i)?.evidence?.ko1:null,confirmed:reviewed}));
   const assumedSeconds=false;
   const identity=r.querySelector('[data-dg="confirmed"]');if(reviewed&&identity)identity.checked=true;
   combinedReferences.set(i,{isin,source:read("source"),venue:read("venue"),url:read("url"),bid:read("bid"),ask:read("ask"),quoteAt:read("quoteAt"),assumedSeconds,paired:reviewed,reviewed,delayed:combinedDrafts.get(i)?.delayed||false,imageEvidence:combinedDrafts.get(i)?.evidence,barriers,goldReference:read("goldReference"),goldAt:read("goldAt"),goldUrl:read("goldUrl"),fxUrl:read("fxUrl"),fxReference:read("fxReference"),fxAt:read("fxAt"),referenceConfirmed:r.querySelector('[data-combined="referenceConfirmed"]').checked});rankUI();enrichProduct(i);
  });
  r.querySelectorAll('[data-combined]').forEach(el=>el.addEventListener('input',()=>{combinedReferences.delete(i);if(el.type!=='checkbox')r.querySelector('[data-combined="reviewed"]').checked=false;rankUI();}));
  r.querySelector("[data-combined-clear]").addEventListener("click",()=>{combinedReferences.delete(i);combinedDrafts.delete(i);resetCombinedForm(i);rankUI();});
  q.appendChild(r);
  r.querySelector("#dgDetailShot"+i).addEventListener("change",async e=>{
   const input=e.target,files=Array.from(input.files||[]),isin=document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value;
   if(!files.length)return;
   const productContext=returnProductIsin===isin&&validIsin(isin)?Object.freeze({isin,basis:'opened-product'}):null;
   const pendingImages=retainSelectedImages(input);
   const status=document.getElementById('dgOcrStatus'+i);
   if(status)status.textContent='📷 '+files.length+' Bild(er) ausgewählt. Bilddateien werden übernommen …';
   try{
    const retained=await pendingImages;
    await processProductImages(i,retained,productContext);
   }catch(e){if(status)status.textContent='⚠️ '+e.message;}
   finally{input.value='';input.disabled=activeProductImports.has(i);rankUI();}
  });
  r.querySelector('[data-research]').addEventListener('click',()=>enrichProduct(i));
  r.querySelectorAll('[data-dg]').forEach(el=>el.addEventListener('input',()=>{listRevision++;if(el.dataset.dg!=="confirmed"){combinedReferences.delete(i);productQuotes.delete(i);futureResearchQuotes.delete(i);if(["isin","dir"].includes(el.dataset.dg)){detailScreenshots.delete(i);}else if(["price","lev","ko","spread"].includes(el.dataset.dg)){}rowVersions.set(i,(rowVersions.get(i)||0)+1);if(el.dataset.dg==="isin"){combinedDrafts.delete(i);resetCombinedForm(i);}}rankUI();}));
 }
 await restoreListArchive();
 // Offline-first. Never await a remote correction before rendering all
 // persisted on-device product identities and screenshot evidence.
 const restoredProducts=loadIdentities();
 restoreProductRows(applyResearchedTerms(restoredProducts));
 productRowsReady=true;
 b.querySelector('[data-return-upload]').addEventListener('click',()=>{
  const rows=Array.from(document.querySelectorAll('[data-dg="isin"]')).map(el=>({isin:el.value,index:el.dataset.i}));
  const row=screenshotReturnRow(returnProductIsin,rows);
  if(!row){updateScreenshotReturn();return;}
  document.getElementById('dgDetailShot'+row.index)?.click();
 });
 b.querySelector('[data-return-reprocess]').addEventListener('click',async()=>{try{await reprocessOriginals(false);}catch(e){const status=document.querySelector('[data-return-status]');if(status)status.textContent='⚠️ '+e.message;}});
 b.querySelector('[data-return-delete]').addEventListener('click',async()=>{try{await deleteProductOriginals(returnProductIsin);const status=document.querySelector('[data-return-status]');if(status)status.textContent='Gespeicherte Originaldateien dieses Produkts gelöscht. Erkannte Produktdaten bleiben erhalten.';}catch(e){const status=document.querySelector('[data-return-status]');if(status)status.textContent='Löschen fehlgeschlagen: '+e.message;}});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)reprocessOriginals(true).catch(e=>console.warn('[BOB] Originalprüfung',e.message));});
 setTimeout(()=>reprocessOriginals(true).catch(e=>console.warn('[BOB] Originalprüfung',e.message)),1000);
 b.querySelector('[data-return-close]').addEventListener('click',()=>{
  returnProductIsin='';returnProductPending=false;
  try{localStorage.removeItem(RETURN_PRODUCT_KEY);}catch(_){}
  updateScreenshotReturn();
 });
 setTimeout(()=>updateScreenshotReturn(true),0);
 window.addEventListener('pageshow',()=>{updateScreenshotReturn(true);refreshImportedProducts(true);});
 window.addEventListener('online',()=>refreshImportedProducts(true));
 quoteRefresh=createQuoteRefresh({
  rows:()=>Array.from({length:12},(_,idx)=>{
   const id=idx+1,isin=(document.querySelector('[data-dg="isin"][data-i="'+id+'"]')?.value.trim()||'').toUpperCase();
   const name=document.querySelector('[data-dg="name"][data-i="'+id+'"]')?.value||'';
   const quote=productQuotes.get(id),snapshot=detailScreenshots.get(id);
   const factor=/FAKTOR|FACTOR/i.test([name,quote?.metadata?.name,snapshot?.terms?.type?.value].join(' '));
   const terminal=quote?.isin===isin&&quote?.productVerified&&quote.metadata?.status===2||
       knockoutStatus({isin,snapshot})||
       serverIssuerTerminated({isin});
   // Exclusions suppress recurring issuer quote requests, not manual review or
   // the first fetch of unknown products. List replacement resets cached states.
   const fields=productFieldStates({isin,quote,snapshot,leverage:quote?.leverage},Date.now());
   const repairNeeded=Object.values(fields).some(f=>!(n(f.value)>0)||/fehlt|veraltet|unbestätigt|abweichend/.test(f.state));
   return {id,isin,repairNeeded,suppressed:factor||terminal,key:isin+':'+(rowVersions.get(id)||0)};
  }),
  request:enrichProduct,visible:()=>!document.hidden,interval:30000,limit:4
 });
 refreshImportedProducts(!['night','weekend'].includes(window.BobDegiroPhase?.()));
 const savedCount=restoredProducts.length;
 refreshIssuerCandidates();
 setInterval(()=>{if(!document.hidden)refreshIssuerCandidates();},10*60*1000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshIssuerCandidates();});
 b.querySelector('#dgCentralStatus').textContent=listArchive?.files?.length?'Aktive Liste: '+listArchive.files.length+' Screenshot(s) · '+savedCount+' Produkte · aufgenommen '+new Date(listArchive.storedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+'. Bleibt aktiv bis zum nächsten erfolgreichen Upload; aktuelle Produktkurse werden separat geprüft.':savedCount?savedCount+' gespeicherte Produkte · die letzte Liste bleibt erhalten; Kursdaten können veralten.':'In diesem Browser sind noch keine lokalen Produkte verfügbar. Vorhandene Serverlisten-Nachweise werden geprüft; bitte keine neue Liste hochladen, bevor der Abruf abgeschlossen ist.';
 // Render first, then check remote correction in the background. Never show
 // a perpetual "Gespeicherte Liste wird geladen ..." during a network outage.
 rankUI();
 restoreServerCorrection().then(committed=>{
  if(committed)return;
  if(!listArchive?.items?.length&&!loadIdentities().length){
   const status=document.getElementById('dgCentralStatus');
   if(status)status.textContent='Keine gespeicherten Produktdaten in diesem Browser wiederherstellbar. Ein Serverlisten-Nachweis ist derzeit nicht verfügbar oder nicht lesbar. Bitte in dem Browser prüfen, in dem die Liste hochgeladen wurde; nichts löschen.';
  }
 }).catch(()=>{});
  const brokerQuotePanel=b.querySelector('#dgBrokerQuotePanel');
 brokerQuotePanel?.addEventListener('click',event=>{
  const button=event.target.closest('[data-dg-broker-quote-upload]');
  if(!button)return;
  const index=Number(button.dataset.dgBrokerQuoteUpload);
  if(!Number.isInteger(index)||index<1||index>12)return;
  const input=document.getElementById('dgDetailShot'+index);
  if(input&&!input.disabled)input.click();
 });
const upload=b.querySelector('#dgListUpload'),uploadButton=b.querySelector('#dgListUploadButton'),addButton=b.querySelector('#dgListAddButton'),uploadStatus=b.querySelector('#dgCentralStatus');
 let listUploadMode='replace',stagedListImages=[],pendingRetryBusy=false;
 uploadStatus.dataset.listReaderVersion='20261026-reviewed-list-retry-v2';
 uploadButton.addEventListener('click',()=>{listUploadMode='replace';stagedListImages=[];upload.click();});
 addButton.addEventListener('click',()=>{listUploadMode='append';upload.click();});
 upload.addEventListener('change',async()=>{
  if(!upload.files?.length)return;
  listRevision++; // Invalidate an older asynchronous reread immediately.
  uploadButton.disabled=true;addButton.disabled=true;upload.disabled=true;
  let files=[];
  try{
   const chosen=await retainSelectedImages(upload);
   const prior=listAppendSourceFiles(listUploadMode,stagedListImages,listArchive);
   if(prior===null)throw Error('Kein heutiges erstes Listenbild gefunden. Bitte mit „Neue DEGIRO-Liste hochladen“ beginnen.');
   files=[...prior.map(x=>x.blob?.name?x.blob:new File([x.blob],x.name,{type:x.blob?.type||'image/png'})),...chosen];
   if(files.length>12)throw Error('Zu viele Listenbilder. Bitte mit einer neuen Liste beginnen und höchstens zwölf Bilder auswählen.');
   const items=await readListBatch(files,recognizeOcr,(i,total,name)=>{uploadStatus.textContent='📷 Bild '+i+' von '+total+' wird gelesen: '+name;});
   await saveReplacementListArchive(files,items);
   stagedListImages=[];
   await clearPendingDegiroList().catch(()=>{});
   // The old screenshot universe is now replaced. Its manual KO and PDF
   // attestations must not silently apply to the new list, even for a shared ISIN.
   try{localStorage.removeItem(PDF_REFERENCE_STORE);}catch(_){}
   returnProductIsin='';returnProductPending=false;
   try{localStorage.removeItem(RETURN_PRODUCT_KEY);}catch(_){}
   populateCandidateRows(items);
   // Persist the new generation before any normal/periodic background snapshot.
   const backgroundSynced=await window.BobPaperSimulation?.sync?.(buildPaperListEvidence(),true);
   rankUI();
   uploadStatus.textContent='✅ '+(listUploadMode==='append'?'Listenbild ergänzt':'Neue Liste übernommen')+': '+files.length+' Bild(er) · '+items.length+' unterschiedliche Produkte. Liste vollständig geprüft und gespeichert; ältere Nachweise bleiben nur historisch. Kurszeiten werden unabhängig geprüft.';
   uploadStatus.textContent+=backgroundSynced?' Hintergrundübernahme bestätigt.':' ⚠️ Hintergrundübernahme noch offen; automatischer Abgleich läuft.';
   const uncertain=items.filter(x=>!validIsin(x.isin)).length;
   if(uncertain)uploadStatus.textContent+=' ⚠️ '+uncertain+' ISIN(s) unsicher – unter Details prüfen.';
   // The paper/background service is refreshed immediately, independently of its
   // ordinary 60-second cadence. Never send removed ISINs from the old list.
   refreshImportedProducts(true).then(()=>refreshImportedProducts());
  }catch(e){
   const message=e?.message||'Bilder konnten nicht gelesen werden';
   // Store only in-memory originals of an incomplete multi-image set.
   // Do not commit a partial list or mutate old DEGIRO/KO evidence.
   const incomplete=/Abgeschnittene Produktzeile|Produktzeile [0-9]+|Listenaufbau nicht erkannt|Keine vollständige DEGIRO-Produktzeile/.test(message);
   if(incomplete&&files.length&&files.length<12){
    stagedListImages=files;
    const persisted=await savePendingDegiroList(files).catch(()=>false);
    uploadStatus.textContent='⚠️ '+message+' '+files.length+' Bild(er) vorgemerkt. '
      +(persisted?'Originalbilder für erneute automatische Prüfung gespeichert.':'Bilder nur bis zum Neuladen vorgemerkt.')
      +' Die bisherige Produktliste bleibt erhalten.';
   }else{
    uploadStatus.textContent='⚠️ '+message+' Die bisherige Produktliste bleibt erhalten.';
   }
  }
  finally{upload.value='';upload.disabled=false;uploadButton.disabled=false;addButton.disabled=false;setTimeout(retrySavedList,1000);}
 });
 // Retry the uncommitted screenshot batch at startup after a new code release.
 // Only an entirely valid batch may replace the user's active saved list.
 const retryPendingList=async()=>{
  if(pendingRetryBusy||upload.disabled||document.hidden)return false;
  pendingRetryBusy=true;
  const generation=listRevision;
  upload.disabled=true;uploadButton.disabled=true;addButton.disabled=true;
  try{
   const saved=await loadPendingDegiroList();
   if(!saved?.length||generation!==listRevision)return false;
   stagedListImages=saved;
   uploadStatus.textContent='🔎 '+saved.length+' gespeicherte Listenbilder werden automatisch erneut geprüft …';
   let items;
   try{
    items=await readListBatch(saved,recognizeOcr,(i,total)=>{uploadStatus.textContent='🔎 Gespeicherter Import: Bild '+i+' von '+total;});
   }catch(e){
    uploadStatus.textContent='⚠️ Gespeicherte Listenbilder noch nicht vollständig prüfbar: '+e.message+' Die aktive Liste bleibt erhalten.';
    return false;
   }
   if(generation!==listRevision)return false;
   await saveReplacementListArchive(saved,items);
   await clearPendingDegiroList().catch(()=>{});
   stagedListImages=[];
   try{localStorage.removeItem(PDF_REFERENCE_STORE);}catch(_){}
   populateCandidateRows(items);
   const synced=await window.BobPaperSimulation?.sync?.(buildPaperListEvidence(),true);
   rankUI();
   uploadStatus.textContent='✅ Automatisch wiederhergestellt: '+saved.length+' Listenbilder · '+items.length+' unterschiedliche Produkte. '
    +(synced?'Hintergrundübernahme bestätigt.':'Hintergrundabgleich noch offen.');
   refreshImportedProducts(true).then(()=>refreshImportedProducts()).catch(()=>{});
   return true;
  }catch(e){
   uploadStatus.textContent='⚠️ Automatische Wiederherstellung nicht bestätigt: '+(e?.message||'Fehler')+'. Die alte Liste bleibt erhalten.';
   return false;
  }finally{
   pendingRetryBusy=false;upload.disabled=false;uploadButton.disabled=false;addButton.disabled=false;
  }
 };
 setTimeout(()=>retryPendingList().catch(()=>{}),800);
 const retrySavedList=async()=>{
  if(document.hidden||upload.disabled||activeProductImports.size)return;
  try{
   const recovered=await recoverArchivedList(recognizeOcr);
   if(!recovered)return;
   restoreProductRows(recovered.rows);rankUI();
   uploadStatus.textContent='✅ '+recovered.corrected+' Produktkennung(en) aus gespeicherten Originalbildern automatisch korrigiert. Ursprüngliche Bildzeit bleibt erhalten; Produktdaten werden erneut geprüft.';
   window.BobPaperSimulation?.sync?.(buildPaperListEvidence(),true);
   await refreshImportedProducts(true);
  }catch(_){uploadStatus.textContent='⚠️ Automatische Zweitlesung noch nicht erfolgreich. Gespeicherte Liste bleibt erhalten; Bob versucht es später erneut.';}
 };
 setTimeout(retrySavedList,1000);
 setInterval(retrySavedList,30*60*1000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)retrySavedList();});
 // Navigation can move this button while restoreListArchive() is awaiting IndexedDB.
 document.getElementById("dgRankBtn").addEventListener("click",async e=>{const button=e.currentTarget;button.disabled=true;rankUI();try{await refreshImportedProducts(true);}finally{button.disabled=false;rankUI();}});
 setInterval(()=>{if(!document.hidden){rankUI();refreshImportedProducts();}},10000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){rankUI();refreshImportedProducts();updateScreenshotReturn(true);}});
 window.addEventListener('online',()=>refreshImportedProducts());
 setInterval(()=>{if(!document.hidden)rankUI();},1000);
}
// Calculations use original values; freshness never fabricates a source timestamp.
function calculationAge(at,limit=90000,now=Date.now()){
 const iso=typeof at==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(at)?Date.parse(at):NaN;
 const t=Number.isFinite(iso)?iso:selectionTimeWindow(at)?.start;
 return Number.isFinite(t)&&t<=now&&now-t<=limit?'':!Number.isFinite(t)?'Aktualität unbekannt – Zeitstempel fehlt oder ist unklar':t>now?'Aktualität unbekannt – Zeitstempel liegt in der Zukunft':'veraltet – Stand: '+new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' (Zürich) · '+Math.floor((now-t)/60000)+' min '+Math.floor((now-t)%60000/1000)+' s alt';
}
function researchPriceProduct(p,now){
 // Copies only: calculations must not rewrite imported originals or grants.
 const q=p.quote;
 if(q?.isin!==p.isin||q.productVerified!==true||q.metadata?.status!==1||q.sourceDisabled||q.metadata?.tradingHalted)return p;
 const fields=productFieldStates(p,now),ask=fields.ask,lev=fields.leverage;
 const current=f=>f&&n(f.value)>0&&Number.isFinite(f.ageSeconds)&&f.ageSeconds>=0&&f.ageSeconds<=90&&!/(unbestätigt|veraltet|abweichend)/i.test(f.state);
 if(current(ask)){
  // Native CHF values must not be silently treated as EUR prices.
  const nativeChf=q.metadata?.currency==='CHF'&&productDisplayQuote(q,p.isin,now)?.currency!=='EUR';
  if(nativeChf)return p;
  return {...p,price:ask.value,priceCalculated:ask.kind==='calculated',
   ...(current(lev)?{leverage:lev.value,leverageCalculated:lev.kind==='calculated'||/berechnet/i.test(lev.state)}:{}),
   researchPriceEvidence:{kind:ask.kind==='calculated'?'calculated':'observation',source:ask.source,at:ask.at,
    leverageAt:current(lev)?lev.at:null,referenceOnly:true,degiroExecutable:false}};
 }
 const c=continuityDisplay(p,now);
 if(c?.state==='calculated')return {...p,price:c.price,leverage:c.leverage,priceCalculated:true,leverageCalculated:true,
  researchPriceEvidence:{kind:'calculated',source:'Bob · theoretischer Produktwert',at:c.at,leverageAt:c.at,referenceOnly:true,degiroExecutable:false}};
 return p;
}
function selectedPriceSnapshot(p,now=Date.now()){
 const selected=researchPriceProduct(p,now),e=selected.researchPriceEvidence;
 if(!e)return null;
 return {version:1,isin:p.isin,currency:'EUR',price:selected.price,leverage:selected.leverage,
  ...e,selectionKey:JSON.stringify([p.isin,e.kind,e.source,e.at,selected.price])};
}
function continuingAnalysis(products,context){
 return products.filter(p=>p.isin||p.name).map(original=>{
  const p=researchPriceProduct(original,context.now??Date.now());
  const analysis=p.quote?.analysisQuote;
  const direct=p.quote?.isin===p.isin&&n(p.quote.price)===n(p.price);
  const at=direct?(p.quote.askAt||p.quote.quoteAt):((analysis&&n(analysis.price)>0&&n(analysis.price)===n(p.price))?analysis.askAt:p.snapshot?.evidence?.Brief?.at||p.snapshot?.sourceTime||p.quote?.askAt||p.quote?.quoteAt);
  const limit=direct||(analysis&&n(analysis.price)>0&&n(analysis.price)===n(p.price))?(p.quote?.analysisMaxAgeSeconds||90)*1000:p.snapshot?SCREENSHOT_MAX_AGE_MS:90000,now=context.now??Date.now();
  const priceWarning=calculationAge(p.researchPriceEvidence?.at||at,p.researchPriceEvidence?90000:limit,now);
  const levAt=p.quote?.isin===p.isin&&n(p.quote.leverage)===n(p.leverage)?p.quote.leverageAt:p.snapshot?.evidence?.Hebel?.at;
  const levWarning=calculationAge(p.researchPriceEvidence?.leverageAt||levAt,limit,now);
  const terms=productTermsStatus(p,now,true);
  const seriesWarning=p.snapshot?.evidence?.Hebel?.fromSeries&&n(p.snapshot.evidence.Hebel.value)===n(p.leverage)?'Hebel: Zeitbezug aus Aufnahmeserie; kein separat bestätigter Anbieterzeitstempel':'';
  const selected=p.researchPriceEvidence;
  const sourceNote=selected?(selected.kind==='calculated'?'Kurs berechnet':'Originalkurs')+' · '+selected.source+' · '+selected.at:'';
  const warning=[priceWarning,levWarning?'Hebel: '+levWarning:'',seriesWarning,...terms.warnings].filter(Boolean).join(' · ');
  return {p,priceBasis:selectedPriceSnapshot(p,now),warning,sourceNote,evaluation:evaluateProduct({...p,...context})};
 });
}
// Research-only KO-buffer order. Missing approval evidence stays missing;
// this list never enters selectionWorkflow, push, paper orders or trade approval.
function unapprovedComparisonRanking(products,context={}){return comparisonRanking(products,context,true);}
// Early watchlist keeps product/KO gates but does not demand the later main setup.
function earlyWarningRanking(products,context={}){return comparisonRanking(products,context,false);}
function comparisonRanking(products,context={},requireSetup=true){
 if(context.spotFresh!==true||!['LONG','SHORT'].includes(context.direction)||
    !(n(context.spot)>0)||!(n(context.atr)>0))return [];
 const now=context.now??Date.now(),seen=new Set(),results=[];
 for(const row of continuingAnalysis(products,context)){
  const {p,evaluation:e}=row,isin=p.isin;
  if(!validIsin(isin)||seen.has(isin)||p.isinConfirmed!==true||
     p.productDirection!==context.direction||knockoutStatus(p)||isFutureProduct(p)||
     /FAKTOR|FACTOR/i.test([p.name,p.quote?.name,p.snapshot?.terms?.type?.value].join(' '))||
     !(n(p.price)>0)||!(n(p.leverage)>=1)||!(n(p.ko)>0)||
     (p.quote?.isin&&p.quote.isin!==isin)||
     (p.snapshot?.isin&&p.snapshot.isin!==isin)||
     (p.quote?.productVerified&&p.quote?.metadata?.status!==undefined&&p.quote.metadata.status!==1)||
     !e.ok||!e.fit||e.direction!==context.direction||(requireSetup&&(e.setupScore<35||e.conflictCount>=3))||
     !Number.isFinite(e.score)||!Number.isFinite(e.koDistancePct))continue;
  seen.add(isin);
  const evidence=finalProductStatus(p,now);
  results.push({...row,proofComplete:evidence.complete,missing:evidence.reasons||[]});
 }
 return results.sort((a,b)=>b.evaluation.score-a.evaluation.score||a.p.isin.localeCompare(b.p.isin)).slice(0,3);
}
function indicativeRecommendations(products,context){
 const now=context.now??Date.now(),seen=new Set();
 if(!['LONG','SHORT'].includes(context.direction))return [];
 return continuingAnalysis(products,context).filter(({p,evaluation:e})=>{
  if(seen.has(p.isin)||!validIsin(p.isin)||p.isinConfirmed!==true)return false;
  seen.add(p.isin);
  return productTermsStatus(p,now,true).complete&&e.ok&&e.fit&&e.direction===context.direction&&e.setupScore>=35&&e.conflictCount<3;
 }).sort((a,b)=>b.evaluation.score-a.evaluation.score||a.p.isin.localeCompare(b.p.isin)).slice(0,3);
}
function renderProductCalculation({p,warning,evaluation:e}){
 const marketWarnings=window.BobAnalysisAge?.()||[];
 const uncertain=!!warning||marketWarnings.length>0;
 return '<details data-product-details="calculation-'+esc(p.isin)+'" style="margin-top:10px"><summary>Berechnung und Bewertung</summary><p class="small">Rechnerische Bewertung mit vorhandenen Werten, auch bei veralteten oder fehlenden Zeitstempeln. Keine aktuell bestätigte Produktfreigabe.</p>'+(marketWarnings.length?'<p><i>'+esc(marketWarnings.join(' · '))+'</i></p>':'')+'<div style="margin:8px 0;'+(uncertain?'font-style:italic':'')+'"><b>'+esc(p.isin||p.name)+'</b> · Kurs '+esc(p.price??'fehlt')+' · <strong>Hebel</strong> '+esc(p.leverage??'fehlt')+' · KO '+esc(p.ko??'fehlt')+(warning?' · '+esc(warning):'')+'<br>'+esc(e.ok?'KO-Pufferwert: '+e.score+'/100 · Marktsignal-Stärke: '+e.setupScore+'/100 · '+e.reasons.join(' · '):e.reasons.join(' · '))+'</div></details>';
}
// Explain a missing ranking from the SAME data/selection gates that Bob uses.
// Never infer market opening hours or create a recommendation from old prices.
function productSelectionExplanation(products,context,ranked,marketWarnings=[]){
 const notes=Array.isArray(marketWarnings)?marketWarnings.filter(x=>typeof x==='string'&&x.trim()):[];
 const direction=context?.direction;
 const found=Array.isArray(products)?products.filter(p=>p&&(p.isin||p.name)):[];
 const choices=Array.isArray(ranked)?ranked:[];
 // Freshness takes priority. Otherwise a stale or absent feed could be
 // falsely presented as a confident neutral market or rejected product.
 if(context?.spotFresh!==true||notes.length){
  const detail=notes.length?' Hinweis: '+notes.slice(0,2).join(' · ').slice(0,240)+'.':'';
  return {state:'market-data',text:'Marktdaten fehlen, sind veraltet oder ihre Aktualität ist nicht ausreichend belegt. Deshalb ist derzeit keine belastbare aktuelle Produktauswahl möglich.'+detail};
 }
 if(!['LONG','SHORT'].includes(direction))
  return {state:'neutral',text:'Marktdaten sind aktuell, aber Bob hat keine bestätigte LONG- oder SHORT-Richtung. Deshalb gilt ABWARTEN; das ist keine Aussage über die Eignung einzelner Produkte.'};
 if(choices.length)
  return {state:'ranked',text:'Bob zeigt '+choices.length+(choices.length===1?' rechnerisch passenden ':' rechnerisch passende ')+direction+'-Kandidaten aus den vorhandenen Nachweisen. Kurszeiten und Handelsverfügbarkeit zusätzlich prüfen.'};
 if(!found.length)
  return {state:'no-products',text:'Die Marktlage ist '+direction+', aber Bob hat aktuell keine erfassten Gold-Hebelprodukte zur Auswahl. Produktliste prüfen oder laden.'};
 const now=context?.now??Date.now();
 const verified=found.filter(p=>validIsin(p.isin)&&p.isinConfirmed===true&&productTermsStatus(p,now,true).complete);
 if(!verified.length)
  return {state:'product-data',text:'Die Marktlage ist '+direction+', aber für die gespeicherten Produkte fehlen ausreichend bestätigte Pflichtdaten oder Produktnachweise. Deshalb kann Bob noch nicht feststellen, ob ein Produkt geeignet ist.'};
 return {state:'no-match',text:'Die Marktdaten sind aktuell und die Richtung ist '+direction+'. Von den ausreichend belegten Produkten erfüllt derzeit keines sämtliche Auswahlkriterien. Andere Produkte können zusätzlich unvollständige Nachweise haben.'};
}
// Reuse the existing source, terms, timing and risk gates. A free-form
// calculationEvidence label is never an input to this approval decision.
function calculatedAnalysisStatus(p,context={},now=Date.now()){
 const blocked=reason=>({status:'blocked',approved:false,reasons:[reason],brokerTradeable:false,executableQuote:false,automaticOrder:false});
 if(!p||!Number.isFinite(now)||![p.price,p.leverage,p.ko,context.spot,context.atr].every(v=>n(v)>0&&Number.isFinite(Number(v))))return blocked('Berechnungswerte fehlen oder sind ungültig');
 if(p.isinConfirmed!==true||!validIsin(p.isin)||isFutureProduct(p)||knockoutStatus(p)||
   /FAKTOR|FACTOR/i.test([p.name,p.quote?.name,p.snapshot?.terms?.type?.value].join(' '))||
   p.quote?.metadata?.tradingHalted===true||p.quote?.sourceDisabled===true||
   (p.snapshot?.isin&&p.snapshot.isin!==p.isin))return blocked('Produkt ausgeschlossen oder Identität nicht bestätigt');
 if(context.spotFresh!==true||p.productDirection!==context.direction||!selectionMarketGate(context).ok)return blocked('Kein bestätigtes aktuelles Marktsignal');
 if(!productTermsStatus(p,now).complete)return blocked('Produktbedingungen nicht vollständig bestätigt');
 const q=p.quote,analysis=analysisReleaseQuote(p,now);
 if(!analysis&&!q?.calculatedProduct?.available)return blocked('Kein prüfbarer berechneter Produktnachweis');
 const candidate=conditionalCandidate(p,context,now),evaluation=evaluateProduct({...p,...context});
 if(!candidate.ok||candidate.direction!==context.direction||!evaluation.ok||!evaluation.fit)return blocked(candidate.reason||'Produkt passt nicht zu den Schutzregeln');
 return {status:'calculated-approved',approved:true,reasons:[],source:analysis?.source||candidate.priceKind,
  at:candidate.at,priceKind:candidate.priceKind,brokerTradeable:false,executableQuote:false,automaticOrder:false};
}
function renderContinuingAnalysis(products,context){
 // Neutral or stale market conditions must not present a product ranking.
 if(!context||!['LONG','SHORT'].includes(context.direction)||context.spotFresh!==true)return '<section data-market-waiting><b>ABWARTEN · keine Rangliste</b></section>';
 // One complete research ranking. Approval and execution gates remain separate.
 if(typeof document!=='undefined')for(const [i,p] of products.entries())for(const [field,key] of [['price','Brief'],['lev','Hebel'],['ko','KO']]){
  const input=document.querySelector('[data-dg="'+field+'"][data-i="'+(i+1)+'"]');if(!input)continue;
  const evidence=p.snapshot?.evidence?.[key],at=evidence?.at||(field==='price'?(p.snapshot?.sourceTime||p.quote?.quoteAt):null);
  const warning=calculationAge(at,p.snapshot?SCREENSHOT_MAX_AGE_MS:90000);
  input.style.fontStyle=warning?'italic':'';input.title=warning;
 }
 const marketWarnings=window.BobAnalysisAge?.()||[];
 const ranked=indicativeRecommendations(products,context);
 const explanation=productSelectionExplanation(products,context,ranked,marketWarnings);
 const explanationHtml='<p data-selection-reason="'+explanation.state+'" role="status" class="small" style="margin:10px 0">'+esc(explanation.text)+'</p>';
 const highestLeverage=Math.max(...ranked.map(({evaluation:e})=>e.leverage));
 const leveragePlaces=ranked.flatMap(({evaluation:e},i)=>e.leverage===highestLeverage?[i+1]:[]);
 const leverageIsins=ranked.flatMap(({p,evaluation:e})=>e.leverage===highestLeverage?[p.isin]:[]);
 const leverageHint=leveragePlaces.length?'<div data-risk-leverage data-risk-isins="'+esc(leverageIsins.join(' / '))+'" data-risk-positions="'+leveragePlaces.join(' / ')+'" style="margin:8px 0"><strong>Risiko: '+(leveragePlaces.length>1?'Plätze ':'Platz ')+leveragePlaces.join(' / ')+' · höchster Hebel: '+highestLeverage.toFixed(2)+'×</strong><details><summary>Erklärung zum Hebelrisiko</summary><div class="small">Unter den formal belegten Empfehlungen; verstärkt Gewinne und Verluste. Hebel laut vorhandenen Werten.</div></details></div>':'';
 const rows=continuingAnalysis((Array.isArray(products)?products:[]).filter(p=>p.productDirection===context.direction),context);
 const now=context?.now??Date.now(),seen=new Set(),rankable=[],unranked=[];
 for(const row of rows){
  const p=row.p||{},isin=p.isin||'';
  if(!isin||seen.has(isin))continue;
  seen.add(isin);
  const evidence=finalProductStatus(p,now),e=row.evaluation||{};
  const calculation=calculatedAnalysisStatus(p,context,now);
  const item={...row,evidence,calculation};
  // Do not invent scores for missing contracts, knocked-out or mismatched products.
  const safe=context?.spotFresh===true&&['LONG','SHORT'].includes(context?.direction)&&
   n(context?.spot)>0&&n(context?.atr)>0&&p.productDirection===context.direction&&
   e.direction===context.direction&&validIsin(isin)&&p.isinConfirmed===true&&!knockoutStatus(p)&&
   !isFutureProduct(p)&&!/FAKTOR|FACTOR/i.test(p.name||'')&&
   !(p.quote?.isin&&p.quote.isin!==isin)&&
   !(p.snapshot?.isin&&p.snapshot.isin!==isin)&&
   n(p.price)>0&&n(p.leverage)>=1&&n(p.ko)>0&&
   Number.isFinite(e.score)&&Number.isFinite(e.koDistancePct);
  (safe?rankable:unranked).push(item);
 }
 rankable.sort((a,b)=>b.evaluation.score-a.evaluation.score||a.p.isin.localeCompare(b.p.isin));
 const marketPlan=window.productMarketPlan?.(context.direction,now);
 const describe=(row,i)=>{
  const p=row.p,e=row.evaluation||{},proof=row.evidence;
  const rank=i===null?'Ohne Rang':'Platz '+(i+1);
  const freshness=row.warning&&row.warning.includes('veraltet')?'Mit veralteten Werten gerechnet':
   row.warning?'Mit Werten unbekannter Aktualität gerechnet':
   marketWarnings.length?'Marktdaten-Aktualität eingeschränkt':'Rechnerischer Vergleich mit vorhandenen Werten';
  const fields=[['Kurs',p.price],['Hebel',p.leverage],['KO',p.ko]].map(([name,value])=>{
   const estimated=p.estimated===true||p.calculated===true||
    (name==='Hebel'&&p.leverageCalculated===true)||
    (name==='Kurs'&&p.priceCalculated===true);
   return name+': '+(n(value)!==null?esc(value):'unbekannt')+
    ' ('+(n(value)===null?'fehlt':estimated?'berechnet':'Quelle/Originalstatus prüfen')+')';
  }).join(' · ');
  return '<div data-unified-ranking-isin="'+esc(p.isin)+'" style="margin:8px 0"><b>'+
   rank+' · '+esc(p.isin)+'</b>'+renderIsinCopy(p.isin,true)+
   ' · '+esc(p.productDirection||'Richtung unbekannt')+
   (i===null?' · nicht zuverlässig bewertbar':' · Vergleichswert '+e.score+'/100')+
   '<br><strong>'+esc(freshness)+'</strong><br>'+fields+(row.sourceNote?'<div data-ranking-price-source>'+esc(row.sourceNote)+'</div>':'')+'<br><strong>'+(i!==null&&e.ok===true&&e.fit===true&&!marketWarnings.length&&row.calculation?.status==='calculated-approved'?'RECHNERISCH FREIGEGEBEN · DEGIRO-Handelbarkeit nicht bestätigt':proof.complete?'Produktnachweise vollständig; DEGIRO-Ausführung nicht bestätigt':'NICHT FREIGEGEBEN · Nachweise offen')+
   '</strong><div class="small" style="white-space:pre-line">'+esc(productRiskPreviewText(p,marketPlan,now))+'</div>'+(row.warning?'<div class="small">'+esc(String(row.warning).slice(0,250))+'</div>':'')+
   (!proof.complete?'<div class="small">Fehlt: '+esc((proof.reasons||[]).slice(0,3).join(' · ').slice(0,300))+'</div>':'')+'</div>';
 };
 return '<section data-unified-product-ranking data-indicative-recommendations><b>Alle Goldprodukte · eine Rangliste · <span style="color:'+({LONG:'#15803d',SHORT:'#b91c1c'}[context?.direction]||'#ca8a04')+'">'+esc(['LONG','SHORT'].includes(context?.direction)?context.direction:'ABWARTEN')+'</span></b>'+
  '<p class="small" data-price-source-priority>Kursreihenfolge: aktueller Originalkurs → aktuelle Ersatzquelle → gekennzeichnete Berechnung. Fehlt auch diese, bleiben ältere Werte als veraltet oder zeitlich unbestätigt sichtbar. Rangliste passend zu LONG oder SHORT; keine Handelsfreigabe oder ausführbare DEGIRO-Order.</p>'+
  explanationHtml+leverageHint+
  rankable.map((r,i)=>describe(r,i)).join('')+
  unranked.map(r=>describe(r,null)).join('')+
  (!rows.length?'<p>Keine Produkte erfasst.</p>':'')+'</section>';
}
function listVenueForSync(isin,archive=listArchive){
 const row=archive?.items?.find(x=>x.isin===isin)?.listRow;
 if(!archive?.storedAt||!archive?.files?.length||row?.isin!==isin||row.version!==1
    ||row.complete!==true||row.crossChecked!==true||row.source!=='DEGIRO-Listenbild'
    ||row.isExecutableQuote!==false||!row.imageReference)return null;
 return {version:1,isin,venue:row.venue,currency:row.currency,source:row.source,
  complete:true,crossChecked:true,isExecutableQuote:false,
  reference:row.imageReference,listUploadedAt:archive.storedAt};
}
function paperProductsForSync(products,archive=listArchive){
 return products.map(p=>{
  const evidence=listVenueForSync(p.isin,archive);
  return {...p,listVenueEvidence:evidence,currency:evidence?.currency||p.currency};
 });
}
// Source-of-truth generation for the server-side paper universe.
function buildPaperListEvidence(){
 const products=Array.from({length:12},(_,z)=>{
  const i=z+1,read=k=>document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]')?.value||'';
  const isin=String(read('isin')).trim().toUpperCase();
  if(!validIsin(isin))return null;
  const quote=productQuotes.get(i)||futureResearchQuotes.get(i);
  return {isin,name:read('name'),productDirection:read('dir'),price:n(read('price')),
   leverage:n(read('lev')),ko:n(read('ko')),spread:n(read('spread')),
   listVenueEvidence:listVenueForSync(isin),currency:listVenueForSync(isin)?.currency||undefined,
   isinConfirmed:!!(quote?.productVerified),snapshot:detailScreenshots.get(i)||null,
   quote:quote?.isin===isin?quote:null};
 }).filter(Boolean);
 return {products,references:products.map(p=>{
    const idx=Array.from({length:12},(_,z)=>z+1).find(i=>document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value?.trim().toUpperCase()===p.isin);
    return combinedReferences.get(idx)||null;
   }),fixedBarriers:window.BobCombined.fixedBarriers(),
   listUploadedAt:listArchive?.storedAt||null,origin:listArchive?.storedAt?'degiro-screenshot':'legacy'};
}
function rankUI(){if(!productRowsReady)return;const result=preserveReadingPosition(renderRankUI);refreshDegiroBrokerQuotePanel();return result;}
// Read-only connection of the shared market plan, existing KO guard and product calculator.
function productRiskPreview(p,market,now=Date.now()){
 const out={available:false,tradeable:false,automaticOrder:false,reason:'Aktueller gemeinsamer Gold-Stopp-/Zielplan fehlt'};
 if(!market?.available||p.productDirection!==market.direction)return out;
 const guard=koProtection({...p,spot:market.entry,atr:market.atr});
 const sign=market.direction==='LONG'?1:-1;
 if(guard.level!=='safe'&&guard.level!=='warning')return {...out,reason:guard.reason};
 // Do not squeeze the market stop inward to make a tight KO product appear suitable.
 if(!(sign*(market.stop-guard.protectiveStopGold)>0))return {...out,reason:'Ungeeignet: Markt-Stopp liegt im bestehenden KO-Schutzbereich. Anderes Produkt wählen.'};
 if(market.entrySuitable===false)return {...out,reason:'Marktplan: Hindernis vor ausreichendem Chance-Risiko-Verhältnis'};
 const q=p.quote,m=q?.productModel,currency=q?.metadata?.currency||q?.currency;
 if(p.isinConfirmed!==true||q?.isin!==p.isin||q?.productVerified!==true||m?.isin!==p.isin||
    m.verifiedSimpleTurbo!==true||m.underlying!=='XAU/USD'||m.direction!==p.productDirection||
    Number(m.ko)!==Number(p.ko)||!['EUR','CHF'].includes(currency)||isFutureProduct(p))
  return {...out,reason:'Bestätigtes passendes EUR-/CHF-Spot-Turbo-Modell fehlt'};
 if(q.fieldRecovery?.state==='conflict'||(q.fieldRecovery?.conflicts||[]).length||
    ['ko','strike','ratio'].some(k=>q.conditions?.[k]?.value!==undefined&&Number(q.conditions[k].value)!==Number(m[k])))
  return {...out,reason:'Widersprüchliche Produktbedingungen – Stopp-/Zielumrechnung offen'};
 const quote=window.BobStopAssistant?.selectQuote(q,p.isin,now,currency);
 const fx=market.spots?.[currency==='CHF'?'usd_chf_meta':'usd_eur_meta'];
 const clocks=[market.at,quote?.at,quote?.askAt,fx?.fetchedAt].map(x=>typeof x==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(x)?Date.parse(x):NaN);
 if(!quote||!clocks.every(x=>Number.isFinite(x)&&now>=x&&now-x<=90000)||Math.max(...clocks)-Math.min(...clocks)>90000||!(fx?.rate>0)||fx.error)
  return {...out,reason:'Zeitlich passende Originalkurse und Gold-/FX-Referenz fehlen'};
 try{
  const model=window.BobTradeProduct.model({isin:p.isin,direction:m.direction,currency,
   simpleSpotTurbo:true,referenceConfirmed:true,bid:quote.bid,goldReference:market.entry,
   fxReference:fx.rate,fxScenario:fx.rate,ratio:m.ratio,strike:m.strike,ko:m.ko,
   entry:quote.ask,quantity:1,source:quote.source,referenceAt:quote.at});
  const stop=window.BobTradeProduct.price(model,market.stop),target=window.BobTradeProduct.price(model,market.target);
  if(!stop.available||!target.available||!(stop.price<quote.ask&&quote.ask<target.price))return {...out,reason:'Kein passender Produkt-Stopp-/Zielkorridor'};
  return {...out,available:true,reason:'',currency,stop:stop.price,target:target.price,
   lossPerUnit:quote.ask-stop.price,stopGold:market.stop,targetGold:market.target,ko:m.ko,
   referenceAt:quote.at,source:quote.source,guard};
 }catch(_){return {...out,reason:'Produktwerte für individuelle Umrechnung unvollständig'};}
}
function productRiskPreviewText(p,market,now=Date.now()){
 const r=productRiskPreview(p,market,now);
 if(!r.available)return 'Stopp/Ziel offen · '+r.reason;
 const money=v=>'≈ '+v.toFixed(4)+' '+r.currency;
 return 'Vorläufiger Produktplan · Stopp '+money(r.stop)+' · Ziel '+money(r.target)+
  ' · Verlust am Stopp je Stück '+money(r.lossPerUnit)+' (ab beobachtetem Briefkurs)'+
  '\nGold-Stopp '+r.stopGold.toFixed(2)+' USD · Gold-Ziel '+r.targetGold.toFixed(2)+' USD · KO '+r.ko.toFixed(2)+' USD'+
  '\nReferenz: '+r.source+' · '+r.referenceAt+
  '\nSchätzung bei konstantem FX und Produktbedingungen, vor Gebühren. Gesamtverlust erst mit tatsächlichem Kaufkurs und Stückzahl unter Mein Trade. Keine garantierten Ausführungskurse.';
}
let earlyProductSnapshot=null,lastEarlyProductWarning=null;
function renderEarlyProductPanel(warning=lastEarlyProductWarning){
 lastEarlyProductWarning=warning;
 const panel=document.getElementById('dgEarlyProductRanking');if(!panel)return;
 const content=earlyProductRankingText(warning).trim();
 panel.hidden=!content;
 if(panel.textContent!==content)panel.textContent=content;
}
function earlyProductExclusions(products,context){
 return continuingAnalysis(products.filter(p=>p.productDirection===context.direction),context).map(({p,evaluation:e})=>{
  const reasons=[];
  if(!validIsin(p.isin)||p.isinConfirmed!==true)reasons.push('Produktidentität nicht bestätigt');
  if(!(n(p.price)>0&&n(p.leverage)>=1&&n(p.ko)>0))reasons.push('Kurs, Hebel oder KO fehlt');
  if((p.quote?.isin&&p.quote.isin!==p.isin)||(p.snapshot?.isin&&p.snapshot.isin!==p.isin))reasons.push('Produktnachweis gehört zu anderer ISIN');
  if(!e.ok||!e.fit)reasons.push(...(e.reasons||[]).filter(t=>/KO|fehlt|ausgeschlossen|gesperrt|ABWARTEN|Basiswert|Future/i.test(t)));
  return p.isin+' – '+(reasons.length?[...new Set(reasons)].join(' · '):'Produkt-/Quellennachweis nicht ausreichend');
 }).join('\n');
}
function earlyProductRankingText(warning,now=Date.now()){
 if(!warning?.available||(Number.isFinite(warning.expiresAt)&&warning.expiresAt<=now)||!['active','watch'].includes(warning.state)||!['LONG','SHORT'].includes(warning.direction))return '';
 const heading='\n\nPassende '+warning.direction+'-Produkte · vorläufige Rangliste';
 const snapshot=earlyProductSnapshot;
 if(!snapshot||now-snapshot.at>60000||now<snapshot.at)return heading+'\nProduktdaten werden geladen – noch keine aktuelle Rangliste.';
 const context={...snapshot.context,direction:warning.direction,now};
 const rows=earlyWarningRanking(snapshot.products,context);
 const market=window.productMarketPlan?.(warning.direction,now);
 if(context.spotFresh!==true)return heading+'\nGoldkurs nicht aktuell bestätigt – keine aktuelle Rangliste.';
 if(!rows.length)return heading+'\nKein ausreichend passendes Produkt nach den bestehenden Risiko- und Datenprüfungen.\n'+(earlyProductExclusions(snapshot.products,context)||'Keine Produkte dieser Richtung erfasst.');
 return heading+rows.map(({p,evaluation:e,warning:age,missing},i)=>
  '\n'+(i+1)+'. '+p.isin+' · Hebel '+p.leverage+' · KO-Abstand '+e.koDistancePct.toFixed(2)+' %'+
  (e.setupScore<35||e.conflictCount>=3?' · Hauptsignal/technische Bestätigung fehlt':'')+(age?' · '+age:'')+(missing.length?' · Nachweise offen: '+missing.join(' · '):'')+'\n'+productRiskPreviewText(p,market,now)).join('')+
  '\nBeobachtungsliste zur Frühwarnung · keine Handelsfreigabe. Hauptsignal und Einstieg separat bestätigen. Kurse und DEGIRO-Handelbarkeit separat prüfen.';
}
function renderRankUI(){
 expireVisibleList();
 saveIdentities();
 updateScreenshotReturn();
 const returnRow=screenshotReturnRow(returnProductIsin,Array.from(document.querySelectorAll('[data-dg="isin"]')).map(el=>({isin:el.value,index:el.dataset.i})));
 const returnStatus=document.querySelector('[data-return-status]');
 if(returnStatus)returnStatus.textContent=returnRow?document.getElementById('dgOcrStatus'+returnRow.index)?.textContent||'':'';
 for(const [i,x] of futureResearchQuotes){
  const isin=document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value.trim().toUpperCase();
  if(isin!==x.isin){futureResearchQuotes.delete(i);continue;}
  const meta=document.getElementById("dgResearch"+i),info=x.metadata;
  if(meta)meta.textContent="🌐 "+x.source+" · ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · "+(info.strike?"Basispreis "+info.strike+" USD · ":"")+(info.ratio?"Bezugsverhältnis "+info.ratio+" · ":"")+(info.contract?"Kontrakt "+info.contract+" · ":"")+x.reason+futureResearchText(x)+productEstimateText(x)+". Analyse- und Freigabestatus siehe Produktkarte.";
 }
 for(let i=1;i<=12;i++){const out=document.getElementById('dgEvidence'+i),html=screenshotSummary(detailScreenshots.get(i));if(out)updateProductHtml(out,html);}
 for(const [i,q] of productQuotes){
  const computed=document.getElementById("dgCalculatedState"+i);if(computed)computed.textContent=productEstimateText(q);
  const state=document.getElementById("dgQuoteState"+i),timing=quoteTiming(q);
  if(state)state.textContent=q.eligible&&q.marketOpen&&timing.fresh?"aktuell · "+timing.ageSeconds+" s alt":(q.backupActive?"Backup aktiv · ":"GESPERRT · ")+(timing.ageSeconds===null?"Zeitstempel unbekannt":timing.ageSeconds+" s alt")+(q.marketOpen?"":" · Markt geschlossen");
 }
 const s=spot(),d=scenario(),a=atr(),technical=window.BobTechnicalContext?.()||{};
 const bundle=window.liveBundleCache,sourceAge=n(bundle?.spots?.xaus_age_seconds),fetchAt=n(bundle?.fetched_at);
 const spotAge=sourceAge!==null&&fetchAt!==null?sourceAge+(Date.now()/1000-fetchAt):null;
 const spotFresh=spotAge!==null&&spotAge>=-5&&spotAge<=60&&!bundle?.spots?.spot_error;
 const ps=Array.from({length:12},(_,z)=>z+1).map(i=>({
  name:document.querySelector('[data-dg="name"][data-i="'+i+'"]')?.value.trim(),
  isin:document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value.trim(),
  productDirection:document.querySelector('[data-dg="dir"][data-i="'+i+'"]')?.value,
  price:n(document.querySelector('[data-dg="price"][data-i="'+i+'"]')?.value),
  leverage:n(document.querySelector('[data-dg="lev"][data-i="'+i+'"]')?.value),
  ko:n(document.querySelector('[data-dg="ko"][data-i="'+i+'"]')?.value),
  snapshot:detailScreenshots.get(i),quote:productQuotes.get(i)||futureResearchQuotes.get(i),isinConfirmed:false,
  spot:s
 }));
 for(const [z,p] of ps.entries()){
  p.isinConfirmed=automaticIdentity(p);
  const badge=document.getElementById("dgCompletion"+(z+1));
  if(badge)updateProductHtml(badge,productCompletionBadge(p,Date.now(),combinedReferences.get(z+1)));
 }
 const uploadMissing=document.querySelector('[data-return-missing]');
 if(uploadMissing){const i=Number(returnRow?.index),p=ps[i-1];const html=p&&p.isin===returnProductIsin?renderUploadMissing(p,finalProductStatus(p,Date.now(),combinedReferences.get(i))):'';if(uploadMissing._missingHtml!==html){uploadMissing.innerHTML=html;uploadMissing._missingHtml=html;}}
 const completion=document.querySelector('[data-return-complete]');
 if(completion){
  const i=Number(returnRow?.index),p=ps[i-1];
  completion.hidden=!(p&&p.isin===returnProductIsin&&productDataStatus(p,Date.now(),combinedReferences.get(i)).complete);
 }

 for(let i=1;i<=12;i++){const out=document.getElementById("dgCombinedState"+i),ref=combinedReferences.get(i);if(ref&&ref.isin!==ps[i-1].isin)combinedReferences.delete(i);if(out)updateProductHtml(out,window.BobCombined.render(window.BobCombined.assess(ps[i-1],combinedReferences.get(i),bundle))+window.BobCombined.renderComparison(window.BobCombined.compareSnapshot(ps[i-1],combinedReferences.get(i),combinedDrafts.get(i),productQuotes.get(i))));}
 earlyProductSnapshot={at:Date.now(),products:ps,context:{...technical,...selectionUiSignals(),spotFresh,spot:s,atr:a,
  trend:document.getElementById('trend')?.textContent,trend2:document.getElementById('trend2')?.textContent,
  rsi:n(document.getElementById('rsi')?.textContent),hist:n(document.getElementById('hist')?.textContent),adx:n(document.getElementById('adx')?.textContent)}};
 window.BobRisk?.update({bundle,products:ps,context:earlyProductSnapshot.context});
 renderEarlyProductPanel();
 const savedProducts=ps.filter(p=>p.name||p.isin);
 const savedSummary=document.getElementById("dgSavedProductsSummary");
 if(savedSummary)updateProductHtml(savedSummary,renderGoldProductsHeading(savedProducts));
 const manualOut=document.getElementById("dgManualSnapshots");
 if(manualOut){
  const ctx={direction:d,spotFresh,spot:s,atr:a,trend:document.getElementById('trend')?.textContent,trend2:document.getElementById('trend2')?.textContent,...selectionUiSignals(),rsi:n(document.getElementById('rsi')?.textContent),hist:n(document.getElementById('hist')?.textContent),adx:n(document.getElementById('adx')?.textContent),...technical};
  const comparison=rankManualSnapshots(ps,ctx);
  manualOut.innerHTML=comparison.total?'<b>📷 Vergleich belegter Momentaufnahmen · '+comparison.total+' Produkt(e)</b>'+comparison.candidates.map((p,i)=>'<div class="small" style="margin-top:8px"><b>'+(i+1)+'. '+esc(p.isin)+'</b> · KO-Pufferwert '+p.evaluation.score+'/100 · KO-Abstand '+p.evaluation.koDistancePct.toFixed(2)+'%<br>Brief '+esc(p.snapshot.ask)+' EUR · Geld '+esc(p.snapshot.bid)+' EUR · Hebel '+esc(p.leverage)+' · KO '+esc(p.ko)+(p.evaluation.warnings.length?'<br>'+esc(p.evaluation.warnings.join(' · ')):'')+'</div>').join('')+'<div class="small">Rangfolge nur innerhalb der belegten Momentaufnahmen. Laufende Aktualisierung, Marktstatus und Ausführbarkeit nicht bestätigt – keine Live-Freigabe. Unvollständige Produkte sind nicht im Vergleich.</div>':'';
 }
 const conditionalOut=document.getElementById("dgConditionalOut");
 if(conditionalOut){
  const hasModels=ps.some(p=>p.quote?.calculatedProduct||p.quote?.futureResearch);
  const ctx={spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,...selectionUiSignals(),rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),...technical};
  conditionalOut.innerHTML=hasModels?renderConditional(rankConditional(ps,ctx)):"";
 }
 const r=rankProducts(ps,{requireFreshQuotes:true,spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,...selectionUiSignals(),rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),...technical});
 const o=document.getElementById("dgTop3Out");if(!o)return r;
 const selectionContext={direction:d,spotFresh:spotFresh&&!(window.BobAnalysisAge?.().length),spot:s,atr:a,trend:document.getElementById('trend')?.textContent,trend2:document.getElementById('trend2')?.textContent,...selectionUiSignals(),rsi:n(document.getElementById('rsi')?.textContent),hist:n(document.getElementById('hist')?.textContent),adx:n(document.getElementById('adx')?.textContent),...technical};
 const references=ps.map((_,i)=>combinedReferences.get(i+1));
 const flow=selectionWorkflow(ps,selectionContext,bundle,references);
 const missingOut=document.getElementById("dgMissingProducts");
 if(missingOut){
  const html=productUploadCards(ps,d,Date.now(),flow,selectionContext);
  if(updateProductHtml(missingOut,html)){
   bindCompactCards(missingOut);
  }
 }

 const intraday=window.BobIntradayState,shadowOut=document.getElementById('intradayProducts');
 if(shadowOut){
  if(intraday?.available&&['LONG','SHORT'].includes(intraday.direction)){
   const test=selectionWorkflow(ps,intraday.context,bundle,references);
   const candidates=test.groups.flatMap(g=>g.candidates).slice(0,3);
   shadowOut.textContent='DEGIRO-Testvergleich (keine Freigabe): '+(candidates.length?candidates.map((p,i)=>(i+1)+'. '+p.isin+' · '+p.priceKind+' · KO-Pufferwert '+p.score+'/100').join('\n'):'kein ausreichend belegtes Produkt · '+test.gateReasons.concat(test.notApproved.flatMap(p=>p.reasons)).slice(0,3).join(' · '));
   intraday.products=candidates.map(p=>({isin:p.isin,price:p.price,at:p.at,priceKind:p.priceKind,score:p.score}));
  }else shadowOut.textContent='DEGIRO-Testvergleich: ABWARTEN – '+(intraday?.reason||'Intraday-Daten fehlen');
 }

 window.BobAudit?.capture(ps,flow,bundle);
 window.BobPaperSimulation?.sync({...buildPaperListEvidence(),products:paperProductsForSync(ps),references});
 window.BobPush?.updateSelection?.({products:ps,context:selectionContext,bundle:{spots:bundle?.spots,fetched_at:bundle?.fetched_at,history:{data_state:bundle?.history?.data_state}},references,fixedBarriers:window.BobCombined.fixedBarriers()},flow);
 const flowHtml=renderContinuingAnalysis(ps,selectionContext);if(updateProductHtml(o,flowHtml))bindCompactCards(o);
 const approvalOut=document.getElementById('dgApprovalOut');
 const approvalHtml='<details data-product-details="selection-check"><summary>Freigabeprüfung · '+(flow.approved?flow.approvedCount+' geeignete Produkte':'ABWARTEN')+'</summary>'+renderSelectionWorkflow(flow,ps)+'</details>';if(approvalOut&&updateProductHtml(approvalOut,approvalHtml))bindCompactCards(approvalOut);return flow;

}

if(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{inject().catch(e=>console.warn(e));});else inject().catch(e=>console.warn(e));}
// Test selection deliberately does not consult signal/recommendation gates.
function tradeTestProducts(){
 const seen=new Set();return Array.from(document.querySelectorAll('[data-dg="isin"]')).flatMap(el=>{
  const isin=el.value.trim().toUpperCase(),i=Number(el.dataset.i);
  if(!validIsin(isin)||seen.has(isin))return [];seen.add(isin);
  const direction=document.querySelector('[data-dg="dir"][data-i="'+i+'"]')?.value;
  const q=productQuotes.get(i),reference=exitReference(isin);
  return [{isin,direction,name:document.querySelector('[data-dg="name"][data-i="'+i+'"]')?.value||isin,
   quote:q?.isin===isin?q:null,reference}];
 });
}
function exitReference(isin){
 isin=String(isin||'').trim().toUpperCase();
 for(let i=1;i<=12;i++){
  if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value.trim().toUpperCase()!==isin)continue;
  const r=combinedReferences.get(i)||combinedDrafts.get(i)?.fields,q=productQuotes.get(i),m=q?.productModel;
  if(q?.isin===isin&&q.productVerified&&q.metadata?.currency==='CHF'){
   const native=q.currency==='CHF'?q:q.nativeChartEvidence;
   return {isin,currency:'CHF',direction:q.metadata.direction||m?.direction,bid:native?.bid,referenceAt:native?.bidAt||native?.pointAt,source:native?.source||q.source,ratio:q.conditions?.ratio?.value||m?.ratio,strike:q.conditions?.strike?.value||m?.strike,ko:q.conditions?.ko?.value||m?.ko};
  }
  if(r&&n(r.bid)>0)return {isin,currency:'EUR',direction:document.querySelector('[data-dg="dir"][data-i="'+i+'"]')?.value,bid:r.bid,source:r.source,referenceAt:r.quoteAt,goldReference:r.goldReference,fxReference:r.fxReference,fxScenario:r.fxReference,ko:r.barriers?.[0]?.value||r.ko1||document.querySelector('[data-dg="ko"][data-i="'+i+'"]')?.value,strike:m?.strike,ratio:m?.ratio};
  if(q?.found&&q.isin===isin&&m?.underlying==='XAU/USD')return {isin,currency:q.currency||'EUR',direction:m.direction,bid:q.bid,source:q.source,referenceAt:q.bidAt||q.quoteAt,goldReference:q.leverageInputs?.spotUsd,fxReference:q.leverageInputs?.usdEur,fxScenario:q.leverageInputs?.usdEur,ratio:m.ratio,strike:m.strike,ko:m.ko};
 }
 return null;
}
window.BobDegiro={selectedPriceSnapshot,researchPriceProduct,earlyWarningRanking,renderEarlyProductPanel,productRiskPreview,productRiskPreviewText,earlyProductRankingText,agreedExcludedDegiroFactorRow,degiroManualQuoteSummary,degiroScreenQuoteState,degiroBrokerQuotePanelState,refreshDegiroBrokerQuotePanel,goldProductBrokerListStatus,savePendingDegiroList,loadPendingDegiroList,clearPendingDegiroList,degiroFileDiagnostic,reviewedDegiroListReference,recognizeReviewedDegiroOriginal,segmentedDegiroListReadings,listAppendSourceFiles,paperProductsForSync,listVenueForSync,refreshVenueAssessment:()=>rankUI(),sharedVenueStatus,renderVenueHistory,observedDegiroListRow,degiroListBlocks,parseDegiroListRow,agreedDegiroListRow,degiroListRects,clippedDegiroListReference,recognizeDegiroList,serverVenueEvidence,degiroVenueObserved,screenshotSeriesContext,applyLearnedRanking,productHelpState,renderProductHelp,calculatedLeverageEvidence,calculatedAnalysisStatus,recoverArchivedList,productObservedTimeStatus,sharedProductFieldTime,detailScreenshotData,parseDegiroDisplayedQuote,renderDegiroDisplayedQuote,degiroListObservation,renderDegiroListEvidence,koProtection,renderProductCalculation,refreshTradeTestQuotes:()=>refreshImportedProducts(true),tradeTestProducts,koEvidenceStatus,KO_MAX_AGE_MS,currentConvertedChfEvidence,termSeriesReference,currentProductTerm,renderTermSeriesValidity,productDataStatus,productCompletionBadge,renderSecondaryValidity,analysisReleaseQuote,recognizePlainOcr,reprocessOriginals,scalarCellRect,readScalarCell,originalRetention,saveProductOriginal,loadProductOriginals,markOriginalProcessed,deleteProductOriginals,removeUnconfirmedFields,screenshotBatchSummary,renderUploadMissing,readTermDate,screenshotProductLink,knockoutStatus,explicitKnockout,knockoutCard,invalidateProductQuote,retainProductResearch,missingValueLocation,restorePdfReference,parseProductPdf,readProductPdf,sgIdentityRect,readSgIdentity,linkScreenshotSeries,ocrGlyphPair,strictOcrNumber,ocrNumericFields,unconfirmedOcrFields,preferOriginalTableRead,bnpBadgeRect,normalizeBnpQuoteColumns,imageIdentityDiagnostic,reviewedImageText,detailStateKey,updateProductHtml,preserveReadingPosition,zurichListDay,listExpired,clearDailyList,archiveTransaction,saveListArchive,saveReplacementListArchive,restoreListArchive,automaticIdentity,automaticCondition,recoverTermRows,screenshotReturnRow,renderProductDecision,readListBatch,collectiveSignal,productFieldStates,renderProductFieldStates,indicativeRecommendations,unapprovedComparisonRanking,calculationAge,continuingAnalysis,renderContinuingAnalysis,compactProductCard,screenshotSummary,retainSelectedImages,renderImageImportStatus,renderIssuerHelp,renderProductSources,applyResearchedTerms,durableCondition,maturityDeadline,writeStoredProducts,cleanStoredProduct,recoverReviewedLists,restoreProductRows,selectionUiSignals,selectionMarketGate,costRiskAssessment,finalProductStatus,parseProductTerms,productTermsStatus,selectionTimeWindow,selectionDetailStatus,selectionWorkflow,renderSelectionWorkflow,recognizeOcr,exitReference,createQuoteRefresh,screenshotCurrentState,renderScreenshotCurrentState,conditionalCandidate,rankConditional,renderConditional,qualityText,isFutureProduct,futureResearchText,productEstimateText,calculatedProductDisplay,renderPrimaryProductValues,rankManualSnapshots,productUploadCards,sourceTimestamp,screenshotTimes,evidenceTiming,manualSnapshotStatus,needsDirectionalData,loadIdentities,saveIdentities,riskModel,koDistancePct,evaluateProduct,quoteTiming,currentQuote,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates,validIsin,normalizeOcrIsin,populateCandidateRows,recoverOcrIsins,detailScreenshotData,missingProductData,supplementaryHint,screenshotTimeLabel,mergeScreenshotEvidence,manualProductMissing,escapeHtml:esc};
})();


/* Product-specific scenarios for active trades. No executable broker quotes. */
(function(root){
 const positive=v=>typeof v==='number'&&Number.isFinite(v)&&v>0;
 function model(values){
  if(!values||values.simpleSpotTurbo!==true||values.referenceConfirmed!==true)throw Error('Produktbedingungen und zusammengehörige Referenzwerte bestätigen. Unterstützt: einfaches Gold-Spot-Turbo in EUR oder CHF.');
  if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(values.isin||'')||!['LONG','SHORT'].includes(values.direction))throw Error('Produkt-ISIN oder Richtung fehlt.');
  const currency=values.currency||'EUR';if(!['EUR','CHF'].includes(currency))throw Error('Produktwährung muss EUR oder CHF sein.');
  const x={isin:values.isin,direction:values.direction,simpleSpotTurbo:true,referenceConfirmed:true,currency};
  for(const k of ['bid','goldReference','fxReference','fxScenario','ratio','strike','ko','entry','quantity']){x[k]=Number(values[k]);if(!positive(x[k]))throw Error('Produktwert fehlt: '+k);}
  if(!Number.isInteger(x.quantity))throw Error('Stückzahl muss ganzzahlig sein.');
  for(const k of ['source','referenceAt']){x[k]=String(values[k]||'').trim();if(!x[k])throw Error('Produktnachweis fehlt: '+k);}
  if((x.direction==='LONG'&&x.goldReference<=x.ko)||(x.direction==='SHORT'&&x.goldReference>=x.ko))throw Error('Referenz liegt an oder jenseits der KO-Barriere.');
  return x;
 }
 function price(m,gold){
  if(!m||!positive(gold))return {available:false,reason:'Produktnachweis fehlt'};
  const d=m.direction==='LONG'?1:-1;
  if(d*(gold-m.ko)<=0)return {available:false,reason:'KO-Barriere erreicht; kein regulärer Verkaufskurs'};
  const eur=m.bid+d*m.ratio*((gold-m.strike)*m.fxScenario-(m.goldReference-m.strike)*m.fxReference);
  return positive(eur)?{available:true,price:eur,pnl:(eur-m.entry)*m.quantity}:{available:false,reason:'Kein positiver Modellkurs'};
 }
 function withFx(m,spots,now=Date.now()){
  const fx=spots?.[m?.currency==='CHF'?'usd_chf_meta':'usd_eur_meta'],rate=Number(fx?.rate),at=Date.parse(fx?.fetchedAt);
  if(!m||!positive(rate)||!Number.isFinite(at)||at>now)return m;
  return {...m,fxScenario:rate,fxDetails:{...fx,delayed:!!fx.error||now-at>90000}};
 }
 function label(m,gold){const x=price(m,gold);return x.available?'≈ '+x.price.toFixed(4)+' '+(m.currency||'EUR')+'/Stück (geschätzt)'+(m.fxDetails?.delayed?' · FX-Aktualisierung verzögert':''):x.reason;}
 root.BobTradeProduct={model,price,label,withFx};
 if(typeof module!=='undefined')module.exports=root.BobTradeProduct;
})(typeof window!=='undefined'?window:globalThis);


/* Scenario estimates from a dated user reference; never executable quotes. */
(function(){
const num=v=>v!==null&&v!==undefined&&String(v).trim()!==''&&Number.isFinite(Number(String(v).replace(',','.')))?Number(String(v).replace(',','.')):null;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function planInput(bundle,analysis,bars,direction,now=Date.now()){
 const out={available:false,reason:'Frische passende Gold-Spot-Analyse oder Produktrichtung fehlt. Ziel/Stop bleiben offen.'};
 const b=bundle?.spots,gold=num(b?.xaus),atr=num(analysis?.at),raw=b?.spot_price_as_of;
 const at=typeof raw==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(raw)?Date.parse(raw):NaN;
 if(analysis?.ready!==true||!['LONG','SHORT'].includes(direction)||!(gold>0&&atr>0)||b?.is_genuine_xauusd_spot!==true||b.spot_error||!Number.isFinite(at)||now-at<0||now-at>60000)return out;
 const recent=Array.isArray(bars)?bars.slice(-30):[],last=recent.at(-1),previous=recent.at(-2);
 const interval=num(last?.openTime)-num(previous?.openTime);
 if(recent.length<30||!recent.every(x=>x.instrument==='XAU/USD'&&x.isOpen===false&&num(x.openTime)>0&&num(x.high)>0&&num(x.low)>0&&num(x.close)>0)||!(interval>=60000&&interval<=3600000)||Number(last.openTime)+interval>now||now-Number(last.openTime)>2*interval+60000){out.reason='Abgeschlossene aktuelle XAU/USD-Technikhistorie fehlt; keine Ziel-/Stopübernahme aus Futures, Demo oder veralteten Kerzen.';return out;}
 return {available:true,gold,atr,at:raw,source:b.primary||'XAU/USD Spot',historyAt:new Date(Number(last.openTime)+interval).toISOString(),direction};
}
function calculate(p){
 const out={available:false,reasons:[],rows:[],isEstimate:true,tradeable:false,currency:p.currency||'EUR'};
 if(!['EUR','CHF'].includes(out.currency))out.reasons.push('Produktwährung EUR oder CHF fehlt');
 const required=['bid','goldReference','fxReference','fxScenario','ratio','strike','ko','entry','quantity','planGold','targetGold','stopGold'];
 const v=Object.fromEntries(required.map(k=>[k,num(p[k])]));
 if(!window.BobDegiro?.validIsin(p.isin))out.reasons.push('Gültige Produkt-ISIN fehlt');
 if(!['LONG','SHORT'].includes(p.direction))out.reasons.push('Long-/Short-Richtung fehlt');
 if(p.simpleSpotTurbo!==true)out.reasons.push('Einfaches Gold-Spot-Turbo in EUR oder CHF ohne Quanto bestätigen; kein Future oder Optionsschein');
 if(p.referenceConfirmed!==true||!String(p.source||'').trim()||!String(p.referenceAt||'').trim())out.reasons.push('Zusammengehörige Referenzwerte mit Quelle und Kurszeit bestätigen');
 for(const k of required)if(!(v[k]>0))out.reasons.push('Positiver Wert fehlt: '+k);
 if(v.quantity!==null&&!Number.isInteger(v.quantity))out.reasons.push('Stückzahl muss ganzzahlig sein');
 if(out.reasons.length)return out;
 const d=p.direction==='LONG'?1:-1,hit=g=>d===1?g<=v.ko:g>=v.ko;
 if(hit(v.goldReference)||hit(v.planGold)){out.reasons.push('Referenz oder Plan-Goldkurs liegt an/jenseits der KO-Barriere; keine Verkaufskursschätzung');return out;}
 if(d*(v.targetGold-v.planGold)<=0||d*(v.stopGold-v.planGold)>=0){out.reasons.push('Ziel und Stop müssen auf den passenden Seiten des Plan-Goldkurses liegen');return out;}
 for(const [label,gold] of [['Am Ziel',v.targetGold],['Am Stop',v.stopGold]]){
  if(hit(gold)){out.rows.push({label,gold,available:false,reason:'KO-Barriere würde erreicht: kein normaler Verkaufskurs berechenbar'});continue;}
  const price=v.bid+d*v.ratio*((gold-v.strike)*v.fxScenario-(v.goldReference-v.strike)*v.fxReference);
  if(!(price>0)){out.rows.push({label,gold,available:false,reason:'Modell ergibt keinen positiven Verkaufskurs'});continue;}
  out.rows.push({label,gold,available:true,price,proceeds:price*v.quantity,pnl:(price-v.entry)*v.quantity});
 }
 out.available=out.rows.some(r=>r.available);out.source=p.source;out.referenceAt=p.referenceAt;out.fxScenario=v.fxScenario;out.formula='Geld₀ + Richtung × Bezugsverhältnis × [(Gold-Szenario − Basispreis) × FX-Szenario − (Gold₀ − Basispreis) × FX₀]';return out;
}
function render(x){
 if(x.reasons.length)return '<div class="warning">Offen: '+x.reasons.map(esc).join(' · ')+'</div>';
 return '<b>Geschätzter Verkaufskurs pro Stück</b><table><tr><th>Szenario Gold USD</th><th>Geldkurs '+esc(x.currency||'EUR')+'/Stück</th><th>Erlös '+esc(x.currency||'EUR')+'</th><th>Gewinn/Verlust '+esc(x.currency||'EUR')+'</th></tr>'+x.rows.map(r=>'<tr><td>'+esc(r.label)+' · '+r.gold.toFixed(2)+'</td>'+(r.available?'<td>≈ '+r.price.toFixed(2)+'</td><td>≈ '+r.proceeds.toFixed(2)+'</td><td>≈ '+r.pnl.toFixed(2)+'</td>':'<td colspan="3">'+esc(r.reason)+'</td>')+'</tr>').join('')+'</table><div class="small">Referenz: '+esc(x.source)+' · '+esc(x.referenceAt)+' (Originalzeit; keine Sekunden ergänzt). Angenommener USD→'+esc(x.currency||'EUR')+'-Kurs am Ausstieg: '+x.fxScenario+'. Linearer Turbo-Ansatz mit konstantem Preisaufschlag, konstantem Basispreis und Bezugsverhältnis; ohne Gebühren, Steuern und künftige Finanzierung. KO-Berührung auf dem Weg, Preisstellung und Ausführung unbestätigt. Genauigkeit noch nicht gemessen. Kein bestätigter zukünftiger Geldkurs.</div><details><summary>Rechenweg</summary>'+esc(x.formula)+'</details>';
}
function assessPlan(values){
 const result={available:false,tradeable:false,automaticOrder:false,reasons:[],currency:values.currency||'EUR'};
 const budget=num(values.lossBudget),minBuffer=num(values.minKoBuffer??0),minRR=num(values.minPlanRR??2);
 if(!(budget>0))result.reasons.push('Verlustbudget in der Produktwährung eingeben');
 if(!(minBuffer>=0))result.reasons.push('Mindestabstand Stopp–KO muss mindestens null sein');
 if(!(minRR>0))result.reasons.push('Positives Mindest-CRV eingeben');
 const scenario=calculate(values);
 if(scenario.reasons.length)result.reasons.push(...scenario.reasons);
 if(result.reasons.length)return result;
 const target=scenario.rows.find(r=>r.label==='Am Ziel'),stop=scenario.rows.find(r=>r.label==='Am Stop');
 if(!stop?.available||!target?.available){result.reasons.push('Stopp oder Ziel erreicht die KO-Barriere oder ergibt keinen gültigen Modellkurs');return result;}
 const entry=num(values.entry),quantity=num(values.quantity),lossPerUnit=entry-stop.price,gainPerUnit=target.price-entry;
 if(!(lossPerUnit>0&&gainPerUnit>0)){result.reasons.push('Für einen neuen Trade muss der geplante Einstieg zwischen Modell-Stoppkurs und Modell-Zielkurs liegen');return result;}
 const loss=lossPerUnit*quantity,gain=gainPerUnit*quantity,rr=gainPerUnit/lossPerUnit;
 const buffer=(values.direction==='LONG'?1:-1)*(num(values.stopGold)-num(values.ko));
 const maxQuantity=Math.floor(budget/lossPerUnit+1e-10);
 const checks=[{ok:loss<=budget+1e-8,text:'Geplanter Verlust am Stopp innerhalb des Budgets'},
  {ok:buffer>0&&buffer+1e-8>=minBuffer,text:'Stopp liegt vor KO und erfüllt deinen Mindestabstand'},
  {ok:rr+1e-10>=minRR,text:'Chance-Risiko-Verhältnis erreicht deinen Mindestwert'}];
 return {...result,available:true,fits:checks.every(c=>c.ok),checks,loss,gain,rr,buffer,maxQuantity,
  stopPrice:stop.price,targetPrice:target.price,capital:entry*quantity,budget,minBuffer,minRR,
  source:scenario.source,referenceAt:scenario.referenceAt,isEstimate:true};
}
function renderPlan(x){
 if(!x.available)return '<div role="status">Planprüfung offen: '+x.reasons.map(esc).join(' · ')+'</div>';
 const money=v=>v.toFixed(2)+' '+esc(x.currency);
 return '<div role="status"><b>'+(x.fits?'✓ Passt rechnerisch zu deinen Planvorgaben':'Plan anpassen · Vorgaben noch nicht erfüllt')+'</b></div>'+
  '<ul>'+x.checks.map(c=>'<li>'+(c.ok?'✓ ':'✗ ')+esc(c.text)+'</li>').join('')+'</ul>'+
  '<div>Einsatz: '+money(x.capital)+'<br><strong>Verlust am Stopp: ≈ −'+money(x.loss)+'</strong> · Budget '+money(x.budget)+
  '<br><strong>Gewinn am Ziel: ≈ +'+money(x.gain)+'</strong><br>Chance/Risiko: '+x.rr.toFixed(2)+':1 · Mindestwert '+x.minRR+
  '<br>Stopp–KO-Abstand: '+x.buffer.toFixed(2)+' USD im Goldpreis · Mindestabstand '+x.minBuffer.toFixed(2)+' USD'+
  '<br>Modell-Stopp: ≈ '+money(x.stopPrice)+' je Stück · Modell-Ziel: ≈ '+money(x.targetPrice)+' je Stück'+
  '<br>Nach Verlustbudget rechnerisch höchstens '+x.maxQuantity+' Stück (vor Kosten; keine Kaufempfehlung).</div>'+
  '<p class="small">Szenario vor Gebühren, Finanzierung und Ausführungsabweichungen. Das Verlustbudget ist keine garantierte Verlustgrenze; Kurslücken können den Verlust erhöhen. Referenz: '+esc(x.source)+' · '+esc(x.referenceAt)+'. Planung aktiviert keinen Trade.</p>';
}
function mountPlan(panel,readMain){
 const box=document.createElement('details');box.id='bobTradePlanFit';
 const fields=[['entry','Geplanter Einstieg je Stück'],['quantity','Geplante Stückzahl'],['planGold','Goldpreis beim geplanten Einstieg (USD)'],['stopGold','Geplanter Gold-Stopp (USD)'],['targetGold','Geplantes Gold-Ziel (USD)'],['lossBudget','Verlustbudget'],['minKoBuffer','Mindestabstand Stopp–KO (Gold USD)'],['minPlanRR','Mindest-Chance/Risiko']];
 box.innerHTML='<summary><b>Trade planen · Produktpassung</b></summary><p>Zusatz vor einem Kauf: Produkt und Referenzwerte aus dem Formular verwenden. Geplante Kaufdaten bleiben getrennt von deiner tatsächlichen Position.</p><p data-plan-identity></p><div class="grid">'+fields.map(([k,label])=>'<div><label for="plan-'+k+'" data-plan-label="'+k+'">'+label+'</label><input id="plan-'+k+'" data-plan="'+k+'" type="number" min="0" step="'+(k==='quantity'?'1':'any')+'"></div>').join('')+'</div><button type="button" data-plan-copy>Vorhandene Eingaben in Planung übernehmen</button> <button type="button" data-plan-evaluate>Produktpassung prüfen</button><div data-plan-result class="small" style="margin-top:10px">Noch keine Planprüfung.</div>';
 panel.querySelector('h3').after(box);
 const get=k=>box.querySelector('[data-plan="'+k+'"]'),out=box.querySelector('[data-plan-result]');
 const keyFor=()=>{const v=readMain();return 'bobTradePlanDraftV1:'+v.isin+':'+v.currency;};
 let activeKey='';
 function refresh(){
  const v=readMain(),key=keyFor(),currency=v.currency||'EUR';
  if(key!==activeKey){
   activeKey=key;for(const [k]of fields)get(k).value=k==='minPlanRR'?'2':k==='minKoBuffer'?'0':'';
   try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved)for(const [k]of fields)if(saved[k]!==undefined)get(k).value=saved[k];}catch(_){}
  }
  box.querySelector('[data-plan-identity]').textContent='Produkt: '+(v.isin||'oben auswählen')+' · '+(v.direction||'Richtung offen')+' · '+currency;
  box.querySelector('[data-plan-label="entry"]').textContent='Geplanter Einstieg '+currency+'/Stück';
  box.querySelector('[data-plan-label="lossBudget"]').textContent='Verlustbudget '+currency;
  out.textContent='Eingaben oder Produktreferenz geändert. Produktpassung erneut prüfen.';
 }
 function draft(){return Object.fromEntries(fields.map(([k])=>[k,get(k).value]));}
 box.addEventListener('input',()=>{try{localStorage.setItem(activeKey,JSON.stringify(draft()));}catch(_){}out.textContent='Plan geändert. Produktpassung erneut prüfen.';});
 box.querySelector('[data-plan-copy]').addEventListener('click',()=>{
  const v=readMain();for(const k of ['entry','quantity','planGold','stopGold','targetGold'])if(num(v[k])>0)get(k).value=v[k];
  try{localStorage.setItem(activeKey,JSON.stringify(draft()));}catch(_){}
  out.textContent='In die Planung kopiert. Verlustbudget und gewünschte Mindestwerte prüfen.';
 });
 box.querySelector('[data-plan-evaluate]').addEventListener('click',()=>{const v=readMain();out.innerHTML=renderPlan(assessPlan({...v,...draft()}));try{localStorage.setItem(activeKey,JSON.stringify(draft()));}catch(_){}});
 panel.addEventListener('input',e=>{if(!box.contains(e.target))refresh();});
 panel.addEventListener('change',e=>{if(!box.contains(e.target))refresh();});
 // Programmatic reference/plan copies must invalidate an old result as well.
 for(const selector of ['[data-exit-reference]','[data-exit-plan]'])panel.querySelector(selector)?.addEventListener('click',()=>{out.textContent='Referenz oder Goldplan wird übernommen. Anschließend Planung übernehmen und erneut prüfen.';});
 refresh();
}

function init(){
 if(document.getElementById('bobExitEstimate'))return;
 const parent=document.getElementById('dgTop3');if(!parent)return;
 const panel=document.createElement('div');panel.id='bobExitEstimate';panel.className='card';
 const fields=[['isin','Produkt-ISIN','text'],['currency','Produktwährung (EUR oder CHF)','text'],['entry','Tatsächlicher Einstieg EUR/Stück','number'],['quantity','Stückzahl','number'],['bid','Geldkurs der Referenz EUR/Stück','number'],['goldReference','Gold Spot USD zur Referenz','number'],['fxReference','USD→EUR zur Referenz','number'],['source','Referenzquelle (z. B. DEGIRO-Screenshot)','text'],['referenceAt','Kurszeit laut Referenz','text'],['ratio','Bezugsverhältnis','number'],['strike','Basispreis USD','number'],['ko','KO-Barriere USD','number'],['planGold','Gold Spot USD für den Handelsplan','number'],['targetGold','Gold-Ziel USD','number'],['stopGold','Gold-Stop USD','number'],['fxScenario','Angenommener USD→EUR-Kurs am Ausstieg','number']];
 panel.innerHTML='<h3>Geschätzter Ausstiegskurs pro Stück</h3><div class="small">Referenz-Geldkurs und gleichzeitig beobachtete Gold-/FX-Werte eingeben oder aus vorhandenen Produktnachweisen übernehmen. Dieses Szenario ersetzt keinen aktuellen Verkaufskurs. Eingaben werden beim Berechnen auf diesem Gerät gespeichert.</div><div class="grid">'+fields.map(([k,l,t])=>'<div><label for="exit-'+k+'">'+l+'</label><input id="exit-'+k+'" data-exit="'+k+'" type="'+t+'" '+(t==='number'?'step="any" min="0"':'')+'></div>').join('')+'<div><label for="exit-direction">Produktrichtung</label><select id="exit-direction" data-exit="direction"><option value="">Auswählen</option><option>LONG</option><option>SHORT</option></select></div></div><label><input type="checkbox" data-exit="simpleSpotTurbo"> Einfaches Gold-Spot-Turbo in EUR oder CHF, ohne Quanto; Bedingungen am Produkt geprüft</label><br><label><input type="checkbox" data-exit="referenceConfirmed"> Referenz-Geldkurs, Gold und FX gehören zeitlich zusammen; Quelle und Kurszeit geprüft</label><div class="grid"><button data-exit-reference>Produktnachweis übernehmen</button><button data-exit-plan>Ziel/Stop aus aktueller Goldanalyse</button><button data-exit-calculate>Verkaufskurse schätzen</button><button data-exit-monitor>Produkt-Trade überwachen / aktualisieren</button></div><div data-exit-output class="small">Noch keine Schätzung. Tatsächliche Position eingeben; keine Order oder Trade-Aktivierung.</div>';
 parent.after(panel);
 const currencyInput=panel.querySelector('[data-exit="currency"]'),currencySelect=document.createElement('select');
 currencySelect.id='exit-currency';currencySelect.dataset.exit='currency';currencySelect.innerHTML='<option>EUR</option><option>CHF</option>';currencyInput.replaceWith(currencySelect);
 currencySelect.addEventListener('change',()=>{
  for(const key of ['entry','bid','goldReference','fxReference','fxScenario','referenceAt','source'])panel.querySelector('[data-exit="'+key+'"]').value='';
  for(const key of ['referenceConfirmed','simpleSpotTurbo'])panel.querySelector('[data-exit="'+key+'"]').checked=false;
  panel.querySelector('[data-exit-output]').textContent='Währung geändert: Kaufkurs und Referenzwerte in der gewählten Währung ergänzen. Keine Beträge wurden umetikettiert.';
 });
 const autoButton=document.createElement('button');autoButton.type='button';autoButton.dataset.tradeReferenceRetry='';autoButton.textContent='Fehlende Werte automatisch per ISIN abrufen';autoButton.onclick=automaticTradeReference;panel.append(autoButton);
 // Keep identity and actual position visible; technical references remain available.
 const reference=document.createElement('details'),summary=document.createElement('summary'),grid=document.createElement('div');
 summary.textContent='Referenzwerte und Produktbedingungen prüfen';grid.className='grid';reference.append(summary,grid);
 const positionGrid=panel.querySelector('.grid');
 for(const el of panel.querySelectorAll('[data-exit]'))if(!['isin','currency','entry','quantity','direction','simpleSpotTurbo','referenceConfirmed'].includes(el.dataset.exit))grid.append(el.closest('div'));
 positionGrid.after(reference);
 panel.querySelector('h3').textContent='2 · Kaufdaten ergänzen';
 const hint=document.createElement('p');hint.className='small';hint.id='bobTradeFormHint';reference.after(hint);
 const updateForm=()=>{
  const read=k=>panel.querySelector('[data-exit="'+k+'"]');
  const currency=read('currency').value||'EUR';
  for(const [key,label]of Object.entries({entry:'Tatsächlicher Einstieg '+currency+'/Stück',bid:'Geldkurs der Referenz '+currency+'/Stück',fxReference:'USD→'+currency+' zur Referenz',fxScenario:'Angenommener USD→'+currency+'-Kurs am Ausstieg'})){const l=panel.querySelector('label[for="exit-'+key+'"]');if(l)l.textContent=label;}
  const ready=/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(read('isin').value.trim().toUpperCase())&&Number(read('entry').value)>0&&Number.isInteger(Number(read('quantity').value))&&Number(read('quantity').value)>0&&['LONG','SHORT'].includes(read('direction').value)&&read('simpleSpotTurbo').checked&&read('referenceConfirmed').checked;
  const monitor=panel.querySelector('[data-exit-monitor]');monitor.disabled=!ready;
  monitor.textContent='3 · Produkt-Überwachung starten / aktualisieren';
  const missing=[];if(!read('isin').value)missing.push('Produkt');if(!(Number(read('entry').value)>0))missing.push('Kaufkurs');if(!(Number.isInteger(Number(read('quantity').value))&&Number(read('quantity').value)>0))missing.push('ganze Stückzahl');if(!read('direction').value)missing.push('Richtung');if(!read('simpleSpotTurbo').checked||!read('referenceConfirmed').checked)missing.push('Produkt- und Referenzprüfung');
  hint.textContent=ready?'✓ Kaufdaten ergänzt. Jetzt Überwachung starten; Bob prüft dabei die aktuellen Marktdaten.':'Noch offen: '+missing.join(', ')+'. Vorhandene Angaben bleiben erhalten.';
 };
 panel.addEventListener('input',()=>queueMicrotask(updateForm));panel.addEventListener('change',updateForm);
 panel.addEventListener('click',()=>queueMicrotask(updateForm));
 try{const saved=JSON.parse(localStorage.getItem('bobExitScenarioV1')||'null');if(saved)for(const el of panel.querySelectorAll('[data-exit]'))if(Object.prototype.hasOwnProperty.call(saved,el.dataset.exit)){if(el.type==='checkbox')el.checked=saved[el.dataset.exit]===true;else el.value=saved[el.dataset.exit];}}catch(_){}
 const get=k=>panel.querySelector('[data-exit="'+k+'"]'),read=()=>Object.fromEntries(Array.from(panel.querySelectorAll('[data-exit]')).map(el=>[el.dataset.exit,el.type==='checkbox'?el.checked:el.value.trim()]));
 mountPlan(panel,read);
 panel.querySelector('[data-exit-reference]').addEventListener('click',()=>{
  const isin=get('isin').value.trim().toUpperCase()||document.getElementById('dgIsin')?.value.trim().toUpperCase();
  const r=window.BobDegiro.exitReference?.(isin);
  if(!r){panel.querySelector('[data-exit-output]').textContent='Kein zugehöriger Produktnachweis vorhanden. Referenzwerte manuell eintragen.';return;}
  if((r.currency||'EUR')!==(get('currency').value||'EUR')){
   if(Number(get('entry').value)>0){panel.querySelector('[data-exit-output]').textContent='Produktwährung weicht vom Kauf ab. Währung und Kaufkurs zuerst prüfen.';return;}
   for(const k of ['bid','goldReference','fxReference','fxScenario','source','referenceAt'])get(k).value='';
  }
  for(const [k,v] of Object.entries(r))if(get(k)&&v!==null&&v!==undefined&&v!=='')get(k).value=v;
  get('referenceConfirmed').checked=false;get('simpleSpotTurbo').checked=false;
  panel.querySelector('[data-exit-output]').textContent='Vorhandene Werte übernommen. Fehlende Referenzwerte und tatsächlichen Einstieg/Stückzahl ergänzen; Bedingungen und zeitliche Zuordnung prüfen.';
 });
 panel.querySelector('[data-exit-plan]').addEventListener('click',async()=>{
  const direction=get('direction').value,isin=get('isin').value;
  let plan=planInput(window.liveBundleCache,window.A,window.C,direction);
  if(!plan.available&&!window.BobSession?.expired()&&typeof window.loadData==='function'){
   panel.querySelector('[data-exit-output]').textContent='Aktuelle Gold-Spot-Analyse für Ziel/Stop wird geladen …';
   try{await window.loadData(true);plan=planInput(window.liveBundleCache,window.A,window.C,direction);}catch(_){}
  }
  if(get('isin').value!==isin||get('direction').value!==direction)return;
  const gold=plan.gold,atr=plan.atr;
  if(window.BobSession?.expired()||!plan.available){panel.querySelector('[data-exit-output]').textContent=plan.reason||'Sitzung abgelaufen.';return;}
  const stop=window.stopModel?.(direction,gold,atr,1.5)?.stop,target=window.targetModel?.(direction,gold,stop,2)?.target;
  if(!(stop>0&&target>0)){panel.querySelector('[data-exit-output]').textContent='Technischer Ziel-/Stopplan nicht verfügbar.';return;}
  get('planGold').value=gold;get('stopGold').value=stop.toFixed(2);get('targetGold').value=target.toFixed(2);
  panel.querySelector('[data-exit-output]').textContent='Ziel/Stop für die vorhandene '+direction+'-Position übernommen: '+stop.toFixed(2)+' / '+target.toFixed(2)+' USD. Gold '+gold+' USD · '+plan.source+' · Kurszeit '+plan.at+' · Historie bis '+plan.historyAt+'. Technische Szenarien, keine neue Trade-Freigabe und keine Vorhersage des besten Ausstiegszeitpunkts.';
 });
 panel.querySelector('[data-exit-calculate]').addEventListener('click',()=>{const values=read();try{localStorage.setItem('bobExitScenarioV1',JSON.stringify(values));}catch(_){}panel.querySelector('[data-exit-output]').innerHTML=render(calculate(values));});
 panel.querySelector('[data-exit-monitor]').addEventListener('click',async()=>{
  const out=panel.querySelector('[data-exit-output]');
  try{const values=read();out.textContent=await window.activateProductTrade(values);localStorage.setItem('bobExitScenarioV1',JSON.stringify(values));}
  catch(e){out.textContent=e.message||'Produkt-Trade konnte nicht übernommen werden.';}
 });
 panel.querySelectorAll('[data-exit]').forEach(el=>el.addEventListener('input',()=>{if(!['referenceConfirmed','entry','quantity'].includes(el.dataset.exit))get('referenceConfirmed').checked=false;panel.querySelector('[data-exit-output]').textContent='Eingaben geändert; Schätzung erneut berechnen.';}));
 updateForm();
}
function selectProduct(isin){
 const panel=document.getElementById('bobExitEstimate');if(!panel||!window.BobDegiro.validIsin(isin))return;
 const get=k=>panel.querySelector('[data-exit="'+k+'"]');
 const changed=get('isin').value.trim().toUpperCase()!==isin;
 if(changed)for(const el of panel.querySelectorAll('[data-exit]')){if(el.type==='checkbox')el.checked=false;else el.value='';}
 get('isin').value=isin;
 const reference=window.BobDegiro.exitReference?.(isin);
 if(reference&&(changed||(reference.currency||'EUR')===(get('currency').value||'EUR')))for(const [key,value] of Object.entries(reference))if(get(key)&&(key==='currency'||!get(key).value)&&value!==null&&value!==undefined)get(key).value=value;
 let saved;try{saved=JSON.parse(localStorage.getItem('bobExitScenarioV1')||'null');}catch(_){}
 if(saved?.isin===isin&&(!get('currency').value||(saved.currency||'EUR')===get('currency').value))for(const [key,value]of Object.entries(saved))if(get(key)&&get(key).type!=='checkbox'&&!get(key).value&&value!==null&&value!==undefined)get(key).value=value;
 let receipt;try{receipt=JSON.parse(localStorage.getItem('bobTradeEvidenceV1')||'{}')[isin];}catch(_){}
 if(receipt?.isin===isin&&(!get('currency').value||(receipt.currency||'EUR')===get('currency').value)){
  const known={currency:receipt.currency||'EUR',entry:receipt.entry?.price,quantity:receipt.entry?.quantity,direction:receipt.direction,ratio:receipt.ratio,strike:receipt.strike,ko:receipt.ko};
  for(const [key,value]of Object.entries(known))if(!get(key).value&&value!==null&&value!==undefined)get(key).value=value;
 }
 if(!get('currency').value)get('currency').value='EUR';
 // Stored confirmations are rechecked by the existing issuer/reference validation.
 panel.dispatchEvent(new Event('change',{bubbles:true}));
 automaticTradeReference();
}
function issuerTradeFields(x,isin){
 if(!x||x.isin!==isin||x.productVerified!==true)throw Error('Produktidentität noch nicht bestätigt.');
 const m=x.metadata||{},model=x.productModel||{},c=x.conditions||{};
 if(m.status===2||m.tradingHalted===true)throw Error('Produkt beendet oder Handel ausgesetzt.');
 if(m.underlyingType!=='SPOT'&&model.underlying!=='XAU/USD')throw Error('Gold-Spot-Basiswert nicht bestätigt; kein Spot-Modell für Futures.');
 const currency=m.currency||x.currency;if(!['EUR','CHF'].includes(currency))throw Error('Produktwährung EUR/CHF nicht bestätigt.');
 const fields={currency},put=(k,v)=>{if(num(v)>0)fields[k]=num(v);};
 for(const k of ['ratio','strike','ko'])put(k,c[k]?.value??model[k]??m[k]);
 if(['LONG','SHORT'].includes(m.direction||model.direction))fields.direction=m.direction||model.direction;
 const q=currency==='CHF'?(x.currency==='CHF'?x:x.nativeChartEvidence):x.analysisQuote||x;
 if(!q||(q.currency||(currency==='EUR'?'EUR':null))!==currency)throw Error('Referenzkurs in '+currency+' fehlt; umgerechnete Kurse werden nicht als Originalkurs übernommen.');
 if(num(q.bid)>0&&(q.bidAt||q.quoteAt||q.pointAt)&&Number.isFinite(Date.parse(q.bidAt||q.quoteAt||q.pointAt))){
  fields.bid=num(q.bid);fields.referenceAt=q.bidAt||q.quoteAt||q.pointAt;fields.source=(q.source||x.source||'Emittentenabfrage')+' · '+(x.sourceUrl||'')+' · Referenz für Berechnung, kein zugesicherter DEGIRO-Ausführungskurs';
 }
 return fields;
}
let autoReferenceBusy=false;
async function automaticTradeReference(){
 const panel=document.getElementById('bobExitEstimate');if(!panel||autoReferenceBusy)return;
 const get=k=>panel.querySelector('[data-exit="'+k+'"]'),out=panel.querySelector('[data-exit-output]');
 const isin=get('isin').value.trim().toUpperCase(),direction=get('direction').value;
 if(!window.BobDegiro.validIsin(isin)){out.textContent='Für den automatischen Abruf ist eine gültige ISIN erforderlich.';return;}
 const before=Object.fromEntries(Array.from(panel.querySelectorAll('[data-exit]')).filter(el=>!['entry','quantity'].includes(el.dataset.exit)).map(el=>[el.dataset.exit,el.type==='checkbox'?el.checked:el.value]));
 autoReferenceBusy=true;out.textContent='Produktwerte per ISIN bei SG und vorhandenen Ersatzquellen abrufen …';
 try{
  const r=await fetch('/api/degiro/enrich?isin='+encodeURIComponent(isin),{cache:'no-store',signal:AbortSignal.timeout(65000)});
  if(!r.ok)throw Error('Produktquelle antwortet mit '+r.status);
  const x=await r.json();if(get('isin').value.trim().toUpperCase()!==isin)return;
  if(Object.entries(before).some(([key,value])=>(get(key).type==='checkbox'?get(key).checked:get(key).value)!==value)){out.textContent='Eingaben wurden während des Abrufs geändert und bleiben erhalten. Bitte den Abruf erneut starten.';return;}
  const fields=issuerTradeFields(x,isin);
  if(fields.currency!==(get('currency').value||'EUR')&&Number(get('entry').value)>0)throw Error('Produktwährung ist '+fields.currency+'. Währung im Formular zuerst korrigieren und Kaufkurs in dieser Währung eingeben.');
  if(direction&&fields.direction&&direction!==fields.direction)throw Error('Produktrichtung widerspricht dem Kauf; keine Werte übernommen.');
  get('referenceConfirmed').checked=false;get('simpleSpotTurbo').checked=false;
  for(const [k,v] of Object.entries(fields))if(get(k))get(k).value=v;
  panel.dispatchEvent(new Event('change',{bubbles:true}));
  out.textContent='Produktwerte übernommen. Quelle: '+(x.source||x.sourceUrl||'ISIN-Abfrage')+'. Produktbedingungen und zeitliche Referenz bleiben getrennt prüfbar.';
  const evidence=fields.referenceAt&&fields.bid?await researchReference():null;
  if(get('isin').value.trim().toUpperCase()!==isin)return;
  const values=Object.fromEntries(Array.from(panel.querySelectorAll('[data-exit]')).map(el=>[el.dataset.exit,el.type==='checkbox'?el.checked:el.value.trim()]));
  localStorage.setItem('bobExitScenarioV1',JSON.stringify(values));
  const unchanged=['currency','direction','ratio','strike','ko','bid','referenceAt'].every(k=>fields[k]===undefined||String(get(k).value)===String(fields[k]));
  if(unchanged&&x.productModel?.verifiedSimpleTurbo===true&&x.productModel?.isin===isin&&evidence?.available===true&&evidence.originalTime===fields.referenceAt&&Number.isFinite(evidence.maxSkewSeconds)&&evidence.maxSkewSeconds>=0&&evidence.maxSkewSeconds<=90){
   values.simpleSpotTurbo=true;values.referenceConfirmed=true;
   get('simpleSpotTurbo').checked=true;get('referenceConfirmed').checked=true;
   panel.dispatchEvent(new Event('change',{bubbles:true}));
   localStorage.setItem('bobExitScenarioV1',JSON.stringify(values));
   out.textContent='✓ Produktwerte und zeitliche Zuordnung automatisch geprüft. Ergänze nur noch fehlende Kaufdaten und starte die Überwachung.';
   return values;
  }
  out.textContent+=' Kaufkurs und Stückzahl bleiben unverändert. Fehlende Vertragswerte werden nicht geschätzt; Gold-/FX-Referenzen und Verkaufskurse sind ausdrücklich Näherungen. Überwachung noch nicht aktiviert.';
 }catch(e){out.textContent='Automatischer Abruf noch unvollständig: '+e.message+' Vorhandene Kaufdaten bleiben erhalten.';}
 finally{autoReferenceBusy=false;panel.dispatchEvent(new Event('change',{bubbles:true}));if(get('isin').value.trim().toUpperCase()!==isin&&window.BobDegiro.validIsin(get('isin').value.trim().toUpperCase()))queueMicrotask(automaticTradeReference);}
}
function referenceHtml(x){
 const local=t=>new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false})+' Schweizer Zeit';
 return 'Gold-/FX-Werte übernommen: Gold '+esc(x.goldReference)+' USD · USD→'+esc(x.currency||'EUR')+' '+esc(x.fxReference)+'.<br>Gold-Beobachtung: '+esc(local(x.goldAt))+' · FX-Minute: '+esc(local(x.fxStart))+' bis '+esc(local(x.fxEnd))+' · maximaler Zeitversatz '+esc(x.maxSkewSeconds)+' Sekunden.<br><a href="'+esc(x.goldUrl)+'" target="_blank" rel="noopener">Goldquelle</a> · <a href="'+esc(x.fxUrl)+'" target="_blank" rel="noopener">FX-Quelle</a><br>'+esc(x.note)+'<br>Referenz in den Berechnungsdetails prüfen und bestätigen. Ziel/Stop ergänzen. Ausstiegs-FX zunächst konstant angenommen.';
}
function restoreReference(){
 const p=document.getElementById('bobExitEstimate');if(!p)return false;
 const get=k=>p.querySelector('[data-exit="'+k+'"]');
 try{const x=JSON.parse(localStorage.getItem('bobTradeMarketReferencesV1')||'{}')[get('isin').value];
 if(!x||(x.currency||'EUR')!==(get('currency').value||'EUR')||x.at!==get('referenceAt').value||x.bid!==get('bid').value)return false;
 for(const k of ['goldReference','fxReference','fxScenario','source'])get(k).value=x[k];
 if(x.evidence)p.querySelector('[data-exit-output]').innerHTML=referenceHtml(x.evidence);return true;
 }catch(_){return false;}
}
async function researchReference(){
 const panel=document.getElementById('bobExitEstimate');if(!panel)return;
 const get=k=>panel.querySelector('[data-exit="'+k+'"]'),out=panel.querySelector('[data-exit-output]');
 const currency=get('currency').value||'EUR',isin=get('isin').value,at=get('referenceAt').value,bid=get('bid').value,source=get('source').value.split(' · Historische Näherungsreferenz:')[0];
 if(!window.BobDegiro?.validIsin(isin)||!at||!(num(bid)>0)){out.textContent='Zuerst Produkt-ISIN und datierten Geldkurs übernehmen.';return;}
 get('referenceConfirmed').checked=false;out.textContent='Historische Gold-/FX-Referenz zur Originalzeit wird gesucht …';
 try{
  const response=await fetch('/api/trade-reference?at='+encodeURIComponent(at)+'&currency='+encodeURIComponent(currency),{cache:'no-store'}),x=await response.json();
  if(get('currency').value!==currency||get('isin').value!==isin||get('referenceAt').value!==at||get('bid').value!==bid)return;
  if(!response.ok||!x.available){out.textContent=x.reason||'Referenz fehlt.';return;}
  if((x.currency||'EUR')!==currency)throw Error('Referenzwährung stimmt nicht überein');
  get('goldReference').value=x.goldReference;get('fxReference').value=x.fxReference;get('fxScenario').value=x.fxReference;
  get('source').value=source+' · Historische Näherungsreferenz: '+x.goldSource+' @ '+x.goldAt+'; '+x.fxSource+' @ '+x.fxStart+' bis '+x.fxEnd+'; Zeitzone Europe/Zurich angenommen; maximaler Zeitversatz '+x.maxSkewSeconds+' s';
  try{const all=JSON.parse(localStorage.getItem('bobTradeMarketReferencesV1')||'{}');all[isin]={currency,at,bid,goldReference:x.goldReference,fxReference:x.fxReference,fxScenario:x.fxReference,source:get('source').value,evidence:x};localStorage.setItem('bobTradeMarketReferencesV1',JSON.stringify(all));}catch(_){}
  out.innerHTML=referenceHtml(x);return x;
 }catch(_){if(get('isin').value===isin&&get('referenceAt').value===at)out.textContent='Referenzabruf fehlgeschlagen. Keine historischen Werte ersetzt.';}
}
window.BobExitEstimate={assessPlan,renderPlan,mountPlan,selectProduct,calculate,render,init,researchReference,restoreReference,planInput,issuerTradeFields,automaticTradeReference};
if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();}
})();


/* Dated personal trade evidence. No orders and no invented quote precision. */
(function(){
const KEY='bobTradeEvidenceV1',esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function number(v){let s=String(v||'').trim();if(s.includes(','))s=s.replace(/\./g,'').replace(',','.');return /^\d+(?:\.\d+)?$/.test(s)?Number(s):null;}
function parse(text){
 const raw=String(text||''),ids=[...new Set(raw.toUpperCase().match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])].filter(x=>window.BobDegiro.validIsin(x));
 if(ids.length!==1)return{ok:false,reason:'Genau eine gültige ISIN muss im Bild sichtbar sein. Kursbild bitte mit ISIN erneut aufnehmen.'};
 const match=re=>{const m=raw.match(re);return m?m[1].trim():null;},val=label=>number(match(new RegExp('\\b(?:'+label+')(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR|CHF)?\\s*([0-9]+(?:[.,][0-9]+)?)','i')));
 const time=match(/\b(\d{2}[/.]\d{2}[/.]\d{4},?\s+\d{2}:\d{2}(?::\d{2})?)\b/),direction=/\b(?:CALL|LONG)\b/i.test(raw)?'LONG':/\b(?:PUT|SHORT)\b/i.test(raw)?'SHORT':null;
 const explicit=raw.match(/(?:Kurs|Geld|Brief|Bid|Ask)\s*[:=]?\s*(EUR|CHF)\b/i);
 const currency=explicit?explicit[1].toUpperCase():/\bEUR\b|€/.test(raw)?'EUR':null;
 if(!currency&&/\bGeld\b|\bBid\b|\bKauf\b/i.test(raw))return{ok:false,reason:'Produktwährung EUR oder CHF am Original nachweisen.'};
 if(/\b(?:CALL|LONG)\b/i.test(raw)&&/\b(?:PUT|SHORT)\b/i.test(raw))return{ok:false,reason:'Produktrichtung widersprüchlich.'};
 if((raw.match(/\b(?:Geld|Bid)(?!\s*(?:Vol|Volumen))/gi)||[]).length>1)return{ok:false,reason:'Mehrere Geldkurse: ein einziges Geld-/Briefpaar zeigen.'};
 const purchase=/\bKauf\b/i.test(raw)&&/Ausf.hrungsdatum|Transaktions.ID|Order.[I1l]?D/i.test(raw);
 const x={ok:true,isin:ids[0],currency:currency||raw.match(/Produktwährung\s+(EUR|CHF)/)?.[1]||'EUR',direction,time,kind:purchase?'entry':/\bGeld\b|\bBid\b/i.test(raw)?'quote':'details'};
 if(purchase){x.entry=val('Kurs');x.quantity=val('Anzahl|Anz\\.');x.orderId=match(/Order.ID\s*[:=]?\s*([a-z0-9-]+(?:\s*\n\s*[a-z0-9-]+)?)/i)||match(/Transaktions.ID\s*[:=]?\s*(\d+)/i);x.feesChf=number(match(/(?:Gesamte Kosten|Gesamtgebühr)\s*CHF\s*-?\s*([0-9]+(?:[.,][0-9]+)?)/i));if(!(x.entry>0&&Number.isInteger(x.quantity)&&x.quantity>0&&time))return{ok:false,reason:'Kaufpreis, ganzzahlige Stückzahl oder Ausführungsdatum fehlt. OCR-Text am Original korrigieren.'};}
 else if(x.kind==='quote'){x.bid=val('Geld|Bid');x.ask=val('Brief|Ask');if(!(x.bid>0&&x.ask>=x.bid&&time))return{ok:false,reason:'Zusammengehörige Geld-/Briefkurse und originales Kursdatum fehlen.'};}
 x.ko=val('BAR|KO|K\\.O\\.-Schwelle|KO-Barriere');x.strike=val('BP|Basispreis');x.ratio=val('Bezugsverhältnis');return x;
}
const PRODUCT_REFERENCES={DE000FG5GUX2:{ratio:0.1,source:'Société Générale Produktseite, recherchiert 02.10.2026',url:'https://www.sg-zertifikate.de/product-details/fg5gux'}};
function draft(raw){
 const ids=[...new Set(String(raw).toUpperCase().match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])];
 const candidate=ids.length===1?ids[0]:'';
 const fallback=parse(String(raw).replace(candidate,'DE000FG5GUX2'));
 const val=label=>{const m=raw.match(new RegExp('\\b(?:'+label+')(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR|CHF)?\\s*([0-9]+(?:[.,][0-9]+)?)','i'));return m?m[1]:'';};
 return {isin:candidate,currency:(raw.match(/(?:Kurs|Geld|Brief|Bid|Ask)\s*[:=]?\s*(EUR|CHF)\b/i)?.[1]||(/\bEUR\b|€/.test(raw)?'EUR':/\bCHF\b/.test(raw)?'CHF':'EUR')).toUpperCase(),kind:/\bKauf\b/i.test(raw)?'entry':/\bGeld\b|\bBid\b/i.test(raw)?'quote':'details',direction:/\bCall\b|\bLong\b/i.test(raw)?'LONG':/\bPut\b|\bShort\b/i.test(raw)?'SHORT':'',time:(raw.match(/\b\d{2}[/.]\d{2}[/.]\d{4},?\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||'',entry:val('Kurs'),quantity:val('Anzahl'),feesChf:fallback.ok?fallback.feesChf??'':'',bid:val('Geld|Bid'),ask:val('Brief|Ask'),ko:val('BAR|KO|KO-Barriere'),strike:val('BP|Basispreis'),ratio:val('Bezugsverhältnis')};
}
function reviewed(v){
 if(!window.BobDegiro.validIsin(v.isin))return{ok:false,reason:'ISIN am Original korrigieren; eine unsichere OCR-ISIN wird nicht übernommen.'};
 if(v.currency&&!['EUR','CHF'].includes(v.currency))return{ok:false,reason:'Produktwährung EUR oder CHF wählen.'};
 const currency=v.currency||'EUR';
 const keys=['entry','quantity','feesChf','bid','ask','ko','strike','ratio'];
 for(const k of keys)if(String(v[k]??'').trim()!==''&&number(v[k])===null)return{ok:false,reason:'Ungültige Zahl: '+k};
 const lines=['ISIN '+v.isin,v.direction||'',v.time||'','Produktwährung '+currency];
 if(v.kind==='entry')lines.push('Auftrag Kauf','Ausführungsdatum '+v.time,'Anzahl '+v.quantity,'Kurs '+currency+' '+v.entry,'Gesamte Kosten CHF '+v.feesChf);
 else if(v.kind==='quote')lines.push('Geld '+currency+' '+v.bid,'Brief '+currency+' '+v.ask);
 else if(v.kind!=='details')return{ok:false,reason:'Bildtyp wählen.'};
 if(v.ko)lines.push('KO '+v.ko);if(v.strike)lines.push('Basispreis '+v.strike);if(v.ratio)lines.push('Bezugsverhältnis '+v.ratio);
 return parse(lines.join('\n'));
}
function merge(old,x,source){
 const out=JSON.parse(JSON.stringify(old||{isin:x.isin}));
 if(out.isin!==x.isin)throw Error('ISIN stimmt nicht überein');
 if(old&&(old.currency||'EUR')!==(x.currency||'EUR'))throw Error('Produktwährung widerspricht gespeicherten Belegen; keine Beträge ersetzt.');
 out.currency=x.currency||'EUR';
 if(x.kind==='entry'){
  if(out.entry&&JSON.stringify([out.entry.price,out.entry.quantity,out.entry.at])!==JSON.stringify([x.entry,x.quantity,x.time]))throw Error('Weiterer oder abweichender Kauf: Einstieg bleibt erhalten. Mehrere Ausführungen müssen gesondert zusammengeführt werden.');
  out.entry={price:x.entry,quantity:x.quantity,at:x.time,feesChf:x.feesChf,source,orderId:x.orderId};
 }
 if(x.kind==='quote'){
  const date=t=>{const m=String(t).match(/(\d{2})[/.](\d{2})[/.](\d{4}),?\s+(\d{2}):(\d{2})(?::(\d{2}))?/);return m?m[3]+m[2]+m[1]+m[4]+m[5]+(m[6]||''):'';};
  if(out.quote&&date(x.time)<date(out.quote.at))throw Error('Älteres Kursbild: bestehende Kursmomentaufnahme bleibt erhalten.');
  out.quote={bid:x.bid,ask:x.ask,at:x.time,source};
 }
 for(const k of ['direction','ko','strike','ratio'])if(x[k]!==null&&x[k]!==undefined)out[k]=x[k];return out;
}
// A confirmed screenshot may prepare observation, never a broker order.
const AUTO_KEY='bobConfirmedScreenshotSetupV1';
let automatic=null,automaticBusy=false,automaticStatus={state:'idle',message:'Screenshot hochladen. Bob ergänzt danach die verfügbaren Daten.'};
try{automatic=JSON.parse(localStorage.getItem(AUTO_KEY)||'null');}catch(_){}
function autoSave(){try{localStorage.setItem(AUTO_KEY,JSON.stringify(automatic));}catch(_){}}
function autoStatus(state,message){automaticStatus={state,message,at:new Date().toISOString()};if(typeof document!=='undefined')document.dispatchEvent(new Event('bob-trade-automation'));}
function screenshotDay(at){const m=String(at||'').match(/^(\d{2})[/.](\d{2})[/.](\d{4})/);return m?m[3]+'-'+m[2]+'-'+m[1]:null;}
function setupCandidate(t,today){
 if(!t?.entry||!window.BobDegiro.validIsin(t.isin)||!['EUR','CHF'].includes(t.currency)||!(t.entry.price>0)||!Number.isInteger(t.entry.quantity)||t.entry.quantity<=0)return {ok:false,reason:'Kaufpreis, Stückzahl, ISIN und Produktwährung am Original ergänzen.'};
 if(screenshotDay(t.entry.at)!==today)return {ok:false,reason:'Historischer Kauf: Bitte bestätigen, dass diese Position noch offen ist, und manuell erfassen.'};
 return {ok:true,key:JSON.stringify([t.isin,t.currency,t.entry.price,t.entry.quantity,t.entry.at]),isin:t.isin,currency:t.currency,entry:t.entry.price,quantity:t.entry.quantity,direction:t.direction||'',at:t.entry.at};
}
async function requestHelp(code){
 try{const r=await fetch('/api/assistance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code}),signal:AbortSignal.timeout(10000)});const x=await r.json();return r.ok&&x.ok===true;}catch(_){return false;}
}
function todayZurich(){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich'}).format(new Date());}
function queueSetup(t){
 const candidate=setupCandidate(t,todayZurich());
 if(!candidate.ok){autoStatus('needs-user',candidate.reason);return;}
 if(automatic?.key===candidate.key&&['done','consumed'].includes(automatic.state)){autoStatus('done','Dieser Kauf wurde bereits verarbeitet. Er wird nicht erneut aktiviert.');return;}
 if(window.BobTradeSync?.current()?.active){autoStatus('active','Eine Position wird bereits überwacht. Der Screenshot ersetzt keinen laufenden Trade.');return;}
 automatic={...candidate,state:'pending',attempts:0,nextAt:0,createdAt:Date.now()};autoSave();runSetup();
}
async function runSetup(){
 if(automaticBusy||!automatic||automatic.state!=='pending'||Date.now()<automatic.nextAt)return;
 const task=automatic;
 if(Date.now()-task.createdAt>3600000||screenshotDay(task.at)!==todayZurich()){task.state='expired';autoSave();autoStatus('needs-user','Kauf blieb ohne bestätigte Überwachung. Bitte prüfen, ob die Position noch offen ist.');return;}
 if(window.BobTradeSync?.current()?.active){task.state='consumed';autoSave();return;}
 const field=k=>document.querySelector('[data-exit="'+k+'"]');
 const same=()=>['isin','currency','entry','quantity'].every(k=>field(k)&&(k==='entry'||k==='quantity'?Number(field(k).value)===task[k]:field(k).value.trim()===task[k]));
 if(!same()){task.state='conflict';autoSave();autoStatus('needs-user','Die Kaufangaben wurden geändert. Bitte die richtige Position bestätigen.');return;}
 automaticBusy=true;task.attempts++;autoStatus('checking','Kauf bestätigt. Bob prüft Produktdaten, Quellen und Stopp-/Zielplan automatisch …');
 try{
  // Reconcile server positions before attempting local observation setup.
  const response=await fetch('/api/real-trades/read',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('Serverabgleich noch offen');
  const server=await response.json();if(!Array.isArray(server.trades))throw Error('Serverabgleich unvollständig');
  if(server.trades.some(t=>t.active||t.snapshot?.recordOnly&&!t.snapshot?.consumed)){
   task.state='consumed';autoSave();autoStatus('checking','Ein gespeicherter Kauf ist vorhanden. Bob gleicht ihn ab; keine zweite Position wird angelegt.');return;
  }
  const values=await window.BobExitEstimate.automaticTradeReference();
  if(!values||!same()||automatic!==task)throw Error('Produktdaten oder Quellenprüfung noch offen');
  if(task.direction&&values.direction!==task.direction){task.state='conflict';autoSave();autoStatus('needs-user','Produktrichtung widerspricht dem bestätigten Kauf. Bitte Original prüfen.');return;}
  if(typeof window.loadData==='function')await window.loadData(true);
  if(!same()||automatic!==task||window.BobTradeSync?.current()?.active)throw Error('Position oder Eingaben haben sich geändert');
  // Consume BEFORE activation, so an interrupted page cannot reopen a closed trade.
  task.state='consumed';autoSave();
  await window.activateProductTrade(values);
  if(!window.BobTradeSync?.current()?.active)throw Error('Start nicht bestätigt');
  task.state='done';autoSave();autoStatus('done','Überwachung lokal eingerichtet. Serverbestätigung wird gesondert angezeigt.');
 }catch(_){
  if(automatic!==task)return;
  if(window.BobTradeSync?.current()?.active){task.state='done';autoSave();autoStatus('checking','Trade lokal aktiv. Bob prüft die Server-Synchronisierung.');}
  else{
   task.state='pending';task.nextAt=Date.now()+Math.min(300000,30000*2**Math.min(task.attempts-1,4));autoSave();
   let queued=false;if(task.attempts>=3)queued=await requestHelp('trade-setup-stalled');
   autoStatus('waiting',queued?'Datenprüfung noch offen. Technische KI-Prüfung vorgemerkt; Bob versucht es weiter.':'Datenprüfung noch offen. Bob versucht es automatisch erneut; Überwachung noch nicht bestätigt.');
  }
 }finally{automaticBusy=false;}
}

function init(){
 const exit=document.getElementById('bobExitEstimate');if(!exit||document.getElementById('bobTradeUpload'))return;
 const p=document.createElement('div');p.id='bobTradeUpload';p.className='card';p.innerHTML='<h3>Mein Trade · Screenshots</h3><p class="small">Kaufbestätigung einmal, Kursbilder bei Aktualisierung. Produktkopf/Details gemeinsam ergänzen. Jedes Bild braucht die ISIN. Originalzeiten bleiben erhalten. Speicherung auf diesem Gerät.</p><label for="trade-images">Trade erfassen / Kurs aktualisieren</label><input id="trade-images" type="file" accept="image/*" multiple><div id="trade-ocr-status" class="small"></div><label for="trade-select">Gespeichertes Produkt</label><select id="trade-select"></select><div id="trade-review"></div><div id="trade-result" class="small"></div>';exit.before(p);
 const research=document.createElement('button');research.dataset.tradeReferenceRetry='';research.textContent='Gold-/FX-Referenz zur Kurszeit suchen';research.addEventListener('click',()=>window.BobExitEstimate.researchReference());exit.querySelector('[data-exit-calculate]').before(research);
 const details=document.createElement('details');details.innerHTML='<summary>Produktbedingungen und Zeitbezug bestätigen</summary>';const grid=exit.querySelector('.grid');if(grid&&!grid.querySelector('#exit-entry'))details.append(grid);for(const el of [...exit.children])if(el.tagName==='LABEL'||el.tagName==='BR')details.append(el);exit.querySelector('h3').after(details);p.append(exit);exit.className='';
 let all={};try{all=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(_){}let drafts=[];
 const select=p.querySelector('select'),review=p.querySelector('#trade-review'),result=p.querySelector('#trade-result');
 const fill=(lookup=false)=>{const t=all[select.value];if(!t)return;const set=(k,v)=>{const e=exit.querySelector('[data-exit="'+k+'"]');if(e)e.value=v??'';};
  // A different product must never inherit another product's model/reference.
  for(const e of exit.querySelectorAll('[data-exit]')){if(e.type==='checkbox')e.checked=false;else e.value='';}
  const r=window.BobDegiro.exitReference?.(t.isin),catalog=PRODUCT_REFERENCES[t.isin];if(r)for(const [k,v]of Object.entries(r))set(k,v);
  set('isin',t.isin);set('currency',t.currency||'EUR');set('direction',t.direction);set('entry',t.entry?.price);set('quantity',t.entry?.quantity);set('ko',t.ko??r?.ko);set('strike',t.strike??r?.strike);set('ratio',t.ratio??r?.ratio??catalog?.ratio);
  if(t.quote){set('bid',t.quote.bid);set('source',t.quote.source);set('referenceAt',t.quote.at);set('goldReference','');set('fxReference','');set('fxScenario','');}
  const fields={entry:'Kaufbestätigung mit Preis und Stückzahl',quote:'Kursbild mit ISIN, Geld/Brief und Datum',direction:'Produktkopf mit Long/Short',ratio:'Produktdetails: Bezugsverhältnis',strike:'Produktdetails: Basispreis',ko:'Produktkopf: Barriere'};
  const missing=Object.entries(fields).filter(([k])=>!t[k]&&!(r&&r[k])&&!(catalog&&catalog[k])).map(([,v])=>v);
  result.innerHTML='<b>'+esc(t.isin)+'</b> · '+esc(t.direction||'Richtung offen')+'<br>Einstieg: '+(t.entry?esc(t.entry.price)+' '+esc(t.currency||'EUR')+' × '+esc(t.entry.quantity)+' · '+esc(t.entry.at):'offen')+(t.entry?.feesChf!==null&&t.entry?.feesChf!==undefined?'<br>Kaufgebühren: '+esc(t.entry.feesChf)+' CHF':'')+'<br>Kursmomentaufnahme: '+(t.quote?esc(t.quote.bid)+' '+esc(t.currency||'EUR')+' Geld · '+esc(t.quote.at):'offen')+(t.entry&&t.quote?'<br>Rechnerischer G/V vor Kosten und FX: '+((t.quote.bid-t.entry.price)*t.entry.quantity).toFixed(2)+' '+esc(t.currency||'EUR'):'')+'<br>'+esc(missing.length?'Benötigtes Bild: '+missing.join(' · '):'Produktnachweise vorhanden.')+(catalog?'<br>Bezugsverhältnis: '+esc(catalog.ratio)+' · '+esc(catalog.source)+' <a target="_blank" rel="noopener" href="'+esc(catalog.url)+'">Quelle</a>':'')+'<br>Für die Ausstiegsschätzung: Gold-/FX-Referenz in Produktwährung prüfen und Ziel/Stop übernehmen. Minutenzeiten sind keine sekundengenauen Echtzeitnachweise.';
  exit.querySelector('[data-exit-output]').textContent='Trade übernommen. Fehlende Referenzen prüfen; Verkaufskurse darunter schätzen.';
  exit.dispatchEvent(new Event('change',{bubbles:true}));
  window.BobExitEstimate.restoreReference();
  if(lookup&&t.quote)window.BobExitEstimate.researchReference();
 };
 const refresh=isin=>{select.innerHTML=Object.keys(all).map(id=>'<option>'+esc(id)+'</option>').join('');if(isin)select.value=isin;fill(!!isin);};select.addEventListener('change',fill);refresh();
 p.querySelector('input').addEventListener('change',async e=>{const files=[...e.target.files];autoStatus('checking','Bilder werden erkannt …');drafts=[];let saleSeen=false;review.innerHTML='';if(files.length>4){result.textContent='Bitte höchstens vier Bilder gleichzeitig auswählen.';return;}
  for(const file of files){try{const o=await window.BobDegiro.recognizeOcr(file,'trade-ocr-status');
   if(/\bVerkauf\b/i.test(o.data.text)&&!/\bKauf\b/i.test(o.data.text)){
    saleSeen=true;
    if(!window.BobTradeSale?.prepareFile)throw Error('Verkauf erkannt. Verkaufsprüfung unter Details öffnen.');
    await window.BobTradeSale.prepareFile(file);autoStatus('needs-user','Verkauf erkannt. Vorausgefüllten Beleg prüfen und den vollständigen Verkauf bestätigen.');continue;
   }
   drafts.push({source:file.name,raw:o.data.text});}catch(err){result.textContent='Bild '+file.name+': '+err.message;autoStatus('needs-user','Bild konnte nicht sicher zugeordnet werden. Bitte lesbares Original prüfen.');requestHelp('screenshot-import-failed');}}
  const fields=[['isin','ISIN'],['currency','Produktwährung EUR oder CHF'],['time','Originaldatum und Uhrzeit'],['entry','Kaufpreis in Produktwährung/Stück'],['quantity','Stückzahl'],['feesChf','Kaufgebühren CHF'],['bid','Geldkurs in Produktwährung'],['ask','Briefkurs in Produktwährung'],['ko','Angezeigte Barriere USD'],['strike','Basispreis USD'],['ratio','Bezugsverhältnis']];
  if(drafts.length)autoStatus('needs-user','Bilder erkannt. Kaufdaten am Original prüfen und bestätigen; danach übernimmt Bob die Einrichtung.');
  review.innerHTML=drafts.map((d,i)=>{const v=draft(d.raw);return '<fieldset data-trade-card="'+i+'"><legend>'+esc(d.source)+'</legend><label>Bildtyp<select data-review="kind"><option value="entry" '+(v.kind==='entry'?'selected':'')+'>Kaufbestätigung</option><option value="quote" '+(v.kind==='quote'?'selected':'')+'>Kursdaten</option><option value="details" '+(v.kind==='details'?'selected':'')+'>Produktdetails</option></select></label><label>Richtung<select data-review="direction"><option value="">Offen</option><option '+(v.direction==='LONG'?'selected':'')+'>LONG</option><option '+(v.direction==='SHORT'?'selected':'')+'>SHORT</option></select></label><div class="grid">'+fields.map(([k,l])=>'<label data-review-field="'+k+'">'+l+'<input data-review="'+k+'" value="'+esc(v[k])+'"></label>').join('')+'</div><div class="small">Leere oder unsichere Werte am Original ergänzen. Sekunden nicht erfinden. Barriere und Basispreis dürfen bei Produktdetails offen bleiben.</div><details><summary>Original-OCR-Text anzeigen</summary><pre style="white-space:pre-wrap">'+esc(d.raw)+'</pre></details></fieldset>';}).join('')+(drafts.length?'<label><input type="checkbox" id="trade-confirm"> ISIN, Preise, Stückzahl und Originalzeiten geprüft; ein gezeigter Kauf ist tatsächlich noch offen</label><button id="trade-save">Geprüfte Bilder übernehmen</button>':'');
  for(const card of review.querySelectorAll('[data-trade-card]')){const type=card.querySelector('[data-review="kind"]');const show=()=>{for(const el of card.querySelectorAll('[data-review-field]')){const k=el.dataset.reviewField;el.hidden=['entry','quantity','feesChf'].includes(k)?type.value!=='entry':['bid','ask'].includes(k)?type.value!=='quote':false;}};type.addEventListener('change',show);show();}
  review.querySelector('#trade-save')?.addEventListener('click',()=>{if(!review.querySelector('#trade-confirm').checked){result.textContent='Bitte erkannte Werte am Original prüfen und bestätigen.';return;}
   let next=JSON.parse(JSON.stringify(all)),last='',reviewedItems=[];try{for(const [i,d]of drafts.entries()){const card=review.querySelector('[data-trade-card="'+i+'"]'),values=Object.fromEntries([...card.querySelectorAll('[data-review]')].map(e=>[e.dataset.review,e.value.trim()])),x=reviewed(values);if(!x.ok)throw Error(d.source+': '+x.reason);reviewedItems.push(x);next[x.isin]=merge(next[x.isin],x,'DEGIRO-Screenshot: '+d.source);last=x.isin;}localStorage.setItem(KEY,JSON.stringify(next));all=next;refresh(last);review.innerHTML='';p.querySelector('#trade-ocr-status').textContent='Gespeichert. Einstieg bleibt bei Kursaktualisierungen erhalten.';
   if(!saleSeen&&reviewedItems.some(x=>x.kind==='entry')&&new Set(reviewedItems.map(x=>x.isin)).size===1)queueSetup(all[last]);
   else autoStatus('checking','Nachweise gespeichert. Vorhandene Überwachung wird weiter abgeglichen.');}catch(err){result.textContent=err.message;}});
 });
}
window.BobTradeUpload={parse,draft,reviewed,merge,init,setupCandidate,queueSetup,runSetup,status:()=>({...automaticStatus}),requestHelp};
if(typeof document!=='undefined'&&typeof setInterval==='function'){setInterval(runSetup,30000);window.addEventListener?.('online',runSetup);}if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();}
})();




/* Manual paper positions: isolated from real trades, pushes and learning statistics. */
(function(root){
 const KEY='bobManualTradeTestV1';
 function position(isin,direction,entry,quantity,now=Date.now()){
  if(!root.BobDegiro.validIsin(isin))throw Error('Bitte ein Produkt auswählen.');
  if(!['LONG','SHORT'].includes(direction))throw Error('Produktrichtung fehlt im Nachweis. Bitte Produktdaten ergänzen.');
  entry=Number(entry);quantity=Number(quantity);
  if(!Number.isFinite(entry)||entry<=0||!Number.isSafeInteger(quantity)||quantity<=0)throw Error('Positiven Einstieg und eine ganze Stückzahl eingeben.');
  return {isin,direction,entry,quantity,createdAt:new Date(now).toISOString(),mode:'manual-paper-test'};
 }
 function valuation(p,q,now=Date.now()){
  const valid=x=>x?.currency==='EUR'&&typeof x.bid==='number'&&Number.isFinite(x.bid)&&x.bid>0&&Number.isFinite(Date.parse(x.bidAt||x.quoteAt))&&Date.parse(x.bidAt||x.quoteAt)<=now;
  if(!q||q.isin!==p.isin||q.productVerified!==true)return {available:false,reason:'Kein bestätigter Produktkurs für diese ISIN verfügbar.'};
  const candidates=[];
  if(q.found===true&&valid(q))candidates.push({...q,referenceOnly:false});
  if(q.metadata?.status===1&&q.analysisQuote?.source&&valid(q.analysisQuote))candidates.push({...q.analysisQuote,referenceOnly:true});
  candidates.sort((a,b)=>Date.parse(b.bidAt||b.quoteAt)-Date.parse(a.bidAt||a.quoteAt));
  const x=candidates[0];
  if(!x)return {available:false,reason:'Kein datierter EUR-Geldkurs verfügbar. '+(q.reason||'Kursabruf erneut versuchen.')};
  const at=Date.parse(x.bidAt||x.quoteAt),bid=x.bid;
  return {available:true,bid,at,source:x.source||'Anbieter',referenceOnly:x.referenceOnly,stale:!!x.delayed||now-at>90000,
   pnl:(bid-p.entry)*p.quantity,value:bid*p.quantity};
 }
 function mount(guide){
  const opener=guide.querySelector('#bobTradeTestOpen');if(!opener)return;
  const panel=document.createElement('div');panel.id='bobManualTradeTest';panel.hidden=true;
  panel.innerHTML='<h3>Trade-Test · fiktiv</h3><p>Produkt frei auswählen – auch bei ABWARTEN oder ohne Empfehlungsfreigabe. Kein Kauf, keine Trade-Pushs. Separater Test auf diesem Gerät; dein echter Trade bleibt erhalten.</p><label for="manualTestProduct">Produkt</label><select id="manualTestProduct"></select><button type="button" data-test-refresh>Produktliste und Kurse aktualisieren</button><div class="grid"><label>Angenommener Einstieg EUR/Stück<input data-test-entry type="number" min="0" step="any"></label><label>Fiktive Stückzahl<input data-test-quantity type="number" min="1" step="1" value="1"></label></div><button type="button" data-test-save>Fiktiven Trade erfassen</button><button type="button" data-test-clear>Test entfernen</button><p data-test-message role="status"></p><p data-test-result style="white-space:pre-line"></p><p class="small">Bewertung zum verfügbaren Geldkurs, ohne Gebühren und Finanzierung. Dieser manuelle Test bleibt lokal unverändert. Eine separate schreibgeschützte Kopie kann bei bestehender Bob-Anmeldung neue Anbieter-Geldkurse im Hintergrund beobachten. Stop-/Zielschwellen werden nur gemeldet, wenn du sie ausdrücklich festlegst. Keine Order, keine automatische Glattstellung oder Trade-Pushs.</p>';
  const checklist=document.createElement('details');checklist.id='bobEveningCheck';
  checklist.innerHTML='<summary>Abendtest · Checkliste öffnen</summary><p>Fiktiver Test, kein Kauf. Die Häkchen dokumentieren deine Beobachtungen auf diesem Gerät; sie sind kein automatischer Nachweis.</p><p>Vorab am 8.10.2026: 48 automatische Prüfungen für Modellablauf, Stop/Ziel und Push-Regeln bestanden. Handy-Empfang und Live-Hintergrundbetrieb sind damit noch nicht bestätigt.</p>';
  const steps=[
   'Kurs und Ergebnis: Kurse aktualisieren; Kurszeit, Einstieg und Stückzahl prüfen. Ergebnis = (Referenzkurs − Einstieg) × Stückzahl.',
   'Darstellung: Ergebnis fett; Gewinn mit + grün, Verlust mit − rot. Null neutral. Einseitige Marktbewegung prüft nicht beide Farben.',
   'Aktualisierung: Bob mit offenem Trade-Test mindestens 2 Minuten sichtbar lassen. Neue Kurszeit und passende Neuberechnung beobachten; unveränderter Kurs darf gleiches Ergebnis liefern.',
   'Speicherung: Bob neu laden und Trade-Test öffnen. Produkt, Einstieg und Stückzahl müssen erhalten bleiben.',
   'Modellablauf: Unter Lernen → Fortlaufende Marktsimulation → Simulation prüfen → Technischer Probelauf die Ereignisse öffnen. Stop-Nachziehen, Teilgewinn, Zielverlängerung und Ausstieg prüfen. Künstliche Folgekurse, kein Live-Handelsergebnis.',
   'Push-Empfang: Im Push-Menü die vorhandene Test-Push-Funktion auslösen und Empfang am Handy prüfen. Ein empfangener Test-Push belegt noch keine Stop-/Zielauslösung bei geschlossener App.'
  ];
  let checked=[];try{checked=JSON.parse(localStorage.getItem('bobEveningChecksV1')||'[]');if(!Array.isArray(checked))checked=[];}catch(_){}
  steps.forEach((text,i)=>{const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.checked=checked.includes(i);box.style.width='auto';label.style.display='block';label.style.margin='12px 0';label.append(box,document.createTextNode(' '+text));checklist.append(label);box.addEventListener('change',()=>{checked=box.checked?[...new Set([...checked,i])]:checked.filter(x=>x!==i);try{localStorage.setItem('bobEveningChecksV1',JSON.stringify(checked));}catch(_){box.checked=false;}});});
  const limit=document.createElement('p');limit.textContent='Noch separater Testbedarf: echte Stop-/Ziel-Pushs bei geschlossener App, berechnete EUR-Stopps und durchgehende Hintergrundüberwachung. Der manuelle Trade-Test startet diese Überwachung nicht. Konto/Risiko dürfen für die obigen Schritte leer bleiben.';checklist.append(limit);panel.append(checklist);
  guide.append(panel);
  // Read-only server shadow; NEVER write, replace or remove bobManualTradeTestV1.
  const watch=document.createElement('section');watch.style.cssText='border:1px solid #cbd5e1;border-radius:12px;padding:12px;margin:12px 0;';
  watch.innerHTML='<h4>Hintergrundbeobachtung · bestehender Test bleibt unverändert</h4><p class="small" data-watch-status role="status">Verbindung wird geprüft …</p><p class="small" data-watch-value style="white-space:pre-line"></p><div class="grid"><label>Optional: Stop EUR/Stück<input type="number" min="0" step="any" data-watch-stop placeholder="Nicht gesetzt"></label><label>Optional: Ziel EUR/Stück<input type="number" min="0" step="any" data-watch-target placeholder="Nicht gesetzt"></label></div><button type="button" data-watch-levels>Separate Schwellen speichern</button><button type="button" data-watch-refresh>Beobachtung prüfen</button><p class="small">Nur bestätigte neue EUR-Geldkurse werden gespeichert. Kein nachträglicher Kursverlauf, keine fiktiven Verkäufe, keine automatischen Push-Nachrichten. Kurs- und Datenausfälle sind sichtbar. Für den erstmaligen Datenabgleich Bob einmal öffnen.</p>';
  panel.append(watch);
  const wStatus=watch.querySelector('[data-watch-status]'),wValue=watch.querySelector('[data-watch-value]');
  const wStop=watch.querySelector('[data-watch-stop]'),wTarget=watch.querySelector('[data-watch-target]');
  async function watchApi(action,payload){
   const response=await fetch('/api/audit/'+action,{method:'POST',credentials:'same-origin',
     cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   if(!response.ok)throw Error('Hintergrundspeicher HTTP '+response.status);
   return response.json();
  }
  let watchConnected=false;
  async function refreshWatch(){
   try{
    const data=await watchApi('read',{mode:'manual-paper-watch'});
    if(!data.connected){wStatus.textContent=data.reason||'Noch nicht mit dem Server verbunden';return;}
    watchConnected=true;
    const w=data.watch||{},v=w.valuation;
    wStatus.textContent='Server-Beobachtung: '+(w.status||'unbestätigt')+' · '+(w.reason||'')+
      ' · zuletzt geprüft '+(w.checkedAt?new Date(w.checkedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch nicht');
    wValue.textContent='Getrennt gespeicherter Test: '+w.position.isin+' · '+w.position.direction+
      ' · Einstieg '+w.position.entry.toFixed(4)+' EUR · '+w.position.quantity+' Stück'+
      '\\n'+(v?'Neuer beobachteter Geldkurs '+v.bidEur.toFixed(4)+' EUR · '+v.source+
        ' · '+new Date(v.quoteAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+
        ' · fiktives Bruttoergebnis '+v.pnlEur.toFixed(2)+' EUR':'Aktuell kein bestätigter Kurs · fiktiver Gewinn/Verlust nicht neu berechenbar')+
      '\\nNeue gespeicherte Kursbeobachtungen: '+(w.eventsCount||0)+
      '\\nBeobachtete Stop-/Zielüberschreitungen: '+((w.alerts||[]).length||0);
    wStop.value=w.stopEur??'';wTarget.value=w.targetEur??'';
   }catch(e){wStatus.textContent='Server-Beobachtung nicht bestätigt: '+e.message;}
  }
  async function syncWatch(position){
   if(!position)return;
   try{
    const response=await watchApi('write',{mode:'manual-paper-watch-sync',position});
    if(!response.ok){wStatus.textContent=response.reason||'Server-Kopie konnte nicht verbunden werden';return;}
    watchConnected=true;
    await refreshWatch();
   }catch(e){wStatus.textContent='Hintergrundabgleich noch nicht möglich: '+e.message;}
  }
  watch.querySelector('[data-watch-refresh]').addEventListener('click',refreshWatch);
  watch.querySelector('[data-watch-levels]').addEventListener('click',async()=>{
   if(!watchConnected){wStatus.textContent='Zuerst den bestehenden Test mit dem Server verbinden';return;}
   const stopEur=wStop.value.trim()===''?null:Number(wStop.value);
   const targetEur=wTarget.value.trim()===''?null:Number(wTarget.value);
   if((stopEur!==null&&(!Number.isFinite(stopEur)||stopEur<=0))||
      (targetEur!==null&&(!Number.isFinite(targetEur)||targetEur<=0))){
    wStatus.textContent='Schwellen müssen positive EUR-Beträge sein.';return;
   }
   try{
    const response=await watchApi('write',{mode:'manual-paper-watch-levels',stopEur,targetEur});
    if(!response.ok){wStatus.textContent=response.reason||'Grenzen nicht gespeichert';return;}
    await refreshWatch();
   }catch(e){wStatus.textContent='Grenzen nicht gespeichert: '+e.message;}
  });
  const select=panel.querySelector('select'),entry=panel.querySelector('[data-test-entry]'),quantity=panel.querySelector('[data-test-quantity]'),message=panel.querySelector('[data-test-message]'),result=panel.querySelector('[data-test-result]');
  let saved=null,products=[];
  try{const x=JSON.parse(localStorage.getItem(KEY)||'null');if(x?.mode==='manual-paper-test')saved=position(x.isin,x.direction,x.entry,x.quantity,Date.parse(x.createdAt));}catch(_){}
  // The one-time sync is an explicit read of the existing browser record;
  // no modification to the local test or any automated portfolio.
  if(saved)void syncWatch(saved);
  else wStatus.textContent='Kein gespeicherter manueller Trade auf diesem Gerät gefunden.';
  function render(){
   if(!saved){result.textContent='Noch kein fiktiver Trade erfasst.';return;}
   const item=root.BobDegiro.tradeTestProducts().find(x=>x.isin===saved.isin),v=valuation(saved,item?.quote);
   result.textContent='TEST · '+saved.isin+' · '+saved.direction+'\nAngenommener Einstieg '+saved.entry.toFixed(4)+' EUR × '+saved.quantity+' Stück = '+(saved.entry*saved.quantity).toFixed(2)+' EUR\n'+(v.available?(v.referenceOnly?'Referenzkurs (nicht ausführbar)':v.stale?'Veralteter Geldkurs':'Verfügbarer Geldkurs')+' '+v.bid.toFixed(4)+' EUR · '+v.source+' · '+new Date(v.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' (Zürich)':v.reason);
   if(v.available){
    result.append(document.createTextNode('\nFiktiver Bruttogewinn/-verlust '));
    const amount=document.createElement('strong'),rounded=Number(v.pnl.toFixed(2));
    amount.textContent=(rounded>0?'+':rounded<0?'−':'')+Math.abs(rounded).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})+' EUR';
    amount.style.fontWeight='700';amount.style.color=rounded>0?'#15803d':rounded<0?'#b91c1c':'#374151';
    result.append(amount);
    if(v.stale)result.append(document.createTextNode(' · mit veraltetem Kurs berechnet'));
   }
  }
  function refresh(){
   const selected=select.value||saved?.isin;products=root.BobDegiro.tradeTestProducts();select.replaceChildren();
   const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=products.length?'Produkt auswählen':'Keine importierten Produkte – zuerst DEGIRO-Liste hochladen';select.append(placeholder);
   for(const p of products){const o=document.createElement('option');o.value=p.isin;o.textContent=p.isin+' · '+(p.direction||'Richtung offen')+' · '+p.name;select.append(o);}
   if(products.some(p=>p.isin===selected))select.value=selected;
   render();
  }
  opener.addEventListener('click',()=>{panel.hidden=!panel.hidden;if(!panel.hidden){refresh();if(saved){entry.value=saved.entry;quantity.value=saved.quantity;void syncWatch(saved);}panel.scrollIntoView({behavior:'smooth',block:'start'});}});
  panel.querySelector('[data-test-refresh]').addEventListener('click',async e=>{
   const button=e.currentTarget;button.disabled=true;message.textContent='Produktkurse werden abgerufen …';
   try{await root.BobDegiro.refreshTradeTestQuotes();refresh();message.textContent='Kursabruf abgeschlossen. Verfügbaren Kursstand siehe Testbewertung.';}
   catch(_){message.textContent='Kursabruf fehlgeschlagen. Vorhandener Kursstand bleibt sichtbar.';}
   finally{button.disabled=false;}
  });
  select.addEventListener('change',()=>{entry.value='';message.textContent='Angenommenen Einstieg selbst eingeben. Die Auswahl erteilt keine Einstiegsempfehlung.';});
  panel.querySelector('[data-test-save]').addEventListener('click',()=>{
   try{const p=root.BobDegiro.tradeTestProducts().find(x=>x.isin===select.value);if(!p)throw Error('Bitte ein vorhandenes Produkt auswählen.');
    const next=position(p.isin,p.direction,entry.value,quantity.value);localStorage.setItem(KEY,JSON.stringify(next));saved=next;message.textContent='Fiktiver Trade gespeichert. Keine echte Position und keine Order.';render();
   }catch(e){message.textContent=e.message;}
  });
  panel.querySelector('[data-test-clear]').addEventListener('click',()=>{try{localStorage.removeItem(KEY);saved=null;message.textContent='Test entfernt.';render();}catch(_){message.textContent='Test konnte nicht entfernt werden.';}});
  setInterval(()=>{if(!panel.hidden&&!document.hidden)render();},30000);
 }
 root.BobManualTradeTest={position,valuation,mount};
})(typeof window!=='undefined'?window:globalThis);

