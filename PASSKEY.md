# Daily Passkey second factor (staged)

This change is not enabled by default. `BOB_PASSKEY_AVAILABLE=1` exposes
`/passkey` and checks durable second-factor state after primary authentication.
Enrollment requires an existing, validated browser session, the current password,
and a WebAuthn registration with user verification. Successfully enrolling the
first credential enables enforcement for the account. No credentials are
pre-enrolled by this change.

A successful Passkey ceremony grants exactly 24 hours to that browser session.
Reads do not extend this deadline. New sessions/devices require their own proof.
The existing login option “Angemeldet bleiben” retains the primary session for
seven days; without it the existing primary session expires after eight hours.
The authenticator chooses fingerprint, face recognition, or device PIN; Bob does
not receive biometric data and cannot require fingerprint specifically.

WebAuthn verification requires the canonical scanner origin, RP ID, challenge,
user presence and verification, and a valid signature. Challenges expire after
five minutes and are consumed even on a rejected verification. Five failed
ceremonies/recovery attempts within five minutes block more attempts temporarily.
State is serialized under PostgreSQL row locks. The database retains public
credential keys, counters, hashed recovery codes, and session-bound proof expiry.
An unavailable store denies access rather than silently skipping the factor.

Eight one-use recovery codes are displayed at initial enrollment. Store them
away from the phone. A password reset does not disable Passkeys. Password plus
one recovery code grants access to enroll another Passkey. The mobile page now supports removing an old credential after adding a new one.
Removing a key invalidates all other daily grants and all pending ceremonies;
the last key cannot be removed. Management requires a recent second-factor proof
and sensitive operations recheck the password. New recovery codes replace old
ones only after the user acknowledges a code from the new set. Codes must be
stored outside the lost phone (for example in a recoverable password manager).

## Deployment prerequisites (do not activate yet)

- Existing ChatGPT MCP and other Basic-only clients will be denied once enrolled.
  The draft now supports an independent `BOB_MCP_SERVICE_TOKEN` (random,
  at least 32 characters), accepted as Bearer or Basic with username
  `bob-readonly` ONLY on POST /mcp for the two existing
  allowlisted read tools. Provision it securely on the scanner before enrollment. The existing private
  plugin can retain its Basic configuration, identity, skills, and tools; the
  user replaces only the connection credentials through the protected host
  dialog on their phone. The setup page includes password-protected display and
  copy buttons. No secret is embedded in plugin files or sent in chat. It never grants browser access, general
  API access, writes, or trades. Do not reuse the user password or push token.
  No service token has been generated, configured, or placed in this repository.
- Deploy the push backend with `webauthn==3.0.1` and the new database table before
  enabling scanner enforcement. Existing service-token authentication protects
  the internal `/auth-passkey/` RPC routes.
- The passkey RPC uses the existing public HTTPS push-service URL by default.
  An optional `BOB_PASSKEY_STORE_URL` override must also be HTTPS. Existing
  `PUSH_SERVICE_URL` configuration is not changed.
- Verify the completed credential revocation/recovery management flow
  on a staging deployment with a real phone. Local cryptographic fixtures are
  not proof that a particular mobile browser or platform authenticator works.
- Keep the feature gate off until these prerequisites are resolved. No production
  environment variables or account credentials were changed in this draft.

## Validation

`python -m unittest test_passkey test_basic_auth_throttle test_auth test_persistent_auth test_auth_runtime_cost test_recovery test_recovery_locking test_bob_mcp -q`

68 tests ran: 65 passed, 3 pre-existing skips. Tests include real ES256 registration
and authentication fixtures, wrong origin/challenge, missing user verification,
bad signature, replay, exact expiry, one-use recovery, failed-store denial,
Basic/cookie bypass prevention, and HTTP redirects/API denial. `node --check
passkey.js` also passes. No live enrollment, email, broker login, or trade occurred.

## Mobile verification boundary

The page uses a single-column responsive layout, 48px minimum controls, clipboard
buttons, and native WebAuthn on the same device, without a QR code. Enrollment,
code acknowledgement/rotation, lost-key removal, and machine-key display are
implemented. The existing plugin package was inspected and left unchanged;
Basic service credentials preserve its existing connection protocol and tools.
GitHub and Render integrations are not modified by this feature.

A 360px touch-browser test now passes in GitHub Actions (run 39295376946,
2026-10-19, commit 42da50e9afee7444f145a08dcfd729fd590ff4ac).
`browser_passkey.cjs` uses real Chromium WebAuthn with a virtual internal
authenticator and the actual Python signature-verification/state code over an
isolated test bridge. It verifies layout width, enrollment, fixed 24-hour expiry,
authentication, one-use recovery, replacement enrollment, revoking the lost key
and other session grants, and two-phase recovery-code rotation. No real account,
production requests, database, credentials, or plugin connection are involved.

The local browser still cannot launch because socket creation is denied.
The physical Android authenticator, production RPC/database integration and
ChatGPT credential-entry flow remain unverified. Keep enforcement off until
machine-key provisioning and a real product read succeed; user enrollment and
recovery-code safekeeping require the user's phone. Existing access is unchanged.
