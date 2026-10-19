# Optional DEGIRO read-only connectivity probe

Under **Mehr → DEGIRO**, the connection status is fetched without contacting
DEGIRO. A separate button performs one login, client-details read, portfolio
read and logout attempt. This does not implement automated trading.

## One-time setup on the existing Bob web service

1. Set the build command to `pip install -r requirements-degiro.txt`.
   The checked-in render.yaml contains this command, but an existing service
   not managed by that Blueprint requires its dashboard setting to be updated.
2. Store `BOB_DEGIRO_USERNAME` and `BOB_DEGIRO_PASSWORD` in the service's protected
   environment settings. Never commit them or send them in chat.
3. Deploy, open Mehr → DEGIRO and enter the six-digit authenticator OTP if
   required. Tap **DEGIRO-Lesetest starten**. No TOTP seed is requested or stored.

The library is unofficial and broker permission remains unconfirmed. A read
result does not establish authorization for automated trading. In-app approval,
CAPTCHA and challenges beyond the OTP flow are not implemented or bypassed.
Failures return a generic authentication diagnostic without remote response text.

## Boundaries

- SDK pinned to degiro-connector 3.0.36. No paid API, browser service or new hosting
  instance. Existing hosting and normal broker fees are not made free by this.
- Child process has a 45-second hard limit and suppresses SDK logs. Each HTTP
  request has connect/read timeouts. No retries or persistent login loop.
- Fixed HTTPS host/method/path allowlist permits login, client details, portfolio
  update and logout only. Order checks, creation, updates and cancellation are
  absent. Redirects are disabled. No account data is stored or returned to UI.
- Username/password stay server-side; OTP is sent in a same-origin authenticated
  POST and cleared from the form. Neither OTP nor password is placed in a URL.
- One attempt at a time, at least 60 seconds between attempts per server process.
- A timeout or logout failure may leave a remote session until it expires; the UI
  must not claim successful logout. The SDK session is never reused by Bob.
- Status indicates local setup only. Only READ_OK confirms an actual portfolio
  response. Tests using mock transport are not live connectivity tests.

Run `python -m unittest test_degiro_readonly` with requirements-degiro.txt installed.
The actual SDK is exercised against mocked HTTP responses, including leading-zero
OTP preservation and failed authentication; no test logs into a real account.

## Experimental product evidence probe

The authenticated existing probe endpoint additionally accepts `isins`, a list of
at most three ISINs. The default empty list retains the portfolio-only probe.
Product lookup and detail lookup preserve explicitly named bid/ask/status fields.
If a matching product has a VWD identifier and the account supplies a user token,
the probe also requests its chart object from the fixed DEGIRO chart-feed URL.
Missing fields remain missing; last prices never become bid/ask quotes. Raw status
fields are not interpreted as account trade permission. All results retain
`approval: UNVERIFIED`. No ranking, approval, jobs or trading rules are modified.
The existing 45-second isolated worker deadline still applies to the entire probe;
three products may exceed it. This is a bounded manual diagnostic, not a 30-second
background collector. In-app confirmation remains unsupported by this worker.

Validation: `python -m unittest test_degiro_readonly test_degiro_product_probe`.
These tests use synthetic responses; no live gold-product response is confirmed.
