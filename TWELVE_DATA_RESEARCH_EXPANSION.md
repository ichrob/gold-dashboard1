# Twelve Data Basic: manual internal-research extensions (13 Nov 2026)

**Status: draft review branch, not merged, not deployed, not scheduled.**
Existing `gold_fallback.py`, Bob's primary quote feeds, original trading
decisions, DEGIRO product evidence, and all mobile/web displays remain unchanged.

## What Twelve Data explicitly confirmed in writing on 12–13 Nov 2026

The provider's 03:45 and 21:05 UTC emails to Bob's project mailbox say:

- Free **Basic** supports occasional XAU/USD historical OHLC retrieval for
  internal **non-display evaluation** at 1min, 5min, 15min, 30min, 1h, 1day.
  Gold is a perpetual **trial symbol**, not an expiring upgrade.
- The written 13 Nov follow-up confirms all four **EUR/USD, USD/CHF, EUR/CHF, CHF/EUR** pairs for occasional manual non-display evaluation. Each FX pair and interval still needs one-off opt-in and valid UTC source-time metadata. FX daily remains disabled until its own daily calendar is verified.
- The same follow-up confirms XAU/USD **4h** and **8h**, plus `/earliest_timestamp` at **1 credit** per request. XAU/USD daily date labels use **Australia/Sydney**, even when timezone=UTC is requested. The adapter preserves real Sydney midnight UTC instants, including DST transitions.
- Local EMA/MACD/RSI/ATR computation from permitted historical data for private
  **non-display** internal research is okay. The vendor's own indicator
  endpoints also exist on Basic, but credit weights require individual
  verification; this adapter calls **none** of those endpoints.
- Private raw archives can exist while the Basic account is active.
  Raw copies must be deleted within **30 days after account closure or
  loss of access**. Results may remain only if they do not reconstruct
  the original licensed bars. This draft does not automate deletion and
  therefore must not become a permanent archive without a retention owner.
- The free Basic tier is for **evaluation**, not a regularly scheduled,
  unattended backend research service. **Any continuous/scheduled use needs a
  paid plan**, which Bob is forbidden from activating.
- Displaying Twelve Data bars, derived indicators or other licensed results
  in a personal password-protected Bob web/mobile app is **not permitted** on
  Basic. Research data must not pass into Bob's live trading engine, public
  endpoints, private dashboards or user notifications.
- Documented Basic quota: 8 credits per minute and 800 per day. A separate
  local ledger caps this adapter's manual calls at 7/min and 700/day,
  but **does not know other consumers of the same Twelve Data account**.
  It is not a substitute for provider-side quota checks.

See the original project email thread, not an inferred licence from HTTP 200.
Public documentation: https://support.twelvedata.com/en/articles/5656039-how-to-get-historical-prices
and https://support.twelvedata.com/en/articles/5615854-credits .

## What is implemented in this isolated draft

`twelve_research_extension.py` provides:

1. Explicit authorization gating. Gold's eight confirmed intervals
   (1min, 5min, 15min, 30min, 1h, 4h, 8h, 1day) require the global
   `BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED=1` manual opt-in. EUR/USD,
   USD/CHF, EUR/CHF and CHF/EUR need a **separate flag per symbol/interval**.
   FX daily is blocked until its own calendar timezone is established.
2. Manual one-shot, no-retry `/time_series` queries with UTC source metadata
   for intraday or Sydney calendar proof for XAU/USD daily; closed-bar,
   OHLC, interval, duplicate, gap and size checks.
   Date-bounded queries **omit outputsize** to avoid response truncation.
   Original revisions are stored independently, identified by hash.
   Missing leading, trailing and entire-window bars are explicitly reported
   as **unverified** missing ranges; a no-bar response is `NO_BARS`, not success.
3. Manual one-shot `/earliest_timestamp` queries, stored privately per
   symbol/interval. Command output says only whether it succeeded; it never
   prints licensed timestamps or actual prices.
4. Internal-only EMA, MACD, RSI, ATR and a gross XAU/USD spot-reference
   movement comparison, **not** hypothetical product execution or EUR P&L.
5. An optional strictly same-source/same-time EUR/USD × USD/CHF synthetic
   EUR/CHF conversion, and its reciprocal CHF/EUR. A gap, unequal timeframe,
   unequal history, missing provenance or nonpositive price fails closed.
   Synthetic FX is **not** an executable market quotation or proof of DEGIRO
   availability.
6. SQLite call ledger and research-only local archive. There are no API routes,
   UI writes, cron jobs, subscriptions, auto-retries, account upgrades, orders
   or production fallback switches.

A successfully built or unit-tested adapter **does not establish** that a
licensed production data feed is working. The last authenticated historical
XAU/USD 1h probe was separate from this draft.

## Manual evaluation (not for scheduled background execution)

Use an existing Basic account's key via a private process environment
(`TWELVEDATA_API_KEY`); **never** paste it into issues, logs, chat or screenshots.
All adapter requests send it using Twelve Data's documented HTTP
`Authorization` header, **not** the URL query string.
Use a private **persistent** encrypted storage location; an ephemeral Render
filesystem is not safe for durable quota accounting or retention.

`BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED=1` is the human operator's opt-in
to the written free-use limits; it is not a billing or credential switch.
The separate `BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED=1` is valid
**only after** verifying exclusive execution and a durable shared ledger.
It must not be enabled for multiple workers, multiple devices sharing one
Basic key or transient Render instances.

Example research-only manual depth inspection, after the above guards are
actually verified and the account's other request consumers are idle:

```sh
python twelve_research_extension.py --symbol XAU/USD --interval 5min \
  --earliest-only --archive /verified-private-path/twelve-research.sqlite
```

A bounded manual bar request (UTC, end exclusive):

```sh
python twelve_research_extension.py --symbol XAU/USD --interval 5min \
  --start-utc "2026-11-11 22:00:00" --end-utc "2026-11-11 22:15:00" \
  --archive /verified-private-path/twelve-research.sqlite
```

For direct and major FX pairs, verify the requested interval first and set a
one-off, independent flag, such as `BOB_TWELVEDATA_SCOPE_EUR_CHF_1H=1` or
`BOB_TWELVEDATA_SCOPE_CHF_EUR_1H=1`. XAU/USD 4h/8h is confirmed; FX daily
is still blocked. For XAU/USD daily requests supply UTC instants matching
**Sydney midnight**, not UTC midnight (DST days may last 23 or 25 hours).
No scheduled requests are permitted.

The internal cross-rate function receives stored, validated rows; it never
downloads CHF/EUR directly, publishes derived currency prices or injects
them into DEGIRO products.

## Remaining release blockers

- Run unit tests, full relevant CI and a branch review. Keep the PR in DRAFT.
- Verify the actual daily and intraday provider responses with authorized
  one-off requests. DST-aware Sydney daily parsing is covered by unit tests,
  but no authenticated daily response has been accepted yet. Ambiguous
  metadata must still **fail closed**.
- Verify request credit weights and quotas against live response headers.
  This local ledger alone cannot coordinate with other account consumers.
- Validate an **exclusive** operator process and private persistent quota
  archive. Implement documented erasure if Basic access is terminated.
- Confirm actual authenticated Basic access for each requested FX interval.
  The written 13 Nov permission for XAU/USD 4h/8h and direct EUR/CHF and
  CHF/EUR does not itself prove live availability.
- Any future simulation comparison requires original provenance and license
  separation. No Twelve Data display, automated scheduled polling, live
  fallback, real-money trade, or billing is authorized.

Test without any real key:

```sh
python -m unittest test_gold_fallback test_twelve_research_extension
```
