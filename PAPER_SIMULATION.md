# Prospective Gold/product simulation

The campaign starts 2026-10-08 00:00 Europe/Zurich, has no fixed end date,
and admits entries only during Bob's existing intraday entry session. There
is one open case at a time and at most one entry per rule/bar/direction.
No order, broker login, push delivery, account budget or real position changes
are made. A scheduled case is not fabricated before the campaign start.

The independent daemon consumes the latest live bundle approximately every
30 seconds, uses `background_analysis.js` and the existing selection workflow,
and persists its state in PostgreSQL. Market snapshot, rule version, original
levels, selected product and entry quote are frozen. Repeated timestamps do not
advance a case. Stop/target events are observed quotes, not continuous tick or
fill reconstruction. A gap exceeding 90 seconds ends the case as inconclusive.

The versioned policy takes a simulated 50% partial profit at the first target.
The remainder uses the existing `background_push.advance` profit protection,
trailing stop and confirmed target-extension rules. Stops only tighten. Stop
checks occur before new stop changes. Remaining exposure closes at a reached
unextended target, the first weakening-profit signal, confirmed opposite
direction, four-hour timeout or 21:45 Zurich. These are simulation assumptions;
they do not silently become the user's actual trading instructions.

The shared product rules choose an eligible ranked product. The already-existing
indicative/stale-data mode is explicitly separate and never gets an executable
product return. The authenticated browser sends its current product list and
evidence independently of Push settings. If absent, the worker imports the
latest previously stored selection evidence; the known DE000PJ9NCK0 identity
from the user's October 7 images is a fallback only, not invented quote data.
An empty browser does not erase another device's universe. The universe is the
latest nonempty sync, not a claim that DEGIRO still lists an archived product.

Up to four issuer quote requests are scheduled asynchronously. They reuse the
existing public quote, permission and backup pipeline and do not block the main
background/Push request. A valid, open-market EUR bid/ask pair no older than
90 seconds is required for a product gross comparison: entry ask, exits bid,
weighted by the simulated fractional exposure. Estimated/chart quotes,
missing exit quotes, indicative candidates or unknown currency produce an
unknown product result. No leverage-based EUR or futures-return guess is made.
Quote sources/times are retained per event. Gross results exclude unknown fees,
financing, slippage and net profit; no DEGIRO execution is claimed.

Details are retained 30 days after closure, up to 100 newest cases per selected
day in the UI. Daily aggregates remain indefinitely; the latest 366 are shown
in the read response. Counts exclude the artificial technical demonstration
and ambiguous gold cases. Product-positive counts include only cases with
complete quote evidence. Gold R uses the original stop distance and observed
exit gold price. These are not independent-trade success probabilities and do
not prove that every analysis decision was correct.

The read-only technical demo anchors a hypothetical LONG path to the latest
observed gold reference when available. Its following prices, LONG signal and
levels are artificial, it has no product quote, and it is never stored in the
live cases or aggregates. It demonstrates tightening, partial gain, extension
and a subsequent stop exit without polluting prospective evaluation.

Tests cover LONG/SHORT stops, target ordering, monotone trailing, partial
weights, target extension, reversal, gaps, stale product prices, source clocks,
read-only reporting and tomorrow's start boundary. Existing Push/audit checks
are also run. A complete prospective market case still requires future data.
