export default async ({ page, context }) => {
  const { videoId, moments } = context;
  if (!/^[A-Za-z0-9_-]{11}$/.test(videoId) || !Array.isArray(moments) || moments.length > 3) {
    return {data:{frames:[]},type:'application/json'};
  }
  const frames=[];
  await page.setViewport({width:800,height:600});
  page.setDefaultTimeout(12000);
  try {
    await page.goto(`https://www.youtube.com/watch?v=${videoId}`, {waitUntil:'domcontentloaded',timeout:25000});
    // Ordinary playback only. No login, proxy, CAPTCHA handling or bypass.
    const reject=await page.$('button[aria-label="Reject all"]');
    if (reject) await reject.click();
    await page.waitForFunction(() => {
      const v=document.querySelector('video');
      return v && v.readyState>=2 && v.videoWidth>0 && !document.querySelector('.ad-showing');
    });
    const actual=await page.evaluate(() => document.querySelector('#movie_player')?.getVideoData?.().video_id);
    if(actual!==videoId)return {data:{frames:[]},type:'application/json'};
    for(const moment of moments){
      if(!Number.isFinite(moment.at)||moment.at<0||moment.at>86400)break;
      await page.evaluate(at=>{const v=document.querySelector('video');v.pause();v.currentTime=at;},moment.at);
      await page.waitForFunction(at=>{const v=document.querySelector('video');return v&&!v.seeking&&v.readyState>=2&&Math.abs(v.currentTime-at)<0.5&&!document.querySelector('.ad-showing');},{timeout:10000},moment.at);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const video=await page.$('video');
      const data=await video.screenshot({type:'jpeg',quality:65,encoding:'base64'});
      const at=await page.evaluate(()=>document.querySelector('video').currentTime);
      frames.push({at,dataUrl:'data:image/jpeg;base64,'+data});
    }
  } catch { /* Return only bounded evidence, never raw provider error details. */ }
  return {data:{videoId,frames},type:'application/json'};
};
