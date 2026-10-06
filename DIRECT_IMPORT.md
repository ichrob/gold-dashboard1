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
