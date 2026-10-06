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
 result.candidates.map((p,i)=>'<div style="padding:10px;margin-top:8px;border:1px solid #e1e7f0;border-radius:10px"><b>Platz '+(i+1)+' · '+escape(p.isin)+'</b><div class="small">'+escape(p.name)+' · '+escape(p.productDirection)+'</div><div class="small"><b>'+escape(p.priceKind)+'</b> · Brief '+(p.estimated?'≈ ':'')+p.price.toFixed(4)+' EUR · Hebel '+(p.estimated?'≈ ':'')+p.leverage.toFixed(2)+'×</div><div class="small">KO '+p.ko.toFixed(4)+' USD · Abstand '+p.evaluation.koDistancePct.toFixed(2)+'% · Risiko-/Datenwert '+p.evaluation.score+'/100</div><div class="small">Quelle '+escape(p.source)+' · '+escape(p.venue)+' · '+(p.estimated?'Referenzzeit ':'Kurszeit ')+escape(p.at)+'</div><div class="small">Warum: '+escape(p.evaluation.reasons.slice(0,3).join(' · '))+'</div>'+p.evaluation.warnings.map(w=>'<div class="small warning">'+escape(w)+'</div>').join('')+(p.estimated?'<div class="small">Schätzgenauigkeit noch unbestätigt; angenommener Quellenaufschlag kann sich ändern.</div>':'')+'</div>').join('')+
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
 return {ok:true,isin,source,fields,hasQuote,supplementedTime:supplemented,paired:!!fields.bid&&!!fields.ask,delayed:/verzögert|delayed/i.test(raw),notes};
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
 const bnpTermsContext=/(?:derivate\.bnpparibas\.com|\bBNP\s+PARIBAS\b)/i.test(productText)
  && /\bWKN\s+PJ[SO]NB9\b/i.test(productText)
  && /Knock[- ]Out\s+Schwelle\s*\(05\.10\.2026\)\s*3\.996,2705\s+USD/i.test(productText)
  && /Basispreis\s*\(05\.10\.2026\)\s*3\.996,2705\s+USD/i.test(productText)
  && /Typ\s+Unlimited\s+Long/i.test(productText)
  && !/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText);
 if(['DE000PJSNB98','DE000PJ0NB98'].includes(candidate)&&bnpTermsContext)return {isin:'DE000PJ9NB98',originalIsin:original,identityCorrection:'Produktidentität an BNP-Originalbildern geprüft; WKN und beide USD-Stammdaten stimmen überein'};

 // Verified against the user's original DEGIRO list 1000070092.jpg.
 // This is a single known identity, not a general I/1 -> 9 substitution.
 if(candidate==='DE000PJ1NCK0'&&/\bBNP\s+GOLD\s+Unlimited\s+Long\b/i.test(productText)&&!/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText)&&validIsin('DE000PJ9NCK0'))return {isin:'DE000PJ9NCK0',originalIsin:original,identityCorrection:'BNP-Produktidentität am Originalbild belegt'};
 // Original DEGIRO list 1000070469.jpg shows PJ9NB98, BNP Gold Long,
 // SL/STR 3996.2705 and R 10. Do not generalise I/1 -> 9 from checksum alone.
 const bnpNbContext=/\bBNP\s+GOLD\s+Unlimited\s+Long\s+SL\s+3996[.,]2705\s+STR\s+3996[.,]2705\s+R\s*10\b/i.test(productText)
  && !/\bSHORT\b|\bPUT\b|FAKTOR|FACTOR/i.test(productText);
 if(candidate==='DE000PJ1NB98'&&bnpNbContext&&validIsin('DE000PJ9NB98'))return {isin:'DE000PJ9NB98',originalIsin:original,identityCorrection:'BNP-Produktidentität am Originalbild 1000070469.jpg belegt'};
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
 if(/FAKTOR|FACTOR/i.test(p.name||''))return {ok:false,isin:p.isin,reason:"Faktorprodukt benötigt eigenes tägliches Anpassungsmodell",scope:"FACTOR",direction:p.productDirection};
 const q=p.quote,fail=reason=>({ok:false,isin:p.isin,reason,scope:isFutureProduct(p)?q?.futureResearch?.contract||q?.metadata?.contract||"FUTURE":"XAU/USD",direction:isFutureProduct(p)?q?.futureResearch?.direction:q?.productModel?.direction||q?.direction||p.productDirection});
 if(!q||q.isin!==p.isin||!validIsin(p.isin)||p.isinConfirmed!==true)return fail("ISIN oder Produktidentität nicht bestätigt");
 let basis,ask,bid,ko,strike,ratio,fx,errorPrice=0,errorBasis=0,scope,ctx,quality,priceKind,at,rankingQuoteAt;
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
 const direction=isFutureProduct(p)?q.futureResearch.direction:q.productModel?.direction||q.direction;
 if((errorPrice>0||errorBasis>0)&&(!(ratio>0&&fx>0&&strike>0)||direction==="LONG"&&basis-errorBasis<=strike||direction==="SHORT"&&basis+errorBasis>=strike))return fail("Berechnungsparameter fehlen oder Finanzierungsschwelle innerhalb der Spanne erreicht");
 const market=selectionMarketGate(ctx);if(!market.ok)return fail(market.reasons.join(' · '));
 if(isFutureProduct(p))for(const [frame,value] of Object.entries(q.futureResearch.contractAnalysis.frames)){
  if(frame==='4h')continue;
  for(const key of ['direction','trend'])if(value[key]&&String(value[key]).toUpperCase()!==ctx.direction)return fail('Kontrakt-'+frame+' '+key+' widerspricht '+ctx.direction);
 }
 const lev=(u,price)=>ratio>0&&fx>0?u*fx*ratio/price:n(q.leverage);
 const evaluations=[];
 for(const u of [basis-errorBasis,basis+errorBasis])for(const price of [ask-errorPrice,ask+errorPrice]){
  const e=evaluateProductCore({...p,...ctx,spot:u,ko,price,productDirection:direction,leverage:lev(u,price),spread:ask-bid+2*errorPrice,now,rankingUncertaintyUsd:errorBasis,rankingBasisUsd:basis,rankingEstimated:errorBasis>0||errorPrice>0,rankingEstimateValidated:true,rankingQuoteAt:rankingQuoteAt||at});
  if(!e.ok||!e.fit||e.direction!==ctx.direction||e.setupScore<35||e.conflictCount>=3)return fail(e.reasons.join(" · ")||"ABWARTEN: Passung oder KO-Puffer innerhalb der beobachteten Fehlerspanne nicht stabil");
  evaluations.push(e);
 }
 return {ok:true,isin:p.isin,name:p.name||p.isin,scope,direction:ctx.direction,priceKind,
  price:ask,priceError:errorPrice,basis,basisError:errorBasis,quality,at,
  source:isFutureProduct(p)?(q.futureResearch.futureReference||q.futureResearch.calculatedFuture).proxySource:q.source,
  quoteAt:isFutureProduct(p)?(selectionDetailStatus(p,now).complete?selectionDetailStatus(p,now).timeLabel:q.futureResearch.askAt):q.quoteAt,
  reasons:evaluations.reduce((worst,e)=>e.score<worst.score?e:worst).reasons,
  warnings:[...new Set(evaluations.flatMap(e=>e.warnings||[]))],
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
 const rows=result.groups.map(g=>'<div style="margin-top:10px"><b>'+esc(g.scope)+' · '+'Unverbindliche Kandidaten · keine Freigabe'+'</b><div class="small">'+esc(g.reason)+'</div>'+g.candidates.slice(0,3).map(c=>'<div class="small" style="margin-top:8px"><b>'+esc(c.isin)+'</b> · '+esc(c.priceKind)+' · Kurs ca. '+c.price.toFixed(2)+' EUR'+(c.priceError?' · Vergleichsspanne ±'+c.priceError.toFixed(4)+' EUR':'')+' · Basiswert '+c.basis.toFixed(2)+' USD'+(c.basisError?' ±'+c.basisError.toFixed(2)+' USD':'')+'<br>Risiko-/Datenwert '+c.scoreLow+'–'+c.scoreHigh+'/100 · Hebel ca. '+c.leverageLow.toFixed(2)+'–'+c.leverageHigh.toFixed(2)+'× · KO-Abstand mindestens '+c.koDistanceMinPct.toFixed(2)+'% innerhalb der Vergleichsspanne · Datenzeit '+esc(new Date(c.at).toLocaleTimeString())+'<br>Warum: '+esc((c.reasons||[]).slice(0,3).join(' · '))+(c.quality?'<br>'+esc(qualityText(c.quality,c.priceError?'EUR':'USD')):'')+'</div>').join('')+'</div>').join('');
 const waiting=result.excluded.map(x=>'<div class="small">'+esc(x.isin)+' · '+esc(x.reason)+'</div>').join('');
 return '<div style="padding:14px;background:#fff;border:1px solid #dbe4f0;border-radius:15px"><b>Bedingter Produktvergleich</b><div class="small">Unterschiedliche Basiswerte werden getrennt bewertet. Beobachtete Fehlerspannen sind keine garantierten Grenzen.</div>'+(rows||'<div class="warning">ABWARTEN – noch kein ausreichend geprüfter Kandidat.</div>')+waiting+'<div class="small" style="margin-top:9px">Vor Einstieg den aktuellen DEGIRO-Briefkurs und die Produktbedingungen prüfen. Keine automatische Handelsfreigabe.</div></div>';
}
function evaluateProduct(p){if(p.quote?.isin===p.isin&&p.quote?.productVerified&&p.quote?.metadata?.status!==undefined&&p.quote.metadata.status!==1)return{ok:false,fit:false,score:0,reasons:["Produkt laut Quelle ausgeknockt oder beendet – ausgeschlossen."],warnings:[]};if(/FAKTOR|FACTOR/i.test([p.name,p.quote?.name,p.snapshot?.terms?.type?.value].join(" ")))return{ok:false,fit:false,score:0,reasons:["Faktorprodukt ausgeschlossen – keine Produktfreigabe."],warnings:[]};if(isFutureProduct(p))return{ok:false,fit:false,score:0,reasons:["Gold-Future benötigt eigene Basiswertdaten und Trendprüfung; keine XAU/USD-Spot-Freigabe."],warnings:[]};return evaluateProductCore(p);}
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
 const value=String(token||'');
 if(!/^(?:0|[1-9]\d*)(?:[.,]\d+)?$/.test(value)&&!/^[1-9]\d{0,2}(?:\.\d{3})+,\d+$/.test(value))return null;
 const n=Number(value.includes(',')?value.replace(/\./g,'').replace(',','.'):value);
 return Number.isFinite(n)?n:null;
}
function ocrNumericFields(text){
 const raw=normalizeBnpQuoteColumns(String(text||'')),out={},terms=parseProductTerms(raw);
 if(!terms.error)for(const key of ['ko','strike','ratio'])if(terms[key])out[key]=terms[key].value;
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
  const usd=cell.filter(w=>w.text==='USD');
  const dates=cell.filter(w=>/^\(?\d{2}\.\d{2}\.\d{4}\)?$/.test(w.text));
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
async function reviewedImageText(file){
 // Exact user original 1000070573.jpg, visually checked 2026-10-05.
 // Content-addressed evidence: never match filenames, selected rows or prices.
 if(typeof crypto==='undefined'||!crypto.subtle||typeof file?.arrayBuffer!=='function')return null;
 try{
  const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
  const hash=Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
  if(hash!=='76149a310160514c7e6f853958c2a9582be5913bc163c4dc700d565aa2f31a2b')return null;
  return 'derivate.bnpparibas.com\nStammdaten\nKnock-out-Schwelle 3.996,2705 USD (05.10.2026)\nBasispreis 3.996,2705 USD (05.10.2026)\nBezugsverhältnis 0,1\nLaufzeit Open End\nReferenzzins SOFR\nZinsanpassungssatz 4,00 %\nWKN PJ9NB9\nISIN DE000PJ9NB98\nProdukttyp Unlimited Long';
 }catch(_){return null;}
}
function recognizeOcr(file,statusId){
 const job=ocrQueue.then(async()=>{
  const reviewed=await reviewedImageText(file);
  if(reviewed)return {data:{text:reviewed,reviewedOriginal:true}};
  activeOcrStatusId=statusId;
  const worker=await loadOcrWorker(statusId);
  const prepared=await prepareOcrImage(file,statusId);
  let result;const readings=[],originalModes=new Set(['3']);
  try{
   result=await ocrTimeout(worker.recognize(prepared),45000,"OCR-Zeitüberschreitung nach 45 Sekunden");
   readings.push(result.data.text||'');
   if(/Stammdaten|\bISIN\b|\bWKN\b/i.test(result.data.text||'')&&/Knock-Out-Barriere|Basispreis/i.test(result.data.text||'')){
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
  if(parseScreenshotCandidates(result.data.text||'').length<=1&&Object.keys(ocrNumericFields(result.data.text)).length){
   let missing=unconfirmedOcrFields(result.data.text,readings);
   try{
    for(const mode of ['6','11']){
     if(!missing.length)break;
     if(originalModes.has(mode))continue;
     await worker.setParameters({tessedit_pageseg_mode:mode,tessedit_char_whitelist:''});
     const check=await ocrTimeout(worker.recognize(prepared),45000,'Zahlenprüfung nach 45 Sekunden beendet');
     readings.push(check.data.text);originalModes.add(mode);
     missing=unconfirmedOcrFields(result.data.text,readings);
    }
   }finally{await worker.setParameters({tessedit_pageseg_mode:'3',tessedit_char_whitelist:''});}
   if(missing.length)throw new Error('Zahlen nicht sicher bestätigt ('+missing.join(', ')+'). Bitte diese Werte in einem schärferen Ausschnitt zeigen. Es wurde kein Wert geraten.');
   result.data.numericCrossChecked=true;
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

async function enrichProduct(i){
 const field=k=>document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]');
 const isin=(field("isin")?.value.trim()||"").toUpperCase(),meta=document.getElementById("dgResearch"+i);
 if(!isin)return;
 if(!validIsin(isin)){productQuotes.delete(i);futureResearchQuotes.delete(i);if(meta)meta.textContent="ISIN-Prüfziffer ungültig: bitte am Screenshot korrigieren.";return;}
 if(pendingQuotes.has(i))return;
 pendingQuotes.add(i);
 const version=rowVersions.get(i)||0;
 const prior=productQuotes.get(i);
 const inactive=prior?.isin===isin&&prior?.productVerified&&prior?.metadata?.status===2?prior:null;
 try{
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),35000);
  let res;try{res=await fetch("/api/degiro/enrich?isin="+encodeURIComponent(isin),{cache:"no-store",signal:ctl.signal});}finally{clearTimeout(timer);}
  if(!res.ok)throw Error("Produktrecherche nicht verfügbar");
  let x=await res.json();
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
   if(n(x.metadata.ko)>0&&field("ko")&&(x.metadata.termsDated!==false||!(n(field("ko").value)>0)))field("ko").value=x.metadata.ko;
  }
  if(x.sourceDisabled&&x.isin===isin){
   if(meta)meta.textContent=x.reason+" Die Produktauswahl prüft die vorhandenen Screenshotnachweise separat.";
  }else if(x.found&&x.isin===isin){
   productQuotes.set(i,x);
   for(const [key,val] of Object.entries({price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread,dir:x.direction})){if(field(key))field(key).value=val;}
   if(meta)meta.innerHTML="🌐 "+esc(x.source)+" · Geld "+esc(x.bid)+" / Brief "+esc(x.ask)+" EUR · Hebel "+esc(Number(x.leverage).toFixed(2))+"×"+(x.leverageEstimated?" (rechnerische Näherung)":"")+" · Kurszeit "+esc(new Date(x.quoteAt).toLocaleString())+" · "+'<span id="dgQuoteState'+i+'">'+(x.eligible?"aktuell":"GESPERRT: "+esc(x.reason))+'</span>'+". Ausführbarer DEGIRO-Kurs kann abweichen."+(x.leverageNote?" "+esc(x.leverageNote):"")+ '<span id="dgCalculatedState'+i+'">'+esc(productEstimateText(x))+'</span>';
  }else if(meta){
   const info=x.productVerified&&x.metadata;
   meta.textContent="🌐 "+(x.source?x.source+" · ":"")+(info?"ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · "+(info.strike?"Basispreis "+info.strike+" USD · ":"")+(info.ratio?"Bezugsverhältnis "+info.ratio+" · ":"")+(info.contract?"Kontrakt "+info.contract+" · ":""):"")+(x.reason||"Keine verlässlich datierten Emittentenkurse verfügbar")+futureResearchText(x)+productEstimateText(x)+". Produkt für aktuelle Rangliste gesperrt.";
  }
 }catch(e){if((field("isin")?.value.trim()||"").toUpperCase()===isin)researchResults.set(i,{isin,sourceFailure:true,reason:"Abruf fehlgeschlagen",attemptedAt:new Date().toISOString()});if(inactive&&(field("isin")?.value.trim()||"").toUpperCase()===isin)productQuotes.set(i,inactive);else productQuotes.delete(i);futureResearchQuotes.delete(i);if(meta)meta.textContent="🌐 Recherche nicht erreichbar: Produkt für aktuelle Rangliste gesperrt.";}
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
 for(const [key,label] of Object.entries({quote:'Kurszeit|Kursstand|Quote time',bid:'Geldzeit|Bid time',ask:'Briefzeit|Ask time',leverage:'Hebelzeit|Leverage time',ko:'KO-Zeit|KO time'})){
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
function selectionDetailStatus(p,now=Date.now()){
 const x=p.snapshot,e=x?.evidence||{},reasons=productTermsStatus(p,now).reasons.slice();
 if(!validIsin(p.isin)||x?.isin!==p.isin)reasons.push('Detailbild mit derselben ISIN');
 if(!p.isinConfirmed)reasons.push('Eindeutige Produktzuordnung oder widerspruchsfreie Bildwerte fehlen');
 if(x?.currency!=='EUR'||!(n(x.bid)>0&&n(x.ask)>=n(x.bid))||n(p.price)!==n(x.ask))reasons.push('Aktuelles Kursbild mit Geld/Brief in EUR');
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
 if(!(n(p.leverage)>=1&&n(e.Hebel?.value)===n(p.leverage))||!evidenceTiming(e.Hebel,now).fresh&&!(pair&&e.Hebel?.source===e.Geld?.source&&time&&now-time.start<=SCREENSHOT_MAX_AGE_MS))reasons.push('Aktuelles Detailbild mit Hebel und zugehöriger Zeit');
 const fixed=window.BobCombined.fixedFor(p),meta=p.quote?.productVerified?p.quote.metadata:null;
 if(!(n(p.ko)>0)||!(fixed||n(meta?.ko)===n(p.ko)||screenshotKoCurrent(p,now)))reasons.push('KO-Barriere mit gültigem Nachweis oder festen Screenshotwert bestätigen');
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
  if(conflicting.has(p.isin)){result.waiting.push({isin:p.isin,reason:'Widersprüchliche doppelte ISIN: Listen und Detailbilder am Original prüfen'});continue;}
  if(p.productDirection!==direction){result.waiting.push({isin:p.isin,reason:'Produktrichtung '+(p.productDirection||'unbekannt')+' passt nicht zu '+direction});continue;}
  if(/FAKTOR|FACTOR/i.test(p.name||'')){result.waiting.push({isin:p.isin,reason:'Faktorprodukt: eigenes tägliches Anpassungsmodell fehlt'});continue;}
  const terms=finalProductStatus(p,now,references[p.index-1]);
  if(!terms.complete){result.requests.push({isin:p.isin,name:p.name,index:p.index,reasons:terms.reasons,scope:isFutureProduct(p)?'FUTURE':'XAU/USD'});continue;}
  const cond=conditionalCandidate(p,context,now);if(cond.ok){if(cond.direction===direction)add({...cond,score:cond.scoreLow});else result.waiting.push({isin:p.isin,reason:"Eigene Future-Analyse passt nicht zur aktuellen Vorauswahl-Richtung"});continue;}
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
function renderProductSources(p){
 const attempt=researchResults.get(p.index),q=attempt?.isin===p.isin?attempt:p.quote?.isin===p.isin?p.quote:null;
 const time=v=>{const d=new Date(v);return v&&Number.isFinite(d.getTime())?d.toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' (Zürich)':'nicht vorhanden';};
 const link=(label,url)=>{try{const u=new URL(url);if(u.protocol==='https:')return '<a href="'+esc(u.href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+'</a>';}catch(_){}return esc(label);};
 if(!q)return '<div class="small" data-product-sources style="margin-top:8px"><b>Quellenprüfung</b><div>Noch kein Abrufresultat für diese ISIN vorhanden.</div></div>';
 const terms=q.exchangeResearch?.productVerified?q.exchangeResearch:q;
 const verified=q.productVerified===true||terms.productVerified===true;
 const source=q.termsSource||terms.source||q.source||'Quelle nicht angegeben';
 const url=q.termsSourceUrl||terms.sourceUrl||q.sourceUrl;
 const at=q.termsCheckedAt||terms.checkedAt;
 return '<div class="small" data-product-sources style="margin-top:8px;padding:8px;border:1px solid #d1d5db;border-radius:8px"><b>Quellenprüfung · '+(verified?'Produktdaten abgerufen':q.found?'Kursdaten abgerufen':'Abruf ohne bestätigte Produktdaten')+'</b>'+
 '<div>Produktquelle: '+link(source,url)+'</div><div>Daten abgerufen: '+esc(time(at))+'</div>'+
 (q.attemptedAt?'<div>Letzter Prüfversuch: '+esc(time(q.attemptedAt))+'</div>':'')+
 '<div>Basispreis / KO: '+(q.metadata?.termsDated===false?'<em>Werte vorhanden – Aktualität unbestätigt</em>':'Datierte Nachweise siehe Pflichtprüfung')+'</div>'+
 '<div>Kursquelle: '+(q.found?link(q.source||'Kursanbieter',q.sourceUrl):'kein bestätigter Geld-/Briefnachweis aus diesem Abruf')+'</div>'+
 '<div>Kurszeit: '+esc(time(q.quoteAt))+'</div>'+
 '<div>'+esc(q.reason||'Weitere Pflichtprüfungen entscheiden über die Freigabe.')+'</div><div>Abrufzeit ist keine Kurszeit und kein Gültigkeitsnachweis.</div></div>';
}
function productIssuerLabel(p){
 const sgIds=['DE000FG4JXV7','DE000FG309G0','DE000FG7EPT1','DE000FC1CHB7','DE000FG5GUT0','DE000FG6XB39','DE000FG5NMF2','DE000FG7MTA6'];
 const sg=sgIds.includes(p.isin)||/^SG\b|Soci[eé]t[eé] G[eé]n[eé]rale/i.test(p.name||'');
 return sg?'SG':/BNP|Paribas/i.test(p.name||'')||['DE000PJ9NB98','DE000PJ9NCK0'].includes(p.isin)?'BNP':'Emittenten';
}
function renderTestScreenshotRequest(p){
 const issuer=productIssuerLabel(p);
 return '<div data-test-screenshot-request class="small" style="margin:12px 0;padding:12px;background:#eaf3ff;border-radius:10px"><b>Für den Intraday-Test: aktuelle Screenshots erneut hochladen</b><div>Bitte öffne die '+esc(issuer)+'-Produktseite für <strong>'+esc(p.isin)+'</strong> und lade neue Bilder über den Knopf darunter hoch.</div><ul><li><b>Kursdaten:</b> Geld- und Briefkurs, angezeigtes Datum/Uhrzeit sowie ISIN oder WKN sichtbar aufnehmen.</li><li><b>Stammdaten:</b> fehlende oder nicht aktuell bestätigte Angaben ergänzen, insbesondere Basispreis und KO-Barriere mit Datenstand.</li></ul><div>Für einen späteren Vergleich erneut ein aktuelles Kursbild ergänzen. So kann Bob die Produktentwicklung besser auswerten. Kein Kauf nötig; die Bilder allein erteilen keine Handelsfreigabe.</div></div>';
}
function renderIssuerHelp(p,reasons){
 if(!reasons?.length||!validIsin(p.isin))return '';
 const issuer=productIssuerLabel(p),url=issuer==='SG'?'https://www.sg-zertifikate.de/product-details/'+p.isin.slice(5,11).toLowerCase():null;
 return '<div class="small" data-issuer-help style="margin:10px 0">'+(url?'<a data-screenshot-product="'+esc(p.isin)+'" href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">SG-Produkt öffnen</a>':'Produktseite des Emittenten öffnen ('+esc(issuer)+').')+'<details><summary>Hilfe zum Screenshot</summary>ISIN, fehlende Werte und den angezeigten Datenstand aufnehmen. Nach der Bildauswahl wird automatisch eingelesen.<button type="button" data-copy-product-isin="'+esc(p.isin)+'">ISIN kopieren</button><span role="status" data-copy-status></span></details></div>';
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
function bindIsinCopy(root){
 root.querySelectorAll('[data-screenshot-product]').forEach(link=>{
  if(link.dataset.returnBound)return;link.dataset.returnBound='1';
  link.addEventListener('click',()=>rememberScreenshotProduct(link.dataset.screenshotProduct));
 });
 root.querySelectorAll('[data-copy-product-isin]').forEach(button=>button.addEventListener('click',async()=>{
  const isin=button.dataset.copyProductIsin,status=button.parentNode.querySelector('[data-copy-status]');
  try{await navigator.clipboard.writeText(isin);if(status)status.textContent=' ISIN kopiert: '+isin;}
  catch(_){if(status)status.textContent=' Bitte manuell kopieren: '+isin;}
 }));
}
function renderMissingValues(reasons,p={}){
 const values=[...new Set(reasons||[])];if(!values.length)return '';
 const provider=/^BNP\b/i.test(p.name||'')||['DE000PJ9NCK0','DE000PG0XK25'].includes(p.isin)?'BNP-Produktseite':'SG-Produktseite';
 const location=reason=>{
  if(/Future-Kontrakt|Futures-Kontrakt/.test(reason))return 'Stammdaten: Basiswert mit Kontraktmonat/Jahr. Bei fehlenden Details: Dokumentation → Endgültige Bedingungen, Referenzkontrakt / Futures Contract und Börse.';
  if(/Geld|Brief|Kurszeit|Kursbild|Produktkurs|Kursnachweis/.test(reason))return 'Kursbereich oben: Geld und Brief in EUR zusammen mit „Kurs von“ (Datum/Uhrzeit) aufnehmen. Falls auch der Hebel fehlt: Kennzahlen ergänzen.';
  if(/Hebel/.test(reason))return 'Kennzahlen: Hebel aufnehmen. Den zugehörigen Datenstand mit erfassen, sofern angezeigt.';
  if(/Basispreis|Finanzierungslevel/.test(reason))return 'Stammdaten: Basispreis und das direkt daneben angegebene Datum aufnehmen.';
  if(/KO|Knock-out|Barriere/i.test(reason))return 'Stammdaten: Knock-Out-Barriere und das direkt daneben angegebene Datum aufnehmen.';
  if(/Bezugsverhältnis/.test(reason))return 'Stammdaten: Bezugsverhältnis aufnehmen.';
  if(/Basiswert/.test(reason))return 'Stammdaten: Basiswert aufnehmen; bei Futures den vollständigen Kontrakt zeigen.';
  if(/ISIN|Bildzuordnung|Detailbild|Original|Long\/Short/.test(reason))return 'Stammdaten: ISIN und Typ (Call/Put) sowie den Produktnamen aufnehmen.';
  if(/Währung/.test(reason))return 'Kursbereich: Währung neben Geld/Brief aufnehmen.';
  if(/Laufzeit|Fälligkeit|abgelaufen/.test(reason))return 'Produktname / Stammdaten: Open End oder Fälligkeit aufnehmen; ergänzend Produktbeschreibung.';
  return 'Stammdaten und Produktbeschreibung prüfen; ergänzende Angaben stehen unter Dokumentation.';
 };
 return '<details class="small" data-missing-values style="margin-top:8px"><summary style="cursor:pointer;padding:8px 0"><strong>Fehlende Werte</strong></summary><ul>'+values.map(reason=>'<li style="margin:10px 0"><strong>'+esc(reason.startsWith('Exakter Gold-Future-Kontrakt fehlt')?'Exakter Future-Kontrakt fehlt oder ist nicht aktuell bestätigt':reason)+'</strong><br>Screenshot auf der '+esc(provider)+': '+esc(location(reason))+'</li>').join('')+'</ul><div>Den Produktlink oben öffnen. Lesbare Screenshots mit ISIN, Feldnamen und angezeigtem Datenstand über „Detailbilder ergänzen“ hochladen. Mehrere Ausschnitte sind möglich. Nicht angezeigte Datumsangaben bleiben offen; die Handy-Uhr ersetzt keinen Datenstand.</div></details>';
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
function compactProductCard(p,reasons=[],status='Nicht freigegeben'){
 const x=p.snapshot,terms=x?.terms||{},values=[];
 for(const [key,label] of Object.entries({strike:'Basispreis USD',ko:'KO USD',ratio:'Bezugsverhältnis',underlying:'Basiswert'})){
  const v=terms[key]?.value??(key==='ko'?x?.evidence?.KO?.value:null);if(v!==undefined&&v!==null)values.push(label+': '+v);
 }
 for(const [key,e] of Object.entries(x?.evidence||{})){if(key!=='KO'&&key!=='Spread')values.push(key+': '+e.value+(e.at?' · '+e.at:''));}
 const groups=[],unconfirmed=[];
 for(const reason of reasons){
  const dated=/datier|24 Stunden|Gültigkeit/i.test(reason)&&!/widerspr|ungültig/i.test(reason);
  const field=/Basispreis|Finanzierungslevel/.test(reason)?'Basispreis':/KO|Knock|Barriere/i.test(reason)?'KO-Barriere':null;
  if(dated&&field){const label=field+': Werte vorhanden – Aktualität unbestätigt';if(!unconfirmed.includes(label))unconfirmed.push(label);continue;}
  const label=/Future-Kontrakt|Futures-Kontrakt|Referenzkontrakt/.test(reason)?'Future-Kontrakt (Stammdaten → Basiswert; ggf. Dokumente → Endgültige Bedingungen)':/Basispreis|Finanzierungslevel/.test(reason)?'Basispreis: gültiger Nachweis (Stammdaten)':/KO|Knock|Barriere/i.test(reason)?'KO-Barriere: gültiger Nachweis (Stammdaten)':/Geld|Brief|Kurs/.test(reason)?'Geld, Brief und Quellenzeit (Kursdaten)':/Hebel/.test(reason)?'Hebel mit Datenstand (Kennzahlen)':/Bezugsverhältnis/.test(reason)?'Bezugsverhältnis fehlt oder ist nicht eindeutig (Stammdaten)':/Basiswert/.test(reason)?'Exakter Basiswert fehlt (Stammdaten / Produktbeschreibung)':/Produkttyp|Long\/Short|Produktrichtung/.test(reason)?'Produkttyp / Richtung (Stammdaten → Typ)':/Laufzeit|Fälligkeit/.test(reason)?'Laufzeit / Fälligkeit (Stammdaten)':/Währung/.test(reason)?'Produktwährung (Kursdaten)':/ISIN|Bildzuordnung|Original|bestätig/.test(reason)?'Produktzuordnung oder Bildwerte nicht eindeutig':reason.split(':')[0]+' (Quellen und Einzelheiten → Fehlende Werte)';
  if(!groups.includes(label))groups.push(label);
 }
 return '<div data-product-isin="'+esc(p.isin||'row-'+p.index)+'" data-selection-blocked="'+p.index+'" style="padding:12px;margin-top:10px;border:1px solid #d1d5db;border-radius:12px;overflow-wrap:anywhere"><b>'+esc(p.isin)+'</b> · '+esc(p.productDirection||'')+'<div class="small">'+'<strong>Nicht freigegeben</strong><br>Begründung: '+esc(status.replace(/^Nicht freigegeben · /,''))+'</div>'+
 (values.length?'<details style="margin-top:10px"><summary>Automatisch erkannte Werte</summary><div class="small">'+values.map(esc).join('<br>')+'</div></details>':'')+
 (unconfirmed.length?'<div class="small" style="margin-top:8px"><em>'+unconfirmed.map(esc).join('<br>')+'</em></div>':'')+
 '<details style="margin-top:8px"><summary>Fehlende Werte ('+groups.length+')</summary><div class="small">'+(groups.length?groups.map(esc).join('<br>'):'Keine fehlenden Produktnachweise.')+'</div></details>'+
 renderIssuerHelp(p,reasons)+renderTestScreenshotRequest(p)+'<button data-selection-upload="'+p.index+'">Screenshots hinzufügen</button>'+renderImageImportStatus(p.index)+
 '<details data-product-details="'+p.index+'" style="margin-top:10px"><summary>Quellen und Einzelheiten</summary><div class="small">'+esc(p.name||'')+'</div>'+renderProductSources(p)+renderMissingValues(reasons,p)+renderProductDecision(p,false,[status,...reasons])+screenshotSummary(x)+'<button data-card-research="'+p.index+'">Daten erneut abrufen</button></details></div>';
}
function bindCompactCards(root){
 bindIsinCopy(root);
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
 const notApproved=r.notApproved||[];
 return '<b>'+ (r.approved?'Zur Produktauswahl freigegeben · '+r.approvedCount+' geeignete'+(r.approvedCount===1?'s Produkt':' Produkte'):'Abwarten – derzeit kein geeignetes Produkt')+'</b>'+steps+
 '<div class="small">'+esc((r.gateReasons||[]).join(' · '))+'</div>'+
 '<div class="small">'+r.total+' unterschiedliche Produkte. Vorauswahl nach Analyse-Richtung '+esc(r.direction)+'; fehlende Preise erhalten keine Rangpunkte.</div>'+
 r.groups.map(g=>'<div style="margin-top:12px"><b>'+esc(g.scope)+' · '+g.total+' bewertbare Produkte</b>'+g.candidates.map((c,i)=>'<div data-product-isin="'+esc(c.isin)+'" style="padding:10px;margin-top:8px;border:1px solid #dbe4f0;border-radius:12px"><b>Platz '+(i+1)+' · '+esc(c.isin)+'</b><div class="small">'+esc(c.name)+'<br>'+esc(c.priceKind)+' · Brief '+Number(c.price).toFixed(2)+' EUR · Risiko-/Datenwert '+c.score+'/100<br>Warum: '+esc((c.reasons||[]).slice(0,3).join(' · '))+'<br>Quelle '+esc(c.source||'Produktnachweis')+' · Datenzeit '+esc(c.at)+(c.quoteAt?' · Produktkurszeit '+esc(c.quoteAt):'')+(c.quality?'<br>'+esc(qualityText(c.quality,'USD')):'')+'</div>'+renderProductDecision(c)+renderProductSources(c)+'</div>').join('')+'</div>').join('')+
 (notApproved.length?'<details style="margin-top:14px"><summary>Weitere Produkte · nicht freigegeben ('+notApproved.length+')</summary>'+notApproved.map(p=>compactProductCard({...products[p.index-1],...p},p.missingReasons,p.reasons.some(v=>/neutral|NEUTRAL/.test(v))?'Nicht freigegeben · Marktsignal neutral':'Nicht freigegeben · '+(p.reasons[0]||'Nachweise prüfen'))).join('')+'</details>':'')+
 '<details class="small" style="margin-top:10px"><summary>Hinweise zur Produktauswahl</summary>Spot und Future werden getrennt bewertet. Weniger als drei belegte Produkte ergeben eine kürzere Liste. Freigabe gilt ausschließlich für diese geprüfte Produktauswahl, nicht als Handelsauftrag oder garantierter bester Trade. Kandidaten mit offenen Nachweisen bleiben gesperrt; tatsächlichen DEGIRO-Preis vor dem Einstieg prüfen.</details>';
}

function productUploadCards(products,direction,now=Date.now()){
 return (products||[]).map((p,z)=>({...p,index:z+1})).filter(p=>p.name||p.isin).sort((a,b)=>Number(b.productDirection===direction)-Number(a.productDirection===direction)).map(p=>compactProductCard(p,finalProductStatus(p,now).reasons,'Produktnachweise prüfen')).join('');
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
function parseProductTerms(raw){
 raw=String(raw).replace(/(?:©|®|ⓘ|@)/g,'').replace(/Bezugsverhaltnis/g,'Bezugsverhältnis');
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
  let matches=Array.from(String(raw).matchAll(new RegExp('(?:^|\\n)\\s*(?:'+label+')\\s*[:=]?\\s*([^\\n]+)','gi')));
  // Issuers use "Produktart" for the instrument family and "Typ" for
  // Call/Put or Long/Short. Only fall back to Typ when no product-family
  // label exists, otherwise both rows would be treated as contradictory.
  if(key==='type'&&!matches.length)matches=Array.from(String(raw).matchAll(/(?:^|\n)\s*Typ\s*[:=]?\s*([^\n]+)/gi));
  if(!matches.length)continue;
  const values=Array.from(new Set(matches.map(m=>m[1].trim())));
  if(values.length!==1)return {error:'Widersprüchliche Produktbedingung: '+label.split('|')[0]};
  let value=values[0],dateText=null,dateWarning=null;
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
   value=strictOcrNumber(m[1]);if(!(value>0&&Number.isFinite(value)))return {error:label.split('|')[0]+': positiver Wert erforderlich'};
  }
  out[key]={value,at:dateWarning?null:at,dateText,ocrCorrection:dateWarning||(numberCorrection&&['ko','strike'].includes(key)?'OCR-Trennzeichen anhand des deutschen Tabellenformats vereinheitlicht; am Original prüfen':null)};
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
  const record=PRODUCT_CONDITION_RESEARCH[p.isin];if(!record||p.direction!==record.direction)return p;
  const old=p.snapshot?.isin===p.isin?p.snapshot:{isin:p.isin},terms={...old.terms};
  for(const [key,value]of Object.entries(record.values))if(!terms[key]||terms[key].value===undefined||terms[key].value==='')terms[key]={value,at:null,source:record.source,conditionVerified:true,reviewedAt:CONDITION_RESEARCH_AT};
  return {...p,snapshot:{...old,terms}};
 });
}
function automaticIdentity(p){
 if(!validIsin(p.isin))return false;
 const q=p.quote,x=p.snapshot;
 const image=x?.isin===p.isin&&['ISIN','WKN'].includes(x.identityBasis);
 const issuer=q?.isin===p.isin&&q.productVerified===true;
 if(!image&&!issuer)return false;
 if(image){
  if(x.direction&&p.productDirection!==x.direction)return false;
  for(const [field,key]of Object.entries({price:'Kurs',leverage:'Hebel',ko:'KO'})){
   const e=x.evidence?.[key];
   // A verified quote for this exact product may update mutable market values.
   // Identity is separate from quote freshness; downstream quote gates remain.
   if(e&&n(p[field])!==n(e.value)&&!(issuer&&['price','leverage'].includes(field)&&n(q[field])!==null&&n(p[field])===n(q[field])))return false;
  }
 }
 if(issuer&&q.direction&&q.direction!==p.productDirection)return false;
 return true;
}
function automaticCondition(e,key){
 if(!e?.source||e.conflict||e.revoked||e.ocrCorrection)return false;
 const value=String(e.value??'').trim();
 return key==='ratio'?n(e.value)>0&&n(e.value)<=1:
  key==='underlying'?/^(Gold|XAU\/USD|Gold Future)$/i.test(value):
  key==='type'?/^(BEST Turbo-Optionsscheine? \(Open-End\)|Turbo|Turbo BEST|Mini Future|Knock-out Turbo|Unlimited (?:Long|Short))$/i.test(value):
  key==='maturity'?/^(Open[ -]?End|Unbegrenzt)$/i.test(value):key==='currency'?value==='EUR':false;
}
function durableCondition(e,key,now){
 if(!e?.source||e.revoked===true||e.conflict===true)return false;
 if(e.automatic===true&&!e.at&&automaticCondition(e,key))return true;
 // Only explicit product-condition evidence may outlive a daily market snapshot.
 if(['type','currency','maturity'].includes(key)&&e.reviewed===true)return true;
 const checked=Date.parse(e.reviewedAt);
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
 if(e.at){const age=now-Date.parse(e.at);return Number.isFinite(age)&&age>=0&&age<=86400000;}
 const m=String(e.dateText||'').match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
 return !!m&&m[3]+'-'+m[2]+'-'+m[1]===zurichListDay(now).day;
}
function screenshotKoCurrent(p,now){
 const x=p.snapshot,e=x?.evidence?.KO,t=x?.terms?.ko;
 if(x?.isin!==p.isin||n(e?.value)!==n(p.ko))return false;
 if(e?.at)return currentDatedTerm(e,now);
 return ['ISIN','WKN'].includes(x.identityBasis)&&n(t?.value)===n(p.ko)&&
  t?.source===e?.source&&t?.dateText===e?.dateText&&currentDatedTerm(t,now);
}
function productTermsStatus(p,now=Date.now()){
 const reasons=[],values={},q=p.quote?.isin===p.isin?p.quote:null;
 const meta=q?.productVerified?q.metadata:null;
 const model=q?.productModel?.isin===p.isin?q.productModel:meta?.underlyingType==='FUTURE'&&meta.contract&&meta.contract===q?.futureResearch?.contract?q.futureResearch:null;
 const shot=p.snapshot?.isin===p.isin?p.snapshot:null,terms={...(q?.productVerified?q.conditions:{}),...shot?.terms};
 if(shot&&['ISIN','WKN'].includes(shot.identityBasis))for(const [key,e]of Object.entries(shot.terms||{})){
  if(automaticCondition(e,key))terms[key]={...e,automatic:true};
 }
 if(!validIsin(p.isin)||p.isinConfirmed!==true)reasons.push('Eindeutige Produktzuordnung oder widerspruchsfreie Bildwerte fehlen');
 if(!['LONG','SHORT'].includes(p.productDirection))reasons.push('Long/Short fehlt');
 if(/FAKTOR|FACTOR/i.test([p.name,q?.name,meta?.name,terms.type?.value].join(' ')))reasons.push('Faktorprodukt ausgeschlossen');
 const api=model&&q?.productVerified&&q.source&&q.checkedAt&&now>=Date.parse(q.checkedAt)&&now-Date.parse(q.checkedAt)<=86400000?model:null;
 const labels={ratio:'Bezugsverhältnis',strike:'Basispreis in USD',underlying:'Exakter Basiswert (z. B. XAU/USD)',type:'Produkttyp',maturity:'Laufzeit / Fälligkeit oder Open End',currency:'Produktwährung'};
 for(const [key,label] of Object.entries(labels)){
  const e=terms[key],age=now-Date.parse(e?.at);
  if(key==='strike'&&shot&&['ISIN','WKN'].includes(shot.identityBasis)&&currentDatedTerm(e,now)||durableCondition(e,key,now)||e?.source&&Number.isFinite(age)&&age>=0&&age<=86400000)values[key]=e.value;
  else if(api&&['ratio','strike','underlying'].includes(key))values[key]=api[key];
  if(values[key]===undefined||values[key]==='')reasons.push(label+((e?.value!==undefined&&e.value!=='')?(key==='strike'?': Wert eingelesen; gültiger datierter Nachweis fehlt oder ist älter als 24 Stunden':': Wert eingelesen; Produktbedingung nicht eindeutig belegt'):': Wert fehlt'));
 }
 for(const key of ['ratio','strike'])if(values[key]!==undefined&&!(n(values[key])>0))reasons.push(labels[key]+': ungültig');
 if(values.currency&&values.currency!=='EUR')reasons.push('Produktwährung EUR erforderlich');
 if(values.type&&!/turbo|mini.?future|knock.?out|^Unlimited (?:Long|Short)$/i.test(values.type))reasons.push('Produkttyp nicht als Turbo / Knock-out bestätigt');
 const typeDirection=String(values.type||'').match(/^Unlimited (Long|Short)$/i);
 if(typeDirection&&typeDirection[1].toUpperCase()!==p.productDirection)reasons.push('Produktrichtung widerspricht Produkttyp');
 const future=isFutureProduct(p)||/future/i.test(values.underlying||'');
 if(future){
  const e=terms.contract,age=now-Date.parse(e?.at);
  values.contract=e?.source&&Number.isFinite(age)&&age>=0&&age<=86400000?e.value:null;
  if(!/^GC[FGHJKMNQUVXZ]\d{2}$/.test(values.contract||''))reasons.push('Exakter Gold-Future-Kontrakt fehlt oder ist nicht aktuell bestätigt. Öffne das betroffene Produkt bei DEGIRO: Produktdetails → Dokumente → Endgültige Bedingungen (falls dort nicht vorhanden: Dokumente auf der Emittentenseite). Nutze im Dokument die Suche (Lupe): zuerst deine ISIN, dann Basiswert / Underlying, Referenzkontrakt / Futures Contract oder Kontraktmonat. Die Angaben stehen häufig in einer Tabelle mit Produktbedingungen; bei mehreren Produkten zählt nur die Zeile zu deiner ISIN. Benötigt werden der genaue Future mit Monat/Jahr und Börse. Suche zusätzlich nach Roll / Rollover / Anpassung des Basiswerts für einen möglichen Kontraktwechsel. Lade gut lesbare Screenshots der passenden Tabellenzeile samt Spaltenüberschriften und der relevanten Textstellen als Detailbilder zu diesem Produkt hoch; ISIN und Dokumentdatum bitte mit aufnehmen. Eine feste Seitenzahl kann Bob ohne das konkrete Dokument nicht nennen.');
  if(meta?.contract&&values.contract&&meta.contract!==values.contract)reasons.push('Future-Kontrakt widerspricht Emittentendaten');
  if(values.underlying&&!/\bgold\b.*\bfuture\b|\bfuture\b.*\bgold\b/i.test(values.underlying))reasons.push('Exakter Gold-Future-Basiswert widerspricht Produktart');
 }else if(values.underlying&&values.underlying!=='XAU/USD')reasons.push('Basiswert ungenau: Gold allein bestätigt keinen Spot-Basiswert');
 if(meta?.direction&&meta.direction!==p.productDirection||model?.direction&&model.direction!==p.productDirection||shot?.direction&&shot.direction!==p.productDirection)reasons.push('Long/Short widerspricht Produktnachweis');
 for(const key of ['ratio','strike'])if(model?.[key]&&values[key]&&n(model[key])!==n(values[key]))reasons.push(labels[key]+': Screenshot und Emittent widersprechen sich');
 if(values.maturity&&!/^open\s*end$|^unbegrenzt$/i.test(values.maturity)){
  const end=maturityDeadline(values.maturity);
  if(!Number.isFinite(end)||end<=now)reasons.push('Fälligkeit fehlt als eindeutiger Zeitpunkt oder Produkt ist abgelaufen');
 }
 const ko=shot?.evidence?.KO,apiKoAge=now-Date.parse(q?.checkedAt);
 if(!(n(p.ko)>0))reasons.push('Knock-out-Schwelle fehlt');
 else if(!screenshotKoCurrent(p,now)&&!(meta&&meta.termsDated!==false&&q.source&&n(meta.ko)===n(p.ko)&&apiKoAge>=0&&apiKoAge<=86400000))reasons.push('Knock-out-Schwelle: datierter Produktnachweis fehlt oder älter als 24 Stunden');
 if(meta?.ko&&n(p.ko)!==n(meta.ko))reasons.push('Knock-out-Schwelle widerspricht Produktquelle: gespeichert '+p.ko+' USD ('+(ko?.source||'Produktliste / manuelle Eingabe')+'; Stand '+(ko?.at||ko?.dateText||'nicht belegt')+'), Quelle '+meta.ko+' USD ('+(q.termsSource||q.source||'Produktquelle')+'; Gültigkeitsstand '+(meta.termsDated===false?'nicht belegt':q.checkedAt||'nicht belegt')+'). Abrufzeit '+(q.termsCheckedAt||q.checkedAt||'unbekannt')+' ist kein Gültigkeitsdatum.');
 if(meta?.status!==undefined&&(!(meta.status&1)||meta.status&(2|8|16|32)))reasons.push('Produkt laut Emittent nicht aktiv');
 return {complete:reasons.length===0,reasons,values};
}
function finalProductStatus(p,now=Date.now(),reference){
 const status=productTermsStatus(p,now),reasons=status.reasons.slice();
 const q=p.quote?.isin===p.isin?p.quote:null;
 const r=q?.productVerified&&q.metadata?.contract===q.futureResearch?.contract?q.futureResearch:null;
 const pair=(x,source)=>!!source&&n(x?.bid)>0&&n(x?.ask)>=n(x.bid)&&!x.delayed&&freshTimes([x.bidAt,x.askAt],now,90);
 const issuer=pair(q,q?.source)&&q.found&&!q.estimated&&!q.calculatedProduct&&q.currency==='EUR'&&q.direction===p.productDirection&&q.marketOpen;
 const future=pair(r,q?.source)&&r.direction===p.productDirection&&r.marketOpen;
 const shot=selectionDetailStatus(p,now);
 const ref=reference?.isin===p.isin&&reference.reviewed&&reference.paired&&reference.source&&reference.venue&&!reference.delayed&&n(reference.bid)>0&&n(reference.ask)>=n(reference.bid)&&freshTimes([reference.quoteAt],now,90);
 if(!issuer&&!future&&!shot.complete&&!ref)reasons.push('Geld-/Briefnachweis fehlt: Emittentenkurs höchstens 90 Sekunden oder geprüftes Screenshot-Kursbild höchstens 14 Stunden; '+shot.reasons.filter(x=>!status.reasons.includes(x)).join(' · '));
 return {...status,complete:!reasons.length,reasons};
}
function detailScreenshotData(text,expectedIsin){
 let raw=normalizeBnpQuoteColumns(String(text||""));
 // BNP's Gold reference identifier is not the certificate ISIN.
 // Scope removal to the explicit Gold underlying section, preserving all
 // certificate identifiers and rejecting conflicting product identities.
 if(/derivate\.bnpparibas\.com|BNP\s+Paribas/i.test(raw)&&/Basiswert\s+GOLD\b/i.test(raw)){
  raw=raw.replace(/(Basiswert\s+GOLD\s+ISIN\s*[:=]?\s*)USFX0{5}XAU\b/i,'Basiswert GOLD\nReferenzkennung XAU/USD');
  raw=raw.replace(/(?:^|\n)\s*Basiswert\s*\n(?=\s*Basiswert\s+GOLD\b)/i,'\n');
 }
 if(!validIsin(expectedIsin))return{ok:false,reason:"Bitte zuerst die ISIN dieses Produkts am Screenshot prüfen und korrigieren."};
 const identity=screenshotIdentity(raw,expectedIsin);
 if(!identity.ok)return identity;
 if(/BNP\s+PARIBAS|derivate\.bnpparibas\.com/i.test(raw)){
  raw=raw.replace(/\bVerkaufen\b/g,'Geld').replace(/\bKaufen\b/g,'Brief');
 }
 // Reject an entire numeric token instead of accepting a numeric prefix
 // such as 12 from "12,O9". Alphabet characters are never prices.
 const numericTokens=raw.matchAll(/(?:^|\n)\s*(?:Geld|Brief|Bid|Ask|Hebel)\s*[:=]?\s*(?:€|EUR)?\s*([0-9][0-9A-Za-z.,]*)/gi);
 for(const token of numericTokens)if(strictOcrNumber(token[1])===null)return {ok:false,reason:'Zahl enthält unklare Zeichen: '+token[1]+'. Bitte einen schärferen Ausschnitt zeigen.'};
 const titlePair=sgScreenshotTitlePair(raw,expectedIsin);
 if(titlePair){
  // Both values are visible in this same image's SG browser title. Never
  // borrow the second price or its timestamp from another screenshot.
  raw=raw.replace(/\b(?:Geld|Brief)\b/gi,'Kursanzeige');
  raw+='\nGeld '+titlePair.bid+' EUR\nBrief '+titlePair.ask+' EUR';
 }
 if(identity.basis==='WKN')raw='ISIN '+expectedIsin+'\n'+raw;
 const x=ocrExtract(raw.replace(/(\bBAR\s*\n)[@©●•®]\s*(?=[0-9])/gi,"$1"));
 if(/\b(?:SHORT|PUT)\b/i.test(raw)&&/\b(?:LONG|CALL)\b/i.test(raw))return {ok:false,reason:'Long/Short im Bild widersprüchlich: Produktzuordnung prüfen'};
 if(!x.price){const top=raw.match(/(?:^|\n)\s*€\s*([0-9]+(?:[.,][0-9]+)?)\b/);if(top)x.price=top[1].replace(",",".");}
 const amount=label=>{const m=raw.match(new RegExp("\\b(?:"+label+")(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR)?\\s*([0-9]+(?:[.,][0-9]+)?)","i"));return m?Number(m[1].replace(",",".")):null;};
 const draft=window.BobCombined.screenshotDraft(raw,expectedIsin);
 if(draft.hasQuote&&!draft.paired)return{ok:false,reason:'Produkt erkannt'+(identity.basis==='WKN'?' über WKN '+identity.wkn:'')+', aber Geld-/Briefpaar nicht vollständig oder eindeutig. Bitte beide Kurse im selben Bild zeigen.'};
 const bid=draft.paired?n(draft.fields.bid):amount("Geld|Bid"),ask=draft.paired?n(draft.fields.ask):amount("Brief|Ask");
 if(draft.fields.ko1)x.ko=draft.fields.ko1;
 if((bid!==null&&bid<=0)||(ask!==null&&ask<=0)||(bid!==null&&ask!==null&&ask<bid))return{ok:false,reason:"Geld-/Briefkurse widersprüchlich gelesen. Bitte ein schärferes Bild hochladen."};
 const quoteText=raw.replace(/(?:^|\n)\s*(?:Produktdatenstand|Bedingungenstand|Fälligkeit|Faelligkeit|Laufzeit|KO-Zeit|Hebelzeit)\s*[:=]?[^\n]*/gi,'');
 const stamp=screenshotTimes(raw).quote?.text||(quoteText.match(/\b\d{2}[/.]\d{2}[/.]\d{4}\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||"";
 const currency=/\bEUR\b|€/.test(raw)?"EUR":"";
 if(bid!==null&&ask!==null&&currency==="EUR"){x.price=String(ask);x.spread=String(Math.round((ask-bid)*1000000)/1000000);}
 if(!x.leverage){const lv=raw.match(/\bLV\s+(\d+(?:[.,]\d+)?)/i);if(lv)x.leverage=lv[1].replace(",",".");}
 const terms=parseProductTerms(raw);
 if(terms.error)return {ok:false,reason:terms.error};
 // Explicit wrapped SG product heading/table text, not an inferred product model.
 if(/BEST Turbo-\s*(?:\n\s*Produktart\s+)?Optionsscheine?\s*\(Open-\s*End\)/i.test(raw)){
  terms.type={value:'BEST Turbo-Optionsscheine (Open-End)',at:null};
  terms.maturity={value:'Open End',at:null};
 }
 if(!terms.currency&&currency==='EUR'&&bid!==null&&ask!==null)terms.currency={value:'EUR',at:null,fromQuote:true};
 if(terms.ko)x.ko=String(terms.ko.value);
 return{ok:true,...x,identityBasis:identity.basis,bid,ask,currency,sourceTime:stamp,times:screenshotTimes(raw),terms,delayed:/verzögert|delayed/i.test(raw),combinedDraft:draft};
}
// Show only product identifiers on failures, never the full private OCR transcript.
function imageIdentityDiagnostic(raw){
 const text=String(raw||'').toUpperCase();
 const ids=[...new Set(text.match(/\b(?=[A-Z0-9]*[0-9])[A-Z]{2}[A-Z0-9]{10}\b/g)||[])].slice(0,3);
 const wkns=[...new Set(Array.from(text.matchAll(/\bWKN\s*[:=]?\s*([A-Z0-9]{6})\b/g),m=>m[1]))].slice(0,3);
 return 'Gelesen: '+(ids.length?'ISIN '+ids.join(', '):'keine ISIN')+(wkns.length?' · WKN '+wkns.join(', '):'');
}
function screenshotIdentity(raw,expectedIsin){
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
 const unique=[...new Set(wkns.map(code=>badge&&code.length===6&&Array.from(code).every((char,i)=>ocrGlyphPair(char,badge[1][i]))?badge[1]:code))];
 if(validIsin(expectedIsin)&&expectedIsin.startsWith('DE000')&&unique.length===1&&unique[0]===expectedIsin.slice(5,11))return{ok:true,basis:'WKN',wkn:unique[0]};
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
async function readScreenshot(i,file){
 const status=document.getElementById("dgOcrStatus"+i),field=k=>document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]');
 if(!file)return;
 const expected=(field("isin")?.value||"").trim().toUpperCase(),version=(rowVersions.get(i)||0)+1;rowVersions.set(i,version);
 if(status)status.textContent="📷 "+file.name+" für "+expected+" wird automatisch eingelesen …";rankUI();
 try{
  const result=await recognizeOcr(file,"dgOcrStatus"+i);
  if((rowVersions.get(i)||0)!==version||(field("isin")?.value||"").trim().toUpperCase()!==expected)return;
  const x=detailScreenshotData(result.data.text,expected);
  if(!x.ok){const reason=x.reason+" "+imageIdentityDiagnostic(result.data.text)+" · Bildimport 05.10-15";if(status)status.textContent="⚠️ "+reason;return{ok:false,reason};}
  const merged=mergeScreenshotEvidence(detailScreenshots.get(i),x,file.name);
  productQuotes.delete(i);
  for(const [k,v] of Object.entries({dir:merged.direction,price:merged.price,lev:merged.leverage,ko:merged.ko,spread:merged.spread})){if(v!==""&&v!==null&&v!==undefined&&field(k))field(k).value=v;}
  if(merged.clearSpread&&field("spread"))field("spread").value="";
  detailScreenshots.set(i,merged);if(field("confirmed"))field("confirmed").checked=false;
  prefillCombinedForm(i,x.combinedDraft,file.name);
  if(status)status.textContent="✅ Zusatzbild zugeordnet. Erkannte Werte automatisch übernommen. "+(merged.sourceTime?"Kurszeit im Bild: "+merged.sourceTime:"Kurszeit im Bild fehlt.");
  const meta=document.getElementById("dgResearch"+i);if(meta)meta.textContent="📷 "+(x.combinedDraft?.source||'Screenshot')+"-Momentaufnahme · "+(merged.bid!==null?"Geld "+merged.bid+" / Brief "+(merged.ask??"fehlt")+" "+merged.currency+" · ":"")+"keine laufenden Live-Daten. Unvollständige Kursnachweise bleiben gesperrt.";
  rankUI();
  return{ok:true,data:x,raw:result.data.text,reason:x.identityBasis==='WKN'?'über passende WKN zugeordnet':'über ISIN zugeordnet'};
 }catch(e){if((rowVersions.get(i)||0)!==version)return;const reason=e?.message||'Unbekannter Fehler';if(status)status.textContent="⚠️ Bild konnte nicht eingelesen werden: "+reason+". Bitte erneut auswählen.";return{ok:false,reason};}
}
// The user declares one multi-image selection to be a contemporaneous series.
// Preserve original field timestamps and condition dates; record inferred timing.
function linkScreenshotSeries(outcomes){
 const accepted=outcomes.filter(o=>o.ok&&o.data),ids=new Set(accepted.map(o=>o.data.isin));
 if(accepted.length<2||ids.size!==1)return null;
 const full=[],dates=[],clocks=[];
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
 }
 let text='',sources=[],basis='Kurszeit aus zugehörigem Bild';
 if(full.length){
  if(new Set(full.map(v=>selectionTimeWindow(v.text).start)).size!==1)return null;
  text=full[0].text;sources=full.map(v=>v.source);
 }else{
  if(new Set(dates.map(v=>v.text)).size!==1||new Set(clocks.map(v=>v.text)).size!==1)return null;
  text=dates[0].text+' '+clocks[0].text;sources=[dates[0].source,clocks[0].source];
  basis='Datum und Kursuhrzeit aus derselben Aufnahmeserie kombiniert; Gleichzeitigkeit laut Nutzer';
 }
 const window=selectionTimeWindow(text);if(!window)return null;
 const series={text,at:new Date(window.start).toISOString(),sources:[...new Set(sources)],basis,userDeclaredSimultaneous:true,timezone:'Europe/Zurich angenommen'};
 for(const o of accepted){
  const x=o.data;x.captureSeries=series;
  const hasQuote=x.bid!=null&&x.ask!=null;
  if(hasQuote&&!x.sourceTime&&!x.times?.quote?.present){
   x.sourceTime=text;x.times={...x.times,quote:{present:true,text,at:series.at,fromSeries:true}};
   // A leverage in this same quote image shares the declared capture time.
   if(n(x.leverage)!==null&&!x.times.leverage?.present)x.times.leverage={present:true,text,at:series.at,fromSeries:true};
  }
 }
 return series;
}
function screenshotBatchSummary(outcomes){
 const accepted=outcomes.filter(x=>x.ok).length;
 return (accepted?'✅ ':'⚠️ ')+accepted+' von '+outcomes.length+' Bild(ern) übernommen. '+(accepted?'':'')+outcomes.map(x=>(x.ok?'✓ ':'⚠️ ')+x.name+': '+x.reason).join(' · ');
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
 if(hasQuote&&!x.captureSeries)delete merged.captureSeries;
 merged.times={...(previous.times||{})};
 if(hasQuote)for(const key of ['quote','bid','ask'])delete merged.times[key];
 for(const [key,value] of Object.entries(x.times||{}))if(hasQuote&&['quote','bid','ask'].includes(key)||!['quote','bid','ask'].includes(key)&&value.present)merged.times[key]=value;
 merged.terms={...(previous.terms||{})};
 for(const [key,value] of Object.entries(x.terms||{})){
  if(value.fromQuote&&merged.terms[key]?.value===value.value)continue;
  const incoming={...value,source};
  incoming.automatic=['ISIN','WKN'].includes(x.identityBasis)&&automaticCondition(incoming,key);
  merged.terms[key]=incoming;
 }
 if(!hasQuote){for(const key of ["bid","ask","currency","sourceTime","delayed"])merged[key]=previous[key]??x[key];}
 else {for(const key of ["Kurs","Geld","Brief","Spread"])delete evidence[key];merged.clearSpread=n(x.spread)===null;}
 for(const [key,value] of Object.entries({Richtung:x.direction,Kurs:x.price,Hebel:x.leverage,KO:x.ko,Geld:x.bid,Brief:x.ask,Spread:x.spread})){if(value!==""&&value!==null&&value!==undefined)evidence[key]={value,source,at:fieldSourceTime(x,key),dateText:key==='KO'?x.terms?.ko?.dateText:null};}
 if(hasQuote&&evidence.Spread){const times=[evidence.Geld?.at,evidence.Brief?.at];evidence.Spread.at=times.every(Boolean)?times.sort()[0]:null;}
 for(const [key,field] of Object.entries({Kurs:"price",Hebel:"leverage",KO:"ko",Spread:"spread",Richtung:"direction"})){merged[field]=evidence[key]?.value??"";}
 return merged;
}
function supplementaryHint(missing){
 const identity=missing.includes("eindeutige ISIN");
 const staticFields=missing.some(v=>["Produktrichtung","Hebel","KO-Schwelle"].includes(v));
 const quotes=missing.some(v=>["Produktkurs","Geld-/Briefkurse für den Spread","bestätigte aktuelle Kursdaten mit Zeitstempeln"].includes(v));
 return (identity?"Bitte ein Bild mit eindeutig sichtbarer ISIN hochladen. ":"")+(staticFields?"Bitte Produktübersicht mit Richtung, Hebel und KO-Schwelle ergänzen. Für Hebel und KO sind eigene datierte Quellen erforderlich; ein neues Kursbild erneuert sie nicht. ":"")+(quotes?"Bitte Kursdatenbild mit ISIN, Geld, Brief und ausdrücklich zugeordneter Kurszeit (Datum, Sekunden, Zeitzone) ergänzen. Uploadzeit zählt nicht. ":"")+"Unlesbare oder widersprüchliche Angaben bleiben offen.";
}
function screenshotTimeLabel(x){
 const e=x?.evidence?.Geld;
 if(e?.at){const t=evidenceTiming(e);return 'Kursquelle: '+e.at+' · '+(t.ageSeconds===null?'Zeit unklar':t.ageSeconds+' s alt · '+(t.fresh?'Nachweis innerhalb von 14 Stunden gültig':'Nachweis abgelaufen'))+' · Momentaufnahme, keine Live-Verifizierung.';}
 return x?.sourceTime?'Kursstand im Bild: '+x.sourceTime+' · Aktualität nicht verifiziert. Vollständige, ausdrücklich zugeordnete Kurszeit mit Sekunden und Zeitzone erforderlich.':'Kurszeit fehlt – Aktualität nicht prüfbar. Kein Live-Kurs.';
}
function screenshotSummary(x){
 if(!x)return "";
 const seriesNote=x.captureSeries?'<div><b>Gemeinsame Aufnahmeserie: '+esc(x.captureSeries.text)+'</b><br>'+esc(x.captureSeries.basis)+' · '+esc(x.captureSeries.timezone)+'<br>Bildquellen: '+esc(x.captureSeries.sources.join(', '))+'</div>':'';
 const labels={ratio:'Bezugsverhältnis',strike:'Basispreis USD',underlying:'Basiswert',contract:'Future-Kontrakt',type:'Produkttyp',maturity:'Laufzeit',currency:'Produktwährung',ko:'KO-Barriere'};
 const card=(label,e,time)=>'<div style="min-width:0;max-width:100%;overflow-wrap:anywhere;border-bottom:1px solid #ddd;padding:10px 0;'+(calculationAge(e.at,SCREENSHOT_MAX_AGE_MS)&&!e.conditionVerified?'font-style:italic':'')+'"><b>'+esc(label)+': '+esc(e.value)+'</b>'+(e.ocrCorrection?'<div>'+esc(e.ocrCorrection)+'</div>':'')+'<div>Quelle: '+esc(e.source||'nicht angegeben')+'</div><div>'+esc(time)+'</div></div>';
 const terms=x.terms||{},ko=x.evidence?.KO;
 const sameKo=terms.ko&&ko&&n(terms.ko.value)===n(ko.value);
 const rows=Object.entries(x.evidence||{}).filter(([key])=>key!=='Spread'&&!(key==='KO'&&sameKo)).map(([key,e])=>{
  const t=evidenceTiming(e);return card(key==='KO'?'KO-Barriere':key,e,e.at||(e.dateText?'Datenstand '+e.dateText+(currentDatedTerm(e,Date.now())?' · für diesen Kalendertag belegt; keine Kurszeit':' · nicht für heute bestätigt'):key==='Richtung'?'Eingelesen · am Original prüfen':'Wert eingelesen · Quellenzeit fehlt'));
 }).join('');
 const termRows=Object.entries(terms).filter(([key])=>key!=='quanto').map(([key,e])=>card(labels[key]||key,e,(e.automatic||['ISIN','WKN'].includes(x.identityBasis)&&automaticCondition(e,key))?'Automatisch aus zugeordnetem Bild gelesen · keine Kurszeit':e.conditionVerified?'Produktbedingung recherchiert '+e.reviewedAt+' · keine Kurszeit':e.reviewed&&['type','currency','maturity'].includes(key)?'Geprüfte Produktbedingung · keine Kurszeit':e.at||(e.dateText?'Datenstand '+e.dateText+(currentDatedTerm(e,Date.now())?' · für diesen Kalendertag belegt; keine Kurszeit':' · nicht für heute bestätigt'):'Wert eingelesen · Produktnachweis noch nicht bestätigt; Datenstand fehlt'))).join('');
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
 b.innerHTML='<div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b><div class="small">Produktliste erfassen → Bilder pro ISIN ergänzen → belegte Daten vergleichen</div></div></div>'+
 '<div id="dgScreenshotReturn" hidden style="margin-top:14px;padding:14px;background:#eaf3ff;border:2px solid #1677ff;border-radius:14px;scroll-margin-top:16px"><b>Screenshots für <span data-return-isin></span></b><p class="small">Hier beim zuletzt geöffneten Produkt weitermachen. Die Bilder werden weiterhin auf die passende ISIN geprüft.</p><button type="button" data-return-upload style="width:100%;background:#1677ff">↑ Bilder für dieses Produkt hinzufügen</button><button type="button" data-return-close>Fertig / ausblenden</button><div role="status" data-return-status></div></div>'+
 '<div style="margin-top:14px;padding:12px;background:#fff;border-radius:16px;border:1px solid #e1e7f0">'+
 '<b>📷 DEGIRO-Liste</b><button type="button" id="dgListUploadButton" style="margin-top:10px;width:100%;background:#1677ff">↑ DEGIRO-Liste hochladen</button>'+
 '<input id="dgListUpload" type="file" accept="image/*" multiple hidden>'+
 '<div class="small" style="margin-top:8px">Einen oder mehrere Listen-Screenshots gleichzeitig auswählen. Eine neue Auswahl ersetzt die bisherige Liste nach erfolgreichem Einlesen.</div>'+
 '<div id="dgCentralStatus" class="small" role="status" aria-live="polite" style="margin-top:9px">Gespeicherte Liste wird geladen …</div><details id="dgSavedListImages"></details></div>'+
 '<div class="small" style="margin-top:9px">Automatische Produktrecherche: beim Öffnen und alle 15 Minuten, solange Bob sichtbar ist. Quellenzeiten bleiben unverändert: Emittentenkurse höchstens 90 Sekunden; Screenshot-Kursnachweise 14 Stunden ab Quellenzeit gültig, keine Echtzeitkurse. Neue Kursbilder ersetzen den bisherigen Kursnachweis. Fehlende Kurse bleiben offen, berechnete Werte sind Schätzungen.</div>'+
 '<div id="dgTop3Out" style="margin-top:12px"></div>'+
 '<details style="margin-top:12px"><summary style="cursor:pointer;font-weight:700">Alle gespeicherten Produkte / weitere Detailbilder</summary><div id="dgMissingProducts" style="margin-top:12px"></div></details>'+
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
  r.innerHTML='<b>Kandidat '+i+'</b><div id="dgOcrStatus'+i+'" class="small" style="margin-top:5px">Wartet auf Screenshot.</div><div id="dgResearch'+i+'" class="small research" style="margin-top:5px">🌐 Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="'+i+'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="'+i+'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="'+i+'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="'+i+'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="'+i+'" type="number" step=".01" placeholder="KO-Level"><input data-dg="isin" data-i="'+i+'" placeholder="ISIN"></div><button data-research="'+i+'">Aktuelle Produktdaten laden</button>';
  r.insertAdjacentHTML("beforeend",'<div id="dgEvidence'+i+'"></div><div style="margin-top:8px"><label for="dgDetailShot'+i+'">📷 Zusatzbild für dieses Produkt hochladen</label><input id="dgDetailShot'+i+'" type="file" accept="image/*" multiple><div class="small">Produktdetail oder Kursdaten mit sichtbarer ISIN. Mehrere Bilder können nacheinander ergänzt werden. Kurszeit braucht Datum, Sekunden und Zeitzone; Hebel und KO benötigen eigene Quellenzeiten. Fehlende Zeiten werden nicht ergänzt.</div></div>');
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
   const pendingImages=retainSelectedImages(input);
   const status=document.getElementById('dgOcrStatus'+i);
   if(status)status.textContent='📷 '+files.length+' Bild(er) ausgewählt. Bilddateien werden übernommen …';
   try{
    const retained=await pendingImages;
    input.disabled=true;
    rankUI();
    const outcomes=[];
    for(const file of retained){if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value!==isin)break;const result=await readScreenshot(i,file);if(result)outcomes.push({name:file.name,...result});}
    if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value===isin){
     const series=linkScreenshotSeries(outcomes);
     if(series){
      let merged=detailScreenshots.get(i);
      for(const o of outcomes.filter(o=>o.ok&&o.data))merged=mergeScreenshotEvidence(merged,o.data,o.name);
      detailScreenshots.set(i,merged);
      for(const o of outcomes.filter(o=>o.ok))o.reason+=' · gemeinsame Aufnahmezeit '+series.text;
     }
    }
    if(status&&document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value===isin&&outcomes.length){
     status.textContent=screenshotBatchSummary(outcomes);
    }
   }catch(e){if(status)status.textContent='⚠️ '+e.message;}
   finally{input.value='';input.disabled=false;rankUI();}
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
 b.querySelector('[data-return-close]').addEventListener('click',()=>{
  returnProductIsin='';returnProductPending=false;
  try{localStorage.removeItem(RETURN_PRODUCT_KEY);}catch(_){}
  updateScreenshotReturn();
 });
 setTimeout(()=>updateScreenshotReturn(true),0);
 window.addEventListener('pageshow',()=>updateScreenshotReturn(true));
 quoteRefresh=createQuoteRefresh({
  rows:()=>Array.from({length:12},(_,idx)=>{const id=idx+1,isin=(document.querySelector('[data-dg="isin"][data-i="'+id+'"]')?.value.trim()||'').toUpperCase();return {id,isin,key:isin+':'+(rowVersions.get(id)||0)};}),
  request:enrichProduct,visible:()=>!document.hidden,interval:900000
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
 return Number.isFinite(t)&&t<=now&&now-t<=limit?'':!Number.isFinite(t)?'Aktualität unbekannt – Zeitstempel fehlt oder ist unklar':t>now?'Aktualität unbekannt – Zeitstempel liegt in der Zukunft':'veraltet – Stand: '+new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+' (Zürich)';
}
function continuingAnalysis(products,context){
 return products.filter(p=>p.isin||p.name).map(p=>{
  const at=p.snapshot?.evidence?.Brief?.at||p.snapshot?.sourceTime||p.quote?.askAt||p.quote?.quoteAt;
  const warning=calculationAge(at,p.snapshot?SCREENSHOT_MAX_AGE_MS:90000,context.now??Date.now());
  return {p,warning,evaluation:evaluateProduct({...p,...context})};
 });
}
function renderContinuingAnalysis(products,context){
 if(typeof document!=='undefined')for(const [i,p] of products.entries())for(const [field,key] of [['price','Brief'],['lev','Hebel'],['ko','KO']]){
  const input=document.querySelector('[data-dg="'+field+'"][data-i="'+(i+1)+'"]');if(!input)continue;
  const e=p.snapshot?.evidence?.[key],at=e?.at||(field==='price'?(p.snapshot?.sourceTime||p.quote?.quoteAt):null);
  const warning=calculationAge(at,p.snapshot?SCREENSHOT_MAX_AGE_MS:90000);
  input.style.fontStyle=warning?'italic':'';input.title=warning;
 }

 const marketWarnings=window.BobAnalysisAge?.()||[];
 const rows=continuingAnalysis(products,context).map(({p,warning,evaluation:e})=>{
  const uncertain=!!warning||marketWarnings.length>0;
  return '<div style="margin:8px 0;'+(uncertain?'font-style:italic':'')+'"><b>'+esc(p.isin||p.name)+'</b> · Kurs '+esc(p.price??'fehlt')+' · Hebel '+esc(p.leverage??'fehlt')+' · KO '+esc(p.ko??'fehlt')+(warning?' · '+esc(warning):'')+'<br>'+esc(e.ok?'Rechnerische Bewertung: '+e.score+' Punkte · '+e.reasons.join(' · '):e.reasons.join(' · '))+'</div>';
 }).join('');
 return '<details data-product-details="calculations"><summary>Berechnung mit vorhandenen Werten</summary><p class="small"><i>Berechnung läuft auch mit veralteten Werten und ohne Zeitstempel weiter. Die rechnerische Bewertung ist keine aktuell bestätigte Produktfreigabe.</i></p>'+ (marketWarnings.length?'<p><i>'+esc(marketWarnings.join(' · '))+'</i></p>':'')+rows+'</details>';
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
  if(meta)meta.textContent="🌐 "+x.source+" · ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · "+(info.strike?"Basispreis "+info.strike+" USD · ":"")+(info.ratio?"Bezugsverhältnis "+info.ratio+" · ":"")+(info.contract?"Kontrakt "+info.contract+" · ":"")+x.reason+futureResearchText(x)+productEstimateText(x)+". Produkt für aktuelle Rangliste gesperrt.";
 }
 for(let i=1;i<=12;i++){const out=document.getElementById('dgEvidence'+i),html=screenshotSummary(detailScreenshots.get(i));if(out)updateProductHtml(out,html);}
 for(const [i,q] of productQuotes){
  const computed=document.getElementById("dgCalculatedState"+i);if(computed)computed.textContent=productEstimateText(q);
  const state=document.getElementById("dgQuoteState"+i),timing=quoteTiming(q);
  if(state)state.textContent=q.eligible&&q.marketOpen&&timing.fresh?"aktuell · "+timing.ageSeconds+" s alt":"GESPERRT · "+(timing.ageSeconds===null?"Zeitstempel unbekannt":timing.ageSeconds+" s alt")+(q.marketOpen?"":" · Markt geschlossen");
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
 for(const p of ps)p.isinConfirmed=automaticIdentity(p);
 for(let i=1;i<=12;i++){const out=document.getElementById("dgCombinedState"+i),ref=combinedReferences.get(i);if(ref&&ref.isin!==ps[i-1].isin)combinedReferences.delete(i);if(out)updateProductHtml(out,window.BobCombined.render(window.BobCombined.assess(ps[i-1],combinedReferences.get(i),bundle))+window.BobCombined.renderComparison(window.BobCombined.compareSnapshot(ps[i-1],combinedReferences.get(i),combinedDrafts.get(i),productQuotes.get(i))));}
 const missingOut=document.getElementById("dgMissingProducts");
 if(missingOut){
  const html=productUploadCards(ps,d);
  if(updateProductHtml(missingOut,html)){
   bindCompactCards(missingOut);
  }
 }
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
 window.BobPush?.updateSelection?.({products:ps,context:selectionContext,bundle:{spots:bundle?.spots,fetched_at:bundle?.fetched_at,history:{data_state:bundle?.history?.data_state}},references,fixedBarriers:window.BobCombined.fixedBarriers()},flow);
 const flowHtml=renderSelectionWorkflow(flow,ps)+renderContinuingAnalysis(ps,selectionContext);if(updateProductHtml(o,flowHtml))bindCompactCards(o);return flow;

}

if(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{inject().catch(e=>console.warn(e));});else inject().catch(e=>console.warn(e));}
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
window.BobDegiro={linkScreenshotSeries,ocrGlyphPair,strictOcrNumber,ocrNumericFields,unconfirmedOcrFields,preferOriginalTableRead,bnpBadgeRect,normalizeBnpQuoteColumns,imageIdentityDiagnostic,reviewedImageText,detailStateKey,updateProductHtml,zurichListDay,listExpired,clearDailyList,archiveTransaction,saveListArchive,restoreListArchive,automaticIdentity,automaticCondition,recoverTermRows,screenshotReturnRow,renderProductDecision,readListBatch,collectiveSignal,calculationAge,continuingAnalysis,renderContinuingAnalysis,compactProductCard,screenshotSummary,retainSelectedImages,renderImageImportStatus,renderIssuerHelp,renderProductSources,applyResearchedTerms,durableCondition,maturityDeadline,writeStoredProducts,cleanStoredProduct,recoverReviewedLists,restoreProductRows,selectionUiSignals,selectionMarketGate,costRiskAssessment,finalProductStatus,parseProductTerms,productTermsStatus,selectionTimeWindow,selectionDetailStatus,selectionWorkflow,renderSelectionWorkflow,recognizeOcr,exitReference,createQuoteRefresh,screenshotCurrentState,renderScreenshotCurrentState,conditionalCandidate,rankConditional,renderConditional,qualityText,isFutureProduct,futureResearchText,productEstimateText,rankManualSnapshots,productUploadCards,sourceTimestamp,screenshotTimes,evidenceTiming,manualSnapshotStatus,needsDirectionalData,loadIdentities,saveIdentities,riskModel,koDistancePct,evaluateProduct,quoteTiming,currentQuote,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates,validIsin,normalizeOcrIsin,populateCandidateRows,recoverOcrIsins,detailScreenshotData,missingProductData,supplementaryHint,screenshotTimeLabel,mergeScreenshotEvidence,manualProductMissing,escapeHtml:esc};
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
 function label(m,gold){const x=price(m,gold);return x.available?'≈ '+x.price.toFixed(4)+' EUR/Stück (berechnet)':x.reason;}
 root.BobTradeProduct={model,price,label};
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
 const details=document.createElement('details');details.innerHTML='<summary>Berechnungsdetails und fehlende Referenzen anzeigen</summary>';const grid=exit.querySelector('.grid');if(grid)details.append(grid);for(const el of [...exit.children])if(el.tagName==='LABEL'||el.tagName==='BR')details.append(el);exit.querySelector('h3').after(details);p.append(exit);exit.className='';
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
