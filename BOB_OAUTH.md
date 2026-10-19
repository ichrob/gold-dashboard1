# Private ChatGPT OAuth connection

Bob now publishes OAuth discovery at `/.well-known/oauth-authorization-server`
and `/.well-known/oauth-protected-resource`. Register the HTTPS `/mcp` URL in
ChatGPT as a separate custom MCP connection, using OAuth and dynamic client
registration. The only scope is `bob:products:read`.

The public client uses PKCE S256 and the exact stable ChatGPT callback
`https://chatgpt.com/connector_platform_oauth_redirect`. Every authorization
redirect includes the issuer (`iss`). No client secret is required or accepted.
The registered ID is public, reused for this one allowed client configuration,
and does not grant access without the account owner's consent and PKCE proof.

The user signs in on Bob, completes the existing daily factor if enrolled, and
explicitly approves the read scope. OAuth access tokens last at most one hour;
refresh tokens rotate and cannot extend the original grant. Grants last at most
28 days and are capped at the existing authorization end date, November 16, 2026
(Europe/Zurich). A later period needs a deliberate policy update and new consent.

State lives in the existing PostgreSQL service via authenticated internal RPC.
Only token hashes are stored. Authorization codes and refresh tokens are consumed
under a database row lock. Replay revokes the associated grant. Store failure
denies access. A password reset revokes OAuth state in the same transaction.
No additional host, paid service, dependency or secret is introduced.

`/oauth/connections` lists the number of active grants and offers immediate
revocation of all OAuth grants. The page is linked from `/passkey`. It does not
revoke the older standalone service key; that remains a separate credential.

Deployment is additive: both services deploy the same commit; the push service
creates the new table on startup. Until its new version is live, OAuth fails
closed while existing Bob login and service-key access remain available.

Validation: `python -m unittest test_bob_oauth test_bob_oauth_db test_bob_mcp
test_recovery test_persistent_auth`. PostgreSQL tests require the isolated CI
`BOB_TEST_DATABASE_URL`, never the production database URL. A real ChatGPT
registration, owner consent and product read are still required after deployment
before claiming the mobile connection works. Do not remove the old plugin's MCP
declaration until a verified app connection ID can replace it.
