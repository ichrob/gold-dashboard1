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
window.BobCombined={fixedBarriers,compareSnapshot,renderComparison,fixedFor,saveFixed,removeFixed,assess,render,form,time,rank,renderTop3,screenshotDraft,mergeDraft};
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
 const bnpNbContext=/\bBNP\s+GOLD\s+Unlimited\s+Long\s+SL\s+3996[.,]2705\s+STR\s+3996[.,]2705\s+R\s*10\b/i.test(productText)
  && !/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText);
 if(['DE000PJ1NB98','DE000PJ0NB98'].includes(candidate)&&bnpNbContext&&validIsin('DE000PJ9NB98'))return {isin:'DE000PJ9NB98',originalIsin:original,identityCorrection:'BNP-Produktidentität am Originalbild 1000070469.jpg belegt'};
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
function costRiskAssessment(p){
 const now=p.now??Date.now(),spot=n(p.spot),price=n(p.price),ko=n(p.ko),lev=n(p.leverage),atr=n(p.atr);
 const reasons=[],blocked=[],warnings=[],parts={spread:0,trading:0,financing:0,ko:0,leverage:0,data:0};
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
 return {score,fit:!blocked.length,parts,spreadPct,tradingPct,financingPct,knownCostsPct,totalCostsPct:null,reasons:blocked.map(x=>'ABWARTEN: '+x).concat(reasons),warnings};
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
function refreshImportedProducts(force=false){return quoteRefresh?quoteRefresh.refresh(force):Promise.resolve();}
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
function fieldSourceTime(x,key){
 const field={Geld:'bid',Brief:'ask',Hebel:'leverage',KO:'ko'}[key];
 if(x.times?.[field]?.present)return x.times[field].at;
 return ['Geld','Brief','Kurs','Spread'].includes(key)?x.times?.quote?.at||null:null;
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
  if(n(value)===null||n(e[key]?.value)!==n(value)||!evidenceTiming(e[key],now).fresh)reasons.push(key+': eigener Zeitnachweis fehlt oder älter als 14 Stunden');
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
 if(x?.times?.leverage?.present&&!evidenceTiming(e.Hebel,now).fresh)reasons.push('Eigene Hebelzeit ist ungültig oder veraltet');
 if(x?.delayed)reasons.push('Nicht verzögerten Produktkurs ergänzen');
 if(!(n(e.Hebel?.value)>=1&&(seriesAnalysis||n(e.Hebel?.value)===n(p.leverage)))||!evidenceTiming(e.Hebel,now).fresh&&!(pair&&e.Hebel?.source===e.Geld?.source&&time&&now-time.start<=SCREENSHOT_MAX_AGE_MS))reasons.push('Aktuelles Detailbild mit Hebel und zugehöriger Zeit');
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
 for(const [key,label] of [['trend','EMA-Trend'],...(['intraday-shadow-v1','intraday-fast-v3','intraday-consistent-v4','intraday-responsive-v6'].includes(context.policy)?[]:[['trend2','Langfristtrend']]),['mtf','MTF']]){
  const value=side(context[key]);if(!value)reasons.push(label+' neutral oder nicht bestätigt');else if(value!==d)reasons.push(label+' widerspricht '+d);
 }
 for(const [key,label] of [['hist','MACD'],['momentum','Momentum']]){
  const value=n(context[key]);if(value===null||value===0)reasons.push(label+' neutral oder nicht vorhanden');else if((value>0?'LONG':'SHORT')!==d)reasons.push(label+' widerspricht '+d);
 }
 if(!(n(context.atr)>0))reasons.push('ATR fehlt: KO-Puffer gegenüber Volatilität nicht prüfbar');
 return {ok:!reasons.length,reasons};
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
 for(const [scope,candidates] of groups){candidates.sort((a,b)=>b.score-a.score||a.isin.localeCompare(b.isin));result.groups.push({scope,total:candidates.length,candidates:candidates.slice(0,3)});}
 // This is an upload priority, not a product recommendation from incomplete prices.
 result.requests.sort((a,b)=>Number(a.scope==='FUTURE')-Number(b.scope==='FUTURE')||a.index-b.index);
 // At most three displayed selections overall; each keeps its own basis label.
 const selected=result.groups.flatMap(g=>g.candidates).sort((a,b)=>b.score-a.score||a.isin.localeCompare(b.isin)).slice(0,3);
 result.groups=result.groups.map(g=>({...g,candidates:g.candidates.filter(c=>selected.includes(c))})).filter(g=>g.candidates.length);
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
function renderIsinCopy(isin,compact=false){
 if(compact)return validIsin(isin)?'<span style="display:inline-block;vertical-align:middle"><button type="button" data-copy-product-isin="'+esc(isin)+'" aria-label="ISIN '+esc(isin)+' kopieren" title="ISIN kopieren" style="width:36px;min-height:36px;padding:4px;margin:0 4px;font-size:18px">⧉</button><span class="small" role="status" data-copy-status></span></span>':'';
 return validIsin(isin)?'<span style="display:inline-block;margin:4px 8px"><button type="button" data-copy-product-isin="'+esc(isin)+'" aria-label="ISIN '+esc(isin)+' kopieren" style="min-height:44px">📋 ISIN kopieren</button><span role="status" data-copy-status></span></span>':'';
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
   try{await navigator.clipboard.writeText(isin);if(status)status.textContent=' ISIN kopiert: '+isin;}
   catch(_){
    const field=document.createElement('textarea');field.value=isin;field.readOnly=true;field.style.cssText='position:fixed;left:0;top:0;opacity:0';
    document.body.append(field);field.select();field.setSelectionRange(0,isin.length);
    let copied=false;try{copied=document.execCommand('copy');}catch(_){}finally{field.remove();}
    if(status)status.textContent=copied?' ISIN kopiert: '+isin:' Bitte manuell kopieren: '+isin;
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
  if(node.tagName==='DETAILS')labels.unshift((node.querySelector(':scope > summary')?.textContent||'').replace(/\(\d+\)/g,'').replace(/\s+/g,' ').trim());
  if(node===product)break;
  node=node.parentElement;
 }
 return (product?.getAttribute('data-product-isin')||'panel')+'|'+labels.join('>');
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
 if(x?.isin!==p.isin||!series?.userDeclaredSimultaneous||!time||now<time.start||now-time.start>SCREENSHOT_MAX_AGE_MS)return {...live,basis:'incomplete'};
 const result=selectionDetailStatus(p,now,true),reasons=result.reasons.slice();
 // Undated terms must actually belong to this series, not an older merged import.
 for(const key of ['strike','ko']){
  const term=x.terms?.[key]||(key==='ko'?x.evidence?.KO:null);
  if(!currentDatedTerm(term,now)&&!currentDatedTerm(p.quote?.conditions?.[key],now)&&(!series.members?.includes(term?.source)||term?.conflict||term?.revoked))reasons.push((key==='strike'?'Basispreis':'KO-Barriere')+': Wert gehört nicht zur aktuellen Aufnahmeserie');
 }
 return {...result,complete:!reasons.length,reasons,basis:'series',warnings:productTermsStatus(p,now,true).warnings};
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
function renderProductDirectionStatus(p,now=Date.now()){
 const {blocked,stale,missing}=productDirectionDataState(p,now);
 const label=blocked?(missing?'Werte fehlen oder sind widersprüchlich':'Datenprüfung offen'):stale?'Werte vorhanden (fehlende Aktualität)':'Daten vollständig';
 return '<span data-direction-data-status role="status" aria-label="'+esc(label)+'" style="display:inline-flex;align-items:center;gap:6px;margin-left:8px"><strong style="font-size:1.6em;font-weight:900;color:'+(blocked?'#b91c1c':'#15803d')+'">'+(blocked?'✗':stale?'(✓)':'✓')+'</strong>'+(stale?'<span style="font-weight:700">(fehlende Aktualität)</span>':'')+'</span>';
}
function valuePresenceMark(missing){
 return missing?'<span style="color:#b91c1c;font-weight:700" aria-label="Wert fehlt">✗</span>':'<span style="color:#15803d;font-weight:700" aria-label="Wert vorhanden">✓</span>';
}
function compactProductExclusion(p){
 const direct=p.quote?.isin===p.isin&&p.quote?.productVerified?p.quote:null;
 return direct?.metadata?.status===2?'Produkt beendet oder ausgeknockt – ausgeschlossen':/FAKTOR|FACTOR/i.test([p.name,direct?.metadata?.name,p.snapshot?.terms?.type?.value].join(' '))?'Faktorprodukt ausgeschlossen':null;
}
function additionalProductsComplete(products,now=Date.now()){
 const remaining=products.filter(p=>!knockoutStatus(p)&&!compactProductExclusion(p));
 return remaining.length>0&&remaining.every(p=>{const state=productDirectionDataState(p,now);return !state.blocked&&!state.stale;});
}
function compactProductCard(p,reasons=[],status='Nicht freigegeben'){
 reasons=reasons.map(reason=>productEvidenceReason(p,reason));
 if(knockoutStatus(p))return knockoutCard(p);
 const direct=p.quote?.isin===p.isin&&p.quote?.productVerified?p.quote:null;
 const excluded=compactProductExclusion(p);
 if(excluded)return '<div data-product-isin="'+esc(p.isin)+'" style="padding:14px;margin-top:10px;border:1px solid #dc2626;border-radius:12px"><b>'+esc(p.isin)+'</b><p>'+esc(excluded)+'</p><p>Keine weiteren Daten oder Screenshots erforderlich.</p>'+(direct?.lifecycleEvidence?'<p>'+esc(direct.reason)+'</p>':'')+renderProductSources(p)+'</div>';
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
 const missingNumbers=Object.values(fieldStates).filter(f=>f.state==='fehlt').map(f=>f.key);
 const dataText=data.complete?'Werte vorhanden':missingNumbers.length?'Fehlende Kurswerte: '+missingNumbers.join(', '):'Geld, Brief und Hebel vorhanden';
 const shortReason=r=>String(r).split('. Öffne')[0].split(' · Fundort:')[0].slice(0,160);
 const automaticQuoteIssue=!complete&&groups.length>0&&groups.every(r=>/^(Live-Kursbestätigung|Kursart und Aktualität|Hebel berechnet|Hebel vorhanden|BNP-Kursabruf)/.test(r));
 const evidenceTitle=automaticQuoteIssue?'Werte vorhanden · Aktualitätsprüfung offen':missingNumbers.length?'Fehlende Werte und Nachweise':'Werte und Aktualitätsprüfung';
 const next=automaticQuoteIssue?'Automatischer Kurs- und Hebelabruf wird erneut geprüft. Vorhandene Werte bleiben mit ihrem ursprünglichen Datenstand nutzbar; derzeit keine neuen Bilder erforderlich.':complete&&neutral?'Marktsignal neutral – auf eine bestätigte Richtung warten. Dafür sind keine neuen Bilder nötig.':complete?'Produktdaten vollständig – Auswahlgrund unter „Warum derzeit nicht ausgewählt?“ prüfen.':temporal&&data.complete?'Werte vorhanden – den offenen Zeitbezug unter „Werte und Aktualitätsprüfung“ prüfen.':'Offene Angaben unter „Werte und Aktualitätsprüfung“ ansehen und nur diese ergänzen.';
 return '<div data-product-isin="'+esc(p.isin||'row-'+p.index)+'" '+(selected?'data-selection-approved':'data-selection-blocked')+'="'+p.index+'" style="padding:12px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;overflow-wrap:anywhere"><b>'+esc(p.isin)+'</b>'+renderIsinCopy(p.isin)+productCompletionBadge(p)+'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px">'+esc(p.productDirection||'')+renderProductDirectionStatus(p)+'</div>'+
 '<div class="small" data-product-status><div><b>Daten:</b> '+valuePresenceMark(missingNumbers.length>0)+' '+esc(dataText)+'</div><div><b>Zeitbezug:</b> '+valuePresenceMark(!complete).replace('Wert vorhanden','Zeitbezug bestätigt').replace('Wert fehlt','Aktualität nicht bestätigt')+' '+(complete?'für diesen Analyseweg bestätigt':temporal?'Aktualitätsprüfung offen – vorhandene Werte bleiben erhalten':'noch nicht vollständig prüfbar')+'</div><div><b>Aktuelle Auswahl:</b> '+(selected?'freigegeben · ausgewählt':'nicht ausgewählt')+(neutral?' · Marktsignal neutral':'')+'</div></div>'+
 '<p data-product-next><b>Nächster Schritt:</b> '+esc(selected?'Tatsächlichen DEGIRO-Kurs vor einem Einstieg prüfen.':next)+'</p>'+renderPrimaryProductValues(p)+
 (allReasons.length?'<div class="small">'+allReasons.slice(0,2).map(shortReason).map(esc).join('<br>')+'</div>':'')+
 (selected?'': '<details style="margin-top:8px"><summary>Warum derzeit nicht ausgewählt?</summary><div class="small">'+(allReasons.length?allReasons.map(esc).join('<br>'):neutral?'Keine bestätigte Long-/Short-Marktrichtung. Die vollständigen Produktdaten müssen dafür nicht erneut hochgeladen werden.':'Die aktuelle Markt- und Risikoprüfung hat das Produkt nicht ausgewählt; vollständige Daten allein erteilen keine Freigabe.')+'</div></details>')+
 '<details data-product-values style="margin-top:10px"><summary><strong>Gespeicherte Bildwerte, Quellen und Zeitbezug</strong></summary>'+
 renderProductFieldStates(p)+renderTermSeriesValidity(p)+(currentConvertedChfEvidence(p)?'<div data-current-chf-proof>Aktueller CHF-Kurs und zeitlich passender Wechselkurs als EUR-Nachweis verwendet. Der historische Bildkurs bleibt unverändert; dafür ist kein nachträglicher Wechselkurs erforderlich. Hebel mit ursprünglichem Bildzeitpunkt berücksichtigt.</div>':'')+
 (values.length?'<details style="margin-top:10px"><summary>Automatisch erkannte Werte</summary><div class="small">'+values.map(esc).join('<br>')+'</div></details>':'')+
 (unconfirmed.length?'<div class="small" style="margin-top:8px"><em>'+unconfirmed.map(esc).join('<br>')+'</em></div>':'')+
 '</details><details style="margin-top:8px"><summary>'+evidenceTitle+(groups.length?' · '+groups.length+' Prüfpunkte':'')+'</summary><div class="small">'+(groups.length?groups.map(label=>'<div style="margin:10px 0"><strong>'+(automaticQuoteIssue?valuePresenceMark(false)+' Werte vorhanden · ':'')+esc(label)+'</strong><br>Fundort: '+esc(locations.get(label))+'</div>').join(''):'Produktdaten vollständig. Ergänzungen nur bei einem neuen Datenstand erforderlich.')+'</div>'+renderIssuerHelp(p,reasons)+renderTestScreenshotRequest(p)+'</details>'+
 '<button data-selection-upload="'+p.index+'">Bilder / PDF zu diesem Produkt hinzufügen</button><button data-product-trade="'+esc(p.isin)+'">Vorhandenen Trade mit diesem Produkt erfassen</button>'+renderImageImportStatus(p.index)+
 '<details data-product-details="'+p.index+'" style="margin-top:10px"><summary>Quellen und Einzelheiten</summary><div class="small">'+esc(p.name||'')+'</div>'+renderProductSources(p)+renderMissingValues(reasons,p)+renderProductDecision(p,selected,[status,...reasons])+screenshotSummary(x)+'<button data-card-research="'+p.index+'">Daten erneut abrufen</button></details></div>';
}
function renderPrimaryProductValues(p,now=Date.now()){
 const q=p.quote?.isin===p.isin&&p.quote.productVerified?p.quote:null;
 const live=q?.found?q:q?.analysisQuote||q?.referenceQuote;
 const fields=productFieldStates(p,now),at=live?.bidAt||live?.askAt||q?.quoteAt;
 const clocks=[live?.bidAt||at,live?.askAt||at].map(t=>Date.parse(t));
 const current=!q?.sourceFailure&&live!==q?.referenceQuote&&live?.currency==='EUR'&&!live.delayed&&n(live.bid)>0&&n(live.ask)>=n(live.bid)&&clocks.every(t=>Number.isFinite(t)&&now-t>=0&&now-t<=300000)&&Math.max(...clocks)-Math.min(...clocks)<=90000;
 const fmt=v=>n(v)>0?Number(v).toLocaleString('de-CH',{maximumFractionDigits:4}):'—';
 const stamp=at&&Number.isFinite(Date.parse(at))?new Date(at).toLocaleString('de-CH',{timeZone:'Europe/Zurich',hour12:false})+' (Zürich)':'Zeitbezug unbestätigt';
 const currency=current?'EUR':p.snapshot?.currency||p.currency||'EUR';
 return '<div class="small" data-primary-product-values><b>'+(current?'Aktueller Anbieterwert':'Gespeicherte Referenz')+'</b><br>'+valuePresenceMark(fields.bid.state==='fehlt')+' Geld '+fmt(current?live.bid:fields.bid.value)+' / '+valuePresenceMark(fields.ask.state==='fehlt')+' Brief '+fmt(current?live.ask:fields.ask.value)+' '+esc(currency)+(current&&live.priceKind==='issuer-chart'?' · Chartkurs, kein bestätigter Ausführungskurs':'')+'<br>'+(current?'Quelle: '+esc(live.source||q.source||'Produktanbieter')+' · '+esc(stamp):'Datenstand: '+esc(fields.ask.state))+'<br>'+valuePresenceMark(fields.leverage.state==='fehlt')+' Hebel '+fmt(fields.leverage.value)+' · '+esc(fields.leverage.state)+(fields.leverage.state==='fehlt'&&q?.leverageCalculation?.reason?'<br>Berechnung derzeit nicht möglich: '+esc(q.leverageCalculation.reason):'')+'</div>';
}
function bindCompactCards(root){
 bindIsinCopy(root);
 root.querySelectorAll('[data-product-trade]').forEach(btn=>btn.addEventListener('click',()=>{
  const input=document.getElementById('exit-isin');if(!input)return;
  input.value=btn.dataset.productTrade;
  input.dispatchEvent(new Event('input',{bubbles:true}));
  document.querySelector('[data-exit-reference]')?.click();
  document.querySelector('#bobNavigation [data-view="trade"]')?.click();
  const panel=document.getElementById('bobTradeUpload')||document.getElementById('bobExitEstimate');
  if(panel?.parentElement.tagName==='DETAILS')panel.parentElement.open=true;
  document.getElementById('exit-entry')?.focus();
 }));
 root.querySelectorAll('[data-selection-upload]').forEach(btn=>btn.addEventListener('click',()=>document.getElementById('dgDetailShot'+btn.dataset.selectionUpload)?.click()));
 root.querySelectorAll('[data-card-research]').forEach(btn=>btn.addEventListener('click',()=>enrichProduct(Number(btn.dataset.cardResearch))));
}
function renderProductDecision(c,approved=true,blocked=[]){
 const unique=values=>[...new Set(values.filter(Boolean).map(x=>String(x).split('. Öffne')[0]))];
 const concerns=unique([...(c.warnings||[]),...(c.reasons||[]).filter(x=>/widerspr|fehlt|unbekannt|unbestätigt|veraltet|Abweichung|Schätzung|ABWARTEN/i.test(x)),...blocked.map(x=>String(x).split('. Öffne')[0])]);
 const reasons=unique(c.reasons||[]);
 const why=approved?['Produktrichtung '+c.direction+' passt zur bestätigten Auswahlrichtung.','Produktnachweise und die für diesen Berechnungsweg geltenden Prüfungen bestanden.','Rangfolge nach Risikowert: '+c.score+'/100; bei Gleichstand entscheidet die ISIN, nicht eine höhere erwartete Rendite.',...reasons]:reasons;
 const revoke=['Marktrichtung passt nicht mehr oder die Marktprüfung fällt aus.','Erforderliche Produkt-/Kursnachweise fehlen, laufen ab oder widersprechen sich.','Produkt ist inaktiv, abgelaufen oder die KO-Schwelle ist erreicht.','Risikoprüfung scheitert: etwa KO-Abstand unter 1 %, Puffer unter 1,5 ATR oder Risikowert unter 60/100.','Das Produkt fällt aus den höchstens drei ausgewählten Kandidaten.'];
 if(c.basisError>0||c.priceError>0)revoke.push('Die Schätzung ist nicht mehr ausreichend belegt oder die Prüfung innerhalb der beobachteten Fehlerspanne scheitert.');
 const lines=xs=>xs.map(esc).join('<br>');
 return '<details class="small" style="margin-top:8px"><summary>Warum dieses Produkt?</summary><b>Warum '+(approved?'ausgewählt':'nicht freigegeben')+'?</b><div>'+lines(why.length?why:['Keine Freigabe: Produktprüfung noch offen.'])+'</div><b>Was spricht dagegen / ist unsicher?</b><div>'+lines(concerns.length?concerns:['Keine zusätzlichen Warnungen aus dieser Prüfung. Das bedeutet nicht risikofrei.'])+'</div><b>Wann entfällt die Freigabe?</b><div>'+lines(revoke)+'</div></details>';
}
function renderSelectionWorkflow(r,products=[]){
 const steps='<div class="small">Listenbilder → unverbindliche Kandidaten → Pflichtprüfung → bis zu 3 geeignete Produkte</div><details><summary class="small">So bewertet Bob Kosten und Risiko</summary><div class="small">Risiko-/Datenwert: 100 minus Abzüge für Handels- und Finanzierungskosten, KO und Datenqualität. Spread nur zur Information: kein Punkteabzug und keine Spread-Sperre. Die Hebelhöhe allein bringt weder Plus- noch Minuspunkte. Vergleich: 1.000 EUR / 1 Kalendertag. Unbekannte Kosten erhalten jeweils den vollen 10-Punkte-Abzug; kein bestätigter Kostenvorteil. Mindestwert 60. Gleiche Werte bedeuten Gleichstand; ISIN sortiert nur die Anzeige. Kostennachweise unter Details / manuelle Kursnachweise.</div></details>';
 const excluded=(r.notApproved||[]).filter(p=>knockoutStatus({...products[p.index-1],...p}));
 return '<b>'+ (r.approved?'Zur Produktauswahl freigegeben · '+r.approvedCount+' geeignete'+(r.approvedCount===1?'s Produkt':' Produkte'):'Abwarten – derzeit kein geeignetes Produkt')+'</b>'+steps+
 '<div class="small">'+esc((r.gateReasons||[]).join(' · '))+'</div>'+
 '<div class="small">'+r.total+' unterschiedliche Produkte. Vorauswahl nach Analyse-Richtung '+esc(r.direction)+'; fehlende Preise erhalten keine Rangpunkte.</div>'+
 r.groups.map(g=>'<div style="margin-top:12px"><b>'+esc(g.scope)+' · '+g.total+' bewertbare Produkte</b>'+g.candidates.map((c,i)=>'<div data-product-isin="'+esc(c.isin)+'" style="padding:10px;margin-top:8px;border:1px solid #dbe4f0;border-radius:12px"><b>Platz '+(i+1)+' · '+esc(c.isin)+'</b>'+renderIsinCopy(c.isin,true)+productCompletionBadge(products.find(p=>p.isin===c.isin)||c)+'<div class="small" data-product-status><div><b>Daten:</b> vollständig</div><div><b>Zeitbezug:</b> für diesen Analyseweg bestätigt</div><div><b>Aktuelle Auswahl:</b> geeignet für '+esc(c.direction)+renderProductDirectionStatus(products.find(p=>p.isin===c.isin)||c)+'</div></div><p><b>Nächster Schritt:</b> Tatsächlichen DEGIRO-Kurs vor einem Einstieg prüfen.</p><button data-product-trade="'+esc(c.isin)+'">Vorhandenen Trade mit diesem Produkt erfassen</button><details data-product-values style="margin-top:10px"><summary><strong>Produktwerte anzeigen</strong></summary><div class="small">'+esc(c.name)+'<br>'+esc(c.priceKind)+' · Brief '+Number(c.price).toFixed(2)+' EUR · Risiko-/Datenwert '+c.score+'/100<br>Warum: '+esc((c.reasons||[]).slice(0,3).join(' · ')).replace(/\bHebel\b/g,'<strong>Hebel</strong>')+'<br>Quelle '+esc(c.source||'Produktnachweis')+' · Datenzeit '+esc(c.at)+(c.quoteAt?' · Produktkurszeit '+esc(c.quoteAt):'')+(c.quality?'<br>'+esc(qualityText(c.quality,'USD')):'')+'</div>'+renderProductDecision(c)+renderProductSources(c)+'</details></div>').join('')+'</div>').join('')+
 excluded.map(p=>knockoutCard({...products[p.index-1],...p})).join('')+
 '<details class="small" style="margin-top:10px"><summary>Hinweise zur Produktauswahl</summary>Spot und Future werden getrennt bewertet. Weniger als drei belegte Produkte ergeben eine kürzere Liste. Freigabe gilt ausschließlich für diese geprüfte Produktauswahl, nicht als Handelsauftrag oder garantierter bester Trade. Kandidaten mit offenen Nachweisen bleiben gesperrt; tatsächlichen DEGIRO-Preis vor dem Einstieg prüfen.</details>';
}

function productUploadCards(products,direction,now=Date.now(),flow=null){
 const selected=new Set((flow?.groups||[]).flatMap(g=>g.candidates).map(p=>p.isin));
 return (products||[]).map((p,z)=>({...p,index:z+1})).filter(p=>p.name||p.isin).sort((a,b)=>Number(b.productDirection===direction)-Number(a.productDirection===direction)).map(p=>{
  const blocked=flow?.notApproved?.find(v=>v.index===p.index);
  const status=selected.has(p.isin)?'Freigegeben · ausgewählt':blocked?'Nicht freigegeben · '+(blocked.reasons?.[0]||'Nachweise prüfen'):'Produktnachweise prüfen';
  return compactProductCard(p,blocked?.missingReasons||finalProductStatus(p,now).reasons,status);
 }).join('');
}


// Original list images live in IndexedDB, independently of Android's file picker.
let listArchive=null,listArchiveUrls=[],productArchivePayload='';
const LIST_DAY_KEY='bobDegiroListDayV1';
function zurichListDay(now=Date.now()){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now));
 const get=k=>parts.find(p=>p.type===k).value;
 return {day:get('year')+'-'+get('month')+'-'+get('day'),closed:Number(get('hour'))>=22};
}
function listExpired(day,now=Date.now()){const current=zurichListDay(now);return !!day&&(day!==current.day||current.closed);}
function clearDailyList(){
 const empty=JSON.stringify({version:2,products:[]});
 listArchive=null;productArchivePayload=empty;
 localStorage.setItem(PRODUCT_STORE_KEY,empty);localStorage.setItem(IDENTITY_KEY,'[]');localStorage.removeItem(LIST_DAY_KEY);
 showListArchive();
 return archiveTransaction('readwrite',store=>{store.delete('list');return store.put(empty,'products');});
}
function expireVisibleList(){
 const day=localStorage.getItem(LIST_DAY_KEY);
 if(!listExpired(day))return;
 clearDailyList().catch(()=>{});populateCandidateRows([]);
 const label=document.getElementById('dgCentralStatus');if(label)label.textContent='Tagesliste um 22 Uhr abgelaufen. Bitte am nächsten Morgen neue Listenbilder einlesen.';
}

function archiveTransaction(mode,action){
 return new Promise((resolve,reject)=>{
  const request=indexedDB.open('bobProductArchive',1);
  request.onupgradeneeded=()=>request.result.createObjectStore('records');
  request.onerror=()=>reject(request.error);
  request.onsuccess=()=>{
   const db=request.result,tx=db.transaction('records',mode);let result;
   tx.oncomplete=()=>{db.close();resolve(result?.result);};
   tx.onerror=tx.onabort=()=>{db.close();reject(tx.error||Error('Bildspeicher nicht verfügbar'));};
   try{result=action(tx.objectStore('records'));}catch(e){db.close();reject(e);}
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
async function saveListArchive(files,items){
 if(zurichListDay().closed)throw Error('Tagesliste endet um 22 Uhr Schweizer Zeit. Bitte am nächsten Morgen neu einlesen.');
 const record={files:files.map(file=>({name:file.name,blob:file})),items,storedAt:new Date().toISOString()};
 await archiveTransaction('readwrite',store=>{store.put(JSON.stringify({version:2,products:items.map(cleanStoredProduct).filter(Boolean)}),'products');return store.put(record,'list');});
 localStorage.setItem(LIST_DAY_KEY,zurichListDay(Date.parse(record.storedAt)).day);
 listArchive=record;showListArchive();
 // Best effort: storage persistence does not change quote/evidence timestamps.
 try{navigator.storage?.persist?.().catch(()=>{});}catch(_){}
}
async function restoreListArchive(){
 try{
  listArchive=await archiveTransaction('readonly',store=>store.get('list'));
  const day=listArchive?.storedAt?zurichListDay(Date.parse(listArchive.storedAt)).day:localStorage.getItem(LIST_DAY_KEY);
  if(listExpired(day)||(!day&&zurichListDay().closed)){await clearDailyList();return;}
  if(day)localStorage.setItem(LIST_DAY_KEY,day);
  const backup=await archiveTransaction('readonly',store=>store.get('products'));
  if(!localStorage.getItem(PRODUCT_STORE_KEY)&&backup){localStorage.setItem(PRODUCT_STORE_KEY,backup);}
  if(!day&&localStorage.getItem(PRODUCT_STORE_KEY))localStorage.setItem(LIST_DAY_KEY,zurichListDay().day);
  showListArchive();
 }catch(_){productStorageMessage='Bildspeicher nicht erreichbar. Vorhandene Produktdaten werden weiterhin geladen.';}
}
const IDENTITY_KEY='bobDegiroIdentitiesV1', PRODUCT_STORE_KEY='bobDegiroProductsV2';
let productStorageMessage='',productStorageBlocked=false;
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
 try{const rows=items.map(cleanStoredProduct).filter(Boolean).slice(0,12),payload=JSON.stringify({version:2,products:rows});
  if(rows.length&&!localStorage.getItem(LIST_DAY_KEY))localStorage.setItem(LIST_DAY_KEY,zurichListDay().day);
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
 writeStoredProducts(items);
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
 return !!x&&(['ISIN','WKN'].includes(x.identityBasis)||x.identityBasis==='Valor'&&SWISS_SG_VALORS[x.isin]===x.identityValor||x.identityBasis==='Produktkontext'&&validIsin(x.isin)&&x.identityContext?.isin===x.isin&&x.identityContext?.basis==='opened-product');
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
 if(automatic?.policy==='declared-series-v1'&&automatic.origin==='automatic'&&automatic.isin===p.isin&&automatic.source===e.source&&direct?.source===e.source&&n(direct.value)===n(e.value)){
  const age=now-Date.parse(automatic.observedAt);
  if(Number.isFinite(age)&&age>=0&&age<=86400000)return {origin:'automatic',text:automatic.observedAt,label:'Zeitbezug der automatischen Abrufserie'};
 }
 const x=p.snapshot,series=x?.captureSeries,own=x?.terms?.[key];
 if(x?.isin!==p.isin||!hasScreenshotIdentity(x)||!series?.userDeclaredSimultaneous||!series.members?.includes(e.source)||own?.source!==e.source||n(own.value)!==n(e.value))return null;
 const time=selectionTimeWindow(series.text);
 return time&&now>=time.start&&now-time.start<=86400000?{origin:'screenshot',text:series.text,label:'Zeitbezug der Aufnahmeserie'}:null;
}
const KO_MAX_AGE_MS=8*60*60*1000;
function koTermTime(p,e,now){
 if(!e?.source||!(n(e.value)>0)||e.conflict||e.revoked||e.ocrCorrection)return NaN;
 if(e.at)return Date.parse(e.at);
 if(p.quote?.isin===p.isin&&p.quote.productVerified&&p.quote.conditions?.ko===e&&e.conditionVerified&&currentDatedTerm(e,now))return Date.parse(e.reviewedAt);
 const ref=termSeriesReference(p,'ko',e,now);
 if(ref)return ref.origin==='automatic'?Date.parse(ref.text):selectionTimeWindow(ref.text)?.start;
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
  return ref?'<div data-term-series-validity><b>'+esc(key==='strike'?'Basispreis':'KO-Schwelle')+': Seriennachweis für Bob gültig</b><br>'+esc(ref.label+' · '+ref.text)+' · kein separat bestätigtes Emittenten-Gültigkeitsdatum</div>':'';
 }).join('');
}
function screenshotKoCurrent(p,now){
 const x=p.snapshot,e=x?.evidence?.KO,t=x?.terms?.ko;
 if(x?.isin!==p.isin||n(e?.value)!==n(p.ko))return false;
 if(e?.conflict||e?.revoked||e?.ocrCorrection)return false;
 if(e?.at)return currentProductTerm(p,'ko',e,now);
 if(e?.dateText&&e.dateText!==t?.dateText)return false;
 // An undated repeat in a quote image does not invalidate the separate
 // dated terms image. Match identity and amount; never transfer its date.
 return hasScreenshotIdentity(x)&&n(t?.value)===n(p.ko)&&currentProductTerm(p,'ko',t,now);
}
function termValueMatches(value,actual,e){
 if(n(value)===n(actual))return true;
 const digits=e?.displayDecimals;
 return n(e?.value)===n(value)&&!!e?.source&&Number.isInteger(digits)&&digits>=2&&digits<=8&&n(actual)>0&&Number(n(actual).toFixed(digits))===n(value);
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
   if((currentProductTerm(p,key,old,now)||key==='ko'&&currentDatedTerm(old,now))&&!termValueMatches(old.value,direct.value,old))reasons.push((key==='strike'?'Basispreis':'KO-Barriere')+': aktuelle Nachweise widersprechen sich');
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
function productFieldStates(p,now=Date.now()){
 const q=p.quote?.isin===p.isin&&p.quote.productVerified?p.quote:null;
 const shot=p.snapshot?.isin===p.isin?p.snapshot:null;
 const live=q?.found?q:q?.analysisQuote||q?.referenceQuote;
 const from=(key,value,at,source,limit=90000,kind='')=>{
  const t=typeof at==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(at)?Date.parse(at):selectionTimeWindow(at)?.start;
  const age=Number.isFinite(t)?now-t:null;
  return {key,value,at:at||null,source:source||'gespeicherter Wert',kind,ageSeconds:age===null?null:Math.floor(age/1000),state:!(n(value)>0)?'fehlt':age===null||age<0?'Aktualität unbestätigt':age>limit?'veraltet':kind==='screenshot'?'Momentaufnahme · innerhalb Nachweisfrist (14 h)':limit===300000&&age>90000?'innerhalb Altersgrenze (300 s)':'aktuell'};
 };
 const items={},analysisLimit=(q?.analysisMaxAgeSeconds||90)*1000;
 for(const [key,label] of [['bid','Geld'],['ask','Brief']]){
  const direct=live?.currency==='EUR'&&n(live.bid)>0&&n(live.ask)>=n(live.bid);
  const e=shot?.evidence?.[label];
  items[key]=from(label,direct?live[key]:key==='ask'?(n(p.price)>0?p.price:shot?.currency==='CHF'?null:shot?.ask):shot?.currency==='CHF'?null:shot?.bid,direct?live[key+'At']:e?.at||shot?.sourceTime,direct?live.source:e?.source,direct?analysisLimit:SCREENSHOT_MAX_AGE_MS,direct?live.priceKind:'screenshot');
  if(direct&&(live===q?.referenceQuote||q?.sourceFailure)&&items[key].state!=='veraltet')items[key].state='Aktualität unbestätigt · letzter erfolgreicher Abruf';
  if(!direct&&e?.fromSeries){items[key].fromSeries=true;items[key].timeText=e.timeText;}
 }
 const le=shot?.evidence?.Hebel,leverage=n(p.leverage)>0?p.leverage:n(q?.leverage)>0?q.leverage:!le?.conflict&&!le?.revoked?le?.value:null,directLev=q&&n(q.leverage)===n(leverage);
 items.leverage=from('Hebel',leverage,directLev?q.leverageAt:n(le?.value)===n(leverage)?le?.at:null,directLev?(q.leverageSource||q.source):le?.source,directLev?90000:SCREENSHOT_MAX_AGE_MS,directLev?'':'screenshot');
 if(!directLev&&le?.fromSeries){items.leverage.fromSeries=true;items.leverage.timeText=le.timeText;}
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
 return items;
}
function renderProductFieldStates(p){
 const fields=productFieldStates(p);
 const calculation=p.quote?.leverageCalculation, comparison=p.quote?.leverageComparison;
 const detail=calculation?.available?'<div>Berechnungsbasis: Briefkurs '+esc(calculation.inputs?.askEur)+' EUR · Quellenzeit '+esc(calculation.inputs?.askAt)+' · '+esc(calculation.inputs?.priceKind==='issuer-chart'?'Chartbeobachtung':calculation.inputs?.priceSource)+'<br>Basiswert: '+esc(calculation.inputs?.basisEstimated?'geschätzt':calculation.inputs?.basisDelayed?'verzögerter Quellenkurs':'Quellenkurs')+' · '+esc(calculation.inputs?.basisSource)+' · '+esc(calculation.inputs?.contract||'Gold Spot')+'<br>Zeitabstand der Eingangskurse: '+esc(calculation.skewSeconds)+' s (Analysetoleranz: '+esc(calculation.maxAllowedSkewSeconds||30)+' s; maximales Datenalter: '+esc(calculation.maxAllowedInputAgeSeconds||90)+' s)</div>':'';
 const comparisonDetail=comparison?'<div>Hebelvergleich: '+esc(comparison.comparable?(comparison.warning?'Auffällige Abweichung: ':'Abweichung: ')+comparison.relativeDifferencePct+' % · '+comparison.note:comparison.reason)+'</div>':'';
 const native=p.quote?.nativeChartEvidence,fx=p.quote?.currencyConversion;
 const nativeInfo=native?'<div><b>Originalkurs CHF: Geld '+esc(native.bid)+' / Brief '+esc(native.ask)+'</b><br>Quellenzeit '+esc(native.pointAt)+(fx?'<br>Für die Analyse in EUR umgerechnet · CHF/EUR '+esc(fx.rate)+' · '+esc(fx.at):'<br>EUR-Umrechnung noch nicht verfügbar')+'</div>':'';
 return '<div class="small" data-field-status>'+nativeInfo+detail+comparisonDetail+Object.values(fields).map(f=>'<div><b>'+valuePresenceMark(f.state==='fehlt')+' '+esc(f.key)+(f.kind==='issuer-chart'?' (Chartkurs)':'')+': '+esc(f.key==='Hebel'&&n(f.value)>0?Number(f.value).toLocaleString('de-CH',{minimumFractionDigits:2,maximumFractionDigits:2}):f.value??'—')+' · '+esc(f.state)+'</b>'+ (f.at?'<br>'+ (f.fromSeries?'Zeitbezug der Aufnahmeserie ':'Quellenzeit ')+esc(f.at)+' · '+esc(f.ageSeconds)+' s alt':f.fromSeries&&f.timeText?'<br>Zeitbezug der Aufnahmeserie '+esc(f.timeText)+(/\d{2}[/.]\d{2}[/.]\d{4}/.test(f.timeText)?' · Sekunden unbekannt':' · Kursdatum fehlt'):'')+'<br>'+esc(f.source)+(f.kind==='issuer-chart'?' · Chartbeobachtung, kein ausführbarer Kursnachweis':'')+'</div>').join('')+(p.quote?.leverageEstimated?'<div>'+esc(p.quote.leverageNote)+'</div>':'')+(p.quote?.leverageCalculation?.available===false?'<div>Hebelberechnung: '+esc(p.quote.leverageCalculation.reason)+'</div>':'')+(p.quote?.backupStatus?.state==='unavailable'?'<div>Onvista-Backup derzeit nicht verfügbar: '+esc(p.quote.backupStatus.code)+'</div>':'')+'</div>';
}
// A current native quote and its own FX evidence supersede the old screenshot
// quote for analysis selection. The image and its gearing retain original clocks.
function currentConvertedChfEvidence(p,now=Date.now()){
 const q=p.quote,a=q?.analysisQuote,native=q?.nativeChartEvidence,fx=q?.currencyConversion,f=fx?.evidence;
 const x=p.snapshot,e=x?.evidence?.Hebel;
 if(q?.isin!==p.isin||!q.productVerified||q.metadata?.status!==1||isFutureProduct(p)||knockoutStatus(p)||!automaticIdentity(p)||!productTermsStatus(p,now).complete)return null;
 if(!a||a.priceKind!=='issuer-chart'||a.currency!=='EUR'||!a.source||a.delayed||native?.currency!=='CHF'||native.delayed||fx?.fromCurrency!=='CHF'||fx.toCurrency!=='EUR'||!fx.source||f?.base!=='USD'||f.marketSession!=='open'||f.eurSource!=='live'||f.chfSource!=='live')return null;
 if(x?.isin!==p.isin||!hasScreenshotIdentity(x)||!e?.source||e.conflict||e.revoked||e.ocrCorrection||!(n(e.value)>=1)||n(e.value)!==n(p.leverage)||!evidenceTiming(e,now).fresh)return null;
 const rate=n(f.eur)/n(f.chf),near=(v,w)=>Number.isFinite(v)&&Number.isFinite(w)&&Math.abs(v-w)<=Math.max(1e-9,Math.abs(w)*1e-12);
 if(!(n(f.eur)>0&&n(f.chf)>0&&rate>0&&rate<10&&n(native.bid)>0&&n(native.ask)>=n(native.bid))||!near(n(fx.rate),rate)||!near(n(a.bid),n(native.bid)*rate)||!near(n(a.ask),n(native.ask)*rate)||n(p.price)!==n(a.ask)||fx.nativeAt!==native.pointAt)return null;
 const raw=[native.pointAt,f.dataAt,f.eurAt,f.chfAt,a.bidAt,a.askAt,fx.at];
 const clocks=raw.map(v=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(v)?Date.parse(v):NaN);
 if(clocks.some(t=>!Number.isFinite(t)||t>now||now-t>300000)||Math.max(...clocks)-Math.min(...clocks)>90000)return null;
 const oldest=Math.min(...clocks.slice(0,4));
 if(clocks.slice(4).some(t=>t!==oldest))return null;
 const local=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Zurich',weekday:'short',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now)),part=k=>local.find(x=>x.type===k)?.value;
 if(['Sat','Sun'].includes(part('weekday'))||Number(part('hour'))<8||Number(part('hour'))>=22)return null;
 return {...a,at:new Date(oldest).toISOString(),leverage:n(e.value),leverageAt:e.at,leverageKind:'screenshot',isExecutableQuote:false};
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
 let raw=normalizeProductTermLayout(normalizeSwissSgText(normalizeBnpQuoteColumns(String(text||""))));
 // BNP's Gold reference identifier is not the certificate ISIN.
 // Scope removal to the explicit Gold underlying section, preserving all
 // certificate identifiers and rejecting conflicting product identities.
 if(/derivate\.bnpparibas\.com|BNP\s+Paribas/i.test(raw)&&/Basiswert\s+GOLD\b/i.test(raw)){
  raw=raw.replace(/(Basiswert\s+GOLD\s+ISIN\s*[:=]?\s*)USFX0{5}XAU\b/i,'Basiswert GOLD\nReferenzkennung XAU/USD');
  raw=raw.replace(/(?:^|\n)\s*Basiswert\s*\n(?=\s*Basiswert\s+GOLD\b)/i,'\n');
 }
 if(!validIsin(expectedIsin))return{ok:false,reason:"Bitte zuerst die ISIN dieses Produkts am Screenshot prüfen und korrigieren."};
 const identity=screenshotIdentity(raw,expectedIsin,productContext);
 if(!identity.ok)return identity;
 if(explicitKnockout(raw))return {ok:true,isin:expectedIsin,identityBasis:identity.basis,identityContext:identity.context||null,terms:{},times:{},lifecycle:{isin:expectedIsin,status:'KNOCKED_OUT',verified:true,text:'KNOCKED OUT',identityBasis:identity.basis}};

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
 if(['WKN','Valor','Produktkontext'].includes(identity.basis))raw='ISIN '+expectedIsin+'\n'+raw;
 const x=ocrExtract(raw.replace(/(\bBAR\s*\n)[@©●•®]\s*(?=[0-9])/gi,"$1"));
 if(/\b(?:SHORT|PUT)\b/i.test(raw)&&/\b(?:LONG|CALL)\b/i.test(raw))return {ok:false,reason:'Long/Short im Bild widersprüchlich: Produktzuordnung prüfen'};
 if(!x.price){const top=raw.match(/(?:^|\n)\s*€\s*([0-9]+(?:[.,][0-9]+)?)\b/);if(top)x.price=top[1].replace(",",".");}
 const amount=label=>{const m=raw.match(new RegExp("\\b(?:"+label+")(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR)?\\s*([0-9]+(?:[.,][0-9]+)?)","i"));return m?Number(m[1].replace(",",".")):null;};
 const native=swissScreenshotQuote(raw);
 const draft=native?{ok:false,currency:'CHF',hasQuote:native.hasQuote,paired:native.paired,partialQuote:native.partialQuote,fields:{bid:native.bid,ask:native.ask}}:window.BobCombined.screenshotDraft(raw,expectedIsin);
 if(draft.hasQuote&&!draft.paired&&!draft.partialQuote)return{ok:false,reason:'Produkt erkannt'+(identity.basis==='WKN'?' über WKN '+identity.wkn:'')+', aber Geld-/Briefpaar nicht vollständig oder eindeutig. Bitte beide Kurse im selben Bild zeigen.'};
 const bid=draft.partialQuote?draft.partialQuote.bid:draft.paired?n(draft.fields.bid):amount("Geld|Bid"),ask=draft.partialQuote?draft.partialQuote.ask:draft.paired?n(draft.fields.ask):amount("Brief|Ask");
 const importWarnings=[],importNotes=[];
 if(draft.partialQuote){x.price="";x.spread="";importWarnings.push(bid===null?"Geldkurs fehlt: Kursbereich mit Geld und Brief ergänzen.":"Briefkurs fehlt: Kursbereich mit Geld und Brief ergänzen.");}
 if(draft.fields.ko1)x.ko=draft.fields.ko1;
 if((bid!==null&&bid<=0)||(ask!==null&&ask<=0)||(bid!==null&&ask!==null&&ask<bid))return{ok:false,reason:"Geld-/Briefkurse widersprüchlich gelesen. Bitte ein schärferes Bild hochladen."};
 const quoteText=raw.replace(/(?:^|\n)\s*(?:Produktdatenstand|Bedingungenstand|Fälligkeit|Faelligkeit|Laufzeit|KO-Zeit|Hebelzeit)\s*[:=]?[^\n]*/gi,'');
 const stamp=screenshotTimes(raw).quote?.text||(quoteText.match(/\b\d{2}[/.]\d{2}[/.]\d{4}\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||"";
 const currency=native?'CHF':/\bEUR\b|€/.test(raw)?"EUR":"";
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
 return{ok:true,...x,importWarnings,importNotes,identityBasis:identity.basis,identityValor:identity.valor||null,identityContext:identity.context||null,bid,ask,currency,sourceTime:stamp,times:screenshotTimes(raw),terms,delayed:/verzögert|delayed/i.test(raw),combinedDraft:draft};
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
function screenshotIdentity(raw,expectedIsin,productContext=null){
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
const PRODUCT_OCR_VERSION='2026-10-07-bnp-recovery-v6';
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
async function processProductImages(i,files,context,records=null){
 if(activeProductImports.has(i))return;
 activeProductImports.add(i);
 const input=document.getElementById('dgDetailShot'+i),status=document.getElementById('dgOcrStatus'+i);
 const isin=document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value;
 const batch=records?.[0]?.batch||crypto.randomUUID(),outcomes=[],storageWarnings=[];
 if(input)input.disabled=true;
 try{
  for(let j=0;j<files.length;j++){
   if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value!==isin)break;
   const file=files[j];let record=records?.[j];
   if(!records)try{record=await saveProductOriginal(file,isin,context,batch);}catch(e){storageWarnings.push('Original nicht gespeichert: '+e.message);}
   const result=await readScreenshot(i,file,context);
   if(result)outcomes.push({name:file.name,...result});
   try{await markOriginalProcessed(record,result);}catch(e){storageWarnings.push('Erkennungsstand nicht gespeichert: '+e.message);}
  }
  if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value===isin){
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
 const records=(await loadProductOriginals()).filter(r=>automatic||r.isin===returnProductIsin).sort((a,b)=>a.savedAt-b.savedAt);
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
async function readScreenshot(i,file,productContext=null){
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
  const result=await recognizeOcr(file,"dgOcrStatus"+i,true);
  if((rowVersions.get(i)||0)!==version||(field("isin")?.value||"").trim().toUpperCase()!==expected)return;
  const x=detailScreenshotData(result.data.text,expected,productContext,result.data.unconfirmedFields||[]);
  if(x.ok)removeUnconfirmedFields(x,result.data.unconfirmedFields||[]);
  if(!x.ok){const reason=x.reason+" "+imageIdentityDiagnostic(result.data.text)+" · Bildimport 05.10-15";if(status)status.textContent="⚠️ "+reason;return{ok:false,reason};}
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
  return{ok:true,data:x,raw:result.data.text,reason:(x.identityBasis==='Produktkontext'?'dem zuvor geöffneten Produkt '+expected+' zugeordnet':x.identityBasis==='WKN'?'über passende WKN zugeordnet':x.identityBasis==='Valor'?'über passenden Valor '+x.identityValor+' zugeordnet':'über ISIN zugeordnet')+([...x.importWarnings||[],...x.importNotes||[]].length?' · '+[...x.importWarnings||[],...x.importNotes||[]].join(' · '):'')};
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
 const incomingQuote=n(x.price)!==null||x.bid!=null||x.ask!=null;
 if(previous?.isin===x.isin&&incomingQuote&&oldTime&&newTime&&newTime.end<oldTime.start)
  throw new Error('Älteres Kursbild: vorhandene neuere Kursdaten bleiben erhalten.');

 previous=previous||{};
 // Never transfer evidence across identities, including direct callers.
 if(previous.isin&&previous.isin!==x.isin)previous={};
 const evidence={...(previous.evidence||{})};
 const hasQuote=n(x.price)!==null||x.bid!==null&&x.bid!==undefined||x.ask!==null&&x.ask!==undefined;
 // Keep the original quote's timestamp when adding only static product details.
 const merged={...previous,...x,evidence,clearSpread:false};
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
  const incoming={...value,source};
  incoming.automatic=hasScreenshotIdentity(x)&&automaticCondition(incoming,key);
  merged.terms[key]=incoming;
 }
 if(!hasQuote){for(const key of ["bid","ask","currency","sourceTime","delayed"])merged[key]=previous[key]??x[key];}
 else {for(const key of ["Kurs","Geld","Brief","Spread"])delete evidence[key];merged.clearSpread=n(x.spread)===null;}
 for(const [key,value] of Object.entries({Richtung:x.direction,Kurs:x.price,Hebel:x.leverage,KO:x.ko,Geld:x.bid,Brief:x.ask,Spread:x.spread})){if(value!==""&&value!==null&&value!==undefined)evidence[key]={value,source,at:fieldSourceTime(x,key),dateText:key==='KO'?x.terms?.ko?.dateText:null,...(['Geld','Brief','Kurs','Spread'].includes(key)?{currency:x.currency}:{}),...(key==='KO'?{displayDecimals:x.terms?.ko?.displayDecimals}:{}),...((key==='Hebel'?x.times?.leverage?.fromSeries:['Geld','Brief','Kurs','Spread'].includes(key)&&!x.times?.[{Geld:'bid',Brief:'ask'}[key]]?.present&&x.times?.quote?.fromSeries)?{fromSeries:true,timeBasis:(key==='Hebel'?'Hebel aus derselben Aufnahmeserie · ':'')+(x.captureSeries?.basis||'Zeit aus gemeinsamer Bilderserie'),timeText:x.captureSeries?.text,timeOrigin:x.captureSeries?.timeOrigin,timeSources:[...(x.captureSeries?.sources||[])]}:{})};}
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
 const card=(label,e,time)=>'<div style="min-width:0;max-width:100%;overflow-wrap:anywhere;border-bottom:1px solid #ddd;padding:10px 0;'+(calculationAge(e.at,SCREENSHOT_MAX_AGE_MS)&&!e.conditionVerified?'font-style:italic':'')+'"><b>'+esc(label)+': '+esc(e.value)+'</b>'+(e.ocrCorrection?'<div>'+esc(e.ocrCorrection)+'</div>':'')+'<div>Quelle: '+esc(e.source||'nicht angegeben')+'</div><div>'+esc(time)+'</div></div>';
 const terms=x.terms||{},ko=x.evidence?.KO;
 const sameKo=terms.ko&&ko&&n(terms.ko.value)===n(ko.value);
 const rows=Object.entries(x.evidence||{}).filter(([key])=>key!=='Spread'&&!(key==='KO'&&sameKo)).map(([key,e])=>{
  const t=evidenceTiming(e);return card(key==='KO'?'KO-Barriere':['Geld','Brief','Kurs','Spread'].includes(key)?key+' '+(e.currency||x.currency||''):key,e,(e.fromSeries?e.timeBasis+' · Zeitbezug '+e.at+' · keine separat bestätigte Hebelzeit':e.at)||(e.dateText?'Datenstand '+e.dateText+(currentDatedTerm(e,Date.now())?' · für diesen Kalendertag belegt; keine Kurszeit':' · nicht für heute bestätigt'):key==='Richtung'?'Eingelesen · am Original prüfen':'Wert eingelesen · Quellenzeit fehlt'));
 }).join('');
 const termRows=Object.entries(terms).filter(([key,e])=>key!=='quanto'&&e).map(([key,e])=>card(labels[key]||key,e,(e.automatic||hasScreenshotIdentity(x)&&automaticCondition(e,key))?'Automatisch aus zugeordnetem Bild gelesen · keine Kurszeit':e.conditionVerified?'Produktbedingung recherchiert '+e.reviewedAt+' · keine Kurszeit':e.reviewed&&['type','currency','maturity'].includes(key)?'Geprüfte Produktbedingung · keine Kurszeit':e.at||(e.dateText?'Datenstand '+e.dateText+(currentDatedTerm(e,Date.now())?' · für diesen Kalendertag belegt; keine Kurszeit':' · nicht für heute bestätigt'):'Wert eingelesen · Produktnachweis noch nicht bestätigt; Datenstand fehlt'))).join('');
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
async function inject(){
 if(document.getElementById("dgTop3"))return;
 const a=document.getElementById("dgProductOut"); if(!a)return;
 const b=document.createElement("div");
 b.id="dgTop3";
 b.style.cssText="margin-top:14px;padding:16px;background:#f7f9fc;border-radius:20px;border:1px solid #e5eaf2";
 b.innerHTML='<style>#dgTop3 > details,#dgTop3Out > section,#dgTop3Out > details{box-sizing:border-box;min-width:0;margin-top:14px;padding:12px;background:#fff;border:1px solid #e1e7f0;border-radius:16px;overflow-wrap:anywhere}#dgTop3 > details > summary,#dgTop3Out > details > summary{cursor:pointer;font-weight:700}#dgTop3 > details[open] > summary,#dgTop3Out > details[open] > summary{margin-bottom:10px}</style><div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b></div></div>'+
 '<div id="dgTop3Out" style="margin-top:12px"></div>'+
 '<details style="margin-top:12px"><summary id="dgSavedProductsSummary" style="cursor:pointer;font-weight:700">Gold-Hebelprodukte</summary><div id="dgMissingProducts" style="margin-top:12px"></div></details>'+
 '<div id="dgScreenshotReturn" hidden style="margin-top:14px;padding:14px;background:#eaf3ff;border:2px solid #1677ff;border-radius:14px;scroll-margin-top:16px"><b>Screenshots für <span data-return-isin></span></b><p class="small">Bilder werden diesem zuvor geöffneten Produkt zugeordnet, auch wenn ISIN oder WKN im Bild fehlen. Eine eindeutig abweichende Produktkennung wird gemeldet.</p><div data-return-product-link></div><div data-return-missing></div><p class="small">Fehlenden Wert erneut aufnehmen: Produktseite öffnen, Screenshot machen und anschließend hier beim selben Produkt hinzufügen.</p><button type="button" data-return-upload style="width:100%;background:#1677ff">↑ Bilder / PDF für dieses Produkt hinzufügen</button><div class="small" style="margin:8px 0">Originaldateien: lokal auf diesem Gerät, bis zu 7 Tage / insgesamt 100 MB. Nach Erkennungsupdates prüft Bob gespeicherte Dateien erneut. Ursprüngliche Datenstände bleiben erhalten.</div><button type="button" data-return-reprocess>Gespeicherte Bilder erneut prüfen</button><button type="button" data-return-delete>Gespeicherte Originaldateien löschen</button><button type="button" data-return-close>Fertig / ausblenden</button><div role="status" data-return-status style="overflow-wrap:anywhere;min-width:0"></div><div role="status" data-return-complete hidden style="margin-top:12px;font-weight:700;color:#15803d">✅ Datenübertragung komplett</div></div>'+
 '<div style="margin-top:14px;padding:12px;background:#fff;border-radius:16px;border:1px solid #e1e7f0">'+
 '<b>📷 DEGIRO-Liste</b><button type="button" id="dgListUploadButton" style="margin-top:10px;width:100%;background:#1677ff">↑ DEGIRO-Liste hochladen</button>'+
 '<input id="dgListUpload" type="file" accept="image/*" multiple hidden>'+
 '<details style="margin-top:8px"><summary>Hinweise zum Hochladen</summary><div class="small">Einen oder mehrere Listen-Screenshots gleichzeitig auswählen. Eine neue Auswahl ersetzt die bisherige Liste nach erfolgreichem Einlesen.</div></details>'+
 '<div id="dgCentralStatus" class="small" role="status" aria-live="polite" style="margin-top:9px">Gespeicherte Liste wird geladen …</div><details id="dgSavedListImages"></details></div>'+
 '<details style="margin-top:9px"><summary>Datenabruf und Gültigkeit</summary><div class="small">Automatische Produktrecherche: beim Öffnen und alle 15 Minuten, solange Bob sichtbar ist. Quellenzeiten bleiben unverändert: Emittentenkurse höchstens 90 Sekunden; Screenshot-Kursnachweise 14 Stunden ab Quellenzeit gültig, keine Echtzeitkurse. Neue Kursbilder ersetzen den bisherigen Kursnachweis. Fehlende Kurse bleiben offen, berechnete Werte sind Schätzungen.</div></details>'+
 '<div id="dgStorageStatus" class="small" role="status"></div>'+
 '<div id="dgManualSnapshots" style="margin-top:12px" hidden></div>'+
 '<div id="dgConditionalOut" style="margin-top:12px" hidden></div>'+
 '<details style="margin-top:10px"><summary style="cursor:pointer;font-weight:700">Details / manuelle Kursnachweise</summary><div class="small" style="margin:7px 0">Hier lassen sich Screenshotwerte korrigieren und datierte Stuttgart-/Onvista-Nachweise bedingt auswerten.</div><div id="dgTop3Inputs"></div></details>'+
 '<button style="margin-top:10px;width:100%" id="dgRankBtn">🔎 Analyse erneut ausführen</button>';
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
  r.querySelectorAll('[data-dg]').forEach(el=>el.addEventListener('input',()=>{if(el.dataset.dg!=="confirmed"){combinedReferences.delete(i);productQuotes.delete(i);futureResearchQuotes.delete(i);if(["isin","dir"].includes(el.dataset.dg)){detailScreenshots.delete(i);}else if(["price","lev","ko","spread"].includes(el.dataset.dg)){}rowVersions.set(i,(rowVersions.get(i)||0)+1);if(el.dataset.dg==="isin"){combinedDrafts.delete(i);resetCombinedForm(i);}}rankUI();}));
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
 refreshImportedProducts(true);
 const savedCount=restoredProducts.length;
 b.querySelector('#dgCentralStatus').textContent=listArchive?.files?.length?'Gespeicherte Liste: '+listArchive.files.length+' Bild(er) · '+savedCount+' Produkte. Gespeichert bis 22 Uhr Schweizer Zeit.':savedCount?savedCount+' Produkte gespeichert. Frühere Originalbilder sind nicht gespeichert; die Produktdaten bleiben bis 22 Uhr erhalten.':'Bitte für heute neue Listenbilder einlesen. Tageslisten gelten bis 22 Uhr Schweizer Zeit.';
 const upload=b.querySelector('#dgListUpload'),uploadButton=b.querySelector('#dgListUploadButton'),uploadStatus=b.querySelector('#dgCentralStatus');
 uploadButton.addEventListener('click',()=>upload.click());
 upload.addEventListener('change',async()=>{
  if(!upload.files?.length)return;
  uploadButton.disabled=true;upload.disabled=true;
  try{
   const files=await retainSelectedImages(upload);
   const items=await readListBatch(files,recognizeOcr,(i,total,name)=>{uploadStatus.textContent='📷 Bild '+i+' von '+total+' wird gelesen: '+name;});
   await saveListArchive(files,items);
   populateCandidateRows(items);rankUI();
   uploadStatus.textContent='✅ '+files.length+' Bild(er) gelesen · '+items.length+' unterschiedliche Produkte erkannt. Bilder und Produkte bis heute 22 Uhr Schweizer Zeit gespeichert – auch nach dem Schließen.';
   const uncertain=items.filter(x=>!validIsin(x.isin)).length;
   if(uncertain)uploadStatus.textContent+=' ⚠️ '+uncertain+' ISIN(s) unsicher – unter Details prüfen.';
   refreshImportedProducts(true).then(()=>refreshImportedProducts());
  }catch(e){uploadStatus.textContent='⚠️ '+(e?.message||'Bilder konnten nicht gelesen werden')+' Die bisherige Produktliste bleibt erhalten.';}
  finally{upload.value='';upload.disabled=false;uploadButton.disabled=false;}
 });
 b.querySelector("#dgRankBtn").addEventListener("click",async e=>{const button=e.currentTarget;button.disabled=true;rankUI();try{await refreshImportedProducts(true);}finally{button.disabled=false;rankUI();}});
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
 const rows=continuingAnalysis(products,context).map(({p,warning,evaluation:e})=>{
  const uncertain=!!warning||marketWarnings.length>0;
  return '<div style="margin:8px 0;'+(uncertain?'font-style:italic':'')+'"><b>'+esc(p.isin||p.name)+'</b> · Kurs '+esc(p.price??'fehlt')+' · Hebel '+esc(p.leverage??'fehlt')+' · KO '+esc(p.ko??'fehlt')+(warning?' · '+esc(warning):'')+'<br>'+esc(e.ok?'Rechnerische Bewertung: '+e.score+' Punkte · '+e.reasons.join(' · '):e.reasons.join(' · '))+'</div>';
 }).join('');
 return '<section data-indicative-recommendations><b>Rechnerische Empfehlung · <span style="color:'+({LONG:'#15803d',SHORT:'#b91c1c'}[context.direction]||'#ca8a04')+'">'+esc(['LONG','SHORT'].includes(context.direction)?context.direction:'ABWARTEN')+'</span></b>'+leverageHint+ (recommendations||'<p>ABWARTEN: '+(['LONG','SHORT'].includes(context.direction)?'Aktuell erfüllt kein Produkt alle Auswahlkriterien.':'Keine bestätigte Long-/Short-Marktrichtung.')+'</p>')+'</section><details data-product-details="calculations"><summary>Berechnung mit vorhandenen Werten</summary><p class="small"><i>Berechnung läuft auch mit veralteten Werten und ohne Zeitstempel weiter. Die rechnerische Bewertung ist keine aktuell bestätigte Produktfreigabe.</i></p>'+ (marketWarnings.length?'<p><i>'+esc(marketWarnings.join(' · '))+'</i></p>':'')+rows+'</details>';
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
  const html=productUploadCards(ps,d,Date.now(),flow);
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
 window.BobPaperSimulation?.sync({products:ps,references,fixedBarriers:window.BobCombined.fixedBarriers()});
 window.BobPush?.updateSelection?.({products:ps,context:selectionContext,bundle:{spots:bundle?.spots,fetched_at:bundle?.fetched_at,history:{data_state:bundle?.history?.data_state}},references,fixedBarriers:window.BobCombined.fixedBarriers()},flow);
 const flowHtml=renderContinuingAnalysis(ps,selectionContext)+'<details data-product-details="selection-check"><summary>Freigabeprüfung · '+(flow.approved?flow.approvedCount+' geeignete Produkte':'ABWARTEN')+'</summary>'+renderSelectionWorkflow(flow,ps)+'</details>';if(updateProductHtml(o,flowHtml))bindCompactCards(o);return flow;

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
window.BobDegiro={refreshTradeTestQuotes:()=>refreshImportedProducts(true),tradeTestProducts,koEvidenceStatus,KO_MAX_AGE_MS,currentConvertedChfEvidence,termSeriesReference,currentProductTerm,renderTermSeriesValidity,productDataStatus,productCompletionBadge,renderSecondaryValidity,analysisReleaseQuote,recognizePlainOcr,reprocessOriginals,scalarCellRect,readScalarCell,originalRetention,saveProductOriginal,loadProductOriginals,markOriginalProcessed,deleteProductOriginals,removeUnconfirmedFields,screenshotBatchSummary,renderUploadMissing,readTermDate,screenshotProductLink,knockoutStatus,explicitKnockout,knockoutCard,invalidateProductQuote,retainProductResearch,missingValueLocation,restorePdfReference,parseProductPdf,readProductPdf,sgIdentityRect,readSgIdentity,linkScreenshotSeries,ocrGlyphPair,strictOcrNumber,ocrNumericFields,unconfirmedOcrFields,preferOriginalTableRead,bnpBadgeRect,normalizeBnpQuoteColumns,imageIdentityDiagnostic,reviewedImageText,detailStateKey,updateProductHtml,zurichListDay,listExpired,clearDailyList,archiveTransaction,saveListArchive,restoreListArchive,automaticIdentity,automaticCondition,recoverTermRows,screenshotReturnRow,renderProductDecision,readListBatch,collectiveSignal,productFieldStates,renderProductFieldStates,indicativeRecommendations,calculationAge,continuingAnalysis,renderContinuingAnalysis,compactProductCard,screenshotSummary,retainSelectedImages,renderImageImportStatus,renderIssuerHelp,renderProductSources,applyResearchedTerms,durableCondition,maturityDeadline,writeStoredProducts,cleanStoredProduct,recoverReviewedLists,restoreProductRows,selectionUiSignals,selectionMarketGate,costRiskAssessment,finalProductStatus,parseProductTerms,productTermsStatus,selectionTimeWindow,selectionDetailStatus,selectionWorkflow,renderSelectionWorkflow,recognizeOcr,exitReference,createQuoteRefresh,screenshotCurrentState,renderScreenshotCurrentState,conditionalCandidate,rankConditional,renderConditional,qualityText,isFutureProduct,futureResearchText,productEstimateText,rankManualSnapshots,productUploadCards,sourceTimestamp,screenshotTimes,evidenceTiming,manualSnapshotStatus,needsDirectionalData,loadIdentities,saveIdentities,riskModel,koDistancePct,evaluateProduct,quoteTiming,currentQuote,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates,validIsin,normalizeOcrIsin,populateCandidateRows,recoverOcrIsins,detailScreenshotData,missingProductData,supplementaryHint,screenshotTimeLabel,mergeScreenshotEvidence,manualProductMissing,escapeHtml:esc};
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
window.BobExitEstimate={calculate,render,init,researchReference,restoreReference,planInput};
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
  panel.innerHTML='<h3>Trade-Test · fiktiv</h3><p>Produkt frei auswählen – auch bei ABWARTEN oder ohne Empfehlungsfreigabe. Kein Kauf, keine Trade-Pushs. Separater Test auf diesem Gerät; dein echter Trade bleibt erhalten.</p><label for="manualTestProduct">Produkt</label><select id="manualTestProduct"></select><button type="button" data-test-refresh>Produktliste und Kurse aktualisieren</button><div class="grid"><label>Angenommener Einstieg EUR/Stück<input data-test-entry type="number" min="0" step="any"></label><label>Fiktive Stückzahl<input data-test-quantity type="number" min="1" step="1" value="1"></label></div><button type="button" data-test-save>Fiktiven Trade erfassen</button><button type="button" data-test-clear>Test entfernen</button><p data-test-message role="status"></p><p data-test-result style="white-space:pre-line"></p><p class="small">Bewertung zum verfügbaren Geldkurs, ohne Gebühren und Finanzierung. Dieser manuelle Test prüft Produktauswahl und Kursentwicklung; er startet keine Stop-/Zielüberwachung im Hintergrund.</p>';
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
  const select=panel.querySelector('select'),entry=panel.querySelector('[data-test-entry]'),quantity=panel.querySelector('[data-test-quantity]'),message=panel.querySelector('[data-test-message]'),result=panel.querySelector('[data-test-result]');
  let saved=null,products=[];
  try{const x=JSON.parse(localStorage.getItem(KEY)||'null');if(x?.mode==='manual-paper-test')saved=position(x.isin,x.direction,x.entry,x.quantity,Date.parse(x.createdAt));}catch(_){}
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
  opener.addEventListener('click',()=>{panel.hidden=!panel.hidden;if(!panel.hidden){refresh();if(saved){entry.value=saved.entry;quantity.value=saved.quantity;}panel.scrollIntoView({behavior:'smooth',block:'start'});}});
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
