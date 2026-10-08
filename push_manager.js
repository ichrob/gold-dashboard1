/* Bob Push Manager: browser notification + optional server Web Push registration. */
(function(){
  const KEY="bobPushV1", LEGACY="goldScannerPush";
  const PUSH_API="/api/push";
  const defaults={registered:false,serverRegistered:false,general:false,trade:false,activeTrade:false};
  function read(){
    try{
      const raw=localStorage.getItem(KEY);
      if(raw)return {...defaults,...JSON.parse(raw)};
      const old=localStorage.getItem(LEGACY);
      if(old)return {...defaults,...JSON.parse(old)};
    }catch(_){}
    return {...defaults};
  }
  function save(s){const next={...defaults,...s};try{localStorage.setItem(KEY,JSON.stringify(next));}catch(_){}return next;}
  function b64ToBytes(value){
    const pad="=".repeat((4-(value.length%4))%4);
    const raw=atob(value.replace(/-/g,"+").replace(/_/g,"/")+pad);
    return Uint8Array.from(raw,c=>c.charCodeAt(0));
  }
  async function registerServerPush(reg){
    try{
      const keyRes=await fetch(PUSH_API+"/vapid-public-key",{cache:"no-store"});
      if(!keyRes.ok)throw new Error("VAPID-Key konnte nicht geladen werden.");
      const {publicKey}=await keyRes.json();
      if(!publicKey)throw new Error("VAPID-Key fehlt.");
      if(!reg.pushManager)return false;
      // Recreate the browser subscription with the current VAPID public key.
      // This repairs subscriptions created with a previous VAPID key after a
      // server-side key rotation or a recreated push database.
      let sub=await reg.pushManager.getSubscription();
      if(sub){
        try{
          await fetch(PUSH_API+"/unsubscribe",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({endpoint:sub.endpoint})
          });
        }catch(_){}
        try{await sub.unsubscribe();}catch(_){}
        sub=null;
      }
      sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(publicKey)});
      const res=await fetch(PUSH_API+"/subscribe",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({subscription:sub.toJSON()})
      });
      if(!res.ok)throw new Error("Push-Subscription konnte nicht gespeichert werden.");
      return true;
    }catch(_){return false;}
  }
  async function enable(){
    if(!("Notification" in window))throw new Error("Web-Benachrichtigungen werden von diesem Browser nicht unterstützt.");
    const p=await Notification.requestPermission();
    if(p!=="granted")throw new Error("Benachrichtigungen wurden nicht freigegeben.");
    let serverRegistered=false;
    if("serviceWorker" in navigator){
      const reg=await navigator.serviceWorker.register("/sw.js",{updateViaCache:"none"});
      try{await reg.update();}catch(_){}
      serverRegistered=await registerServerPush(reg);
    }
    const next=save({...read(),registered:true,serverRegistered});syncWorkerPreferences();return next;
  }
  function state(){return read();}
  function allowed(kind){
    const s=read();
    return s.registered&&Notification.permission==="granted"&&s[kind]===true&&(kind!=="trade"||s.activeTrade===true);
  }
  let batch=null;
  const names={
    'signal-change':'EINSTIEG', 'reversal':'TRADE-WARNUNG · Richtungswechsel',
    'stop-hit':'TRADE-WARNUNG · Stop erreicht', 'stop-near':'TRADE-WARNUNG · Stop wird knapp',
    'target':'TRADE-WARNUNG · Ziel erreicht', 'target-extension':'TRADE-PLAN · Ziel erreicht – neues Ziel',
    'profit-protection':'TRADE-WARNUNG · Stop nachziehen', 'trailing-stop':'TRADE-WARNUNG · Stop nachziehen',
    'profit-weak':'TRADE-WARNUNG · Gewinn schützen'
  };
  function eventKind(title,data){
    const alias={'trade-close-recommendation':'reversal','trade-close-target':'target','profit-protection-warning':'profit-weak'};
    if(alias[data.kind])return alias[data.kind];
    if(data.kind==='active-trade-warning')return /erreicht/.test(title)?'stop-hit':'stop-near';
    if(/Stop-Loss anpassen/.test(title))return 'trailing-stop';
    return data.eventKind||data.kind||'';
  }
  function beginBatch(){if(!batch)batch=[];}
  async function flushBatch(){
    const items=batch;batch=null;if(!items?.length)return false;
    const priority={'ko-hit':0,'stop-hit':1,'personal-risk':2,'reversal':3,'data-unavailable':4,'stop-near':5,'target-extension':6,'target':7};
    items.sort((a,b)=>(priority[a.data.eventKind]??8)-(priority[b.data.eventKind]??8));
    const extended=items.some(x=>x.data.eventKind==='target-extension');
    const urgent=['ko-hit','stop-hit','reversal'].includes(items[0].data.eventKind);
    const advisory=['target','target-extension','trailing-stop','profit-protection','profit-weak','signal-change'];
    const visible=items.filter(x=>!(extended&&x.data.eventKind==='target')&&!(urgent&&advisory.includes(x.data.eventKind)));
    const first=visible[0];
    return emitNow(items.some(x=>x.kind==='trade')?'trade':first.kind,first.title,visible.map(x=>x.body).join(' | '),{...first.data,events:items.map(x=>x.data.eventKind)});
  }
  async function emit(kind,title,body,data={}){
    if(read().backgroundEnabled&&!data.test)return false;
    if(data.isin||/product|best.trade|produktempfehl|bester trade/i.test([kind,data.kind,title].join(' ')))return false;
    if(!data.test&&!allowed(kind))return false;
    const event=eventKind(title,data);data={...data,eventKind:event};
    if(!data.test&&names[event]){
      title=event==='signal-change'?'EINSTIEG · '+(['LONG','SHORT'].includes(data.direction)?data.direction:(body.match(/\b(LONG|SHORT)\b/)||['','NEUTRAL'])[1]):names[event];
      if(event==='signal-change'&&!body.startsWith('Neuer Einstieg:'))body='Neuer Einstieg: '+body+'. Keine Produktfreigabe.';
    }
    if(batch&&!data.test){batch.push({kind,title,body,data});return true;}
    return emitNow(kind,title,body,data);
  }
  async function emitNow(kind,title,body,data={}){
    if(read().backgroundEnabled&&!data.test)return false;
    // Generic notification calls must never bypass the dedicated server selection check.
    if(data.isin||/product|best.trade|produktempfehl|bester trade/i.test([kind,data.kind,title].join(' ')))return false;
    const testTrade=kind==="trade"&&data&&data.test===true;
    if(testTrade){
      const s=read();
      if(!(s.registered&&Notification.permission==="granted"&&s.trade===true))return false;
    }else if(!allowed(kind))return false;
    const tag="bob-"+kind+"-"+(data.signalId||"current");
    if(!data.test){
      const at=Number(data.candleClosedAt||data.dataAt);
      body+=' · Datenzeit: '+(at>0?new Date(at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'unbekannt')+'.';
    }
    if(data.test)title="TEST · "+title;
    else if(!/^(?:EINSTIEG|TRADE-WARNUNG|TRADE-PLAN|DATENSTATUS)/.test(title))title=(kind==="trade"?"TRADE-WARNUNG · ":"EINSTIEG · ")+title;
    const payload={title,body,data:{...data,url:data.url||"/",kind,signalId:data.signalId||null,tradeId:kind==="trade"?activeTradeId():null,expiresAt:data.expiresAt||Date.now()+180000},tag};
    if(!data.test&&typeof window.sendNtfy==="function")await window.sendNtfy(kind,title,body);
    let serverSent=false;
    if(read().serverRegistered){
      try{
        const res=await fetch("/api/push/send",{
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(payload)
        });
        if(res.ok){
          const result=await res.json().catch(()=>null);
          serverSent=Boolean(result&&result.sent>0);
          if(result&&result.vapidReset){
            const reg=await navigator.serviceWorker.ready;
            serverSent=await registerServerPush(reg);
            if(serverSent){
              const retry=await fetch("/api/push/send",{
                method:"POST",
                headers:{"Content-Type":"application/json"},
                body:JSON.stringify(payload)
              });
              if(retry.ok){
                const retryResult=await retry.json().catch(()=>null);
                serverSent=Boolean(retryResult&&retryResult.sent>0);
              }
            }
          }
        }
      }catch(_){}
    }
    if(serverSent)return true;
    const options={body,tag,data:payload.data,renotify:false};
    try{
      if("serviceWorker" in navigator){
        const reg=await navigator.serviceWorker.ready;
        await reg.showNotification(title,options);
        return true;
      }
      new Notification(title,options);
      return true;
    }catch(_){return false;}
  }
  function activeTradeId(){try{const t=JSON.parse(localStorage.getItem('goldScannerTradeMgmt')||'{}');return t.tradeId||t.fibonacciMonitor?.tradeId||null;}catch(_){return null;}}
  function syncWorkerPreferences(){
    if(!('serviceWorker' in navigator))return;
    navigator.serviceWorker.ready.then(reg=>reg.active?.postMessage({type:'BOB_PUSH_PREFERENCES',general:read().general===true,trade:read().trade===true,activeTrade:read().activeTrade===true,tradeId:activeTradeId()})).catch(()=>{});
  }
  let selectionBusy=false,selectionLastAt=0,selectionLastKey='',selectionGeneration=0;
  function productStatus(text){const el=typeof document!=='undefined'?document.getElementById('productPushStatus'):null;if(el)el.textContent=text;}
  async function updateSelection(evidence,flow){
    const s=read();
    if(!s.general){productStatus('Produktpush: aus – Marktsignale sind deaktiviert.');return false;}
    if(!s.serverRegistered||!allowed('general')){productStatus('Produktpush: Gerät für Server-Push registrieren.');return false;}
    const key=JSON.stringify([flow.direction,flow.groups.map(g=>[g.scope,g.candidates.map(p=>p.isin)]),flow.gateReasons]);
    if(selectionBusy||(key===selectionLastKey&&Date.now()-selectionLastAt<10000))return false;
    selectionBusy=true;const generation=selectionGeneration;
    try{
      const reg=await navigator.serviceWorker.ready,sub=await reg.pushManager.getSubscription();
      if(!sub||!read().general||generation!==selectionGeneration)return false;
      const payload={...evidence,capturedAt:Date.now(),endpoint:sub.endpoint};
      const res=await fetch('/api/push/selection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const result=res.ok?await res.json():null;
      if(generation!==selectionGeneration||!read().general)return false;
      selectionLastAt=Date.now();selectionLastKey=key;
      productStatus(!result?'Produktpush: Serverprüfung derzeit nicht erreichbar; keine neue Empfehlung.':result.disabled?'Produktpush: Marktsignale serverseitig aus – Einstellung erneut synchronisieren.':result.approvedCount?'Produktpush: '+result.approvedCount+' Produkt(e) serverseitig geprüft. '+(result.sent?'Benachrichtigung versandt.':'Unveränderte Auswahl / Wiederholung unterdrückt.'):'Produktpush: Abwarten – keine freigegebene Auswahl.');
      return Boolean(result?.sent);
    }catch(_){selectionLastAt=Date.now();selectionLastKey=key;productStatus('Produktpush: Serverprüfung nicht erreichbar; keine neue Empfehlung.');return false;}
    finally{selectionBusy=false;}
  }
  function set(kind,value){
    const next=save({...read(),[kind]:Boolean(value)});
    if(kind==='trade'||kind==='activeTrade')syncWorkerPreferences();
    if(kind==='general'){selectionGeneration++;selectionLastAt=0;selectionLastKey='';syncWorkerPreferences();}
    return next;
  }
  function setActiveTrade(value){return set("activeTrade",value);}
  window.BobPush={state,save,enable,allowed,emit,beginBatch,flushBatch,set,setActiveTrade,updateSelection,syncWorkerPreferences};
  syncWorkerPreferences();

  // Active-trade push monitor. This intentionally stays in the push layer:
  // it does not place orders or alter market/DEGIRO logic. It only triggers
  // the existing stop-management suggestion and a close recommendation when
  // the stored active-trade stop is actually breached.
  function activeTradePushMonitor(){
    try{
      const s=read();
      if(s.backgroundEnabled||!s.registered||!s.trade||!s.activeTrade)return;
      const raw=localStorage.getItem("goldScannerTradeMgmt");
      if(!raw)return;
      const t=JSON.parse(raw);
      if(!t?.active||!t?.dir||!Number.isFinite(Number(t.stop)))return;

      const priceEl=document.getElementById("tradePrice");
      const liveEl=document.getElementById("price");
      const p=Number(priceEl?.value)||Number.parseFloat(String(liveEl?.textContent||"").replace(",","."));
      if(!Number.isFinite(p))return;

      // Stop proximity/breach transitions are owned by maybePushAnalysisAlerts.
      // Keep a single alert producer; the second monitor only updates stops.
      // Let Bob's existing, tested stop model decide whether the stop can be
      // improved. The function itself emits "Stop-Loss anpassen" only when the
      // new stop is genuinely better, so normal price noise stays silent.
      const stopBtn=document.querySelector('button[onclick="suggestStopUpdate()"]');
      if(stopBtn && typeof window.suggestStopUpdate==="function"){
        stopBtn.click();
      }
    }catch(e){
      // Push monitoring must never interfere with the rest of Bob.
      console.warn("Bob active-trade push monitor",e);
    }
  }

  window.addEventListener("load",()=>{
    setTimeout(activeTradePushMonitor,1500);
    setInterval(activeTradePushMonitor,60000);
  });
})()