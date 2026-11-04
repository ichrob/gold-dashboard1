# Bob Zentrale – non-destructive first phase

The proposed second installable web app is served at `/zentrale/` by the
**existing** scanner process. It has a distinct manifest ID, start URL, scope,
service worker and icon from the original Bob PWA. This is not a second paid
Render instance and not an Android native APK.

- Login: the existing Bob session is required for the private page.
- Permissions: only existing authenticated GET `/api/operations-summary`
  is called, **only when the user presses the update button**. This is a
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
storage/archive and settings. Hash navigation reuses one explicitly requested
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
