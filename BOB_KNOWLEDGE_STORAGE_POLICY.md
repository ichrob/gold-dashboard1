# Bob: five-area knowledge compression and verified retention

## Contract

Retain **verified outcomes and source provenance** separately from large original
recordings. A classification or AI-written interpretation is **not** itself a
replacement for an immutable replay, trade result, source quote, or test proof.

The new `storage_knowledge.py` writes a very small **bounded descriptive
snapshot** of all five areas into `bob_knowledge_snapshots` on the existing
half-hour storage sample cadence. Five sampled indexed queries, maximum 64
source keys per area, no source identifiers/payloads in the resulting report.
It reports sample coverage accurately and never grants deletion authority.
This is **stage 1**, not completed lossless archival.

## Area-by-area finalization plan

| Area | Must retain as compact operational result | Original evidence |
| --- | --- | --- |
| Diagnostics | error family, validated root cause, fixed revision, recurrence counter, failing/passing tests | trace clock, original diagnostic event and proof of repair; existing 7-day bounded journal plus archived original analysis |
| Decisions | precise direction incl. WAIT, indicators, source times, price basis, rationale, evaluation window, outcome linkage | immutable decision and follow-up price evidence, replayable under original rules |
| Improvements | baseline/candidate, sample size, confidence, adverse cases, verified winner or explicit inconclusive verdict | original observation and independent comparison; existing cold-observation archive |
| Simulations | profile, original signal, entry and exit, capital/currency, position, P&L, drawdown, rejected entries, risk checks | original paper cases, trades and per-horizon source prices; never collapse separate simulations |
| Quality | metric name/version/scope, mismatch summary, before/after quality, pass/fail gate and error counts | original metric input and decimal recomputation; existing cold-metric archive |

## How an actual local payload may be replaced

1. **Select an immutable closed window**, never active trades, live signals or
   incomplete simulation and comparison runs. Include exact original clock and
   writer version.
2. Compute compact validated result(s) and an **immutable manifest** of source
   IDs, reference keys and SHA-256 hashes. Store state `pending`, NOT `verified`.
3. Upload original raw batch to private Google Drive with authenticated
   encryption, original source context, fixed checksums and a scoped reference
   ledger. Re-download and verify the **plaintext** source bytes.
4. **Restore on an independent database instance** and prove the same end-to-end
   existing readers, original clocks, source rows, foreign keys and simulation
   results. Bad/missing/expired archive or incomplete result -> fail closed.
5. Only after independent restore and per-area reader compatibility, use a
   narrowly bounded CAS write to replace **large payloads** with immutable
   references. Leave source identities, time fields, critical trading fields and
   FKs in PostgreSQL. Do not `DELETE` decision records with linked outcomes.
6. Verify read-through again. Re-run historical replay and paper comparison
   tests before claiming the case complete. Failed verification -> rollback.
7. Measure physical Render volume usage before and after safe maintenance.
   Logical JSONB size changes, TOAST estimates or VACUUM reuse are **not**
   physical free bytes. Never use VACUUM FULL/repack without independent spare
   disk, WAL and lock-budget evidence.
8. **No mass-delete toggle.** Per-area migration stays disabled until CI,
   isolated PostgreSQL regression, security review and explicit validated
   operator authorization. No credentials to GitHub; no paid scaling/orders.

## Current implementation and next gates

- Existing `cold_analysis.py`, `cold_metrics.py` and
  `cold_observations.py` already perform download/checksum/read-through
  before replacing payload content with references. Preserve those paths.
- `cold_decision_product_writer.py` is opt-in and currently not authorized;
  its verified test preview is not physical reclaimed space.
- Simulation-specific historical compaction is NOT enabled. A profit-only
  summary would destroy reproducible entries and risk evidence.
- The `bob_diagnostic_history` 7-day / 60,000-event limit is already
  implemented with bounded batches; investigate retention lag before tuning
  prune cadence or deleting events.
- The new `knowledgeSummaries` report deliberately uses
  `interpretationStatus=descriptive-only-not-validated-learning`,
  `deletionAuthorized=false` and `physicalBytesFreed=null`. It cannot mark
  a strategy or repair as successful just because an event disappears.

**Acceptance**: per-area independent restore, byte-identical source replay,
source/summary parity including failed/no-trade cases, measured volume change,
no real orders, no shortened historical simulations, and zero unauthorised
source row deletions. Until then retain original data or verified cold pointers.

## Neuer Historien-Evaluationsworker – erste echte Vorwärtsseiten

`storage_history_evaluations.py` verarbeitet ältere als zwei volle Tage
liegende Diagnose- und Entscheidungsbelege in strikten 400er-Seiten. Er läuft
mit eigenem DB-Zugang und 15-Minuten-Pause, nie in der heißen Markt-/Push-
Schreibtransaktion. Die jeweils ursprünglichen Datensatz-Identitäten und
Originalzeiten gehen in einen SHA-256-Seitenfingerabdruck; der persistente
Cursor erlaubt nach einem Neustart weiterzuarbeiten. Kategorien und Ergebnisse
sind eng auf die vorhandenen bekannten Statuswerte begrenzt. Es werden keine
privaten Originaldaten, Produktkurse oder IDs als Evaluation kopiert.

Der aktuelle Stand bedeutet ausdrücklich **nicht**, dass das komplette
Quelljournal fehlerfrei und nachträglich unverändert ist: Nachträgliche
Quellkorrekturen oder rückdatierte neue Ereignisse werden von dieser reinen
Vorwärtsiteration nicht erneut nachgescannt. Ein vollständiger unabhängiger
Abgleich und Replay sind eine separate Pflicht vor jeder Referenzmigration.
Eine solche Manifest-Seite autorisiert **keine Löschung**. Für die anderen
Bereiche laufen bisher die vorhandenen 64er-Lernstichproben und die
separaten geschlossenen Paper-Receipt-Scans weiter; vollständige
Bewertungen aller Simulationen und Qualitätsdaten sind ausdrücklich offen.

## Kompakte Tagesbewertung aus bestätigten Papier-Abschlussbelegen

`storage_paper_evaluation.py` liest nachgelagert höchstens 256 bereits
arithmetisch abgeschlossene, unveränderliche `bob_paper_final_receipts`
pro Durchgang. Die eigenständige, gedrosselte Aufgabe schreibt je
Strategieprofil und Quellen-Tag nur die Anzahlen von positivem,
negativem, unverändertem und unklassifiziertem Modell-Brutto-Ergebnis
sowie eine quellgebundene SHA-256-Reihenfolge. In der privaten Anzeige
stehen nur Aggregate und Verarbeitungsstand; keine ISIN, Fallkennungen,
Ausführungs- oder Kontoinformationen. Die Originalfälle und Belege bleiben
unverändert, mögliche spätere oder rückdatierte Originaländerungen sind
weiter nicht vollständig unabhängig nachgescannt.

Diese Aggregation **ist keine bestätigte reale Rendite, keine Netto-
Gewinnwahrscheinlichkeit und kein Strategiegewinner**. Das gesonderte
2.000-EUR-Risikomodell hat noch keine gleichwertigen arithmetischen
Abschlussbelege in `bob_paper_final_receipts` und wird nicht erfunden.
Vor Archiv-Referenzierung müssen alle Quellenkonten, offene/negative
Testfälle, Stopps/Ziele, Originalkurse und Replay/Restore unabhängig
verglichen werden. Keine automatische Falllöschung.
