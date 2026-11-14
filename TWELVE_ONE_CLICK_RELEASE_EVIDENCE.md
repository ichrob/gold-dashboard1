# Twelve Data: release evidence checklist (manual one-shot only)

Status: **BLOCKED**. This document does not grant permission, set an environment flag, or schedule a request. PR #1636 and the stacked safety-test PR #1722 remain isolated from Bob production.

## Gate 1: full tests
- Exact PR-head SHA: run the complete Bob CI, risk, security and repair checks; store URLs, SHA, conclusions.
- Run `python -m unittest -v test_twelve_research_one_click test_twelve_research_extension test_twelve_research_storage_bridge` in an isolated, keyless test environment.
- Verify localhost Host/Origin/CSRF denial, GET no side effect, single use after failure, five-minute idle expiry, disabled button and no price/secret output.
- **No release** if any check is absent, skipped unexpectedly, or fails.

## Gate 2: free-account quota
- Identify *all* processes/devices consuming the same Basic account before asserting exclusive use.
- Verify a durable, exclusive transaction/lock and account-wide shared quota ledger. The current local SQLite budget (7/min, 700/day) alone cannot establish account-wide safety.
- Verify actual provider credit cost and response headers with a specifically authorized single request **only after all other gates**; deny when uncertain.
- No cron, periodic polling, retries, paid upgrades or fallback into live feeds.

## Gate 3: private archive
- Verify persistent encrypted research storage, recovery and access controls independently; an ephemeral Render filesystem is not sufficient.
- Aiven SQL health is read-only and does not prove a safe writable quota ledger or host RAM.
- Test the existing Bob runtime's Drive OAuth scope on the dedicated private folder with synthetic encrypted data, independent download and authenticated restore. ChatGPT's Drive access does not establish Bob runtime access.
- Keep all provider OHLC, indicators and timestamps out of Bob Handy/Web, push, public logs, trading engine and DEGIRO execution.

## Gate 4: retention
- Name an accountable owner for account termination/access revocation.
- Implement and test raw-data deletion within 30 days of lost access, including copies, backups and Drive artifacts, with auditable deletion receipts. Fail closed if deletion cannot be guaranteed.
- Do not delete original trading evidence or unrelated Bob archives.

## Gate 5: one real evaluation
- Only after Gates 1–4: confirm user-authorized, documented free Basic scope, operator-only environment and verified credential without exposing the key.
- Perform **one** bounded manual XAU/USD request, validate original timestamps, response metadata, credits and private storage. No automatic repeat on failure.
- Provider HTTP success alone is not a licence or proof of quota compliance.

## Gate 6: local button release
- Require all signed evidence before release flags are set; flags themselves are not evidence.
- Button must remain localhost-only, single-use and non-display; **do not put licensed output in Bob Handy/Web** under Basic.
- Confirm no paid services, no ongoing background jobs and no trade/order change.
- If any gate is unresolved, the correct outcome is **BLOCKED**, not a partial production release.
