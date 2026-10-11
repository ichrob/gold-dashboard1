"""Read-only Bob UI for staged DEGIRO execution e-mails.

Review is required before any real trade is activated. This component
never touches existing position forms, push settings, simulations or orders.
"""
PANEL = r"""
<script>
(() => {
  function mount() {
    if (document.getElementById('bobEmailTradeImport')) return true;
    const host = document.getElementById('bobTradeUpload') ||
                 document.getElementById('bobExitEstimate') ||
                 document.getElementById('dgTop3');
    if (!host || !host.parentNode) return false;
    const wrapper=document.createElement('details');
    wrapper.id='bobEmailTradeImport';
    wrapper.style.cssText='margin-top:14px;padding:12px;border:1px solid #cbd5e1;border-radius:13px;background:#fff';
    const summary=document.createElement('summary');
    summary.textContent='DEGIRO-Kaufbestätigungen per E-Mail';
    const note=document.createElement('p');
    note.className='small';
    note.textContent='Eingehende DEGIRO-Mails werden nach Einrichtung automatisch ausgelesen. Die hier gezeigten Datensätze sind Vorschläge, keine geprüften Brokerpositionen. Es wird kein Trade aktiviert, keine Order ausgeführt und keine Push-Überwachung aus einer E-Mail eingeschaltet.';
    const button=document.createElement('button');
    button.type='button';
    button.textContent='E-Mail-Import prüfen';
    const status=document.createElement('p');
    status.className='small';
    status.setAttribute('role','status');
    status.textContent='E-Mail-Postfach und Weiterleitungsregel müssen zunächst verbunden werden.';
    const records=document.createElement('div');
    wrapper.append(summary,note,button,status,records);
    host.after(wrapper);
    let working=false;
    async function load() {
      if(working)return;
      working=true;button.disabled=true;
      status.textContent='Gespeicherte Importvorschläge werden geprüft …';
      try{
        const response=await fetch('/api/trade-email/read',{
          method:'POST',credentials:'same-origin',cache:'no-store',
          headers:{'Content-Type':'application/json'},body:'{}'
        });
        if(!response.ok)throw Error('HTTP '+response.status);
        const data=await response.json();
        status.textContent=data.configured?'Empfang konfiguriert · E-Mail-Inhalt wird nur als Vorschlag erfasst.':'E-Mail-Empfang ist noch nicht verbunden. Keine automatische Überwachung.';
        records.replaceChildren();
        for(const item of data.items||[]) {
          const e=item.result||{};
          if(e.status==='ignored')continue;
          const row=document.createElement('div');
          row.style.cssText='margin:9px 0;padding:10px;border:1px solid #e2e8f0;border-radius:9px';
          const title=document.createElement('strong');
          title.textContent=(e.status==='pending-review'?'Prüfung erforderlich': 'Nicht übernommen: '+(e.status||'unvollständig'));
          const detail=document.createElement('p');
          detail.className='small';
          detail.textContent=[e.isin,e.side,e.quantity&&e.quantity+' Stück',
              e.priceEur&&e.priceEur+' EUR/Stück',e.executedAt,e.reason]
              .filter(Boolean).join(' · ');
          row.append(title,detail);records.append(row);
        }
        if(!records.childElementCount){
          const empty=document.createElement('p');
          empty.className='small';empty.textContent='Noch keine DEGIRO-Bestätigung erfasst.';
          records.append(empty);
        }
      }catch(e){
        status.textContent='E-Mail-Archiv noch nicht erreichbar: '+e.message;
      }finally{working=false;button.disabled=false;}
    }
    button.addEventListener('click',load);
    wrapper.addEventListener('toggle',()=>{if(wrapper.open)load();});
    return true;
  }
  let attempts=0;
  const boot=setInterval(()=>{attempts++;if(mount()||attempts>=45)clearInterval(boot);},500);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);
  else mount();
})();
</script>

"""
