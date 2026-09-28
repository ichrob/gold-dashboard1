/* Bob push manager: browser permission, PWA registration, dedupe and typed events. */
(function(){
  const KEY='bobPushV1';
  const defaults={registered:false,general:false,trade:false,activeTrade:false};
  function state(){try{return {...defaults,...JSON.parse(localStorage.getItem(KEY)||'{}')}}catch(_){return {...defaults}}}
  function save(s){localStorage.setItem(KEY,JSON.stringify(s));return s}
  async function enable(){if(!('Notification'in window))throw new Error('Web Notifications werden nicht unterstützt.');const p=await Notification.requestPermission();if(p!=='granted')throw new Error('Benachrichtigungen wurden nicht freigegeben.');let s=state();s.registered=true;save(s);if('serviceWorker'in navigator)await navigator.serviceWorker.register('/sw.js');return s}
  function allowed(kind){const s=state();return s.registered&&Notification.permission==='granted'&&s[kind]===true&&(kind!=='trade'||s.activeTrade===true)}
  function emit(kind,title,body,data={}){if(!allowed(kind))return false;const tag=`bob-${kind}-${data.signalId||'current'}`;if('serviceWorker'in navigator){navigator.serviceWorker.ready.then(r=>r.showNotification(title,{body,tag,data:{url:data.url||'/',kind,signalId:data.signalId||null}})).catch(()=>{});return true}try{new Notification(title,{body,tag})}catch(_){}return true}
  function set(kind,value){const s=state();s[kind]=Boolean(value);return save(s)}
  function setActiveTrade(value){return set('activeTrade',value)}
  window.BobPush={state,save,enable,allowed,emit,set,setActiveTrade};
})();
