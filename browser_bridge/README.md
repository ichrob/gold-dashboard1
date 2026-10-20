# Bob DEGIRO export bridge

This is a free, opt-in export handoff for Firefox Android with the signed Violentmonkey add-on. It avoids the unsupported server SDK login. It does not automate login, bypass DEGIRO blocks, execute orders, or promise live/background synchronization.

## Installation and use

1. Open Bob in Firefox for Android, then More → DEGIRO → DEGIRO → Bob mit Firefox.
2. Install Violentmonkey from the linked Mozilla Android listing. Review its broad page permissions.
3. Open the linked `bob_degiro_export.user.js` in Firefox and install it in Violentmonkey. Its match list must contain only the canonical Bob origin and `https://trader.degiro.nl/*`.
4. Reload Bob and the DEGIRO browser tab. Sign into DEGIRO yourself, including any required second factor.
5. In Bob, activate receipt for ten minutes. In DEGIRO, choose Portfolio → Export → CSV. Return to Bob; the Products and report panels show a local snapshot.
6. Stop receipt when finished. Remove imported data using Bob's existing CSV clear button. Remove the script in Violentmonkey to uninstall the bridge.

Both tabs must be in the same Firefox profile. The Chrome/PWA copy and Bob's server do not receive the snapshot. Exports are user-provided, historical data; no ranking, KO or trade permissions are granted. A CSV download and returning to Bob remain manual. The extension does not run an unattended 30-second sync.

## Data flow and bounds

Version 1.1.0 observes existing anchor clicks, detached anchor dispatchEvent clicks (FileSaver-style), and window.open for same-origin blob downloads or `/reporting/` CSV URLs, including paths ending in `/csv`. It patches the actual page globals through unsafeWindow instead of relying on a manager window wrapper. It never invents endpoints or inspects credentials, cookies, general network requests or account page state. Standard downloads continue. For selected HTTP CSV anchors the read-only copy completes first (or times out after 12 seconds), then the original click is forwarded even on failure; this avoids Firefox cancelling the copy when a same-tab download starts. Blob downloads remain immediate and window.open is forwarded immediately to preserve popup activation. A same-origin GET reads only the selected download, rejects redirects, enforces a 2 MB cap and uses Bob's shared CSV parser. Unsupported download mechanisms fail without replacing Bob holdings; manual CSV import remains available.

A bounded status heartbeat shares only the helper version, timestamp and one fixed state (ready/reading/staged/error). Bob warns about a missing DEGIRO helper or an outdated script instead of silently staying in the waiting state. Activation is displayed as active only after a versioned helper acknowledgment, with a three-second failure timeout. Message-source checks accept the real page window as well as the manager wrapper; browser fixtures exercise a distinct wrapper to avoid the earlier same-realm testing blind spot. Foreground/pageshow events retry pending delivery. Existing 1.0.0 installations must be updated once through the update link in Bob, then both Bob and DEGIRO reloaded.

Only normalized report fields enter the add-on's shared storage, with a ten-minute eligibility limit. No raw CSV, URL, session or password is transferred. Acknowledged data is removed from the queue. Expired queue data is removed when the script next runs; this is not guaranteed secure deletion at the exact expiry time. The user can remove the script and its stored data in the manager.

Bob independently requires a local ten-minute opt-in and validates freshness, ISIN checksums, duplicate ISINs, quantities, currencies and complete valid rows before replacement. It allowlists saved fields and forces every execution/verification flag to false. It accepts only same-window, same-origin messages; this is not cryptographic broker attestation. Scripts already executing on the same page share that page's trust boundary. Snapshot text is rendered with textContent.

## Rebuild and verification

`python tools/build_degiro_browser_bridge.py` embeds Bob's current parser plus `browser_bridge/runtime.js` in the installable userscript. `test_degiro_browser_build.py` checks reproducibility.

`node test_degiro_browser_bridge.js` checks validation and permission boundaries.

`node browser_degiro_browser_bridge.cjs` runs two real headless Chromium tabs with synthetic CSV downloads and a simulated userscript-manager store. Set `BOB_BRIDGE_BROWSER=firefox` to use an installed Playwright Firefox. It checks consent, valid import, detached dispatchEvent downloads, direct `/csv` links, window.open downloads, URL rejection, helper-version and broker-status diagnostics, invalid/partial/duplicate/stale rejection, replacement, persistence, deletion, mobile widths and the absence of credential/third-party transfers. The detached dispatch regression was reproduced against 1.0.0 before the fix; this demonstrates a code defect, not proof of which download mechanism the user’s live DEGIRO page used. CI runs this alongside the existing Bob browser tests.

These tests do not verify a signed Violentmonkey installation on Samsung/Android or the current DEGIRO export implementation. A real device export after the user installs the helper is still required before claiming live compatibility. A successful synthetic test is not a successful live broker test.
