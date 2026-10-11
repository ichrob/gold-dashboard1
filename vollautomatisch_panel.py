"""Isolated UI for an authenticated, fixed-quote PAPER-ONLY regression demo.

Existing mobile navigation in Bob.html provides the Vollautomatisch workspace.
This panel adds an actual executable prototype without duplicate navigation.
"""
PANEL = r"""
<section id="bob-vollautomatisch-demo" class="card" style="margin:12px 0;padding:16px;border:1px solid #b6c3d2;border-radius:14px;background:#fff;color:#16263c">
 <h3>100 € · Simulations-Probelauf</h3>
 <p class="small" style="color:#475569">Getrennter Rechenkern mit synthetischen Produktkursen in Euro. Er testet Kauf, Positionsgrösse, Stop-Loss, Gewinnziel, Trailing-Stop und Kostenannahmen. Noch kein automatischer Handel mit Marktdaten.</p>
 <button type="button" id="bobAutoDemoRun" class="bob-primary">Probelauf mit Beispieldaten starten</button>
 <p class="small" id="bobAutoDemoStatus" role="status">Noch nicht ausgeführt · keine Echtgeld-Orders möglich.</p>
 <div id="bobAutoDemoResults" hidden>
  <div id="bobAutoDemoNumbers" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0"></div>
  <details open><summary><b>Simulierter Orderverlauf</b></summary>
   <ol id="bobAutoDemoEvents" style="padding-left:22px;line-height:1.7"></ol>
  </details>
  <p class="small">Die Kurse sind frei erfunden und nachträglich festgelegt. Der Probelauf ist ein Funktionstest, kein Erfolgsnachweis. Einstieg zum Briefkurs, Ausstieg zum Geldkurs, zusätzliche Slippage; Gebühren im Probelauf auf 0 € gesetzt.</p>
 </div>
</section>
<script>
(function(){
 function mount(){
  const root=document.getElementById('bob-vollautomatisch-demo');
  if(!root)return;
  const auto=document.getElementById('bob-view-auto');
  if(auto)auto.append(root);
  const run=document.getElementById('bobAutoDemoRun');
  const status=document.getElementById('bobAutoDemoStatus');
  const results=document.getElementById('bobAutoDemoResults');
  const summary=document.getElementById('bobAutoDemoNumbers');
  const events=document.getElementById('bobAutoDemoEvents');
  const eur=new Intl.NumberFormat('de-CH',{style:'currency',currency:'EUR'});
  run.addEventListener('click',async()=>{
   run.disabled=true;status.textContent='Synthetische Trades werden berechnet …';
   results.hidden=true;
   try{
    const response=await fetch('/api/vollautomatisch/demo',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)throw Error('Probelauf konnte nicht geladen werden (HTTP '+response.status+').');
    const data=await response.json();
    if(data.mode!=='PAPER_ONLY'||data.live_order_capable!==false||data.synthetic!==true)throw Error('Unsicherer Simulationsstatus');
    summary.replaceChildren();events.replaceChildren();
    const cells=[
      ['Startkapital',eur.format(data.initial_eur)],
      ['Virtuelles Endkapital',eur.format(data.equity_eur)],
      ['Veränderung',eur.format(data.equity_eur-data.initial_eur)],
      ['Maximaler Rückgang',(data.max_drawdown_fraction*100).toFixed(2)+' %']
    ];
    for(const [label,value] of cells){
     const cell=document.createElement('div');cell.style='padding:10px;border:1px solid #e2e8f0;border-radius:10px;min-width:0';
     const title=document.createElement('small');title.style='display:block;color:#475569';title.textContent=label;
     const body=document.createElement('strong');body.textContent=value;cell.append(title,body);summary.append(cell);
    }
    const descriptions={
      BUY_PAPER:'Virtueller Kauf',SELL_PAPER:'Virtueller Verkauf',
      TRAIL_PAPER:'Stop nachgezogen',BLOCKED:'Einstieg gesperrt',
      STALE_FEED:'Kurs veraltet'
    };
    for(const e of data.events){
     const line=document.createElement('li');
     const name=descriptions[e.event]||'Testereignis';
     const price=typeof e.price_eur==='number'?' · '+eur.format(e.price_eur):'';
     const stop=typeof e.stop_eur==='number'?' · Stop '+eur.format(e.stop_eur):'';
     const amount=typeof e.quantity==='number'?' · '+e.quantity+' Stück':'';
     const gain=typeof e.pnl_eur==='number'?' · Ergebnis '+eur.format(e.pnl_eur):'';
     line.textContent=name+' · '+e.at+amount+price+stop+gain+(e.reason?' · '+e.reason:'');
     events.append(line);
    }
    status.textContent='Funktionstest berechnet · '+data.quotes_processed+' künstliche Kursbeobachtungen · keine echte Order';
    results.hidden=false;
   }catch(error){status.textContent='Probelauf nicht verfügbar: '+String(error.message||error);}
   finally{run.disabled=false;}
  });
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
</script>
"""
