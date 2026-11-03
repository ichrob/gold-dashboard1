/* Bob: manual-only Top-3 order preparation. No broker control, order or quote fetch. */
(function(root){
'use strict';
const MAX_QUOTE_AGE=90000,MAX_FX_AGE=90000;
const positive=n=>typeof n==='number'&&Number.isFinite(n)&&n>0;
const nonnegative=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
const stamp=s=>typeof s==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(s)?Date.parse(s):NaN;
const fresh=(s,now,limit)=>Number.isFinite(stamp(s))&&now>=stamp(s)&&now-stamp(s)<=limit;
const validSide=s=>s==='LONG'||s==='SHORT';
const fmt=(n,d=2)=>Number.isFinite(n)?n.toLocaleString('de-CH',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const seenAt=s=>Number.isFinite(stamp(s))?new Date(stamp(s)).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'unbekannt';
function readChfFx(spots,now=Date.now(),currency='EUR'){
 if(currency==='CHF')return {available:true,rate:1,note:'Produkt direkt in CHF'};
 if(currency!=='EUR')return {available:false,reason:'Nur EUR-/CHF-Produkte unterstützt'};
 const chf=spots?.usd_chf_meta,eur=spots?.usd_eur_meta;
 if(chf?.error||eur?.error||!positive(Number(chf?.rate))||!positive(Number(eur?.rate))||
   !fresh(chf?.fetchedAt,now,MAX_FX_AGE)||!fresh(eur?.fetchedAt,now,MAX_FX_AGE))
  return {available:false,reason:'Aktuelle, datierte USD/CHF- und USD/EUR-Umrechnung fehlt'};
 return {available:true,rate:Number(chf.rate)/Number(eur.rate),
   note:'EUR/CHF aus USD/CHF ÷ USD/EUR; FX-Quellenzeit '+seenAt(chf.fetchedAt)+' / '+seenAt(eur.fetchedAt)};
}
function evaluate({candidate,product,quote,stopPlan,fx,budgetCHF,riskCHF,feesCHF,now=Date.now(),direction}={}){
 const item={isin:String(candidate?.isin||''),direction,available:false,entry:null,stop:null,
  quantity:null,currency:null,totalCHF:null,investedCHF:null,lossCHF:null,reason:'',
  source:null,quoteAt:null,fxNote:'',priceKind:null,warning:'Richtwerte, keine ausführbaren DEGIRO-Kurse'};
 const block=reason=>({...item,reason});
 if(!candidate||!validSide(direction)||candidate.direction!==direction||
    product?.isin!==item.isin||product.productDirection!==direction||
    product.isinConfirmed!==true)return block('Richtung und ISIN müssen zum geprüften Ranking passen.');
 if(!quote||quote.isin!==item.isin||!['EUR','CHF'].includes(quote.currency)||
    !positive(Number(quote.ask))||!positive(Number(quote.bid))||Number(quote.ask)<Number(quote.bid)||
    !fresh(quote.at,now,MAX_QUOTE_AGE)||!fresh(quote.askAt,now,MAX_QUOTE_AGE)||
    Math.abs(stamp(quote.askAt)-stamp(quote.at))>30000||
    !['issuer','research'].includes(quote.kind)||!String(quote.source||'').trim())
  return block('Kein zeitgleich datiertes, aktuelles Geld-/Briefpaar dieser ISIN.');
 item.entry=Number(quote.ask);item.currency=quote.currency;item.source=quote.source;
 item.quoteAt=quote.askAt;item.priceKind=quote.kind;
 if(!stopPlan?.available||stopPlan.currency!==quote.currency||
    !positive(Number(stopPlan.stop))||!(Number(stopPlan.stop)<item.entry)||
    !fresh(stopPlan.referenceAt,now,MAX_QUOTE_AGE)||
    Math.abs(stamp(stopPlan.referenceAt)-stamp(quote.at))>30000)
  return block('Produkt-Stopp fehlt oder passt nicht zur aktuellen Quelle; keine Stückzahl berechnen.');
 item.stop=Number(stopPlan.stop);
 if(!fx?.available||!positive(fx.rate))return block(fx?.reason||'Aktuelle Währungsumrechnung fehlt.');
 item.fxNote=fx.note||'';
 if(!positive(budgetCHF)||!positive(riskCHF)||!nonnegative(feesCHF))
  return block('Maximales Kapital, Verlustrisiko und Gebühren (auch 0 explizit) in CHF eintragen.');
 const costPerUnit=item.entry*fx.rate,lossPerUnit=(item.entry-item.stop)*fx.rate;
 if(!positive(costPerUnit)||!positive(lossPerUnit)||budgetCHF<=feesCHF||riskCHF<=feesCHF)
  return block('Kapital oder Risikobudget reicht nach Gebühren nicht aus.');
 const byBudget=Math.floor((budgetCHF-feesCHF)/costPerUnit);
 const byRisk=Math.floor((riskCHF-feesCHF)/lossPerUnit);
 const quantity=Math.min(byBudget,byRisk);
 if(!Number.isSafeInteger(quantity)||quantity<=0)return block('Kein ganzes Stück innerhalb von Kapital- und Risikogrenze.');
 item.available=true;item.quantity=quantity;item.investedCHF=quantity*costPerUnit;
 item.totalCHF=item.investedCHF+feesCHF;item.lossCHF=quantity*lossPerUnit+feesCHF;
 item.reason='Manuelle Richtwerte; bei DEGIRO Preis, Menge, Gebühren und separate VERKAUF-Stop-Order prüfen.';
 return item;
}
const session={budgetCHF:'',riskCHF:'',feesCHF:'',last:null};
function ensurePanel(){
 if(typeof document==='undefined')return null;
 const anchor=document.getElementById('dgTop3Out');
 if(!anchor)return null;
 let panel=document.getElementById('bobManualTop3');
 if(panel)return panel;
 panel=document.createElement('section');
 panel.id='bobManualTop3';
 panel.className='card';
 panel.style.cssText='border:1px solid #dbe4f0;padding:14px;margin-top:12px;background:#f8fbff';
 panel.innerHTML='<h3>Top 3 · Werte zum manuellen Eintragen</h3>'+
  '<p class="small">Bob verwendet exakt die bestehende LONG-/SHORT-Auswahl. Kein GO, keine Order und kein Klick auf DEGIRO. Aktualisierung mit Bobs bestehender Marktprüfung (im Handelsfenster etwa 30 Sek.); Quellenzeiten bestimmen die Gültigkeit, nicht das Neuladen der Anzeige.</p>'+
  '<div class="grid">'+
   '<div><label for="bobManualBudget">Maximaler Einsatz (CHF)</label><input id="bobManualBudget" type="number" min="0.01" step="0.01" inputmode="decimal" placeholder="selbst festlegen"></div>'+
   '<div><label for="bobManualRisk">Maximaler Verlust bis Stopp (CHF)</label><input id="bobManualRisk" type="number" min="0.01" step="0.01" inputmode="decimal" placeholder="selbst festlegen"></div>'+
   '<div><label for="bobManualFees">Kauf- und Verkaufsgebühren gesamt (CHF)</label><input id="bobManualFees" type="number" min="0" step="0.01" inputmode="decimal" placeholder="nachgewiesen; 0 ausdrücklich"></div>'+
  '</div>'+
  '<div data-manual-top3-status class="small" role="status"></div>'+
  '<div data-manual-top3-rows></div>'+
  '<p class="small">Der Kaufwert ist der beobachtete Briefkurs, **kein** verbindliches DEGIRO-Limit. Ein Schutzstopp ist eine getrennte VERKAUF-Order nach tatsächlichem Kauf; Stop- und KO-Gaps können höhere Verluste verursachen. Stückzahlen sind Planwerte, keine Brokerbestätigung.</p>';
 anchor.insertAdjacentElement('afterend',panel);
 for(const [id,key] of [['bobManualBudget','budgetCHF'],['bobManualRisk','riskCHF'],['bobManualFees','feesCHF']]){
  const input=panel.querySelector('#'+id);
  input.value=session[key];
  input.addEventListener('input',()=>{session[key]=input.value;if(session.last)renderFrom(session.last);});
 }
 panel.addEventListener('click',async e=>{
  const btn=e.target.closest('button[data-manual-copy]');
  if(!btn||btn.disabled)return;
  const value=btn.dataset.manualCopy;
  const status=panel.querySelector('[data-manual-top3-status]');
  try{
   if(!navigator.clipboard?.writeText)throw Error('clipboard-unavailable');
   await navigator.clipboard.writeText(value);
   status.textContent='Einzelwert kopiert. Bei DEGIRO vor Eingabe und Absenden selbst prüfen.';
  }catch(_){status.textContent='Kopieren auf diesem Gerät nicht möglich. Wert bitte manuell übernehmen.';}
 });
 return panel;
}
function parseAmount(s){return String(s).trim()===''?NaN:Number(s);}
function renderFrom(snapshot){
 const panel=ensurePanel();if(!panel)return;
 const now=Date.now(),{flow,products,bundle}=snapshot,side=flow?.direction;
 const rows=panel.querySelector('[data-manual-top3-rows]');
 const status=panel.querySelector('[data-manual-top3-status]');
 const selected=flow?.approved&&validSide(side)?
  (flow.groups||[]).flatMap(g=>g.candidates||[]).filter((c,i,all)=>all.findIndex(p=>p.isin===c.isin)===i).slice(0,3):[];
 const budgetCHF=parseAmount(session.budgetCHF),riskCHF=parseAmount(session.riskCHF),feesCHF=parseAmount(session.feesCHF);
 const market=root.productMarketPlan?.(side,now);
 const offers=selected.map((candidate,i)=>{
  const product=(products||[]).find(p=>p.isin===candidate.isin);
  const currency=product?.quote?.metadata?.currency||product?.quote?.currency;
  const quote=root.BobStopAssistant?.selectQuote(product?.quote,candidate.isin,now,currency);
  const stopPlan=product&&market?.available?root.BobDegiro?.productRiskPreview(product,market,now):null;
  const fx=readChfFx(bundle?.spots,now,quote?.currency||currency);
  const plan=evaluate({candidate,product,quote,stopPlan,fx,budgetCHF,riskCHF,feesCHF,now,direction:side});
  const line=(label,value,copy)=>'<div style="margin:5px 0"><b>'+label+':</b> '+escape(value)+
   (copy!==null&&copy!==undefined?'<button type="button" data-manual-copy="'+escape(copy)+'" style="width:auto;margin-left:8px;padding:5px 9px;font-size:12px;background:#334155">Kopieren</button>':'')+'</div>';
  const entry=plan.entry!==null?fmt(plan.entry,4)+' '+plan.currency+'/Stück':'—';
  const stop=plan.stop!==null?'≈ '+fmt(plan.stop,4)+' '+plan.currency+'/Stück':'—';
  return '<article style="padding:12px;border:1px solid #dde5ef;border-radius:12px;margin-top:10px;background:white">'+
   '<b>Platz '+(i+1)+' · '+escape(candidate.isin)+' · '+escape(side)+'</b>'+
   line('ISIN',candidate.isin,candidate.isin)+
   line('KAUF · Briefkurs als Limit-Richtwert',entry,plan.entry!==null?String(plan.entry):null)+
   line('STOP-LOSS · späterer VERKAUF',stop,plan.stop!==null?String(Number(plan.stop.toFixed(4))):null)+
   line('Stückzahl',plan.available?String(plan.quantity):'—',plan.available?String(plan.quantity):null)+
   line('Geschätzter Gesamtbetrag',plan.available?fmt(plan.totalCHF)+' CHF':'—',plan.available?String(Number(plan.totalCHF.toFixed(2))):null)+
   (plan.available?'<div class="small">Modellverlust bei Stopp einschließlich eingegebener Gebühren: ≈ '+fmt(plan.lossCHF)+' CHF. Tatsächlicher Verlust kann durch Gaps, KO oder fehlende Ausführung größer sein.</div>':'')+
   '<div class="small" style="margin-top:7px">'+escape(plan.source?'Quelle: '+plan.source+' · Original-Briefkurszeit '+seenAt(plan.quoteAt)+' Zürich. '+plan.fxNote:'Keine aktuelle Original-Kursquelle.')+'</div>'+
   '<div class="small" style="margin-top:5px;color:'+(plan.available?'#166534':'#9a3412')+'">'+escape(plan.reason)+'</div></article>';
 });
 status.textContent=selected.length?
  'Richtung '+side+' · '+selected.length+' Ranking-Produkte · geprüft '+new Date(now).toLocaleTimeString('de-CH',{timeZone:'Europe/Zurich'})+' · keine DEGIRO-Ausführungszusage':
  'ABWARTEN · keine aktuellen freigegebenen Ranking-Produkte, daher keine Kauf-/Stop-/Stückzahlwerte.';
 const output=offers.length?offers.join(''):'<p class="small">Keine drei Kandidaten erzwingen. Erst bestätigtes Markt- und Produktsignal abwarten.</p>';
 if(rows._html!==output){rows.innerHTML=output;rows._html=output;}
}
function render(flow,products,bundle){
 session.last={flow,products,bundle};
 renderFrom(session.last);
}
const api={evaluate,readChfFx,render};
root.BobManualTop3=api;
if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
