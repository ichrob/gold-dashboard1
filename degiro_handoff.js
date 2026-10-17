/* Manual order planning only. No brokerage requests or accessibility automation. */
(function(root){
'use strict';
const KEY='bob.degiro2.plan.v1';
function day(date=new Date()){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);}
function cents(value){const s=String(value).trim().replace(',','.');if(!/^\d{1,9}(\.\d{1,2})?$/.test(s))throw Error('Geldbeträge mit höchstens zwei Nachkommastellen eingeben.');const n=Math.round(Number(s)*100);if(!Number.isSafeInteger(n))throw Error('Betrag zu groß.');return n;}
function isin(value){const s=String(value).trim().toUpperCase();if(!/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(s))throw Error('Bitte eine gültige ISIN eingeben.');const digits=s.replace(/[A-Z]/g,c=>String(c.charCodeAt(0)-55));let sum=0;[...digits].reverse().forEach((c,i)=>{let n=Number(c)*(i%2?2:1);sum+=n>9?n-9:n;});if(sum%10)throw Error('ISIN-Prüfziffer stimmt nicht.');return s;}
function reserve(state,input,today=day()){
 const budget=cents(input.budget),fees=cents(input.fees),price=cents(input.price),qty=Number(input.qty);
 if(budget<=0||price<=0||!/^\d+$/.test(String(input.qty))||!Number.isSafeInteger(qty)||qty<1)throw Error('Budget, Stückzahl und Limit müssen positiv sein.');
 if(!['EUR','CHF'].includes(input.currency)||!['Kauf','Verkauf'].includes(input.side))throw Error('Ungültige Währung oder Richtung.');
 const orders=state&&state.day===today?state.orders:[];
 if(!Array.isArray(orders))throw Error('Gespeicherte Planung ist ungültig.');
 if(orders.length&&state.currency!==input.currency)throw Error('Bestehende Tagesentwürfe zuerst entfernen, bevor du die Währung wechselst.');
 const cost=qty*price+fees;if(!Number.isSafeInteger(cost))throw Error('Orderbetrag zu groß.');
 const used=orders.reduce((n,o)=>{if(!Number.isSafeInteger(o.cost)||o.cost<0||!['Kauf','Verkauf'].includes(o.side))throw Error('Gespeicherte Planung ist ungültig.');return n+(o.side==='Kauf'?o.cost:0);},0);
 if(used+(input.side==='Kauf'?cost:0)>budget)throw Error('Die geplanten Käufe überschreiten dein Tagesbudget.');
 const order={isin:isin(input.isin),side:input.side,qty,price,fees,cost};
 return {day:today,currency:input.currency,budget,orders:[...orders,order]};
}
function maxQuantity(state,input,today=day()){
 const budget=cents(input.budget),price=cents(input.price),fees=cents(input.fees);
 if(price<=0)throw Error('Zuerst ein positives Limit eingeben.');
 const current=state&&state.day===today?state:null;
 if(current&&current.orders.length&&current.currency!==input.currency)throw Error('Währung passt nicht zur Tagesplanung.');
 const used=current?current.orders.filter(o=>o.side==='Kauf').reduce((n,o)=>n+o.cost,0):0;
 return Math.max(0,Math.floor((budget-used-fees)/price));
}
function money(c){return (c/100).toFixed(2).replace('.',',');}
function summary(o,c){return `ENTWURF – nicht übermittelt\n${o.side}: ${o.isin}\nStückzahl: ${o.qty}\nLimit je Stück: ${money(o.price)} ${c}\nGeschätzte Gebühren: ${money(o.fees)} ${c}\n${o.side==='Kauf'?'Planbetrag inkl. Gebühren':'Bruttoverkaufswert zzgl. Gebühren (kein Budgetguthaben)'}: ${money(o.cost)} ${c}\nIn DEGIRO Produkt, Währung, Handelsplatz, Gültigkeit und Gebühren prüfen und selbst bestätigen.`;}
const api={day,cents,isin,reserve,summary,maxQuantity};if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
function mount(){
 const host=document.getElementById('bob-view-degiro2');if(!host)return;
 const box=document.createElement('section');box.className='card';box.style.padding='16px';
 box.innerHTML=`<h3>Handy-Assistent · manuelle Bestätigung</h3>
 <p>Plane deine Orders und öffne anschließend DEGIRO. Jeden echten Kauf oder Verkauf prüfst und bestätigst du selbst in der App.</p>
 <p>Das Tagesbudget begrenzt nur hier geplante Käufe, nicht tatsächliche Trades oder Verluste. Verkäufe geben kein Planbudget frei. Keine Verbindung zum Depot.</p>
 <form id="dg2-form"><label>Tagesbudget <input name="budget" inputmode="decimal" required></label>
 <label>Währung <select name="currency"><option>EUR</option><option>CHF</option></select></label>
 <label>Vorhandenes Bob-Produkt <select id="dg2-product"><option value="">Manuell eingeben</option></select></label><button type="button" id="dg2-refresh">Produktliste übernehmen</button>
 <label>ISIN <input name="isin" maxlength="12" autocapitalize="characters" required></label>
 <label>Richtung <select name="side"><option>Kauf</option><option>Verkauf</option></select></label>
 <label>Stückzahl <input name="qty" inputmode="numeric" required></label>
 <label>Limit je Stück (max. 2 Nachkommastellen) <input name="price" inputmode="decimal" required></label>
 <label>Geschätzte Gebühren <input name="fees" inputmode="decimal" value="0" required></label>
 <button type="button" id="dg2-size">Maximale Kaufstückzahl berechnen</button><p>Rechnerische Budgetobergrenze, keine Empfehlung zur vollständigen Ausschöpfung.</p>
 <button type="submit">Entwurf speichern</button></form>
 <p role="status" aria-live="polite" id="dg2-status"></p><p id="dg2-budget"></p><div id="dg2-orders"></div>
 <p><a id="dg2-open">DEGIRO öffnen</a></p>
 <p>Falls sich nur die Webseite öffnet, starte die DEGIRO-App über ihr Symbol. ISIN dort selbst suchen. Es werden keine Eingaben oder Bestätigungen in der App automatisiert.</p>
 <p>Planung nur auf diesem Gerät und in diesem Browser. Tageswechsel: Schweizer Zeit. Andere Geräte, gelöschte Browserdaten und echte Orders werden nicht abgeglichen. Keine zusätzliche Softwarelizenz oder API-Gebühr; bestehende Hosting- und Handelskosten bleiben bestehen.</p>`;
 host.append(box);box.querySelectorAll('label').forEach(el=>{el.style.display='block';el.style.margin='12px 0';});box.querySelectorAll('input,select').forEach(el=>{el.style.display='block';el.style.padding='10px';el.style.maxWidth='100%';});
 const form=box.querySelector('form'),status=box.querySelector('#dg2-status');let state=null;
 const products=box.querySelector('#dg2-product');
 function refreshProducts(){products.replaceChildren(new Option('Manuell eingeben',''));const items=root.BobDegiro?.tradeTestProducts?.()||[];for(const p of items){try{products.append(new Option(p.isin+' · '+(p.name||''),isin(p.isin)));}catch(e){}}}
 box.querySelector('#dg2-refresh').onclick=()=>{refreshProducts();status.textContent='Produktidentitäten aus Bob geladen. Das aktuelle Limit bitte in DEGIRO prüfen.';};
 products.onchange=()=>{if(products.value){form.elements.isin.value=products.value;form.elements.price.value='';form.elements.qty.value='';status.textContent='ISIN übernommen. Aktuelles Limit und Stückzahl ergänzen.';}};
 box.querySelector('#dg2-size').onclick=()=>{try{if(form.elements.side.value!=='Kauf')throw Error('Verkaufsstückzahl anhand deines echten Bestands selbst eingeben.');const qty=maxQuantity(read(),Object.fromEntries(new FormData(form)));form.elements.qty.value=qty||'';status.textContent=qty?'Rechnerische maximale Stückzahl eingetragen. Du kannst sie reduzieren.':'Kein Budget für ein weiteres Stück verfügbar.';}catch(e){status.textContent=e.message;}};
 refreshProducts();
 function read(){const raw=localStorage.getItem(KEY);return raw?JSON.parse(raw):null;}
 function render(){const current=state&&state.day===day()?state:null;const orders=current?current.orders:[];if(!Array.isArray(orders))throw Error('Ungültige gespeicherte Planung.');
 box.querySelector('#dg2-budget').textContent=current?`${current.day} · Geplante Käufe: ${money(orders.filter(o=>o.side==='Kauf').reduce((n,o)=>n+o.cost,0))} / ${money(current.budget)} ${current.currency}`:'Heute noch keine Entwürfe.';
 const list=box.querySelector('#dg2-orders');list.replaceChildren();orders.forEach((order,i)=>{
 const article=document.createElement('article'),text=document.createElement('textarea');text.readOnly=true;text.rows=8;text.style.width='100%';text.style.boxSizing='border-box';text.value=summary(order,current.currency);text.setAttribute('aria-label','Orderentwurf');article.append(text);
 function button(label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=fn;article.append(b);}
 async function copy(value){try{await navigator.clipboard.writeText(value);status.textContent='Kopiert. Bitte in DEGIRO prüfen.';}catch(e){text.focus();text.select();status.textContent='Bitte den markierten Entwurf manuell kopieren.';}}
 button('ISIN kopieren',()=>copy(order.isin));button('Entwurf kopieren',()=>copy(text.value));
 button('Entwurf entfernen',()=>{try{const latest=read();if(JSON.stringify(latest)!==JSON.stringify(state))throw Error('Planung wurde in einem anderen Fenster geändert. Seite neu laden.');const next={...state,orders:state.orders.filter((_,j)=>j!==i)};localStorage.setItem(KEY,JSON.stringify(next));state=next;render();status.textContent='Entwurf entfernt. Dies storniert keine Order bei DEGIRO.';}catch(e){status.textContent=e.message;}});list.append(article);
 });}
 try{state=read();if(state&&state.day===day()){form.elements.budget.value=money(state.budget);form.elements.currency.value=state.currency;}render();}catch(e){status.textContent='Planung konnte nicht geladen werden: '+e.message;form.querySelector('button').disabled=true;}
 form.addEventListener('submit',e=>{e.preventDefault();try{const latest=read();const next=reserve(latest,Object.fromEntries(new FormData(form)));localStorage.setItem(KEY,JSON.stringify(next));state=next;render();status.textContent='Entwurf gespeichert – keine Order übermittelt.';}catch(err){status.textContent=err.message;}});
 const web='https://trader.degiro.nl/';const link=box.querySelector('#dg2-open');link.href=/Android/i.test(navigator.userAgent||'')?'intent://trader.degiro.nl/#Intent;scheme=https;package=nl.degiro.trader;S.browser_fallback_url='+encodeURIComponent(web)+';end':web;
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){try{state=read();render();}catch(e){status.textContent=e.message;}}});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof window==='undefined'?globalThis:window);
