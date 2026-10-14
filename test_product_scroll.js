const assert=require('assert'),fs=require('fs'),vm=require('vm');
const ctx={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const preserve=ctx.window.BobDegiro.preserveReadingPosition;
assert.equal(preserve(()=>42),42); // Non-browser callers remain supported.
let current,position;
const body={};
const root={id:'products',tagName:'DIV',parentElement:body,children:[],contains:()=>true,
 closest:s=>s==='[id]'?root:null,querySelectorAll:()=>root.children,getBoundingClientRect:()=>({top:-100}),getClientRects:()=>[1]};
function card(isin,top){
 const c={tagName:'DIV',parentElement:root,children:[],getAttribute:()=>isin,
 closest:s=>s==='[id]'?root:c,getBoundingClientRect:()=>({top}),getClientRects:()=>[1]};
 const child={tagName:'P',parentElement:c,children:[],closest:s=>s==='[id]'?root:c,
 getBoundingClientRect:()=>({top:top+30}),getClientRects:()=>[1]};c.children=[child];return c;
}
ctx.document={body,documentElement:{style:{overflowAnchor:'auto'}},elementFromPoint:()=>current,
 getElementById:()=>root};
Object.assign(ctx.window,{scrollX:0,scrollY:500,innerWidth:400,innerHeight:800,scrollTo:p=>{position=p;}});
root.children=[card('A',80),card('B',500)];current=root.children[0].children[0];
assert.equal(preserve(()=>{root.children=[card('B',50),card('A',280)];return 'updated';}),'updated');
assert.equal(position.top,700); // Same ISIN and paragraph, despite ranking change.
assert.equal(position.behavior,'instant');assert.equal(ctx.document.documentElement.style.overflowAnchor,'auto');
current=root.children[1].children[0];ctx.window.scrollY=700;
preserve(()=>{root.children=[card('A',180)];});assert.equal(position.top,600); // Shrinking content above.
current=root.children[0].children[0];
assert.throws(()=>preserve(()=>{throw Error('render failed');}),/render failed/);
assert.equal(ctx.document.documentElement.style.overflowAnchor,'auto');
console.log('Product refresh preserves reading position across replacement, reorder and height changes');
