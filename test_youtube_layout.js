const fs=require('fs'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
for(const [key,id] of [['overview','youtubeOverview'],['manual','youtubeManualDetails'],['latest','youtubeLatest']]){
 assert(html.includes('id="'+id+'"'),key+' section must exist');
}
const order=['youtubeOverview','youtubeLatest','youtubeManual'].map(id=>html.indexOf('id="'+id+'"'));
assert(order[0]<order[1]&&order[1]<order[2]);
assert(html.includes('showLastVideos(\'Live-Abruf fehlgeschlagen\')'));
assert(html.includes('if(!r.items.length)return;'));
assert(html.includes('id="youtubeListStatus"'));
assert(html.includes('.slice(0,3).map(x=>({title:String(x.title||'), 'Browser must retain only three video links');
assert(html.includes('v.items.filter(x=>x&&isVideoUrl(x.url)).slice(0,3)'), 'Old browser caches must show at most three videos');
assert(html.includes('readVideos=new Set([...readVideos].filter(id=>latestVideoIds.includes(id)))'), 'Evicted read flags must be deleted');

assert(html.includes('Math.round((r.intervalSeconds||900)/60)'), 'YouTube refresh cadence must follow the server interval');
assert(html.includes("research:'YouTube'"));
assert(html.includes('r.mcoOutlook'), 'MCO heading must read the verified video direction, not consensus');
assert(!html.includes("c.textContent='MCO Markets · '+r.consensus"), 'Do not display independent-source consensus as MCO view');
assert(html.includes('MCO Markets · Noch nicht analysiert'), 'No video text must be labeled not analyzed');
assert(html.includes("['research','▶','YouTube']"));
assert(html.includes("count?'YouTube: '+count+' ungelesene Videos':'YouTube'"));
for(const id of ['goldResearchStatus','goldResearchCounts','goldResearchConsensus','goldResearchItems','goldResearchSources','youtubeScreenshotButton','youtubeScreenshotInput','youtubeResearchUrl','youtubeResearchAnalyze','youtubeResearchTranscript','youtubeResearchImport','youtubeResearchStatus']){
 assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id+' id must be unique');
}
assert(html.includes("document.addEventListener('click',e=>{if(e.target.closest?.('[data-view=\\\"research\\\"]'))load();});")||html.includes('[data-view="research"]'));
console.log('YouTube mobile navigation and grouped workflow labels OK');
