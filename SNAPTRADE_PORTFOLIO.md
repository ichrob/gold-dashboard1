# Personal portfolio read-only extension

The DEGIRO tab shows the broker's last supplied valuation price and acquisition
price, when available. These prices do not have a verified original quote clock;
`positionsSourceAt` records the broker holdings fetch, not price formation.

Per-position market value and unrealized gross P/L use decimal arithmetic only
for known unit-priced kinds. Options, futures, CFDs, bonds and unclassified
instruments have no guessed multiplier. Missing acquisition prices remain
unknown. No cross-currency totals, fee assumptions or realized-profit claims.
The provider's native account `net_value` is shown separately. Cash equivalents
are explicitly identified; values are never added to cash again.

The existing 600-second worker reads recent orders through a GET-only allowlist.
Activities are read once per day, up to four 500-row pages, and are explicitly
marked incomplete if more remain. Provider failures preserve the previous journal
with an unavailable status. A submitted or canceled stop order does not become an
active trade stop. Journal entries and holdings never create MyTrade, Top 3,
product approvals, paper entries, or real orders.

The last 1008 distinct holdings snapshots and 300 quantity observations are kept
in a bounded, compressed, Fernet-encrypted document in the existing private
`bob_settings` store. The document is scoped to a hash of the personal client ID.
The UI draws account values separately by account and currency; it makes no
return calculation, since contributions, withdrawals and asset transfers change
account values. Persistence failure remains visible. Disconnect removes both the
configuration and portfolio document. No credentials, account IDs, holdings or
journal rows are added to operational diagnostics or repository fixtures.

A separate best-effort 30-second worker uses existing bounded issuer readers for
checksum-valid ISINs supplied as an exact provider symbol. It requires a verified
matching identity, currency, original bid/ask and clocks at most 90 seconds old.
Calculated, converted, mismatched and stale quotes are rejected. No identifiers
are guessed from names. These quotes are displayed separately from broker
valuation prices and do not grant executable DEGIRO quote evidence.

Validation: targeted arithmetic, unknown multiplier, currency, partial snapshot,
activity pagination/cadence, encrypted persistence, owner separation, disconnect
race, source identity/freshness and HTTP authentication tests; the existing
mobile browser regression also covers history, missing journal data, XSS-safe
rendering and stable expanded sections.
