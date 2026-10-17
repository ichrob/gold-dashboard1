# Diagramme under Mehr

Eight read-only sections share the authenticated audit reports: title alternatives,
ranking optimization, paper capital, drawdown, price accuracy, fixed-plan exits,
entry regimes/direction, and forward signal quality. No orders or new selection
rules are issued by the charts.

- Paper accounts use at most 366 stored daily valuations, not invented intraday
  equity. Euro P/L and percent since each account's own initial capital are separate.
  Daily sampled drawdown differs from the cumulative maximum observed by the worker.
  Unvalued days break the curve; missing quotes can conceal deeper drawdowns.
- Original/model price points are partitioned by the existing full learning identity
  (ISIN, currency, source, terms and scope). Store at most 720 observations per state,
  expose the newest 240 for each of the newest 24 states. A corrected chart point
  uses the candidate frozen BEFORE observing that point, never its subsequent fit.
  Training points and revoked leases have no corrected value. Chart MAE uses the
  original quote as denominator on exactly the paired observations; the learner's
  existing acceptance metric and thresholds remain unchanged.
- New lifecycle captures also freeze a separate original-stop/original-target case.
  It retains shared source, gap, KO and time safeguards and has no adaptive trailing,
  partial profit or reversal exits. Quotes continue until BOTH paths end. Legacy
  captures have no retroactive fixed path. A stop comparison requires complete
  evidence for both paths and all original candidate products. Return denominator
  remains EUR 100 including unallocated cash. Giveback is the positive observed
  peak profit minus the remaining positive exit profit, not an executable peak fill.
- Regimes come from frozen entry labels, split by currency and LONG/SHORT. Results
  are descriptive. Signal hit rate and mean directional gold movement use the same
  evaluated cases per horizon; missing and neutral counts remain visible.
- Missing data never becomes zero return. Accessible value tables accompany curves.
  Currency/horizon controls continue to apply to title, exit and regime comparisons.
  Account data uses a bounded read-only endpoint without loading case histories.

Validation: JS transformations/rendering tests cover gaps, missing values, currency
isolation and stale/empty states. Python tests cover frozen correction timing,
fixed-plan continuation after Bob exits, quote failure, target exits and bounded
read-only portfolio reporting. Existing PostgreSQL lifecycle integration also
covers persisted captures, restart and immutable entry. These tests establish
software behavior, not market accuracy or profitable future trading.

## Summary, evidence and change history

The compact overview groups measured improvements, declines and missing evidence.
Selection data never becomes a validated benefit merely because its mean is positive;
a stale audit response suppresses the current overview. Longer lists are expandable.

Each evidence panel counts observations, preselected spaced windows and observation
days. Spacing is applied BEFORE reading the result, so a missing result does not
shift selection to a conveniently profitable nearby observation. Signal summaries
prefer the background record for each candle and use separate 15/60/240-minute
windows. Neutral signals are not failures. Actual statistical independence is not
claimed. Account/drawdown observations are not treated as independent trades.

For descriptive means, at least 20 usable spaced observations on 10 observation
days are needed for an optional 95% percentile range. A deterministic 800-replicate
circular moving-block bootstrap resamples pairs of adjacent observation days and
recomputes the observation-weighted mean. This describes the spaced subset, which
can differ from the chart's all-observation mean. It does not establish causality,
resolve all dependence or multiple testing, change trading gates, or promise
coverage in every market regime. Otherwise uncertainty is explicitly unquantified.
Existing 99% adoption evidence remains separately labeled as historical evidence.

Ranking and per-identity price change events appear as dated vertical markers in
the relevant price/return window, plus an expandable timeline. Each event exposes
its saved reason and available evidence. Later observations are strictly after the
event and before the next saved event, from the available bounded report window;
no historical return is invented. Signal-rule history also displays stored checks,
including the next monitoring evidence when available. Limited history, absent
follow-ups and the difference between temporal association and causation remain
explicit. No behavior or adoption thresholds are changed by these display features.

## Completion bar

A 0–100 progress bar above the summary counts saved comparison checks in the
current bounded reports, across product currencies. Green means an evaluable
result, not a winning trade. Orange means an explicitly finished, unevaluable
comparison or immutable invalid/unavailable signal start. Missing signal follow-up
prices and unknown legacy status remain open; they may still be harvested later.
Gray means open. ABWARTEN is a completed neutral signal check, not a gain. The bar
separately counts title, Bob-exit, prospective original-plan and 15/60/240-minute
signal checks; these are not statistically independent trials. Legacy captures
without a fixed-plan branch create no invented pending shadow test. Other learning
phases and software tests are explicitly outside this scope.

Completion is (evaluable + explicitly unevaluable terminal checks) / all counted
checks. Zero checks have no percentage and never show 100%. A breakdown shows each
category. Existing checks finishing increase completion; newly captured checks or
rolling retention can lower the percentage. Stale data retains gray historical
segments with a stale label. The accessible progressbar exposes exact counts and
updates with the existing audit refresh, including manual refresh.

## Missing-value collection and user-initiated repair handoff

Below the progress bar, collect deficient title, Bob-exit and original-plan cases
plus signal missing-reason totals from the stored current report. Deduplicate by
comparison identity. Include explicit missing evidence even while another leg is
still running, but exclude ordinary pending future horizons and successful cases.
Retain old visible evidence with an explicit stale label when refresh fails; never
interpret an unavailable report as a successful repair. Source report retention/window limits remain visible; the subsequent automatic-repair
queue below preserves unresolved incidents independently.

The button “ChatGPT soll die Probleme selbstständig lösen” prepares a concrete
repair request and opens the native share sheet on explicit click. It does not
invoke ChatGPT in the background or claim recipient delivery. Cancel stops without
copying. Unsupported/failed sharing falls back to clipboard and a generic ChatGPT
link; blocked clipboard leaves a readable selectable report. No private data is
placed in URL parameters. Only allowlisted diagnosis fields, ISINs, original source
timestamps and sanitized reasons are included; no account, position size, secrets,
or wholesale payloads. The user still chooses ChatGPT and sends the prepared text.
The progress refresh avoids rebuilding this section merely for the 30-second age
check, preserving expanded details and manual-copy text while the report is current.


## Automatic attempt before ChatGPT escalation

`evidence_repair` runs in the existing 120-second background audit loop, with its
own committed transaction after normal harvesting. Discovery and processing are
bounded, queued in PostgreSQL, and independent of opening the app. Signal checks
retry a missing historical outcome using only the original stream and target
window, recompute excursions, insert only absent outcomes, and verify the stored
result. A present-day quote cannot fill a historical hole. Product checks re-read
the frozen plan and exact original quote archive. Terminal exit checks inspect
saved states/events; they never resume a historical gap from a current price.

Already-consumed ranking experiments remain immutable. Late evidence requiring a
separate historical review is escalated, not silently used to alter prior learning.
Invalid original entries and irreconstructible exit paths are escalated after one
verified inspection; other unavailable evidence retries at most three times with
120 seconds between attempts. Exceptions do not become success. Each attempt has
a dated action/result; the heartbeat advances only on a committed successful cycle.
Unresolved records remain stored when the source rolls out; recovered history has
90-day retention. Reads and sharing do not trigger repairs or send messages.

Only server-confirmed `escalated` cases with at least one saved attempt are offered
by the ChatGPT button. Pending cases stay with Bob. The report contains the attempted
actions and remaining reason. UI and share payload show stale status explicitly;
up to 300 queued/escalated records are returned, with counts and truncation notice.
Original source fetch workers continue their existing cadence; this recovery task
reuses the original archive and never fabricates a provider backfill capability.


## Zeitgleicher MCO-Fibonacci-Vergleich
Unter Diagramme: Auswahl der bis zu drei gelisteten MCO-Videos; Kursmarken, signed USD-Differenz und prozentuale Abweichung. Explizite Analysezeit inklusive Datum/Zeitzone, eindeutige Zeitebene und Spot-Basis werden aus benachbarten bestätigten Untertiteln übernommen. Uploadzeit und Videosekunden sind kein Ersatz. Ohne Nachweise bleibt die Abweichung offen. Historische Bob-Werte werden mit dem heutigen bestehenden Pivot-Algorithmus aus ausschließlich damals geschlossenen echten OHLC-Kerzen nachberechnet und so beschriftet; der angezeigte Goldkurs ist der letzte damalige Kerzenschluss. Keine Signal-/Lernwirkung. Chartpunkte aus sparsamen Beobachtungen und Kerzenlücken sind ausgeschlossen.

Zeitfallback: Ein belegter Originalzeitpunkt hat immer Vorrang. Sonst kann ein explizit als aktuell genannter Goldkurs gegen echte historische OHLC-Spannen abgeglichen werden. Suchfenster: genanntes Datum mit Zeitzonenpuffer, sonst ausdrücklich angenommene 72 Stunden vor einer bestätigten Veröffentlichung. Ein einzelner zusammenhängender Trefferbereich bis 30 Minuten liefert seinen Mittelpunkt als markierte Zeitschätzung, mitsamt Zeitbereich, Suchannahme und Archivabdeckung. Mehrfachtreffer bleiben mehrdeutig. Fibonacci-Ziele sind keine aktuellen Goldkurse. Geschätzte Zeitzuordnungen wirken nur auf diese Darstellung.


## Allgemeiner MCO-Wertevergleich
Der Vergleich sammelt zusätzlich eindeutig beschriftete Zahlen aus Untertiteln: aktuellen Goldkurs, EMA/SMA, RSI, ADX/DMI, ATR, MACD, Bollinger, Stochastik, VWAP, Unterstützung/Widerstand, Tageshoch/-tief, Einstieg, Stopp und Ziel. Nicht zugeordnete numerische Originalaussagen bleiben aufklappbar; Limits werden angezeigt. Nicht gesprochene Einblendungen sind nicht automatisch erfasst.
Für alle Werte gilt dieselbe Originalzeit-/Schätzzeit-Priorität. Historische Indikatoren werden mit Bobs Funktionen berechnet, nur mit expliziten Perioden und passender Zeitebene/Basis. Echte Null- und negative MACD-Werte bleiben erhalten. Oszillator-Differenzen sind Punkte, keine Prozent-Rendite. Einzelne Diagramme haben getrennte Skalen. Unterstützungen, Widerstände, Tagesextrema, VWAP, geglättete Stochastik sowie Trade-Pläne bleiben ohne identische Definition/Sitzung/Szenario sichtbar, aber ohne erfundenen Bob-Vergleich. ATR-Glättung und Initialisierungsunterschiede sind beschriftet. Kein Einfluss auf Signale, Lernen oder Orders.
