# Private operational diagnostics

The existing POST /mcp transport now supports `bob_diagnostics`, in addition to the two product tools. It reads cached market inputs, background heartbeat, collection status, research progress, paper-account heartbeat, push monitor counts and the sanitized problem index. Each observation retains its original timestamp when available; `observedAt` only marks report collection. Missing data is unavailable, stale market caches remain stale, and push monitor counts do not prove delivery. Reports do not assess forecast quality or authorize trading.

## Authorization and rollout

Both scanner and push-service revisions must include this change. The push-service `/diagnostics` route requires its existing internal credential and executes a read-only database transaction. No diagnostic data is added to public health endpoints.

Existing OAuth grants, including legacy persisted grants without a scope field, retain `bob:products:read`. Their refresh tokens cannot gain permissions. To access diagnostics, reconnect through the existing ChatGPT OAuth connection with `bob:products:read bob:diagnostics:read` and approve the updated consent page. A diagnostics-only grant cannot call product tools. Existing machine keys and legacy Basic authentication remain product-only.

The plugin's existing connection must refresh its discovered scopes and tools. Do not recreate the plugin or copy credentials into chat. Validate the deployed revision and make an authenticated `bob_diagnostics` call after reconnection. Until that call succeeds, report end-to-end verification as pending.

## Verification

`python -m unittest test_bob_mcp test_bob_diagnostics -q`

Tests cover old-grant preservation, refresh scope escalation rejection, new scope exchange and rotation, consent text, HTTP scope enforcement, bounded/no-secret summaries, missing/stale evidence, fixed tool arguments, and SELECT-only push snapshot reads.
