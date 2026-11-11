import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { tick, WORKFLOW } from './worker.mjs';

const now = Date.parse('2026-11-08T10:04:00Z');
function fixture(options = {}) {
  const data = new Map();
  const storage = { get: async key => data.get(key), put: async (key, val) => data.set(key, val) };
  const calls = [];
  const env = { GITHUB_TOKEN: 'github_pat_TEST_ONLY_01234567890123456789', ENABLED: 'true' };
  const request = async (url, init) => {
    calls.push({ url, init });
    if (options.networkError && init.method !== 'POST') throw new TypeError('private network details');
    if (options.headerError && init.method !== 'POST') throw new TypeError('Invalid character in header content Authorization');
    if (options.contextError && init.method !== 'POST') throw new TypeError('Cannot perform I/O on behalf of a different request');
    if (options.readError && init.method !== 'POST') return new Response('', { status: options.readError });
    if (options.invalidJson && init.method !== 'POST') return new Response('not-json', {status:200});
    if (url.endsWith('/dispatches')) {
      assert.equal(data.get('attempt').state, 'dispatch_uncertain');
      if (options.timeout) throw new Error('network exception with secret');
      return options.postStatus === 204 ? new Response(null, { status: 204 })
        : Response.json({ workflow_run_id: 123 }, { status: options.postStatus || 200 });
    }
    if (!url.includes('/runs?')) return Response.json({ id: WORKFLOW, state: options.disabled ? 'disabled_manually' : 'active' });
    const status = new URL(url).searchParams.get('status');
    if (options.malformed) return Response.json({ total_count: 1, workflow_runs: [] });
    const run = status === options.active ? { workflow_id: WORKFLOW, head_branch: 'main' }
      : status === 'success' && options.recent ? {
        workflow_id: WORKFLOW, head_branch: 'main', id: 12, status: 'completed', conclusion: 'success',
        updated_at: new Date(now - 60_000).toISOString(),
      } : null;
    return Response.json({ total_count: run ? 1 : 0, workflow_runs: run ? [run] : [] });
  };
  return { data, storage, env, request, calls, posts: () => calls.filter(c => c.init.method === 'POST') };
}
test('dispatches the fixed workflow/main and persists before network', async () => {
  const f = fixture();
  assert.equal((await tick(f.env, f.storage, now, now, f.request)).state, 'dispatch_accepted');
  assert.equal(f.posts().length, 1);
  assert.equal(f.posts()[0].init.body, '{"ref":"main"}');
  assert.match(f.posts()[0].url, /382076329\/dispatches$/);
});
for (const active of ['queued', 'in_progress', 'waiting', 'pending', 'requested']) {
  test(`does not dispatch over ${active} run`, async () => {
    const f = fixture({ active });
    assert.equal((await tick(f.env, f.storage, now, now, f.request)).state, 'run_already_active');
    assert.equal(f.posts().length, 0);
  });
}
test('recent success suppresses fallback', async () => {
  const f = fixture({ recent: true });
  assert.equal((await tick(f.env, f.storage, now, now, f.request)).state, 'recent_success');
  assert.equal(f.posts().length, 0);
});
test('dry run does not mutate dispatch ledger or start a run', async () => {
  const f = fixture(); f.env.ENABLED = 'false'; f.env.DRY_RUN = 'true';
  assert.equal((await tick(f.env, f.storage, now, now, f.request)).state, 'dry_run_would_dispatch');
  assert.equal(f.data.size, 0); assert.equal(f.posts().length, 0);
});
for (const options of [{ readError: 403 }, { readError: 429 }, { malformed: true }, { disabled: true }]) {
  test(`fails closed ${JSON.stringify(options)}`, async () => {
    const f = fixture(options);
    await assert.rejects(tick(f.env, f.storage, now, now, f.request));
    assert.equal(f.posts().length, 0);
  });
}
test('ambiguous timeout cannot dispatch same slot after restart', async () => {
  const f = fixture({ timeout: true });
  await assert.rejects(tick(f.env, f.storage, now, now, f.request), /dispatch_outcome_unknown/);
  assert.equal((await tick(f.env, f.storage, now, now + 60_000, f.request)).state, 'duplicate_suppressed');
  assert.equal(f.posts().length, 1);
});
test('accepted 204 and repeated tick dispatch only once', async () => {
  const f = fixture({ postStatus: 204 });
  await tick(f.env, f.storage, now, now, f.request);
  assert.equal((await tick(f.env, f.storage, now, now, f.request)).state, 'duplicate_suppressed');
  assert.equal(f.posts().length, 1);
});
test('disabled Cron with a saved secret stays entirely offline', async () => {
  const f = fixture(); f.env.ENABLED = 'false';
  assert.equal((await tick(f.env, f.storage, now, now, f.request)).state, 'observation_only_disabled');
  assert.equal(f.calls.length, 0); assert.equal(f.data.size, 0);
});
for (const options of [{networkError:true,expected:'github_network_unavailable'},
                       {headerError:true,expected:'github_header_invalid'},
                       {contextError:true,expected:'github_request_context'},
                       {invalidJson:true,expected:'github_invalid_json'}]) {
  test(`read errors are classified safely: ${options.expected}`, async () => {
    const f = fixture(options);
    await assert.rejects(tick(f.env,f.storage,now,now,f.request),
      new RegExp(options.expected));
    assert.equal(f.posts().length,0);
  });
}
test('disabled Cron without secret reports observation only', async () => {
  const f = fixture(); f.env.GITHUB_TOKEN = undefined; f.env.ENABLED = 'false';
  assert.equal((await tick(f.env, f.storage, now, now, f.request)).state, 'observation_only_no_token');
  assert.equal(f.calls.length, 0); assert.equal(f.data.size, 0);
});
test('fine-grained token whitespace is trimmed before remote use', async () => {
  const f = fixture();
  const original = f.env.GITHUB_TOKEN;
  f.env.GITHUB_TOKEN = ' \n' + original + '\r\n';
  assert.equal((await tick(f.env,f.storage,now,now,f.request)).state,'dispatch_accepted');
  const request = f.calls.find(x => x.url.includes('/actions/workflows/'));
  assert.equal(request.init.headers.Authorization,'Bearer '+original);
});
test('malformed GitHub token fails before any network access', async () => {
  const f = fixture();
  f.env.GITHUB_TOKEN = 'Bearer\nprivate\rtext';
  await assert.rejects(tick(f.env,f.storage,now,now,f.request),/github_token_format_invalid/);
  assert.equal(f.calls.length,0);
});
test('stale tick and enabled clock without secret cannot send', async () => {
  const f = fixture();
  await assert.rejects(tick(f.env, f.storage, now - 180_000, now, f.request));
  f.env.GITHUB_TOKEN = undefined;
  await assert.rejects(tick(f.env, f.storage, now, now, f.request), /github_token_missing/);
  assert.equal(f.calls.length, 0);
});
test('public HTTP requests never trigger dispatch', async () => {
  assert.equal((await worker.fetch()).status, 404);
});
