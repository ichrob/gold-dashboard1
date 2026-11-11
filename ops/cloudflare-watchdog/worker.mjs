// One clock for the existing watchdog; no market data or repair logic here.
export const REPO = 'ichrob/gold-dashboard1';
export const WORKFLOW = 382076329;
const BASE = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}`;
const PERIOD = 600_000;
const ACTIVE = ['queued', 'in_progress', 'waiting', 'pending', 'requested'];

function safeTransportCode(error) {
  // Only fixed categories are returned. Never log exception text, secret,
  // GitHub response body or request headers.
  const message = typeof error?.message === 'string' ? error.message : '';
  if (/invalid.*header|header.*invalid|invalid character/i.test(message)) return 'github_header_invalid';
  if (/different request|outside.*request context/i.test(message)) return 'github_request_context';
  if (/invalid.*url|url.*invalid/i.test(message)) return 'github_url_invalid';
  return 'github_network_unavailable';
}

// One bounded, tokenless probe for the actual Cloudflare->GitHub egress path.
// Operationally opt-in only while DISABLED. All results are fixed states,
// numeric HTTP statuses or allowlisted error codes; never retain response bodies.
// The durable marker is written BEFORE attempting remote I/O; no automatic retries.
export async function probeUnauthGitHub(storage, request = fetch, now = Date.now()) {
  const key = 'unauth-egress-probe-20261111-v1';
  let prior;
  try { prior = await storage.get(key); }
  catch { return { state: 'unauth_storage_unavailable' }; }
  if (prior) return { state: 'unauth_already_attempted' };
  try { await storage.put(key, { at: now, status: 'started' }); }
  catch { return { state: 'unauth_storage_unavailable' }; }
  // No credentials, no workflow launch, no external dependency or new service.
  // GitHub's fixed public /zen endpoint tests the same api.github.com host.
  const url = 'https://api.github.com/zen';
  let step = 'plain';
  try {
    let response = await request(url);
    if (!response || !Number.isInteger(response.status)) return { state: 'unauth_invalid_response', step };
    const plainStatus = response.status;
    step = 'headers';
    const headers = { Accept: 'application/vnd.github+json', 'User-Agent': 'bob-watchdog-clock' };
    response = await request(url, { headers });
    if (!response || !Number.isInteger(response.status)) return { state: 'unauth_invalid_response', step };
    const headerStatus = response.status;
    step = 'redirect';
    response = await request(url, { headers, redirect: 'manual' });
    if (!response || !Number.isInteger(response.status)) return { state: 'unauth_invalid_response', step };
    const redirectStatus = response.status;
    step = 'signal';
    response = await request(url, { headers, redirect: 'manual', signal: AbortSignal.timeout(5000) });
    if (!response || !Number.isInteger(response.status)) return { state: 'unauth_invalid_response', step };
    return { state: 'unauth_http_observed', plainStatus, headerStatus, redirectStatus, signalStatus: response.status };
  } catch (error) {
    return { state: 'unauth_fetch_failed', step, code: safeTransportCode(error) };
  }
}

export async function tick(env, storage, scheduledTime, now = Date.now(), request = fetch) {
  if (!Number.isSafeInteger(scheduledTime) || scheduledTime > now + 5000 || now - scheduledTime > 120_000) {
    throw new Error('invalid_or_stale_tick');
  }
  // Operator-only tokenless egress diagnostic; never dispatch in this mode.
  if (env.ENABLED !== 'true' && env.DIAG_UNAUTH === 'true') {
    return probeUnauthGitHub(storage, request, now);
  }
  // An unarmed clock may record Cron receipt without access to any GitHub credential.
  // This is not proof of a successful GitHub dispatch or its monitoring job.
  if (env.ENABLED !== 'true' && env.DRY_RUN !== 'true') {
    // Merely installing a Secret must NEVER start GitHub reads or noisy errors.
    return { state: env.GITHUB_TOKEN ? 'observation_only_disabled' : 'observation_only_no_token' };
  }
  if (!env.GITHUB_TOKEN) throw new Error('github_token_missing');
  // Chrome clipboard may include trailing whitespace; trim it without
  // disclosing the value. Only the expected fine-grained GitHub PAT shape
  // is eligible for an outbound Authorization header.
  const token = typeof env.GITHUB_TOKEN === 'string' ? env.GITHUB_TOKEN.trim() : '';
  if (!/^github_pat_[A-Za-z0-9_]{20,255}$/.test(token)) throw new Error('github_token_format_invalid');
  const slot = Math.floor(scheduledTime / PERIOD);
  let previous;
  try { previous = await storage.get('attempt'); }
  catch { throw new Error('clock_storage_unavailable'); }
  if (previous && (previous.slot >= slot || now - previous.at < PERIOD)) return { state: 'duplicate_suppressed' };
  let signal;
  try { signal = AbortSignal.timeout(18_000); }
  catch { throw new Error('clock_abort_unavailable'); }
  const headers = {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token}`,
    'X-GitHub-Api-Version': '2026-03-10',
    'User-Agent': 'bob-watchdog-clock',
  };
  // Redirects are never followed automatically with a bearer token:
  // Cloudflare may throw before returning HTTP when mode='error'.
  // In manual mode any 3xx is rejected as an ordinary non-2xx response.
  async function get(suffix) {
    let response;
    try { response = await request(BASE + suffix, { headers, signal, redirect: 'manual' }); }
    catch (error) { throw new Error(safeTransportCode(error)); }
    if (!response || typeof response.ok !== 'boolean') throw new Error('github_response_shape');
    if (!response.ok) throw new Error(`github_read_${response.status}`);
    try { return await response.json(); }
    catch { throw new Error('github_invalid_json'); }
  }
  const workflow = await get('');
  if (workflow.id !== WORKFLOW || workflow.state !== 'active') throw new Error('workflow_not_active');
  const lists = await Promise.all([...ACTIVE, 'success'].map(status =>
    get(`/runs?branch=main&status=${status}&per_page=1`)));
  for (const list of lists) {
    if (!Number.isSafeInteger(list.total_count) || list.total_count < 0 || !Array.isArray(list.workflow_runs)
        || (list.total_count === 0) !== (list.workflow_runs.length === 0)) throw new Error('inconsistent_run_list');
    for (const run of list.workflow_runs) {
      if (run.workflow_id !== WORKFLOW || run.head_branch !== 'main') throw new Error('unexpected_run');
    }
  }
  if (lists.slice(0, ACTIVE.length).some(list => list.total_count > 0)) return { state: 'run_already_active' };
  const last = lists.at(-1).workflow_runs[0];
  if (last) {
    const completed = Date.parse(last.updated_at);
    if (!Number.isFinite(completed) || last.status !== 'completed' || last.conclusion !== 'success') {
      throw new Error('invalid_success_record');
    }
    if (now - completed < PERIOD) return { state: 'recent_success', run_id: last.id };
  }
  // Explicit opt-in: an initial deployment only observes, it cannot dispatch.
  if (env.ENABLED !== 'true') return { state: 'dry_run_would_dispatch' };
  // Persist BEFORE sending: ambiguous timeout/restart must never retry this slot.
  const attempt = { slot, at: now, state: 'dispatch_uncertain' };
  await storage.put('attempt', attempt);
  let response;
  try {
    response = await request(BASE + '/dispatches', {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: 'main' }), signal, redirect: 'manual',
    });
  } catch {
    throw new Error('dispatch_outcome_unknown');
  }
  if (response.status !== 200 && response.status !== 204) {
    await storage.put('attempt', { ...attempt, state: 'dispatch_rejected', status: response.status });
    throw new Error(`github_dispatch_${response.status}`);
  }
  let runId = null;
  if (response.status === 200) {
    try { runId = (await response.json()).workflow_run_id ?? null; } catch { /* accepted; do not repeat */ }
  }
  const result = { ...attempt, state: 'dispatch_accepted', run_id: runId };
  await storage.put('attempt', result);
  return result;
}

// SQLite-backed DO storage supplies persistent serialization across invocations.
export class WatchdogClock {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; }
  async fetch(request) {
    return this.ctx.blockConcurrencyWhile(async () => {
      try {
        const { scheduledTime } = await request.json();
        const result = await tick(this.env, this.ctx.storage, scheduledTime);
        await this.ctx.storage.put('last_check', { at: Date.now(), ...result });
        console.log(JSON.stringify(result));
        return Response.json(result);
      } catch (error) {
        // Never log response bodies, headers, tokens or raw network exceptions.
        const message = /^(invalid_|inconsistent_|unexpected_|workflow_|github_|dispatch_|clock_)/.test(error.message)
          ? error.message : 'clock_check_failed';
        await this.ctx.storage.put('last_check', { at: Date.now(), state: 'error', code: message });
        console.error(message);
        return Response.json({ state: 'error', code: message }, { status: 502 });
      }
    });
  }
}

export default {
  async scheduled(event, env) {
    const stub = env.CLOCK.get(env.CLOCK.idFromName('bob-existing-watchdog'));
    const response = await stub.fetch('https://internal/tick', {
      method: 'POST', body: JSON.stringify({ scheduledTime: event.scheduledTime }),
    });
    if (!response.ok) throw new Error('clock_tick_failed');
  },
  fetch() { return new Response('Not found', { status: 404 }); },
};
