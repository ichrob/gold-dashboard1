# Paper entry review, daily review and three-stop study

New paper entries store a forward-only `entryChecklist` with the original Gold time,
rule version, frozen evaluator context, source readiness, direction/plan consistency,
product pair and existing KO guard. The existing entry filters run first. A failed
required checklist blocks the new virtual entry; supplementary unknown trend/timing
information is explicitly labelled and does not invent an approval. Wait reasons
retain their existing bounded daily history; the latest full checklist and aggregate
check-state counts are stored per day. Successful entries are no longer counted as
wait checks. Old day counts and entries are not rewritten.

The daily review is read-only and uses the selected day's at most 100 case details.
It separates legacy entries, confirmed required checks, failed checks, unknowns,
settled unpriced cases and results after each case's frozen example costs. A loss
alone is not an avoidable error. Only recorded required failures become review
candidates. Existing strategy research remains responsible for independent validation.

The balanced 100 EUR account additionally registers a three-stop forward study:

- Original Bob initial stop, frozen at entry.
- Initial stop at 1.5 times the actual entry ATR.
- Lowest low / highest high of the last 20 contiguous, fully closed 5-minute
  XAU/USD candles, known at entry. Missing or stale structure is unavailable.

All variants use the same observed entry ask, whole-unit quantity, target and
original monitoring end. Each performs one full hypothetical exit; these are stop
experiments, not replicas of Bob's partial-target lifecycle. Stops remain frozen.
The existing KO guard is also applied; a crossed barrier or an unconfirmed terminal
price cannot create a profit. No shadow result touches account cash or existing
stop management. Different initial stops imply different initial risks at equal
exposure; the UI states this limitation.

`bob_paper_stop_studies` survives restarts and continues after the original paper
case closes. The existing quote worker includes pending study ISINs and advances
at most 32 studies per cycle, with at most 8 registrations. SQL transactions isolate
study failures from the real paper ledgers. No additional network provider or job
service is created. Completed details are retained for 30 days.

Net comparisons require all three variants to finish with paired observed quotes,
no source regressions, no gaps over 90 seconds and matching source timing. Entry
ask / exit bid already includes spread. Fees, slippage and additional holding cost
are frozen example assumptions using `paper_costs`, never verified DEGIRO fees.
Unknowns are excluded from every compared variant equally. Under 20 complete pairs
is collection only; even beyond that, results are descriptive research and never
automatically promote a rule or prove profitability.

UI: Simulation > account details > entry checklist, daily decisions, and (balanced
account) fixed / ATR / structure stop comparison. Existing balances and histories
are preserved. No broker orders, new notifications or paid service changes.
