# Issuer import check — 6 October 2026

Read-only checks during the Swiss trading morning, no orders or paid services.

## BNP

The existing public product-header endpoint returned identified PJ9NB9 quotes
at 08:29:15 Zurich. The parser accepted the dated snapshot. The earlier missing
`bidDate` was therefore an incomplete/off-hours response, not proof of a renamed
field. A repeated identical URL returned the same old response at 08:31:52,
despite `Cache-Control: no-cache`. The intermediary responsible is not known.

A standard cache-busting query returned distinct current source timestamps at
08:32:57. The repaired adapter was exercised again at 08:34:06: the oldest quote
component was three seconds old. Bid, ask, leverage and response clocks remain
independent; freshness still expires after 90 seconds. The query bucket is 15
seconds, matching the local cache, and never serves as price-time evidence.

The adapter now preserves verified static conditions if quote data is incomplete.
Ratio, underlying, currency, explicitly stated product type and open-ended
maturity can be retained. KO and strike stay observations without a verified
effective date: neither responseDate, keyFigures.lastUpdate nor the future
determinationDate proves their validity date. Missing quote clocks cannot
generate a price, fresh flag or eligibility. Confirmed terminal status wins over
an active secondary-source result. Errors retain fixed diagnostic codes through
routing and comdirect enrichment, without exposing raw responses.

## SG

Public product/AllProperties requests identified DE000FG7K283 (7127448).
The 08:29 and 08:33 Zurich checks returned `TimeStamp` 2026-10-06T06:16:22.647,
without an offset, even with a distinct URL. It is at least about 13–17 minutes
old under the plausible UTC interpretation; treating it as European local time
would make it older. Separate ask/leverage times were not supplied. The endpoint
also advertises `Cache-Control: public, max-age=300`.

StrikeBarrierUpdateTime was 2026-10-06T01:01:26.677, also without an offset.
This is separate raw issuer evidence, not an executable quote clock. The live
SG adapter remains disabled; this change does not reactivate SG or onvista.

## Access and limits

HTTP 200 proves technical reachability, not permission for permanent reuse.
SG's published legal notices require prior written permission for covered
reproduction/caching. BNP's German site states a Germany/Austria/Luxembourg
resident audience. No new provider permission, registration or contract was
obtained. No new SG feed is enabled. BNP changes repair the existing adapter.

Sources:
- https://derivate.bnpparibas.com/nutzungsbedingungen/
- https://www.sg-zertifikate.de/contentmgmt/media/13ihwnzp/legal_information_de-de.pdf

The frozen four-day comparison and its policy, market collection, all stored
trades and user data are unchanged. This check does not prove perpetual uptime,
automatic complete product approval or an available licensed SG real-time feed.

## Follow-up at 08:45 Zurich

BNP PJ9NB9 was retested through the repaired adapter: bid EUR 12.07, ask EUR
12.08, both dated 08:45:27.014 Zurich, checked at 08:45:31.589. Identity and
quote freshness passed. This still does not date KO/strike or grant a trade.

The SG website's own chart service requests `Prices/Live?productId=7127448`.
At 08:45:32.254 it returned HTTP 200 with bid EUR 10.50, ask EUR 10.51 and
point date `2026-10-06T08:45:30.953+02:00`, about 1.3 seconds old. The product
response independently confirmed DE000FG7K283, CBDE, XAUUSD and EUR/USD
currencies. Thus the AllProperties quote-time limitation does not apply to
every SG endpoint. This is a dated chart point, not evidence of independent
bid/ask or leverage clocks, quantities or dated executable terms.

A pure, offline parser now validates known SG product IDs and chart identity,
price order, explicit timezone, chronology and freshness. The real response
passed. Evidence stays under `chartEvidence`; it cannot set found, fresh or
eligible. No chart data is automatically fetched or persisted in Bob.

DE000FG7K283 now routes to SG diagnostics instead of an unsuccessful BNP
lookup. The diagnostic correctly says unattended provider permission is
unconfirmed rather than attributing the block to the user's superseded request.
Runtime SG network calls remain blocked. The legal PDF was retrieved again:
its caching/reproduction restriction still requires clarification before any
permanent import. No access restrictions were bypassed or contracts obtained.

This follow-up changes neither the frozen comparison nor user/trade data.

## Calculated chart gearing — 09:37 Zurich

A separately dated issuer leverage is not intrinsically necessary for research
gearing. The offline SG chart path now supports
`Gold USD × USD/EUR × (1 / SG Ratio) / chart Ask EUR` for identified simple
spot turbos with explicitly supported currency treatment. SG's Ratio `10:1`
means multiplier 0.1, not 10. The issuer's undated CurrentLeverage is ignored.

Each chart, gold and FX observation must carry its own explicit timezone and
be no more than 60 seconds old, with at most 15 seconds between inputs. The
calculated evidence retains the oldest input time and every individual source
time. Futures, unsupported models, stale/missing clocks and unknown ratio
units are rejected. It never promotes a chart to executable quotes or grants
product eligibility. It performs no network requests or persistence.

Fresh SG product and chart requests succeeded at 09:37:38 Zurich. In this test
environment the existing exchangerate.dev FX endpoint returned HTTP 403 and
the xaus spot request timed out. Therefore a complete current real-input
gearing test did not pass; synthetic formula and rejection tests did pass.
No access controls were bypassed. The official SG Markets API documentation
requires client credentials and authorization; it does not establish free
access to these retail ISINs. Automatic SG import remains disabled pending
provider permission and suitable complete inputs. BNP is unchanged.

- https://shared.sgmarkets.com/sp-help-center-content/external-api-doc.html

## 7 October — authorized direct website import

The user confirmed that SG's positive reply of 7 October responds to the
private-use request including 30-second retrieval. The previous permission
block is removed for SG website requests. No onvista path is re-enabled.

`sg_direct.py` now imports the verified direct IDs for DE000FG7K283 and
DE000FG4JXV7 through Products, AllProperties and Prices/Live. Shared serialized
requests and cached errors enforce at least 30 seconds between refreshes per
product per process. Metadata is reused for five minutes; source clocks never
advance on cache hits. The existing product refresh in the open application
requests updates every 30 seconds; this is not a new always-on collection job.

Identified ratio, currency, underlying, product type and explicitly open-ended
maturity are handed to the existing condition UI. KO and strike remain raw
observations when their effective timezone/date cannot be established. Dated
chart pairs are retained as chartEvidence and shown in the diagnostic reason,
with freshness recomputed on each read. They do not manufacture a leverage
clock or override a verified screenshot. Unknown direct IDs retain a technical
verification diagnostic, not the obsolete permission claim. BNP is unchanged.

Regression coverage includes wrong product identity, inactive products, source
outage, metadata retention, stale chart evidence, original clocks and the
30-second boundary. Automatic trade/product release remains gated by complete
valid evidence. No trades are performed.

## 7 October — actual saved-list completeness audit

The authenticated Bob view contained ten historical list products. A generic
`BNP Unlimited` screenshot type overrode BNP's verified `Unlimited Long` term;
the missing-type reason was then mislabeled as KO because it contained
"Knock-out". Verified issuer conditions now take precedence over generic list
labels; conflicting ratios and daily strike/KO evidence still block. Product
source attribution now follows the actual chosen terms source.

SG identities additionally verified: FG5NMF2=6953148 (ended, status 8),
FG7K3L2=7127648 (ended, status 8), FG6XB39=7072444 (active),
FG309G0=7032167 (active, exact GCZ26 identity), FE4UF01=6628472 (factor,
classification 44100, excluded). No price request is made for excluded factors
or ended products. Their cards request no further screenshots.

SG StrikeBarrierUpdateTime explicitly dates strike/barrier changes. For the
current calendar date only, the adapter stores that date without inventing an
intraday timestamp or timezone. Current real responses from FG5GUT0, FC1CHB7,
FG7EPT1, FG6XB39 and FG309G0 passed through the backend and frontend terms
checks. FG4JXV7 is a Classic with fixed strike/barrier and expiry 18 December
2026; fixed contract evidence is separate from a daily date and expires with
its contract or an unrefreshed verification. Product model reference:
https://www.sg-zertifikate.de/contentmgmt/media/c5bihw1s/bro_turbo-optionsscheine.pdf

Per-product locks preserve 30-second source throttling without letting one slow
SG request serialize every other SG product. Exact futures contract identity
is imported as identified metadata; no future gets spot-trade eligibility.

Remaining limitation: SG chart pairs are dated observations, while
CurrentLeverage does not supply its own source clock. These changes do not
promote chart evidence to executable quotes. The sampled comdirect FG5GUT0
page had old/different strike values (4073.3331 versus SG 4074.353817) and an
undated leverage; it cannot close that evidence gap. BNP's complete current
snapshot and dated terms succeeded, but intermittent retrieval failures remain
possible. No source clocks, terms validity dates or missing values are invented.


### Follow-up: source priority and backup feasibility (2026-10-07)

The direct issuer is now queried before comdirect. Verified SG direct imports,
dated BNP terms, and issuer-confirmed terminal status do not wait for a secondary
HTML request. comdirect remains the static-data fallback when issuer evidence is
incomplete. Previously a secondary request could consume its timeout before the
primary quote was even requested. Permanently confirmed knockouts in TERMINAL
still short-circuit all network requests. Quote freshness rules are unchanged.

The BNP public website bundle advertises push.bnpparibas.com with adapter set
SmarthouseFeed and fields bid, ask, quotetime, currentleverage. A public generic
TLCP client probe returned CONERR 71, "License not valid for this Client type".
No adapter was enabled and no alternate client identity was attempted. This is
not a working backup. Direct HTTP probes of the BNP header and Stuttgart product
page returned 403 in this execution environment; that does not establish an
outage on Render or permission to bypass restrictions. Earlier BNP responses
were several minutes old even with unique cache keys; request time must not be
used to repair their source timestamps.

Validation: 76 Python regressions passed, including primary-source priority,
secondary fallback, terminal exclusions, and rejection of undated/stale data.
Full automatic fresh quote + leverage coverage remains unresolved.
