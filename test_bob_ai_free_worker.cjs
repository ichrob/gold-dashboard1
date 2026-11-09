/* Security tests for Cloudflare Free AI worker; no real AI calls. */
const assert = require("node:assert/strict");
const {generateKeyPairSync, sign} = require("node:crypto");
const {pathToFileURL} = require("node:url");
const path = require("node:path");

(async () => {
  const worker = await import(pathToFileURL(path.join(__dirname, "bob_ai_free_worker.mjs")).href);
  assert.match(worker.REVIEW_POLICY,/TEILAUSSCHNITT/);
  assert.match(worker.REVIEW_POLICY,/NameError/);
  assert.match(worker.REVIEW_POLICY,/unbestätigt/);
  const {privateKey, publicKey} = generateKeyPairSync("rsa", {modulusLength: 2048});
  const jwk = publicKey.export({format:"jwk"});
  Object.assign(jwk, {kid:"test-key",alg:"RS256",use:"sig"});
  const b64 = value => Buffer.from(JSON.stringify(value)).toString("base64url");
  const now = Math.floor(Date.now()/1000);
  const claims = {
    iss:"https://token.actions.githubusercontent.com",
    aud:worker.AUDIENCE, repository:"ichrob/gold-dashboard1",
    repository_owner:"ichrob", ref:"refs/heads/main",
    workflow_ref:"ichrob/gold-dashboard1/.github/workflows/bob-second-ai-review.yml@refs/heads/main",
    event_name:"workflow_run", iat:now, exp:now+240
  };
  const jwt = overrides => {
    const msg = b64({kid:"test-key",alg:"RS256",typ:"JWT"})+"."+b64({...claims,...overrides});
    return msg+"."+sign("RSA-SHA256",Buffer.from(msg),privateKey).toString("base64url");
  };
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    assert.equal(url,"https://token.actions.githubusercontent.com/.well-known/jwks");
    assert.equal(options?.redirect,"manual");
    return Response.json({keys:[jwk]});
  };
  try {
    assert.equal(await worker.verifyGithubOIDC(jwt({})),true);
    assert.equal(await worker.verifyGithubOIDCDetail(jwt({})), "ok");
    // A malicious or unexpected JWKS redirect must NOT be followed.
    let lookedAtRedirect = false;
    const redirectJwks = async (url, options) => {
      assert.equal(url,"https://token.actions.githubusercontent.com/.well-known/jwks");
      assert.equal(options.redirect,"manual");
      lookedAtRedirect = true;
      return new Response(null,{status:302,headers:{location:"https://evil.example/keys"}});
    };
    assert.equal(await worker.verifyGithubOIDCDetail(jwt({}),redirectJwks),"jwks-http");
    assert.equal(lookedAtRedirect,true);
    const failingJwks = async () => {throw new Error("never-print-this-secret");};
    assert.equal(await worker.verifyGithubOIDCDetail(jwt({}), failingJwks), "exception-jwks-fetch");
    assert.equal(await worker.verifyGithubOIDCDetail(jwt({aud:"wrong"})), "claim-audience");
    assert.equal(await worker.verifyGithubOIDCDetail(jwt({workflow_ref:"wrong"})), "claim-workflow");
    assert.equal(await worker.verifyGithubOIDCDetail(jwt({repository:"wrong/other"})), "claim-repository");
    for(const overrides of [
      {aud:"else"},{repository:"attacker/repo"},{ref:"refs/heads/feature"},
      {workflow_ref:"ichrob/gold-dashboard1/.github/workflows/ci.yml@refs/heads/main"},
      {exp:now-30},{iat:now-1000},{event_name:"push"}
    ]) assert.equal(await worker.verifyGithubOIDC(jwt(overrides)),false);
    const forged=jwt({});
    assert.equal(await worker.verifyGithubOIDC(forged.slice(0,-2)+"AA"),false);
    assert.equal(await worker.verifyGithubOIDC("Bearer fake"),false);
    const diff="FILE: server.py\n@@ -1 +1 @@\n-x()\n+y()";
    assert.equal(worker.validReviewRequest({pr:42,sha:"a".repeat(40),diff}),true);
    assert.equal(worker.validReviewRequest({pr:42,sha:"a".repeat(40),diff:diff+"\n+api_key=private"}),false);
    const calls=[];
    const env={AI:{run: async (...args)=>{calls.push(args);return {response:"Prüfung: kein klarer Fehler."}}}};
    const create=(token,payload)=>new Request("https://bob-test.workers.dev/review",{
      method:"POST", headers: {"authorization":"Bearer "+token,"content-type":"application/json"},
      body:JSON.stringify(payload)
    });
    const noToken=await worker.default.fetch(create("fake",{pr:42,sha:"a".repeat(40),diff}),env);
    assert.equal(noToken.status,401);assert.equal(calls.length,0);
    const wrongClaim = await worker.default.fetch(create(jwt({workflow_ref:"other"}),{pr:42,sha:"a".repeat(40),diff}),env);
    assert.equal(wrongClaim.status,401);
    assert.equal(wrongClaim.headers.get("x-bob-oidc-check"),"claim-workflow");
    assert.equal(JSON.stringify(await wrongClaim.json()).includes("other"),false);
    assert.equal(calls.length,0);
    const badPayload=await worker.default.fetch(create(jwt({}),{pr:42,sha:"a".repeat(40),diff:"SECRET=oops"}),env);
    assert.equal(badPayload.status,400);assert.equal(calls.length,0);
    const okay=await worker.default.fetch(create(jwt({}),{pr:42,sha:"a".repeat(40),diff}),env);
    assert.equal(okay.status,200);
    assert.equal((await okay.json()).response,"Prüfung: kein klarer Fehler.");
    assert.equal(calls.length,1);
    assert.equal(calls[0][0],worker.MODEL);
    assert.equal(calls[0][1].messages[0].content,worker.REVIEW_POLICY);
    console.log("Cloudflare OIDC AI worker security tests OK");
  } finally {
    globalThis.fetch=oldFetch;
  }
})().catch(e=>{console.error(e);process.exitCode=1});
