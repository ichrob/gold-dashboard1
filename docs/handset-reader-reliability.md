# Bounded handset reading and selective refresh

This extends the existing user-started read-only workflow. It is not bot-detection evasion, background broker control or order automation.

| Improvement | Implementation | Verification |
|---|---|---|
| Per-product delivery | Persist each outcome, then send an immutable authenticated revision in the background. Never remove/ACK the active outbox. Coalesce while busy; final delivery retains exact ACK semantics. | Source integration guards, server duplicate/revision tests, Samsung transfer check |
| Selected quote refresh | Explicit local chooser for 1–3 ISINs from the saved original list. Server checks ownership, 14-hour list age, membership and terminal status. Existing local PIN handoff starts reading only after verified Markets. | Planner validation, handoff JVM test, cancellation guards |
| Confirmed terminal exclusions | Skip only an exact-ISIN productVerified issuer status with a terminal bit. A missing quote, generic halt or unverified status cannot exclude a product. | Positive and negative planner tests |
| Stable semantic navigation | Observe the same window/action/semantic target for at least 400 ms. Existing exact identity, safe target, return-transition, finite retry and overall timeout checks remain. Security challenge blocks stop the reader/session immediately. | JVM stability/clock reset/challenge tests plus existing emulator regressions |
| Separate clocks | Preserve display text and minute precision, explicitly unknown display timezone, original capture time and server receipt time. Never synthesize sourceTime. | Server observation tests |
| Completion report | Native report retains the latest checkpoint after delivery and shows complete/partial/missing-quote counts with exact final ACK status. Web report shows complete/partial/terminated/factor counts and calculable selected scenarios or reasons. | JS and mobile browser tests |

Targeted revisions merge by original capture time into the same list universe; an older delayed upload cannot replace a newer captured value. Other products remain visible. A new list generation is isolated.

## Samsung acceptance

Install the signed update over the current app, without uninstalling. Start one full Gold read. Verify per-product server receipts while reading, then the final summary. Use “Einzelne Produktkurse aktualisieren · höchstens 3” to select one active ISIN: login if required, direct ISIN search/read without new list screenshots, a newer observation for that ISIN, and unchanged evidence for the other products. Cancel preparation or press Stop: no delayed login/navigation may start. Unknown security challenges must stop; no repeated PIN attempt. These require real-device confirmation and must not be inferred from emulator success.
