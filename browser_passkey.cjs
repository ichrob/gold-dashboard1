// Real Chromium WebAuthn + actual Python verification, isolated synthetic account.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const origin = 'https://bob-private-scanner.onrender.com';
const bridge = spawn('python', ['browser_passkey_bridge.py'], {stdio:['pipe','pipe','inherit']});
const pending = [];
createInterface({input:bridge.stdout}).on('line', line => pending.shift()(JSON.parse(line)));
function rpc(action, binding, payload = {}) {
  return new Promise(resolve => { pending.push(resolve); bridge.stdin.write(JSON.stringify({action,binding,payload,...(action === '_advance' ? payload : {})})+'\n'); });
}
(async()=>{
  const browser = await chromium.launch({headless:true});
  try {
    async function phone(binding) {
      const context = await browser.newContext({viewport:{width:360,height:800},isMobile:true,hasTouch:true});
      const page = await context.newPage();
      const errors=[]; page.on('pageerror', e=>errors.push(e.message));
      await context.route('**/*', async route=>{
        const url=new URL(route.request().url());
        if(url.origin !== origin) throw Error('Unexpected outbound request');
        if(url.pathname==='/passkey') return route.fulfill({contentType:'text/html',body:fs.readFileSync('passkey.html','utf8')});
        if(url.pathname==='/passkey.js') return route.fulfill({contentType:'text/javascript',body:fs.readFileSync('passkey.js','utf8')});
        if(url.pathname.startsWith('/api/passkey/')) {
          const result=await rpc(url.pathname.split('/').pop(),binding,route.request().postDataJSON());
          return route.fulfill({status:result.ok===false?403:200,contentType:'application/json',body:JSON.stringify(result)});
        }
        return route.abort();
      });
      const cdp=await context.newCDPSession(page);
      await cdp.send('WebAuthn.enable');
      await cdp.send('WebAuthn.addVirtualAuthenticator',{options:{protocol:'ctap2',transport:'internal',hasResidentKey:true,hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
      await page.goto(origin+'/passkey');
      await page.waitForFunction(()=>!document.getElementById('status').textContent.includes('geprüft'));
      return {page,context,errors};
    }
    async function enroll(page,name){
      await page.locator('#password').fill('test-password');
      await page.locator('#key-name').fill(name);
      await page.locator('#register').click();
      await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Bestätigt bis'));
    }
    const first=await phone('b'.repeat(64));
    await enroll(first.page,'Altes Handy');
    assert.equal(await first.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    const codes=(await first.page.locator('#codes').innerText()).trim().split('\n');
    assert.equal(codes.length,8);
    await first.page.locator('#ack-code').fill(codes[0]);
    await first.page.locator('#ack').click();
    await first.page.locator('#backup').waitFor({state:'hidden'});
    await rpc('_advance','b'.repeat(64),{seconds:86400});
    await first.page.reload();
    await first.page.locator('#verify').waitFor({state:'visible'});
    await first.page.locator('#verify').click();
    await first.page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Bestätigt bis'));
    const second=await phone('c'.repeat(64));
    await second.page.locator('#recovery summary').click();
    await second.page.locator('#code').fill(codes[0]);
    await second.page.locator('#recover').click();
    await second.page.locator('#setup').waitFor({state:'visible'});
    await enroll(second.page,'Neues Handy');
    second.page.on('dialog',d=>d.accept());
    await second.page.locator('#password').fill('test-password');
    await second.page.locator('#keys li').filter({hasText:'Altes Handy'}).getByRole('button').click();
    await second.page.waitForFunction(()=>document.querySelectorAll('#keys li').length===1);
    assert.equal((await rpc('status','b'.repeat(64))).verified,false);
    assert.equal((await rpc('recover','d'.repeat(64),{code:codes[0]})).ok,false);
    await second.page.locator('#password').fill('test-password');
    await second.page.locator('#rotate').click();
    await second.page.locator('#backup').waitFor({state:'visible'});
    const replacement=(await second.page.locator('#codes').innerText()).trim().split('\n');
    await second.page.locator('#ack-code').fill(replacement[0]);
    await second.page.locator('#ack').click();
    await second.page.locator('#backup').waitFor({state:'hidden'});
    assert.equal((await rpc('recover','e'.repeat(64),{code:codes[1]})).ok,false);
    assert.equal((await rpc('recover','f'.repeat(64),{code:replacement[0]})).ok,true);
    assert.deepEqual(first.errors,[]); assert.deepEqual(second.errors,[]);
    console.log('PASS: 360px layout, real virtual WebAuthn enrollment/authentication, fixed 24h expiry, recovery, replacement key, lost-key revocation, single-use codes and rotation. No production access; physical Android and connection dialog remain untested.');
  } finally {await browser.close();bridge.stdin.end();}
})().catch(e=>{console.error(e);bridge.kill();process.exitCode=1;});
