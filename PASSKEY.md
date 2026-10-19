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
one recovery code grants access to enroll another Passkey. Old credentials are
not automatically revoked; a reviewed removal/revocation UI is still required
before production activation, especially after a device is lost. Recovery-code
acknowledgement/rotation is also not yet implemented.

## Deployment prerequisites (do not activate yet)

- Existing ChatGPT MCP and other Basic-only clients will be denied once enrolled.
  The draft now supports an independent Bearer `BOB_MCP_SERVICE_TOKEN` (random,
  at least 32 characters), accepted ONLY on POST /mcp for the two existing
  allowlisted read tools. Provision it securely on the scanner and in the
  private plugin before enrollment. It never grants browser access, general
  API access, writes, or trades. Do not reuse the user password or push token.
  No service token has been generated, configured, or placed in this repository.
- Deploy the push backend with `webauthn==3.0.1` and the new database table before
  enabling scanner enforcement. Existing service-token authentication protects
  the internal `/auth-passkey/` RPC routes.
- The scanner's `PUSH_SERVICE_URL` must be HTTPS; this implementation deliberately
  refuses plaintext for these RPC calls. Confirm the actual production setting
  without exposing secrets before activation.
- Finish credential revocation/recovery management and verify the complete flow
  on a staging deployment with a real phone. Local cryptographic fixtures are
  not proof that a particular mobile browser or platform authenticator works.
- Keep the feature gate off until these prerequisites are resolved. No production
  environment variables or account credentials were changed in this draft.

## Validation

`python -m unittest test_passkey test_basic_auth_throttle test_auth test_persistent_auth test_auth_runtime_cost test_recovery test_recovery_locking test_bob_mcp -q`

64 tests ran: 61 passed, 3 pre-existing skips. Tests include real ES256 registration
and authentication fixtures, wrong origin/challenge, missing user verification,
bad signature, replay, exact expiry, one-use recovery, failed-store denial,
Basic/cookie bypass prevention, and HTTP redirects/API denial. `node --check
passkey.js` also passes. No live enrollment, email, broker login, or trade occurred.
