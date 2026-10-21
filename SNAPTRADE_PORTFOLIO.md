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

The controlled SnapTrade worker reads recent orders through a GET-only allowlist. It uses a 600-second minimum interval while the authenticated DEGIRO view is active and six hours in the background.
Activities are read once per day, up to four 500-row pages, and are explicitly
marked incomplete if more remain. Provider failures preserve the previous journal
with an unavailable status. A submitted or canceled stop order does not become an
active trade stop. Journal entries and holdings never create MyTrade, Top 3,
product approvals, paper entries, or real orders.

Up to 1008 distinct holdings snapshots (at most 2 MB) and 300 quantity observations are kept
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

## Explicit CSV reconciliation

The existing device-local portfolio export is not uploaded automatically. In the
DEGIRO tab, compare the stored CSV, select its account and review position/ISIN
pairs. Exact existing ISIN matches are accepted; a matching name only suggests an
option and never confirms it. Where SnapTrade has no ISIN, explicit confirmation
and a stable provider instrument UUID are required. Account, currency, duplicate
assignments and contradictory provider ISINs are checked on the server.

Saving sends only the selected normalized CSV rows and mappings to the existing
encrypted private store. Future reads reapply a mapping only to the same account,
provider instrument key, symbol and currency. Clearing the mapping removes its
historical evidence, inferred financial values and obsolete quote link, while
retaining the device-local CSV and current broker data. Disconnect removes all
server-side Personal data as before.

CSV price, quantity, value and optional acquisition price are historical export
fields. Import time is not used as original quote/export time. A CSV acquisition
price never overwrites a current broker acquisition price. Export account-currency
conversion values are not used as native-currency product values.

For an unclassified but explicitly named factor/turbo/knock-out certificate only,
a native-currency export value matching quantity times export price (within
rounding tolerance) permits an explicitly labeled CSV-calculated unit valuation
using the latest broker quantity, valuation price and acquisition price. This is
an inferred unit quotation, not an independently verified contract multiplier or
executable quote. Options, futures, bonds and unrecognized assets get no inferred
multiplier. All trading approvals and simulation/stop rules remain separate.

## Automatic identifier reconciliation

The primary CSV button now performs an automatic server-side identity check.
The local file is shared only by this explicit action; it does not require
per-position checkboxes. Multiple accounts require an account choice first.
Manual reconciliation remains an optional fallback.

Automatic identity evidence is restricted to an exact provider ISIN, an explicit
`WKN:` national identifier for a checksum-valid DE000 ISIN, an earlier binding to
the unchanged stable provider instrument, or an exact instrument FIGI match from
OpenFIGI's ISIN/currency mapping response. Arbitrary six-character tickers,
product names, quantities and share-class/composite FIGIs do not prove identity.
Conflicting or duplicate candidates remain unresolved with a reason.

The free, unauthenticated OpenFIGI mapping endpoint receives only ISIN and
currency, never account IDs, names, holdings, amounts or credentials. Requests
are bounded to ten identifiers and 500 KB, have an eight-second timeout, reject
redirects, cache positive matches for a day and failures for fifteen minutes,
and are limited to one public batch per minute. There are no subscriptions or
paid refreshes. No lookup is attempted unless the broker provides a FIGI to
compare. Reference: https://www.openfigi.com/api/documentation

Unresolved CSV evidence is stored encrypted and reconsidered on the existing
600-second holdings worker. This is not a promise that a missing identity will
become available. Existing trade approvals and quote freshness rules are intact.
