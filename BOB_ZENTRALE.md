# Bob Zentrale – non-destructive first phase

The proposed second installable web app is served at `/zentrale/` by the
**existing** scanner process. It has a distinct manifest ID, start URL, scope,
service worker and icon from the original Bob PWA. This is not a second paid
Render instance and not an Android native APK.

- Login: the existing Bob session is required for the private page.
- Permissions: only existing authenticated GET `/api/operations-summary`
  is called, once when the page opens and when the user presses the update button. This is a
  bounded read-only projection, not proof of continuous simulation operation.
- Display: simulations, background status, issue groups, product evidence,
  and up to 30 of the already-registered test families. Stale and missing
  inputs remain visibly unknown; no invented success indicators.
- Security: all HTML is no-store; dedicated service worker has no caches;
  app renders server strings with `textContent` only. No trading, order,
  archive, deletion, repair or Push POST endpoints are exposed.
- The original Bob UI, database, existing worker schedules and services
  remain unchanged.

After deployment open `https://bob-private-scanner.onrender.com/zentrale/`
on Android Chrome, sign in with Bob if needed and reopen the URL. From Chrome
choose **Add to Home screen / Install** if offered. If Android creates a
shortcut instead of a standalone PWA, this is still a separate entry but
not a native app. The original Bob icon remains separate.

## What phase 1 does NOT achieve

No Render disk space is released merely by separating presentation. The
configured Postgres allocation is shared; there is **no database
migration**, automated source deletion, new service, paid plan or extra
background worker. Real space reclamation needs table-level measurements,
lossless archive+restore verification and an explicitly approved retention
policy. Do not confuse a successful external archive with released database
bytes. Do not cut over simulations, early warnings or DEGIRO product imports
until the new UI and runtime have been verified independently.

Run: `python -m unittest test_bob_zentrale`.

## Shared administration hub (5 November 2026)

The five sections are overview, simulations/research, problems/maintenance,
storage/archive and settings. Hash navigation reuses one shared
operations snapshot. There is no polling, second worker, database or service.
A refresh clears previous observations; failures/timeouts never leave an old
healthy state displayed as current. Source clocks are displayed in Swiss time.
The existing operations projection includes a small allowlisted storage view
from already collected observations. Disk, database and unavailable RAM remain
separate; neither archive receipts nor this UI claim measured savings.

The assistant's More page links directly to the hub. Core navigation and active
trade warnings remain in the assistant. Detailed simulation, research, results,
problem and settings screens still open their existing destinations: this phase
centralizes navigation and status, not the complete detail implementations.
Moving their code/loading lifecycle requires separate profiling and regression
validation; hiding links alone would not reduce server RAM or storage.

Validation: `python -m unittest test_bob_zentrale test_bob_operations
 test_storage_brief test_bob_operations_http`; browser checks cover mobile
navigation, a single shared GET, stale index disclosure and clearing failed
refreshes. No measured storage saving is claimed.

## Clear overview and handset evidence

The hub now reads once on page opening; manual refresh is single-flight, with
no periodic polling or focus/resume loop. Section changes reuse that snapshot.
Long case/test lists render when their section is opened. A compact two-column
menu preserves all five destinations. The overview separates last confirmed
monitor cycle, indexed open groups and explicit user-action requests. Unknown
problem indexes never become zero problems. Operational source/trade/push issues
precede research in the grouped list. Original last-success times remain visible.

Handset status is a tiny projection of existing telemetry, reader results and
list-import receipts. It contains no pictures, OCR text, ISINs, tokens or PIN
diagnostics. Running is displayed only when device receipt and observation are
both at most 120 seconds old and the pairing is unrevoked/unexpired. The latest
reporting device is labelled separately from the latest stored reader run and
list import: device/run association is not inferred. OCR attachment counts do
not prove successful on-device parsing or an actual server OCR execution. No
remote commands, reading tasks or tests are started by the hub.

Validate with `python -m unittest test_zentrale_status test_bob_operations
 test_bob_operations_http test_bob_zentrale` and `browser_zentrale.cjs` in CI.
This server-side UI update needs no replacement Android APK.
