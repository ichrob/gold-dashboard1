# Private remote TEST push

Existing `/mcp` advertises three additional tools. `bob_push_devices` and
`bob_push_test_status` require `bob:diagnostics:read`. `bob_push_test` requires
new explicit `bob:push:test` OAuth consent. Existing access/refresh tokens and
legacy service credentials are never upgraded. Consent lists the bounded
write capability; revocation remains `/oauth/connections`.

The tool can only queue the fixed existing synthetic delivery test for an
explicit `deviceId` from the private list. No endpoint/key/credentials are
returned. Device identifiers describe browser registrations, not verified
Samsung identity; resolve multiple devices with the user, never broadcast.
`requestId` must be a new random 32-character lowercase hex ID and must be
reused on retry. Database locks prevent duplicate scheduling. Max one request
per five minutes and ten in a rolling 24h per device. Existing channel settings
and pending tests are respected; remote calls cannot subscribe or enable them.

Delivery uses the existing background worker, fixed TEST title/body, 30-second
delay, expiration and signed receipt machinery. Request ID correlates provider
attempts to browser API acknowledgements/clicks without returning receipt
secrets. Provider acceptance is not handset display, browser API resolution is
not Android tray evidence. Provider retries can duplicate a notification after
an ambiguous transport failure; a stable notification tag replaces the test.

Deployment prepares the server but does not grant the ChatGPT connector new
permissions. Refresh its tool definitions/reconnect and explicitly approve
`bob:push:test` when prompted. First handset registration and OS permission
must happen on that handset. No real orders or unrestricted remote control.
