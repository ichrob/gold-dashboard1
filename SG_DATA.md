# SG gold turbo data

Bob has verified source mappings for the seven SG ISINs in
`sg_quotes.PRODUCT_IDS`. Eligibility also requires the issuer to confirm XAU/USD
spot as the underlying. FG309G has a separate exact-contract futures research
view; futures remain excluded from the spot ranking. Unknown ISINs remain
blocked until their source identity has been verified. BNP uses its existing
independent adapter.

## Data and provenance

- SG `Products` and `AllProperties`: identity, XAU/USD basis, direction, KO,
  financing strike and reciprocal issue ratio.
- onvista product snapshot: separately dated SG OTC bid and ask. Only contributor
  `SGED`, venue `@_SGED`, EUR prices, `RLT` quality and positive sizes are accepted.
  The product ID, ISIN, issuer, direction and ratio must agree. SG supplies the
  authoritative KO and financing strike; delayed secondary barrier differences
  are recorded and do not replace the issuer values.
- XAUS compact spot: USD per troy ounce and `price_as_of`.
- exchangerate.dev USD/EUR: `live`, open session, `data_updated_at` and the EUR
  `effective_at`. The response timestamp, goldprice.dev conversion timestamp,
  and daily reference FX are **not** evidence of a current FX observation.

Every changing input must be at most 60 seconds old and no more than 5 seconds
in the future, on both server and browser. Cache hits retain all observation
times. Old/unknown/failed data, inactive products, breached barriers, weekends
and times outside the standard SG OTC session (08:00–22:00 Europe/Berlin) are
blocked. Actual current two-sided quotes and sizes are still required during
the nominal session; the schedule alone does not establish tradability.

## Calculated gearing, not issuer leverage

SG's public metadata does not independently date its `CurrentLeverage` field.
onvista's calculated figures may be delayed. Neither is used as a current Hebel.

For simple non-quanto Classic, Unlimited and BEST gold turbos (SG classifications
43, 45 and 47), Bob displays a clearly labelled **rechnerischer Hebel (Näherung)**:

`XAU/USD spot × USD/EUR rate × fractional ratio / current ask in EUR`

This is absolute gearing under the unit-delta approximation (±1 according to
direction), with FX held constant. It is not a measured effective elasticity or
an SG-published leverage value. Premiums, changing FX, delta departures, funding
costs and issuer pricing can change realized returns. Options, quanto products,
other underlying assets and unverified turbo variants are excluded.

`leverageAt` is the oldest contributing observation, not calculation/request
time. The actual gold and both FX observation fields are also checked separately
so a future input cannot be concealed by taking a minimum.

The estimate is identified in the enrichment result and on each ranking card.
The quotes are SG OTC quotes relayed by onvista, not DEGIRO executable quotes.
Bob does not place orders; the DEGIRO price and product conditions still need
checking before an order.

## Public references

- https://www.sg-zertifikate.de/knock-out-produkte
- https://www.sg-zertifikate.de/produkte/handel/handelspartner
- https://www.onvista.de/derivate/Knock-Outs/340459583-FG4JXV-DE000FG4JXV7
- https://xaus.com/api
- https://exchangerate.dev/docs/api-reference
- https://exchangerate.dev/learn/gold-price-local-currency

No new account, API key, subscription or paid service is required. The FX cache
is shared across product requests and uses a 45-second TTL (at most 80/hour per
running Bob process under continuous polling); missing/failing inputs fail closed.

## Gold futures research (FG309G)

SG confirms `DE000FG309G0` as `C_CMX_GOLD_F_Z26`, RIC `GCZ26`, underlying
ISIN `XC0009656924` (Gold Future Dec 2026). The secondary snapshot must match
instrument `188570012`, notation `317423266`, USD and exchange `CXE`. A rollover
or changed contract identity fails closed; no continuous/front-month symbol or
XAU/USD quote is substituted.

`futureResearch` is a separate non-executable response envelope. It contains
separately dated SG OTC bid/ask, official SG KO/strike, the exact futures contract,
and (when supplied with a valid observation time and matching notation) the
secondary dated underlying figure. `datetimeCalculation`, request time and
undated `referencePrice` never date the underlying observation.

A research-only approximate gearing and distance to current SG KO may be shown
using a futures observation no older than 30 minutes, current bid/ask and both
current FX observation timestamps. This mixes observation times and is explicitly
labelled as an estimate using a delayed/unverified-real-time basis. It is neither
current issuer leverage nor a current KO distance. The 30-minute limit is solely
a research display limit; it never relaxes the 60-second trading gate. Cache hits
recompute ages and remove estimates when product/FX inputs expire.

Even if a futures observation is recent, automatic eligibility remains false:
real-time source quality and a trend/MTF history for the exact contract have not
been established. Both live and manual screenshot ranking reject known futures;
no spot LONG/SHORT signal can authorize them. A missing FX feed still preserves
the dated product research without an estimate.

CME's free public quotes are delayed by at least ten minutes:
https://www.cmegroup.com/trading/about-all-delayed-quotes.html
No paid feed, new service, account or subscription was added.


## Calculated GCZ26 price using Investing.com CFD observations

`futureResearch.calculatedFuture` is explicitly labelled **Berechneter
Future-Kurs**, with `isExchangeRealtime=false` and `eligible=false`.
The fixed formula is `F(t₀) + CFD(t) − CFD(t₀)`: the last dated, exact GCZ26
underlying observation plus the observed CFD dollar change since that time.
The futures/CFD basis is assumed constant until the next reference observation.
This is an uncalibrated estimate, not a guaranteed accurate real-time price.
No fitted beta or forecast drift is added without validation data.

The free public Investing.com Gold page's structured data is checked for
instrument 8830, USD/troy ounce, an active/open, non-delayed CFD, declared
December 2026 month, 2026-12-29 settlement and 2026-08-27 rollover. Despite the
page's GC1! metadata label, these are CFD observations, never exchange quotes.
Only the quote's epoch-millisecond `lastUpdateTime` dates the CFD. The other
relative-instrument quotes and undated bid/ask are not used. An unavailable,
blocked, redirected or changed page does not become a fabricated observation.
There is no public Investing.com API or guaranteed page access/refresh rate.

One shared background daemon starts when futures research is requested, reads
the public page at most once per 30 seconds and stays active for one hour after
the last fresh research request. It does not block /api/live or any running
monitor. It records actual observations, without rewriting cached timestamps.
The in-memory, bounded one-hour buffer resets on deployment/restart. After
startup, the calculation waits until the buffer covers a real reference time;
this can take the source's full delay (typically 10–20 minutes or longer).
No CFD history is invented to conceal that warm-up.

CFD(t₀) is linearly interpolated between collected observations bracketing t₀,
each at most 30 seconds away, or directly observed if a timestamp matches.
Interpolation itself is approximate; both bracketing timestamps and their
maximum distance are retained. The reference may be at most 30 minutes old,
the latest CFD observation at most 60 seconds old, and the intervening buffer
must have no gap exceeding 90 seconds. Future timestamps, rollover, missing
references and outdated inputs remove the numeric estimate. Browser research
refreshes every 30 seconds and hides stale estimates as their timestamps age.
The calculation time never substitutes for an observation time.

The dated reference price remains visible separately. The calculated field
never replaces Bob's XAU/USD feed or supplies executable product/ranking inputs.
Delayed-reference gearing/KO estimates remain separately labelled, and automatic
futures eligibility remains blocked pending exact-contract trend/MTF data.
Reference/CFD basis changes, interpolation, page caching and differing quote
conventions are material sources of error. No precision or statistical
confidence interval is claimed without matched validation observations.

Official explanation of the CFD/exchange distinction and lack of public API:
https://www.investing-support.com/hc/en-us/articles/115003804125-Why-is-Prev-Close-Different-from-the-Close-Price-in-the-Historical-Data-Table-on-Investing-com
https://www.investing-support.com/hc/en-us/articles/115005473825-Do-You-Offer-API-Access-at-Investing-com


## Fallback policy for other DEGIRO products

A directly observed, fresh eligible issuer quote takes precedence. If that
quote becomes unavailable or outdated, Bob tries a verified product model and
labels any output **Berechneter Produktkurs**. No calculated number is inserted
into executable `price`, `bid`, `ask`, leverage or trade-eligibility fields.
Browser ranking also rejects a response explicitly marked `priceKind=calculated`.

For the verified simple, non-quanto SG XAU/USD turbos (classifications 43,45,47)
Bob can retain an observed bid/ask reference whose gold, both FX observations,
and product observation times are all within five seconds of one another.
Without such a reference it displays why a calculation is unavailable.
The anchored model for each side is:

`P(t) = P₀ + direction × ratio × [(XAU(t) − strike) × FX(t) − (XAU₀ − strike) × FX₀]`

`direction=+1` for LONG and `−1` for SHORT; ratio is the confirmed fractional
ratio and FX is EUR per USD. The model holds the original EUR premium and spread
constant, with unit delta. It accounts for current FX changes including their
impact on the funding strike, rather than applying a fixed advertised leverage.
It is an approximation, never a published issuer or DEGIRO quote. Conditional comparison requires measured empirical errors.

Current gold and FX observations must each be at most 60 seconds old and within
15 seconds of each other. Reference age is capped at 30 minutes. Identity,
underlying, direction, ratio, current SG strike/KO and classification must agree;
changed terms require a new observed anchor. KO crossings, closed session,
expiry, source-integrity failures and stale inputs remove the numeric estimate.
A network outage may reuse a model only when the current issuer metadata still
matches all its terms. Current inputs retain their actual source timestamps.
There is no network call during cache-age recalculation. Anchors are bounded
and process-local, so a restart requires new observations.

Any other issuer-verified SG product on the exact GCZ26 identity can share the
existing GCZ26 underlying research/calculation feed. It must match all four
issuer fields (NMP, RIC, underlying ISIN and name). A separately verified OTC
product source is still required for that product's own price or gearing;
no reference product bid, ask, KO, ratio or leverage is copied to another ISIN.
New contract months require their own registered sources. Options, quanto,
other underlyings and BNP products without verified model parameters do not
receive a fabricated fallback. The policy is direct quote, verified estimate,
or an explicit unavailable state, all within the existing free services.


## Conditional comparison and empirical validation

Frozen calculations are matched once to dated observations within five seconds.
Identity and reference-age buckets (up to 60s, 300s, 900s, 1800s) remain separate.
Readiness requires 20 distinct matches spanning at least ten minutes in the
applicable bucket and a validation received within 30 minutes. Product models
also check older anchors before reanchoring, using independent current gold/FX,
never the current observed product bid/ask in the forecast. Both bid and ask
must qualify. This is a deterministic model check, not a guaranteed error bound
or a statistical confidence interval. The measured maximum error, floored at
EUR 0.01 / USD 0.10, supplies comparison spans. Predictions, matches and anchors
are bounded and process-local; deployments and restarts reset readiness.

GCZ26 indicators use Yahoo's delayed GCZ26.CMX history, verified as COMEX USD
Gold Dec 26. The background collector requests 5m/5d and 1h/6mo history every
minute while requested. Only closed valid bars are retained; 15m and 4h bars
require complete constituent candles. Each frame needs 220 bars. EMA20/50/200,
MACD, RSI, ATR, confirmed pivots and Fibonacci levels are displayed separately
from spot. Direction requires all four frames to agree; CFD nowcasts do not
enter indicators or add another technical source. Errors, missing history and
stale analysis produce ABWARTEN, without blocking the live endpoint.

The conditional comparison groups candidates by underlying contract and
direction. Current identity, session, terms, timestamps, timing and KO/funding
checks still apply. Scores and risk metrics are evaluated at comparison-span
corners. A favorite requires separated score ranges (two-point margin), with
no unresolved same-direction candidate in its group. The observed-quote list
remains distinct. Every conditional result requires checking the current
DEGIRO ask and product conditions; it grants no automatic trade approval.


## Gold-API replacement (2026-10-01)

The runtime collector no longer requests Investing.com. It uses the documented
free, keyless Gold-API endpoint `https://api.gold-api.com/price/XAU` once every
30 seconds, validating XAU, Gold, USD, exchangeRate=1 and the original
`updatedAt` (at most 60 seconds old). This bypasses the XAUS intermediary;
XAUS attributes its spot data to this same provider, so these are not treated
as independent sources. The CFD parser/formula remain solely for regressions.

The replacement formula is `F_ref * Spot_now / Spot_ref`, holding the dated
Future/Spot factor fixed over a maximum 30-minute reference horizon. It is
an assumption, not an exchange realtime quote or a fitted carry-rate model.
Spot reference alignment is unchanged: both actual bracketing observations
within 30 seconds, interpolation explicit, no observation gap over 90 seconds.
Only ticks actually gathered by Bob count; no invented history at startup.
Gold-API spot errors use their own identity/method/horizon key and cannot
inherit earlier CFD calibration. Own GCZ26 indicators still use exact-contract
Yahoo history and never count spot movement as independent confirmation.


## Screenshot current-state assessment (2026-10-02)

Each confirmed product card now shows a read-only partial assessment. Gold-spot
scenarios require a genuine XAU/USD bundle and its original `spot_price_as_of`;
request time, response `updated_at`, and device/upload time cannot date a price.
The live bundle now retains the provider's price observation timestamp.

The signed distance to the stated KO is displayed separately from confirmed
current KO: a product-name barrier is a scenario input, not proof that the barrier
is still valid. A crossing is not proof of a past issuer KO event. Generic Gold
without confirmed underlying metadata is explicitly a spot scenario. Known or
named futures never fall back to spot or continuous GC=F. Exact-contract
nowcasts remain labelled estimates, not exchange realtime.

Gearing uses a validated existing product estimate or dated quote/FX and an
exact-contract basis. An old screenshot ask, the name's LV and an unconfirmed
Bv value cannot manufacture current gearing. Screenshot spread remains an
observed momentary spread. All missing source/time/identity evidence stays
visible; this panel never changes ranking, eligibility or execution fields.
No new network source, paid account, service, order or provider permission
is introduced by this assessment.
## Collection recovery (2026-10-02)

The autonomous collector uses the dated last-trade quote from the existing
Yahoo GCZ26.CMX analysis feed, verifying COMEX, USD, Gold Dec 26, FUTURE and
the original regularMarketTime. Its fixed fallback is the already registered
onvista GCZ26 underlying, validating the product-page and underlying/notation
identities on each request. The newest usable dated reference is shared with
SG future calculations, with its source preserved separately from product data. SG product metadata, OTC bid/ask and FX availability no longer
block collection of the separate dated future reference. Neither this reference
nor a calculated future grants product eligibility. `researchAvailable` identifies
successful SG research separately from the executable-quote `found` flag.

Each collection cycle merges real source-timestamped spot observations from the
durable archive. This repairs a process-local gap when another scanner instance
saved the missing ticks. An outage that no instance observed remains a genuine
gap; the existing alignment, 90-second continuity, 60-second spot freshness and
30-minute reference-age checks still block calculation until a usable reference
falls within newly collected continuous observations. No history is fabricated.

The free GitHub collection-health schedule runs every five minutes in the Swiss
collection window to reduce idle-service pauses. Scheduled Actions can be delayed
and free Render services can sleep or restart; this is not guaranteed uptime.
Diagnostics retain source failures during backoff and report the actual estimate
failure reason and the ages of reference and spot inputs.

The exact-contract Yahoo reference and analysis share one chart request per
interval per minute. Cache hits retain provider timestamps, and HTTP 429 /
Retry-After backoff is shared by both consumers. Reference polling cannot
bypass the history source's wait period.

## Separate issuer barrier evidence

SG AllProperties may contain StrikeBarrierUpdateTime independently of BIDTIME.
Bob preserves that raw date, the USD barrier, and the retrieval time in
metadata.koEvidence. Missing offsets stay unknown; retrieval time never becomes
an issuer update time. The screenshot assessment displays this evidence even
when no fresh product quote exists. It does not establish a validity interval,
confirm a past KO event, refresh manual evidence, or grant trading eligibility.
Malformed or absent barrier-update dates produce no dated barrier evidence.


## Investing.com display card (2026-10-05)

The fourth gold card independently reads the public German Gold page (instrument
8830, USD per troy ounce, CFD) at most once per 30-second market-card cache.
It retains the original lastUpdateTime and provider changePcr. The label
“Echtzeit CFD · laut Investing.com” requires an active, open, non-delayed CFD
and a source timestamp no older than 120 seconds. Old/closed/delayed quotes
remain explicitly labelled; failures cannot invent a price or renew its time.
This display does not feed the Spot/Future model, ranking, or trade monitoring.
There is no guaranteed second-by-second stream or public API entitlement.
