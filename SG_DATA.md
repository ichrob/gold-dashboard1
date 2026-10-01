# SG gold turbo data

Bob has verified source mappings for the seven SG ISINs in
`sg_quotes.PRODUCT_IDS`. Eligibility also requires the issuer to confirm XAU/USD
spot as the underlying; gold futures remain excluded. Unknown ISINs remain
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
