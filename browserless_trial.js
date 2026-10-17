export default async ({ page, context }) => {
  const { videoId, moments } = context;
  const frames=[];
  const reply=(status)=>({data:{videoId,status,frames:status==='captured'?frames:[]},type:'application/json'});
  if (!/^[A-Za-z0-9_-]{11}$/.test(videoId) || !Array.isArray(moments) || moments.length > 3) return reply('identity-unconfirmed');
  await page.setViewport({width:800,height:600});
  page.setDefaultTimeout(10000);
  let stage='navigation-failed';
  try {
    await page.goto(`https://www.youtube.com/watch?v=${videoId}`, {waitUntil:'domcontentloaded',timeout:25000});
    // Ordinary playback only. Never solve a challenge or bypass access restrictions.
    const reject=await page.$('button[aria-label="Reject all"],button[aria-label="Alle ablehnen"]');
    if (reject) await reject.click();
    if(new URL(page.url()).hostname==='consent.youtube.com')return reply('consent-required');
    stage='player-unavailable';
    await page.waitForSelector('#movie_player');
    const blocked=await page.evaluate(()=>{
      const text=document.querySelector('#movie_player')?.innerText||'';
      return /confirm you.re not a bot|bestätigen.*kein bot|sign in to confirm|video unavailable|video nicht verfügbar/i.test(text);
    });
    if(blocked)return reply('access-blocked');
    const actual=await page.evaluate(()=>{
      const p=document.querySelector('#movie_player');
      return p?.getVideoData?.().video_id || p?.getPlayerResponse?.()?.videoDetails?.videoId || '';
    });
    if(actual!==videoId)return reply('identity-unconfirmed');
    stage='playback-unavailable';
    await page.evaluate(()=>{const v=document.querySelector('video');if(v){v.muted=true;v.play().catch(()=>{});}});
    const skip=await page.$('.ytp-skip-ad-button,.ytp-ad-skip-button');
    if(skip){try{await skip.click();}catch{}}
    await page.waitForFunction(() => {
      const v=document.querySelector('video');
      return v && v.readyState>=2 && v.videoWidth>0 && !document.querySelector('.ad-showing');
    },{timeout:15000});
    for(const moment of moments){
      if(!Number.isFinite(moment.at)||moment.at<0||moment.at>86400)return reply('seek-failed');
      stage='seek-failed';
      await page.evaluate(at=>{const v=document.querySelector('video');v.pause();v.currentTime=at;},moment.at);
      await page.waitForFunction(at=>{const v=document.querySelector('video');return v&&!v.seeking&&v.readyState>=2&&Math.abs(v.currentTime-at)<0.5&&!document.querySelector('.ad-showing');},{timeout:7000},moment.at);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      // Recheck identity immediately before each image, including after advertisements.
      const verified=await page.evaluate(id=>{const p=document.querySelector('#movie_player');return (p?.getVideoData?.().video_id||p?.getPlayerResponse?.()?.videoDetails?.videoId)===id&&!p.classList.contains('ad-showing');},videoId);
      if(!verified)return reply('identity-unconfirmed');
      stage='screenshot-failed';
      const video=await page.$('video');
      const data=await video.screenshot({type:'jpeg',quality:65,encoding:'base64'});
      const at=await page.evaluate(()=>document.querySelector('video').currentTime);
      frames.push({at,dataUrl:'data:image/jpeg;base64,'+data});
    }
    return reply('captured');
  } catch { return reply(stage); }
};
