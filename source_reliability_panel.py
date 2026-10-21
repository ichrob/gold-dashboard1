"""Private operational panel; plain text, no external transmission or push."""
PANEL = r'''<details id="bobSourceReliability" class="card" style="margin:12px 0">
<summary><strong>Datenquellen &amp; Unterbrechungen</strong></summary>
<p id="bobSourceReliabilityStatus" role="status">Messstand wird geladen …</p>
<p class="small">Quellenfehler und Einschränkungen der Analyse werden getrennt gezählt. Zeiten gelten nur für beobachtete Messintervalle. Während Neustarts oder Messlücken bleibt die tatsächliche Verfügbarkeit unbekannt. Außerhalb des Handelszeitfensters pausiert die Ausfallzählung.</p>
<div id="bobSourceReliabilityRows"></div>
</details>
<script>
(()=>{
 const names={current:'Aktuell',stale:'Zeitstempel veraltet',unavailable:'Nicht erreichbar / keine Daten',incomplete:'Daten unvollständig',paused:'Messung pausiert',unknown:'Noch nicht geprüft'};
 const fmt=t=>t?new Date(t*1000).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch nicht bestätigt';
 async function refresh(){
  if(document.hidden||window.BobSession?.expired?.())return;
  const status=document.getElementById('bobSourceReliabilityStatus');
  try{
   const response=await fetch('/api/source-reliability',{cache:'no-store',credentials:'same-origin'});
   if(!response.ok)throw Error('unavailable');
   const data=await response.json();
   const entries=Object.entries(data.sources||{});
   const bad=x=>['stale','unavailable','incomplete'].includes(x.state);
   const effective=entries.filter(([k])=>k.startsWith('analysis/'));
   status.textContent=(entries.length?'':'Noch keine bestätigten Messungen · ')+effective.filter(([,v])=>bad(v)).length+' Zeitrahmen mit Dateneinschränkung · '+effective.filter(([,v])=>v.state==='unknown').length+' ungeprüft · '+
    entries.filter(([k,v])=>!k.startsWith('analysis/')&&bad(v)).length+' Quellenprobleme · Archiv: '+
    (data.storage?.state==='ready'?'erreichbar':'noch nicht bestätigt')+' · zuletzt gespeichert: '+fmt(data.storage?.lastSavedAt)+
    ' · wiederhergestellte Kerzenserien: '+(data.storage?.restoredSeries||0);
   const out=document.getElementById('bobSourceReliabilityRows');
   const opened=new Set([...out.children].filter(x=>x.open).map(x=>x.dataset.key));
   out.replaceChildren();
   for(const [key,row] of entries){
    const item=document.createElement('details');item.dataset.key=key;item.open=opened.has(key);
    const title=document.createElement('summary');
    title.textContent=key.replace('analysis/','Analyse · ').replace('/',' · ')+' — '+(names[row.state]||'Unbekannt');
    const p=document.createElement('p');p.className='small';
    p.textContent=(row.incidents||0)+' beobachtete Störungen · '+Math.round((row.badSeconds||0)/60)+' Minuten eingeschränkt · '+
     Math.round((row.unknownSeconds||0)/60)+' Minuten unbeobachtet · Messbeginn: '+fmt(row.since)+' · geprüft: '+fmt(row.checkedAt);
    item.append(title,p);
    for(const event of [...(row.events||[])].reverse()){
     const e=document.createElement('p');e.className='small';e.textContent=fmt(event.at)+' · '+(names[event.state]||'Unbekannt');item.append(e);
    }
    out.append(item);
   }
  }catch(_){status.textContent='Quellenstatistik momentan nicht erreichbar. Vorherige Werte sind nicht als aktuell bestätigt.';}
 }
 refresh();setInterval(refresh,30000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
</script>'''
