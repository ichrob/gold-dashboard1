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
      let sub=await reg.pushManager.getSubscription();
      if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(publicKey)});
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
})();