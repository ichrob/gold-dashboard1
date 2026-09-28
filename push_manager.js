/* Bob Push Manager: one canonical browser-notification path, PWA-safe and state-migrating. */
(function(){
  const KEY="bobPushV1", LEGACY="goldScannerPush";
  const defaults={registered:false,general:false,trade:false,activeTrade:false};
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
  async function enable(){
    if(!("Notification" in window))throw new Error("Web-Benachrichtigungen werden von diesem Browser nicht unterstützt.");
    const p=await Notification.requestPermission();
    if(p!=="granted")throw new Error("Benachrichtigungen wurden nicht freigegeben.");
    if("serviceWorker" in navigator){
      const reg=await navigator.serviceWorker.register("/sw.js",{updateViaCache:"none"});
      try{await reg.update();}catch(_){}
    }
    const s=save({...read(),registered:true});
    return s;
  }
  function state(){return read();}
  function allowed(kind){
    const s=read();
    return s.registered&&Notification.permission==="granted"&&s[kind]===true&&(kind!=="trade"||s.activeTrade===true);
  }
  async function emit(kind,title,body,data={}){
    if(!allowed(kind))return false;
    const tag="bob-"+kind+"-"+(data.signalId||"current");
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