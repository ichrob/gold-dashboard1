"""Compact, read-only trade risk and confirmed screenshot exit UI for Mein Trade."""
PANEL = r"""
<script>
(() => {
  let started = false;
  function mount() {
    if (started || document.getElementById('bobTradeRiskReview')) return true;
    const host = document.getElementById('bobTradeUpload') ||
      document.getElementById('bobExitEstimate');
    if (!host || !host.parentNode) return false;
    const root = document.createElement('details');
    root.id='bobTradeRiskReview';
    root.style.cssText='margin:12px 0;padding:12px;border:1px solid #94a3b8;border-radius:12px;background:var(--panel,#fff);color:var(--text,#17212f)';
    root.innerHTML = `
      <summary style="font-weight:700;cursor:pointer">Trade prüfen &amp; auswerten</summary>
      <p class="small">Nur Berechnung und Dokumentation. Keine DEGIRO-Order.</p>
      <details style="margin:10px 0">
        <summary><b>1. Vor dem Kauf · Stopp, Risiko &amp; Gebühren</b></summary>
        <label style="display:block;margin:9px 0">Produktwährung <select id="bobTradeRiskCurrency"><option value="EUR">EUR</option><option value="CHF">CHF</option></select></label>
        <div id="bobTradeRiskFields" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:9px 0"></div>
        <button type="button" id="bobTradeRiskButton">Risiko berechnen</button>
        <p id="bobTradeRiskResult" class="small" role="status"></p>
      </details>
      <details style="margin:10px 0">
        <summary><b>2. DEGIRO-Verkauf abschließen</b></summary>
        <p class="small">Screenshot auswählen, Felder aus dem Beleg prüfen. Nur den vollständig verkauften Trade bestätigen.</p>
        <label style="display:block;margin:6px 0">Aktiver Trade<select id="bobTradeSaleSelect" style="width:100%;padding:7px"></select></label>
        <label style="display:block;margin:6px 0">Original-Screenshot<input id="bobTradeSaleImage" type="file" accept="image/*" style="display:block;width:100%"></label>
        <button type="button" id="bobTradeSaleOcr">Werte aus Screenshot erkennen</button>
        <div id="bobTradeSaleFields" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px"></div>
        <label style="display:block;margin:6px 0">Verkaufsgrund
          <select id="bobTradeSaleReason" style="width:100%;padding:7px">
            <option value="other">Noch nicht belegt</option>
            <option value="stop-loss-user-confirmed">Stop-Loss laut Nutzer</option>
            <option value="manual">Manueller Verkauf</option>
          </select>
        </label>
        <label style="display:block;margin:8px 0"><input type="checkbox" id="bobTradeSaleCheck"> Ich bestätige den DEGIRO-Verkauf anhand des Screenshots.</label>
        <button type="button" id="bobTradeSaleSave">Verkauf dokumentieren · Überwachung beenden</button>
        <p id="bobTradeSaleStatus" class="small" role="status"></p>
      </details>
      <button type="button" id="bobTradeReviewRefresh">Abgeschlossene Trades auswerten</button>
      <div id="bobTradeReviewResults" role="status" style="margin-top:10px"></div>`;
    host.after(root); started=true;
    const $=id=>root.querySelector('#'+id);
    const risk = [
      ['entry','Produkt-Kaufkurs',true],['quantity','Stückzahl',true],
      ['stop','Stopp im Produktkurs'],['target','Ziel im Produktkurs'],
      ['atr','ATR des Produktes'],['structureStop','Struktur-Stopp Produkt'],
      ['chfPerUnit','CHF je Produkteinheit'],['buyFeeCHF','Kaufgebühr CHF'],
      ['sellFeeCHF','Verkaufsgebühr CHF'],['maxRiskPct','Max. Produktrisiko %']
    ];
    const sale = [
      ['transactionId','DEGIRO Transaktions-ID','text'],
      ['executedLocal','Zeit (TT.MM.JJJJ HH:MM:SS)','text'],
      ['price','Verkaufspreis je Stück','number'],
      ['saleValueCHF','Brutto CHF','number'],
      ['feesCHF','Gebühren CHF','number'],
      ['saleNetCHF','Auszahlung CHF','number'],
      ['eurPerCHF','DEGIRO Wechselkurs','number']
    ];
    function buildFields(host,defs) {
      for(const [key,label,required] of defs) {
        const wrap=document.createElement('label');
        wrap.style.cssText='display:block;font-size:12px';
        wrap.textContent=label;
        const input=document.createElement('input');
        input.name=key;input.style.cssText='box-sizing:border-box;width:100%;padding:7px;margin-top:3px;font-size:14px';
        input.type=(required==='text'?'text':'number');
        if(input.type==='number'){input.step='any';input.min='0';input.inputMode='decimal';}
        if(required===true)input.required=true;
        wrap.append(input);host.append(wrap);
      }
    }
    buildFields($('bobTradeRiskFields'),risk);
    buildFields($('bobTradeSaleFields'),sale);
    $('bobTradeRiskFields').querySelector('[name=maxRiskPct]').value='5';
    function readFields(id,defs) {
      const host=$(id),o={};
      for(const [key] of defs){
        const input=host.querySelector('[name='+key+']');
        if(input.value.trim())o[key]=(input.type==='number'?Number(input.value):input.value.trim());
      }
      return o;
    }
    async function request(path,body){
      const response=await fetch('/api/real-trades/'+path,{method:'POST',credentials:'same-origin',
        cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await response.json();
      if(!response.ok || data.ok===false)throw Error(data.error||data.reason||'HTTP '+response.status);
      return data;
    }
    function fmt(n,digits=2){return n===null||n===undefined?'nicht nachgewiesen':Number(n).toLocaleString('de-CH',{minimumFractionDigits:digits,maximumFractionDigits:digits});}
    $('bobTradeRiskButton').onclick=async()=>{
      const output=$('bobTradeRiskResult');
      output.textContent='Berechne …';
      try {
        const fields=readFields('bobTradeRiskFields',risk);
        const result=(await request('risk',{plan:{...fields,currency:$('bobTradeRiskCurrency').value,sourceVerified:false}})).review;
        output.textContent='Risiko '+fmt(result.riskPct)+' % · Break-even '+fmt(result.breakEvenProduct,4)+' '+result.currency+' · Stopp netto '+fmt(result.riskStopCHF)+' CHF · Ziel netto '+fmt(result.targetNetCHF)+' CHF. '+result.warnings.join(' · ');
      } catch(e){output.textContent='Prüfung: '+e.message;}
    };
    let active=[];
    async function refresh() {
      const data=await request('read',{});
      active=(data.trades||[]).filter(x=>x.active);
      const select=$('bobTradeSaleSelect');
      const prev=select.value;
      select.replaceChildren();
      for(const t of active){
        const option=document.createElement('option');
        option.value=t.id; option.textContent=(t.snapshot?.product?.isin||t.id)+' · '+(t.snapshot?.product?.quantity||'?')+' Stück';
        select.append(option);
      }
      if(active.some(t=>t.id===prev))select.value=prev;
      const container=$('bobTradeReviewResults');container.replaceChildren();
      let closed=(data.trades||[]).filter(t=>!t.active&&!t.snapshot?.recordOnly).slice(0,10);
      for(const t of closed){
        if(closed.indexOf(t)<3){
          try {const detailed=await request('read',{tradeId:t.id});
            const matched=(detailed.trades||[]).find(x=>x.id===t.id);
            if(matched&&matched.evaluation)t.evaluation=matched.evaluation;
          } catch (_) { /* Preserve existing summary when model history is unavailable. */ }
        }
        const div=document.createElement('div');div.style.cssText='border-top:1px solid #cbd5e1;padding:9px 0';
        const ev=t.evaluation||{},title=document.createElement('b'),body=document.createElement('p');
        title.textContent=t.snapshot?.product?.isin||'Trade';
        body.className='small';
        body.textContent=ev.verdict+' · Netto CHF: '+fmt(ev.realizedNetCHF)+' · Netto Produkt: '+fmt(ev.realizedNetProduct)+' · Modell-MFE/MAE: '+fmt(ev.modelMfePct)+' / '+fmt(ev.modelMaePct)+' % (wenn beobachtet)';
        div.append(title,body);container.append(div);
      }
      if(!closed.length)container.textContent='Noch kein bestätigter Abschluss im Journal.';
      if(!active.length)$('bobTradeSaleStatus').textContent='Kein aktiver Echtgeld-Trade in Bob. Zuerst Kauf und Überwachung erfassen.';
    }
    $('bobTradeReviewRefresh').onclick=()=>refresh().catch(e=>$('bobTradeReviewResults').textContent=e.message);
    root.addEventListener('toggle',()=>{if(root.open)refresh().catch(e=>$('bobTradeReviewResults').textContent=e.message)});
    $('bobTradeSaleOcr').onclick=async()=>{
      const status=$('bobTradeSaleStatus');
      try{
        const file=$('bobTradeSaleImage').files[0];
        if(!file||!file.type.startsWith('image/')||file.size>8_000_000)throw Error('Bitte ein Bild bis 8 MB auswählen');
        if(!window.BobDegiro?.recognizePlainOcr)throw Error('Lokale Bilderkennung nicht verfügbar. Werte bitte selbst eingeben');
        status.textContent='Screenshot wird auf dem Gerät gelesen …';
        const result=await window.BobDegiro.recognizePlainOcr(file,'bobTradeSaleStatus');
        const raw=String(result?.data?.text||'');
        if(raw.length<30)throw Error('Screenshot nicht ausreichend lesbar');
        const selection=active.find(t=>t.id===$('bobTradeSaleSelect').value);
        const evidence=raw.match(/\\bDE[A-Z0-9]{10}\\b/i);
        if(evidence&&selection&&evidence[0].toUpperCase()!==selection.snapshot?.product?.isin)
          throw Error('Erkannte ISIN stimmt nicht mit dem gewählten Trade überein');
        const pick=(pattern)=>{const match=raw.match(pattern);return match?match[1]:null;};
        const decimal=value=>Number(value.replace(/\\s/g,'').replace(/\\./g,'').replace(',','.'));
        const fields={
          transactionId:pick(/Transaktions[-\\s]*ID[^0-9\\n]*([0-9]{5,14})/i),
          price:pick(/^\\s*Kurs\\s*(?:€|EUR)?\\s*([0-9][0-9.,]*)/im),
          saleValueCHF:pick(/^\\s*Wert\\s*CHF\\s*([0-9][0-9.,]*)/im),
          feesCHF:pick(/^\\s*Gesamtgebühr\\s*CHF\\s*-?\\s*([0-9][0-9.,]*)/im),
          saleNetCHF:pick(/^\\s*Gesamt\\s*CHF\\s*([0-9][0-9.,]*)/im),
          eurPerCHF:pick(/^\\s*Wechselkurs\\s*([0-9][0-9.,]*)/im)
        };
        const time=raw.match(/(?:Datum)\\s*(\\d{1,2}[./]\\d{1,2}[./]\\d{4})\\s+(\\d{2}:\\d{2}:\\d{2})/i);
        if(time)fields.executedLocal=time[1].replace(/\\//g,'.')+' '+time[2];
        let count=0;
        for(const [name,value] of Object.entries(fields)){
          if(value===null||value===undefined)continue;
          const input=$('bobTradeSaleFields').querySelector('[name='+name+']');
          if(!input)continue;
          const normalized=input.type==='number'?decimal(value):value;
          if(input.type==='number'&&!Number.isFinite(normalized))continue;
          input.value=normalized;count++;
        }
        status.textContent='OCR hat '+count+' Angaben vorausgefüllt. Bitte alle Werte mit dem DEGIRO-Beleg vergleichen. Keine automatische Freigabe.';
      }catch(error){status.textContent='OCR-Hinweis: '+error.message;}
    };
    $('bobTradeSaleSave').onclick=async()=>{
      const status=$('bobTradeSaleStatus');status.textContent='Prüfe Beleg …';
      try {
        const chosen=active.find(t=>t.id===$('bobTradeSaleSelect').value);
        if(!chosen)throw Error('Kein eindeutiger aktiver Echtgeld-Trade ausgewählt');
        const file=$('bobTradeSaleImage').files[0];
        if(!file || !file.type.startsWith('image/') || file.size>8_000_000)throw Error('Bitte Original-Screenshot bis 8 MB auswählen');
        if(!$('bobTradeSaleCheck').checked)throw Error('Ausführung erst nach eigener Prüfung bestätigen');
        const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
        const imageSha256=Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');
        const fields=readFields('bobTradeSaleFields',sale);
        const p=chosen.snapshot.product||{};
        const receipt={...fields,imageSha256,side:'SELL',isin:p.isin,quantity:p.quantity,
          exitReason:$('bobTradeSaleReason').value};
        await request('confirm-sale',{tradeId:chosen.id,userConfirmed:true,sale:receipt});
        status.textContent='Verkauf dokumentiert. Überwachung in Bob beendet.';
        $('bobTradeSaleCheck').checked=false;await refresh();
      } catch(e){status.textContent='Nicht gespeichert: '+e.message;}
    };
    return true;
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);
  else mount();
  let n=0;const timer=setInterval(()=>{n++;if(mount()||n>45)clearInterval(timer)},500);
})();
</script>
"""
