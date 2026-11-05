# Bob Zentrale Android

Separate application ID `ch.bob.zentrale`, label Bob Zentrale, launcher icon and
window without a browser address bar. A minimal native WebView shell serves the
existing HTTPS hub, so server-side UI updates need no APK rebuild. Only INTERNET
permission; no accessibility service, OCR model, push worker or local database.
The app has its own session: log in once using the ordinary Bob form. Credentials
are not passed from the launcher, logged, or sent through a JavaScript bridge.
There is no JavaScript/native bridge. Foreign origins, cleartext, local file and
content requests are blocked. TLS failures cancel loading. No offline promise.

The independently versioned signed APK is published as `Bob-Zentrale.apk` under
`bob-zentrale-v<version>` after successful main CI, unit tests, release build,
package/permission checks and verification against the existing certificate pin.
These releases are not marked latest, preserving Bob Handy's existing update
endpoint. Debug packages end in `.debug` and are not production updates.

Device acceptance remains separate from compilation: install on Samsung, verify
launcher icon has no browser badge, log in, switch all five hub sections, refresh,
check back/reload and offline recovery. Detail pages use existing Bob routes;
third-party sites are not opened in this WebView. This is an online app, not a
native reimplementation of the charts and analysis engine. Installing it does
not claim Render RAM or disk savings.
