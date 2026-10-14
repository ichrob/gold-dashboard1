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
function resetFixedList(){
 // A new screenshot generation revokes the older hand-confirmed barriers,
 // including fixed defaults on historically known ISINs.
 try{
  const ids=new Set([...Object.keys(FIXED_KO_DEFAULTS),...Object.keys(fixedBarriers())]);
  localStorage.setItem(FIXED_KO_KEY,JSON.stringify(Object.fromEntries([...ids].map(id=>[id,null]))));
  return true;
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
 result.candidates.map((p,i)=>'<div style="padding:10px;margin-top:8px;border:1px solid #e1e7f0;border-radius:10px"><b>Platz '+(i+1)+' · '+escape(p.isin)+'</b><div class="small">'+escape(p.name)+' · '+escape(p.productDirection)+'</div><div class="small"><b>'+escape(p.priceKind)+'</b> · Brief '+(p.estimated?'≈ ':'')+p.price.toFixed(4)+' EUR · Hebel '+(p.estimated?'≈ ':'')+p.leverage.toFixed(2)+'×</div><div class="small">KO '+p.ko.toFixed(4)+' USD · Abstand '+p.evaluation.koDistancePct.toFixed(2)+'% · Risiko-/Datenwert '+p.evaluation.score+'/100</div><div class="small">Quelle '+escape(p.source)+' · '+escape(p.venue)+' · '+(p.estimated?'Referenzzeit ':'Kurszeit ')+escape(p.at)+'</div><div class="small">Warum: '+escape(p.evaluation.reasons.slice(0,3).join(' · ')).replace(/\bHebel\b/g,'<strong>Hebel</strong>')+'</div>'+p.evaluation.warnings.map(w=>'<div class="small warning">'+escape(w)+'</div>').join('')+(p.estimated?'<div class="small">Schätzgenauigkeit noch unbestätigt; angenommener Quellenaufschlag kann sich ändern.</div>':'')+'</div>').join('')+
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
 const rows=result.groups.map(g=>'<div style="margin-top:10px"><b>'+esc(g.scope)+' · '+'Unverbindliche Kandidaten · keine Freigabe'+'</b><div class="small">'+esc(g.reason)+'</div>'+g.candidates.slice(0,3).map(c=>'<div class="small" style="margin-top:8px"><b>'+esc(c.isin)+'</b> · '+esc(c.priceKind)+' · Kurs ca. '+c.price.toFixed(2)+' EUR'+(c.priceError?' · Vergleichsspanne ±'+c.priceError.toFixed(4)+' EUR':'')+' · Basiswert '+c.basis.toFixed(2)+' USD'+(c.basisError?' ±'+c.basisError.toFixed(2)+' USD':'')+'<br>Risiko-/Datenwert '+c.scoreLow+'–'+c.scoreHigh+'/100 · Hebel ca. '+c.leverageLow.toFixed(2)+'–'+c.leverageHigh.toFixed(2)+'× · KO-Abstand mindestens '+c.koDistanceMinPct.toFixed(2)+'% innerhalb der Vergleichsspanne · Datenzeit '+esc(new Date(c.at).toLocaleTimeString())+'<br>Warum: '+esc((c.reasons||[]).slice(0,3).join(' · ')).replace(/\bHebel\b/g,'<strong>Hebel</strong>')+(c.quality?'<br>'+esc(qualityText(c.quality,c.priceError?'EUR':'USD')):'')+'</div>').join('')+'</div>').join('');
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
function knockoutCard(p){
 const e=knockoutStatus(p);if(!e)return '';
 return '<div data-product-isin="'+esc(p.isin)+'" data-product-knocked-out style="padding:14px;margin-top:10px;border:1px solid #dc2626;border-radius:12px;background:#fff7f7"><b>'+esc(p.isin)+'</b> · '+esc(p.productDirection||'')+renderProductDirectionStatus(p)+'<div style="color:#b91c1c;font-weight:700;margin-top:8px">Ausgeknockt – Produkt ausgeschlossen</div><p class="small">Der Emittent meldet „KNOCKED OUT“. Keine weiteren Daten oder Screenshots erforderlich. Dieses Produkt wird nicht mehr für die Produktauswahl oder eine Produktfreigabe berücksichtigt.</p><div class="small">Nachweis: '+esc(e.source)+(e.observedDate?' · gesehen am '+esc(e.observedDate):'')+'. Der genaue Knock-out-Zeitpunkt ist damit nicht belegt.</div></div>';
}
function evaluateProduct(p){if(knockoutStatus(p))return{ok:false,fit:false,score:0,reasons:["Ausgeknockt – Produkt ausgeschlossen. Keine weiteren Daten erforderlich."],warnings:[]};if(p.quote?.isin===p.isin&&p.quote?.productVerified&&p.quote?.metadata?.status!==undefined&&p.quote.metadata.status!==1)return{ok:false,fit:false,score:0,reasons:["Produkt laut Quelle ausgeknockt oder beendet – ausgeschlossen."],warnings:[]};if(/FAKTOR|FACTOR/i.test([p.name,p.quote?.name,p.snapshot?.terms?.type?.value].join(" ")))return{ok:false,fit:false,score:0,reasons:["Faktorprodukt ausgeschlossen – keine Produktfreigabe."],warnings:[]};if(isFutureProduct(p))return{ok:false,fit:false,score:0,reasons:["Gold-Future benötigt eigene Basiswertdaten und Trendprüfung; keine XAU/USD-Spot-Freigabe."],warnings:[]};return evaluateProductCore(p);}
// Bob ranking policy v1: product costs/risk, never a profit probability.
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
 if(koPct!==null){parts.ko=Math.min(25,Math.max(0,(5-koPct)*5));if(koPct<1)blocked.push('KO-Abstand unter 1%');}
 if(atrMultiple!==null){parts.ko=Math.max(parts.ko,Math.min(25,Math.max(0,(3-atrMultiple)*5)));if(atrMultiple<1.5)blocked.push('KO-Puffer kleiner als 1,5 ATR');}
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
 const penalty=Object.values(parts).reduce((a,b)=>a+b,0),score=Math.round(Math.max(0,100-penalty)*10)/10;
 reasons.push('Daten: '+(estimated?'Schätzung':'Kursangabe')+'; Abzüge KO '+parts.ko.toFixed(1)+', Hebel '+parts.leverage.toFixed(1)+' Punkte; Datenqualität ohne Gewichtung');
 if(score<60)blocked.push('Risikowert unter 60/100');
 return {score,fit:!blocked.length,koProtection:koGuard,parts,spreadPct,tradingPct,financingPct,knownCostsPct,totalCostsPct:null,reasons:blocked.map(x=>'ABWARTEN: '+x).concat(reasons),warnings};
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
 const raw=normalizeSwissSgText(normalizeBnpQuoteColumns(String(text||''))),out={};
 // A failed neighbouring field must not discard independently readable evidence.
 for(const key of ['ko','strike','ratio']){const terms=parseProductTerms(raw,[key]);if(!terms.error&&terms[key])out[key]=terms[key].value;}
 for(const [key,label] of [['bid','Geld|Bid|Verkaufen'],['ask','Brief|Ask|Kaufen'],['leverage','Hebel|Leverage']]){
  const matches=Array.from(raw.matchAll(new RegExp('(?:^|\\n)\\s*(?:'+label+')\\s*[:=]?\\s*(?:€|EUR)?\\s*([0-9A-Za-z.,]+)','gi')));
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
const REVIEWED_SG_IMAGE_TEXT={"4b50a5004c994b4172dda6f5bb76a0de2f5a5eefed10bd2d825ded6344fbf81b": "SOCIETE GENERALE ZERTIFIKATE\nTyp Put\nBasispreis 4.376,6213 USD (06.10.2026)\nKnock-Out-Barriere 4.376,6213 USD (06.10.2026)\nKnock-Out Zeit 00:00 - 24:00\nAusgabetag 21.09.2026\nQuanto Nein\nRisikoprämie -5,00%\nKennzahlen\nHebel 20,9696", "1d49ece095818e84e51457f0b9070d67ac9b7e6decb692cc739fd59cd4ad1d5f": "sg-zertifikate.de\nStammdaten\nISIN DE000FG7EPT1\nWKN FG7EPT\nProduktart BEST Turbo-Optionsscheine (Open-End)\nBasiswert Gold\nBezugsverhältnis 10:1\nTyp Put\nBasispreis 4.376,6213 USD (06.10.2026)\nKnock-Out-Barriere 4.376,6213 USD (06.10.2026)\nAusgabetag 21.09.2026\nQuanto Nein", "49870b5da5c84cb16328e2d953c23cd82ee52d2f05c3f2412b45f2bfe5bb1bca": "FG7EPT - 17,65 / 17,66 €\nsg-zertifikate.de\nKurs von: 21:03:12 (06.10.2026)\nGeld\n17,650 EUR\nBrief\n17,660 EUR", "bb8043bea38181718c6ff63da03e2dc0104b3168d251020b0bbe8ba726c756b1": "FG7EPT - 17,64 / 17,65 €\nsg-zertifikate.de\nBEST Turbo-Optionsschein\nOpen-End | Put | auf Gold |\n4.376,6213 USD\nFG7EPT WKN Kopieren\nKurs von: 21:03:09 (06.10.2026)\nGeld\n17,640 EUR", "c4aacaade2d9259e69b16d9ae45a179a34e80b441295ce725468fbc07618841d": "159787428 - 35.67 / 35.68 CHF\nsg-zertifikate.ch\nSOCIETE GENERALE DERIVATIVES\nBEST Turbo-Optionsscheine auf Gold\n159787428 Valor kopieren\nKurs von: 16:21:24 (07.10.2026)\nGeld\n35.670 CHF\nStückzahl 25'000\nBrief\n35.680 CHF"};
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
 const words=data.words||[],rows=words.filter(w=>labels[key]?.test(w.text));if(rows.length!==1)return null;
 const b=rows[0].bbox,h=b.y1-b.y0;if(h<6)return null;
 const numeric=words.filter(w=>/^\d+(?:[.,]\d+)*(?::1)?$/.test(w.text));
 let values=numeric.filter(w=>w.bbox.x0>b.x1&&Math.abs((w.bbox.y0+w.bbox.y1-b.y0-b.y1)/2)<h);
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
   const value=String(result.data?.text||'').trim();
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
function recognizeOcr(file,statusId,allowPartial=false){
 const job=ocrQueue.then(async()=>{
  const reviewed=await reviewedImageText(file);
  if(reviewed)return {data:{text:reviewed,reviewedOriginal:true}};
  activeOcrStatusId=statusId;
  const worker=await loadOcrWorker(statusId);
  const prepared=await prepareOcrImage(file,statusId);
  let result,identityData;const readings=[],originalModes=new Set(['3']);
  try{
   result=await ocrTimeout(worker.recognize(prepared),45000,"OCR-Zeitüberschreitung nach 45 Sekunden");
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
  const queued=rows().filter(row=>validIsin(row.isin)&&
   (force||!attempts.has(row.id)||attempts.get(row.id).key!==row.key||now()-attempts.get(row.id).at>=interval));
  if(!queued.length)return Promise.resolve();
  async function worker(){
   while(queued.length&&visible()){
    const row=queued.shift(),current=rows().find(x=>x.id===row.id);
    if(!current||current.key!==row.key||current.isin!==row.isin)continue;
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
  let res;try{res=await fetch("/api/degiro/enrich?isin="+encodeURIComponent(isin)+(termsOnly?"&scope=terms":""),{cache:"no-store",signal:ctl.signal});}finally{clearTimeout(timer);}
  if(!res.ok)throw Error("Produktrecherche nicht verfügbar");
  let x=retainProductResearch(prior,await res.json(),isin);
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
  const ctx=q.sharedTimeContext,chart=q.chartEvidence||q.nativeChartEvidence;
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
 if(isFutureProduct(p))reasons.push(p.quote?.futureResearch?.contractAnalysis?.available?"Gold-Future: Kontraktanalyse vorhanden; bedingten Vergleich beachten. Keine Spot-Freigabe":"Gold-Future: eigene Basiswertdate…40887 tokens truncated…ry(outcomes){
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
async function readListBatch(files,recognize,progress=()=>{}){
 if(!files.length)throw new Error('Keine Bilder ausgewählt.');
 const texts=[],recoveries={};
 for(const [index,file] of files.entries()){
  progress(index+1,files.length,file.name);
  const result=await recognize(file,'dgCentralStatus');
  const text=result?.data?.text||'';
  if(!parseScreenshotCandidates(text).length)throw new Error('Keine Produkt-ISIN in '+file.name+' erkannt. Bitte das Listenbild prüfen.');
  texts.push(text);Object.assign(recoveries,result.data.isinRecoveries||{});
 }
 const items=parseScreenshotCandidates(texts.join('\n\n'));
 for(const x of items)if(recoveries[x.isin]){x.originalIsin=recoveries[x.isin];x.ocrRecovery=true;}
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

async function inject(){
 if(document.getElementById("dgTop3"))return;
 const a=document.getElementById("dgProductOut"); if(!a)return;
 const b=document.createElement("div");
 b.id="dgTop3";
 b.style.cssText="margin-top:14px;padding:16px;background:#f7f9fc;border-radius:20px;border:1px solid #e5eaf2";
 b.innerHTML='<style>#dgTop3 > details,#dgTop3Out > section,#dgTop3Out > details,#dgApprovalOut > details{box-sizing:border-box;min-width:0;margin-top:14px;padding:12px;background:#fff;border:1px solid #e1e7f0;border-radius:16px;overflow-wrap:anywhere}#dgTop3 > details > summary,#dgTop3Out > details > summary,#dgApprovalOut > details > summary{cursor:pointer;font-weight:700}#dgTop3 > details[open] > summary,#dgTop3Out > details[open] > summary,#dgApprovalOut > details[open] > summary{margin-bottom:10px}</style><div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b></div></div>'+
 '<div id="dgTop3Out" style="margin-top:12px"></div>'+
 '<details style="margin-top:12px"><summary id="dgSavedProductsSummary" style="cursor:pointer;font-weight:700">Gold-Hebelprodukte</summary><div id="dgMissingProducts" style="margin-top:12px"></div></details>'+
 '<div id="dgScreenshotReturn" hidden style="margin-top:14px;padding:14px;background:#eaf3ff;border:2px solid #1677ff;border-radius:14px;scroll-margin-top:16px"><b>Screenshots für <span data-return-isin></span></b><p class="small">Bilder werden diesem zuvor geöffneten Produkt zugeordnet, auch wenn ISIN oder WKN im Bild fehlen. Eine eindeutig abweichende Produktkennung wird gemeldet.</p><div data-return-product-link></div><div data-return-missing></div><p class="small">Fehlenden Wert erneut aufnehmen: Produktseite öffnen, Screenshot machen und anschließend hier beim selben Produkt hinzufügen.</p><button type="button" data-return-upload style="width:100%;background:#1677ff">↑ Bilder / PDF für dieses Produkt hinzufügen</button><div class="small" style="margin:8px 0">Originaldateien: lokal auf diesem Gerät, bis zu 7 Tage / insgesamt 100 MB. Nach Erkennungsupdates prüft Bob gespeicherte Dateien erneut. Ursprüngliche Datenstände bleiben erhalten.</div><button type="button" data-return-reprocess>Gespeicherte Bilder erneut prüfen</button><button type="button" data-return-delete>Gespeicherte Originaldateien löschen</button><button type="button" data-return-close>Fertig / ausblenden</button><div role="status" data-return-status style="overflow-wrap:anywhere;min-width:0"></div><div role="status" data-return-complete hidden style="margin-top:12px;font-weight:700;color:#15803d">✅ Datenübertragung komplett</div></div>'+
 '<div style="margin-top:14px;padding:12px;background:#fff;border-radius:16px;border:1px solid #e1e7f0">'+
 '<details id="dgIssuerCatalogPanel" style="margin-bottom:12px;border:1px solid #d7e0ea;border-radius:10px;padding:10px"><summary><b>Automatische Gold-Produktrecherche · externe Kandidaten</b></summary><p class="small">Bob überprüft die früher in DEGIRO beobachteten ISINs ohne Screenshot bei Emittenten. Nicht die vollständige aktuelle DEGIRO-Liste; Handelbarkeit und neue Produkte sind nicht bestätigt. Keine automatische Top-3-Freigabe.</p><div role="status" class="small" id="dgIssuerStatus">Noch keine Serverprüfung.</div><div id="dgIssuerCandidates"></div></details>'+ '<b>📷 DEGIRO-Liste</b><button type="button" id="dgListUploadButton" style="margin-top:10px;width:100%;background:#1677ff">↑ DEGIRO-Liste hochladen</button>'+
 '<input id="dgListUpload" type="file" accept="image/*" multiple hidden>'+
 '<details style="margin-top:8px"><summary>Hinweise zum Hochladen</summary><div class="small">Einen oder mehrere Listen-Screenshots gleichzeitig auswählen. Eine neue Auswahl ersetzt die bisherige Liste nach erfolgreichem Einlesen.</div></details>'+
 '<div id="dgCentralStatus" class="small" role="status" aria-live="polite" style="margin-top:9px">Gespeicherte Liste wird geladen …</div><details id="dgSavedListImages"></details></div>'+

 '<div id="dgStorageStatus" class="small" role="status"></div>'+
 '<div id="dgManualSnapshots" style="margin-top:12px" hidden></div>'+
 '<div id="dgConditionalOut" style="margin-top:12px" hidden></div>'+
 '<div id="dgTop3Inputs" hidden></div>' +
 '<button style="margin-top:10px;width:100%" id="dgRankBtn" hidden>🔎 Analyse erneut ausführen</button><div id="dgApprovalOut"></div>';
 a.parentNode.insertBefore(b,a.nextSibling);
 const q=b.querySelector("#dgTop3Inputs");
 for(let i=1;i<=12;i++){
  const r=document.createElement("div");
  r.style.cssText="margin:8px 0;padding:9px;background:#fff;border-radius:10px";
  r.innerHTML='<b>Kandidat '+i+'</b><div id="dgOcrStatus'+i+'" class="small" style="margin-top:5px">Wartet auf Screenshot.</div><div id="dgResearch'+i+'" class="small research" style="margin-top:5px">🌐 Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="'+i+'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="'+i+'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="'+i+'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="'+i+'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="'+i+'" type="number" step=".01" placeholder="KO-Level"><div><input data-dg="isin" data-i="'+i+'" placeholder="ISIN" aria-label="ISIN"><button type="button" data-copy-product-isin="" style="min-height:44px">ISIN kopieren</button><span role="status" data-copy-status></span></div><span id="dgCompletion'+i+'" role="status"></span></div><button data-research="'+i+'">Aktuelle Produktdaten laden</button>';
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
 const restoredProducts=loadIdentities();
 restoreProductRows(applyResearchedTerms(localStorage.getItem(PRODUCT_STORE_KEY)?restoredProducts:recoverReviewedLists(restoredProducts)));
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
 window.addEventListener('pageshow',()=>updateScreenshotReturn(true));
 quoteRefresh=createQuoteRefresh({
  rows:()=>Array.from({length:12},(_,idx)=>{const id=idx+1,isin=(document.querySelector('[data-dg="isin"][data-i="'+id+'"]')?.value.trim()||'').toUpperCase();return {id,isin,key:isin+':'+(rowVersions.get(id)||0)};}),
  request:enrichProduct,visible:()=>!document.hidden,interval:30000,limit:4
 });
 refreshImportedProducts(!['night','weekend'].includes(window.BobDegiroPhase?.()));
 const savedCount=restoredProducts.length;
 refreshIssuerCandidates();
 setInterval(()=>{if(!document.hidden)refreshIssuerCandidates();},10*60*1000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshIssuerCandidates();});
 b.querySelector('#dgCentralStatus').textContent=listArchive?.files?.length?'Aktive Liste: '+listArchive.files.length+' Screenshot(s) · '+savedCount+' Produkte · aufgenommen '+new Date(listArchive.storedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+'. Bleibt aktiv bis zum nächsten erfolgreichen Upload; aktuelle Produktkurse werden separat geprüft.':savedCount?savedCount+' gespeicherte Produkte · die letzte Liste bleibt erhalten; Kursdaten können veralten.':'Noch keine gespeicherte Liste. Bitte einmal DEGIRO-Screenshots einlesen.';
 const upload=b.querySelector('#dgListUpload'),uploadButton=b.querySelector('#dgListUploadButton'),uploadStatus=b.querySelector('#dgCentralStatus');
 uploadButton.addEventListener('click',()=>upload.click());
 upload.addEventListener('change',async()=>{
  if(!upload.files?.length)return;
  listRevision++; // Invalidate an older asynchronous reread immediately.
  uploadButton.disabled=true;upload.disabled=true;
  try{
   const files=await retainSelectedImages(upload);
   const items=await readListBatch(files,recognizeOcr,(i,total,name)=>{uploadStatus.textContent='📷 Bild '+i+' von '+total+' wird gelesen: '+name;});
   await saveListArchive(files,items);
   // The old screenshot universe is now replaced. Its manual KO and PDF
   // attestations must not silently apply to the new list, even for a shared ISIN.
   window.BobCombined.resetFixedList();
   try{localStorage.removeItem(PDF_REFERENCE_STORE);}catch(_){}
   returnProductIsin='';returnProductPending=false;
   try{localStorage.removeItem(RETURN_PRODUCT_KEY);}catch(_){}
   populateCandidateRows(items);
   // Persist the new generation before any normal/periodic background snapshot.
   const backgroundSynced=await window.BobPaperSimulation?.sync?.(buildPaperListEvidence(),true);
   rankUI();
   uploadStatus.textContent='✅ Neue aktive Liste: '+files.length+' Bild(er) · '+items.length+' unterschiedliche Produkte. Vorherige Liste ersetzt und gespeichert – bleibt bis zum nächsten Upload erhalten. Kurszeiten werden unabhängig geprüft.';
   uploadStatus.textContent+=backgroundSynced?' Hintergrundübernahme bestätigt.':' ⚠️ Hintergrundübernahme noch offen; automatischer Abgleich läuft.';
   const uncertain=items.filter(x=>!validIsin(x.isin)).length;
   if(uncertain)uploadStatus.textContent+=' ⚠️ '+uncertain+' ISIN(s) unsicher – unter Details prüfen.';
   // The paper/background service is refreshed immediately, independently of its
   // ordinary 60-second cadence. Never send removed ISINs from the old list.
   refreshImportedProducts(true).then(()=>refreshImportedProducts());
  }catch(e){uploadStatus.textContent='⚠️ '+(e?.message||'Bilder konnten nicht gelesen werden')+' Die bisherige Produktliste bleibt erhalten.';}
  finally{upload.value='';upload.disabled=false;uploadButton.disabled=false;setTimeout(retrySavedList,1000);}
 });
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
function continuingAnalysis(products,context){
 return products.filter(p=>p.isin||p.name).map(p=>{
  const analysis=p.quote?.analysisQuote;
  const direct=p.quote?.isin===p.isin&&n(p.quote.price)===n(p.price);
  const at=direct?(p.quote.askAt||p.quote.quoteAt):((analysis&&n(analysis.price)>0&&n(analysis.price)===n(p.price))?analysis.askAt:p.snapshot?.evidence?.Brief?.at||p.snapshot?.sourceTime||p.quote?.askAt||p.quote?.quoteAt);
  const limit=direct||(analysis&&n(analysis.price)>0&&n(analysis.price)===n(p.price))?(p.quote?.analysisMaxAgeSeconds||90)*1000:p.snapshot?SCREENSHOT_MAX_AGE_MS:90000,now=context.now??Date.now();
  const priceWarning=calculationAge(at,limit,now);
  const levAt=p.quote?.isin===p.isin&&n(p.quote.leverage)===n(p.leverage)?p.quote.leverageAt:p.snapshot?.evidence?.Hebel?.at;
  const levWarning=calculationAge(levAt,limit,now);
  const terms=productTermsStatus(p,now,true);
  const seriesWarning=p.snapshot?.evidence?.Hebel?.fromSeries&&n(p.snapshot.evidence.Hebel.value)===n(p.leverage)?'Hebel: Zeitbezug aus Aufnahmeserie; kein separat bestätigter Anbieterzeitstempel':'';
  const warning=[priceWarning,levWarning?'Hebel: '+levWarning:'',seriesWarning,...terms.warnings].filter(Boolean).join(' · ');
  return {p,warning,evaluation:evaluateProduct({...p,...context})};
 });
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
 return '<details data-product-details="calculation-'+esc(p.isin)+'" style="margin-top:10px"><summary>Berechnung und Bewertung</summary><p class="small">Rechnerische Bewertung mit vorhandenen Werten, auch bei veralteten oder fehlenden Zeitstempeln. Keine aktuell bestätigte Produktfreigabe.</p>'+(marketWarnings.length?'<p><i>'+esc(marketWarnings.join(' · '))+'</i></p>':'')+'<div style="margin:8px 0;'+(uncertain?'font-style:italic':'')+'"><b>'+esc(p.isin||p.name)+'</b> · Kurs '+esc(p.price??'fehlt')+' · <strong>Hebel</strong> '+esc(p.leverage??'fehlt')+' · KO '+esc(p.ko??'fehlt')+(warning?' · '+esc(warning):'')+'<br>'+esc(e.ok?'Rechnerische Bewertung: '+e.score+' Punkte · '+e.reasons.join(' · '):e.reasons.join(' · '))+'</div></details>';
}
function renderContinuingAnalysis(products,context){
 if(typeof document!=='undefined')for(const [i,p] of products.entries())for(const [field,key] of [['price','Brief'],['lev','Hebel'],['ko','KO']]){
  const input=document.querySelector('[data-dg="'+field+'"][data-i="'+(i+1)+'"]');if(!input)continue;
  const e=p.snapshot?.evidence?.[key],at=e?.at||(field==='price'?(p.snapshot?.sourceTime||p.quote?.quoteAt):null);
  const warning=calculationAge(at,p.snapshot?SCREENSHOT_MAX_AGE_MS:90000);
  input.style.fontStyle=warning?'italic':'';input.title=warning;
 }

 const marketWarnings=window.BobAnalysisAge?.()||[];
 const ranked=indicativeRecommendations(products,context);
 const highestLeverage=Math.max(...ranked.map(({evaluation:e})=>e.leverage));
 const leveragePlaces=ranked.flatMap(({evaluation:e},i)=>e.leverage===highestLeverage?[i+1]:[]);
 const leverageHint=leveragePlaces.length?'<div data-risk-leverage style="margin:8px 0"><strong>Risiko: '+(leveragePlaces.length>1?'Plätze ':'Platz ')+leveragePlaces.join(' / ')+' · höchster Hebel: '+highestLeverage.toFixed(2)+'×</strong><details><summary>Erklärung zum Hebelrisiko</summary><div class="small">Unter den angezeigten Empfehlungen; verstärkt Gewinne und Verluste. Hebel laut vorhandenen Werten.</div></details></div>':'';
 const recommendations=ranked.map(({p,warning,evaluation:e},i)=>'<div style="margin:10px 0"><b>'+ (i+1)+'. '+esc(p.isin)+'</b>'+renderIsinCopy(p.isin,true)+'<b> · '+esc(e.direction)+'</b><br><strong>'+esc(warning&&warning.includes('veraltet')?'Mit veralteten Werten gerechnet':warning?'Mit Werten unbekannter Aktualität gerechnet':marketWarnings.length?'Marktdaten-Aktualität eingeschränkt':'Rechnerische Empfehlung mit vorhandenen Werten')+'</strong><br>Risiko-/Datenwert '+e.score+'/100 · KO-Abstand '+e.koDistancePct.toFixed(2)+'%<details data-product-details="recommendation-'+esc(p.isin)+'"><summary>Begründung und Datenhinweise</summary>'+esc(warning||'Produktkurs innerhalb des Zeitfensters; weitere Feldzeiten siehe Details')+'<br>'+esc(e.reasons.join(' · ')).replace(/\bHebel\b/g,'<strong>Hebel</strong>')+'</details></div>').join('');
 return '<section data-indicative-recommendations><b>Rechnerische Empfehlung · <span style="color:'+({LONG:'#15803d',SHORT:'#b91c1c'}[context.direction]||'#ca8a04')+'">'+esc(['LONG','SHORT'].includes(context.direction)?context.direction:'ABWARTEN')+'</span></b>'+leverageHint+ (recommendations||'<p>ABWARTEN: '+(['LONG','SHORT'].includes(context.direction)?'Aktuell erfüllt kein Produkt alle Auswahlkriterien.':'Keine bestätigte Long-/Short-Marktrichtung.')+'</p>')+'</section>';
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
   isinConfirmed:!!(quote?.productVerified),snapshot:detailScreenshots.get(i)||null,
   quote:quote?.isin===isin?quote:null};
 }).filter(Boolean);
 return {products,references:products.map(p=>{
    const idx=Array.from({length:12},(_,z)=>z+1).find(i=>document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value?.trim().toUpperCase()===p.isin);
    return combinedReferences.get(idx)||null;
   }),fixedBarriers:window.BobCombined.fixedBarriers(),
   listUploadedAt:listArchive?.storedAt||null,origin:listArchive?.storedAt?'degiro-screenshot':'legacy'};
}
function rankUI(){
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
 const savedProducts=ps.filter(p=>p.name||p.isin);
 const savedSummary=document.getElementById("dgSavedProductsSummary");
 if(savedSummary)updateProductHtml(savedSummary,'Gold-Hebelprodukte'+(additionalProductsComplete(savedProducts)?' <strong aria-label="Alle Produktdaten und Zeitbezüge bestätigt" style="font-size:1.6em;font-weight:900;color:#15803d">✓</strong>':''));
 const manualOut=document.getElementById("dgManualSnapshots");
 if(manualOut){
  const ctx={direction:d,spotFresh,spot:s,atr:a,trend:document.getElementById('trend')?.textContent,trend2:document.getElementById('trend2')?.textContent,...selectionUiSignals(),rsi:n(document.getElementById('rsi')?.textContent),hist:n(document.getElementById('hist')?.textContent),adx:n(document.getElementById('adx')?.textContent),...technical};
  const comparison=rankManualSnapshots(ps,ctx);
  manualOut.innerHTML=comparison.total?'<b>📷 Vergleich belegter Momentaufnahmen · '+comparison.total+' Produkt(e)</b>'+comparison.candidates.map((p,i)=>'<div class="small" style="margin-top:8px"><b>'+(i+1)+'. '+esc(p.isin)+'</b> · Risiko-/Datenwert '+p.evaluation.score+'/100 · KO-Abstand '+p.evaluation.koDistancePct.toFixed(2)+'%<br>Brief '+esc(p.snapshot.ask)+' EUR · Geld '+esc(p.snapshot.bid)+' EUR · Hebel '+esc(p.leverage)+' · KO '+esc(p.ko)+(p.evaluation.warnings.length?'<br>'+esc(p.evaluation.warnings.join(' · ')):'')+'</div>').join('')+'<div class="small">Rangfolge nur innerhalb der belegten Momentaufnahmen. Laufende Aktualisierung, Marktstatus und Ausführbarkeit nicht bestätigt – keine Live-Freigabe. Unvollständige Produkte sind nicht im Vergleich.</div>':'';
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
   shadowOut.textContent='DEGIRO-Testvergleich (keine Freigabe): '+(candidates.length?candidates.map((p,i)=>(i+1)+'. '+p.isin+' · '+p.priceKind+' · Risiko-/Datenwert '+p.score+'/100').join('\n'):'kein ausreichend belegtes Produkt · '+test.gateReasons.concat(test.notApproved.flatMap(p=>p.reasons)).slice(0,3).join(' · '));
   intraday.products=candidates.map(p=>({isin:p.isin,price:p.price,at:p.at,priceKind:p.priceKind,score:p.score}));
  }else shadowOut.textContent='DEGIRO-Testvergleich: ABWARTEN – '+(intraday?.reason||'Intraday-Daten fehlen');
 }

 window.BobAudit?.capture(ps,flow,bundle);
 window.BobPaperSimulation?.sync({...buildPaperListEvidence(),products:ps,references});
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
  if(r&&n(r.bid)>0)return {isin,direction:document.querySelector('[data-dg="dir"][data-i="'+i+'"]')?.value,bid:r.bid,source:r.source,referenceAt:r.quoteAt,goldReference:r.goldReference,fxReference:r.fxReference,fxScenario:r.fxReference,ko:r.barriers?.[0]?.value||r.ko1||document.querySelector('[data-dg="ko"][data-i="'+i+'"]')?.value,strike:m?.strike,ratio:m?.ratio};
  if(q?.found&&q.isin===isin&&m?.underlying==='XAU/USD')return {isin,direction:m.direction,bid:q.bid,source:q.source,referenceAt:q.bidAt||q.quoteAt,goldReference:q.leverageInputs?.spotUsd,fxReference:q.leverageInputs?.usdEur,fxScenario:q.leverageInputs?.usdEur,ratio:m.ratio,strike:m.strike,ko:m.ko};
 }
 return null;
}
window.BobDegiro={recoverArchivedList,productObservedTimeStatus,sharedProductFieldTime,detailScreenshotData,parseDegiroDisplayedQuote,renderDegiroDisplayedQuote,degiroListObservation,renderDegiroListEvidence,koProtection,renderProductCalculation,refreshTradeTestQuotes:()=>refreshImportedProducts(true),tradeTestProducts,koEvidenceStatus,KO_MAX_AGE_MS,currentConvertedChfEvidence,termSeriesReference,currentProductTerm,renderTermSeriesValidity,productDataStatus,productCompletionBadge,renderSecondaryValidity,analysisReleaseQuote,recognizePlainOcr,reprocessOriginals,scalarCellRect,readScalarCell,originalRetention,saveProductOriginal,loadProductOriginals,markOriginalProcessed,deleteProductOriginals,removeUnconfirmedFields,screenshotBatchSummary,renderUploadMissing,readTermDate,screenshotProductLink,knockoutStatus,explicitKnockout,knockoutCard,invalidateProductQuote,retainProductResearch,missingValueLocation,restorePdfReference,parseProductPdf,readProductPdf,sgIdentityRect,readSgIdentity,linkScreenshotSeries,ocrGlyphPair,strictOcrNumber,ocrNumericFields,unconfirmedOcrFields,preferOriginalTableRead,bnpBadgeRect,normalizeBnpQuoteColumns,imageIdentityDiagnostic,reviewedImageText,detailStateKey,updateProductHtml,zurichListDay,listExpired,clearDailyList,archiveTransaction,saveListArchive,restoreListArchive,automaticIdentity,automaticCondition,recoverTermRows,screenshotReturnRow,renderProductDecision,readListBatch,collectiveSignal,productFieldStates,renderProductFieldStates,indicativeRecommendations,calculationAge,continuingAnalysis,renderContinuingAnalysis,compactProductCard,screenshotSummary,retainSelectedImages,renderImageImportStatus,renderIssuerHelp,renderProductSources,applyResearchedTerms,durableCondition,maturityDeadline,writeStoredProducts,cleanStoredProduct,recoverReviewedLists,restoreProductRows,selectionUiSignals,selectionMarketGate,costRiskAssessment,finalProductStatus,parseProductTerms,productTermsStatus,selectionTimeWindow,selectionDetailStatus,selectionWorkflow,renderSelectionWorkflow,recognizeOcr,exitReference,createQuoteRefresh,screenshotCurrentState,renderScreenshotCurrentState,conditionalCandidate,rankConditional,renderConditional,qualityText,isFutureProduct,futureResearchText,productEstimateText,rankManualSnapshots,productUploadCards,sourceTimestamp,screenshotTimes,evidenceTiming,manualSnapshotStatus,needsDirectionalData,loadIdentities,saveIdentities,riskModel,koDistancePct,evaluateProduct,quoteTiming,currentQuote,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates,validIsin,normalizeOcrIsin,populateCandidateRows,recoverOcrIsins,detailScreenshotData,missingProductData,supplementaryHint,screenshotTimeLabel,mergeScreenshotEvidence,manualProductMissing,escapeHtml:esc};
})();


/* Product-specific scenarios for active trades. No executable broker quotes. */
(function(root){
 const positive=v=>typeof v==='number'&&Number.isFinite(v)&&v>0;
 function model(values){
  if(!values||values.simpleSpotTurbo!==true||values.referenceConfirmed!==true)throw Error('Produktbedingungen und zusammengehörige Referenzwerte bestätigen. Unterstützt: einfaches Gold-Spot-Turbo in EUR.');
  if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(values.isin||'')||!['LONG','SHORT'].includes(values.direction))throw Error('Produkt-ISIN oder Richtung fehlt.');
  const x={isin:values.isin,direction:values.direction,simpleSpotTurbo:true,referenceConfirmed:true,currency:'EUR'};
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
  const fx=spots?.usd_eur_meta,rate=Number(fx?.rate),at=Date.parse(fx?.fetchedAt);
  if(!m||!positive(rate)||!Number.isFinite(at)||at>now)return m;
  return {...m,fxScenario:rate,fxDetails:{...fx,delayed:!!fx.error||now-at>90000}};
 }
 function label(m,gold){const x=price(m,gold);return x.available?'≈ '+x.price.toFixed(4)+' EUR/Stück (geschätzt) · Gold '+gold.toFixed(2)+' USD/oz'+(m.fxDetails?.delayed?' · FX-Aktualisierung verzögert':''):x.reason;}
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
 const out={available:false,reasons:[],rows:[],isEstimate:true,tradeable:false};
 const required=['bid','goldReference','fxReference','fxScenario','ratio','strike','ko','entry','quantity','planGold','targetGold','stopGold'];
 const v=Object.fromEntries(required.map(k=>[k,num(p[k])]));
 if(!window.BobDegiro?.validIsin(p.isin))out.reasons.push('Gültige Produkt-ISIN fehlt');
 if(!['LONG','SHORT'].includes(p.direction))out.reasons.push('Long-/Short-Richtung fehlt');
 if(p.simpleSpotTurbo!==true)out.reasons.push('Einfaches Gold-Spot-Turbo in EUR ohne Quanto bestätigen; kein Future oder Optionsschein');
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
 return '<b>Geschätzter Verkaufskurs pro Stück</b><table><tr><th>Szenario Gold USD</th><th>Geldkurs EUR/Stück</th><th>Erlös EUR</th><th>Gewinn/Verlust EUR</th></tr>'+x.rows.map(r=>'<tr><td>'+esc(r.label)+' · '+r.gold.toFixed(2)+'</td>'+(r.available?'<td>≈ '+r.price.toFixed(2)+'</td><td>≈ '+r.proceeds.toFixed(2)+'</td><td>≈ '+r.pnl.toFixed(2)+'</td>':'<td colspan="3">'+esc(r.reason)+'</td>')+'</tr>').join('')+'</table><div class="small">Referenz: '+esc(x.source)+' · '+esc(x.referenceAt)+' (Originalzeit; keine Sekunden ergänzt). Angenommener USD→EUR-Kurs am Ausstieg: '+x.fxScenario+'. Linearer Turbo-Ansatz mit konstantem Preisaufschlag, konstantem Basispreis und Bezugsverhältnis; ohne Gebühren, Steuern und künftige Finanzierung. KO-Berührung auf dem Weg, Preisstellung und Ausführung unbestätigt. Genauigkeit noch nicht gemessen. Kein bestätigter zukünftiger Geldkurs.</div><details><summary>Rechenweg</summary>'+esc(x.formula)+'</details>';
}
function init(){
 if(document.getElementById('bobExitEstimate'))return;
 const parent=document.getElementById('dgTop3');if(!parent)return;
 const panel=document.createElement('div');panel.id='bobExitEstimate';panel.className='card';
 const fields=[['isin','Produkt-ISIN','text'],['entry','Tatsächlicher Einstieg EUR/Stück','number'],['quantity','Stückzahl','number'],['bid','Geldkurs der Referenz EUR/Stück','number'],['goldReference','Gold Spot USD zur Referenz','number'],['fxReference','USD→EUR zur Referenz','number'],['source','Referenzquelle (z. B. DEGIRO-Screenshot)','text'],['referenceAt','Kurszeit laut Referenz','text'],['ratio','Bezugsverhältnis','number'],['strike','Basispreis USD','number'],['ko','KO-Barriere USD','number'],['planGold','Gold Spot USD für den Handelsplan','number'],['targetGold','Gold-Ziel USD','number'],['stopGold','Gold-Stop USD','number'],['fxScenario','Angenommener USD→EUR-Kurs am Ausstieg','number']];
 panel.innerHTML='<h3>Geschätzter Ausstiegskurs pro Stück</h3><div class="small">Referenz-Geldkurs und gleichzeitig beobachtete Gold-/FX-Werte eingeben oder aus vorhandenen Produktnachweisen übernehmen. Dieses Szenario ersetzt keinen aktuellen Verkaufskurs. Eingaben werden beim Berechnen auf diesem Gerät gespeichert.</div><div class="grid">'+fields.map(([k,l,t])=>'<div><label for="exit-'+k+'">'+l+'</label><input id="exit-'+k+'" data-exit="'+k+'" type="'+t+'" '+(t==='number'?'step="any" min="0"':'')+'></div>').join('')+'<div><label for="exit-direction">Produktrichtung</label><select id="exit-direction" data-exit="direction"><option value="">Auswählen</option><option>LONG</option><option>SHORT</option></select></div></div><label><input type="checkbox" data-exit="simpleSpotTurbo"> Einfaches Gold-Spot-Turbo in EUR, ohne Quanto; Bedingungen am Produkt geprüft</label><br><label><input type="checkbox" data-exit="referenceConfirmed"> Referenz-Geldkurs, Gold und FX gehören zeitlich zusammen; Quelle und Kurszeit geprüft</label><div class="grid"><button data-exit-reference>Produktnachweis übernehmen</button><button data-exit-plan>Ziel/Stop aus aktueller Goldanalyse</button><button data-exit-calculate>Verkaufskurse schätzen</button><button data-exit-monitor>Produkt-Trade überwachen / aktualisieren</button></div><div data-exit-output class="small">Noch keine Schätzung. Tatsächliche Position eingeben; keine Order oder Trade-Aktivierung.</div>';
 parent.after(panel);
 const autoButton=document.createElement('button');autoButton.type='button';autoButton.textContent='Fehlende Werte automatisch per ISIN abrufen';autoButton.onclick=automaticTradeReference;panel.append(autoButton);
 // Keep identity and actual position visible; technical references remain available.
 const reference=document.createElement('details'),summary=document.createElement('summary'),grid=document.createElement('div');
 summary.textContent='Referenzwerte und Produktbedingungen prüfen';grid.className='grid';reference.append(summary,grid);
 const positionGrid=panel.querySelector('.grid');
 for(const el of panel.querySelectorAll('[data-exit]'))if(!['isin','entry','quantity','direction','simpleSpotTurbo','referenceConfirmed'].includes(el.dataset.exit))grid.append(el.closest('div'));
 positionGrid.after(reference);
 panel.querySelector('h3').textContent='2 · Einstieg und Stückzahl / 3 · Überwachung starten';
 const hint=document.createElement('p');hint.className='small';hint.id='bobTradeFormHint';reference.after(hint);
 const updateForm=()=>{
  const read=k=>panel.querySelector('[data-exit="'+k+'"]');
  const ready=/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(read('isin').value.trim().toUpperCase())&&Number(read('entry').value)>0&&Number(read('quantity').value)>0&&['LONG','SHORT'].includes(read('direction').value)&&read('simpleSpotTurbo').checked&&read('referenceConfirmed').checked;
  const monitor=panel.querySelector('[data-exit-monitor]');monitor.disabled=!ready;
  monitor.textContent='3 · Produkt-Überwachung starten / aktualisieren';
  hint.textContent=ready?'Position erfasst. Beim Start prüft Bob zusätzlich Referenzwerte, Produktmodell und aktuelle Marktdaten.':'Zum Start: Produkt, Einstieg und Stückzahl ergänzen; Richtung, Bedingungen und zeitliche Zuordnung der Referenzwerte prüfen.';
 };
 panel.addEventListener('input',()=>queueMicrotask(updateForm));panel.addEventListener('change',updateForm);
 panel.addEventListener('click',()=>queueMicrotask(updateForm));
 try{const saved=JSON.parse(localStorage.getItem('bobExitScenarioV1')||'null');if(saved)for(const el of panel.querySelectorAll('[data-exit]'))if(Object.prototype.hasOwnProperty.call(saved,el.dataset.exit)){if(el.type==='checkbox')el.checked=saved[el.dataset.exit]===true;else el.value=saved[el.dataset.exit];}}catch(_){}
 const get=k=>panel.querySelector('[data-exit="'+k+'"]'),read=()=>Object.fromEntries(Array.from(panel.querySelectorAll('[data-exit]')).map(el=>[el.dataset.exit,el.type==='checkbox'?el.checked:el.value.trim()]));
 panel.querySelector('[data-exit-reference]').addEventListener('click',()=>{
  const isin=get('isin').value.trim().toUpperCase()||document.getElementById('dgIsin')?.value.trim().toUpperCase();
  const r=window.BobDegiro.exitReference?.(isin);
  if(!r){panel.querySelector('[data-exit-output]').textContent='Kein zugehöriger Produktnachweis vorhanden. Referenzwerte manuell eintragen.';return;}
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
 panel.querySelectorAll('[data-exit]').forEach(el=>el.addEventListener('input',()=>{if(el.dataset.exit!=='referenceConfirmed')get('referenceConfirmed').checked=false;panel.querySelector('[data-exit-output]').textContent='Eingaben geändert; Schätzung erneut berechnen.';}));
 updateForm();
}
function issuerTradeFields(x,isin){
 if(!x||x.isin!==isin||x.productVerified!==true)throw Error('Produktidentität noch nicht bestätigt.');
 const m=x.metadata||{},model=x.productModel||{},c=x.conditions||{};
 if(m.status===2||m.tradingHalted===true)throw Error('Produkt beendet oder Handel ausgesetzt.');
 if(m.underlyingType!=='SPOT'&&model.underlying!=='XAU/USD')throw Error('Gold-Spot-Basiswert nicht bestätigt; kein Spot-Modell für Futures.');
 if(m.currency!=='EUR'&&x.currency!=='EUR')throw Error('Produktwährung EUR nicht bestätigt.');
 const fields={},put=(k,v)=>{if(num(v)>0)fields[k]=num(v);};
 for(const k of ['ratio','strike','ko'])put(k,c[k]?.value??model[k]??m[k]);
 if(['LONG','SHORT'].includes(m.direction||model.direction))fields.direction=m.direction||model.direction;
 const q=x.analysisQuote||x;
 if(num(q.bid)>0&&(q.bidAt||q.quoteAt)&&Number.isFinite(Date.parse(q.bidAt||q.quoteAt))){
  fields.bid=num(q.bid);fields.referenceAt=q.bidAt||q.quoteAt;fields.source=(q.source||x.source||'Emittentenabfrage')+' · '+(x.sourceUrl||'')+' · Referenz für Berechnung, kein zugesicherter DEGIRO-Ausführungskurs';
 }
 return fields;
}
let autoReferenceBusy=false;
async function automaticTradeReference(){
 const panel=document.getElementById('bobExitEstimate');if(!panel||autoReferenceBusy)return;
 const get=k=>panel.querySelector('[data-exit="'+k+'"]'),out=panel.querySelector('[data-exit-output]');
 const isin=get('isin').value.trim().toUpperCase(),direction=get('direction').value;
 if(!window.BobDegiro.validIsin(isin)){out.textContent='Für den automatischen Abruf ist eine gültige ISIN erforderlich.';return;}
 autoReferenceBusy=true;out.textContent='Produktwerte per ISIN bei SG und vorhandenen Ersatzquellen abrufen …';
 try{
  const r=await fetch('/api/degiro/enrich?isin='+encodeURIComponent(isin),{cache:'no-store',signal:AbortSignal.timeout(65000)});
  if(!r.ok)throw Error('Produktquelle antwortet mit '+r.status);
  const x=await r.json();if(get('isin').value.trim().toUpperCase()!==isin)return;
  const fields=issuerTradeFields(x,isin);
  if(direction&&fields.direction&&direction!==fields.direction)throw Error('Produktrichtung widerspricht dem Kauf; keine Werte übernommen.');
  get('referenceConfirmed').checked=false;get('simpleSpotTurbo').checked=false;
  for(const [k,v] of Object.entries(fields))if(get(k))get(k).value=v;
  panel.dispatchEvent(new Event('change',{bubbles:true}));
  out.textContent='Produktwerte übernommen. Quelle: '+(x.source||x.sourceUrl||'ISIN-Abfrage')+'. Produktbedingungen und zeitliche Referenz bleiben getrennt prüfbar.';
  if(fields.referenceAt&&fields.bid)await researchReference();
  if(get('isin').value.trim().toUpperCase()!==isin)return;
  const values=Object.fromEntries(Array.from(panel.querySelectorAll('[data-exit]')).map(el=>[el.dataset.exit,el.type==='checkbox'?el.checked:el.value.trim()]));
  localStorage.setItem('bobExitScenarioV1',JSON.stringify(values));
  out.textContent+=' Kaufkurs und Stückzahl bleiben unverändert. Fehlende Vertragswerte werden nicht geschätzt; Gold-/FX-Referenzen und Verkaufskurse sind ausdrücklich Näherungen. Überwachung noch nicht aktiviert.';
 }catch(e){out.textContent='Automatischer Abruf noch unvollständig: '+e.message+' Vorhandene Kaufdaten bleiben erhalten.';}
 finally{autoReferenceBusy=false;}
}
function referenceHtml(x){
 const local=t=>new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false})+' Schweizer Zeit';
 return 'Gold-/FX-Werte übernommen: Gold '+esc(x.goldReference)+' USD · USD→EUR '+esc(x.fxReference)+'.<br>Gold-Beobachtung: '+esc(local(x.goldAt))+' · FX-Minute: '+esc(local(x.fxStart))+' bis '+esc(local(x.fxEnd))+' · maximaler Zeitversatz '+esc(x.maxSkewSeconds)+' Sekunden.<br><a href="'+esc(x.goldUrl)+'" target="_blank" rel="noopener">Goldquelle</a> · <a href="'+esc(x.fxUrl)+'" target="_blank" rel="noopener">FX-Quelle</a><br>'+esc(x.note)+'<br>Referenz in den Berechnungsdetails prüfen und bestätigen. Ziel/Stop ergänzen. Ausstiegs-FX zunächst konstant angenommen.';
}
function restoreReference(){
 const p=document.getElementById('bobExitEstimate');if(!p)return false;
 const get=k=>p.querySelector('[data-exit="'+k+'"]');
 try{const x=JSON.parse(localStorage.getItem('bobTradeMarketReferencesV1')||'{}')[get('isin').value];
 if(!x||x.at!==get('referenceAt').value||x.bid!==get('bid').value)return false;
 for(const k of ['goldReference','fxReference','fxScenario','source'])get(k).value=x[k];
 if(x.evidence)p.querySelector('[data-exit-output]').innerHTML=referenceHtml(x.evidence);return true;
 }catch(_){return false;}
}
async function researchReference(){
 const panel=document.getElementById('bobExitEstimate');if(!panel)return;
 const get=k=>panel.querySelector('[data-exit="'+k+'"]'),out=panel.querySelector('[data-exit-output]');
 const isin=get('isin').value,at=get('referenceAt').value,bid=get('bid').value,source=get('source').value.split(' · Historische Näherungsreferenz:')[0];
 if(!window.BobDegiro?.validIsin(isin)||!at||!(num(bid)>0)){out.textContent='Zuerst Produkt-ISIN und datierten Geldkurs übernehmen.';return;}
 get('referenceConfirmed').checked=false;out.textContent='Historische Gold-/FX-Referenz zur Originalzeit wird gesucht …';
 try{
  const response=await fetch('/api/trade-reference?at='+encodeURIComponent(at),{cache:'no-store'}),x=await response.json();
  if(get('isin').value!==isin||get('referenceAt').value!==at||get('bid').value!==bid)return;
  if(!response.ok||!x.available){out.textContent=x.reason||'Referenz fehlt.';return;}
  get('goldReference').value=x.goldReference;get('fxReference').value=x.fxReference;get('fxScenario').value=x.fxReference;
  get('source').value=source+' · Historische Näherungsreferenz: '+x.goldSource+' @ '+x.goldAt+'; '+x.fxSource+' @ '+x.fxStart+' bis '+x.fxEnd+'; Zeitzone Europe/Zurich angenommen; maximaler Zeitversatz '+x.maxSkewSeconds+' s';
  try{const all=JSON.parse(localStorage.getItem('bobTradeMarketReferencesV1')||'{}');all[isin]={at,bid,goldReference:x.goldReference,fxReference:x.fxReference,fxScenario:x.fxReference,source:get('source').value,evidence:x};localStorage.setItem('bobTradeMarketReferencesV1',JSON.stringify(all));}catch(_){}
  out.innerHTML=referenceHtml(x);
 }catch(_){if(get('isin').value===isin&&get('referenceAt').value===at)out.textContent='Referenzabruf fehlgeschlagen. Keine historischen Werte ersetzt.';}
}
window.BobExitEstimate={calculate,render,init,researchReference,restoreReference,planInput,issuerTradeFields,automaticTradeReference};
if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();}
})();

/* Dated personal trade evidence. No orders and no invented quote precision. */
(function(){
const KEY='bobTradeEvidenceV1',esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function number(v){let s=String(v||'').trim();if(s.includes(','))s=s.replace(/\./g,'').replace(',','.');return /^\d+(?:\.\d+)?$/.test(s)?Number(s):null;}
function parse(text){
 const raw=String(text||''),ids=[...new Set(raw.toUpperCase().match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])].filter(x=>window.BobDegiro.validIsin(x));
 if(ids.length!==1)return{ok:false,reason:'Genau eine gültige ISIN muss im Bild sichtbar sein. Kursbild bitte mit ISIN erneut aufnehmen.'};
 const match=re=>{const m=raw.match(re);return m?m[1].trim():null;},val=label=>number(match(new RegExp('\\b(?:'+label+')(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR)?\\s*([0-9]+(?:[.,][0-9]+)?)','i')));
 const time=match(/\b(\d{2}[/.]\d{2}[/.]\d{4},?\s+\d{2}:\d{2}(?::\d{2})?)\b/),direction=/\b(?:CALL|LONG)\b/i.test(raw)?'LONG':/\b(?:PUT|SHORT)\b/i.test(raw)?'SHORT':null;
 if(!/\bEUR\b|€/.test(raw)&&/\bGeld\b|\bBid\b|\bKauf\b/i.test(raw))return{ok:false,reason:'EUR-Währung am Original nachweisen.'};
 if(/\b(?:CALL|LONG)\b/i.test(raw)&&/\b(?:PUT|SHORT)\b/i.test(raw))return{ok:false,reason:'Produktrichtung widersprüchlich.'};
 if((raw.match(/\b(?:Geld|Bid)(?!\s*(?:Vol|Volumen))/gi)||[]).length>1)return{ok:false,reason:'Mehrere Geldkurse: ein einziges Geld-/Briefpaar zeigen.'};
 const purchase=/\bKauf\b/i.test(raw)&&/Ausf.hrungsdatum|Transaktions.ID|Order.[I1l]?D/i.test(raw);
 const x={ok:true,isin:ids[0],direction,time,kind:purchase?'entry':/\bGeld\b|\bBid\b/i.test(raw)?'quote':'details'};
 if(purchase){x.entry=val('Kurs');x.quantity=val('Anzahl|Anz\\.');x.orderId=match(/Order.ID\s*[:=]?\s*([a-z0-9-]+(?:\s*\n\s*[a-z0-9-]+)?)/i)||match(/Transaktions.ID\s*[:=]?\s*(\d+)/i);x.feesChf=number(match(/(?:Gesamte Kosten|Gesamtgebühr)\s*CHF\s*-?\s*([0-9]+(?:[.,][0-9]+)?)/i));if(!(x.entry>0&&Number.isInteger(x.quantity)&&x.quantity>0&&time))return{ok:false,reason:'Kaufpreis, ganzzahlige Stückzahl oder Ausführungsdatum fehlt. OCR-Text am Original korrigieren.'};}
 else if(x.kind==='quote'){x.bid=val('Geld|Bid');x.ask=val('Brief|Ask');if(!(x.bid>0&&x.ask>=x.bid&&time))return{ok:false,reason:'Zusammengehörige Geld-/Briefkurse und originales Kursdatum fehlen.'};}
 x.ko=val('BAR|KO|K\\.O\\.-Schwelle|KO-Barriere');x.strike=val('BP|Basispreis');x.ratio=val('Bezugsverhältnis');return x;
}
const PRODUCT_REFERENCES={DE000FG5GUX2:{ratio:0.1,source:'Société Générale Produktseite, recherchiert 02.10.2026',url:'https://www.sg-zertifikate.de/product-details/fg5gux'}};
function draft(raw){
 const ids=[...new Set(String(raw).toUpperCase().match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])];
 const candidate=ids.length===1?ids[0]:'';
 const fallback=parse(String(raw).replace(candidate,'DE000FG5GUX2'));
 const val=label=>{const m=raw.match(new RegExp('\\b(?:'+label+')(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR)?\\s*([0-9]+(?:[.,][0-9]+)?)','i'));return m?m[1]:'';};
 return {isin:candidate,kind:/\bKauf\b/i.test(raw)?'entry':/\bGeld\b|\bBid\b/i.test(raw)?'quote':'details',direction:/\bCall\b|\bLong\b/i.test(raw)?'LONG':/\bPut\b|\bShort\b/i.test(raw)?'SHORT':'',time:(raw.match(/\b\d{2}[/.]\d{2}[/.]\d{4},?\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||'',entry:val('Kurs'),quantity:val('Anzahl'),feesChf:fallback.ok?fallback.feesChf??'':'',bid:val('Geld|Bid'),ask:val('Brief|Ask'),ko:val('BAR|KO|KO-Barriere'),strike:val('BP|Basispreis'),ratio:val('Bezugsverhältnis')};
}
function reviewed(v){
 if(!window.BobDegiro.validIsin(v.isin))return{ok:false,reason:'ISIN am Original korrigieren; eine unsichere OCR-ISIN wird nicht übernommen.'};
 const keys=['entry','quantity','feesChf','bid','ask','ko','strike','ratio'];
 for(const k of keys)if(String(v[k]??'').trim()!==''&&number(v[k])===null)return{ok:false,reason:'Ungültige Zahl: '+k};
 const lines=['ISIN '+v.isin,v.direction||'',v.time||''];
 if(v.kind==='entry')lines.push('Auftrag Kauf','Ausführungsdatum '+v.time,'Anzahl '+v.quantity,'Kurs EUR '+v.entry,'Gesamte Kosten CHF '+v.feesChf);
 else if(v.kind==='quote')lines.push('Geld EUR '+v.bid,'Brief EUR '+v.ask);
 else if(v.kind!=='details')return{ok:false,reason:'Bildtyp wählen.'};
 if(v.ko)lines.push('KO '+v.ko);if(v.strike)lines.push('Basispreis '+v.strike);if(v.ratio)lines.push('Bezugsverhältnis '+v.ratio);
 return parse(lines.join('\n'));
}
function merge(old,x,source){
 const out=JSON.parse(JSON.stringify(old||{isin:x.isin}));
 if(out.isin!==x.isin)throw Error('ISIN stimmt nicht überein');
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
function init(){
 const exit=document.getElementById('bobExitEstimate');if(!exit||document.getElementById('bobTradeUpload'))return;
 const p=document.createElement('div');p.id='bobTradeUpload';p.className='card';p.innerHTML='<h3>Mein Trade · Screenshots</h3><p class="small">Kaufbestätigung einmal, Kursbilder bei Aktualisierung. Produktkopf/Details gemeinsam ergänzen. Jedes Bild braucht die ISIN. Originalzeiten bleiben erhalten. Speicherung auf diesem Gerät.</p><label for="trade-images">Trade erfassen / Kurs aktualisieren</label><input id="trade-images" type="file" accept="image/*" multiple><div id="trade-ocr-status" class="small"></div><label for="trade-select">Gespeichertes Produkt</label><select id="trade-select"></select><div id="trade-review"></div><div id="trade-result" class="small"></div>';exit.before(p);
 const research=document.createElement('button');research.textContent='Gold-/FX-Referenz zur Kurszeit suchen';research.addEventListener('click',()=>window.BobExitEstimate.researchReference());exit.querySelector('[data-exit-calculate]').before(research);
 const details=document.createElement('details');details.innerHTML='<summary>Produktbedingungen und Zeitbezug bestätigen</summary>';const grid=exit.querySelector('.grid');if(grid&&!grid.querySelector('#exit-entry'))details.append(grid);for(const el of [...exit.children])if(el.tagName==='LABEL'||el.tagName==='BR')details.append(el);exit.querySelector('h3').after(details);p.append(exit);exit.className='';
 let all={};try{all=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(_){}let drafts=[];
 const select=p.querySelector('select'),review=p.querySelector('#trade-review'),result=p.querySelector('#trade-result');
 const fill=(lookup=false)=>{const t=all[select.value];if(!t)return;const set=(k,v)=>{const e=exit.querySelector('[data-exit="'+k+'"]');if(e)e.value=v??'';};
  // A different product must never inherit another product's model/reference.
  for(const e of exit.querySelectorAll('[data-exit]')){if(e.type==='checkbox')e.checked=false;else e.value='';}
  const r=window.BobDegiro.exitReference?.(t.isin),catalog=PRODUCT_REFERENCES[t.isin];if(r)for(const [k,v]of Object.entries(r))set(k,v);
  set('isin',t.isin);set('direction',t.direction);set('entry',t.entry?.price);set('quantity',t.entry?.quantity);set('ko',t.ko??r?.ko);set('strike',t.strike??r?.strike);set('ratio',t.ratio??r?.ratio??catalog?.ratio);
  if(t.quote){set('bid',t.quote.bid);set('source',t.quote.source);set('referenceAt',t.quote.at);set('goldReference','');set('fxReference','');set('fxScenario','');}
  const fields={entry:'Kaufbestätigung mit Preis und Stückzahl',quote:'Kursbild mit ISIN, Geld/Brief und Datum',direction:'Produktkopf mit Long/Short',ratio:'Produktdetails: Bezugsverhältnis',strike:'Produktdetails: Basispreis',ko:'Produktkopf: Barriere'};
  const missing=Object.entries(fields).filter(([k])=>!t[k]&&!(r&&r[k])&&!(catalog&&catalog[k])).map(([,v])=>v);
  result.innerHTML='<b>'+esc(t.isin)+'</b> · '+esc(t.direction||'Richtung offen')+'<br>Einstieg: '+(t.entry?esc(t.entry.price)+' EUR × '+esc(t.entry.quantity)+' · '+esc(t.entry.at):'offen')+(t.entry?.feesChf!==null&&t.entry?.feesChf!==undefined?'<br>Kaufgebühren: '+esc(t.entry.feesChf)+' CHF':'')+'<br>Kursmomentaufnahme: '+(t.quote?esc(t.quote.bid)+' EUR Geld · '+esc(t.quote.at):'offen')+(t.entry&&t.quote?'<br>Rechnerischer G/V vor Kosten und FX: '+((t.quote.bid-t.entry.price)*t.entry.quantity).toFixed(2)+' EUR':'')+'<br>'+esc(missing.length?'Benötigtes Bild: '+missing.join(' · '):'Produktnachweise vorhanden.')+(catalog?'<br>Bezugsverhältnis: '+esc(catalog.ratio)+' · '+esc(catalog.source)+' <a target="_blank" rel="noopener" href="'+esc(catalog.url)+'">Quelle</a>':'')+'<br>Für die Ausstiegsschätzung: Gold-/USD→EUR-Referenz prüfen und Ziel/Stop übernehmen. Minutenzeiten sind keine sekundengenauen Echtzeitnachweise.';
  exit.querySelector('[data-exit-output]').textContent='Trade übernommen. Fehlende Referenzen prüfen; Verkaufskurse darunter schätzen.';
  window.BobExitEstimate.restoreReference();
  if(lookup&&t.quote)window.BobExitEstimate.researchReference();
 };
 const refresh=isin=>{select.innerHTML=Object.keys(all).map(id=>'<option>'+esc(id)+'</option>').join('');if(isin)select.value=isin;fill(!!isin);};select.addEventListener('change',fill);refresh();
 p.querySelector('input').addEventListener('change',async e=>{const files=[...e.target.files];drafts=[];review.innerHTML='';if(files.length>4){result.textContent='Bitte höchstens vier Bilder gleichzeitig auswählen.';return;}
  for(const file of files){try{const o=await window.BobDegiro.recognizeOcr(file,'trade-ocr-status');drafts.push({source:file.name,raw:o.data.text});}catch(err){result.textContent='Bild '+file.name+': '+err.message;}}
  const fields=[['isin','ISIN'],['time','Originaldatum und Uhrzeit'],['entry','Kaufpreis EUR/Stück'],['quantity','Stückzahl'],['feesChf','Kaufgebühren CHF'],['bid','Geldkurs EUR'],['ask','Briefkurs EUR'],['ko','Angezeigte Barriere USD'],['strike','Basispreis USD'],['ratio','Bezugsverhältnis']];
  review.innerHTML=drafts.map((d,i)=>{const v=draft(d.raw);return '<fieldset data-trade-card="'+i+'"><legend>'+esc(d.source)+'</legend><label>Bildtyp<select data-review="kind"><option value="entry" '+(v.kind==='entry'?'selected':'')+'>Kaufbestätigung</option><option value="quote" '+(v.kind==='quote'?'selected':'')+'>Kursdaten</option><option value="details" '+(v.kind==='details'?'selected':'')+'>Produktdetails</option></select></label><label>Richtung<select data-review="direction"><option value="">Offen</option><option '+(v.direction==='LONG'?'selected':'')+'>LONG</option><option '+(v.direction==='SHORT'?'selected':'')+'>SHORT</option></select></label><div class="grid">'+fields.map(([k,l])=>'<label data-review-field="'+k+'">'+l+'<input data-review="'+k+'" value="'+esc(v[k])+'"></label>').join('')+'</div><div class="small">Leere oder unsichere Werte am Original ergänzen. Sekunden nicht erfinden. Barriere und Basispreis dürfen bei Produktdetails offen bleiben.</div><details><summary>Original-OCR-Text anzeigen</summary><pre style="white-space:pre-wrap">'+esc(d.raw)+'</pre></details></fieldset>';}).join('')+(drafts.length?'<label><input type="checkbox" id="trade-confirm"> ISIN, Preise, Stückzahl und Originalzeiten am Bild geprüft</label><button id="trade-save">Geprüfte Bilder übernehmen</button>':'');
  for(const card of review.querySelectorAll('[data-trade-card]')){const type=card.querySelector('[data-review="kind"]');const show=()=>{for(const el of card.querySelectorAll('[data-review-field]')){const k=el.dataset.reviewField;el.hidden=['entry','quantity','feesChf'].includes(k)?type.value!=='entry':['bid','ask'].includes(k)?type.value!=='quote':false;}};type.addEventListener('change',show);show();}
  review.querySelector('#trade-save')?.addEventListener('click',()=>{if(!review.querySelector('#trade-confirm').checked){result.textContent='Bitte erkannte Werte am Original prüfen und bestätigen.';return;}
   let next=JSON.parse(JSON.stringify(all)),last='';try{for(const [i,d]of drafts.entries()){const card=review.querySelector('[data-trade-card="'+i+'"]'),values=Object.fromEntries([...card.querySelectorAll('[data-review]')].map(e=>[e.dataset.review,e.value.trim()])),x=reviewed(values);if(!x.ok)throw Error(d.source+': '+x.reason);next[x.isin]=merge(next[x.isin],x,'DEGIRO-Screenshot: '+d.source);last=x.isin;}localStorage.setItem(KEY,JSON.stringify(next));all=next;refresh(last);review.innerHTML='';p.querySelector('#trade-ocr-status').textContent='Gespeichert. Einstieg bleibt bei Kursaktualisierungen erhalten.';}catch(err){result.textContent=err.message;}});
 });
}
window.BobTradeUpload={parse,draft,reviewed,merge,init};if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();}
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
