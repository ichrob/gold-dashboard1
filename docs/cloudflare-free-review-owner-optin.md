# Owner opt-in review via existing Cloudflare Workers Free AI

Date: 13 November 2026. This changes only the existing
bob-second-ai-review workflow's Python eligibility checks. It does not
create another Worker, AI binding, free API key, cron task, agent, or
paid-plan model. The existing Worker still requires signed GitHub OIDC
(main trusted workflow, fixed repository, RSA verification and audience).

An *ordinary*, same-repository PR by owner ichrob can receive one
independent, non-authoritative automated AI code review after successful
CI and only if its body contains exactly this marker:

    <!-- BOB_AI_REVIEW_OPT_IN_V1 -->

Existing known Bob repair-case markers continue to work unchanged.
Opt-in does NOT:
- permit forks, different authors or untrusted GitHub contexts;
- allow automatic review of draft PRs;
- allow stale CI or changed SHA;
- bypass filtering of public safe source patches;
- bypass existing at most two reviews per PR UTC day and one per SHA;
- authorize merges, orders, risk changes, credentials or private files.

A qualifying PR can remove the marker to stop future automatic review.
A missed or failed Cloudflare inference must not block core CI, production
signals or data collection. The Cloudflare Free plan allows 10,000
neurons/day; exceeding it fails instead of silently purchasing capacity.
No plan upgrade is authorized. A paid-only model must never be used.

The existing model is @cf/qwen/qwen2.5-coder-32b-instruct. Verify that
it remains available within Workers Free before use. AI suggestions
remain review comments and require independent tests.

Offline tests:
    python -m unittest test_ai_peer_review test_ai_peer_review_free test_ai_peer_review_research_optin test_bob_ai_quality_gate

Release acceptance: complete Bob CI, inspect the proposed PR diff, do
one opt-in review only on a reviewed, public, non-draft owner PR and
verify a real GitHub OIDC-signed review comment with no secret or raw
error leakage. Existing Workers OIDC and Free budget guards remain.
