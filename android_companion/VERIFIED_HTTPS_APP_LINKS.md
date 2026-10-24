# Bob – Handy: verified HTTPS one-tap links

## Goal
A **normal HTTPS link** clicked by the user in ChatGPT should be resolved by
Android's **verified App Links** mechanism to the installed signed `Bob – Handy`.
The app may preview **only a single allowlisted display**; the already
implemented local **„✅ Geteilten Anzeigeauftrag einmalig öffnen“** is still
required. One tap to open the app is not permission to execute anything.

Example: https://bob-private-scanner.onrender.com/handy/OPEN_PRODUCTS

## Association prerequisites
1. Stable Android application ID remains `ch.bob.degirocompanion.stable`.
2. Server HTTPS host is **exactly** `bob-private-scanner.onrender.com`.
3. The public `/.well-known/assetlinks.json` must answer **HTTP 200**, exact
   `Content-Type: application/json`, HTTPS, **no login and no redirect**.
4. `android_companion/app_link_certificate.sha256` is created **only** from
   the verified *public* release signing certificate fingerprint exposed by
   the existing pinned GitHub Actions public repository variable. A missing,
   wrong or placeholder certificate results in **HTTP 503**, not a fabricated
   successful association. The full private signing key is never exported.
5. The Android manifest limits the verified link filter to the host and
   `/handy/OPEN_` path prefix. The Kotlin parser additionally requires a
   known exact action and rejects queries, fragments, encoded paths, arbitrary
   URLs and all trading/broker operations.

## User confirmation and unsupported clients
ChatGPT, certain clients or Android settings may still force a browser even
for a correctly verified link; the final confirmation is an **actual Samsung
test**, never green CI alone. For clients that open the web landing instead,
Bob offers the existing two-tap custom-scheme proposal link or the proven
clipboard fallback: copy `BOB-HANDY/1|OPEN_PRODUCTS`, use
`📋 Kopierten ChatGPT-Auftrag prüfen`, then explicitly approve.

## Security
No background handset control, accessibility permission, network
permission in the offline Android companion, financial orders, login,
OTP, or untrusted arbitrary URL execution. A link is not device
authentication. All data-bearing API endpoints remain under Bob session
authentication and the verified association is deliberately public.
