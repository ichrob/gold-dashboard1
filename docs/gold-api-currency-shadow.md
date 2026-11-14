# Gold-API spot FX parity shadow (13 November 2026)

This is an isolated one-shot research utility, NOT a new production FX source.
There are no subscriptions, background jobs, cron triggers, push messages,
DEGIRO reads, market-ranking overrides or real-money order paths.

Gold-API.com documents free, no-key spot endpoints for XAU quoted in USD, EUR
and CHF. Original quote clocks use updatedAt and provider data refreshes about
every 30 seconds. Sources: https://gold-api.com/faqs and
https://gold-api.com/terms .

The helper gold_api_currency_shadow.py derives indicative USD-to-EUR,
USD-to-CHF and CHF-to-EUR parity ratios from exactly three contemporaneous
XAU spot observations. It rejects stale/future timestamps, clocks more than
5 seconds apart, identity errors, NaN, invalid prices and missing legs.
These ratios are INFERRED from gold prices, not broker-executable FX quotes.

The optional compare_to_live_fx helper checks a distinct original FX source
and returns only the percentage disagreement, not an approval or a replacement.
The returned result intentionally does not use Bob's live FX rate schema.
No module in production imports or schedules this utility. Bob's existing
FX feeds and product model remain unchanged.

Test: python -m unittest test_gold_api_currency_shadow.py

Before any later use in offline paper studies, validate live provider
response schemas, source times and repeated observations. Never use this
estimate as an original FX quote, DEGIRO venue, bid/ask or product price.
