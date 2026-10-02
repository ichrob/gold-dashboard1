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
 (q?'<div>Kursnachweis: '+escape(q.source)+' · '+escape(q.venue)+' · Geld '+q.bid.toFixed(4)+' / Brief '+q.ask.toFixed(4)+' EUR · Spread '+q.spread.toFixed(4)+' EUR · '+escape(q.at)+(q.imageSource?' · Bild '+escape(q.imageSource):'')+'</div>':'')+
 (state.basis!==null&&state.basis!==undefined?'<div>'+escape(state.basisLabel)+'</div>':'')+
 (k?'<div>Konservative KO-Schwelle: '+k.value.toFixed(4)+' USD · Quellenabweichung '+k.differenceUsd.toFixed(4)+' USD'+(state.distanceUsd!==null?' · Abstand '+state.distanceUsd.toFixed(2)+' USD / '+state.distancePct.toFixed(2)+'%':'')+'</div>'+k.evidence.map(x=>'<div>KO-Nachweis: '+escape(x.source)+(k.fixed?' · fester Berechnungswert · Bestätigung '+escape(x.confirmedAt)+' (keine Kurszeit)':' · '+escape(x.at)+' · bestätigt gültig bis '+escape(x.validUntil))+'</div>').join(''):'')+
 (e?'<div><b>Schätzung, keine SG-Quotierung:</b> Geld ≈ '+e.bid.toFixed(4)+' / Brief ≈ '+e.ask.toFixed(4)+' EUR · Hebel ≈ '+e.leverage.toFixed(2)+'× · FX-Zeit '+escape(e.fxAt)+'</div><div>'+escape(e.formula)+'</div>':'')+
 state.reasons.map(x=>'<div>Offen: '+escape(x)+'</div>').join('')+
 '<div>Vollständige Bewertungen werden automatisch in der bedingten Top-3 berücksichtigt. Keine Live-Freigabe. Schätzfehler, Preisaufschlag und zwischenzeitliche KO-Berührung unbestätigt. Tatsächlichen DEGIRO-Geld-/Briefkurs vor einer Entscheidung prüfen.</div></div>';
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
   candidate={...p,spot:context.spot,priceKind:'Bestätigter Produktkurs',estimated:false,source:p.quote.source,venue:'Emittenten-Kursquelle',at:p.quote.quoteAt};
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
 return '<div style="padding:14px;background:#fff;border:2px solid #dbe4f0;border-radius:15px"><b>Automatische Top-3 · '+escape(result.direction)+'</b><div class="small">'+escape(result.reason)+' · '+result.total+' passende Produkte</div>'+
 result.candidates.map((p,i)=>'<div style="padding:10px;margin-top:8px;border:1px solid #e1e7f0;border-radius:10px"><b>Platz '+(i+1)+' · '+escape(p.isin)+'</b><div class="small">'+escape(p.name)+' · '+escape(p.productDirection)+'</div><div class="small"><b>'+escape(p.priceKind)+'</b> · Brief '+(p.estimated?'≈ ':'')+p.price.toFixed(4)+' EUR · Hebel '+(p.estimated?'≈ ':'')+p.leverage.toFixed(2)+'× · Spread '+p.spread.toFixed(4)+' EUR</div><div class="small">KO '+p.ko.toFixed(4)+' USD · Abstand '+p.evaluation.koDistancePct.toFixed(2)+'% · technische Passung '+p.evaluation.score+'/100</div><div class="small">Quelle '+escape(p.source)+' · '+escape(p.venue)+' · '+(p.estimated?'Referenzzeit ':'Kurszeit ')+escape(p.at)+'</div><div class="small">Warum: '+escape(p.evaluation.reasons.slice(0,3).join(' · '))+'</div>'+p.evaluation.warnings.map(w=>'<div class="small warning">'+escape(w)+'</div>').join('')+(p.estimated?'<div class="small">Schätzgenauigkeit noch unbestätigt; angenommener Quellenaufschlag und Spread können sich ändern.</div>':'')+'</div>').join('')+
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
 const out={fields:{...(previous?.fields||{})},evidence:{...(previous?.evidence||{})},notes:incoming.notes,delayed:previous?.delayed||false,supplementedTime:previous?.supplementedTime||null};
 const clear=keys=>{for(const key of keys){delete out.fields[key];delete out.evidence[key];}};
 if(incoming.hasQuote){clear(['bid','ask','quoteAt','venue','url','source']);out.delayed=incoming.delayed;out.supplementedTime=incoming.supplementedTime||null;out.fields.source=incoming.source;out.evidence.source=image;}
 if(incoming.fields.ko1)clear(['ko1','koSource1','koUrl1','koAt1','koUntil1']);
 for(const [key,v] of Object.entries(incoming.fields)){if(!incoming.hasQuote&&['url','venue','quoteAt'].includes(key))continue;out.fields[key]=v;out.evidence[key]=image;}
 return out;
}
function compareSnapshot(p,reference,draft,q,now=Date.now()){
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
window.BobCombined={compareSnapshot,renderComparison,fixedFor,saveFixed,removeFixed,assess,render,form,time,rank,renderTop3,screenshotDraft,mergeDraft};
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
function normalizeOcrIsin(value){
 const original=String(value||"").trim().toUpperCase();
 if(validIsin(original))return{isin:original,originalIsin:""};
 // German WKN excludes I/O. Only substitute those confusable glyphs,
 // only for DE000-style identifiers, and accept only a valid checksum.
 // Never infer other digits (such as 9) from an ambiguous OCR character.
 if(!/^DE[0O]{3}[A-Z0-9]{7}$/.test(original))return{isin:original,originalIsin:""};
 const candidate="DE000"+original.slice(5).replace(/O/g,"0").replace(/I/g,"1");
 return validIsin(candidate)?{isin:candidate,originalIsin:original}:{isin:original,originalIsin:""};
}
function koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}
function directionOf(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null)return null;return ko<spot?"LONG":ko>spot?"SHORT":null;}
function riskModel(p){const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);if(spot===null||stop===null||riskEur===null||riskEur<=0)return{ok:false,reason:"Ungültige Eingabedaten für Risiko."};if(fx===null||fx<=0)return{ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};const dist=Math.abs(spot-stop);if(dist<=0)return{ok:false,reason:"Stop-Distanz ist null."};const maxLossUsd=riskEur/fx,approxNotionalUsd=maxLossUsd/(dist/spot),approxNotionalEur=approxNotionalUsd*fx,marginEur=approxNotionalEur/lev,ko=n(p.ko),koPct=koDistancePct(spot,ko),warnings=[];if(ko!==null&&((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");return{ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};}
function technicalQuality(ctx={}){const d=String(ctx.direction||"NEUTRAL").toUpperCase();if(d==="NEUTRAL")return{score:50,reasons:["Kein eindeutiges Richtungsszenario."]};let score=50,reasons=[];const side=v=>{const x=String(v||"").toUpperCase();return x.includes("LONG")||x.includes("BULL")||x.includes("UP")?"LONG":x.includes("SHORT")||x.includes("BEAR")||x.includes("DOWN")?"SHORT":""};const trend=side(ctx.trend),trend2=side(ctx.trend2),mtf=side(ctx.mtf),rsi=Number(ctx.rsi),hist=Number(ctx.hist),adx=Number(ctx.adx),momentum=Number(ctx.momentum);if(trend===d){score+=12;reasons.push("EMA-Trend bestätigt.");}else if(trend&&trend!==d){score-=12;reasons.push("EMA-Trend widerspricht.");}if(trend2===d){score+=10;reasons.push("Langfristtrend bestätigt.");}else if(trend2&&trend2!==d){score-=10;reasons.push("Langfristtrend widerspricht.");}if(mtf===d){score+=15;reasons.push("MTF bestätigt.");}else if(mtf&&mtf!==d){score-=15;reasons.push("MTF widerspricht.");}if(Number.isFinite(rsi)){const support=(d==="LONG"&&rsi>=55&&rsi<=65)||(d==="SHORT"&&rsi>=35&&rsi<=45);const broad=(d==="LONG"&&rsi>=50&&rsi<70)||(d==="SHORT"&&rsi<=50&&rsi>30);if(support){score+=10;reasons.push("RSI liegt im günstigen Trendbereich.");}else if(broad){score+=5;reasons.push("RSI unterstützt die Richtung.");}else if((d==="LONG"&&rsi>75)||(d==="SHORT"&&rsi<25)){score-=10;reasons.push("RSI zeigt erhöhtes Überdehnungsrisiko.");}}if(Number.isFinite(hist)){const h=hist>0?"LONG":hist<0?"SHORT":"";if(h===d){score+=10;reasons.push("MACD-Histogramm bestätigt.");}else if(h&&h!==d){score-=10;reasons.push("MACD-Histogramm widerspricht.");}}if(Number.isFinite(adx)){if(adx>=30){score+=7;reasons.push("ADX zeigt einen starken Trend.");}else if(adx>=20){score+=3;reasons.push("ADX bestätigt vorhandene Trendstärke.");}else if(adx<15){score-=5;reasons.push("ADX zeigt wenig Trendstärke.");}}if(Number.isFinite(momentum)){const m=momentum>0?"LONG":momentum<0?"SHORT":"";if(m===d){score+=8;reasons.push("Momentum bestätigt.");}else if(m&&m!==d){score-=8;reasons.push("Momentum widerspricht.");}}return{score:Math.max(0,Math.min(100,Math.round(score))),reasons};}
const futureIsins=new Set(["DE000FG309G0"]);
function isFutureProduct(p){return p.underlyingType==="FUTURE"||p.quote?.metadata?.underlyingType==="FUTURE"||futureIsins.has(String(p.isin||"").trim().toUpperCase());}
function futureResearchText(x,now=Date.now()){
 const r=x.futureResearch;if(!r)return "";
 const at=v=>typeof v==="string"&&!Number.isNaN(Date.parse(v))?new Date(v).toLocaleString():"unbekannt";
 let text=" · FUTURES-RECHERCHE "+r.contract;
 if(Number.isFinite(r.bid)&&Number.isFinite(r.ask))text+=" · Geld "+r.bid+" / Brief "+r.ask+" EUR · Geldzeit "+at(r.bidAt)+" · Briefzeit "+at(r.askAt);
 if(r.underlyingPriceUsd)text+=" · Futures-Basiswert "+r.underlyingPriceUsd+" USD · Basiswertzeit "+at(r.underlyingAt)+" (verzögert oder Echtzeitstatus unbestätigt)";
 const c=r.calculatedFuture;
 if(c){
  const age=(now-Date.parse(c.priceAt))/1000,refAge=(now-Date.parse(c.referenceAt))/1000;
  if(c.available&&Number.isFinite(c.priceUsd)&&c.priceUsd>0&&age>=0&&age<=60&&refAge>=0&&refAge<=1800){
   text+=" · BERECHNETER FUTURE-KURS: "+Number(c.priceUsd).toFixed(2)+" USD · "+(c.proxySource||"Investing.com CFD")+"-Kurszeit "+at(c.priceAt)+" ("+Math.ceil(age)+" s alt) · echter GCZ26-Referenzkurs "+c.referencePriceUsd+" USD von "+at(c.referenceAt)+" · Zeitversatz "+c.alignmentSeconds+" s"+(c.proxyReferenceKind==="linear-interpolation"?" (Quellenreferenz zeitlich interpoliert)":"")+" · Formel: "+c.formula+" · "+c.note;
  }else{
   const reasons=[];
   if(c.available){
    if(!Number.isFinite(age)||age<0)reasons.push("Schätzungszeit fehlt oder liegt in der Zukunft");
    else if(age>60)reasons.push("Schätzung "+Math.ceil(age)+" s alt (höchstens 60 s)");
    if(!Number.isFinite(refAge)||refAge<0)reasons.push("Future-Referenzzeit fehlt oder liegt in der Zukunft");
    else if(refAge>1800)reasons.push("Future-Referenz "+Math.ceil(refAge/60)+" min alt (höchstens 30 min)");
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
  const r=q?.futureResearch,c=r?.calculatedFuture;
  if(meta?.underlyingType==='FUTURE'&&meta.contract&&meta.contract===r?.contract&&r.contract===c?.contract&&c.available&&n(c.priceUsd)>0&&freshTimes([c.priceAt],now)&&freshTimes([c.referenceAt],now,1800)){
   basis=n(c.priceUsd);basisAt=c.priceAt;basisLabel='Berechneter '+r.contract+'-Kurs (Schätzung, keine Börsen-Echtzeit)';
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
 const status=manualSnapshotStatus(p,shot,now),spread=shot?.currency==='EUR'&&n(shot.bid)>0&&n(shot.ask)>=n(shot.bid)?shot.ask-shot.bid:null;
 out.rows.push({label:'Produktkurse / Nachweise',text:(spread===null?'Kein vollständiges Kursbild':'Screenshot-Spread '+spread.toFixed(4)+' EUR ('+(spread/shot.ask*100).toFixed(3)+'% des Briefs) · '+(shot.sourceTime||'Quellenzeit nicht vollständig belegt'))+' · '+(status.complete?'vollständige Momentaufnahme, keine Live-Verifizierung':status.reasons.join('; '))});
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
 const q=p.quote,fail=reason=>({ok:false,isin:p.isin,reason,scope:isFutureProduct(p)?q?.futureResearch?.contract||q?.metadata?.contract||"FUTURE":"XAU/USD",direction:isFutureProduct(p)?q?.futureResearch?.direction:q?.productModel?.direction||q?.direction||p.productDirection});
 if(!q||q.isin!==p.isin||!validIsin(p.isin)||p.isinConfirmed!==true)return fail("ISIN oder Produktidentität nicht bestätigt");
 let basis,ask,bid,ko,strike,ratio,fx,errorPrice=0,errorBasis=0,scope,ctx,quality,priceKind,at;
 if(isFutureProduct(p)){
  const r=q.futureResearch,c=r?.calculatedFuture,a=r?.contractAnalysis;
  if(!q.productVerified||q.metadata?.underlyingType!=="FUTURE"||q.metadata.contract!==r?.contract||r?.contract!==c?.contract||r?.contract!==a?.contract)return fail("Futures-Kontrakt nicht vollständig bestätigt");
  if(!c.available||!c.validation?.ready||c.validation.sampleCount<20)return fail("Future-Schätzung: Genauigkeit noch nicht ausreichend gemessen");
  if(!a.available||!["LONG","SHORT"].includes(a.direction)||a.technicalSourceFamilies!==1||!Object.values(a.frames||{}).every(f=>f.available)||Object.keys(a.frames||{}).length!==4||!freshTimes([a.checkedAt],now,180)||!Number.isFinite(Date.parse(a.expiresAt))||now>Date.parse(a.expiresAt))return fail("ABWARTEN: eigene Kontrakt-MTF fehlt, ist uneinheitlich oder veraltet");
  if(!r.marketOpen||!Number.isFinite(Date.parse(r.tradingEndAt))||now>Date.parse(r.tradingEndAt)||!freshTimes([r.bidAt,r.askAt,r.fxDataAt,r.fxEffectiveAt,c.priceAt],now)||!freshTimes([c.referenceAt],now,1800))return fail("Future-, Produkt- oder FX-Daten nicht aktuell");
  const times=[r.bidAt,r.askAt,r.fxDataAt,r.fxEffectiveAt,c.priceAt].map(Date.parse);
  if(Math.max(...times)-Math.min(...times)>15000)return fail("Future- und Produktdaten zeitlich zu weit auseinander");
  basis=n(c.priceUsd);ask=n(r.ask);bid=n(r.bid);ko=n(r.ko);strike=n(r.strike);ratio=n(r.ratio);fx=n(r.usdEur);errorBasis=n(c.comparisonErrorUsd);
  if(!(errorBasis>=Math.max(.1,n(c.validation.maxAbsoluteError)||0)))return fail("Gemessene Future-Abweichung fehlt");
  if(r.direction!==a.direction)return fail("Produkt passt nicht zum eigenen Futures-Szenario");
  const timing=n(a.frames['5m'].ema20);
  if(timing===null||a.direction==="LONG"&&basis-errorBasis<=timing||a.direction==="SHORT"&&basis+errorBasis>=timing)return fail("ABWARTEN: berechnete Kursspanne bestätigt das Kontrakt-Timing nicht eindeutig");
  scope=r.contract;priceKind="Bestätigter Produktkurs · berechneter Basiswert";quality=c.validation;at=c.priceAt;
  ctx={direction:a.direction,trend:a.frames['1h'].trend,trend2:a.frames['1h'].ema50>a.frames['1h'].ema200?"LONG":"SHORT",mtf:a.direction,rsi:a.rsi,hist:a.macdHistogram,momentum:a.macdHistogram,atr:a.atr};
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
 const lev=(u,price)=>ratio>0&&fx>0?u*fx*ratio/price:n(q.leverage);
 const evaluations=[];
 for(const u of [basis-errorBasis,basis+errorBasis])for(const price of [ask-errorPrice,ask+errorPrice]){
  const e=evaluateProductCore({...p,...ctx,spot:u,ko,price,productDirection:direction,leverage:lev(u,price),spread:ask-bid+2*errorPrice});
  if(!e.ok||!e.fit||e.direction!==ctx.direction||e.setupScore<35||e.conflictCount>=3)return fail("ABWARTEN: Passung oder KO-Puffer innerhalb der beobachteten Fehlerspanne nicht stabil");
  evaluations.push(e);
 }
 return {ok:true,isin:p.isin,name:p.name||p.isin,scope,direction:ctx.direction,priceKind,
  price:ask,priceError:errorPrice,basis,basisError:errorBasis,quality,at,
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
  const best=candidates[0],unresolved=excluded.some(c=>(c.scope===best.scope||c.scope==="FUTURE"&&best.scope!=="XAU/USD")&&(!c.direction||c.direction===best.direction)),unique=!unresolved&&(candidates.length===1||best.scoreLow>Math.max(...candidates.slice(1).map(c=>c.scoreHigh))+2);
  return {scope,candidates,favorite:unique?best:null,reason:unique?"Bedingter Favorit unter ausreichend geprüften Kandidaten – aktuellen DEGIRO-Briefkurs vor Einstieg prüfen":"ABWARTEN: Vergleichsdaten fehlen oder kein eindeutiger Favorit innerhalb der beobachteten Fehlerspannen"};
 });
 return {groups:results,excluded,tradeable:false,needsDegiroCheck:true};
}
function renderConditional(result){
 const rows=result.groups.map(g=>'<div style="margin-top:10px"><b>'+esc(g.scope)+' · '+(g.favorite?'Bedingter Favorit: '+esc(g.favorite.isin):'ABWARTEN')+'</b><div class="small">'+esc(g.reason)+'</div>'+g.candidates.slice(0,3).map(c=>'<div class="small" style="margin-top:8px"><b>'+esc(c.isin)+'</b> · '+esc(c.priceKind)+' · Kurs ca. '+c.price.toFixed(2)+' EUR'+(c.priceError?' · Vergleichsspanne ±'+c.priceError.toFixed(4)+' EUR':'')+' · Basiswert '+c.basis.toFixed(2)+' USD'+(c.basisError?' ±'+c.basisError.toFixed(2)+' USD':'')+'<br>Technische Passung '+c.scoreLow+'–'+c.scoreHigh+'/100 · Hebel ca. '+c.leverageLow.toFixed(2)+'–'+c.leverageHigh.toFixed(2)+'× · KO-Abstand mindestens '+c.koDistanceMinPct.toFixed(2)+'% innerhalb der Vergleichsspanne · Datenzeit '+esc(new Date(c.at).toLocaleTimeString())+(c.quality?'<br>'+esc(qualityText(c.quality,c.priceError?'EUR':'USD')):'')+'</div>').join('')+'</div>').join('');
 const waiting=result.excluded.map(x=>'<div class="small">'+esc(x.isin)+' · '+esc(x.reason)+'</div>').join('');
 return '<div style="padding:14px;background:#fff;border:1px solid #dbe4f0;border-radius:15px"><b>Bedingter Produktvergleich</b><div class="small">Unterschiedliche Basiswerte werden getrennt bewertet. Beobachtete Fehlerspannen sind keine garantierten Grenzen.</div>'+(rows||'<div class="warning">ABWARTEN – noch kein ausreichend geprüfter Kandidat.</div>')+waiting+'<div class="small" style="margin-top:9px">Vor Einstieg den aktuellen DEGIRO-Briefkurs und die Produktbedingungen prüfen. Keine automatische Handelsfreigabe.</div></div>';
}
function evaluateProduct(p){if(isFutureProduct(p))return{ok:false,fit:false,score:0,reasons:["Gold-Future benötigt eigene Basiswertdaten und Trendprüfung; keine XAU/USD-Spot-Freigabe."],warnings:[]};return evaluateProductCore(p);}
function evaluateProductCore(p){const spot=n(p.spot),ko=n(p.ko),lev=Math.max(1,n(p.leverage)||1),spread=Math.max(0,n(p.spread)||0),atr=n(p.atr),requested=String(p.direction||"NEUTRAL").toUpperCase(),productDirection=String(p.productDirection||directionOf(spot,ko)||"").toUpperCase(),reasons=[],warnings=[];if(spot===null||spot<=0)return{ok:false,fit:false,score:0,reasons:["Kein gültiger XAU/USD-Preis."],warnings:[]};if(!productDirection||!["LONG","SHORT"].includes(productDirection))reasons.push("Richtung des Produkts fehlt.");if(requested!=="NEUTRAL"&&productDirection&&requested!==productDirection)reasons.push("Produkt-Richtung passt nicht zum aktuellen Bob-Szenario.");if(ko!==null&&((productDirection==="LONG"&&ko>=spot)||(productDirection==="SHORT"&&ko<=spot)))return{ok:false,fit:false,score:0,reasons:["KO-Level liegt am oder jenseits des aktuellen Goldpreises – Produkt gesperrt."],warnings:[]};if(ko===null)warnings.push("KO-Level fehlt – KO-Abstand kann nicht geprüft werden.");const koPct=koDistancePct(spot,ko),koDistance=ko===null?null:Math.abs(spot-ko),atrMultiple=koDistance!==null&&atr!==null&&atr>0?koDistance/atr:null;if(koPct!==null&&koPct<2)warnings.push("KO-Abstand unter 2%.");if(koPct!==null&&koPct<1)warnings.push("KO-Abstand unter 1% – sehr enger Puffer.");if(atrMultiple!==null&&atrMultiple<1.5)warnings.push("KO-Puffer kleiner als 1,5 ATR.");if(atrMultiple!==null&&atrMultiple<1)warnings.push("KO-Puffer kleiner als 1 ATR – sehr eng.");if(lev>10)warnings.push("Hebel über 10× – sehr hohe Empfindlichkeit.");if(spread>0)reasons.push("Spread wurde berücksichtigt.");let productScore=100;if(requested!=="NEUTRAL"&&productDirection!==requested)productScore-=60;if(!productDirection)productScore-=20;if(ko===null)productScore-=20;if(koPct!==null&&koPct<2)productScore-=20;if(koPct!==null&&koPct<1)productScore-=20;if(atrMultiple!==null&&atrMultiple<1.5)productScore-=15;if(atrMultiple!==null&&atrMultiple<1)productScore-=20;if(lev>10)productScore-=15;if(spread>0)productScore-=Math.min(10,spread);const quality=technicalQuality(p);const score=Math.round(productScore*0.45+quality.score*0.55);const fit=productScore>=60&&!reasons.some(x=>x.includes("passt nicht"));const conflictCount=quality.reasons.filter(x=>x.includes("widerspricht")).length;const confirmationCount=quality.reasons.filter(x=>x.includes("bestätigt")||x.includes("unterstützt")||x.includes("günstigen")||x.includes("Momentum")).length;if(conflictCount>=3){warnings.push("Mehrere technische Signale widersprechen der Richtung.");}if(requested!=="NEUTRAL"&&quality.score<35){warnings.push("Setup-Qualität sehr niedrig – kein starker technischer Konsens.");}const confidence=Math.max(0,Math.min(100,Math.round(quality.score-(conflictCount*5))));return{ok:true,fit,score:Math.max(0,Math.round(score)),direction:productDirection,koDistancePct:koPct,koDistance,atrMultiple,leverage:lev,reasons:reasons.concat(quality.reasons),warnings,productScore,setupScore:quality.score,confidence,conflictCount,confirmationCount};}
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
 return !isFutureProduct(p)&&!!q&&q.priceKind!=="calculated"&&q.found&&q.eligible===true&&q.marketOpen&&quoteTiming(q,now).fresh&&q.currency==="EUR"&&q.isin===String(p.isin||"").toUpperCase()&&validIsin(p.isin)&&q.price===p.price&&q.leverage===p.leverage&&q.ko===p.ko&&q.spread===p.spread&&q.direction===p.productDirection&&p.isinConfirmed===true;
}
function rankProducts(products,context={}){const scenario=String(context.direction||"NEUTRAL").toUpperCase();if(scenario==="NEUTRAL")return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Momentum ist NEUTRAL – Bob empfiehlt kein DEGIRO-Produkt."};if(context.requireFreshQuotes&&context.spotFresh!==true)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Goldpreis veraltet oder Kurszeit unbekannt – aktuelle Rangliste gesperrt."};const valid=(products||[]).map((p,i)=>Object.assign({_index:i},p)).filter(p=>String(p.name||p.isin||"").trim()&&n(p.spot)>0&&(!context.requireFreshQuotes||currentQuote(p,context.now??Date.now()))).map(p=>Object.assign(p,{evaluation:evaluateProduct(Object.assign({},p,context))})).filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.direction===scenario).sort((a,b)=>b.evaluation.score-a.evaluation.score);if(context.requireFreshQuotes&&!valid.length)return{scenario,candidates:[],total:0,tradeable:false,gateReason:"Keine passenden, bestätigten Produkte mit höchstens 90 Sekunden alten Emittentenkursen für eine Live-Rangliste. Screenshot-Momentaufnahmen werden getrennt geprüft. ISIN unter Details prüfen; veraltete oder fehlende Daten sind gesperrt."};const best=valid[0]?.evaluation;const setupGate=!!best&&(best.setupScore>=35&&best.conflictCount<3);const p=valid[0];const complete=!!p&&n(p.price)>0&&n(p.leverage)>=1&&n(p.ko)>0&&n(p.spread)!==null&&n(p.spread)>=0&&(!p.isin||validIsin(p.isin));return{scenario,candidates:valid.slice(0,4),total:valid.length,tradeable:setupGate&&complete,gateReason:!setupGate?"Technischer Konsens zu schwach oder zu widersprüchlich – kein Favorit.":!complete?"Produktdaten unvollständig oder ISIN ungültig – Kurs, Hebel, KO und Spread unter Details prüfen und ergänzen.":""};}
function scenario(){if(window.BobSession?.expired())return "NEUTRAL";const s=typeof window.confirmedSignalDirection==="function"?window.confirmedSignalDirection():null;if(s&&["LONG","SHORT","NEUTRAL"].includes(String(s).toUpperCase()))return String(s).toUpperCase();const t=String(document.getElementById("signal")?.textContent||"").toUpperCase();return t.includes("LONG")?"LONG":t.includes("SHORT")?"SHORT":"NEUTRAL";}
function spot(){const x=n(window.lastPrice);if(x)return x;const m=String(document.getElementById("price")?.textContent||"").match(/[0-9]+(?:[.,][0-9]+)?/);return m?n(m[0].replace(",",".")):null;}
function atr(){return n(window.A?.at)||n(window.A?.atr)||null;}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
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
   const s=document.getElementById(statusId||"");
   if(!s||!m)return;
   if(m.status==="loading language traineddata")s.textContent="📦 OCR-Sprachdaten werden geladen …";
   else if(m.status==="recognizing text"&&m.progress)s.textContent="📷 OCR "+Math.round(m.progress*100)+"%";
  }
 });
 ocrWorkerPromise=ocrTimeout(initializing,60000,"OCR-Engine konnte nicht innerhalb von 60 Sekunden gestartet werden").catch(e=>{ocrWorkerPromise=null;initializing.then(w=>w.terminate()).catch(()=>{});throw e;});
 return ocrWorkerPromise;
}
async function prepareOcrImage(file,statusId,isinPass=false){
 const status=document.getElementById(statusId||"");
 try{
  const bitmap=await createImageBitmap(file);
  const maxSide=isinPass?3200:1800,scale=Math.min(isinPass?2:1,maxSide/Math.max(bitmap.width,bitmap.height),Math.sqrt(4500000/(bitmap.width*bitmap.height)));
  const canvas=document.createElement("canvas");canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
  const ctx=canvas.getContext("2d",{alpha:false});if(isinPass)ctx.imageSmoothingEnabled=false;ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();
  if(status)status.textContent="🖼️ Screenshot für OCR optimiert …";
  return await new Promise((resolve,reject)=>canvas.toBlob(x=>x?resolve(x):reject(new Error("Bildaufbereitung fehlgeschlagen")),isinPass?"image/png":"image/jpeg",0.86));
 }catch(e){return file;}
}
function recoverOcrIsins(primary,secondary){
 const candidates=Array.from(new Set((String(secondary||"").toUpperCase().match(/DE[0OCD]{3}[A-Z0-9]{6}[0-9](?![A-Z0-9])/g)||[]).map(x=>"DE000"+x.slice(5)).filter(validIsin))),corrections={};
 const text=String(primary||"").replace(/\bDE[0O]{3}[A-Z0-9]{7}\b/g,raw=>{
  if(validIsin(normalizeOcrIsin(raw).isin))return raw;
  const matches=candidates.filter(candidate=>{
   let differences=0;
   for(let i=0;i<12;i++){if(raw[i]===candidate[i])continue;
    if(i>=2&&i<5&&raw[i]==="O"&&candidate[i]==="0")continue;
    if(i>=5&&((raw[i]==="O"&&/[09]/.test(candidate[i]))||(raw[i]==="I"&&/[19]/.test(candidate[i])))){differences++;continue;}
    return false;
   }
   return differences>0&&differences<=2;
  });
  if(matches.length!==1)return raw;
  corrections[matches[0]]=raw;return matches[0];
 });
 return{text,corrections};
}
function recognizeOcr(file,statusId){
 const job=ocrQueue.then(async()=>{
  const worker=await loadOcrWorker(statusId);
  const prepared=await prepareOcrImage(file,statusId);
  let result;
  try{
   result=await ocrTimeout(worker.recognize(prepared),45000,"OCR-Zeitüberschreitung nach 45 Sekunden");
  }catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});throw e;}
  if(parseScreenshotCandidates(result.data.text||"").some(x=>!validIsin(x.isin))){
   let secondaryFailed=false;
   try{
    const status=document.getElementById(statusId||"");if(status)status.textContent="🔎 Unsichere ISINs werden mit einem zweiten Lesedurchgang geprüft …";
    const enlarged=await prepareOcrImage(file,statusId,true);
    await worker.setParameters({tessedit_pageseg_mode:"11",tessedit_char_whitelist:"0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"});
    const second=await ocrTimeout(worker.recognize(enlarged),45000,"ISIN-Zweitlesung nach 45 Sekunden beendet");
    const recovered=recoverOcrIsins(result.data.text,second.data.text);
    result.data.text=recovered.text;result.data.isinRecoveries=recovered.corrections;
   }catch(e){secondaryFailed=true;ocrWorkerPromise=null;await worker.terminate().catch(()=>{});console.warn("[BOB] ISIN-Zweitlesung",e&&e.message?e.message:e);}
   finally{try{if(!secondaryFailed)await worker.setParameters({tessedit_pageseg_mode:"3",tessedit_char_whitelist:""});}catch(e){ocrWorkerPromise=null;await worker.terminate().catch(()=>{});}}
  }
  return result;
 });
 ocrQueue=job.catch(()=>{});
 return job;
}
function ocrExtract(text){
 const raw=String(text||"").replace(/\r/g," ");
 const upper=raw.toUpperCase();
 const ident=normalizeOcrIsin((raw.match(/\b[A-Z]{2}[A-Z0-9]{10}\b/)||[])[0]||"");
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
  productQuotes.delete(i);futureResearchQuotes.delete(i);detailScreenshots.delete(i);rowVersions.set(i,(rowVersions.get(i)||0)+1);
  combinedReferences.delete(i);combinedDrafts.delete(i);
  resetCombinedForm(i);
  const upload=document.getElementById("dgDetailShot"+i);if(upload)upload.value="";
  const confirmed=document.querySelector('[data-dg="confirmed"][data-i="'+i+'"]');if(confirmed)confirmed.checked=false;
  const status=document.getElementById("dgOcrStatus"+i),research=document.getElementById("dgResearch"+i);
  if(research)research.textContent="🌐 Zusatzdaten: warten auf ISIN.";
  if(status)status.textContent=!x?"Wartet auf Screenshot.":!validIsin(x.isin)?"⚠️ ISIN unsicher: "+(x.isin||"nicht erkannt")+". Bitte direkt am Screenshot korrigieren; Produkt bleibt gesperrt.":x.ocrRecovery?"⚠️ OCR-Zweitlesung: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Am Screenshot prüfen und bestätigen.":x.originalIsin?"⚠️ OCR normalisiert: "+x.originalIsin+" → "+x.isin+" (Prüfziffer gültig). Bitte am Screenshot prüfen.":"✅ Aus Screenshot erkannt – ISIN am Screenshot prüfen und bestätigen.";
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
 try{
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),35000);
  let res;try{res=await fetch("/api/degiro/enrich?isin="+encodeURIComponent(isin),{cache:"no-store",signal:ctl.signal});}finally{clearTimeout(timer);}
  if(!res.ok)throw Error("Produktrecherche nicht verfügbar");
  const x=await res.json();
  if((rowVersions.get(i)||0)!==version||(field("isin")?.value.trim()||"").toUpperCase()!==isin)return;
  productQuotes.delete(i);
  futureResearchQuotes.delete(i);
  if(x.isin===isin&&(x.futureResearch||!x.found&&x.calculatedProduct))futureResearchQuotes.set(i,x);
  if(x.isin===isin&&x.productVerified&&x.metadata?.underlyingType==="FUTURE")futureIsins.add(isin);
  if(x.isin===isin&&x.productVerified&&x.metadata){
   if(["LONG","SHORT"].includes(x.metadata.direction)&&field("dir"))field("dir").value=x.metadata.direction;
   if(n(x.metadata.ko)>0&&field("ko"))field("ko").value=x.metadata.ko;
  }
  if(x.found&&x.isin===isin){
   productQuotes.set(i,x);
   for(const [key,val] of Object.entries({price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread,dir:x.direction})){if(field(key))field(key).value=val;}
   if(meta)meta.innerHTML="🌐 "+esc(x.source)+" · Geld "+esc(x.bid)+" / Brief "+esc(x.ask)+" EUR · Spread "+esc(x.spread)+" EUR ("+esc(x.spreadPct)+"%) · Hebel "+esc(Number(x.leverage).toFixed(2))+"×"+(x.leverageEstimated?" (rechnerische Näherung)":"")+" · Kurszeit "+esc(new Date(x.quoteAt).toLocaleString())+" · "+'<span id="dgQuoteState'+i+'">'+(x.eligible?"aktuell":"GESPERRT: "+esc(x.reason))+'</span>'+". Ausführbarer DEGIRO-Kurs kann abweichen."+(x.leverageNote?" "+esc(x.leverageNote):"")+ '<span id="dgCalculatedState'+i+'">'+esc(productEstimateText(x))+'</span>';
  }else if(meta){
   const info=x.productVerified&&x.metadata;
   meta.textContent="🌐 "+(x.source?x.source+" · ":"")+(info?"ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · ":"")+(x.reason||"Keine verlässlich datierten Emittentenkurse verfügbar")+futureResearchText(x)+productEstimateText(x)+". Produkt für aktuelle Rangliste gesperrt.";
  }
 }catch(e){productQuotes.delete(i);futureResearchQuotes.delete(i);if(meta)meta.textContent="🌐 Recherche nicht erreichbar: Produkt für aktuelle Rangliste gesperrt.";}
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
 const out={};
 for(const [key,label] of Object.entries({quote:'Kurszeit|Kursstand|Quote time',bid:'Geldzeit|Bid time',ask:'Briefzeit|Ask time',leverage:'Hebelzeit|Leverage time',ko:'KO-Zeit|KO time'})){
  const matches=Array.from(String(raw).matchAll(new RegExp('(?:^|\\n)\\s*(?:'+label+')\\s*[:=]?\\s*([^\\n]+)','gi')));
  // Multiple conflicting labels are ambiguous. A minute-only time cannot prove 60s.
  out[key]=matches.length===1?{present:true,text:matches[0][1].trim(),at:sourceTimestamp(matches[0][1])}:{present:matches.length>0,text:'',at:null};
 }
 return out;
}
function evidenceTiming(e,now=Date.now()){
 const at=e?.at,parsed=typeof at==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(at)?Date.parse(at):NaN;
 const age=now-parsed;
 return{fresh:Number.isFinite(age)&&age>=0&&age<=60000,ageSeconds:Number.isFinite(age)?Math.ceil(age/1000):null};
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
 if(p.isinConfirmed!==true)reasons.push('Erkannte Werte und Quellenzeiten am Original bestätigen');
 if(x?.currency!=='EUR'||!(n(x?.bid)>0)||!(n(x?.ask)>=n(x?.bid)))reasons.push('Geld und Brief in EUR fehlen');
 const pairs={Geld:x?.bid,Brief:x?.ask,Spread:p.spread,Hebel:p.leverage,KO:p.ko};
 for(const [key,value] of Object.entries(pairs)){
  if(n(value)===null||n(e[key]?.value)!==n(value)||!evidenceTiming(e[key],now).fresh)reasons.push(key+': eigener Zeitnachweis fehlt oder älter als 60 Sekunden');
 }
 if(n(p.price)!==n(x?.ask)||!(n(p.leverage)>=1)||!(n(p.ko)>0)||n(p.spread)===null||Math.abs(n(p.spread)-(n(x?.ask)-n(x?.bid)))>0.000001)reasons.push('Produktwerte unvollständig oder widersprüchlich');
 if(x?.delayed)reasons.push('Bild weist auf verzögerte Kurse hin');
 return{complete:reasons.length===0,reasons,liveVerified:false};
}
function rankManualSnapshots(products,context={}){
 const scenario=String(context.direction||'NEUTRAL').toUpperCase(),now=context.now??Date.now();
 if(!['LONG','SHORT'].includes(scenario)||context.spotFresh!==true)return{candidates:[],total:0,liveVerified:false};
 const candidates=(products||[]).filter(p=>p.productDirection===scenario&&!currentQuote(p,now)&&manualSnapshotStatus(p,p.snapshot,now).complete)
  .map(p=>({...p,evaluation:evaluateProduct({...p,...context})}))
  .filter(p=>p.evaluation.ok&&p.evaluation.fit&&p.evaluation.setupScore>=35&&p.evaluation.conflictCount<3)
  .sort((a,b)=>b.evaluation.score-a.evaluation.score);
 return{candidates,total:candidates.length,liveVerified:false};
}
function productUploadCards(products,direction,now=Date.now()){
 const cards=(products||[]).map((p,z)=>({p,i:z+1})).filter(({p})=>p.name||p.isin);
 cards.sort((a,b)=>Number(b.p.productDirection===direction)-Number(a.p.productDirection===direction));
 if(!cards.length)return '<div class="small">Zuerst eine DEGIRO-Produktliste hochladen. Danach erscheint für jedes erkannte Produkt ein eigener Bild-Upload.</div>';
 const requested=cards.filter(({p})=>needsDirectionalData(p,direction));
 const requestHtml=requested.length?'<div style="padding:10px;border:1px solid #e1e7f0;border-radius:12px;margin-bottom:10px"><b>Weitere Screenshots benötigt · '+esc(direction)+'</b>'+requested.map(({p,i})=>'<div class="small" style="margin-top:6px"><b>ISIN '+esc(p.isin||'unklar')+'</b> · '+esc(Array.from(new Set([...missingProductData(p),...manualSnapshotStatus(p,p.snapshot,now).reasons])).join(' · '))+' <button data-detail-upload="'+i+'">Bilder ergänzen</button></div>').join('')+'</div>':'';
 return requestHtml+'<b>📷 Gespeicherte Produkte · Bilder ergänzen</b><div class="small">'+(['LONG','SHORT'].includes(direction)?'Passende '+esc(direction)+'-Produkte stehen zuerst.':'ABWARTEN: Bilder können ergänzt werden; es gibt keine Produktempfehlung.')+'</div>'+cards.map(({p,i})=>{
  const state=manualSnapshotStatus(p,p.snapshot,now),live=currentQuote(p,now),issuerData=currentQuote({...p,isinConfirmed:true},now);
  const missing=issuerData?(p.isinConfirmed?[]:["ISIN und Produktzuordnung am Original bestätigen"]):live||state.complete?[]:Array.from(new Set([...missingProductData(p),...state.reasons]));
  return '<div style="margin-top:8px;padding:10px;background:#fff;border:1px solid #e1e7f0;border-radius:12px"><b>'+esc(p.isin||p.name)+'</b> · '+esc(p.productDirection||'Richtung unklar')+
   '<div class="small">'+esc(p.name||'')+'</div><div class="small">'+(issuerData?'Datierte Emittentendaten vorhanden; '+(p.isinConfirmed?'DEGIRO-Ausführungskurs prüfen.':'ISIN und Produktzuordnung am Original bestätigen.'):state.complete?'Zeitlich vollständige Momentaufnahme · keine Live-Freigabe.':'Fehlt / prüfen: '+esc(missing.join(' · ')))+'</div>'+
   '<div class="small">Zwei Screenshots pro ISIN möglich: Kursbild und Produktdetails gemeinsam auswählen oder nacheinander ergänzen. Beide müssen die ISIN zeigen.</div><button data-detail-upload="'+i+'">Screenshots für dieses Produkt hinzufügen</button> <button data-card-research="'+i+'">Internetrecherche erneut prüfen</button><label class="small" style="display:block"><input data-card-confirm="'+i+'" type="checkbox" '+(p.isinConfirmed?'checked':'')+'> ISIN, Werte und Quellenzeiten am Original geprüft</label>'+
   screenshotSummary(p.snapshot)+renderScreenshotCurrentState(p,window.liveBundleCache,now)+'<div class="small">'+esc(document.getElementById('dgOcrStatus'+i)?.textContent||'')+'</div><div class="small">'+esc(supplementaryHint(missing))+'</div></div>';
 }).join('');
}
const IDENTITY_KEY='bobDegiroIdentitiesV1';
function saveIdentities(){
 try{const items=[];for(let i=1;i<=12;i++){const read=k=>document.querySelector('[data-dg="'+k+'"][data-i="'+i+'"]')?.value||'';if(validIsin(read('isin')))items.push({isin:read('isin').toUpperCase(),name:read('name'),direction:read('dir')});}localStorage.setItem(IDENTITY_KEY,JSON.stringify(items));}catch(_){}
}
function loadIdentities(){
 try{const items=JSON.parse(localStorage.getItem(IDENTITY_KEY)||'[]');return Array.isArray(items)?items.filter(x=>x&&validIsin(x.isin)).slice(0,12).map(x=>({isin:x.isin,name:String(x.name||x.isin),direction:['LONG','SHORT'].includes(x.direction)?x.direction:'',ko:window.BobCombined.fixedFor({isin:x.isin,productDirection:x.direction})?.value??''})):[];}catch(_){return [];}
}
function needsDirectionalData(p,direction){
 return ['LONG','SHORT'].includes(direction)&&p.productDirection===direction&&!currentQuote({...p,isinConfirmed:true})&&!manualSnapshotStatus(p,p.snapshot).complete;
}

function detailScreenshotData(text,expectedIsin){
 const raw=String(text||""),ids=Array.from(new Set(parseScreenshotCandidates(raw).map(x=>x.isin)));
 if(!validIsin(expectedIsin))return{ok:false,reason:"Bitte zuerst die ISIN dieses Produkts am Screenshot prüfen und korrigieren."};
 if(ids.length!==1||ids[0]!==expectedIsin)return{ok:false,reason:ids.length?"Der Screenshot gehört nicht eindeutig zu "+expectedIsin+". Bitte nur dieses Produkt mit sichtbarer ISIN hochladen.":"ISIN im Zusatzbild fehlt. Bitte die ISIN zusammen mit den Produktdaten zeigen."};
 const x=ocrExtract(raw.replace(/(\bBAR\s*\n)[@©●•®]\s*(?=[0-9])/gi,"$1"));
 if(!x.price){const top=raw.match(/(?:^|\n)\s*€\s*([0-9]+(?:[.,][0-9]+)?)\b/);if(top)x.price=top[1].replace(",",".");}
 const amount=label=>{const m=raw.match(new RegExp("\\b(?:"+label+")(?!\\s*(?:Vol|Volumen))\\s*[:=]?\\s*(?:€|EUR)?\\s*([0-9]+(?:[.,][0-9]+)?)","i"));return m?Number(m[1].replace(",",".")):null;};
 const draft=window.BobCombined.screenshotDraft(raw,expectedIsin);
 if(draft.hasQuote&&!draft.paired)return{ok:false,reason:'Kursbild nicht eindeutig: bitte Geld und Brief eines einzigen Handelsplatzes mit ISIN zeigen.'};
 const bid=draft.paired?n(draft.fields.bid):amount("Geld|Bid"),ask=draft.paired?n(draft.fields.ask):amount("Brief|Ask");
 if(draft.fields.ko1)x.ko=draft.fields.ko1;
 if((bid!==null&&bid<=0)||(ask!==null&&ask<=0)||(bid!==null&&ask!==null&&ask<bid))return{ok:false,reason:"Geld-/Briefkurse widersprüchlich gelesen. Bitte ein schärferes Bild hochladen."};
 const stamp=(raw.match(/\b\d{2}[/.]\d{2}[/.]\d{4}\s+\d{2}:\d{2}(?::\d{2})?\b/)||[])[0]||"";
 const currency=/\bEUR\b|€/.test(raw)?"EUR":"";
 if(bid!==null&&ask!==null&&currency==="EUR"){x.price=String(ask);x.spread=String(Math.round((ask-bid)*1000000)/1000000);}
 if(!x.leverage){const lv=raw.match(/\bLV\s+(\d+(?:[.,]\d+)?)/i);if(lv)x.leverage=lv[1].replace(",",".");}
 return{ok:true,...x,bid,ask,currency,sourceTime:stamp,times:screenshotTimes(raw),delayed:/verzögert|delayed/i.test(raw),combinedDraft:draft};
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
 if(status)status.textContent="📷 Zusatzbild für "+expected+" wird kostenlos im Browser gelesen …";
 try{
  const result=await recognizeOcr(file,"dgOcrStatus"+i);
  if((rowVersions.get(i)||0)!==version||(field("isin")?.value||"").trim().toUpperCase()!==expected)return;
  const x=detailScreenshotData(result.data.text,expected);
  if(!x.ok){if(status)status.textContent="⚠️ "+x.reason;return;}
  productQuotes.delete(i);
  for(const [k,v] of Object.entries({dir:x.direction,price:x.price,lev:x.leverage,ko:x.ko,spread:x.spread})){if(v!==""&&v!==null&&v!==undefined&&field(k))field(k).value=v;}
  const merged=mergeScreenshotEvidence(detailScreenshots.get(i),x,file.name);
  if(merged.clearSpread&&field("spread"))field("spread").value="";
  detailScreenshots.set(i,merged);if(field("confirmed"))field("confirmed").checked=false;
  prefillCombinedForm(i,x.combinedDraft,file.name);
  if(status)status.textContent="✅ Zusatzbild zugeordnet. Gelesene Werte unter Details am Screenshot prüfen. "+(merged.sourceTime?"Kurszeit im Bild: "+merged.sourceTime:"Kurszeit im Bild fehlt.");
  const meta=document.getElementById("dgResearch"+i);if(meta)meta.textContent="📷 "+(x.combinedDraft?.source||'Screenshot')+"-Momentaufnahme · "+(merged.bid!==null?"Geld "+merged.bid+" / Brief "+(merged.ask??"fehlt")+" "+merged.currency+" · ":"")+"keine laufenden Live-Daten. Erkannte Kursnachweis-Felder am Original prüfen und bestätigen; offene Zeiten bleiben gesperrt.";
  rankUI();
 }catch(e){if((rowVersions.get(i)||0)!==version)return;if(status)status.textContent="⚠️ Zusatzbild konnte nicht gelesen werden. Bitte erneut versuchen oder die Angaben unter Details ergänzen.";}
}
function mergeScreenshotEvidence(previous,x,source){
 previous=previous||{};
 const evidence={...(previous.evidence||{})};
 const hasQuote=n(x.price)!==null||x.bid!==null&&x.bid!==undefined||x.ask!==null&&x.ask!==undefined;
 // Keep the original quote's timestamp when adding only static product details.
 const merged={...previous,...x,evidence,clearSpread:false};
 if(!hasQuote){for(const key of ["bid","ask","currency","sourceTime","delayed"])merged[key]=previous[key]??x[key];}
 else {for(const key of ["Kurs","Geld","Brief","Spread"])delete evidence[key];merged.clearSpread=n(x.spread)===null;}
 for(const [key,value] of Object.entries({Richtung:x.direction,Kurs:x.price,Hebel:x.leverage,KO:x.ko,Geld:x.bid,Brief:x.ask,Spread:x.spread})){if(value!==""&&value!==null&&value!==undefined)evidence[key]={value,source,at:fieldSourceTime(x,key)};}
 if(hasQuote&&evidence.Spread){const times=[evidence.Geld?.at,evidence.Brief?.at];evidence.Spread.at=times.every(Boolean)?times.sort()[0]:null;}
 for(const [key,field] of Object.entries({Kurs:"price",Hebel:"leverage",KO:"ko",Spread:"spread",Richtung:"direction"})){merged[field]=evidence[key]?.value??"";}
 return merged;
}
function supplementaryHint(missing){
 const identity=missing.includes("eindeutige ISIN");
 const staticFields=missing.some(v=>["Produktrichtung","Hebel","KO-Schwelle"].includes(v));
 const quotes=missing.some(v=>["Produktkurs","Geld-/Briefkurse für den Spread","bestätigte aktuelle Kursdaten mit Zeitstempeln"].includes(v));
 return (identity?"Bitte ein Bild mit eindeutig sichtbarer ISIN hochladen. ":"")+(staticFields?"Bitte Produktübersicht mit Richtung, Hebel und KO-Schwelle ergänzen. Für Hebel und KO sind eigene datierte Quellen erforderlich; ein neues Kursbild erneuert sie nicht. ":"")+(quotes?"Bitte Kursdatenbild mit ISIN, Geld, Brief und ausdrücklich zugeordneter Kurszeit (Datum, Sekunden, Zeitzone) ergänzen. Uploadzeit zählt nicht. ":"")+"Erkannte Werte bitte am Original prüfen.";
}
function screenshotTimeLabel(x){
 const e=x?.evidence?.Geld;
 if(e?.at){const t=evidenceTiming(e);return 'Kursquelle: '+e.at+' · '+(t.fresh?'höchstens 60 Sekunden alt':t.ageSeconds===null?'Zeit unklar':t.ageSeconds+' s alt / gesperrt')+' · Momentaufnahme, keine Live-Verifizierung.';}
 return x?.sourceTime?'Kursstand im Bild: '+x.sourceTime+' · Aktualität nicht verifiziert. Vollständige, ausdrücklich zugeordnete Kurszeit mit Sekunden und Zeitzone erforderlich.':'Kurszeit fehlt – Aktualität nicht prüfbar. Kein Live-Kurs.';
}
function screenshotSummary(x){
 if(!x)return "";
 const rows=Object.entries(x.evidence||{}).map(([key,e])=>{const t=evidenceTiming(e);return '<tr><td>'+esc(key)+'</td><td>'+esc(e.value)+'</td><td>'+esc(e.source)+'</td><td>'+esc(e.at||'Zeit / Zeitzone fehlt')+(key==='Richtung'?'':' · '+esc(t.ageSeconds===null?'gesperrt':t.ageSeconds+' s · '+(t.fresh?'≤ 60 s':'gesperrt')))+'</td></tr>';}).join("");
 return '<div class="small"><b>Erkannte Angaben – bitte prüfen</b><table style="width:100%"><thead><tr><th>Angabe</th><th>Wert</th><th>Bildquelle</th><th>Quellenzeit</th></tr></thead><tbody>'+rows+'</tbody></table>'+esc(screenshotTimeLabel(x))+'</div>';
}
function manualProductMissing(p){
 const missing=[];
 if(!validIsin(p.isin))missing.push("gültige ISIN");
 if(!(n(p.price)>0))missing.push("Produktkurs");
 if(!(n(p.leverage)>=1))missing.push("Hebel");
 if(!(n(p.ko)>0))missing.push("KO-Schwelle");
 if(n(p.spread)===null||n(p.spread)<0)missing.push("Spread");
 return missing;
}
function missingProductData(p){
 const missing=[];
 if(!validIsin(p.isin))missing.push("eindeutige ISIN");
 if(!["LONG","SHORT"].includes(p.productDirection))missing.push("Produktrichtung");
 if(!(n(p.price)>0))missing.push("Produktkurs");
 if(!(n(p.leverage)>=1))missing.push("Hebel");
 if(!(n(p.ko)>0))missing.push("KO-Schwelle");
 if(n(p.spread)===null||n(p.spread)<0)missing.push("Geld-/Briefkurse für den Spread");
 if(!currentQuote(p))missing.push("bestätigte aktuelle Kursdaten mit Zeitstempeln");
 return missing;
}
function parseScreenshotCandidates(text){
 const raw=String(text||"").replace(/\r/g,"");
 const matches=Array.from(raw.matchAll(/\b[A-Z]{2}[A-Z0-9]{10}\b/g));
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
  const x=ocrExtract(raw.slice(starts[i],i+1<matches.length?starts[i+1]:raw.length));
  const ident=normalizeOcrIsin(m[0]);x.isin=ident.isin;x.originalIsin=ident.originalIsin;
  const existing=hits.find(v=>v.isin===x.isin);
  if(existing){Object.keys(x).forEach(k=>{if(!existing[k]&&x[k])existing[k]=x[k];});}
  else if(hits.length<12)hits.push(x);
 });
 return hits;
}
function inject(){
 if(document.getElementById("dgTop3"))return;
 const a=document.getElementById("dgProductOut"); if(!a)return;
 const b=document.createElement("div");
 b.id="dgTop3";
 b.style.cssText="margin-top:14px;padding:16px;background:#f7f9fc;border-radius:20px;border:1px solid #e5eaf2";
 b.innerHTML='<div style="display:flex;align-items:center;gap:9px"><span style="font-size:25px">🎯</span><div><b style="font-size:18px">DEGIRO-Assistent</b><div class="small">Produktliste erfassen → Bilder pro ISIN ergänzen → belegte Daten vergleichen</div></div></div>'+
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
 '<div class="small" style="margin-top:9px">Automatische Produktrecherche: beim Öffnen und alle 60 Sekunden, solange Bob sichtbar ist. Quellenzeiten bleiben unverändert; Kurse über 90 Sekunden bleiben veraltet. Fehlende Kurse bleiben offen, berechnete Werte sind Schätzungen.</div>'+
 '<div id="dgMissingProducts" style="margin-top:12px"></div>'+
 '<div id="dgManualSnapshots" style="margin-top:12px"></div>'+
 '<div id="dgConditionalOut" style="margin-top:12px"></div>'+
 '<div id="dgTop3Out" style="margin-top:12px"></div>'+
 '<details style="margin-top:10px"><summary style="cursor:pointer;font-weight:700">Details / manuelle Kursnachweise</summary><div class="small" style="margin:7px 0">Hier lassen sich Screenshotwerte korrigieren und datierte Stuttgart-/Onvista-Nachweise bedingt auswerten.</div><div id="dgTop3Inputs"></div></details>'+
 '<button style="margin-top:10px;width:100%" id="dgRankBtn">🔎 Analyse erneut ausführen</button>';
 a.parentNode.insertBefore(b,a.nextSibling);
 const q=b.querySelector("#dgTop3Inputs");
 for(let i=1;i<=12;i++){
  const r=document.createElement("div");
  r.style.cssText="margin:8px 0;padding:9px;background:#fff;border-radius:10px";
  r.innerHTML='<b>Kandidat '+i+'</b><div id="dgOcrStatus'+i+'" class="small" style="margin-top:5px">Wartet auf Screenshot.</div><div id="dgResearch'+i+'" class="small research" style="margin-top:5px">🌐 Zusatzdaten: warten auf ISIN.</div><div class="grid" style="margin-top:6px"><input data-dg="name" data-i="'+i+'" placeholder="Produktname / ISIN"><select data-dg="dir" data-i="'+i+'"><option value="">Richtung</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select><input data-dg="price" data-i="'+i+'" type="number" step=".0001" placeholder="Produktkurs"><input data-dg="lev" data-i="'+i+'" type="number" step=".1" placeholder="Hebel"><input data-dg="ko" data-i="'+i+'" type="number" step=".01" placeholder="KO-Level"><input data-dg="spread" data-i="'+i+'" type="number" step=".01" min="0" placeholder="Spread"><input data-dg="isin" data-i="'+i+'" placeholder="ISIN"></div><label class="small"><input data-dg="confirmed" data-i="'+i+'" type="checkbox"> ISIN, erkannte Werte und zugeordnete Quellenzeiten am Original geprüft</label><button data-research="'+i+'">Aktuelle Produktdaten laden</button>';
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
   input.value="";input.disabled=true;
   try{for(const file of files){if(document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value!==isin)break;await readScreenshot(i,file);}}
   finally{input.disabled=false;}
  });
  r.querySelector('[data-research]').addEventListener('click',()=>enrichProduct(i));
  r.querySelector('[data-dg="confirmed"]').addEventListener('change',()=>{enrichProduct(i);rankUI();});
  r.querySelectorAll('[data-dg]').forEach(el=>el.addEventListener('input',()=>{if(el.dataset.dg!=="confirmed"){combinedReferences.delete(i);productQuotes.delete(i);futureResearchQuotes.delete(i);detailScreenshots.delete(i);rowVersions.set(i,(rowVersions.get(i)||0)+1);if(el.dataset.dg==="isin")r.querySelector('[data-dg="confirmed"]').checked=false;}rankUI();}));
 }
 populateCandidateRows(loadIdentities());
 quoteRefresh=createQuoteRefresh({
  rows:()=>Array.from({length:12},(_,idx)=>{const id=idx+1,isin=(document.querySelector('[data-dg="isin"][data-i="'+id+'"]')?.value.trim()||'').toUpperCase();return {id,isin,key:isin+':'+(rowVersions.get(id)||0)};}),
  request:enrichProduct,visible:()=>!document.hidden
 });
 refreshImportedProducts(true);
 let centralTexts=[],centralRecoveries=[];
 async function processCentralShot(file,label,slot){
  if(!file)return;
  const status=b.querySelector("#dgCentralStatus"),lab=b.querySelector("#dgShotLabel"+slot);
  try{
   if(lab)lab.textContent=label+" wartet …";
   if(status)status.textContent="⏳ "+label+" wartet auf den OCR-Worker …";
   const result=await recognizeOcr(file,"dgCentralStatus");
   centralTexts[slot-1]=result.data.text||"";centralRecoveries[slot-1]=result.data.isinRecoveries||{};
   const all=centralTexts.filter(Boolean).join("\n\n");
   const items=parseScreenshotCandidates(all);const recovered=Object.assign({},...centralRecoveries);for(const x of items){if(recovered[x.isin]){x.originalIsin=recovered[x.isin];x.ocrRecovery=true;}}
   populateCandidateRows(items);
   await refreshImportedProducts(true);
   if(lab)lab.textContent="✓ "+label+" geladen";
   if(status){const count=centralTexts.filter(Boolean).length;status.textContent=count<2?"✅ "+items.length+" Produkt(e) erkannt. Bitte noch Bild "+(count+1)+" hochladen.":"✅ "+count+" Bilder gelesen · "+items.length+" unterschiedliche Produkte erkannt.";const reread=items.filter(x=>x.ocrRecovery).length;if(reread)status.textContent+=" "+reread+" unsichere ISIN(s) durch Zweitlesung erkannt – am Screenshot prüfen.";const corrected=items.filter(x=>x.originalIsin&&!x.ocrRecovery).length;if(corrected)status.textContent+=" "+corrected+" ISIN(s) mit gültiger Prüfziffer aus O/0 bzw. I/1 normalisiert – bitte prüfen.";const uncertain=items.filter(x=>!validIsin(x.isin)).length;if(uncertain)status.textContent+=" ⚠️ "+uncertain+" ISIN(s) bitte unter Details prüfen (OCR unsicher oder Prüfziffer ungültig).";status.textContent+=" Aktuelle Emittentenkurse werden recherchiert. ISINs unter Details am Screenshot bestätigen. Quellen ohne datierte Kurse bleiben gesperrt.";}
   if(centralTexts.filter(Boolean).length>=2)rankUI();
  }catch(e){
   if(lab)lab.textContent=label+" erneut versuchen";
   if(status)status.textContent="⚠️ "+label+" konnte nicht automatisch gelesen werden: "+(e&&e.message?e.message:"OCR-Fehler");
   console.warn("[BOB] DEGIRO OCR",e);
  }
 }
 [1,2,3].forEach(slot=>{
  b.querySelector("#dgCentralShot"+slot).addEventListener("change",e=>processCentralShot(e.target.files&&e.target.files[0],"Bild "+slot,slot));
 });
 b.querySelector("#dgRankBtn").addEventListener("click",async e=>{const button=e.currentTarget;button.disabled=true;rankUI();try{await refreshImportedProducts(true);}finally{button.disabled=false;rankUI();}});
 setInterval(()=>{if(!document.hidden){rankUI();refreshImportedProducts();}},10000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){rankUI();refreshImportedProducts();}});
 window.addEventListener('online',()=>refreshImportedProducts());
 setInterval(()=>{if(!document.hidden)rankUI();},1000);
}
function rankUI(){
 saveIdentities();
 for(const [i,x] of futureResearchQuotes){
  const isin=document.querySelector('[data-dg="isin"][data-i="'+i+'"]')?.value.trim().toUpperCase();
  if(isin!==x.isin){futureResearchQuotes.delete(i);continue;}
  const meta=document.getElementById("dgResearch"+i),info=x.metadata;
  if(meta)meta.textContent="🌐 "+x.source+" · ISIN bestätigt · "+info.underlying+" · "+info.direction+" · KO "+info.ko+" USD · "+x.reason+futureResearchText(x)+productEstimateText(x)+". Produkt für aktuelle Rangliste gesperrt.";
 }
 for(let i=1;i<=12;i++){const out=document.getElementById('dgEvidence'+i),html=screenshotSummary(detailScreenshots.get(i));if(out&&out.innerHTML!==html)out.innerHTML=html;}
 for(const [i,q] of productQuotes){
  const computed=document.getElementById("dgCalculatedState"+i);if(computed)computed.textContent=productEstimateText(q);
  const state=document.getElementById("dgQuoteState"+i),timing=quoteTiming(q);
  if(state)state.textContent=q.eligible&&q.marketOpen&&timing.fresh?"aktuell · "+timing.ageSeconds+" s alt":"GESPERRT · "+(timing.ageSeconds===null?"Zeitstempel unbekannt":timing.ageSeconds+" s alt")+(q.marketOpen?"":" · Markt geschlossen");
 }
 const s=spot(),d=scenario(),a=atr();
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
  spread:n(document.querySelector('[data-dg="spread"][data-i="'+i+'"]')?.value),
  snapshot:detailScreenshots.get(i),quote:productQuotes.get(i)||futureResearchQuotes.get(i),isinConfirmed:document.querySelector('[data-dg="confirmed"][data-i="'+i+'"]')?.checked===true,
  spot:s
 }));
 for(let i=1;i<=12;i++){const out=document.getElementById("dgCombinedState"+i),ref=combinedReferences.get(i);if(ref&&ref.isin!==ps[i-1].isin)combinedReferences.delete(i);if(out)out.innerHTML=window.BobCombined.render(window.BobCombined.assess(ps[i-1],combinedReferences.get(i),bundle))+window.BobCombined.renderComparison(window.BobCombined.compareSnapshot(ps[i-1],combinedReferences.get(i),combinedDrafts.get(i),productQuotes.get(i)));}
 const missingOut=document.getElementById("dgMissingProducts");
 if(missingOut){
  const html=productUploadCards(ps,d);
  if(missingOut.dataset.content!==html){
   missingOut.innerHTML=html;missingOut.dataset.content=html;
   missingOut.querySelectorAll('[data-detail-upload]').forEach(btn=>btn.addEventListener("click",()=>document.getElementById("dgDetailShot"+btn.dataset.detailUpload)?.click()));
   missingOut.querySelectorAll('[data-card-research]').forEach(btn=>btn.addEventListener('click',()=>enrichProduct(Number(btn.dataset.cardResearch))));
   missingOut.querySelectorAll('[data-card-confirm]').forEach(box=>box.addEventListener('change',()=>{
    const field=document.querySelector('[data-dg="confirmed"][data-i="'+box.dataset.cardConfirm+'"]');if(field)field.checked=box.checked;rankUI();
   }));
  }
 }
 const manualOut=document.getElementById("dgManualSnapshots");
 if(manualOut){
  const ctx={direction:d,spotFresh,spot:s,atr:a,trend:document.getElementById('trend')?.textContent,trend2:document.getElementById('trend2')?.textContent,mtf:document.getElementById('mtfSummary')?.textContent,rsi:n(document.getElementById('rsi')?.textContent),hist:n(document.getElementById('hist')?.textContent),adx:n(document.getElementById('adx')?.textContent),momentum:n(document.getElementById('momentum')?.textContent)};
  const comparison=rankManualSnapshots(ps,ctx);
  manualOut.innerHTML=comparison.total?'<b>📷 Vergleich belegter Momentaufnahmen · '+comparison.total+' Produkt(e)</b>'+comparison.candidates.map((p,i)=>'<div class="small" style="margin-top:8px"><b>'+(i+1)+'. '+esc(p.isin)+'</b> · technische Passung '+p.evaluation.score+'/100 · KO-Abstand '+p.evaluation.koDistancePct.toFixed(2)+'%<br>Brief '+esc(p.snapshot.ask)+' EUR · Geld '+esc(p.snapshot.bid)+' EUR · Spread '+esc(p.spread)+' EUR · Hebel '+esc(p.leverage)+' · KO '+esc(p.ko)+(p.evaluation.warnings.length?'<br>'+esc(p.evaluation.warnings.join(' · ')):'')+'</div>').join('')+'<div class="small">Rangfolge nur innerhalb der belegten Momentaufnahmen. Laufende Aktualisierung, Marktstatus und Ausführbarkeit nicht bestätigt – keine Live-Freigabe. Unvollständige Produkte sind nicht im Vergleich.</div>':'';
 }
 const conditionalOut=document.getElementById("dgConditionalOut");
 if(conditionalOut){
  const hasModels=ps.some(p=>p.quote?.calculatedProduct||p.quote?.futureResearch);
  const ctx={spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,mtf:document.getElementById("mtfSummary")?.textContent,rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),momentum:n(document.getElementById("momentum")?.textContent)};
  conditionalOut.innerHTML=hasModels?renderConditional(rankConditional(ps,ctx)):"";
 }
 const r=rankProducts(ps,{requireFreshQuotes:true,spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById("trend")?.textContent,trend2:document.getElementById("trend2")?.textContent,mtf:document.getElementById("mtfSummary")?.textContent,rsi:n(document.getElementById("rsi")?.textContent),hist:n(document.getElementById("hist")?.textContent),adx:n(document.getElementById("adx")?.textContent),momentum:n(document.getElementById("momentum")?.textContent)});
 const o=document.getElementById("dgTop3Out");if(!o)return r;
 if(combinedReferences.size){
  const context={spotFresh,direction:d,atr:a,spot:s,trend:document.getElementById('trend')?.textContent,trend2:document.getElementById('trend2')?.textContent,mtf:document.getElementById('mtfSummary')?.textContent,rsi:n(document.getElementById('rsi')?.textContent),hist:n(document.getElementById('hist')?.textContent),adx:n(document.getElementById('adx')?.textContent),momentum:n(document.getElementById('momentum')?.textContent)};
  const automatic=window.BobCombined.rank(ps,ps.map((_,i)=>combinedReferences.get(i+1)),bundle,context);
  o.innerHTML=window.BobCombined.renderTop3(automatic);return automatic;
 }
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
   '<div style="margin-top:5px"><b>'+action+'</b> · Produktkurs '+(p.price??"—")+' · Hebel '+(e.leverage?e.leverage.toFixed(2):"—")+'×</div>'+
   '<div class="small">'+esc(p.quote.source)+' · Kurszeit '+esc(new Date(p.quote.quoteAt).toLocaleTimeString())+' · Spread '+esc(p.spread)+' EUR · DEGIRO-Ausführungskurs prüfen</div>'+
   (p.quote.leverageNote?'<div class="small">'+esc(p.quote.leverageNote)+'</div>':'')+
   '<div class="small" style="margin-top:4px">KO-Abstand '+ko+' · ATR-Puffer '+at+' · Setup-Qualität '+e.setupScore+'/100</div>'+
   '<div class="small" style="margin-top:7px"><b>Warum:</b> '+esc(reason)+'</div>'+
   (e.warnings.length?'<div class="small warning" style="margin-top:6px">⚠️ '+esc(e.warnings.slice(0,2).join(" · "))+'</div>':'')+
  '</div>';
 }).join("");
 o.innerHTML='<div style="padding:15px;background:#fff;border-radius:18px;border:2px solid #dbe4f0">'+
  '<div class="small">AKTUELLE BOB-ANALYSE · '+esc(r.scenario)+' · '+r.total+' Kandidat(en) geprüft</div>'+
  '<div style="font-size:20px;font-weight:800;margin-top:4px">🎯 Vergleich bestätigter Produktkurse</div>'+
  '<div class="small" style="margin-top:4px">Bob sortiert die passenden Produkte nach technischer Passung und Produktrisiko.</div>'+
  cards+
  '<div class="small" style="margin-top:9px">Die Plätze sind eine technische Rangfolge der geprüften DEGIRO-Kandidaten, keine Gewinnwahrscheinlichkeit und keine Garantie.</div></div>';
 return r;
}

if(typeof document!=="undefined"){if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",()=>{try{inject();}catch(e){console.warn(e);}});else try{inject();}catch(e){console.warn(e);}}
window.BobDegiro={createQuoteRefresh,screenshotCurrentState,renderScreenshotCurrentState,conditionalCandidate,rankConditional,renderConditional,qualityText,isFutureProduct,futureResearchText,productEstimateText,rankManualSnapshots,productUploadCards,sourceTimestamp,screenshotTimes,evidenceTiming,manualSnapshotStatus,needsDirectionalData,loadIdentities,saveIdentities,riskModel,koDistancePct,evaluateProduct,quoteTiming,currentQuote,rankProducts,technicalQuality,ocrExtract,parseScreenshotCandidates,validIsin,normalizeOcrIsin,populateCandidateRows,recoverOcrIsins,detailScreenshotData,missingProductData,supplementaryHint,screenshotTimeLabel,mergeScreenshotEvidence,manualProductMissing,escapeHtml:esc};
})();
