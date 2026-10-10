const fs=require('fs'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
for(const [key,id] of [['overview','youtubeOverview'],['manual','youtubeManualDetails'],['latest','youtubeLatest']]){
 assert(html.includes('id="'+id+'"'),key+' section must exist');
}
const order=['youtubeOverview','youtubeManual','youtubeLatest'].map(id=>html.indexOf('id="'+id+'"'));
assert(order[0]<order[1]&&order[1]<order[2]);
assert(html.includes("research:'YouTube'"));
assert(html.includes("['research','▶','YouTube']"));
assert(html.includes("count?'YouTube: '+count+' ungelesene Videos':'YouTube'"));
for(const id of ['goldResearchStatus','goldResearchCounts','goldResearchConsensus','goldResearchItems','goldResearchSources','youtubeScreenshotButton','youtubeScreenshotInput','youtubeResearchUrl','youtubeResearchAnalyze','youtubeResearchTranscript','youtubeResearchImport','youtubeResearchStatus']){
 assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id+' id must be unique');
}
assert(html.includes("document.addEventListener('click',e=>{if(e.target.closest?.('[data-view=\\\"research\\\"]'))load();});")||html.includes('[data-view="research"]'));
console.log('YouTube mobile navigation and grouped workflow labels OK');
