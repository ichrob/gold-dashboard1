/* Scenario estimates from a dated user reference; never executable quotes. */
(function(){
const num=v=>v!==null&&v!==undefined&&String(v).trim()!==''&&Number.isFinite(Number(String(v).replace(',','.')))?Number(String(v).replace(',','.')):null;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
 panel.innerHTML='<h3>Geschätzter Ausstiegskurs pro Stück</h3><div class="small">Referenz-Geldkurs und gleichzeitig beobachtete Gold-/FX-Werte eingeben oder aus vorhandenen Produktnachweisen übernehmen. Dieses Szenario ersetzt keinen aktuellen Verkaufskurs. Eingaben werden beim Berechnen auf diesem Gerät gespeichert.</div><div class="grid">'+fields.map(([k,l,t])=>'<div><label for="exit-'+k+'">'+l+'</label><input id="exit-'+k+'" data-exit="'+k+'" type="'+t+'" '+(t==='number'?'step="any" min="0"':'')+'></div>').join('')+'<div><label for="exit-direction">Produktrichtung</label><select id="exit-direction" data-exit="direction"><option value="">Auswählen</option><option>LONG</option><option>SHORT</option></select></div></div><label><input type="checkbox" data-exit="simpleSpotTurbo"> Einfaches Gold-Spot-Turbo in EUR, ohne Quanto; Bedingungen am Produkt geprüft</label><br><label><input type="checkbox" data-exit="referenceConfirmed"> Referenz-Geldkurs, Gold und FX gehören zeitlich zusammen; Quelle und Kurszeit geprüft</label><div class="grid"><button data-exit-reference>Produktnachweis übernehmen</button><button data-exit-plan>Ziel/Stop aus aktueller Goldanalyse</button><button data-exit-calculate>Verkaufskurse schätzen</button></div><div data-exit-output class="small">Noch keine Schätzung. Tatsächliche Position eingeben; keine Order oder Trade-Aktivierung.</div>';
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
 panel.querySelector('[data-exit-plan]').addEventListener('click',()=>{
  const direction=get('direction').value,b=window.liveBundleCache?.spots,age=num(b?.xaus_age_seconds),at=num(window.liveBundleCache?.fetched_at),gold=num(window.lastPrice),atr=num(window.A?.at);
  if(window.BobSession?.expired()||window.A?.ready!==true||!['LONG','SHORT'].includes(direction)||!gold||!atr||b?.is_genuine_xauusd_spot!==true||b.spot_error||age===null||at===null||age+Date.now()/1000-at<0||age+Date.now()/1000-at>60){panel.querySelector('[data-exit-output]').textContent='Frische passende Gold-Spot-Analyse oder Produktrichtung fehlt. Ziel/Stop bleiben offen.';return;}
  const stop=window.stopModel?.(direction,gold,atr,1.5)?.stop,target=window.targetModel?.(direction,gold,stop,2)?.target;
  if(!(stop>0&&target>0)){panel.querySelector('[data-exit-output]').textContent='Technischer Ziel-/Stopplan nicht verfügbar.';return;}
  get('planGold').value=gold;get('stopGold').value=stop.toFixed(2);get('targetGold').value=target.toFixed(2);
  panel.querySelector('[data-exit-output]').textContent='Technische Szenarien aus der aktuellen Goldanalyse übernommen. Keine Vorhersage des besten Ausstiegszeitpunkts.';
 });
 panel.querySelector('[data-exit-calculate]').addEventListener('click',()=>{const values=read();try{localStorage.setItem('bobExitScenarioV1',JSON.stringify(values));}catch(_){}panel.querySelector('[data-exit-output]').innerHTML=render(calculate(values));});
 panel.querySelectorAll('[data-exit]').forEach(el=>el.addEventListener('input',()=>{if(el.dataset.exit!=='referenceConfirmed')get('referenceConfirmed').checked=false;panel.querySelector('[data-exit-output]').textContent='Eingaben geändert; Schätzung erneut berechnen.';}));
}
function restoreReference(){
 const p=document.getElementById('bobExitEstimate');if(!p)return false;
 const get=k=>p.querySelector('[data-exit="'+k+'"]');
 try{const x=JSON.parse(localStorage.getItem('bobTradeMarketReferencesV1')||'{}')[get('isin').value];
 if(!x||x.at!==get('referenceAt').value||x.bid!==get('bid').value)return false;
 for(const k of ['goldReference','fxReference','fxScenario','source'])get(k).value=x[k];return true;
 }catch(_){return false;}
}
async function researchReference(){
 const panel=document.getElementById('bobExitEstimate');if(!panel)return;
 const get=k=>panel.querySelector('[data-exit="'+k+'"]'),out=panel.querySelector('[data-exit-output]');
 const isin=get('isin').value,at=get('referenceAt').value,bid=get('bid').value,source=get('source').value;
 if(!window.BobDegiro?.validIsin(isin)||!at||!(num(bid)>0)){out.textContent='Zuerst Produkt-ISIN und datierten Geldkurs übernehmen.';return;}
 get('referenceConfirmed').checked=false;out.textContent='Historische Gold-/FX-Referenz zur Originalzeit wird gesucht …';
 try{
  const response=await fetch('/api/trade-reference?at='+encodeURIComponent(at),{cache:'no-store'}),x=await response.json();
  if(get('isin').value!==isin||get('referenceAt').value!==at||get('bid').value!==bid)return;
  if(!response.ok||!x.available){out.textContent=x.reason||'Referenz fehlt.';return;}
  get('goldReference').value=x.goldReference;get('fxReference').value=x.fxReference;get('fxScenario').value=x.fxReference;
  get('source').value=source+' · Historische Näherungsreferenz: '+x.goldSource+' @ '+x.goldAt+'; '+x.fxSource+' @ '+x.fxStart+' bis '+x.fxEnd+'; Zeitzone Europe/Zurich angenommen; maximaler Zeitversatz '+x.maxSkewSeconds+' s';
  try{const all=JSON.parse(localStorage.getItem('bobTradeMarketReferencesV1')||'{}');all[isin]={at,bid,goldReference:x.goldReference,fxReference:x.fxReference,fxScenario:x.fxReference,source:get('source').value,evidence:x};localStorage.setItem('bobTradeMarketReferencesV1',JSON.stringify(all));}catch(_){}
  out.innerHTML='Gold-/FX-Werte übernommen: Gold '+esc(x.goldReference)+' USD · USD→EUR '+esc(x.fxReference)+'.<br><a href="'+esc(x.goldUrl)+'" target="_blank" rel="noopener">Goldquelle</a> · <a href="'+esc(x.fxUrl)+'" target="_blank" rel="noopener">FX-Quelle</a><br>'+esc(x.note)+'<br>Referenz in den Berechnungsdetails prüfen und bestätigen. Ziel/Stop ergänzen. Ausstiegs-FX zunächst konstant angenommen.';
 }catch(_){if(get('isin').value===isin&&get('referenceAt').value===at)out.textContent='Referenzabruf fehlgeschlagen. Keine historischen Werte ersetzt.';}
}
window.BobExitEstimate={calculate,render,init,researchReference,restoreReference};
if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();}
})();
