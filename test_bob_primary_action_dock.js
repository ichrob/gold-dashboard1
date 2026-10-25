'use strict';
// Regression for mobile primary-action docking. No DOM/browser permissions,
// network calls or DEGIRO interaction are exercised in this test.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('  // Mobile action dock:');
const end=html.indexOf('  function show(key,focus=true){',start);
assert(start>0&&end>start,'Stable view-specific mobile action dock installed before navigation');
const code=html.slice(start,end);
for(const needle of ["registerPinnedAction('problems','bobMobileHelpShare','bobMobileHelpFeedback')",
 "const pinnedActions=new Map()","primaryActionDock.hidden=false","primaryActionDock.replaceChildren(",
 "pinnedObserver.observe(nav);pinnedObserver.observe(primaryActionDock);"])assert(code.includes(needle),needle);
assert(!code.includes('.click()')&&!code.includes('fetch(')&&!code.includes('navigator.share('),
 'Dock must only move a pre-existing user-approved button, never automatically send');
assert(html.includes("showPinnedAction(key);if(focus)"),
 'Every new mobile navigation must re-evaluate the dock');
assert(html.includes('.bob-primary-action-dock{position:fixed;z-index:49;'),
 'Mobile primary action stays in the viewport above navigation');
assert(html.includes('bottom:calc(var(--bob-mobile-nav-height,80px) + 8px)'),
 'The dock uses measured navigation height rather than its old card position');
assert(html.includes('padding-bottom:calc(110px + var(--bob-primary-dock-space,0px))'),
 'Scrollable content must remain reachable behind the floating action');
class FakeNode {
 constructor(tag){
  this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;
  this.hidden=false;this.attributes={};this.events=0;
 }
 append(...elements){for(const child of elements){if(child.parentNode){child.parentNode.children=child.parentNode.children.filter(x=>x!==child);}
  this.children.push(child);child.parentNode=this;}}
 replaceChildren(...elements){for(const old of this.children)old.parentNode=null;this.children=[];this.append(...elements)}
 setAttribute(key,value){this.attributes[key]=value}
 get firstElementChild(){return this.children[0]||null}
 getBoundingClientRect(){return {height:this.hidden?0:this.tagName==='ASIDE'?108:74}}
}
const container=new FakeNode('div'),button=new FakeNode('button'),status=new FakeNode('p');
container.append(button,status);
const nav=new FakeNode('nav'),body=new FakeNode('body');
const styles={},handlers={};
const document={
 body,
 createElement:tag=>new FakeNode(tag),
 documentElement:{style:{setProperty:(k,v)=>{styles[k]=v}}}
};
const window={addEventListener:(name,handler)=>{handlers[name]=handler}};
const dict={bobMobileHelpShare:button,bobMobileHelpFeedback:status};
const context={document,window,nav,panels:{problems:{},trade:{},products:{}},
 byId:id=>dict[id],ResizeObserver:class{observe(){}},};
vm.createContext(context);
vm.runInContext(code+"\nglobalThis.api={dock:primaryActionDock,pins:pinnedActions,show:showPinnedAction,register:registerPinnedAction,align:alignPinnedAction};",context);
const dock=context.api.dock;
assert.equal(dock.hidden,true,'No action is shown on initial unconfigured screen');
assert.equal(body.children.includes(dock),true,'Dock lives outside redesignable content panels');
assert.equal(dock.children.length,0);
context.api.show('problems');
assert.equal(dock.hidden,false);
assert.strictEqual(dock.children[0],button,'Move existing audited button, not clone it');
assert.strictEqual(dock.children[1],status,'Keep actionable feedback visible');
assert.strictEqual(button.parentNode,dock);
assert.equal(styles['--bob-mobile-nav-height'],'74px');
assert.equal(styles['--bob-primary-dock-space'],'108px');
context.api.show('products');
assert.equal(dock.hidden,true,'Dock never overlays unrelated screens');
assert.equal(styles['--bob-primary-dock-space'],'0px');
context.api.show('problems');
assert.strictEqual(dock.children[0],button,'Returning to Problems reuses identical button');
const tradeButton=new FakeNode('button');
dict.tradeButton=tradeButton;
assert.equal(context.api.register('trade','tradeButton'),true,'Future design adds a view without changing dock code');
context.api.show('trade');
assert.equal(dock.children.length,1,'Exactly one primary action visible per view');
assert.strictEqual(dock.children[0],tradeButton);
assert.equal(button.parentNode,null,'Prior view action never remains active');
context.api.show('problems');
assert.strictEqual(dock.children[0],button,'Primary action returns after future view and layout switch');
assert.equal(context.api.register('unknown','tradeButton'),false,'Unregistered pages cannot control dock');
handlers.resize();
assert.equal(styles['--bob-primary-dock-space'],'108px');
console.log('Bob mobile dock: fixed location, original safe handler, correct view, resize, and redesign-independent registration passed');
