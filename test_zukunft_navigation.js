// The Zukunft tab is a planning-only area, never an order execution switch.
const assert=require('assert'),fs=require('fs');
const html=fs.readFileSync('Bob.html','utf8');
const one=(s)=>html.split(s).length-1;
assert(html.includes("future:'Zukunft'"),'Zukunft must have a dedicated panel');
assert(html.includes("['future','◇','Zukunft','Pläne und Broker']"),'Zukunft must remain accessible from Mehr');
assert(html.includes("panels.future.append(futurePanel)"),'Roadmap must be mounted to its own panel');
assert.equal(one("futurePanel.id='bobFuturePlan'"),1,'The future roadmap must be unique');
const plan=html.split("futurePanel.innerHTML=`")[1]?.split("`;")[0];
assert(plan,'Future markup exists');
for(const heading of ['Strategien und Marktphasen','Gewinne schützen','Handelskosten','Strategielabor','Simulation und technische Sicherheit','offizieller Broker'])
 assert(plan.includes(heading),heading+' missing');
assert(plan.includes('kein Echtgeldhandel aktiviert'),'Make status visible');
assert(plan.includes('keine Kauf- oder Verkaufsaufträge'),'Do not imply live orders');
assert(plan.includes('gesonderter ausdrücklicher Freigabe'),'Real orders remain gated');
assert(!/onclick\s*=|<script|\bfetch\(|\/api\/order|\/api\/trade\/execute/i.test(plan),'No executable trading in future planning markup');
assert(html.includes('if(!panels[key])key=\'overview\''),'Existing view handler must be intact');
console.log('Zukunft tab: separate navigation, planned roadmap, no orders, and unchanged view isolation OK');
