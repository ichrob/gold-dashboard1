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
