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
    return save({...read(),registered:true,serverRegistered});
  }
  function state(){return read();}
  function allowed(kind){
    const s=read();
    return s.registered&&Notification.permission==="granted"&&s[kind]===true&&(kind!=="trade"||s.activeTrade===true);
  }
  async function emit(kind,title,body,data={}){
    const testTrade=kind==="trade"&&data&&data.test===true;
    if(testTrade){
      const s=read();
      if(!(s.registered&&Notification.permission==="granted"&&s.trade===true))return false;
    }else if(!allowed(kind))return false;
    const tag="bob-"+kind+"-"+(data.signalId||"current");
    const payload={title,body,data:{...data,url:data.url||"/",kind,signalId:data.signalId||null},tag};
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
    const options={body,tag,data:{url:data.url||"/",kind,signalId:data.signalId||null},renotify:false};
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
  function set(kind,value){return save({...read(),[kind]:Boolean(value)});}
  function setActiveTrade(value){return set("activeTrade",value);}
  window.BobPush={state,save,enable,allowed,emit,set,setActiveTrade};

  // Active-trade push monitor. This intentionally stays in the push layer:
  // it does not place orders or alter market/DEGIRO logic. It only triggers
  // the existing stop-management suggestion and a close recommendation when
  // the stored active-trade stop is actually breached.
  function activeTradePushMonitor(){
    try{
      const s=read();
      if(!s.registered||!s.trade||!s.activeTrade)return;
      const raw=localStorage.getItem("goldScannerTradeMgmt");
      if(!raw)return;
      const t=JSON.parse(raw);
      if(!t?.active||!t?.dir||!Number.isFinite(Number(t.stop)))return;

      const priceEl=document.getElementById("tradePrice");
      const liveEl=document.getElementById("price");
      const p=Number(priceEl?.value)||Number.parseFloat(String(liveEl?.textContent||"").replace(",","."));
      if(!Number.isFinite(p))return;

      const stop=Number(t.stop);
      const breached=(t.dir==="LONG"&&p<=stop)||(t.dir==="SHORT"&&p>=stop);
      if(breached){
        const key="bobPushStopBreach";
        const prior=localStorage.getItem(key);
        const marker=t.dir+":"+stop.toFixed(4)+":"+Math.floor(Date.now()/600000);
        if(prior!==marker){
          localStorage.setItem(key,marker);
          emit("trade","Bob – Trade schließen",
            "Stop-Loss erreicht/überschritten · "+t.dir+" · Kurs "+p.toFixed(2)+" · Stop "+stop.toFixed(2),
            {kind:"trade-close",signalId:"close:"+marker});
        }
        return;
      }

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